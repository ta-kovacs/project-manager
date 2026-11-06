from fastapi import FastAPI
from app.routes import auth, documents, projects

app = FastAPI(
    title="Project Manager API"
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)


@app.get("/health")
def health():
    return {"status": "ok"}
