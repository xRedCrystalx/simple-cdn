"""
Simple helper script to create a new user in the database.
"""

import asqlite, asyncio

async def main() -> None:
    account_name: str = input("Enter a username for the new account: ").strip()

    async with asqlite.connect("main.db") as conn:
        try:
            _ = await conn.execute("INSERT INTO users (username) VALUES (?)", (account_name,))

        except Exception as e:
            await conn.rollback()
            print(f"Failed to create user '{account_name}': {e}")

        await conn.commit()

        row: asqlite.Cursor = await conn.execute("SELECT id FROM users WHERE username = ?", (account_name,))
        result = await row.fetchone()

        print(f"Created user '{account_name}' with id {result["id"]}.")


if __name__ == "__main__":
    asyncio.run(main())