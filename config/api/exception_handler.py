from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Custom exception handler for consistent API error responses."""
    response = exception_handler(exc, context)

    if response is not None:
        # Ensure consistent error format
        errors = []
        if isinstance(response.data, dict):
            for field, messages in response.data.items():
                if isinstance(messages, list):
                    for message in messages:
                        errors.append({"field": field, "message": str(message)})
                else:
                    errors.append({"field": field, "message": str(messages)})
        elif isinstance(response.data, list):
            for message in response.data:
                errors.append({"field": "non_field_errors", "message": str(message)})

        response.data = {
            "success": False,
            "error": {
                "code": response.status_code,
                "message": str(exc) if exc else "An error occurred",
                "details": errors,
            },
        }

    return response


class APIError(Exception):
    """Base API error class."""

    def __init__(self, detail, code=None, status_code=status.HTTP_400_BAD_REQUEST):
        self.detail = detail
        self.code = code or "error"
        self.status_code = status_code
        super().__init__(detail)


class ValidationError(APIError):
    """Validation error."""

    def __init__(self, detail):
        super().__init__(detail, code="validation_error", status_code=status.HTTP_400_BAD_REQUEST)


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(self, detail):
        super().__init__(detail, code="not_found", status_code=status.HTTP_404_NOT_FOUND)


class PermissionDeniedError(APIError):
    """Permission denied error."""

    def __init__(self, detail="You do not have permission to perform this action."):
        super().__init__(detail, code="permission_denied", status_code=status.HTTP_403_FORBIDDEN)
