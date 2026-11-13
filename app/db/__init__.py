"""Database access.

    engine.py     the engine and get_db, the dependency that gives each request a Database
    interface.py  the Database protocol every backend implements (and ConflictError)
    records.py    the plain records repositories return
    orm/          backend built on SQLAlchemy ORM models
    sql/          backend without the ORM: hand-written SQL on psycopg, and schema.sql

Import from the modules; this package itself stays import-free so the backends can use records.py
without import cycles.
"""
