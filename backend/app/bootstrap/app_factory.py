from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router, ws_router
from app.bootstrap import wiring
from app.core.config import ROOT
from app.core.errors import http_error_handler, validation_error_handler


@asynccontextmanager
async def lifespan(_app):
    wiring.manager.start()
    wiring.engine.start()
    wiring.bridge.start()
    try:
        yield
    finally:
        await wiring.bridge.stop()
        await wiring.engine.stop()
        await wiring.manager.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Ujin Smart Home", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    app.include_router(api_router)
    app.include_router(ws_router)

    frontend_dist = ROOT / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app