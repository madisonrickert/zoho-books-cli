"""Typed exceptions with stable error codes and meaningful exit codes.

The CLI entry point catches `ZohoCLIError`, renders the structured JSON to
stderr, and exits with `err.exit_code`.
"""

from __future__ import annotations

from typing import Any

EXIT_SUCCESS = 0
EXIT_UNKNOWN = 1
EXIT_AUTH = 2
EXIT_VALIDATION = 3
EXIT_API = 4
EXIT_RATE_LIMIT = 5
EXIT_NETWORK = 6


class ZohoCLIError(Exception):
    code: str = "unknown"
    exit_code: int = EXIT_UNKNOWN

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


class AuthRequired(ZohoCLIError):
    code = "auth_required"
    exit_code = EXIT_AUTH


class AuthExpired(ZohoCLIError):
    code = "auth_expired"
    exit_code = EXIT_AUTH


class AuthFailed(ZohoCLIError):
    code = "auth_failed"
    exit_code = EXIT_AUTH


class ValidationError(ZohoCLIError):
    code = "validation"
    exit_code = EXIT_VALIDATION


class NotFound(ZohoCLIError):
    code = "not_found"
    exit_code = EXIT_API


class APIError(ZohoCLIError):
    code = "api_error"
    exit_code = EXIT_API


class RateLimited(ZohoCLIError):
    code = "rate_limited"
    exit_code = EXIT_RATE_LIMIT


class NetworkError(ZohoCLIError):
    code = "network"
    exit_code = EXIT_NETWORK
