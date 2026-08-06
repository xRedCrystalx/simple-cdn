"""
Token authentication and password hashing.

Callers identify themselves with a `Red-Authorization: <TOKEN_PREFIX><token>` header. The
dependencies here turn that into a `User`, or raise 403.
"""

import logging, hashlib

from sqlite3 import Row
from fastapi import Header, HTTPException

from utils.database import db_manager
from utils.general import ENV
from utils.models import User

logger = logging.getLogger("cdn.auth")


async def get_token_data(red_authorization: str | None = Header(None)) -> User | None:
    """
    FastAPI dependency resolving the request's token into the account behind it.

    Raises 403 when the header is absent or the token is not one the service issued.
    """
    if red_authorization is None:
        logger.warning("Rejected a request that carried no authorization header.")
        raise HTTPException(403)

    auth: Row | None = await db_manager.execute(
        "SELECT * FROM auth_tokens WHERE token = ? LIMIT 1",
        (red_authorization.removeprefix(ENV.TOKEN_PREFIX), ), fetch_one=True
    )

    if auth is None:
        logger.warning("Rejected a request carrying an unknown token.")
        raise HTTPException(403)

    logger.debug(f"Authenticated user_id {auth['uid']} of type '{auth['type']}'.")
    return User(id=auth["uid"], type=auth["type"])


async def require_auth(red_authorization: str | None = Header(None), _type: str | None = None) -> int:
    """
    Resolve the token and, when `_type` is given, require it to be of that type.

    Returns the account id, which is what the endpoints record against an upload.
    """
    auth: User | None = await get_token_data(red_authorization)

    if auth is None:
        logger.warning("Rejected a request whose token resolved to nothing.")
        raise HTTPException(403)

    if _type is not None and auth.type != _type:
        logger.warning(f"Rejected user_id {auth.id}: token is of type '{auth.type}', the route needs '{_type}'.")
        raise HTTPException(403)

    return auth.id


async def require_admin(red_authorization: str | None = Header(None)) -> int:
    """
    Dependency admitting only admin tokens.
    """
    return await require_auth(red_authorization, _type="admin")

async def require_img(red_authorization: str | None = Header(None)) -> int:
    """
    Dependency admitting only img tokens.
    """
    return await require_auth(red_authorization, _type="img")

async def require_upload(red_authorization: str | None = Header(None)) -> int:
    """
    Dependency admitting only upload tokens.
    """
    return await require_auth(red_authorization, _type="upload")


def hash_password(passwd: str) -> str:
    """
    Hash a file password with scrypt, using SCRYPT_SECRET as the salt.

    Changing that value in the environment makes every existing protected file unopenable.
    """
    hashed_bytes: bytes = hashlib.scrypt(
        passwd.encode("utf-8"),
        salt=ENV.SCRYPT_SECRET.encode("utf-8"),
        n=ENV.SCRYPT_N,
        r=ENV.SCRYPT_R,
        p=ENV.SCRYPT_P,
        maxmem=ENV.SCRYPT_MAXMEM,
        dklen=ENV.SCRYPT_DKLEN
    )

    return hashed_bytes.hex()
