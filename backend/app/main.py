from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

import logging

from .database import SessionLocal, init_database, settings
from .routes.ai import router as ai_router
from .routes.auth import router as auth_router
from .routes.compare import router as compare_router
from .routes.components import router as components_router
from .routes.datasets import router as datasets_router
from .routes.monitoring import router as monitoring_router
from .routes.specs import router as specs_router
from .routes.stats import router as stats_router
from .routes.documents import router as documents_router
from .routes.imports import router as imports_router
from .routes.ocr import router as ocr_router
from .routes.rag import router as rag_router
from .routes.system import router as system_router
from .routes.users import router as users_router
from .routes.validation import router as validation_router
from .services.auth_service import bootstrap_from_env, optional_current_user
from .worker import start_worker, stop_worker


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    with SessionLocal() as db:
        bootstrap_from_env(db)
        try:
            from .services.component_service import backfill_if_empty

            created = backfill_if_empty(db)
            if created:
                logger.info("Backfilled %s component(s) from existing analysis reports", created)
        except Exception:
            logger.exception("Component backfill failed")
            db.rollback()
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
for _router in (components_router, specs_router, compare_router, stats_router, monitoring_router, datasets_router):
    app.include_router(_router, dependencies=public_dependencies)


@app.get("/api/health")
def health():
    return {"status": "ok"}
