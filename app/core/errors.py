from dataclasses import dataclass, field
from typing import Any

from fastapi import status


@dataclass
class AppException(Exception):
    error_code: str
    message: str
    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        return {
            "success": False,
            "error_code": self.error_code,
            "message": self.message,
            "detail": self.detail or self.message,
            "context": self.context,
        }