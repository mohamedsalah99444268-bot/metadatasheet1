from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .database import SessionLocal, create_tables, settings
from .routes.ai import router as ai_router
from .routes.auth import router as auth_router
from .routes.documents import router as documents_router
from .routes.imports import router as imports_router
from .routes.ocr import router as ocr_router
from .routes.rag import router as rag_router
from .routes.system import router as system_router
from .routes.users import router as users_router
from .routes.validation import router as validation_router
from .services.auth_service import bootstrap_from_env, optional_current_user
from .worker import start_worker, stop_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    with SessionLocal() as db:
        bootstrap_from_env(db)
    start_worker()
    try:
        yield
    finally:
        stop_worker()


app = FastAPI(title="SmartDatasheet AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

public_dependencies = [Depends(optional_current_user)]

app.include_router(auth_router)
app.include_router(documents_router, dependencies=public_dependencies)
app.include_router(ai_router, dependencies=public_dependencies)
app.include_router(imports_router, dependencies=public_dependencies)
app.include_router(rag_router, dependencies=public_dependencies)
app.include_router(ocr_router, dependencies=public_dependencies)
app.include_router(validation_router, dependencies=public_dependencies)
app.include_router(system_router, dependencies=public_dependencies)
app.include_router(users_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
