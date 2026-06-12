import asyncio
import asyncpg
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:4000/api"
DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_DNI = os.getenv("ADMIN_DNI", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
OFFERING_ID = int(os.getenv("OFFERING_ID", "1"))
DEFAULT_PASSWORD = "123456"

# Mismos teléfonos usados en el script que generó los estudiantes de prueba
PHONES = ["969728039", "970253943", "984618002", "949850422", "950132313"]


async def obtener_estudiantes_prueba():
    """Consulta la BD y devuelve los DNIs de los estudiantes generados de prueba"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            "SELECT dni, first_name, last_name FROM students WHERE phone = ANY($1::text[])",
            PHONES
        )
        return [(r["dni"], f"{r['first_name']} {r['last_name']}") for r in rows]
    finally:
        await conn.close()


def run_flow_for_student(client, dni, nombre, admin_headers):
    print(f"\n{'='*60}")
    print(f"=== ESTUDIANTE {dni} ({nombre}) ===")
    print(f"{'='*60}\n")

    # --- LOGIN ---
    print("— LOGIN (Estudiante) —")
    r = client.post(f"{BASE_URL}/auth/login", json={"dni": dni, "password": DEFAULT_PASSWORD})
    print(f"→ POST /auth/login\n← {r.status_code}")
    if r.status_code != 200:
        print(f"✗ Login falló para {dni}: {r.text}\n")
        return None
    student_token = r.json()["token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}
    print("✓ Login estudiante devuelve token\n")

    # --- CREAR MATRÍCULA ---
    print("— Crear matrícula —")
    body = {"items": [{"type": "course", "id": OFFERING_ID}]}
    r = client.post(f"{BASE_URL}/enrollments", json=body, headers=student_headers)
    print(f"→ POST /enrollments\nbody: {body}\n← {r.status_code}")
    print(r.json())

    if r.status_code != 201:
        print(f"✗ No se pudo matricular a {dni} (puede ya estar matriculado)\n")
        return None

    created = r.json()["created"][0]
    enrollment_id = created["enrollmentId"]
    installment_id = created["installment_id"]
    print(f"✓ Matrícula creada (enrollment_id={enrollment_id}, installment_id={installment_id})\n")

    # --- SUBIR VOUCHER ---
    print("— Subir voucher —")
    files = {"voucher": ("voucher.jpg", b"fakeimagebytes", "image/jpeg")}
    r = client.post(f"{BASE_URL}/payments/upload-voucher/{installment_id}", files=files, headers=student_headers)
    print(f"→ POST /payments/upload-voucher/{installment_id}\n← {r.status_code}")
    print(r.json())

    # --- APROBAR PAGO (admin) ---
    print("— Aprobar pago (admin) —")
    r = client.post(f"{BASE_URL}/payments/approve", json={"installment_id": installment_id}, headers=admin_headers)
    print(f"→ POST /payments/approve\n← {r.status_code}")
    print(r.json())

    return enrollment_id


def main():
    print("=== PRUEBAS DE INTEGRACIÓN MASIVAS · Matrículas y Pagos ===")
    print(f"API: {BASE_URL}\n")

    # 1. Obtener estudiantes de prueba desde la BD
    print("— Obteniendo estudiantes de prueba desde la BD —")
    estudiantes = asyncio.run(obtener_estudiantes_prueba())
    print(f"✓ Encontrados {len(estudiantes)} estudiantes de prueba\n")

    if not estudiantes:
        print("✗ No se encontraron estudiantes de prueba. Verifica los teléfonos en PHONES.")
        return

    client = httpx.Client(timeout=30)

    # 2. Login admin
    print("— LOGIN (Admin) —")
    r = client.post(f"{BASE_URL}/auth/login", json={"dni": ADMIN_DNI, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Login admin falló: {r.text}"
    admin_token = r.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("✓ Login admin OK\n")

    # 3. Ejecutar flujo completo para cada estudiante
    enrollment_ids = []
    exitosos = 0
    fallidos = 0

    for dni, nombre in estudiantes:
        eid = run_flow_for_student(client, dni, nombre, admin_headers)
        if eid:
            enrollment_ids.append(eid)
            exitosos += 1
        else:
            fallidos += 1

    # 4. Limpieza
    print(f"\n{'='*60}")
    print("— LIMPIEZA: borrando matrículas de prueba —")
    for eid in enrollment_ids:
        r = client.delete(f"{BASE_URL}/enrollments/{eid}", headers=admin_headers)
        print(f"→ DELETE /enrollments/{eid} ← {r.status_code}")

    # 5. Resumen
    print(f"\n{'='*60}")
    print("=== RESUMEN ===")
    print(f"Total estudiantes: {len(estudiantes)}")
    print(f"Matriculados y aprobados exitosamente: {exitosos}")
    print(f"Fallidos (ya matriculados u otro error): {fallidos}")
    print("=== FIN DE PRUEBAS ===")


if __name__ == "__main__":
    main()