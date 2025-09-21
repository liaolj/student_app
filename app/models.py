from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional


class Role(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    PRINCIPAL = "principal"


@dataclass
class Account:
    username: str
    role: Role
    bind_id: Optional[str]
    password_hash: str
    locked_until: Optional[datetime] = None
    failed_attempts: int = 0
    force_password_change: bool = True


@dataclass
class Student:
    student_no: str
    name: str
    class_name: str
    status: str
    has_unread_published_grades: bool = False


@dataclass
class Subject:
    subject_code: str
    subject_name: str


@dataclass
class Teacher:
    teacher_id: str
    name: str
    subjects: List[str]
    classes: List[str]


class ExamStatus(str, Enum):
    PUBLISHED = "published"
    DRAFT = "draft"


@dataclass
class Exam:
    exam_id: str
    exam_name: str
    term: str
    exam_date: date
    classes: List[str]
    status: ExamStatus


@dataclass
class Grade:
    exam_id: str
    subject_code: str
    student_no: str
    score: float
    created_by: str
    created_at: datetime
    updated_at: datetime
    published: bool = False


class AuditAction(str, Enum):
    GRADE_CREATED = "grade_created"
    GRADE_UPDATED = "grade_updated"
    GRADE_PUBLISHED = "grade_published"
    EXPORT = "export"
    PASSWORD_RESET = "password_reset"


@dataclass
class AuditLogEntry:
    timestamp: datetime
    actor: str
    action: AuditAction
    details: dict = field(default_factory=dict)


@dataclass
class LoginResult:
    token: str
    role: Role
    must_change_password: bool


@dataclass
class AggregatedStats:
    highest: float
    lowest: float
    average: float
    pass_rate: float


@dataclass
class StudentGradeView:
    exam_id: str
    exam_name: str
    exam_date: date
    subject_code: str
    subject_name: str
    score: float
    class_average: float


@dataclass
class StudentGradeResponse:
    has_unread: bool
    grades: List[StudentGradeView]


@dataclass
class TeacherGradeView:
    student_no: str
    student_name: str
    class_name: str
    subject_code: str
    score: float
    published: bool


@dataclass
class OverviewEntry:
    exam_id: str
    exam_name: str
    subject_code: str
    subject_name: str
    stats: AggregatedStats


@dataclass
class GradeDetailEntry:
    exam_id: str
    exam_name: str
    subject_code: str
    subject_name: str
    student_no: str
    student_name: str
    class_name: str
    score: float
    published: bool
