"""
Configuration and the small helpers shared across the service.

This module is imported before logging is configured (`ENV` has to exist for the logger
to read its own settings), so anything it logs at import time would be lost. The class
body therefore reports fatal misconfiguration by raising instead of logging.
"""

import secrets, string, os, logging
from pathlib import Path

from fastapi import Request

logger = logging.getLogger("cdn.general")


class ENV:
    """
    Environment backed settings, read once at import time.

    Every value has a default except the two the service refuses to guess:
    - SCRYPT_SECRET, because a default would make every stored password hash forgeable,
    - DOMAIN, because a wrong one hands out URLs that do not resolve.
    """

    BRAND_NAME: str = os.getenv("BRAND_NAME", "simple.cdn")
    DEBUG: bool = bool(os.getenv("DEBUG", False))
    PORT: int = int(os.getenv("PORT", 8000))
    HOST: str = os.getenv("HOST", "localhost")
    DOMAIN: str | None = os.getenv("DOMAIN", None)

    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", 16))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_RETENTION_DAYS: int = int(os.getenv("LOG_RETENTION_DAYS", 30))

    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", 1024 * 1024 * 1)) # 1MB
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", 1024 * 1024 * 512)) # 512MB
    PUBLIC_DIR: str = os.getenv("PUBLIC_DIR", "public")

    TOKEN_PREFIX: str = os.getenv("TOKEN_PREFIX", "Token ")
    TOKEN_SIZE: int = int(os.getenv("TOKEN_SIZE", 32))

    SCRYPT_SECRET: str = os.getenv("SCRYPT_SECRET")
    SCRYPT_N: int = int(os.getenv("SCRYPT_N", 16384))
    SCRYPT_R: int = int(os.getenv("SCRYPT_R", 8))
    SCRYPT_P: int = int(os.getenv("SCRYPT_P", 1))
    SCRYPT_MAXMEM: int = int(os.getenv("SCRYPT_MAXMEM", 0))
    SCRYPT_DKLEN: int = int(os.getenv("SCRYPT_DKLEN", 64))

    if not SCRYPT_SECRET:
        raise ValueError("SECRET environment variable is not set. Please set it in your .env file.")

    if not DOMAIN:
        raise ValueError("DOMAIN environment variable is not set. Please set it in your .env file.")


# Where each uploader type is allowed to write.
UPLOAD_LOCATION_MAP: dict[str, Path] = {
    "admin": Path(ENV.PUBLIC_DIR) / "managed",
    "img": Path(ENV.PUBLIC_DIR) / "img",
    "upload": Path(ENV.PUBLIC_DIR) / "uploads"
}

# In memory mirror of the managed directory, rebuilt from disk on startup and kept in
# step by the upload and delete paths, so browsing never has to hit the filesystem.
FS_MANAGED_TREE: dict[str, list[str | dict[str, list]]] = {}

# Key under which a tree node keeps its file names, separating them from its subfolders.
FS_FILES_KEY: str = "_files"

# Top level names the router already owns. A managed upload claiming one of these would
# shadow a real route, so they are refused outright.
FS_RESERVED_ROOTS: frozenset[str] = frozenset({
    "api", "admin", "upload", "img", "uploads", "favicon.ico", "robots.txt"
})


_ALPHABET: str = "".join(
    c for c in string.ascii_letters + string.digits if c not in "0OIl" # remove confusing characters
)

def random_string(length: int = 8) -> str:
    """Generate a random alphanumeric string of the given length."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))

def public_url(req: Request, endpoint: str) -> str:
    """Build a public URL for a given endpoint, using the request's base URL."""
    return f"https://{ENV.DOMAIN}/{endpoint}"

def human_size(size: int) -> str:
    """
    Render a byte count for the pages, so the limits they show come from the environment.
    """
    units: tuple[str, ...] = ("B", "KB", "MB", "GB", "TB") # probably won't need more than this, but can be extended if necessary

    value: float = float(size)
    unit: int = 0

    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1

    return f"{value:.1f}".removesuffix(".0") + f" {units[unit]}"

def transform_brand() -> str:
    """Transform the brand name into simple-cdn style heading."""
    return ENV.BRAND_NAME.replace(".", "<span class='dot'>.</span>")
