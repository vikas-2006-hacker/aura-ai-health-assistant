from fastapi import HTTPException, status


class HealthError(Exception):
    """Raised when a health-related operation cannot be completed."""


class NotFoundError(HTTPException):
    """Simple not-found exception for the API."""

    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
