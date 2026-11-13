from fastapi import FastAPI

from app import __version__
from app.routes import auth, documents, internal, projects

app = FastAPI(title="Project Manager API", version=__version__)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(internal.router)


@app.get("/health")
def health():
    return {"status": "ok"}
