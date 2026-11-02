from fastapi import FastAPI

app = FastAPI(
    title="Project Manager API"
)

@app.get("/health")
def health():
    return {"status": "ok"}