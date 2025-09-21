from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Tuple

from .models import (
    Account,
    AuditLogEntry,
    Exam,
    ExamStatus,
    Grade,
    Role,
    Student,
    Subject,
    Teacher,
)
from .security import hash_password


def _now() -> datetime:
    return datetime.now(timezone.utc)


students: Dict[str, Student] = {
    "S001": Student(student_no="S001", name="张三", class_name="Class 1", status="在读"),
    "S002": Student(student_no="S002", name="李四", class_name="Class 1", status="在读"),
    "S003": Student(student_no="S003", name="王五", class_name="Class 1", status="在读"),
    "S004": Student(student_no="S004", name="赵六", class_name="Class 2", status="在读"),
    "S005": Student(student_no="S005", name="孙七", class_name="Class 2", status="在读"),
    "S006": Student(student_no="S006", name="周八", class_name="Class 2", status="在读"),
}

subjects: Dict[str, Subject] = {
    "CHN": Subject(subject_code="CHN", subject_name="语文"),
    "MTH": Subject(subject_code="MTH", subject_name="数学"),
    "ENG": Subject(subject_code="ENG", subject_name="英语"),
}

teachers: Dict[str, Teacher] = {
    "T100": Teacher(teacher_id="T100", name="陈老师", subjects=["CHN"], classes=["Class 1", "Class 2"]),
    "T200": Teacher(teacher_id="T200", name="刘老师", subjects=["MTH"], classes=["Class 1", "Class 2"]),
    "T300": Teacher(teacher_id="T300", name="吴老师", subjects=["ENG"], classes=["Class 1", "Class 2"]),
}

exams: Dict[str, Exam] = {
    "EX2025M": Exam(
        exam_id="EX2025M",
        exam_name="2025-上学期-期中考试",
        term="2025-上",
        exam_date=date(2025, 5, 20),
        classes=["Class 1", "Class 2"],
        status=ExamStatus.PUBLISHED,
    )
}

_initial_password_hash = hash_password("Pass@123")
accounts: Dict[str, Account] = {
    "principal": Account(username="principal", role=Role.PRINCIPAL, bind_id=None, password_hash=_initial_password_hash),
    "t_chn": Account(username="t_chn", role=Role.TEACHER, bind_id="T100", password_hash=_initial_password_hash),
    "t_mth": Account(username="t_mth", role=Role.TEACHER, bind_id="T200", password_hash=_initial_password_hash),
    "t_eng": Account(username="t_eng", role=Role.TEACHER, bind_id="T300", password_hash=_initial_password_hash),
    "s_s001": Account(username="s_s001", role=Role.STUDENT, bind_id="S001", password_hash=_initial_password_hash),
    "s_s002": Account(username="s_s002", role=Role.STUDENT, bind_id="S002", password_hash=_initial_password_hash),
    "s_s003": Account(username="s_s003", role=Role.STUDENT, bind_id="S003", password_hash=_initial_password_hash),
    "s_s004": Account(username="s_s004", role=Role.STUDENT, bind_id="S004", password_hash=_initial_password_hash),
    "s_s005": Account(username="s_s005", role=Role.STUDENT, bind_id="S005", password_hash=_initial_password_hash),
    "s_s006": Account(username="s_s006", role=Role.STUDENT, bind_id="S006", password_hash=_initial_password_hash),
}

_grade_seed = {
    ("EX2025M", "CHN", "S001"): 88,
    ("EX2025M", "CHN", "S002"): 76,
    ("EX2025M", "CHN", "S003"): 92,
    ("EX2025M", "CHN", "S004"): 81,
    ("EX2025M", "CHN", "S005"): 67,
    ("EX2025M", "CHN", "S006"): 85,
    ("EX2025M", "MTH", "S001"): 95,
    ("EX2025M", "MTH", "S002"): 82,
    ("EX2025M", "MTH", "S003"): 78,
    ("EX2025M", "MTH", "S004"): 88,
    ("EX2025M", "MTH", "S005"): 73,
    ("EX2025M", "MTH", "S006"): 90,
    ("EX2025M", "ENG", "S001"): 84,
    ("EX2025M", "ENG", "S002"): 79,
    ("EX2025M", "ENG", "S003"): 91,
    ("EX2025M", "ENG", "S004"): 86,
    ("EX2025M", "ENG", "S005"): 72,
    ("EX2025M", "ENG", "S006"): 88,
}

grades: Dict[Tuple[str, str, str], Grade] = {}
for (exam_id, subject_code, student_no), score in _grade_seed.items():
    teacher_id = next(
        teacher.teacher_id
        for teacher in teachers.values()
        if subject_code in teacher.subjects
    )
    timestamp = _now()
    grades[(exam_id, subject_code, student_no)] = Grade(
        exam_id=exam_id,
        subject_code=subject_code,
        student_no=student_no,
        score=score,
        created_by=teacher_id,
        created_at=timestamp,
        updated_at=timestamp,
        published=True,
    )

audit_logs: List[AuditLogEntry] = []
