# V.A.S.T. Voice Assistant

V.A.S.T. is a Django task-management web app with browser microphone commands, AI-backed task summaries, and MCP-style productivity tools. The app is prepared for Railway deployment with PostgreSQL.

## Features

- User registration, login, profile updates, and session authentication.
- Task CRUD with priority, status, category, search, date filters, dashboard metrics, and calendar rendering.
- Microphone commands through the browser Web Speech API.
- Structured `/api/voice/command/` endpoint with intent, confidence, action, and result payloads.
- Rule-based fallback for voice and AI behavior when no API key is configured.
- Optional OpenAI-compatible integration through `OPENAI_API_KEY`.
- MCP-style tools for task analysis, recommendations, smart scheduling, and priority optimization.
- Railway-ready settings using `DATABASE_URL`, WhiteNoise static files, and `gunicorn`.

## Local Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000`.

## Environment Variables

- `DEBUG`: `True` for local development, `False` in Railway.
- `SECRET_KEY`: Django secret key.
- `ALLOWED_HOSTS`: comma-separated hostnames.
- `CSRF_TRUSTED_ORIGINS`: comma-separated HTTPS origins.
- `DATABASE_URL`: Railway PostgreSQL connection string.
- `OPENAI_API_KEY`: optional AI provider key.
- `OPENAI_MODEL`: optional model name, defaults to `gpt-4o-mini`.

## Main API Endpoints

- `POST /api/accounts/register/`
- `POST /api/accounts/login/`
- `POST /api/accounts/logout/`
- `GET/PATCH /api/accounts/profile/`
- `GET/POST /api/tasks/`
- `GET/PATCH/DELETE /api/tasks/<id>/`
- `GET /api/tasks/?view=overdue|completed|high|today|upcoming`
- `GET /api/tasks/?search=meeting`
- `POST /api/voice/command/`
- `POST /api/ai/summary/`
- `GET /api/tools/`
- `POST /api/tools/task-analyzer/execute/`

## Voice Commands To Demo

- `Go to dashboard`
- `Show calendar`
- `Open settings`
- `Create task buy groceries tomorrow at 8 AM priority high`
- `Complete task project deadline`
- `Delete task old reminder`
- `Show overdue tasks`
- `Show high priority tasks`
- `Search for meeting`
- `Export my tasks`
- `Give me a summary`
- `Logout`

Filipino-oriented fallback words are also supported for common actions, including `bukas`, `ngayon`, `gumawa`, `dagdag`, `tapusin`, `burahin`, and `hanapin`.

## Railway Deployment

1. Push this `vast_project` folder to GitHub.
2. Create a Railway project from the GitHub repo.
3. Add a Railway PostgreSQL service.
4. Set environment variables from `.env.example`.
5. Use the default `Procfile` command: `gunicorn vast_config.wsgi --log-file -`.
6. Run migrations from the Railway shell: `python manage.py migrate`.
7. Create an admin user: `python manage.py createsuperuser`.

## Verification

```powershell
python manage.py check
python manage.py test
```

For microphone testing, use Chrome or Edge because Web Speech API support depends on the browser.
