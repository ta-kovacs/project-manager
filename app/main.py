from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import CORS_ORIGINS
from app.routes import auth, documents, internal, projects

app = FastAPI(title="Project Manager API", version=__version__)

# The frontend runs on its own origin. It authenticates with the Authorization header, never cookies,
# so credentials stay disallowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(internal.router)


@app.get("/health")
def health():
    return {"status": "ok"}
