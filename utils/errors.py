"""
Uniform error responses.

FastAPI and Starlette answer failures they detect themselves in their own shapes.
The handlers registered here rewrite all of them into `StatusResponse`, so every failure
the service emits looks like the ones the endpoints return by hand: `status` is always
`"error"` and `message` is always a plain string. The HTTP status codes are left exactly
as FastAPI chose them, only the body changes.
"""

import logging

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from utils.models import StatusResponse

logger = logging.getLogger("cdn.errors")

# What the client is told when something breaks on our side. Deliberately vague: the detail is in the log. 
GENERIC_ERROR_MESSAGE: str = "Internal server error."


def error_response(status_code: int, message: str = GENERIC_ERROR_MESSAGE) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=StatusResponse(status="error", message=message).model_dump()
    )



async def validation_exception_handler(req: Request, exc: RequestValidationError) -> Response:
    """
    Handle a request that did not match the endpoint's model: wrong types, missing fields, malformed JSON.
    """

    logger.warning(f"Rejected a malformed {req.method} request to '{req.url.path}': {exc}")
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "The request did not match the expected shape.")

async def response_validation_exception_handler(req: Request, exc: ResponseValidationError) -> Response:
    """
    Handle an endpoint returning something its own response model rejects.

    Bug on our side - so the caller gets the generic message while the mismatch itself goes to the log with a stack trace.
    """
    logger.error(f"Endpoint '{req.url.path}' returned a response that failed validation: {exc}", exc_info=exc)
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, GENERIC_ERROR_MESSAGE)


async def http_exception_handler(req: Request, exc: StarletteHTTPException) -> Response:
    """
    Handle an HTTPException, whether raised by the app (the auth dependencies do) or by
    the framework itself (404 for an unknown route, 405 for a wrong method).
    """
    # HTTPException carries whatever was passed as detail, which is usually a string but
    # is allowed to be any object; coerce so `message` keeps its declared type.
    detail: str = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    logger.info(f"Refused {req.method} '{req.url.path}' with {exc.status_code}: {detail}")
    return error_response(exc.status_code, detail)

async def unhandled_exception_handler(req: Request, exc: Exception) -> Response:
    """
    Catch-all for anything the endpoints let escape, so a crash still answers in the
    service's own error shape rather than with Starlette's plain text 500.
    """
    logger.critical(f"Unhandled exception while serving {req.method} '{req.url.path}'.", exc_info=exc)
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, GENERIC_ERROR_MESSAGE)


async def register_exception_handlers(app: FastAPI) -> None:
    """
    Attach every handler above to the application. Called once during startup.
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ResponseValidationError, response_validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Starlette only consults this one after the middleware stack has re-raised.
    app.add_exception_handler(Exception, unhandled_exception_handler)

    logger.debug("Registered the StatusResponse exception handlers.")
