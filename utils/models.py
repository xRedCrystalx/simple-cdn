"""
Pydantic models describing every request and response body the API accepts or returns.

These double as the OpenAPI schema, so the field names and docstrings here are public.
"""

from typing import Literal, Any
from pydantic import BaseModel


class StatusResponse(BaseModel):
    """The service's generic result."""

    status: Literal["success", "error"]
    message: str | None = None

    # Deliberately untyped: the payload differs per endpoint (an upload returns `{"url": ...}`)
    data: Any | None = None

class User(BaseModel):
    """
    The caller behind an authentication token, as resolved from the `Red-Authorization` header.
    """

    id: int
    type: Literal["admin", "img", "upload"]

class UserAccount(BaseModel):
    """
    A registered account. The admin panel lets an operator pick one by name, then sends
    the `id` back when it asks for a token.
    """

    id: int
    username: str

class UserListResponse(BaseModel):
    """
    Every account the service knows about.
    """

    users: list[UserAccount]


class AuthTokenRequest(BaseModel):
    """
    Request body for issuing a token: which account it belongs to and what it may do.
    """

    user_id: int
    type: Literal["admin", "img", "upload"]

class AuthTokenResponse(BaseModel):
    """
    A freshly issued token. Returned once and never retrievable again afterwards.
    """

    token: str

class DeleteTokenRequest(BaseModel):
    """
    Request body for revoking tokens. Exactly one field is expected: `token` revokes that
    single token, `user_id` revokes every token an account holds.
    """

    token: str | None = None
    user_id: int | None = None


class StatisticsResponse(BaseModel):
    """
    Counters describing what the service currently holds.
    """

    total_uploads: int
    total_screenshots: int
    total_admin_tokens: int
    used_storage: float
    available_storage: float


class UploadFileMetadata(BaseModel):
    """
    The metadata part of an upload, sent as a JSON encoded form field alongside the file.
    """

    type: Literal["admin", "img", "upload"]
    protected: str | None = None

    # The target folder, admin uploads only
    extra: str | None = None

class ReadFileMetadata(BaseModel):
    """
    Identifies a single file by its public endpoint, plus the password when it has one.
    """

    endpoint: str
    protected: str | None = None
