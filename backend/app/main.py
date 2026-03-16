from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from app.api.routes import router
from app.infra.logging import configure_logging
from app.orchestrator.service import InvalidInputError, InvalidTaskStateError, ResourceNotFoundError
from app.persistence.session import init_db


configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="FleetWarden API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(ResourceNotFoundError)
async def handle_not_found(_request: Request, exc: ResourceNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidTaskStateError)
async def handle_invalid_state(_request: Request, exc: InvalidTaskStateError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(InvalidInputError)
async def handle_invalid_input(_request: Request, exc: InvalidInputError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
