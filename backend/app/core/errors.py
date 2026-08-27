"""Shared application errors."""

from __future__ import annotations


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ValidationFailed(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class UpstreamUnavailable(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)


class UpstreamTimeout(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=504)


class ConfigurationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


class NotFound(AppError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__(message, status_code=404)


class InvalidCredentials(AppError):
    def __init__(self, message: str = "Invalid provider ID or password") -> None:
        super().__init__(message, status_code=401)
        self.error = "invalid_credentials"
