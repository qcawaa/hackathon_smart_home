from __future__ import annotations

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error(status, code, message):
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


async def http_error_handler(_request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) and "error" in exc.detail else {
        "error": {"code": "REQUEST_FAILED", "message": str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=detail)


async def validation_error_handler(_request, _exc):
    return JSONResponse(status_code=422, content={"error": {"code": "INVALID_REQUEST", "message": "Проверьте заполненные поля"}})