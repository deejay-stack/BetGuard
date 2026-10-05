from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import ConfigurationError
from app.core.database import make_engine
from app.api import check, domain, health
from app.api.errors import unavailable
from app.services.model_service import InferenceUnavailable, ModelService
from app.services.domain_service import load_runtime


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        application.state.engine = make_engine()
    except ConfigurationError:
        application.state.engine = None
    application.state.model = ModelService.from_environment()
    application.state.betguard_runtime = load_runtime()
    try:
        yield
    finally:
        application.state.betguard_runtime = None
        application.state.model.close()
        if application.state.engine is not None:
            application.state.engine.dispose()


app = FastAPI(title="BetGuard catalog API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, _error: RequestValidationError):
    # Pydantic's default response can echo the user's complete input URL.
    return JSONResponse(status_code=422, content={"error": {
        "code": "invalid_hostname", "message": "Send a complete HTTP(S) hostname without credentials or an IP address."
    }})


@app.exception_handler(SQLAlchemyError)
async def database_error(_request: Request, _error: SQLAlchemyError):
    return unavailable()


@app.exception_handler(InferenceUnavailable)
async def inference_error(_request: Request, _error: InferenceUnavailable):
    return unavailable("model_unavailable")


@app.middleware("http")
async def no_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(health.router)
app.include_router(check.router)
app.include_router(domain.router)
