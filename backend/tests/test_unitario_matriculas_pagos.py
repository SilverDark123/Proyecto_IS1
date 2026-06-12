import sys
import os
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure backend package is importable when running tests from workspace root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from controllers import enrollmentController as ec
from controllers import paymentController as pc


class SimpleItem:
    def __init__(self, type_, id_):
        self.type = type_
        self.id = id_


class DummyData:
    def __init__(self, items):
        self.items = items


class FakeDB:
    """A tiny fake async DB that inspects SQL to return sensible values for tests."""
    def __init__(self):
        self.execute = AsyncMock()
        self._calls = []

    async def fetchrow(self, sql, *params):
        s = sql.lower()
        # Simulate 'already enrolled' check
        if "where e.student_id = $1 and e.course_offering_id = $2" in s:
            return None
        if "insert into enrollments" in s:
            return {"id": 101}
        if "insert into payment_plans" in s:
            return {"id": 201}
        if "insert into installments" in s:
            return {"id": 301}
        if "select i.*, pp.enrollment_id" in s and "where i.id = $1" in s:
            # default for upload_voucher tests will override via direct assignment
            return None
        return None

    async def fetch(self, sql, *params):
        return []


@pytest.mark.asyncio
async def test_create_enrollment_duplicate_course_returns_error():
    # Arrange: DB returns an existing enrollment for the duplicate check
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"course_name": "Matemáticas", "group_label": None})

    data = DummyData([SimpleItem("course", 123)])

    # Act
    result = await ec.create_enrollment(1, data, db)

    # Assert
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.asyncio
async def test_create_enrollment_success_creates_enrollment_and_payments():
    db = FakeDB()

    data = DummyData([SimpleItem("package", 10)])

    result = await ec.create_enrollment(42, data, db)

    assert isinstance(result, dict)
    assert result.get("message") == "Matrículas creadas correctamente"
    assert "created" in result and isinstance(result["created"], list)
    assert result["created"][0]["enrollmentId"] == 101


@pytest.mark.asyncio
async def test_upload_voucher_no_installment_returns_error():
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)

    fake_file = AsyncMock()
    fake_file.read = AsyncMock(return_value=b"abc")

    res = await pc.upload_voucher(999, fake_file, 1, db)

    assert isinstance(res, dict)
    assert "error" in res


@pytest.mark.asyncio
async def test_upload_voucher_success_updates_installment_and_returns_url():
    db = MagicMock()
    # Simulate installment existing
    db.fetchrow = AsyncMock(return_value={"id": 10, "payment_plan_id": 20, "enrollment_id": 30, "student_id": 1})
    db.execute = AsyncMock()

    fake_file = AsyncMock()
    fake_file.read = AsyncMock(return_value=b"binarydata")

    # Patch upload_to_cloudinary to return a predictable URL
    with patch("config.cloudinary.upload_to_cloudinary", new=AsyncMock(return_value={"url": "http://cdn/voucher.jpg"})):
        res = await pc.upload_voucher(10, fake_file, 1, db)

    assert res.get("message") == "Voucher subido con éxito"
    assert res.get("voucherUrl") == "http://cdn/voucher.jpg"
    # Ensure DB execute updated the installment
    db.execute.assert_called()


@pytest.mark.asyncio
async def test_approve_installment_marks_paid_and_accepts_enrollment_when_all_paid():
    db = MagicMock()
    # First execute - update paid
    db.execute = AsyncMock()

    # fetchrow to return payment_plan/enrollment mapping when queried
    async def fetchrow_side(sql, *params):
        s = sql.lower()
        if "select pp.id as payment_plan_id" in s:
            return {"payment_plan_id": 5, "enrollment_id": 6}
        if "select count(*) as cnt" in s:
            return {"cnt": 0}
        if "select enrollment_type, student_id" in s:
            return {"enrollment_type": "course", "student_id": 7, "course_offering_id": None, "package_offering_id": None}
        return None

    db.fetchrow = AsyncMock(side_effect=fetchrow_side)
    db.fetch = AsyncMock(return_value=[])

    res = await pc.approve_installment(77, db)

    assert res.get("message") == "Installment aprobado"


@pytest.mark.asyncio
async def test_get_student_enrollments_returns_list_with_installments():
    db = MagicMock()

    async def fetch_side(sql, *params):
        s = sql.lower()
        if "from enrollments e" in s and "left join" in s:
            return [{"id": 1, "payment_plan_id": 50, "status": "pendiente"}]
        if "from installments" in s:
            return [{"id": 100, "installment_number": 1, "amount": 700, "status": "pending"}]
        return []

    db.fetch = AsyncMock(side_effect=fetch_side)

    result = await ec.get_student_enrollments(1, db)

    assert isinstance(result, list)
    assert result[0]["installments"][0]["id"] == 100


@pytest.mark.asyncio
async def test_reject_installment_updates_status_and_enrollment():
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "id": 10, "payment_plan_id": 20, "enrollment_id": 30, "due_date": None
    })
    db.execute = AsyncMock()

    res = await pc.reject_installment(10, "Voucher ilegible", db)

    assert res.get("message") == "Pago rechazado y matrícula actualizada"
    db.execute.assert_called()


@pytest.mark.asyncio
async def test_get_pending_payments_returns_list():
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {"id": 1, "enrollment_id": 5, "student_id": 10, "first_name": "Juan",
         "last_name": "Perez", "dni": "12345678"}
    ])

    res = await pc.get_pending_payments(db)

    assert isinstance(res, list)
    assert res[0]["dni"] == "12345678"


@pytest.mark.asyncio
async def test_get_all_installments_filters_by_status():
    db = MagicMock()
    db.execute = AsyncMock()
    db.fetch = AsyncMock(return_value=[
        {"id": 1, "status": "paid", "enrollment_status": "aceptado"}
    ])

    res = await pc.get_all_installments("paid", db)

    assert isinstance(res, list)
    assert res[0]["status_ui"] == "paid"