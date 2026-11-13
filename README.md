# Project Manager

A FastAPI backend for managing projects, their members and documents, backed by PostgreSQL.

## Tech stack

- FastAPI + Uvicorn
- SQLAlchemy ORM, or hand-written SQL on psycopg without the ORM, and Alembic (migrations)
- PostgreSQL 17 (via Docker Compose)

## Running locally

```bash
# 1. Start PostgreSQL (exposed on localhost:5433)
docker compose up -d db

# 2. Install the app (editable) with the development tools; --group needs pip 25.1+
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e . --group dev

# 3. Apply database migrations
alembic upgrade head

# 4. Run the API
uvicorn app.main:app --reload

# 5. Serve the frontend (in a second terminal)
python -m http.server 8080 -d frontend
```

The API is then available at http://localhost:8000, with interactive docs at http://localhost:8000/docs,
and the frontend at http://localhost:8080.

## Frontend

`frontend/` is a basic browser app for the API: log in or create an account, list and create projects,
edit a project's details, upload, download and delete documents, invite users, email a join link and
delete projects (the owner-only controls only show for the owner). It is plain HTML, CSS and JavaScript
modules with no build step, so any static file server can serve it.

- `config.js` says where the API is (`http://localhost:8000` by default; `""` means the frontend's own
  origin); replace that file to point a deployment elsewhere.
- Locally the frontend runs on its own origin, so the API must allow it in `CORS_ORIGINS` (by default
  `http://localhost:8080` and `http://127.0.0.1:8080`).
- In production the frontend image (`frontend/Dockerfile`, `frontend/nginx.conf`) is the public entry
  point on port 80: nginx serves the frontend and forwards every other request to the API, so both share
  one origin and no CORS setup is needed. The API's URLs are unchanged (`/docs`, `/health`, `/projects`, ...).
- The access token is kept in `sessionStorage`: closing the tab, the token expiring or a `401` signs the
  user out.

## Authentication

`POST /auth` registers a user (`username`, `password`, `repeat_password`). Usernames are 3–250 characters
and unique. Passwords must be 10–128 characters with a lowercase letter, an uppercase letter and a digit,
and must not contain the username (ignoring case); a weak password gets `422` listing every rule it breaks.
Passwords are stored only as Argon2 hashes. The rules apply when registering, so older accounts can still
log in.

`POST /login` exchanges a username and password for a JWT access token, valid for one hour:

```json
{"access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600}
```

Every other endpoint except `POST /auth` and `GET /health` requires it as `Authorization: Bearer <jwt>`
(in the interactive docs: **Authorize**). A missing, malformed, tampered or expired token gets `401` with
`WWW-Authenticate: Bearer`. The token only identifies the user; whether they may act on a project (owner or
participant) is checked against the database on every request, so access changes apply immediately.

## Docker

Run PostgreSQL, the API (http://localhost:8000) and the frontend (http://localhost:8080, served by nginx)
together:

```bash
docker compose up --build
```

## Configuration

| Variable | Default | Used by |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5433/mydb` | app and Alembic |
| `DATABASE_ACCESS` | `orm` | how the app reads and writes the database: `orm` (SQLAlchemy models) or `sql` (hand-written SQL on psycopg, no ORM; PostgreSQL only) |
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
| `CORS_ORIGINS` | `http://localhost:8080,http://127.0.0.1:8080` | browser origins allowed to call the API (where the frontend is served), comma-separated |

Inside Docker Compose the app connects to `db:5432` instead.

### Database

Everything that talks to the database lives in `app/db/`. The services use one interface
(`app/db/interface.py`: users, projects and documents repositories, plus commit and rollback) that
returns plain records (`app/db/records.py`), and there are two interchangeable implementations of it:

- `app/db/orm/`: SQLAlchemy ORM models, mapped to records. Alembic migrations are generated from these
  models.
- `app/db/sql/`: no ORM and no SQLAlchemy. Hand-written SQL with `%(name)s` parameters, run on a plain
  psycopg connection, and the schema written by hand in `app/db/sql/schema.sql`. PostgreSQL only.

`DATABASE_ACCESS` picks one per process; both work on the same database. To create the schema without
the ORM or Alembic, run `python -m app.db.sql` against an empty database (then `alembic stamp head` if
Alembic should take over migrations). `schema.sql` also describes how the schema is normalized, and why
`projects.storage_used_bytes` is deliberately denormalized.

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

## Packaging

The app is the Python package `project-manager` (import name `app`), defined in `pyproject.toml` and built
with hatchling. `pyproject.toml` is the only list of dependencies:

- `[project.dependencies]`: runtime dependencies, pinned exactly
- `[dependency-groups]`: development tools that are never part of the package: `test`, `lint`, `tools`
  (build, twine, tox) and `dev` (all of them)

```bash
python -m build          # dist/project_manager-<version>.tar.gz and -py3-none-any.whl
```

The wheel contains only `app/`. The Docker image builds it in a first stage and installs it in the runtime
stage, next to the Alembic migrations. Bump `version` in `pyproject.toml` for a release; the running app
reports it in the OpenAPI docs.

## Tests and tox

```bash
pytest                       # the suite, from the source tree (in-memory SQLite, local storage)
tox                          # tests on every installed Python version (3.12, 3.13, 3.14) + lint
tox -e py314 -- tests/unit   # one version; arguments after -- go to pytest
tox -e lint                  # ruff only
```

`TEST_DATABASE_URL` (a Postgres URL), `TEST_DATABASE_ACCESS=sql` (the backend without the ORM) and
`TEST_STORAGE_BACKEND=s3` (a moto-mocked bucket) switch the suite to what CI uses.
`tests/unit/test_database.py` checks both database backends and `tests/unit/test_schema.py` checks that
`schema.sql` matches the ORM models.

The SQL backend runs on psycopg, so it needs PostgreSQL: on the default in-memory SQLite database its tests
are skipped (CI runs them). To run them locally, use a separate, throwaway database, because the tests
drop every table:

```bash
docker compose up -d db
docker compose exec db createdb -U postgres testdb
export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/testdb
TEST_DATABASE_ACCESS=sql pytest
```

## Linting and formatting

[ruff](https://docs.astral.sh/ruff/) lints and formats the code; its configuration is in `pyproject.toml`.
It is installed with the `lint` (or `dev`) dependency group:

```bash
ruff check .            # lint (add --fix to apply safe fixes)
ruff format .           # format
ruff format --check .   # what CI runs: fails if anything would be reformatted
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and on pushes to `main`:

- **lint**: `ruff check` and `ruff format --check`
- **build**: builds the sdist and wheel, checks them with `twine check`, uploads them as the `dist` artifact,
  and byte-compiles `lambdas/`
- **test**: `tox -e py` against a throwaway PostgreSQL, on Python 3.12 and 3.14, each with the ORM and the
  SQL database backend, plus one run with (mocked) S3 storage
- **docker**: builds the API image (from the package's wheel) and the frontend image
- **migrations**: applies all Alembic migrations against a throwaway PostgreSQL service
- **deploy** (pushes to `main`, or a manual run on `main`): pushes the API image and the frontend image
  (same ECR repository, tagged `frontend-<sha>`) to Amazon ECR, then deploys them to a single EC2 host through
  SSM Run Command: Postgres, the API and the frontend (nginx, on port 80, proxying the API) run there with
  `docker-compose.prod.yaml`, and `alembic upgrade head` runs before they are (re)started; then, if the
  `STORAGE_USAGE_LAMBDA` variable is set, it updates that Lambda function's code

The deploy job is skipped until the `EC2_INSTANCE_ID` repository variable is set, and needs the `S3_BUCKET`
(documents bucket) and `MAIL_SENDER` (verified SES sender) variables, plus the SSM parameters
`/project-manager/share-secret-key`, `/project-manager/jwt-secret-key` and `/project-manager/internal-api-token`. `PUBLIC_BASE_URL` is optional. It signs in to AWS with OIDC
when the `AWS_ROLE_ARN` variable is set, or otherwise with the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` secrets
of a deploy-only IAM user.
