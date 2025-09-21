from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import auth, data, security, services
from app.exceptions import AppError
from app.models import AuditAction, Exam, ExamStatus, Role


@pytest.fixture()
def fresh_app_state():
    importlib.reload(security)
    importlib.reload(data)
    importlib.reload(services)
    importlib.reload(auth)


def _login(username: str, password: str = "Pass@123"):
    return auth.authenticate(username, password)


def _account(token: str):
    return auth.get_account(token)


def test_student_login_and_access_control(fresh_app_state):
    login = _login("s_s001")
    assert login.role == Role.STUDENT
    assert login.must_change_password is True

    account = _account(login.token)
    grades = services.list_student_grades(account)
    assert grades.has_unread is False
    assert {item.subject_code for item in grades.grades} == {"CHN", "MTH", "ENG"}

    with pytest.raises(AppError) as exc:
        services.teacher_list_grades(account)
    assert exc.value.status_code == 403


def test_teacher_import_publish_and_student_notification(fresh_app_state):
    data.exams["EX2025N"] = Exam(
        exam_id="EX2025N",
        exam_name="2025-上学期-期末考试",
        term="2025-上",
        exam_date=date(2025, 7, 10),
        classes=["Class 1", "Class 2"],
        status=ExamStatus.DRAFT,
    )

    teacher_login = _login("t_mth")
    teacher_account = _account(teacher_login.token)

    csv_payload = "exam_id,subject_code,student_no,score\nEX2025N,MTH,S001,96"
    result = services.teacher_import_grades(teacher_account, csv_payload)
    assert result["processed"] == 1
    assert result["errors"] == []

    published = services.publish_grades(teacher_account, "EX2025N", "MTH")
    assert published >= 1

    student_login = _login("s_s001")
    student_account = _account(student_login.token)

    first_view = services.list_student_grades(student_account)
    assert first_view.has_unread is True
    assert any(item.exam_id == "EX2025N" for item in first_view.grades)

    second_view = services.list_student_grades(student_account)
    assert second_view.has_unread is False


def test_principal_reset_password_and_overview(fresh_app_state):
    principal_login = _login("principal")
    principal_account = _account(principal_login.token)

    new_password = auth.reset_password("s_s002")
    services.mark_password_reset(principal_account.username, "s_s002")
    assert len(new_password) >= 8

    student_login = _login("s_s002", new_password)
    assert student_login.must_change_password is True

    overview = services.principal_overview()
    assert any(entry.subject_code == "MTH" for entry in overview)


def test_login_lockout_policy(fresh_app_state):
    for _ in range(5):
        with pytest.raises(AppError) as exc:
            _login("s_s003", "wrong")
        assert exc.value.status_code == 401
    with pytest.raises(AppError) as locked_exc:
        _login("s_s003", "Pass@123")
    assert locked_exc.value.status_code == 423


def test_teacher_exports_are_logged(fresh_app_state):
    teacher_login = _login("t_eng")
    teacher_account = _account(teacher_login.token)

    csv_content = services.teacher_export_grades(teacher_account)
    assert "student_no" in csv_content

    logs = services.list_audit_logs(teacher_account)
    assert any(log.action == AuditAction.EXPORT for log in logs)
