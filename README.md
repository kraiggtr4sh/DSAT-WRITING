# DSAT Writing Practice (Python Version)

AI-powered DSAT Writing section drill tool. This version uses a **Python (FastAPI)** backend with **SQLite** for robust data persistence and **HTMX** for a smooth, JavaScript-free frontend experience.

## Features

- **6 grammar topics** — Punctuation, Transitions, Subject-Verb Agreement, Modifiers, Parallel Structure, Sentence Boundaries.
- **AI-generated questions** — Realistic SAT-style passages generated via Gemini 2.0 Flash.
- **Robust Persistence** — Your stats, streaks, and mistake history are saved in a local SQLite database (`database.db`).
- **No-JS Frontend** — Uses HTMX for dynamic updates, keeping the frontend logic on the server.
- **Modern UI** — Preserves the polished Lora/DM Sans aesthetic of the original.

## Setup

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Set API Key:**
   - Create a `.env` file from the example: `cp .env.example .env` (or manually create it).
   - Add your **Google AI Studio API Key** to `GEMINI_API_KEY`. Get one for free at [aistudio.google.com](https://aistudio.google.com/app/apikey).
3. **Run the App:**
   ```bash
   uvicorn main:app --reload
   ```
4. **Open in Browser:**
   Go to `http://127.0.0.1:8000`.

## File Structure

- `main.py`: FastAPI server routes and logic.
- `models.py`: Database schema (SessionStats, TopicStats, Mistakes).
- `templates/`: Jinja2 HTML templates.
- `static/`: CSS and other static assets.
- `database.db`: SQLite database (auto-created on startup).
- `requirements.txt`: Python package list.

## Customizing

- **Add Topics:** Edit the `TOPICS` list and `TOPIC_INSTRUCTIONS` dictionary in `main.py`.
- **Change Model:** Edit the `genai.GenerativeModel` string in `main.py`.
