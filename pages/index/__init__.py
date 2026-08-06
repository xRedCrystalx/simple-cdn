"""
The public browsing pages.

This router owns the catch-all `/{path:path}`, which is why `main.py` registers it after
every other router: anything reaching here has already failed to match a real route. A
path can turn out to be three different things, and they are tried in that order:

  1. a file in the managed tree, served directly,
  2. a folder in the managed tree, rendered as a listing,
  3. a short endpoint, looked up in the database and either served or locked behind a
     password form.

Anything that is none of those renders the same not found page, deliberately: a missing
file and a file the caller is not meant to know about should be indistinguishable.
"""

import logging
from sqlite3 import Row

from fastapi import APIRouter, Request, Response, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from api.files import read_file
from utils.models import ReadFileMetadata, StatusResponse
from utils.database import db_manager
from utils.general import FS_FILES_KEY, transform_brand
from utils.paths import get_managed_tree_node, is_managed_file


logger = logging.getLogger("cdn.pages.index")
router = APIRouter(tags=["Index page"])
templates = Jinja2Templates(directory="pages")


def build_crumbs(path: str) -> list[dict[str, str]]:
    """
    Build the breadcrumb trail for a folder listing, root first.
    """
    crumbs: list[dict[str, str]] = [{"name": "/", "href": "/"}]
    walked: str = ""

    for part in filter(None, path.split("/")):
        walked = f"{walked}/{part}" if walked else part
        crumbs.append({"name": part, "href": f"/{walked}"})

    return crumbs

def build_items(path: str, node: dict) -> list[dict[str, str]]:
    """
    Turn a managed tree node into the rows the listing template renders: the parent link
    when there is one, then folders, then files.
    """
    base: str = f"{path}/" if path else ""
    items: list[dict[str, str]] = []

    # No parent link at the root, there is nothing above it to walk up to.
    if path:
        parent: str = path.rsplit("/", 1)[0] if "/" in path else ""
        items.append({"kind": "up", "name": "..", "href": f"/{parent}"})

    for folder in sorted(key for key in node if key != FS_FILES_KEY):
        items.append({"kind": "dir", "name": folder, "href": f"/{base}{folder}"})

    for name in sorted(node.get(FS_FILES_KEY, [])):
        items.append({"kind": "file", "name": name, "href": f"/{base}{name}"})

    return items


def render_index(req: Request, path: str, node: dict | None) -> HTMLResponse:
    """
    Render the listing page. A `node` of None renders the same template as the not found
    page, which is what `found` switches on.
    """
    logger.debug(f"Rendering the index page for '{path}' (found={node is not None}).")

    return templates.TemplateResponse(
        req, name="index/index.html",
        context={
            "path": path,
            "crumbs": build_crumbs(path),
            "items": build_items(path, node) if node is not None else [],
            "found": node is not None,
            "brand": transform_brand()
        }
    )

async def serve_file(req: Request, path: str, password: str | None) -> Response:
    """
    Hand the request to the file api, which owns the lookup and the password check.
    Anything it refuses becomes the not found page.
    """

    result: FileResponse | StatusResponse = await read_file(
        req, ReadFileMetadata(endpoint=path, protected=password)
    )

    if isinstance(result, FileResponse):
        return result

    # The reason goes to the log, the visitor only ever sees the not found page.
    logger.info(f"Could not serve '{path}': {result.message}")
    return render_index(req, path, None)


@router.get("/{path:path}", include_in_schema=False)
async def index_page(req: Request, path: str) -> Response:
    """
    Browse the public tree, or open the file at this path.

    Returns the file itself, a folder listing, the password form for a locked file, or the not found page.
    """
    path = path.strip("/")

    logger.debug(f"Index request for '{path}'.")

    # the managed tree answers first, with one of its files or a folder to browse
    if is_managed_file(path):
        return await serve_file(req, path, None)

    node: dict | None = get_managed_tree_node(path)
    if node is not None:
        return render_index(req, path, node)


    # anything left can only be a short database backed endpoint
    row: Row | None = await db_manager.execute(
        "SELECT protected_id FROM endpoints WHERE endpoint = ? LIMIT 1", (path,), fetch_one=True
    )

    if row is None:
        logger.info(f"Nothing found at '{path}'.")
        return render_index(req, path, None) # error page, not found

    if row["protected_id"] is not None:
        logger.debug(f"'{path}' is protected, showing the password form.")
        return templates.TemplateResponse(
            req, name="index/password.html",
            context={
                "path": path,
                "error": None,
                "brand": transform_brand()
            }
        )

    return await serve_file(req, path, None)


# this only runs if password was required (POST from password.html)
@router.post("/{path:path}", include_in_schema=False)
async def unlock_page(req: Request, path: str, password: str = Form()) -> Response:
    """
    Open a locked file with the password submitted from its form.

    Returns the file on success, and the form again on failure.
    """
    path = path.strip("/")

    logger.debug(f"Unlock attempt for '{path}'.")

    result: FileResponse | StatusResponse = await read_file(
        req, ReadFileMetadata(endpoint=path, protected=password)
    )

    if isinstance(result, FileResponse):
        logger.info(f"Unlocked '{path}'.")
        return result

    logger.info(f"Failed unlock attempt for '{path}'.")

    return templates.TemplateResponse(
        req, name="index/password.html",
            context={
                "path": path,
                "error": None,
                "brand": transform_brand()
            }
    )
