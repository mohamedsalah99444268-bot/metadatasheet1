from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import create_tables
from .routes.documents import router as documents_router

app = FastAPI(title="Metadatasheet", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)


@app.on_event("startup")
def on_startup():
    create_tables()


@app.get("/api/health")
def health():
    return {"status": "ok"}
