from __future__ import annotations

import html
import json
import secrets
import urllib.parse
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple

from . import auth, data, services
from .exceptions import AppError
from .models import Account, Role

ROLE_LABELS = {
    Role.STUDENT: "学生",
    Role.TEACHER: "老师",
    Role.PRINCIPAL: "校长",
}


@dataclass
class SessionData:
    token: Optional[str] = None
    flashes: List[Tuple[str, str]] = field(default_factory=list)


SESSIONS: Dict[str, SessionData] = {}
COOKIE_NAME = "SESSION_ID"


def _get_account(session: SessionData) -> Optional[Account]:
    if not session.token:
        return None
    try:
        return auth.get_account(session.token)
    except AppError:
        session.token = None
        return None


def _render_page(title: str, account: Optional[Account], flashes: List[Tuple[str, str]], content: str) -> str:
    nav_links = []
    if account:
        nav_links.append('<a href="/">首页</a>')
        nav_links.append('<a href="/logout">退出登录</a>')
    else:
        nav_links.append('<a href="/login">登录</a>')
    flash_html = "".join(
        f'<div class="flash {html.escape(category)}">{html.escape(message)}</div>'
        for category, message in flashes
    )
    role_badge = (
        f"当前身份：{ROLE_LABELS.get(account.role, account.role.value)}（{html.escape(account.username)}）"
        if account
        else ""
    )
    return f"""<!doctype html>
<html lang=\"zh-CN\">
  <head>
    <meta charset=\"utf-8\" />
    <title>{html.escape(title)}</title>
    <style>
      body {{ font-family: Arial, sans-serif; background: #f6f7fb; margin:0; }}
      header {{ background: #324960; color:#fff; padding:16px 24px; }}
      main {{ padding: 24px; }}
      .container {{ max-width: 1080px; margin:0 auto; background:#fff; padding:24px; box-shadow:0 2px 6px rgba(0,0,0,0.08); border-radius:8px; }}
      nav a {{ color:#fff; margin-right:16px; text-decoration:none; }}
      table {{ width:100%; border-collapse:collapse; margin-top:16px; }}
      th, td {{ border:1px solid #dfe3eb; padding:8px 12px; text-align:left; }}
      th {{ background:#f0f3f8; }}
      .flash {{ padding:12px 16px; border-radius:6px; margin:16px 0; }}
      .flash.error {{ background:#fdecea; color:#b3261e; }}
      .flash.success {{ background:#e5f5eb; color:#176537; }}
      .badge {{ display:inline-block; background:#d93025; color:#fff; padding:0 6px; margin-left:6px; border-radius:999px; font-size:12px; }}
      .tag {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; }}
      .tag.green {{ background:#e5f5eb; color:#176537; }}
      .tag.gray {{ background:#e4e7ed; color:#434a59; }}
      button {{ background:#324960; color:#fff; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; }}
      button.secondary {{ background:#61748f; }}
      button.danger {{ background:#b3261e; }}
      form.inline {{ display:inline-block; margin-right:12px; }}
      label {{ display:block; margin-top:8px; }}
      input[type=\"text\"], input[type=\"password\"], select, textarea {{ width:100%; padding:8px; border:1px solid #cdd5df; border-radius:4px; box-sizing:border-box; }}
    </style>
  </head>
  <body>
    <header>
      <div class=\"container\" style=\"background:transparent; box-shadow:none;\">
        <div style=\"display:flex; justify-content:space-between; align-items:center;\">
          <div>
            <strong>学生成绩管理系统</strong>
            <span style=\"margin-left:16px;\">{role_badge}</span>
          </div>
          <nav>{' '.join(nav_links)}</nav>
        </div>
      </div>
    </header>
    <main>
      <div class=\"container\">
        {flash_html}
        {content}
      </div>
    </main>
  </body>
</html>"""


def _login_form(username: str = "") -> str:
    return f"""
<h1>登录</h1>
<p>使用演示账号体验学生、老师、校长视角。</p>
<form method=\"post\" action=\"/login\" style=\"max-width:360px;\">
  <label>用户名</label>
  <input name=\"username\" required value=\"{html.escape(username)}\" />
  <label>密码</label>
  <input name=\"password\" type=\"password\" required />
  <button type=\"submit\" style=\"margin-top:16px; width:100%;\">登录</button>
</form>
<div style=\"margin-top:24px;\">
  <details>
    <summary>查看演示账号</summary>
    <ul>
      <li>校长：principal / Pass@123</li>
      <li>老师：t_chn、t_mth、t_eng / Pass@123</li>
      <li>学生：s_s001 ~ s_s006 / Pass@123</li>
    </ul>
  </details>
</div>
"""


def render_login_page(session: SessionData, username: str = "") -> str:
    account = _get_account(session)
    flashes = session.flashes.copy()
    session.flashes.clear()
    return _render_page("登录 - 学生成绩管理系统", account, flashes, _login_form(username))


def render_student_page(session: SessionData, term: Optional[str] = None, exam_id: Optional[str] = None) -> str:
    account = _get_account(session)
    if not account or account.role != Role.STUDENT:
        session.flashes.append(("error", "仅学生可访问该页面"))
        return render_redirect("/login")

    try:
        result = services.list_student_grades(account, term=term, exam_id=exam_id)
    except AppError as exc:
        session.flashes.append(("error", exc.detail))
        return render_redirect("/")

    exams = sorted(data.exams.values(), key=lambda e: e.exam_date)
    terms = sorted({exam.term for exam in data.exams.values()})
    selected_term = term or ""
    selected_exam = exam_id or ""
    rows = "".join(
        """
          <tr>
            <td>{exam}</td>
            <td>{date}</td>
            <td>{subject}</td>
            <td>{score:.1f}</td>
            <td>{avg:.2f}</td>
          </tr>
        """.format(
            exam=html.escape(item.exam_name),
            date=item.exam_date.isoformat() if item.exam_date else "-",
            subject=html.escape(item.subject_name),
            score=item.score,
            avg=item.class_average,
        )
        for item in result.grades
    )
    badge = "<span class=\"badge\">新</span>" if result.has_unread else ""
    filters = """
<form method=\"get\" action=\"/student\" style=\"display:flex; gap:16px; flex-wrap:wrap;\">
  <div>
    <label>学期</label>
    <select name=\"term\">
      <option value=\"\">全部</option>
      {term_options}
    </select>
  </div>
  <div>
    <label>考试</label>
    <select name=\"exam_id\">
      <option value=\"\">全部</option>
      {exam_options}
    </select>
  </div>
  <div style=\"align-self:flex-end;\">
    <button type=\"submit\">应用筛选</button>
  </div>
</form>
""".format(
        term_options="".join(
            f'<option value="{html.escape(item)}" {"selected" if item == selected_term else ""}>{html.escape(item)}</option>'
            for item in terms
        ),
        exam_options="".join(
            f'<option value="{exam.exam_id}" {"selected" if exam.exam_id == selected_exam else ""}>{html.escape(exam.exam_name)}</option>'
            for exam in exams
        ),
    )
    table = (
        "<table>" +
        "<thead><tr><th>考试</th><th>日期</th><th>科目</th><th>分数</th><th>班级均分</th></tr></thead><tbody>" +
        (rows or "<tr><td colspan=5>当前筛选条件下暂无发布成绩。</td></tr>") +
        "</tbody></table>"
    )
    content = f"<h1>我的成绩{badge}</h1>" + filters + table
    flashes = session.flashes.copy()
    session.flashes.clear()
    return _render_page("学生主页", account, flashes, content)


def render_teacher_page(
    session: SessionData,
    exam_id: Optional[str] = None,
    class_name: Optional[str] = None,
    sort_by: str = "student_no",
) -> str:
    account = _get_account(session)
    if not account or account.role != Role.TEACHER:
        session.flashes.append(("error", "仅老师可访问该页面"))
        return render_redirect("/login")

    teacher = data.teachers.get(account.bind_id or "")
    if not teacher:
        session.flashes.append(("error", "教师信息未绑定"))
        return render_redirect("/")

    try:
        grades = services.teacher_list_grades(account, exam_id=exam_id, class_name=class_name, sort_by=sort_by)
    except AppError as exc:
        session.flashes.append(("error", exc.detail))
        return render_redirect("/")

    exams = sorted(data.exams.values(), key=lambda e: e.exam_date)
    subjects = [data.subjects.get(code) for code in teacher.subjects if code in data.subjects]
    rows = "".join(
        """
          <tr>
            <td>{student_no}</td>
            <td>{student_name}</td>
            <td>{class_name}</td>
            <td>{subject}</td>
            <td>{score:.1f}</td>
            <td>{status}</td>
          </tr>
        """.format(
            student_no=html.escape(item.student_no),
            student_name=html.escape(item.student_name),
            class_name=html.escape(item.class_name),
            subject=html.escape(item.subject_code),
            score=item.score,
            status='<span class="tag green">已发布</span>' if item.published else '<span class="tag gray">未发布</span>',
        )
        for item in grades
    )
    filters = """
<form method=\"get\" action=\"/teacher\" style=\"display:flex; gap:16px; flex-wrap:wrap;\">
  <div>
    <label>考试</label>
    <select name=\"exam_id\">
      <option value=\"\">全部</option>
      {exam_options}
    </select>
  </div>
  <div>
    <label>班级</label>
    <select name=\"class_name\">
      <option value=\"\">全部</option>
      {class_options}
    </select>
  </div>
  <div>
    <label>排序</label>
    <select name=\"sort_by\">
      {sort_options}
    </select>
  </div>
  <div style=\"align-self:flex-end;\">
    <button type=\"submit\">应用</button>
  </div>
</form>
<form method=\"get\" action=\"/teacher/export\" class=\"inline\">
  <input type=\"hidden\" name=\"exam_id\" value=\"{html.escape(exam_id or '')}\" />
  <input type=\"hidden\" name=\"class_name\" value=\"{html.escape(class_name or '')}\" />
  <button type=\"submit\" class=\"secondary\">导出 CSV</button>
</form>
""".format(
        exam_options="".join(
            f'<option value="{exam.exam_id}" {"selected" if exam.exam_id == exam_id else ""}>{html.escape(exam.exam_name)}</option>'
            for exam in exams
        ),
        class_options="".join(
            f'<option value="{html.escape(cls)}" {"selected" if cls == class_name else ""}>{html.escape(cls)}</option>'
            for cls in teacher.classes
        ),
        sort_options="".join(
            f'<option value="{value}" {"selected" if value == sort_by else ""}>{label}</option>'
            for value, label in (
                ("student_no", "按学号"),
                ("score_desc", "分数从高到低"),
                ("score_asc", "分数从低到高"),
            )
        ),
        exam_id=exam_id or "",
        class_name=class_name or "",
    )
    table = (
        "<table>" +
        "<thead><tr><th>学号</th><th>姓名</th><th>班级</th><th>科目</th><th>分数</th><th>状态</th></tr></thead><tbody>" +
        (rows or "<tr><td colspan=6>暂无成绩记录。</td></tr>") +
        "</tbody></table>"
    )
    subjects_options = "".join(
        f'<option value="{subject.subject_code}">{html.escape(subject.subject_name)}</option>'
        for subject in subjects
        if subject
    )
    content = (
        "<h1>科目成绩列表</h1>" +
        filters +
        table +
        """
<section style=\"margin-top:32px;\">
  <h2>批量导入成绩</h2>
  <form method=\"post\" action=\"/teacher/import\" style=\"max-width:480px;\">
    <label>粘贴 CSV 内容</label>
    <textarea name=\"csv_text\" rows=\"6\" placeholder=\"exam_id,subject_code,student_no,score\"></textarea>
    <button type=\"submit\" style=\"margin-top:12px;\">导入</button>
  </form>
</section>
<section style=\"margin-top:32px;\">
  <h2>发布成绩</h2>
  <form method=\"post\" action=\"/teacher/publish\" style=\"display:flex; gap:16px; flex-wrap:wrap;\">
    <div>
      <label>考试</label>
      <select name=\"exam_id\" required>
        {exam_publish_options}
      </select>
    </div>
    <div>
      <label>科目</label>
      <select name=\"subject_code\" required>
        {subjects_options}
      </select>
    </div>
    <div style=\"align-self:flex-end;\">
      <button type=\"submit\">发布</button>
    </div>
  </form>
</section>
""".format(
            exam_publish_options="".join(
                f'<option value="{exam.exam_id}">{html.escape(exam.exam_name)}</option>'
                for exam in exams
            ),
            subjects_options=subjects_options or "<option value=\"\">暂无科目</option>",
        )
    )
    flashes = session.flashes.copy()
    session.flashes.clear()
    return _render_page("老师主页", account, flashes, content)


def render_principal_page(
    session: SessionData,
    exam_id: Optional[str] = None,
    subject_code: Optional[str] = None,
    class_name: Optional[str] = None,
) -> str:
    account = _get_account(session)
    if not account or account.role != Role.PRINCIPAL:
        session.flashes.append(("error", "仅校长可访问该页面"))
        return render_redirect("/login")

    overview = services.principal_overview()
    details = services.principal_grade_details(
        exam_id=exam_id or None,
        subject_code=subject_code or None,
        class_name=class_name or None,
    )
    audit_logs = services.list_audit_logs(account)

    exams = sorted(data.exams.values(), key=lambda e: e.exam_date)
    subjects = list(data.subjects.values())
    classes = sorted({student.class_name for student in data.students.values()})
    accounts = sorted(data.accounts.values(), key=lambda a: a.username)

    overview_rows = "".join(
        """
          <tr>
            <td>{exam}</td>
            <td>{subject}</td>
            <td>{highest:.1f}</td>
            <td>{lowest:.1f}</td>
            <td>{average:.2f}</td>
            <td>{pass_rate:.2f}%</td>
          </tr>
        """.format(
            exam=html.escape(entry.exam_name),
            subject=html.escape(entry.subject_name),
            highest=entry.stats.highest,
            lowest=entry.stats.lowest,
            average=entry.stats.average,
            pass_rate=entry.stats.pass_rate,
        )
        for entry in overview
    )
    detail_rows = "".join(
        """
          <tr>
            <td>{exam}</td>
            <td>{subject}</td>
            <td>{student_no}</td>
            <td>{student_name}</td>
            <td>{class_name}</td>
            <td>{score:.1f}</td>
            <td>{status}</td>
          </tr>
        """.format(
            exam=html.escape(item.exam_name),
            subject=html.escape(item.subject_name),
            student_no=html.escape(item.student_no),
            student_name=html.escape(item.student_name),
            class_name=html.escape(item.class_name),
            score=item.score,
            status="已发布" if item.published else "未发布",
        )
        for item in details
    )
    log_rows = "".join(
        """
          <tr>
            <td>{time}</td>
            <td>{actor}</td>
            <td>{action}</td>
            <td><pre style=\"margin:0;\">{details}</pre></td>
          </tr>
        """.format(
            time=html.escape(log.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")),
            actor=html.escape(log.actor),
            action=html.escape(log.action.value),
            details=html.escape(json.dumps(log.details, ensure_ascii=False, indent=2)),
        )
        for log in audit_logs
    )
    filters_form = """
<form method=\"get\" action=\"/principal\" style=\"display:flex; gap:16px; flex-wrap:wrap;\">
  <div>
    <label>考试</label>
    <select name=\"exam_id\">
      <option value=\"\">全部</option>
      {exam_options}
    </select>
  </div>
  <div>
    <label>科目</label>
    <select name=\"subject_code\">
      <option value=\"\">全部</option>
      {subject_options}
    </select>
  </div>
  <div>
    <label>班级</label>
    <select name=\"class_name\">
      <option value=\"\">全部</option>
      {class_options}
    </select>
  </div>
  <div style=\"align-self:flex-end;\">
    <button type=\"submit\">应用</button>
  </div>
</form>
<form method=\"get\" action=\"/principal/export\" class=\"inline\">
  <input type=\"hidden\" name=\"exam_id\" value=\"{html.escape(exam_id or '')}\" />
  <input type=\"hidden\" name=\"subject_code\" value=\"{html.escape(subject_code or '')}\" />
  <input type=\"hidden\" name=\"class_name\" value=\"{html.escape(class_name or '')}\" />
  <button type=\"submit\" class=\"secondary\">导出 CSV</button>
</form>
""".format(
        exam_options="".join(
            f'<option value="{exam.exam_id}" {"selected" if exam.exam_id == exam_id else ""}>{html.escape(exam.exam_name)}</option>'
            for exam in exams
        ),
        subject_options="".join(
            f'<option value="{subject.subject_code}" {"selected" if subject.subject_code == subject_code else ""}>{html.escape(subject.subject_name)}</option>'
            for subject in subjects
        ),
        class_options="".join(
            f'<option value="{html.escape(cls)}" {"selected" if cls == class_name else ""}>{html.escape(cls)}</option>'
            for cls in classes
        ),
        exam_id=exam_id or "",
        subject_code=subject_code or "",
        class_name=class_name or "",
    )
    accounts_options = "".join(
        f'<option value="{html.escape(account.username)}">{html.escape(account.username)}（{ROLE_LABELS.get(account.role, account.role.value)}）</option>'
        for account in accounts
    )
    content = (
        "<h1>校长总览</h1>"
        + """
<section>
  <h2>成绩统计</h2>
  <table>
    <thead><tr><th>考试</th><th>科目</th><th>最高分</th><th>最低分</th><th>平均分</th><th>及格率</th></tr></thead>
    <tbody>{overview_rows}</tbody>
  </table>
</section>
<section style=\"margin-top:32px;\">
  <h2>成绩明细</h2>
  {filters_form}
  <table>
    <thead><tr><th>考试</th><th>科目</th><th>学号</th><th>姓名</th><th>班级</th><th>分数</th><th>是否发布</th></tr></thead>
    <tbody>{detail_rows}</tbody>
  </table>
</section>
<section style=\"margin-top:32px;\">
  <h2>账号管理</h2>
  <form method=\"post\" action=\"/principal/reset\" style=\"display:flex; gap:16px; flex-wrap:wrap;\">
    <div>
      <label>选择账号</label>
      <select name=\"username\" required>{accounts_options}</select>
    </div>
    <div style=\"align-self:flex-end;\">
      <button type=\"submit\" class=\"danger\">重置密码</button>
    </div>
  </form>
</section>
<section style=\"margin-top:32px;\">
  <h2>审计日志</h2>
  <table>
    <thead><tr><th>时间</th><th>操作者</th><th>动作</th><th>详情</th></tr></thead>
    <tbody>{log_rows}</tbody>
  </table>
</section>
""".format(
            overview_rows=overview_rows or "<tr><td colspan=6>暂无数据</td></tr>",
            filters_form=filters_form,
            detail_rows=detail_rows or "<tr><td colspan=7>暂无数据</td></tr>",
            accounts_options=accounts_options,
            log_rows=log_rows or "<tr><td colspan=4>暂无日志</td></tr>",
        )
    )
    flashes = session.flashes.copy()
    session.flashes.clear()
    return _render_page("校长总览", account, flashes, content)


def render_redirect(location: str) -> str:
    return f"REDIRECT::{location}"


def _parse_form(handler: BaseHTTPRequestHandler) -> Dict[str, str]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b""
    data = urllib.parse.parse_qs(raw.decode("utf-8"))
    return {key: values[0] for key, values in data.items()}


def _apply_redirect(handler: BaseHTTPRequestHandler, location: str, session_id: str, new_session: bool) -> None:
    handler.send_response(HTTPStatus.SEE_OTHER)
    handler.send_header("Location", location)
    if new_session:
        handler.send_header("Set-Cookie", f"{COOKIE_NAME}={session_id}; Path=/; HttpOnly")
    handler.end_headers()


def _write_html(handler: BaseHTTPRequestHandler, content: str, session_id: str, new_session: bool) -> None:
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    if new_session:
        handler.send_header("Set-Cookie", f"{COOKIE_NAME}={session_id}; Path=/; HttpOnly")
    body = content.encode("utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_csv(handler: BaseHTTPRequestHandler, content: str, filename: str, session_id: str, new_session: bool) -> None:
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/csv; charset=utf-8")
    handler.send_header("Content-Disposition", f"attachment; filename={filename}")
    if new_session:
        handler.send_header("Set-Cookie", f"{COOKIE_NAME}={session_id}; Path=/; HttpOnly")
    body = content.encode("utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _load_session(handler: BaseHTTPRequestHandler) -> Tuple[str, SessionData, bool]:
    cookie_header = handler.headers.get("Cookie", "")
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:  # noqa: BLE001
        cookie = SimpleCookie()
    if COOKIE_NAME in cookie:
        session_id = cookie[COOKIE_NAME].value
        session = SESSIONS.setdefault(session_id, SessionData())
        return session_id, session, False
    session_id = secrets.token_hex(16)
    session = SessionData()
    SESSIONS[session_id] = session
    return session_id, session, True


class GradeRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        session_id, session, new_session = _load_session(self)
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        path = parsed.path

        if path == "/":
            account = _get_account(session)
            if not account:
                _apply_redirect(self, "/login", session_id, new_session)
                return
            if account.role == Role.STUDENT:
                _apply_redirect(self, "/student", session_id, new_session)
                return
            if account.role == Role.TEACHER:
                _apply_redirect(self, "/teacher", session_id, new_session)
                return
            _apply_redirect(self, "/principal", session_id, new_session)
            return

        if path == "/login":
            html_content = render_login_page(session)
            _write_html(self, html_content, session_id, new_session)
            return

        if path == "/logout":
            if session.token:
                auth.logout(session.token)
            session.token = None
            session.flashes.append(("success", "您已退出登录"))
            _apply_redirect(self, "/login", session_id, new_session)
            return

        if path == "/student":
            term = query.get("term", [""])[0] or None
            exam_id = query.get("exam_id", [""])[0] or None
            page = render_student_page(session, term=term, exam_id=exam_id)
            if page.startswith("REDIRECT::"):
                _apply_redirect(self, page.split("::", 1)[1], session_id, new_session)
            else:
                _write_html(self, page, session_id, new_session)
            return

        if path == "/teacher":
            exam_id = query.get("exam_id", [""])[0] or None
            class_name = query.get("class_name", [""])[0] or None
            sort_by = query.get("sort_by", ["student_no"])[0]
            page = render_teacher_page(session, exam_id=exam_id, class_name=class_name, sort_by=sort_by)
            if page.startswith("REDIRECT::"):
                _apply_redirect(self, page.split("::", 1)[1], session_id, new_session)
            else:
                _write_html(self, page, session_id, new_session)
            return

        if path == "/teacher/export":
            account = _get_account(session)
            if not account or account.role != Role.TEACHER:
                session.flashes.append(("error", "无权执行该操作"))
                _apply_redirect(self, "/login", session_id, new_session)
                return
            exam_id = query.get("exam_id", [""])[0] or None
            class_name = query.get("class_name", [""])[0] or None
            try:
                csv_content = services.teacher_export_grades(account, exam_id=exam_id, class_name=class_name)
            except AppError as exc:
                session.flashes.append(("error", exc.detail))
                _apply_redirect(self, "/teacher", session_id, new_session)
                return
            _write_csv(self, csv_content, "teacher_grades.csv", session_id, new_session)
            return

        if path == "/principal":
            exam_id = query.get("exam_id", [""])[0] or None
            subject_code = query.get("subject_code", [""])[0] or None
            class_name = query.get("class_name", [""])[0] or None
            page = render_principal_page(session, exam_id=exam_id, subject_code=subject_code, class_name=class_name)
            if page.startswith("REDIRECT::"):
                _apply_redirect(self, page.split("::", 1)[1], session_id, new_session)
            else:
                _write_html(self, page, session_id, new_session)
            return

        if path == "/principal/export":
            account = _get_account(session)
            if not account or account.role != Role.PRINCIPAL:
                session.flashes.append(("error", "无权执行该操作"))
                _apply_redirect(self, "/login", session_id, new_session)
                return
            filters = {
                "exam_id": query.get("exam_id", [""])[0] or None,
                "subject_code": query.get("subject_code", [""])[0] or None,
                "class_name": query.get("class_name", [""])[0] or None,
            }
            try:
                csv_content = services.principal_export_grades(**filters)
            except AppError as exc:
                session.flashes.append(("error", exc.detail))
                _apply_redirect(self, "/principal", session_id, new_session)
                return
            _write_csv(self, csv_content, "all_grades.csv", session_id, new_session)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        session_id, session, new_session = _load_session(self)
        path = urllib.parse.urlparse(self.path).path

        if path == "/login":
            form = _parse_form(self)
            username = form.get("username", "").strip()
            password = form.get("password", "")
            if not username or not password:
                session.flashes.append(("error", "请输入用户名和密码"))
                html_content = render_login_page(session, username=username)
                _write_html(self, html_content, session_id, new_session)
                return
            try:
                result = auth.authenticate(username, password)
            except AppError as exc:
                session.flashes.append(("error", exc.detail))
                html_content = render_login_page(session, username=username)
                _write_html(self, html_content, session_id, new_session)
                return
            session.token = result.token
            if result.must_change_password:
                session.flashes.append(("success", "首次登录，请尽快修改初始密码"))
            _apply_redirect(self, "/", session_id, new_session)
            return

        if path == "/teacher/import":
            account = _get_account(session)
            if not account or account.role != Role.TEACHER:
                session.flashes.append(("error", "无权执行该操作"))
                _apply_redirect(self, "/login", session_id, new_session)
                return
            form = _parse_form(self)
            csv_text = form.get("csv_text", "").strip()
            if not csv_text:
                session.flashes.append(("error", "请粘贴 CSV 内容"))
                _apply_redirect(self, "/teacher", session_id, new_session)
                return
            try:
                result = services.teacher_import_grades(account, csv_text)
            except AppError as exc:
                session.flashes.append(("error", exc.detail))
            else:
                processed = result.get("processed", 0)
                errors = result.get("errors", [])
                if processed:
                    session.flashes.append(("success", f"成功导入 {processed} 条成绩记录"))
                for message in errors:
                    session.flashes.append(("error", message))
            _apply_redirect(self, "/teacher", session_id, new_session)
            return

        if path == "/teacher/publish":
            account = _get_account(session)
            if not account or account.role != Role.TEACHER:
                session.flashes.append(("error", "无权执行该操作"))
                _apply_redirect(self, "/login", session_id, new_session)
                return
            form = _parse_form(self)
            exam_id = form.get("exam_id", "").strip()
            subject_code = form.get("subject_code", "").strip()
            if not exam_id or not subject_code:
                session.flashes.append(("error", "请选择考试与科目"))
                _apply_redirect(self, "/teacher", session_id, new_session)
                return
            try:
                count = services.publish_grades(account, exam_id, subject_code)
            except AppError as exc:
                session.flashes.append(("error", exc.detail))
            else:
                session.flashes.append(("success", f"已发布 {count} 条成绩"))
            _apply_redirect(self, "/teacher", session_id, new_session)
            return

        if path == "/principal/reset":
            account = _get_account(session)
            if not account or account.role != Role.PRINCIPAL:
                session.flashes.append(("error", "无权执行该操作"))
                _apply_redirect(self, "/login", session_id, new_session)
                return
            form = _parse_form(self)
            username = form.get("username", "").strip()
            if not username:
                session.flashes.append(("error", "请选择账号"))
                _apply_redirect(self, "/principal", session_id, new_session)
                return
            try:
                new_password = auth.reset_password(username)
                services.mark_password_reset(account.username, username)
            except AppError as exc:
                session.flashes.append(("error", exc.detail))
            else:
                session.flashes.append(("success", f"账号 {username} 新密码：{new_password}"))
            _apply_redirect(self, "/principal", session_id, new_session)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    with HTTPServer((host, port), GradeRequestHandler) as httpd:
        print(f"服务器已启动：http://{host}:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:  # pragma: no cover - 手动停止
            print("\n服务器已停止")


if __name__ == "__main__":
    run()
