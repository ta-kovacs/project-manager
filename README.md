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

## Authentication

`POST /login` exchanges a username and password for a JWT access token, valid for one hour:

```json
{"access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600}
```

Every other endpoint except `POST /auth` and `GET /health` requires it as `Authorization: Bearer <jwt>`
(in the interactive docs: **Authorize**). A missing, malformed, tampered or expired token gets `401` with
`WWW-Authenticate: Bearer`. The token only identifies the user; whether they may act on a project (owner or
participant) is checked against the database on every request, so access changes apply immediately.

## Docker

Run the API and PostgreSQL together:

```bash
docker compose up --build
```

## Configuration

| Variable | Default | Used by |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5433/mydb` | app and Alembic |
| `STORAGE_BACKEND` | `local` | where document files are stored: `s3` (deployed environments) or `local` |
| `S3_BUCKET` | – | the S3 bucket for document files (required when `STORAGE_BACKEND=s3`) |
| `STORAGE_DIR` | `storage` | directory for document files with the `local` backend |
| `MAX_DOCUMENT_SIZE` | `10485760` (10 MB) | largest accepted document upload, in bytes |
| `PROJECT_STORAGE_LIMIT` | `104857600` (100 MB) | most document bytes one project may hold; uploads over it get `413` |
| `INTERNAL_API_TOKEN` | unset (internal endpoints disabled) | shared secret of the storage-usage Lambda (production: SSM parameter `/project-manager/internal-api-token`) |
| `MAIL_BACKEND` | `console` | how share emails are sent: `ses` (deployed environments) or `console` (logged) |
| `MAIL_SENDER` | – | verified SES address share emails come from (required when `MAIL_BACKEND=ses`) |
| `JWT_SECRET_KEY` | an insecure development value | signs access tokens from `POST /login` (production: SSM parameter `/project-manager/jwt-secret-key`) |
| `ACCESS_TOKEN_MAX_AGE` | `3600` (1 hour) | how long an access token stays valid, in seconds |
| `SHARE_SECRET_KEY` | an insecure development value | signs share-link tokens (production: SSM parameter `/project-manager/share-secret-key`) |
| `SHARE_LINK_MAX_AGE` | `604800` (7 days) | how long a share link stays valid, in seconds |
| `PUBLIC_BASE_URL` | the address of the request | base of the links in share emails, e.g. `https://pm.example.com` |

Inside Docker Compose the app connects to `db:5432` instead.

### Document storage

Document files are stored in **AWS S3** when deployed (`docker-compose.prod.yaml` sets `STORAGE_BACKEND=s3`);
the API streams them to and from the bucket, so access checks always go through the API. Locally and in
tests they are stored on disk (or in a moto-mocked bucket with `TEST_STORAGE_BACKEND=s3`). The S3 client uses
the standard AWS credential chain; on EC2 that is the instance role, so no keys are configured in the app.

### Project storage limit (S3 + Lambda)

Each project may hold at most `PROJECT_STORAGE_LIMIT` bytes of documents. The API keeps a running total per
project and checks uploads against it; in AWS, the storage-usage Lambda (`lambdas/storage_usage/`) runs on
every S3 change, measures what the bucket really holds for that project, and reports it back through
`PUT /internal/projects/{id}/storage-usage` (authenticated with `INTERNAL_API_TOKEN`). The Lambda's
configuration is described at the top of `lambdas/storage_usage/handler.py`.

## Linting and formatting

[ruff](https://docs.astral.sh/ruff/) lints and formats the code; its configuration is in `pyproject.toml`.
It is installed with the dev dependencies (`pip install -r requirements-dev.txt`):

```bash
ruff check .            # lint (add --fix to apply safe fixes)
ruff format .           # format
ruff format --check .   # what CI runs: fails if anything would be reformatted
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and on pushes to `main`:

- **lint**: `ruff check` and `ruff format --check`
- **build**: installs dependencies and byte-compiles `app/` and `lambdas/`
- **test**: runs pytest against a throwaway PostgreSQL, once with local and once with (mocked) S3 storage
- **docker**: builds the Docker image
- **migrations**: applies all Alembic migrations against a throwaway PostgreSQL service
- **deploy** (pushes to `main`, or a manual run on `main`): pushes the image to Amazon ECR, then deploys it to a
  single EC2 host through SSM Run Command: Postgres and the app run there with `docker-compose.prod.yaml`, and
  `alembic upgrade head` runs before the app is (re)started; then, if the `STORAGE_USAGE_LAMBDA` variable is set,
  it updates that Lambda function's code

The deploy job is skipped until the `EC2_INSTANCE_ID` repository variable is set, and needs the `S3_BUCKET`
(documents bucket) and `MAIL_SENDER` (verified SES sender) variables, plus the SSM parameters
`/project-manager/share-secret-key`, `/project-manager/jwt-secret-key` and `/project-manager/internal-api-token`. `PUBLIC_BASE_URL` is optional. It signs in to AWS with OIDC
when the `AWS_ROLE_ARN` variable is set, or otherwise with the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` secrets
of a deploy-only IAM user.
