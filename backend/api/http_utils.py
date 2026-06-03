"""API 层工具函数。"""

from fastapi import HTTPException

from services.exceptions import ServiceError


def service_error_to_http(exc: ServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)
