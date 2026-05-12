import os
import json
import random
from typing import Optional

import google.generativeai as genai
from fastapi import FastAPI, Request, Form, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, create_engine, select
from dotenv import load_dotenv

from models import SQLModel, SessionStats, TopicStats, Mistake, QuestionPool, sqlite_url, create_db_and_tables

load_dotenv()

# --- Configuration & Constants ---
TOPICS = [
    {"id": "punctuation", "label": "Punctuation", "icon": "✱"},
    {"id": "transitions", "label": "Transitions", "icon": "→"},
    {"id": "subject_verb", "label": "Subject-Verb Agreement", "icon": "⇄"},
    {"id": "modifiers", "label": "Modifiers", "icon": "◎"},
    {"id": "parallel", "label": "Parallel Structure", "icon": "≡"},
    {"id": "sentence_boundary", "label": "Sentence Boundaries", "icon": "¶"},
]

TOPIC_INSTRUCTIONS = {
    "punctuation": "Test one of: comma usage (lists, introductory clauses, FANBOYS conjunctions, nonrestrictive phrases), semicolons between independent clauses, colons before lists or explanations (left side must be complete sentence), or dashes for emphasis or paired nonessential interruptions.",
    "transitions": "Test transition words: contrast (however, nevertheless, in contrast), addition (furthermore, moreover, in addition), cause-effect (therefore, consequently, thus), illustration (for example, for instance), sequence (first, subsequently, finally). Make the logical relationship clear from context so only one transition is correct.",
    "subject_verb": "Test tricky agreement: subject separated from verb by a long prepositional phrase, inverted sentence structure, collective nouns, indefinite pronouns (each, every, neither), compound subjects with or/nor.",
    "modifiers": "Test dangling or misplaced modifiers. The [BLANK] should be a clause or phrase that is either correctly or incorrectly placed. Distractors should dangle or ambiguously modify the wrong noun.",
    "parallel": "Test parallelism in a list, comparison, or correlative conjunction (not only…but also, either…or, both…and). The [BLANK] must complete the parallel structure. Wrong choices break the grammatical pattern.",
    "sentence_boundary": "Test run-ons, comma splices, or fragments. Choices should offer: correct punctuation, comma splice, run-on (no punctuation), and a fragment or unnecessary connector.",
}

# --- App Setup ---
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

engine = create_engine(sqlite_url)

# Temporary store for the current question to validate answer
current_q_cache = {}

def get_session():
    with Session(engine) as session:
        yield session

async def top_up_pool(topic_id: str, api_key: str, model_name: str, instr: str, topic_label: str):
    """Background task to ensure the pool has unused questions."""
    with Session(engine) as session:
        # If we have official questions in the pool, we don't need to generate
        unused = session.exec(
            select(QuestionPool).where(QuestionPool.topic_id == topic_id, QuestionPool.used_count == 0)
        ).all()
        
        # We only top up if we have VERY few questions left (< 3)
        if len(unused) >= 5 or not api_key:
            return

        print(f"--- BATCH GENERATING for {topic_id} ---")
        prompt = f"""Generate 3 distinct DSAT Writing section question objects focused on: {topic_label}
{instr}
Return ONLY valid JSON as a LIST of objects:
[
  {{
    "passage": "...",
    "question": "...",
    "choices": ["...", "...", "...", "..."],
    "correct": 0,
    "explanation": "..."
  }},
  ...
]"""
        try:
            genai.configure(api_key=api_key)
            m_name = model_name if model_name.startswith("models/") else f"models/{model_name}"
            model = genai.GenerativeModel(m_name)
            response = model.generate_content(prompt)
            
            if not response.candidates: return

            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"): text = text[4:]
            
            import re
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                batch_data = json.loads(match.group())
                for q_data in batch_data:
                    new_pool_q = QuestionPool(
                        topic_id=topic_id,
                        passage=q_data["passage"],
                        question=q_data["question"],
                        choices_json=json.dumps(q_data["choices"]),
                        correct_index=q_data["correct"],
                        explanation=q_data["explanation"],
                        used_count=0
                    )
                    session.add(new_pool_q)
                session.commit()
        except Exception as e:
            print(f"--- BATCH ERROR: {str(e)} ---")

@app.on_event("startup")
def on_startup():
    create_db_and_tables(engine)
    with Session(engine) as session:
        if not session.get(SessionStats, 1):
            session.add(SessionStats(id=1))
            session.commit()

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, session: Session = Depends(get_session)):
    stats = session.get(SessionStats, 1)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "topics": TOPICS,
            "stats": stats
        }
    )

@app.get("/debug-models")
async def debug_models(api_key: str = None):
    if not api_key:
        return "Please provide an api_key parameter: /debug-models?api_key=YOUR_KEY"
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        model_list = []
        for m in models:
            model_list.append({
                "name": m.name,
                "supported_methods": m.supported_generation_methods,
                "display_name": m.display_name
            })
        return model_list
    except Exception as e:
        return {"error": str(e)}

@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request, background_tasks: BackgroundTasks, topic_id: str = Form(...), api_key: str = Form(None), model_name: str = Form("models/gemini-2.5-flash"), session: Session = Depends(get_session)):
    topic_label = next(t["label"] for t in TOPICS if t["id"] == topic_id)
    instr = TOPIC_INSTRUCTIONS.get(topic_id, "")

    # 1. PRIORITY: Check the local pool for unused official questions
    pool_q = session.exec(
        select(QuestionPool).where(QuestionPool.topic_id == topic_id, QuestionPool.used_count == 0)
    ).first()
    
    if pool_q:
        pool_q.used_count += 1
        session.add(pool_q)
        session.commit()
        
        q_data = {
            "passage": pool_q.passage,
            "question": pool_q.question,
            "choices": pool_q.choices,
            "correct": pool_q.correct_index,
            "explanation": pool_q.explanation,
            "topic_id": topic_id,
            "topic_label": topic_label,
            "is_official": True
        }
        current_q_cache["last"] = q_data
        
        # Trigger top-up in background if we're running low
        if api_key:
            background_tasks.add_task(top_up_pool, topic_id, api_key, model_name, instr, topic_label)
            
        return templates.TemplateResponse(
            request=request,
            name="components/question_card.html",
            context={"q": q_data}
        )

    # 2. FALLBACK: Use Gemini if pool is empty
    if not api_key:
        return HTMLResponse(content="""
            <div class="question-card" style="border-color: var(--wrong-border); background: var(--wrong-bg);">
                <div class="q-question" style="color: var(--wrong-text);">
                    <strong>Pool Exhausted:</strong> No official questions left for this topic. Please enter your Gemini API key to generate new ones.
                </div>
            </div>
        """)

    genai.configure(api_key=api_key)
    m_name = model_name if model_name.startswith("models/") else f"models/{model_name}"
    
    prompt = f"""Generate a DSAT Writing section question focused on: {topic_label}
{instr}
Return ONLY valid JSON:
{{
  "passage": "Formal academic passage with [BLANK].",
  "question": "Standard SAT question stem.",
  "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
  "correct": 2,
  "explanation": "Brief rule-based explanation."
}}"""

    try:
        model = genai.GenerativeModel(m_name)
        response = model.generate_content(prompt)
        
        if not response.candidates:
            raise Exception("No candidates returned from API.")

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"): text = text[4:]
        
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            q_data = json.loads(match.group())
        else:
            raise Exception("Failed to parse JSON.")
        
        q_data["topic_id"] = topic_id
        q_data["topic_label"] = topic_label
        current_q_cache["last"] = q_data
        
        return templates.TemplateResponse(
            request=request,
            name="components/question_card.html",
            context={"q": q_data}
        )
    except Exception as e:
        error_msg = str(e)
        return HTMLResponse(content=f"""
            <div class="question-card" style="border-color: var(--wrong-border); background: var(--wrong-bg);">
                <div class="q-question" style="color: var(--wrong-text); font-weight: 600;">
                    API Error: {error_msg}
                </div>
                <div style="font-size: 11px; color: var(--text-secondary); margin-top: 15px;">
                    Try refreshing or selecting a different model.
                </div>
            </div>
        """)

@app.post("/answer", response_class=HTMLResponse)
async def answer(request: Request, picked: int = Form(...), session: Session = Depends(get_session)):
    q = current_q_cache.get("last")
    if not q:
        return "Error: No active question."
    
    correct = q["correct"]
    is_right = picked == correct
    
    # Update Session Stats
    stats = session.get(SessionStats, 1)
    stats.total += 1
    if is_right:
        stats.correct += 1
        stats.streak += 1
        stats.best_streak = max(stats.streak, stats.best_streak)
    else:
        stats.streak = 0
        mistake = Mistake(
            topic=q["topic_label"],
            passage=q["passage"],
            question=q["question"],
            choices_json=json.dumps(q["choices"]),
            correct_index=correct,
            picked_index=picked,
            explanation=q["explanation"]
        )
        session.add(mistake)
    
    t_stats = session.get(TopicStats, q["topic_id"])
    if not t_stats:
        t_stats = TopicStats(topic_id=q["topic_id"])
        session.add(t_stats)
    t_stats.total += 1
    if is_right:
        t_stats.correct += 1
    
    session.add(stats)
    session.commit()
    session.refresh(stats)

    return templates.TemplateResponse(
        request=request,
        name="components/answer_result.html",
        context={
            "is_right": is_right,
            "correct_index": correct,
            "picked_index": picked,
            "explanation": q["explanation"],
            "stats": stats
        }
    )

@app.get("/review", response_class=HTMLResponse)
async def review(request: Request, session: Session = Depends(get_session)):
    mistakes = session.exec(select(Mistake).order_by(Mistake.id.desc())).all()
    return templates.TemplateResponse(
        request=request,
        name="components/review_list.html",
        context={"mistakes": mistakes}
    )

@app.get("/stats", response_class=HTMLResponse)
async def stats_view(request: Request, session: Session = Depends(get_session)):
    overall = session.get(SessionStats, 1)
    topic_stats = session.exec(select(TopicStats)).all()
    topic_map = {t["id"]: t["label"] for t in TOPICS}
    
    return templates.TemplateResponse(
        request=request,
        name="components/stats_view.html",
        context={
            "overall": overall,
            "topic_stats": topic_stats,
            "topic_map": topic_map
        }
    )

@app.post("/reset-stats")
async def reset_stats(session: Session = Depends(get_session)):
    session.exec(SQLModel.metadata.tables["sessionstats"].delete())
    session.exec(SQLModel.metadata.tables["topicstats"].delete())
    session.exec(SQLModel.metadata.tables["mistake"].delete())
    session.add(SessionStats(id=1))
    session.commit()
    return HTMLResponse(content="Stats reset successfully. Refresh the page.")

@app.post("/clear-mistakes")
async def clear_mistakes(session: Session = Depends(get_session)):
    session.exec(SQLModel.metadata.tables["mistake"].delete())
    session.commit()
    return HTMLResponse(content="Mistakes cleared.")
