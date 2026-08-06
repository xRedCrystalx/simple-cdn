# Documentation

Detailed reference for `simple-cdn`. For installation and deployment steps see [README.md](README.md).

**Contents**
- [Features](#features)
- [Configuration](#configuration)
- [File Locations](#file-locations)
- [How the API Works](#how-the-api-works)

---

## Features

- Token-based authentication with three privilege levels: `admin`, `img`, `upload`.
- A programmatic HTTP API under `/api` for uploading, downloading and deleting files, plus admin-only endpoints for issuing tokens and reading service statistics.
- Two storage models, picked by the uploading token's type:
  - **Managed uploads** (`admin` tokens) keep their original file name and folder structure, are served straight off disk at the site root, and are browsable through a folder-listing UI.
  - **Endpoint uploads** (`img`/`upload` tokens) are written under a short random, unguessable endpoint; the original file name never appears in the URL and there is no directory listing.
- Optional per-file password protection for endpoint uploads. Passwords are hashed with scrypt and never stored in plain text.
- A minimal web UI:
  - `/` browses the managed file tree, or resolves a short endpoint and serves it (prompting for a password if it is locked).
  - `/upload` is a plain upload form for anyone holding an `upload` token.
  - `/admin` is the admin panel: live statistics, managed uploads, token issuing/revocation, and file deletion.

---

## Configuration

### Environment variables

All configuration is read from `.env` (see `.env.example`) once, at process start.

| Variable | Default | Description |
|---|---|---|
| `BRAND_NAME` | `simple.cdn` | Display name used in page titles and headings. |
| `DEBUG` | `1` | Enables debug-level logging and prints a startup banner. Should be unset/`0` in production. |
| `PORT` | `8000` | Port the service binds to. |
| `HOST` | `localhost` | Address the service binds to. |
| `DOMAIN` | *(required)* | Public domain the service is reachable at. The service refuses to start without it. |
| `DB_POOL_SIZE` | `16` | Number of pooled SQLite connections. |
| `LOG_LEVEL` | `INFO` | Log level for the console and file handlers. |
| `LOG_RETENTION_DAYS` | `30` | How many rotated daily log files to keep. |
| `CHUNK_SIZE` | `1048576` (1 MB) | Chunk size used while streaming an upload to disk. |
| `MAX_UPLOAD_SIZE` | `536870912` (512 MB) | Maximum accepted upload size, in bytes. |
| `PUBLIC_DIR` | `public` | Root directory for managed uploads, images and uploads. |
| `TOKEN_PREFIX` | `Token ` | Prefix expected before the token value in the `Red-Authorization` header. |
| `TOKEN_SIZE` | `32` | Byte length passed to `secrets.token_urlsafe()` when a token is issued. |
| `SCRYPT_SECRET` | *(required)* | Secret used as the scrypt salt for file passwords. Changing it invalidates every existing protected file. |
| `SCRYPT_N` | `16384` | scrypt CPU/memory cost parameter. |
| `SCRYPT_R` | `8` | scrypt block size parameter. |
| `SCRYPT_P` | `1` | scrypt parallelization parameter. |
| `SCRYPT_MAXMEM` | `0` | scrypt max memory (`0` = library default). |
| `SCRYPT_DKLEN` | `64` | scrypt derived key length, in bytes. |

`SCRYPT_SECRET` and `DOMAIN` have no default - the service raises an error at startup if either is missing.

### Static files

Served directly from `static/`, outside the API and outside the OpenAPI schema:

- `static/favicon.ico` -> `GET /favicon.ico`
- `static/robots.txt` -> `GET /robots.txt`, currently `Disallow: /` for every crawler, so hosted content is not indexed by search engines.

Both names are reserved in the managed file tree (see [Reserved routes](#reserved-routes)), so an admin upload can never shadow them.

---

## File Locations

Where each token type's uploads live on disk, and the URL space they are served under.

| URL prefix | Disk location | Written by | Notes |
|---|---|---|---|
| `/` (root) | `public/managed/` | `admin` tokens | Keeps its original name and folder path; browsable as a folder listing. |
| `/uploads/<endpoint>` | `public/uploads/` | `upload` tokens | Random endpoint; original file name is hidden from the URL. |
| `/img/<endpoint>` | `public/img/` | `img` tokens | Random endpoint; original file name is hidden from the URL. |

Example: a managed upload at `public/managed/test/logo.png` is served at `https://your-domain.com/test/logo.png`.

Example: upload via `/upload` page is served at `https://your-domain.com/uploads/abcdefgh`

### Reserved routes

These top-level names belong to the app itself and can never be shadowed by an admin upload:

`api/*`, `uploads/*`, `img/*`, `admin`, `upload`, `favicon.ico`, `robots.txt`

---

## How the API Works

### Authentication

Every token-gated request carries its token in a custom header:

```
Red-Authorization: Token <token>
```

The `Token ` prefix is configurable via `TOKEN_PREFIX` and is stripped before the token is looked up, so it has to match whatever the server is configured with. A missing or unknown token gets a `403`.

Tokens are opaque strings issued by an admin (`POST /api/admin/token`, or the first one printed by `setup.py`). Each token has exactly one type, and that type decides what it may do:

| Type | Can do |
|---|---|
| `admin` | Everything: upload to the managed tree, delete any file, issue/revoke tokens, read statistics. |
| `img` | Upload files under `/img/<endpoint>`, optionally password protected. |
| `upload` | Upload files under `/uploads/<endpoint>`, optionally password protected. |

> [!CAUTION]
> Anyone holding an `img`/`upload` token can host arbitrary files, including HTML and JS, at a URL on your domain. Only issue tokens to people you trust - see the note in the [README](README.md).

### Response shape

Most endpoints return a `StatusResponse`:

```json
{
  "status": "success" | "error",
  "message": "optional human-readable text",
  "data": null | { *extra data in json* }
}
```

Endpoints that hand back a file return the raw file bytes instead (`GET /api/files/`, or the plain `GET /<endpoint>` route).

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/files/` | any token | Upload a file. |
| `GET` | `/api/files/` | none | Download/read a file by endpoint, plus its password if protected. |
| `DELETE` | `/api/files/` | `admin` | Delete a file and its metadata. |
| `POST` | `/api/admin/token` | `admin` | Issue a new token for a user. |
| `DELETE` | `/api/admin/token` | `admin` | Revoke one token, or every token belonging to a user. |
| `GET` | `/api/admin/stats` | `admin` | Upload/screenshot/admin-token counters. |

Everyday browsing - folder listings, plain file links, the password form - goes through the site's own `GET`/`POST /{path}` routes rather than `/api/files/`. `/api/files/` is the raw, scriptable form of the same lookups, meant for uploading, deleting, and reading files programmatically.

### Examples

**Upload a file.** The body is multipart form data: the file itself plus a `metadata` field holding JSON.

```bash
curl -X POST "https://your-domain.com/api/files/" \
  -H "Red-Authorization: Token YOUR_TOKEN" \
  -F "file=@/path/to/photo.png" \
  -F 'metadata={"type": "img", "protected": null}'
```

`metadata.type` must match the token's own type. `protected`, a plain-text password, locks the file behind that password (only valid for `img`/`upload`). 

The `extra` parameter is admin only, specifies the destination folder inside the managed tree, e.g. `"extra": "files/2026"`.

On success:

```json
{ "status": "success", "data": { "url": "https://your-domain.com/img/AbCdEfGhIJ" } }
```

**Download a file**, the ordinary way - this is what the returned URL is for:

```bash
curl -O "https://your-domain.com/img/AbCdEfGhIJ"
```

Download the same file through the API instead, useful when it is password protected:

```bash
curl -X GET "https://your-domain.com/api/files/" \
  -H "Content-Type: application/json" \
  -d '{"endpoint": "img/AbCdEfGhIJ", "protected": "file-password"}' \
  -o photo.png
```

**Delete a file** (admin only):

```bash
curl -X DELETE "https://your-domain.com/api/files/" \
  -H "Red-Authorization: Token ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"endpoint": "img/AbCdEfGhIJ"}'
```

**Issue a token** for an existing user (create the user first with `python3 create_user.py`):

```bash
curl -X POST "https://your-domain.com/api/admin/token" \
  -H "Red-Authorization: Token ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 2, "type": "upload"}'
```

```json
{ "token": "the-new-token-shown-once" }
```

**Revoke a token**, either by value or by user - provide exactly one of the two:

```bash
curl -X DELETE "https://your-domain.com/api/admin/token" \
  -H "Red-Authorization: Token ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 2}'
    # or
  -d '{"token": "token-to-remove"}'
```

**Read the service counters:**

```bash
curl "https://your-domain.com/api/admin/stats" \
  -H "Red-Authorization: Token ADMIN_TOKEN"
```

```json
{
  "total_uploads": 12,
  "total_screenshots": 4,
  "total_admin_tokens": 1,
  "used_storage": null,
  "available_storage": null
}
```