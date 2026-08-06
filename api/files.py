"""
File endpoints: upload, read and delete.

Three storage paths live behind these routes and the uploader's token type picks between
them. Admin uploads keep their filename and are served off the managed tree; img and
upload types are given a short random endpoint that only the database can resolve, which
is also where an optional password lives.
"""

import logging, secrets
from typing import Annotated, Union
from pathlib import Path, PurePosixPath
from sqlite3 import Row

from pydantic import Json
from fastapi import APIRouter, Request, UploadFile, Depends, Form, File
from fastapi.responses import FileResponse

from utils.database import db_manager
from utils.models import StatusResponse, User, UploadFileMetadata, ReadFileMetadata
from utils.auth import get_token_data, require_admin, hash_password
from utils.paths import write_to_disk, safe_managed_path, add_managed_file, remove_managed_file, is_managed_file
from utils.general import random_string, public_url, ENV, UPLOAD_LOCATION_MAP


logger = logging.getLogger("cdn.api.files")
router = APIRouter(prefix="/api/files", tags=["File endpoints"])


async def store_managed_upload(req: Request, file: UploadFile, metadata: UploadFileMetadata, uploader: User) -> StatusResponse:
    """
    Admin uploads are trusted, keep their own name and are served off the managed tree, so they never get a database row.
    """

    # Without a row there is nowhere to keep a password hash, so the option is refused rather than silently ignored.
    if metadata.protected:
        logger.warning(f"User {uploader.id} tried to password protect a managed upload, which is not supported.")
        return StatusResponse(status="error", message="Managed uploads cannot be password protected.")


    resolved: tuple[PurePosixPath, Path] | None = safe_managed_path(f"{metadata.extra or ''}/{file.filename}")
    if resolved is None:
        logger.warning(f"Rejected managed upload from user_id {uploader.id}: unsafe folder or file name.")
        return StatusResponse(status="error", message="Invalid folder or file name.")


    endpoint, file_path = resolved
    logger.info(f"Resolved managed file path: '{file_path}' and endpoint: '{endpoint}'.")

    if not await write_to_disk(file, file_path):
        logger.error(f"Managed upload '{file.filename}' from user_id {uploader.id} could not be written to '{file_path}'.")
        return StatusResponse(status="error", message="Failed to save the uploaded file.")


    await add_managed_file(endpoint)

    logger.info(f"Successfully uploaded managed file '{file.filename}' to '{file_path}' with endpoint '{endpoint}' for user_id {uploader.id}.")
    return StatusResponse(
        status="success",
        data={"url": public_url(req, endpoint.as_posix())}
    )

async def store_endpoint_upload(req: Request, file: UploadFile, metadata: UploadFileMetadata, uploader: User) -> StatusResponse:
    """
    img and upload types are handed a short random endpoint that only the database can
    resolve back to a file, which is also where an optional password lives.
    """

    base_path: Path = UPLOAD_LOCATION_MAP[uploader.type]
    rstring: str = random_string(10)

    # The random string is both the on disk name and the public endpoint, so the original
    # filename never appears in a URL. It is only kept as metadata for the download name.
    file_path: Path = base_path / rstring
    endpoint: str = f"{base_path.name}/{rstring}"

    logger.info(f"Resolved file path: '{file_path}' and endpoint: '{endpoint}'.")

    if not await write_to_disk(file, file_path):
        logger.error(f"Upload '{file.filename}' from user_id {uploader.id} could not be written to '{file_path}'.")
        return StatusResponse(status="error", message="Failed to save the uploaded file.")


    # Save the file metadata to the database
    async with db_manager.acquire_cursor() as cur:
        protected_id: int | None = None

        if metadata.protected:
            try:
                await cur.execute(
                    "INSERT INTO protected (hash) VALUES (?)", (hash_password(metadata.protected),)
                )

                protected_id: int = cur._cursor.lastrowid
                logger.debug(f"Created protected record {protected_id} for endpoint '{endpoint}'.")

            except Exception as e:
                await cur.connection.rollback()

                # The file is already on disk at this point, so remove it to avoid leaving an unreferenced file.
                file_path.unlink(missing_ok=True)

                logger.error(f"Failed to create protected record for file '{file.filename}': {e}")
                return StatusResponse(status="error", message="Failed to protect your file.")


        # Save the file metadata and link it to the protected record
        try:
            await cur.execute(
                "INSERT INTO endpoints (endpoint, type, name, protected_id) VALUES (?, ?, ?, ?)",
                (endpoint, uploader.type, file.filename, protected_id)
            )

        except Exception as e:
            await cur.connection.rollback()

            # The file is already on disk at this point, so remove it to avoid leaving an unreferenced file.
            file_path.unlink(missing_ok=True)

            logger.error(f"Failed to save file metadata for '{file.filename}' at endpoint '{endpoint}': {e}")
            return StatusResponse(status="error", message="Failed to save file metadata.")

        await cur.connection.commit()


    logger.info(f"Successfully uploaded {"protected" if metadata.protected else "normal"} file '{file.filename}' with endpoint '{endpoint}' for user_id {uploader.id}.")
    return StatusResponse(
        status="success",
        data={"url": public_url(req, endpoint)}
    )


@router.post("/")
async def upload_file(
    req: Request,
    file: Annotated[UploadFile, File()],
    metadata: Annotated[Json[UploadFileMetadata], Form()],
    uploader: User = Depends(get_token_data)
) -> StatusResponse:
    """
    Upload a file to the server. This endpoint requires privileges.

    The file is sent as multipart form data alongside a `metadata` field holding the JSON
    described by UploadFileMetadata. Its `type` has to match the type of the token being
    used. On success the response `data` carries the public URL of the new file.
    """

    logger.debug(f"Upload request from user {uploader.id} (token type '{uploader.type}') for '{file.filename}'.")

    # The type of the token must match the type claimed in the metadata.
    if uploader.type != metadata.type:
        logger.warning(f"User {uploader.id} holds a '{uploader.type}' token but claimed type '{metadata.type}'.")
        return StatusResponse(status="error", message="Unauthorized file upload.")

    # size is None when the client sent no length, in which case the check cannot run here.
    if file.size is None or file.size > ENV.MAX_UPLOAD_SIZE:
        logger.warning(f"Rejected {file.size} byte upload from user {uploader.id}.")
        return StatusResponse(status="error", message="File is larger than the limit or has size of 0 bytes.")

    if not file.filename:
        logger.warning(f"Rejected an upload from user {uploader.id} that carried no file name.")
        return StatusResponse(status="error", message="The upload is missing a file name.")


    if uploader.type == "admin":
        return await store_managed_upload(req, file, metadata, uploader)

    if uploader.type in ("img", "upload"):
        return await store_endpoint_upload(req, file, metadata, uploader)

    # The token type is not one of the three that can upload, so the request is rejected.
    logger.error(f"User {uploader.id} holds an unhandled token type '{uploader.type}'.")
    return StatusResponse(status="error", message="Internal error.")



@router.get("/", response_model=None)
async def read_file(req: Request, metadata: ReadFileMetadata) -> Union[FileResponse, StatusResponse]:
    """
    Read a file from the server. Requires the password if the file is locked.

    Returns the file itself, or a `StatusResponse` describing why it could not be served.
    """
    endpoint: str = metadata.endpoint.strip("/")

    file_path: Path
    file_name: str

    logger.debug(f"Read request for endpoint '{endpoint}'.")

    if is_managed_file(endpoint):
        resolved: tuple[PurePosixPath, Path] | None = safe_managed_path(endpoint)

        if resolved is None:
            logger.warning(f"Managed endpoint '{endpoint}' did not resolve to a safe path.")
            return StatusResponse(status="error", message="File not found on the server.")

        file_path = resolved[1]
        file_name = file_path.name

    else:
        # One query for the file and the password hash it may be linked to, the LEFT JOIN
        # keeps unprotected files in the result with a NULL hash.
        row: Row | None = await db_manager.execute((
            "SELECT e.type, e.name, p.hash FROM endpoints e "
            "LEFT JOIN protected p ON e.protected_id = p.id "
            "WHERE e.endpoint = ? LIMIT 1 "),
            (endpoint,), fetch_one=True
        )

        if row is None:
            logger.info(f"No file is registered at endpoint '{endpoint}'.")
            return StatusResponse(status="error", message="File not found on the server.")

        base_path: Path | None = UPLOAD_LOCATION_MAP.get(row["type"])

        if base_path is None:
            logger.error(f"Endpoint '{endpoint}' claims unknown upload type '{row["type"]}'.")
            return StatusResponse(status="error", message="File not found on the server.")

        protect_hash: str = row["hash"]

        if protect_hash:
            if not metadata.protected:
                logger.info(f"Endpoint '{endpoint}' is protected and no password was supplied.")
                return StatusResponse(status="error", message="Incorrect password for protected file.")

            # compare_digest rather than ==, so the comparison does not leak the hash
            if not secrets.compare_digest(hash_password(metadata.protected), protect_hash):
                logger.warning(f"Incorrect password supplied for protected endpoint '{endpoint}'.")
                return StatusResponse(status="error", message="Incorrect password for protected file.")

            logger.debug(f"Password accepted for protected endpoint '{endpoint}'.")

        file_path = base_path / endpoint.rpartition("/")[2] # file identifier
        file_name = row["name"]


    logger.debug(f"Resolved file path: '{file_path}' and file name: '{file_name}' for endpoint '{endpoint}'.")

    # The record can outlive the file if it was removed outside the API, so the disk gets
    # the final say before a response promises anything.
    if not file_path.is_file():
        logger.error(f"File '{file_name}' at path '{file_path}' does not exist or is not a file.")
        return StatusResponse(status="error", message="File not found on the server.")


    logger.info(f"Serving '{file_name}' for endpoint '{endpoint}'.")
    return FileResponse(path=file_path, filename=file_name, content_disposition_type="inline")



async def delete_managed_file(endpoint: str) -> StatusResponse:
    """
    Drop a managed upload from disk and from the tree, there is no metadata to clean up.
    """

    resolved: tuple[PurePosixPath, Path] | None = safe_managed_path(endpoint)

    if resolved is None:
        logger.warning(f"Refusing to delete '{endpoint}', it does not resolve to a safe managed path.")
        return StatusResponse(status="error", message="Invalid folder or file name.")

    managed_endpoint, file_path = resolved

    try:
        file_path.unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Failed to delete managed file at path '{file_path}': {e}")
        return StatusResponse(status="error", message="The file could not be deleted.")

    await remove_managed_file(managed_endpoint)

    logger.info(f"Successfully deleted managed file at path '{file_path}' for endpoint '{endpoint}'.")
    return StatusResponse(status="success", message="File deleted successfully.")

async def delete_endpoint_file(endpoint: str) -> StatusResponse:
    """
    Drop a database backed upload, its metadata and the password record it may hold.
    """
    row: Row | None = await db_manager.execute("SELECT type, protected_id FROM endpoints WHERE endpoint = ? LIMIT 1 ", (endpoint,))
    if row is None:
        logger.info(f"Nothing to delete, no file is registered at endpoint '{endpoint}'.")
        return StatusResponse(status="error", message="File not found on the server.")


    base_path: Path | None = UPLOAD_LOCATION_MAP.get(row["type"])
    if base_path is None:
        logger.error(f"Refusing to delete '{endpoint}', it claims unknown upload type '{row["type"]}'.")
        return StatusResponse(status="error", message="Internal error.")

    file_path: Path = base_path / endpoint.rpartition("/")[2]
    protected_id: int | None = row["protected_id"]

    logger.debug(f"Deleting endpoint '{endpoint}' at '{file_path}' (protected_id {protected_id}).")

    # Metadata goes first: a row without its file reads as a broken link, whereas a file
    # without its row is unreachable and would never be cleaned up.
    async with db_manager.acquire_cursor() as cur:
        try:
            await cur.execute("DELETE FROM endpoints WHERE endpoint = ?", (endpoint,))

        except Exception as e:
            await cur.connection.rollback()

            logger.error(f"Failed to delete metadata for file at endpoint '{endpoint}': {e}")
            return StatusResponse(status="error", message="Failed to delete file metadata.")

        await cur.connection.commit()


    try:
        file_path.unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Failed to delete file at path '{file_path}': {e}")
        return StatusResponse(status="error", message="Metadata was removed, but the file could not be deleted.")

    logger.info(f"Successfully deleted file at path '{file_path}' and its metadata for endpoint '{endpoint}'.")
    return StatusResponse(status="success", message="File deleted successfully.")


@router.delete("/")
async def delete_file(req: Request, metadata: ReadFileMetadata, _: int = Depends(require_admin)) -> StatusResponse:
    """
    Delete a file and, when it has any, its metadata. This endpoint requires admin privileges.
    """
    endpoint: str = metadata.endpoint.strip("/")

    logger.info(f"Delete requested for endpoint '{endpoint}'.")

    # managed uploads never reach the database, the tree and the disk are all they have
    if is_managed_file(endpoint):
        return await delete_managed_file(endpoint)

    return await delete_endpoint_file(endpoint)
