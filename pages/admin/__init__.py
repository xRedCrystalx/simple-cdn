"""
The admin pages.

Two steps: `/admin` asks for a token, the POST to the same path checks it and renders the
panel. The panel is a plain page with no session behind it, so the token is rendered into
it and the browser sends it back on every call the panel makes.
"""

import logging
from sqlite3 import Row

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from utils.database import db_manager
from utils.general import ENV, human_size, transform_brand

templates = Jinja2Templates(directory="pages")

logger = logging.getLogger("cdn.pages.admin")
router = APIRouter(prefix="", tags=["Admin page"])


def render_gateway(req: Request, error: str | None) -> HTMLResponse:
    """
    Render the token form. An `error` both fills the message in and turns the response
    into a 403, so a failed attempt is visible in an access log as well as on the page.
    """
    return templates.TemplateResponse(
        req, name="admin/gateway.html",
        context={
            "brand": transform_brand(),
            "error": error
        },
        status_code=403 if error else 200
    )


# This endpoint renders token request page for unauthenticated users.
@router.get("/admin", include_in_schema=False)
async def admin_page(req: Request) -> HTMLResponse:
    """
    Show the admin token form.
    """
    logger.debug("Serving the admin gateway page.")
    return render_gateway(req, None)


# POST from previous page, this endpoint renders the admin panel if auth succeed.
@router.post("/admin", include_in_schema=False)
async def admin_panel(req: Request, token: str = Form()) -> HTMLResponse:
    """
    Check the submitted token and open the admin panel when it is valid.
    """
    token = token.strip()

    # Deliberately narrower than the auth dependencies: only an admin token opens this
    # page, and the type is part of the query rather than a check afterwards.
    row: Row | None = await db_manager.execute(
        "SELECT 1 FROM auth_tokens WHERE token = ? AND type = 'admin' LIMIT 1", (token,), fetch_one=True
    )

    if row is None:
        logger.info("Rejected an admin panel request carrying an unknown token.")
        return render_gateway(req, "That token is not valid.")

    logger.info("Opened the admin panel for a valid admin token.")

    # the token rides back out with the page, it is all the panel can authorise its calls with
    return templates.TemplateResponse(
        req, name="admin/admin_panel.html",
        context={
            "brand": transform_brand(),
            "max_upload_size": human_size(ENV.MAX_UPLOAD_SIZE),
            "token": token
        }
    )
