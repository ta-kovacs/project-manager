-- The database schema for PostgreSQL, written by hand (no ORM, no Alembic).
--
-- It describes the same tables as the ORM models (app/db/orm/models), from which the Alembic migrations
-- are generated; tests/unit/test_schema.py checks that the two stay in sync. Create a database from it
-- with `python -m app.db.sql` (then `alembic stamp head` if Alembic should manage it from there).
-- Constraints are declared at table level, as the migrations do.
--
-- Normalized: each fact is stored once. A project's members and their roles live in project_users (one
-- row per user and project), documents reference their project, and owners are a role, not a column.
-- The one deliberate exception is projects.storage_used_bytes, a running total of the project's document
-- sizes that saves summing them on every upload (see app/services/document_service.py).

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(250) NOT NULL,
    -- Argon2 hash from app.security; the plain password is never stored
    password_hash VARCHAR(250) NOT NULL,
    CONSTRAINT uq_users_username UNIQUE (username)
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(250) NOT NULL,
    description TEXT,
    -- bytes of document files; adjusted by the API, overwritten by the storage-usage Lambda
    storage_used_bytes BIGINT NOT NULL DEFAULT 0,
    -- when the Lambda last measured storage_used_bytes; older measurements are ignored
    storage_measured_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE project_users (
    project_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    PRIMARY KEY (project_id, user_id),
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT project_role CHECK (role IN ('owner', 'participant'))
);

-- "which projects can this user access": the primary key only covers lookups by project_id
CREATE INDEX ix_project_users_user_id ON project_users (user_id);

-- at most one owner per project
CREATE UNIQUE INDEX uq_project_users_one_owner ON project_users (project_id) WHERE role = 'owner';

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    storage_key VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    -- NULL for documents uploaded before sizes were recorded
    size_bytes BIGINT,
    project_id INTEGER NOT NULL,
    UNIQUE (storage_key),
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
);
