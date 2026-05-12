import requests
import json
from sqlmodel import Session, create_engine, select
from models import QuestionPool, sqlite_url

engine = create_engine(sqlite_url)

DOMAIN_MAP = {
    "Standard English Conventions": ["punctuation", "subject_verb", "modifiers", "sentence_boundary"],
    "Expression of Ideas": ["transitions", "parallel"]
}

def fetch_and_import():
    print("--- Fetching official questions from OpenSAT (Pinesat) ---")
    
    # Increased timeout and slightly smaller limit to avoid timeouts
    url = "https://pinesat.com/api/questions?limit=50"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            print(f"Error: Received status code {response.status_code}")
            return

        questions = response.json()
        if not isinstance(questions, list):
            print("Error: API did not return a list.")
            return

        print(f"Received {len(questions)} potential questions. Importing...")
        
        imported_count = 0
        with Session(engine) as session:
            for item in questions:
                domain = item.get("domain")
                q_obj = item.get("question", {})
                
                if not domain or not q_obj:
                    continue
                
                if "paragraph" not in q_obj:
                    continue

                existing = session.exec(
                    select(QuestionPool).where(QuestionPool.passage == q_obj.get("paragraph"))
                ).first()
                if existing:
                    continue

                topic_ids = DOMAIN_MAP.get(domain, [])
                if not topic_ids:
                    continue
                
                target_topic = topic_ids[imported_count % len(topic_ids)]
                
                raw_choices = q_obj.get("choices", {})
                choice_list = [raw_choices.get("A"), raw_choices.get("B"), raw_choices.get("C"), raw_choices.get("D")]
                
                answer_map = {"A": 0, "B": 1, "C": 2, "D": 3}
                correct_idx = answer_map.get(item.get("correct_answer"), 0)

                new_q = QuestionPool(
                    topic_id=target_topic,
                    passage=q_obj.get("paragraph"),
                    question=q_obj.get("question"),
                    choices_json=json.dumps(choice_list),
                    correct_index=correct_idx,
                    explanation=item.get("explanation") or "Official College Board explanation.",
                    used_count=0
                )
                session.add(new_q)
                imported_count += 1

            session.commit()
        
        print(f"--- Successfully imported {imported_count} official questions ---")

    except Exception as e:
        print(f"Fetch failed: {str(e)}")

if __name__ == "__main__":
    fetch_and_import()
