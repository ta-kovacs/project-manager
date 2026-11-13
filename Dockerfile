# --- build: turn the source into a wheel -----------------------------------------------------------
FROM python:3.14.7-slim AS build

WORKDIR /src
RUN pip install --no-cache-dir build==1.6.1

COPY pyproject.toml README.md ./
COPY app/ ./app/
RUN python -m build --wheel --outdir /dist

# --- runtime: the installed package, plus what is needed to run migrations ---------------------------
FROM python:3.14.7-slim

WORKDIR /app

COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Alembic ships in the image so migrations can run in the app container (alembic upgrade head);
# env.py imports the models from the installed package.
COPY alembic/ ./alembic/
COPY alembic.ini .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
