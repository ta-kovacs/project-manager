from fastapi import FastAPI
from app.routes import auth

## TODO: Token verification dependency, maybe seperate router registration

app = FastAPI(
    title="Project Manager API"
)

app.include_router(auth.router)


@app.get("/health")
def health():
    return {"status": "ok"}
