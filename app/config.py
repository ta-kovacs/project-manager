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

# Most document bytes a single project may hold, in bytes (default 100 MB). Uploads that would go over it
# are rejected. The usage it is checked against is kept up to date by the API and corrected by the
# storage-usage Lambda (lambdas/storage_usage), which measures what S3 actually holds.
PROJECT_STORAGE_LIMIT = int(os.getenv("PROJECT_STORAGE_LIMIT", 100 * 1024 * 1024))

# Shared secret the storage-usage Lambda sends as `Authorization: Bearer <token>` to
# PUT /internal/projects/{id}/storage-usage. When unset, that endpoint rejects every request.
# Production reads it from SSM Parameter Store.
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN") or None

# How share emails (GET /project/{id}/share) are sent (see app/mailer.py):
#   "ses"     - AWS SES; used in deployed environments
#   "console" - written to the application log; for local development
MAIL_BACKEND = os.getenv("MAIL_BACKEND", "console")

# ses backend: the verified SES identity emails are sent from.
MAIL_SENDER = os.getenv("MAIL_SENDER")

# Signs the JWT access tokens issued by POST /login. The default is for local development only;
# production reads a real secret from SSM Parameter Store.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-insecure-jwt-secret-change-me-in-production")

# How long an access token stays valid, in seconds (default 1 hour).
ACCESS_TOKEN_MAX_AGE = int(os.getenv("ACCESS_TOKEN_MAX_AGE", 60 * 60))

# Signs the tokens in share links (GET /project/{id}/share -> GET /join). The default is for local
# development only; production reads a real secret from SSM Parameter Store.
SHARE_SECRET_KEY = os.getenv("SHARE_SECRET_KEY", "dev-only-insecure-share-secret")

# How long a share link stays valid, in seconds (default 7 days).
SHARE_LINK_MAX_AGE = int(os.getenv("SHARE_LINK_MAX_AGE", 7 * 24 * 60 * 60))

# Public address of the API, used to build the links in share emails (e.g. https://pm.example.com).
# When unset, the address the share request was made to is used.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
