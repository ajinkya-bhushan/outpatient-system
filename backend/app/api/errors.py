"""Map AppError to FastAPI HTTPException."""

from fastapi import HTTPException

from app.core.errors import AppError


def raise_app_error(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)
