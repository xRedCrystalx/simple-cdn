"""
The two files browsers and crawlers ask for by a fixed name.

Both are kept out of the OpenAPI schema, they are not part of the API. Their names are
also in FS_RESERVED_ROOTS, so a managed upload cannot take these paths over.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import FileResponse

logger = logging.getLogger("cdn.pages.special")
router = APIRouter(tags=["Special page"])


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """
    Serve the site icon.
    """
    return FileResponse("static/favicon.ico")

@router.get("/robots.txt", include_in_schema=False)
async def robots() -> FileResponse:
    """
    Serve the crawler rules.
    """
    return FileResponse("static/robots.txt")
