"""
Filesystem work: writing uploads to disk and maintaining the managed file tree.

Managed uploads (the admin ones) keep their original names and are served straight off
the path they were written to, so the path a request asks for is attacker controlled.
`safe_managed_path()` is the gatekeeper that ensures a request cannot escape the managed 
directory or collide with the tree's own bookkeeping.

`FS_MANAGED_TREE` mirrors that directory in memory. It is built once from disk on startup
and updated in place as uploads are added and removed. The tree is used to answer
requests for managed files without hitting file system to generate the index page
listing a folder's contents.
"""

import aiofile, logging
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from utils.general import ENV, FS_FILES_KEY, FS_RESERVED_ROOTS, FS_MANAGED_TREE, UPLOAD_LOCATION_MAP

logger = logging.getLogger("cdn.paths")


async def write_to_disk(file: UploadFile, file_path: Path) -> bool:
    """
    Stream an upload to `file_path`, creating the folders it needs on the way.
    Cleans up the half written file and returns False when anything goes wrong.
    """
    logger.debug(f"Writing '{file.filename}' to '{file_path}' in {ENV.CHUNK_SIZE} byte chunks.")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        written: int = 0

        # Chunked rather than read(). A large upload would otherwise be held in memory
        # in full, and MAX_UPLOAD_SIZE defaults to 512MB.
        async with aiofile.async_open(file_path, "wb") as out:
            while chunk := await file.read(ENV.CHUNK_SIZE):
                await out.write(chunk)
                written += len(chunk)

    except Exception as e:
        logger.error(f"Failed to save file '{file.filename}': {e}")
        file_path.unlink(missing_ok=True)

        return False

    logger.info(f"Wrote {written} bytes of '{file.filename}' to '{file_path}'.")
    return True


def safe_managed_path(path: str | None) -> tuple[PurePosixPath, Path] | None:
    """
    Turn path parts into an (endpoint, absolute path) pair inside the managed directory.
    Returns None when anything about the path is unsafe.
    """
    if path is None:
        logger.warning("Rejected None managed path.")
        return None

    segments: list[str] = []

    # Backslashes are normalised first so a Windows style path cannot smuggle a separator past the checks below.
    parts: list[str] = path.replace("\\", "/").split("/")

    for seg in parts:
        # Empty segments and traversal markers are dropped rather than rejected, the
        # resolve() check further down is what actually contains an escape attempt.
        if not seg or seg in (".", ".."):
            continue

        # A file named like the tree's file key would collide with the tree structure.
        if seg == FS_FILES_KEY:
            logger.warning(f"Rejected managed path segment '{seg}'.")
            return None

        segments.append(seg)

    if not segments:
        logger.warning(f"Rejected empty managed path '{path}'.")
        return None

    if segments[0].lower() in FS_RESERVED_ROOTS:
        logger.warning(f"Rejected managed path using reserved root '{segments[0]}'.")
        return None

    endpoint = PurePosixPath(*segments)
    base: Path = UPLOAD_LOCATION_MAP["admin"].resolve()
    resolved: Path = (base / endpoint).resolve()

    # resolve() has followed any symlink and collapsed any traversal the loop above let through, 
    # so whatever is left has to sit under base.
    if not resolved.is_relative_to(base):
        logger.warning(f"Rejected managed path escaping base: '{path}'.")
        return None

    logger.debug(f"Accepted managed path '{path}' as endpoint '{endpoint}'.")
    return endpoint, resolved


def get_managed_tree_node(path: str) -> dict | None:
    """
    Walk the managed tree down to `path`, returns the folder node or None.
    """
    node: dict = FS_MANAGED_TREE

    for part in filter(None, path.split("/")):
        node = node.get(part)

        # Either the part does not exist, or it is a file rather than a folder.
        if not isinstance(node, dict):
            logger.debug(f"No managed folder at '{path}'.")
            return None

    return node


def is_managed_file(path: str) -> bool:
    """
    Report whether `path` names a file the managed tree knows about.

    This is the check that decides whether a request is answered off the managed tree or
    looked up in the database, so it only ever consults memory.
    """
    parent, _, name = path.rpartition("/")
    parent_node: dict | None = get_managed_tree_node(parent)

    return (parent_node is not None) and (name in parent_node.get(FS_FILES_KEY, []))



def _scan_managed_tree(location: Path) -> dict[str, list | dict]:
    """
    Recursively read `location` into a tree node: subfolders become nested dicts, file
    names collect under FS_FILES_KEY.
    """
    tree: dict[str, list | dict] = {}

    for item in sorted(location.iterdir(), key=lambda entry: entry.name):

        # Symlinks are skipped because they could point anywhere outside the managed
        # directory, and the file key is reserved for the tree's own bookkeeping.
        if item.is_symlink() or item.name == FS_FILES_KEY:
            logger.warning(f"Skipping unservable managed entry '{item}'.")
            continue

        if item.is_dir():
            tree[item.name] = _scan_managed_tree(item)

        elif item.is_file():
            tree.setdefault(FS_FILES_KEY, [])\
                .append(item.name)

    return tree

async def reload_managed_tree() -> None:
    """
    Rebuild the whole managed tree from disk. Called once on startup.
    """
    location: Path = UPLOAD_LOCATION_MAP["admin"]

    logger.debug(f"Scanning '{location}' to rebuild the managed file tree.")

    try:
        tree: dict[str, list | dict] = _scan_managed_tree(location)

    except OSError as e:
        # An unreadable managed directory is not fatal: the database backed endpoints
        # still work, so the service starts with an empty tree and says so loudly.
        logger.error(f"Could not read the managed directory '{location}', starting with an empty tree: {e}")
        return

    # Mutated in place rather than rebound, other modules hold a reference to this dict.
    FS_MANAGED_TREE.clear()
    FS_MANAGED_TREE.update(tree)

    logger.info(f"Loaded managed file tree from '{location}'.")


async def add_managed_file(endpoint: PurePosixPath) -> None:
    """
    Register a newly written managed file, creating the missing folder nodes.
    """
    node: dict = FS_MANAGED_TREE

    for part in endpoint.parts[:-1]:
        child = node.get(part)

        # A missing node, or a name that somehow holds a file list, is replaced with a
        # folder so the walk can carry on.
        if not isinstance(child, dict):
            logger.debug(f"Creating managed tree folder node '{part}' for '{endpoint}'.")
            node[part] = dict()

        node = node[part]

    files: list[str] = node.setdefault(FS_FILES_KEY, [])

    # Sorted on insert, which is what lets the index page list a folder without sorting.
    if endpoint.name not in files:
        files.append(endpoint.name)
        files.sort()

    logger.info(f"Added '{endpoint}' to the managed file tree.")


def _prune_empty_dirs(location: Path, root: Path) -> None:
    """
    Delete `location` and each empty parent above it, stopping at `root`.

    Disk is pruned alongside the tree so that a restart, which rebuilds the tree by
    scanning, produces exactly the same structure it had before.
    """
    location = location.resolve()
    root = root.resolve()

    while location != root and root in location.parents:
        try:
            location.rmdir()
            logger.debug(f"Pruned empty managed folder '{location}'.")

        except OSError:
            # still holds something, or is already gone
            return

        location = location.parent

async def remove_managed_file(endpoint: PurePosixPath) -> None:
    """
    Drop a managed file from the tree and prune the folders it leaves empty.
    """
    # The path walked down is kept so the empty folder nodes can be unwound afterwards.
    walked: list[tuple[dict, str]] = []
    node: dict = FS_MANAGED_TREE

    for part in endpoint.parts[:-1]:
        child = node.get(part)

        if not isinstance(child, dict):
            logger.warning(f"Cannot remove '{endpoint}' from the tree, folder '{part}' is not there.")
            return

        walked.append((node, part))
        node = child

    files: list[str] | None = node.get(FS_FILES_KEY)

    if (not files) or (endpoint.name not in files):
        logger.warning(f"Cannot remove '{endpoint}' from the tree, it holds no such file.")
        return

    files.remove(endpoint.name)

    if not files:
        del node[FS_FILES_KEY]

    # Walk back up, dropping every folder node the removal has just emptied.
    for parent, part in reversed(walked):
        if parent[part]:
            break

        del parent[part]

    root: Path = UPLOAD_LOCATION_MAP["admin"]
    _prune_empty_dirs((root / endpoint).parent, root)

    logger.info(f"Removed '{endpoint}' from the managed file tree.")
