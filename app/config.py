import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/mydb",
)

# Document files are stored under this directory (see app/storage.py).
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")

# Largest accepted document upload, in bytes (default 10 MB).
MAX_DOCUMENT_SIZE = int(os.getenv("MAX_DOCUMENT_SIZE", 10 * 1024 * 1024))
