from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from . import data
from .exceptions import AppError
from .models import Account, LoginResult, Role
from .security import generate_random_password, hash_password, verify_password

_tokens: Dict[str, str] = {}

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def authenticate(username: str, password: str) -> LoginResult:
    account = data.accounts.get(username)
    if not account:
        raise AppError(status_code=401, detail="账号或密码错误")

    if account.locked_until and account.locked_until > _now():
        raise AppError(status_code=423, detail="账号或密码错误/账号锁定")

    if not verify_password(password, account.password_hash):
        account.failed_attempts += 1
        if account.failed_attempts >= LOCKOUT_THRESHOLD:
            account.locked_until = _now() + timedelta(minutes=LOCKOUT_MINUTES)
        raise AppError(status_code=401, detail="账号或密码错误")

    account.failed_attempts = 0
    account.locked_until = None

    token = generate_random_password(32)
    _tokens[token] = account.username
    return LoginResult(token=token, role=account.role, must_change_password=account.force_password_change)


def get_account(token: str) -> Account:
    username = _tokens.get(token)
    if not username:
        raise AppError(status_code=401, detail="未登录")
    account = data.accounts.get(username)
    if not account:
        raise AppError(status_code=401, detail="未登录")
    return account


def require_role(token: str, role: Role) -> Account:
    account = get_account(token)
    if account.role != role:
        raise AppError(status_code=403, detail="权限不足")
    return account


def require_teacher_or_principal(token: str) -> Account:
    account = get_account(token)
    if account.role not in {Role.TEACHER, Role.PRINCIPAL}:
        raise AppError(status_code=403, detail="权限不足")
    return account


def change_password(account: Account, old_password: str, new_password: str) -> None:
    if not verify_password(old_password, account.password_hash):
        raise AppError(status_code=400, detail="旧密码不正确")
    account.password_hash = hash_password(new_password)
    account.force_password_change = False
    account.failed_attempts = 0
    account.locked_until = None


def reset_password(username: str) -> str:
    account = data.accounts.get(username)
    if not account:
        raise AppError(status_code=404, detail="账号不存在")
    new_password = generate_random_password()
    account.password_hash = hash_password(new_password)
    account.force_password_change = True
    account.failed_attempts = 0
    account.locked_until = None
    return new_password


def logout(token: str) -> None:
    _tokens.pop(token, None)
