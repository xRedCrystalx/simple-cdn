"""
First run initialisation: creates the directories, the database schema and the first admin token.
"""

import asqlite, asyncio, secrets, dotenv, os
from pathlib import Path

ENV_LOADED: bool = dotenv.load_dotenv()

if not ENV_LOADED:
    raise RuntimeError("Failed to load .env file. Please ensure you are in the working directory of the project and that a .env file exists.")


async def main() -> None:
    Path(os.getcwd() + "/logs").mkdir(exist_ok=True)    # I'm aware that os.getcwd() is not required.
    Path(os.getenv("PUBLIC_DIR")).mkdir(exist_ok=True)

    async with asqlite.connect("main.db") as conn:

        _ = await conn.execute((
            "CREATE TABLE users ( "
            "   id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "   username VARCHAR(24) NOT NULL UNIQUE "
            ");"
        ))

        _ = await conn.execute((
            "CREATE TABLE auth_tokens ( "
            "   token VARCHAR(64) PRIMARY KEY, "
            "   uid INTEGER NOT NULL, "
            "   type VARCHAR(16) NOT NULL, "
            ""
            "   FOREIGN KEY (uid) REFERENCES users(id) ON DELETE CASCADE "
            ");"
        ))


        _ = await conn.execute((
            "CREATE TABLE endpoints ( "
            "   endpoint VARCHAR(128) PRIMARY KEY, "
            "   type VARCHAR(16) NOT NULL, "
            "   name VARCHAR(64), "
            "   lifetime INTEGER, "
            "   protected_id INTEGER, "
            ""
            "   FOREIGN KEY (protected_id) REFERENCES protected(id) ON DELETE SET NULL "
            ");"
        ))

        _ = await conn.execute((
            "CREATE TABLE protected ( "
            "   id INTEGER PRIMARY KEY, "
            "   hash VARCHAR(64) NOT NULL "
            ");"
        ))


        ADMIN_SECRET: str = secrets.token_urlsafe(int(os.getenv("TOKEN_SIZE")))

        _ = await conn.execute(
            "INSERT INTO users (id, username) VALUES (?, ?)", (1, "admin")
        )
        _ = await conn.execute(
            "INSERT INTO auth_tokens (uid, token, type) VALUES (?, ?, ?)", (1, ADMIN_SECRET, "admin")
        )

        await conn.commit()

        print(f"Database initialized successfully. Your admin token: {ADMIN_SECRET}")
        print("Please store this token securely. It will NOT be shown again.")

if __name__ == "__main__":
    asyncio.run(main())
