# simple-cdn

A lightweight self-hosted CDN/file host built with FastAPI. It serves uploaded files,
supports token-based auth, offers a simple programmatic API, and includes a minimal admin panel and upload UI.

More in-depth information can be found in the [documentation](DOCUMENTATION.md).

> [!CAUTION]
> Uploads require a token for a reason! Ensure only trusted individuals can upload files.
>
> This is the tradeoff between freedom and XSS attacks - freedom was chosen during development.

## Requirements

- Python 3.14+
- everything in `requirements.txt`

## Setup & Deployment

```bash
git clone https://github.com/xRedCrystalx/simple-cdn.git
cd simple-cdn

python3 -m venv .venv
source .venv/bin/activate

pip install -U -r requirements.txt
cp .env.example .env
# edit BRAND_NAME, DOMAIN, SCRYPT_SECRET, etc.

# IMPORTANT TO RUN BEFORE STARTING THE SERVICE
python3 setup.py

sudo cp simple-cdn.service /etc/systemd/system/
# edit User, Group, WorkingDirectory

sudo systemctl daemon-reload
sudo systemctl enable --now simple-cdn
```

`setup.py` creates the database, upload directories, and the first admin token.
Save that token - it is only printed once.

All configuration lives in `.env` (see `.env.example`). Notable variables:

- `HOST` / `PORT` - bind address for the service
- `DOMAIN` - public domain used when generating links
- `PUBLIC_DIR` - where uploaded/managed files are stored on disk
- `MAX_UPLOAD_SIZE` - upload limits
- `SCRYPT_SECRET` - secret used to hash file passwords
- `DEBUG` - should be `0` in production

This project assumes you already have a reverse proxy (nginx/caddy/traefik) set up for SSL/TLS certificates.

## Managing

```bash
python3 create_user.py
```

Creates a new user record. Tokens are issued separately via the admin API/panel.

```bash
python3 rebuild_db.py
```

Rebuilds the endpoints database (uploads and images) from what's saved on the file system.

> [!WARNING]
> YOU MIGHT LOSE FILE NAMES AND PASSWORD HASHES, USE AT YOUR OWN RISK

