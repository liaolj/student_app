from __future__ import annotations

from . import auth, services


def run_demo() -> None:
    print("=== 学生成绩管理系统演示 ===")
    principal_login = auth.authenticate("principal", "Pass@123")
    auth.get_account(principal_login.token)
    print("校长登录成功，角色:", principal_login.role.value)

    overview = services.principal_overview()
    print("当前考试统计：")
    for entry in overview:
        stats = entry.stats
        print(
            f"- {entry.exam_name} / {entry.subject_name}: 最高 {stats.highest}, 最低 {stats.lowest}, 平均 {stats.average}, 及格率 {stats.pass_rate}%"
        )

    teacher_login = auth.authenticate("t_chn", "Pass@123")
    teacher = auth.get_account(teacher_login.token)
    teacher_grades = services.teacher_list_grades(teacher)
    print("\n语文老师成绩列表 (前 3 条)：")
    for item in teacher_grades[:3]:
        print(f"- {item.student_name} ({item.student_no}) {item.score} 分")

    student_login = auth.authenticate("s_s001", "Pass@123")
    student = auth.get_account(student_login.token)
    student_view = services.list_student_grades(student)
    print("\n学生张三的成绩：")
    for grade in student_view.grades:
        print(f"- {grade.exam_name} {grade.subject_name}: {grade.score} 分 (班级均分 {grade.class_average})")


if __name__ == "__main__":
    run_demo()
