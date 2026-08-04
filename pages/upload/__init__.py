"""
The upload page.

Only renders the form. The upload itself is done by the page's own script against
`/api/files`, with a token the visitor pastes in, so nothing here needs authentication.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from utils.general import ENV, human_size, transform_brand

templates = Jinja2Templates(directory="pages")


logger = logging.getLogger("cdn.pages.upload")
router = APIRouter(prefix="", tags=["Upload page"])

@router.get("/upload", include_in_schema=False)
async def upload_page(req: Request) -> HTMLResponse:
    """
    Show the upload form.
    """
    logger.debug("Serving the upload page.")

    return templates.TemplateResponse(
        req, name="upload/upload.html",
        context={
            "max_upload_size": human_size(ENV.MAX_UPLOAD_SIZE),
            "brand": transform_brand()
        }
    )
