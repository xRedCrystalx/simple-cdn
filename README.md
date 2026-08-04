# simple-cdn

A lightweight self-hosted CDN/file host built with FastAPI. Serves uploaded files,
supports token-based auth, simple programatic API, and includes a minimal admin panel and upload UI.

## Requirements

- Python 3.14+
- everything in `requirements.txt`

## Setup

```bash
git clone https://github.com/xRedCrystalx/simple-cdn.git
cd simple-cdn

python -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# edit .env: set BRAND_NAME, DOMAIN, SCRYPT_SECRET, etc.

# IMPORTANT TO RUN BEFORE STARTING THE SERVICE
.venv/bin/python setup.py
```

`setup.py` creates the database, upload directories, and the first admin token.
Save that token - it is only printed once.


## Configuration

All configuration lives in `.env` (see `.env.example`). Notable variables:

- `HOST` / `PORT` - bind address for the service
- `DOMAIN` - public domain used when generating links
- `PUBLIC_DIR` - where uploaded/managed files are stored on disk
- `MAX_UPLOAD_SIZE` - upload limits
- `SCRYPT_SECRET` - secret used to hash file passwords
- `DEBUG` - should be `0` in production


## Production deployment

1. Deploy the project to a fixed path (e.g. `/opt/simple-cdn`), set up `.venv`, `.env`, and run `setup.py` there.
2. Set `DEBUG=0` and `HOST=0.0.0.0` (or the appropriate bind address) in `.env`.
3. Put a reverse proxy (nginx/caddy/apache2/traefik) in front for TLS/SSL.
4. Run it as a systemd service using the included unit file:

```bash
sudo cp simple-cdn.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now simple-cdn
```

Adjust `User`, `Group`, and `WorkingDirectory` in `simple-cdn.service` to match
your deployment path first.

## Managing

```bash
.venv/bin/python create_user.py
```

Creates a new user record. Tokens are issued separately via the admin API/panel.

```bash
.venv/bin/python rebuild_db.py
```

Rebuilds endpoints database (uploads and images) that are saved in the file system.

> [!WARNING] 
> YOU MIGHT LOSE FILE NAMES AND PASSWORD HASHES, USE AT YOUR OWN RISK

## License

MIT
