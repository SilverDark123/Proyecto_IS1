# select_students_by_phone.py

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

PHONES = ("969728039", "952873813", "956399615")

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    print("✅ Conectado a la base de datos")

    try:
        students = await conn.fetch(
            """SELECT id, dni, first_name, last_name, phone, parent_name, parent_phone
               FROM students
               WHERE phone = ANY($1::text[])""",
            list(PHONES)
        )

        print(f"\n📋 Estudiantes encontrados: {len(students)}\n")
        for s in students:
            print(f"  ID: {s['id']} | {s['first_name']} {s['last_name']} | DNI: {s['dni']} | Tel: {s['phone']}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()
        print("\n🔌 Conexión cerrada")

if __name__ == "__main__":
    asyncio.run(main())