import sys
import asyncio
import os
import pathlib

# Ensure repo root/backend is on sys.path so imports like `config` work
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.database import DATABASE_URL
import asyncpg

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT id, course_id, group_label FROM course_offerings WHERE visible = true LIMIT 1")
    await conn.close()
    if row:
        print(f"{row['id']}|course|{row['course_id']}|{row.get('group_label')}")
    else:
        print("NO_OFFERING_FOUND")

if __name__ == '__main__':
    asyncio.run(main())
