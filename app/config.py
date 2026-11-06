import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/mydb",
)

# Where document files are stored (see app/storage.py):
#   "s3"    - an AWS S3 bucket; used in deployed environments
#   "local" - a directory on disk; for local development and tests
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")

# local backend: document files are stored under this directory.
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")

# s3 backend: the bucket holding document files. Credentials and region come from the
# standard AWS sources (EC2 instance role, AWS_REGION, ~/.aws/...), as for any boto3 client.
S3_BUCKET = os.getenv("S3_BUCKET")

# Largest accepted document upload, in bytes (default 10 MB).
MAX_DOCUMENT_SIZE = int(os.getenv("MAX_DOCUMENT_SIZE", 10 * 1024 * 1024))
