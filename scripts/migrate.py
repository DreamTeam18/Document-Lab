import asyncio
from pathlib import Path

import psycopg

from app.config import settings


async def main():
    dsn = settings().database_url.get_secret_value()
    if not dsn:
        raise SystemExit("Set DATABASE_URL before applying migrations")
    async with await psycopg.AsyncConnection.connect(dsn, prepare_threshold=None) as conn:
        schema = (Path(__file__).parents[1] / "migrations/001_initial.sql").read_text()
        await conn.execute(schema)
    print("Schema is ready")


if __name__ == "__main__":
    asyncio.run(main())
