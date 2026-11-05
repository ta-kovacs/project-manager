# Project Manager

A FastAPI backend for managing projects, their members and documents, backed by PostgreSQL.

## Tech stack

- FastAPI + Uvicorn
- SQLAlchemy and Alembic (migrations)
- PostgreSQL 17 (via Docker Compose)

## Running locally

```bash
# 1. Start PostgreSQL (exposed on localhost:5433)
docker compose up -d db

# 2. Install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Apply database migrations
alembic upgrade head

# 4. Run the API
uvicorn app.main:app --reload
```

The API is then available at http://localhost:8000, with interactive docs at http://localhost:8000/docs.

## Docker

Run the API and PostgreSQL together:

```bash
docker compose up --build
```

## Configuration

| Variable | Default | Used by |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5433/mydb` | app and Alembic |

Inside Docker Compose the app connects to `db:5432` instead.

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and on pushes to `main`:

- **build**: installs dependencies and byte-compiles `app/`
- **docker**: builds the Docker image
- **migrations**: applies all Alembic migrations against a throwaway PostgreSQL service
- **deploy** (pushes to `main`, or a manual run on `main`): pushes the image to Amazon ECR, then deploys it to a
  single EC2 host through SSM Run Command: Postgres and the app run there with `docker-compose.prod.yaml`, and
  `alembic upgrade head` runs before the app is (re)started

The deploy job is skipped until the `EC2_INSTANCE_ID` repository variable is set. It signs in to AWS with OIDC
when the `AWS_ROLE_ARN` variable is set, or otherwise with the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` secrets
of a deploy-only IAM user.
