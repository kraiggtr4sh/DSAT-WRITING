# DSAT Writing Practice (Python/HTMX)

Instructional context for the AI-powered DSAT Writing drill tool.

## Technical Architecture

- **Backend:** FastAPI (Python 3.9+)
- **Frontend:** HTMX + Jinja2 Templates (Vanilla CSS)
- **Database:** SQLite via SQLModel
- **AI Integration:** Google Generative AI (Gemini 2.0 Flash)

### Core Workflow

1.  **Request Handling:** All user interactions (selecting topics, generating questions, answering) are handled via HTMX `POST` requests.
2.  **State Management:** Persistence is entirely server-side in `database.db`.
3.  **AI Prompts:** Defined in `main.py`. The AI is instructed to return JSON, which is then parsed and rendered using Jinja2 components.

## Development Guidelines

- **Hate JS/Node:** This project is intentionally designed to minimize JavaScript. Do not add JS libraries or complex client-side logic unless absolutely necessary. Prefer HTMX attributes.
- **Data Persistence:** Use `sqlmodel` for any schema changes. Update `models.py` and then `main.py`.
- **UI Consistency:** The styling is defined in `static/style.css`. When adding new components, follow the existing naming conventions and use the CSS variables defined in `:root`.

## Building and Running

1.  `pip install -r requirements.txt`
2.  Set `GEMINI_API_KEY` in `.env`.
3.  `uvicorn main:app --reload`
