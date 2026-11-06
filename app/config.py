import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/mydb",
)

# Document files are stored under this directory (see app/storage.py).
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
