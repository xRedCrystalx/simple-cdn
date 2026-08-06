"""
Admin endpoints: issuing and revoking tokens, and reading the service counters.

The router carries `require_admin` as a router level dependency, so every route below is
admin only without repeating the check.
"""

import logging, secrets, shutil
from fastapi import APIRouter, Request, Depends
from typing import Union
from sqlite3 import Row

from utils.general import ENV
from utils.database import db_manager
from utils.models import (
    StatusResponse, AuthTokenRequest, AuthTokenResponse, DeleteTokenRequest, StatisticsResponse,
    UserAccount, UserListResponse
)
from utils.auth import require_admin

logger = logging.getLogger("cdn.api.admin")
router = APIRouter(
    prefix="/api/admin", tags=["Admin endpoints"], dependencies=[Depends(require_admin)],
    responses={403: {"model": StatusResponse, "description": "The token is missing, unknown or not an admin token."}}
)


@router.get("/users")
async def get_users(req: Request) -> UserListResponse:
    """
    List every account by id and username. This endpoint requires admin privileges.

    Only the two columns the `users` table holds, there is nothing secret in either. The
    admin panel reads this to offer usernames where the token endpoints want an id.
    """
    rows: list[Row] = await db_manager.execute("SELECT id, username FROM users ORDER BY username COLLATE NOCASE", ())

    logger.debug(f"Listed {len(rows)} user account(s).")

    return UserListResponse(users=[UserAccount(id=row["id"], username=row["username"]) for row in rows])


@router.post("/token")
async def create_token(req: Request, token_req: AuthTokenRequest) -> Union[AuthTokenResponse, StatusResponse]:
    """
    Create a new authentication token for a user. This endpoint requires admin privileges.

    The token is returned once, in full, and cannot be retrieved again afterwards.
    """
    token: str = secrets.token_urlsafe(ENV.TOKEN_SIZE)

    logger.debug(f"Issuing a '{token_req.type}' token for user_id {token_req.user_id}.")

    async with db_manager.acquire_cursor() as cur:

        try:
            await cur.execute(
                "INSERT INTO auth_tokens (token, uid, type) VALUES (?, ?, ?)",
                (token, token_req.user_id, token_req.type)
            )

        except Exception as e:
            
            # Most often a user_id with no matching account, which the foreign key refuses.
            await cur.connection.rollback()
            logger.error(f"Failed to generate auth token for user_id {token_req.user_id} of type '{token_req.type}': {e}")
            return StatusResponse(status="error", message="Failed to create auth token.")

        await cur.connection.commit()
        logger.info(f"Generated new auth token for user_id {token_req.user_id} of type '{token_req.type}'")

    return AuthTokenResponse(token=token)


@router.delete("/token")
async def delete_token(req: Request, token_del: DeleteTokenRequest) -> StatusResponse:
    """
    Delete specified token or all tokens of a user. This endpoint requires admin privileges.

    Provide exactly one of `token` or `user_id`.
    """

    # Both would be ambiguous, neither leaves nothing to act on; either way the caller
    # has to say which of the two they meant.
    if token_del.token and token_del.user_id:
        logger.warning("Rejected a token deletion that specified both a token and a user_id.")
        return StatusResponse(status="error", message="Provide either token or user_id, not both.")

    elif token_del.token:
        async with db_manager.acquire_cursor() as cur:
            try:
                await cur.execute("DELETE FROM auth_tokens WHERE token = ?", (token_del.token,))
            except Exception as e:
                await cur.connection.rollback()

                # The token value stays out of the message, the log is not a place to
                # leave working credentials lying around.
                logger.error(f"Failed to delete a single auth token: {e}")
                return StatusResponse(status="error", message="Failed to delete auth token.")

            await cur.connection.commit()
            logger.info("Deleted a single auth token.")

    elif token_del.user_id:
        async with db_manager.acquire_cursor() as cur:
            try:
                await cur.execute("DELETE FROM auth_tokens WHERE uid = ?", (token_del.user_id,))

            except Exception as e:
                await cur.connection.rollback()

                logger.error(f"Failed to delete auth tokens for user_id '{token_del.user_id}': {e}")
                return StatusResponse(status="error", message="Failed to delete auth tokens for the specified user")

            await cur.connection.commit()
            logger.info(f"Deleted every auth token belonging to user_id {token_del.user_id}.")

    else:
        logger.warning("Rejected a token deletion that specified neither a token nor a user_id.")
        return StatusResponse(status="error", message="Provide either token or user_id.")

    return StatusResponse(status="success", message="Token(s) deleted successfully.")


@router.get("/stats")
async def get_statistics(req: Request) -> StatisticsResponse:
    """
    Retrieve statistics about uploads, screenshots, and admin tokens. This endpoint requires admin privileges.
    """
    # One cursor for all three counts, they are only ever read together.
    async with db_manager.acquire_cursor() as cur:
        total_uploads_row = await cur.execute("SELECT COUNT(*) AS total FROM endpoints WHERE type = 'upload'")
        total_uploads = (await total_uploads_row.fetchone())["total"]

        total_screenshots_row = await cur.execute("SELECT COUNT(*) AS total FROM endpoints WHERE type = 'img'")
        total_screenshots = (await total_screenshots_row.fetchone())["total"]

        total_admin_tokens_row = await cur.execute("SELECT COUNT(*) AS total FROM auth_tokens WHERE type = 'admin'")
        total_admin_tokens = (await total_admin_tokens_row.fetchone())["total"]

    logger.debug(f"Statistics: {total_uploads} uploads, {total_screenshots} screenshots, {total_admin_tokens} admin tokens.")

    # disk information
    disk = shutil.disk_usage(ENV.PUBLIC_DIR)
    total_gb: float = disk.total / (1024 ** 3)
    used_gb: float = disk.used / (1024 ** 3)

    return StatisticsResponse(
        total_uploads=total_uploads,
        total_screenshots=total_screenshots,
        total_admin_tokens=total_admin_tokens,
        total_storage=total_gb,
        used_storage=used_gb
    )
