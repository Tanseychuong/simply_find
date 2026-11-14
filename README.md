# SimplyFind

Internships, graduate programmes and entry-level roles for students and
recent graduates, with paperless applications: students keep their
transcripts and certificates in one place and apply with them.

- `backend/`: Django REST API and admin. API reference: [backend/docs/api.md](backend/docs/api.md).
  Ingestion of listings from feeds: [backend/docs/ingestion.md](backend/docs/ingestion.md).
- `frontend/`: the website (React 18, Vite, React Router, Tailwind), with public pages pre-rendered at build time.

## Run the website locally

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to the backend on :8000
npm run lint && npm run build
```

## Run the backend locally

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then edit DATABASE_URL
python manage.py migrate
python manage.py setup_groups && python manage.py setup_categories
python manage.py seed_demo_opportunities   # optional sample roles
python manage.py runserver
python -m pytest -q
```

Deploys to Render from `render.yaml` (website, API and virus scanner):
see [docs/deploy.md](docs/deploy.md).
