from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from statistics import mean
from typing import Iterable, List, Optional, Tuple

from . import data
from .exceptions import AppError
from .models import (
    Account,
    AggregatedStats,
    AuditAction,
    AuditLogEntry,
    Exam,
    Grade,
    GradeDetailEntry,
    OverviewEntry,
    Role,
    StudentGradeResponse,
    StudentGradeView,
    TeacherGradeView,
)

PASSING_SCORE = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_exam(exam_id: str) -> Exam:
    exam = data.exams.get(exam_id)
    if not exam:
        raise AppError(status_code=404, detail="考试不存在")
    return exam


def _require_subject(subject_code: str) -> None:
    if subject_code not in data.subjects:
        raise AppError(status_code=404, detail="科目不存在")


def _require_student(student_no: str) -> None:
    if student_no not in data.students:
        raise AppError(status_code=404, detail="学生不存在")


def _teacher_for_account(account: Account) -> Tuple[str, List[str], List[str]]:
    if account.role != Role.TEACHER:
        raise AppError(status_code=403, detail="权限不足")
    teacher = data.teachers.get(account.bind_id or "")
    if not teacher:
        raise AppError(status_code=403, detail="教师未绑定")
    return teacher.teacher_id, teacher.subjects, teacher.classes


def _grade_key(exam_id: str, subject_code: str, student_no: str) -> Tuple[str, str, str]:
    return (exam_id, subject_code, student_no)


def _record_log(action: AuditAction, actor: str, **details: object) -> None:
    data.audit_logs.append(
        AuditLogEntry(timestamp=_now(), actor=actor, action=action, details=details)
    )


def _grades_for_student(student_no: str) -> List[Grade]:
    return [grade for grade in data.grades.values() if grade.student_no == student_no]


def _visible_grades_for_teacher(account: Account) -> List[Grade]:
    _teacher_id, subjects, classes = _teacher_for_account(account)
    student_ids = {
        s.student_no
        for s in data.students.values()
        if s.class_name in classes
    }
    return [
        grade
        for grade in data.grades.values()
        if grade.subject_code in subjects and grade.student_no in student_ids
    ]


def list_student_grades(account: Account, term: Optional[str] = None, exam_id: Optional[str] = None) -> StudentGradeResponse:
    if account.role != Role.STUDENT:
        raise AppError(status_code=403, detail="权限不足")

    student = data.students.get(account.bind_id or "")
    if not student:
        raise AppError(status_code=404, detail="学生不存在")

    relevant_grades = [grade for grade in _grades_for_student(student.student_no) if grade.published]
    if term:
        relevant_grades = [grade for grade in relevant_grades if data.exams[grade.exam_id].term == term]
    if exam_id:
        relevant_grades = [grade for grade in relevant_grades if grade.exam_id == exam_id]

    views: List[StudentGradeView] = []
    for grade in relevant_grades:
        exam = data.exams.get(grade.exam_id)
        if not exam:
            continue
        subject = data.subjects.get(grade.subject_code)
        class_scores = [
            g.score
            for g in data.grades.values()
            if g.exam_id == grade.exam_id
            and g.subject_code == grade.subject_code
            and data.students[g.student_no].class_name == student.class_name
        ]
        class_average = round(mean(class_scores), 2) if class_scores else grade.score
        views.append(
            StudentGradeView(
                exam_id=grade.exam_id,
                exam_name=exam.exam_name,
                exam_date=exam.exam_date,
                subject_code=grade.subject_code,
                subject_name=subject.subject_name if subject else grade.subject_code,
                score=grade.score,
                class_average=class_average,
            )
        )

    response = StudentGradeResponse(has_unread=student.has_unread_published_grades, grades=sorted(views, key=lambda g: (g.exam_date, g.subject_code)))
    student.has_unread_published_grades = False
    return response


def teacher_update_grade(account: Account, exam_id: str, subject_code: str, student_no: str, score: float) -> Grade:
    teacher_id, subjects, classes = _teacher_for_account(account)
    _require_exam(exam_id)
    _require_subject(subject_code)
    _require_student(student_no)

    if subject_code not in subjects:
        raise AppError(status_code=403, detail="无权操作该科目")

    student = data.students[student_no]
    if student.class_name not in classes:
        raise AppError(status_code=403, detail="无权操作该班级")

    if score < 0 or score > 100:
        raise AppError(status_code=400, detail="分数范围错误")

    key = _grade_key(exam_id, subject_code, student_no)
    timestamp = _now()
    previous = data.grades.get(key)
    rounded_score = round(score, 1)
    if previous:
        old_score = previous.score
        previous.score = rounded_score
        previous.updated_at = timestamp
        previous.created_by = teacher_id
        _record_log(
            AuditAction.GRADE_UPDATED,
            teacher_id,
            exam_id=exam_id,
            subject_code=subject_code,
            student_no=student_no,
            old_score=old_score,
            new_score=previous.score,
        )
        return previous

    grade = Grade(
        exam_id=exam_id,
        subject_code=subject_code,
        student_no=student_no,
        score=rounded_score,
        created_by=teacher_id,
        created_at=timestamp,
        updated_at=timestamp,
        published=False,
    )
    data.grades[key] = grade
    _record_log(
        AuditAction.GRADE_CREATED,
        teacher_id,
        exam_id=exam_id,
        subject_code=subject_code,
        student_no=student_no,
        score=grade.score,
    )
    return grade


def teacher_import_grades(account: Account, csv_content: str) -> dict:
    reader = csv.DictReader(io.StringIO(csv_content))
    errors: List[str] = []
    processed = 0
    for idx, row in enumerate(reader, start=2):
        try:
            exam_id = row["exam_id"].strip()
            subject_code = row["subject_code"].strip()
            student_no = row["student_no"].strip()
            score = float(row["score"].strip())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"第 {idx} 行格式错误: {exc}")
            continue

        try:
            teacher_update_grade(account, exam_id, subject_code, student_no, score)
        except AppError as exc:
            errors.append(f"第 {idx} 行导入失败: {exc.detail}")
            continue
        processed += 1

    return {"processed": processed, "errors": errors}


def teacher_export_grades(account: Account, exam_id: Optional[str] = None, class_name: Optional[str] = None) -> str:
    grades = _visible_grades_for_teacher(account)
    if exam_id:
        grades = [grade for grade in grades if grade.exam_id == exam_id]
    if class_name:
        grades = [grade for grade in grades if data.students[grade.student_no].class_name == class_name]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["exam", "subject", "student_no", "student_name", "class", "score"])
    for grade in grades:
        exam = data.exams.get(grade.exam_id)
        subject = data.subjects.get(grade.subject_code)
        student = data.students.get(grade.student_no)
        writer.writerow(
            [
                exam.exam_name if exam else grade.exam_id,
                subject.subject_name if subject else grade.subject_code,
                grade.student_no,
                student.name if student else grade.student_no,
                student.class_name if student else "",
                grade.score,
            ]
        )

    _record_log(AuditAction.EXPORT, account.bind_id or account.username, scope="teacher", exam_id=exam_id, class_name=class_name)
    return output.getvalue()


def teacher_list_grades(
    account: Account,
    exam_id: Optional[str] = None,
    class_name: Optional[str] = None,
    sort_by: str = "student_no",
) -> List[TeacherGradeView]:
    grades = _visible_grades_for_teacher(account)
    if exam_id:
        grades = [grade for grade in grades if grade.exam_id == exam_id]
    if class_name:
        grades = [grade for grade in grades if data.students[grade.student_no].class_name == class_name]

    views = [
        TeacherGradeView(
            student_no=grade.student_no,
            student_name=data.students[grade.student_no].name,
            class_name=data.students[grade.student_no].class_name,
            subject_code=grade.subject_code,
            score=grade.score,
            published=grade.published,
        )
        for grade in grades
    ]

    reverse = False
    if sort_by == "score_desc":
        key = lambda g: g.score
        reverse = True
    elif sort_by == "score_asc":
        key = lambda g: g.score
    else:
        key = lambda g: (g.student_no, g.subject_code)
    return sorted(views, key=key, reverse=reverse)


def publish_grades(account: Account, exam_id: str, subject_code: str) -> int:
    teacher_id, subjects, classes = _teacher_for_account(account)
    if subject_code not in subjects:
        raise AppError(status_code=403, detail="无权发布该科目")
    _require_exam(exam_id)

    updated = 0
    for grade in data.grades.values():
        if grade.exam_id == exam_id and grade.subject_code == subject_code:
            student = data.students.get(grade.student_no)
            if student and student.class_name in classes:
                if not grade.published:
                    student.has_unread_published_grades = True
                grade.published = True
                updated += 1
    if updated == 0:
        raise AppError(status_code=404, detail="未找到成绩记录")
    _record_log(AuditAction.GRADE_PUBLISHED, teacher_id, exam_id=exam_id, subject_code=subject_code, count=updated)
    return updated


def _aggregate_scores(scores: Iterable[float]) -> Optional[AggregatedStats]:
    scores = list(scores)
    if not scores:
        return None
    highest = max(scores)
    lowest = min(scores)
    avg = round(mean(scores), 2)
    passing = sum(1 for score in scores if score >= PASSING_SCORE)
    pass_rate = round((passing / len(scores)) * 100, 2)
    return AggregatedStats(highest=highest, lowest=lowest, average=avg, pass_rate=pass_rate)


def principal_overview(exam_id: Optional[str] = None) -> List[OverviewEntry]:
    entries: List[OverviewEntry] = []
    exams = [data.exams[exam_id]] if exam_id else data.exams.values()
    for exam in exams:
        for subject in data.subjects.values():
            scores = [
                grade.score
                for grade in data.grades.values()
                if grade.exam_id == exam.exam_id and grade.subject_code == subject.subject_code
            ]
            stats = _aggregate_scores(scores)
            if stats:
                entries.append(
                    OverviewEntry(
                        exam_id=exam.exam_id,
                        exam_name=exam.exam_name,
                        subject_code=subject.subject_code,
                        subject_name=subject.subject_name,
                        stats=stats,
                    )
                )
    return entries


def principal_grade_details(
    exam_id: Optional[str] = None,
    class_name: Optional[str] = None,
    subject_code: Optional[str] = None,
) -> List[GradeDetailEntry]:
    entries: List[GradeDetailEntry] = []
    for grade in data.grades.values():
        if exam_id and grade.exam_id != exam_id:
            continue
        if subject_code and grade.subject_code != subject_code:
            continue
        student = data.students.get(grade.student_no)
        if not student:
            continue
        if class_name and student.class_name != class_name:
            continue
        exam = data.exams.get(grade.exam_id)
        subject = data.subjects.get(grade.subject_code)
        entries.append(
            GradeDetailEntry(
                exam_id=grade.exam_id,
                exam_name=exam.exam_name if exam else grade.exam_id,
                subject_code=grade.subject_code,
                subject_name=subject.subject_name if subject else grade.subject_code,
                student_no=grade.student_no,
                student_name=student.name,
                class_name=student.class_name,
                score=grade.score,
                published=grade.published,
            )
        )
    return entries


def principal_export_grades(**filters: Optional[str]) -> str:
    entries = principal_grade_details(**filters)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["exam", "subject", "student_no", "student_name", "class", "score", "published"])
    for entry in entries:
        writer.writerow(
            [
                entry.exam_name,
                entry.subject_name,
                entry.student_no,
                entry.student_name,
                entry.class_name,
                entry.score,
                "是" if entry.published else "否",
            ]
        )
    _record_log(AuditAction.EXPORT, "principal", scope="principal", filters=filters)
    return output.getvalue()


def list_audit_logs(account: Account) -> List[AuditLogEntry]:
    if account.role == Role.PRINCIPAL:
        return list(data.audit_logs)
    if account.role == Role.TEACHER:
        teacher_id, subjects, _ = _teacher_for_account(account)
        return [
            log
            for log in data.audit_logs
            if log.actor == teacher_id
            or (
                log.details.get("subject_code") in subjects
                and log.action in {AuditAction.GRADE_CREATED, AuditAction.GRADE_UPDATED, AuditAction.GRADE_PUBLISHED}
            )
        ]
    raise AppError(status_code=403, detail="权限不足")


def mark_password_reset(actor: str, username: str) -> None:
    _record_log(AuditAction.PASSWORD_RESET, actor, username=username)
