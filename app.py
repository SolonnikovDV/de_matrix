import json
import os
import re
import hashlib
import sys
import argparse
import socket
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from flask import Flask, render_template, jsonify, abort, send_from_directory, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from pathlib import Path as PathLib
from typing import Dict, Optional, Tuple, Any, List, Set

from core.tree import (
    build_tree_from_matrix_data,
    collect_leaves,
    get_node_by_path,
    get_ancestors,
    path_to_url,
)
from core.loaders import load_unified_source, load_excel, META_KEYS
from core.schema import validate_source, get_schema_info
from core import config_loader as _config_loader
from core.config_loader import load_app_config, load_metadata, invalidate_metadata_cache
from core.tools_matcher import get_tools_for_text
from core.checkpoint import (
    load_checkpoint,
    save_checkpoint,
    source_matches_checkpoint,
    build_checkpoint_data,
    get_source_content_hash,
)
from core.backup import (
    create_backup,
    list_backups,
    restore_backup,
    check_backup_compatibility,
    get_stable_backup_id,
    set_stable_backup_id,
    ensure_stable_backup,
)
from core.upload_merge import merge_upload_into_source
from core.diff_engine import build_revision_payload
from storage.runtime import get_storage_mode, approval_required as storage_approval_required
from storage.db import db_session, ENGINE
from storage.models import (
    Base,
    ChangeRequest,
    ChangeRevision,
    ApprovalDecision,
    User,
    ChangeDiscussionThread,
    ChangeDiscussionMessage,
    NotificationLog,
)
from sqlalchemy import select, text, func, or_
from storage.approval_repo import (
    create_change_request,
    add_revision,
    set_status as approval_set_status,
    get_latest_payload,
    list_change_requests,
    get_change_request_details,
)
from storage.postgres_repo import (
    load_unified_from_db,
    replace_unified_in_db,
    list_domains as list_domains_from_db,
    load_tree_projection,
    upsert_from_staging_projection,
)
from storage.staging_repo import create_staging_batch, load_staging_tree_projection
from storage.mongo_repo import (
    load_literature_map,
    upsert_literature_item,
    delete_literature_item as mongo_delete_literature_item,
    add_literature_file as mongo_add_literature_file,
)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTHOR_NAME = os.environ.get("DE_MATRIX_AUTHOR_NAME", "Dmitry Solonnikov")
AUTHOR_TELEGRAM = os.environ.get("DE_MATRIX_AUTHOR_TELEGRAM", "https://t.me/Dmitry_as_SoloD")
REPOSITORY_URL = os.environ.get("DE_MATRIX_REPO_URL", "https://github.com/SolonnikovDV/de_matrix.git")
SECRET_KEY = os.environ.get("DE_MATRIX_SECRET_KEY") or hashlib.sha256(os.urandom(32)).hexdigest()
ADMIN_USERNAME = os.environ.get("DE_MATRIX_ADMIN_USERNAME", "admin")
ADMIN_BOOTSTRAP_PASSWORD = os.environ.get("DE_MATRIX_ADMIN_PASSWORD", "")
TRUST_REQUEST_ROLE = os.environ.get("DE_MATRIX_TRUST_REQUEST_ROLE", "0").strip().lower() in ("1", "true", "yes")
AUTH_REQUIRED = os.environ.get("DE_MATRIX_AUTH_REQUIRED", "1").strip().lower() in ("1", "true", "yes")
NOTIFICATIONS_ENABLED = os.environ.get("DE_MATRIX_NOTIFICATIONS_ENABLED", "1").strip().lower() in ("1", "true", "yes")
SMTP_HOST = (os.environ.get("DE_MATRIX_SMTP_HOST") or "smtp").strip()
SMTP_PORT = int((os.environ.get("DE_MATRIX_SMTP_PORT") or "1025").strip())
SMTP_FROM = (os.environ.get("DE_MATRIX_SMTP_FROM") or "de-matrix@localhost").strip()
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("DE_MATRIX_DEPLOY_TARGET", "local").strip().lower() == "production":
    app.config["SESSION_COOKIE_SECURE"] = True
# Путь к config — гарантированно относительно app.py (для metadata.yaml: stack_labels, tools)
_config_loader.CONFIG_DIR = PathLib(BASE_DIR) / "config"

_matrix = None
_meta = None
_tree = None
_current_source_file = None  # имя файла-источника, по которому загружены данные
_admin_seed_checked = False


def _is_db_mode() -> bool:
    return get_storage_mode() == "db"


def _session_actor_role() -> Tuple[Optional[str], Optional[str]]:
    actor = (session.get("actor") or "").strip() or None
    role = (session.get("role") or "").strip().lower() or None
    if role not in ("user", "admin"):
        role = None
    return actor, role


def _load_user(username: str) -> Optional[User]:
    uname = (username or "").strip()
    if not uname:
        return None
    with db_session() as db:
        return db.execute(select(User).where(User.username == uname)).scalars().first()


def _require_authenticated():
    actor = (session.get("actor") or "").strip()
    role = (session.get("role") or "").strip().lower()
    if not session.get("authenticated") or role not in ("user", "admin") or not actor:
        return None, (jsonify({"ok": False, "error": "Authentication required"}), 401)
    return {"actor": actor, "role": role}, None


def _ensure_admin_seed():
    with db_session() as db:
        admin = db.execute(select(User).where(User.username == ADMIN_USERNAME)).scalars().first()
        if admin:
            return
        password = ADMIN_BOOTSTRAP_PASSWORD.strip() or "admin12345"
        db.add(
            User(
                username=ADMIN_USERNAME,
                role="admin",
                full_name="System Administrator",
                email="",
                password_hash=generate_password_hash(password),
                must_change_password=True,
                is_active=True,
            )
        )
        print(f"[auth] bootstrap admin '{ADMIN_USERNAME}' created (must change password on first login)")


def _is_safe_next_url(next_url: str) -> bool:
    return bool(next_url) and next_url.startswith("/") and not next_url.startswith("//")


def _extract_actor_role(data: Optional[Dict] = None) -> Tuple[str, str]:
    session_actor, session_role = _session_actor_role()
    if session_role:
        return session_actor or "user", session_role

    payload = data or {}
    actor = (
        request.headers.get("X-Actor")
        or payload.get("actor")
        or request.form.get("actor")
        or request.args.get("actor")
        or "user"
    )
    if TRUST_REQUEST_ROLE:
        role = (
            request.headers.get("X-Role")
            or payload.get("role")
            or request.form.get("role")
            or request.args.get("role")
            or "user"
        )
    else:
        role = "user"
    actor = (actor or "user").strip() or "user"
    role = (role or "user").strip().lower() or "user"
    return actor, role


def _require_admin(data: Optional[Dict] = None):
    actor, role = _extract_actor_role(data)
    if role != "admin":
        return None, (jsonify({"ok": False, "error": "Admin role required"}), 403)
    return actor, None


DISCUSSION_THREAD_STATUSES = {"open", "needs_author_response", "resolved"}


def _serialize_discussion_thread(thread: ChangeDiscussionThread) -> Dict[str, Any]:
    return {
        "id": thread.id,
        "change_request_id": thread.change_request_id,
        "subject": thread.subject,
        "status": thread.status,
        "requires_resolution": bool(thread.requires_resolution),
        "created_by": thread.created_by,
        "created_role": thread.created_role,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        "resolved_by": thread.resolved_by,
        "resolved_at": thread.resolved_at.isoformat() if thread.resolved_at else None,
        "messages": [
            {
                "id": m.id,
                "author": m.author,
                "author_role": m.author_role,
                "body": m.body,
                "kind": m.kind,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in sorted(thread.messages or [], key=lambda x: x.id or 0)
        ],
    }


def _extract_mentions(text_value: str) -> List[str]:
    return sorted(set(re.findall(r"@([A-Za-z0-9_.-]+)", text_value or "")))


def _active_users_by_role(session, role: str) -> List[User]:
    return session.execute(select(User).where(User.role == role, User.is_active == True)).scalars().all()


def _active_user_by_username(session, username: str) -> Optional[User]:
    uname = (username or "").strip()
    if not uname:
        return None
    return session.execute(select(User).where(User.username == uname, User.is_active == True)).scalars().first()


def _render_notification(event_type: str, payload: Dict[str, Any]) -> Tuple[str, str]:
    p = payload or {}
    if event_type == "cr_submitted":
        return (
            f"[de_matrix] Change #{p.get('change_id')} submitted for review",
            (
                f"Change request #{p.get('change_id')}\n"
                f"Title: {p.get('title')}\n"
                f"Author: {p.get('author')}\n"
                f"Status: {p.get('status')}\n"
                "Please review in /changes."
            ),
        )
    if event_type == "cr_status":
        return (
            f"[de_matrix] Change #{p.get('change_id')} status -> {p.get('status')}",
            (
                f"Change request #{p.get('change_id')}\n"
                f"Title: {p.get('title')}\n"
                f"New status: {p.get('status')}\n"
                f"Changed by: {p.get('actor')}\n"
                f"Comment: {p.get('comment') or '-'}"
            ),
        )
    if event_type == "mention":
        return (
            f"[de_matrix] Mention in discussion for change #{p.get('change_id')}",
            (
                f"You were mentioned by {p.get('actor')} in discussion of change #{p.get('change_id')}.\n\n"
                f"{p.get('text') or ''}"
            ),
        )
    if event_type == "release":
        return (
            f"[de_matrix] New release deployed: {p.get('ref')}",
            f"A new release has been deployed.\n\nRef: {p.get('ref')}\nOpen the application to review latest changes.",
        )
    return (
        f"[de_matrix] Notification: {event_type}",
        str(p),
    )


def _create_notification_log(
    session,
    *,
    event_type: str,
    created_by: str,
    recipients: List[str],
    subject: str,
    body: str,
    context: Optional[Dict[str, Any]] = None,
) -> NotificationLog:
    log = NotificationLog(
        event_type=event_type,
        status="pending",
        subject=subject,
        body=body,
        recipients=recipients or [],
        context=context or {},
        error="",
        attempts=0,
        created_by=created_by or "system",
    )
    session.add(log)
    session.flush()
    return log


def _deliver_notification_log(log: NotificationLog) -> Tuple[bool, str]:
    if not NOTIFICATIONS_ENABLED:
        log.status = "skipped"
        log.error = "notifications disabled"
        log.attempts = (log.attempts or 0) + 1
        log.last_attempt_at = datetime.now(timezone.utc)
        return False, "notifications disabled"
    to_list = sorted({(r or "").strip() for r in (log.recipients or []) if (r or "").strip()})
    if not to_list:
        log.status = "skipped"
        log.error = "no recipients"
        log.attempts = (log.attempts or 0) + 1
        log.last_attempt_at = datetime.now(timezone.utc)
        return False, "no recipients"
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = log.subject
    msg.set_content(log.body)
    log.attempts = (log.attempts or 0) + 1
    log.last_attempt_at = datetime.now(timezone.utc)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.send_message(msg)
        log.status = "sent"
        log.error = ""
        log.sent_at = datetime.now(timezone.utc)
        return True, ""
    except Exception as exc:
        err = str(exc)
        log.status = "failed"
        log.error = err
        print(f"[notify] send failed: {err}")
        return False, err


def _notify_cr_submitted(session, cr: ChangeRequest) -> None:
    admins = _active_users_by_role(session, "admin")
    recipients = [u.email for u in admins if u.email and u.username != cr.created_by]
    subject, body = _render_notification(
        "cr_submitted",
        {
            "change_id": cr.id,
            "title": cr.title,
            "author": cr.created_by,
            "status": cr.status,
        },
    )
    log = _create_notification_log(
        session,
        event_type="cr_submitted",
        created_by=cr.created_by,
        recipients=recipients,
        subject=subject,
        body=body,
        context={"change_id": cr.id},
    )
    _deliver_notification_log(log)


def _notify_cr_status_to_author(session, cr: ChangeRequest, status: str, actor: str, comment: str = "") -> None:
    author = _active_user_by_username(session, cr.created_by)
    recipients = [author.email] if author and author.email else []
    subject, body = _render_notification(
        "cr_status",
        {
            "change_id": cr.id,
            "title": cr.title,
            "status": status,
            "actor": actor,
            "comment": comment,
        },
    )
    log = _create_notification_log(
        session,
        event_type="cr_status",
        created_by=actor,
        recipients=recipients,
        subject=subject,
        body=body,
        context={"change_id": cr.id, "status": status},
    )
    _deliver_notification_log(log)


def _notify_mentions(session, change_id: int, actor: str, text_value: str) -> None:
    usernames = _extract_mentions(text_value or "")
    if not usernames:
        return
    recipients: List[str] = []
    for uname in usernames:
        u = _active_user_by_username(session, uname)
        if u and u.email and u.username != actor:
            recipients.append(u.email)
    subject, body = _render_notification(
        "mention",
        {
            "change_id": change_id,
            "actor": actor,
            "text": text_value,
        },
    )
    log = _create_notification_log(
        session,
        event_type="mention",
        created_by=actor,
        recipients=recipients,
        subject=subject,
        body=body,
        context={"change_id": change_id, "mentions": usernames},
    )
    _deliver_notification_log(log)


_SAFE_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")


def _quote_ident(name: str) -> str:
    if not _SAFE_IDENT_RE.match(name or ""):
        raise ValueError(f"Unsafe identifier: {name}")
    return f'"{name}"'


def _qualified_ident(schema: str, name: str) -> str:
    return f"{_quote_ident(schema)}.{_quote_ident(name)}"


def _build_table_ddl(session, schema: str, name: str) -> str:
    cols = session.execute(
        text(
            """
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default
            FROM information_schema.columns c
            WHERE c.table_schema = :schema AND c.table_name = :name
            ORDER BY c.ordinal_position
            """
        ),
        {"schema": schema, "name": name},
    ).mappings().all()
    if not cols:
        return f"-- No columns found for {schema}.{name}"
    constraints = session.execute(
        text(
            """
            SELECT
                tc.constraint_name,
                tc.constraint_type,
                pg_get_constraintdef(pg_constraint.oid) AS constraint_def
            FROM information_schema.table_constraints tc
            JOIN pg_namespace ns ON ns.nspname = tc.table_schema
            JOIN pg_class cls ON cls.relname = tc.table_name AND cls.relnamespace = ns.oid
            JOIN pg_constraint ON pg_constraint.conrelid = cls.oid
                AND pg_constraint.conname = tc.constraint_name
            WHERE tc.table_schema = :schema AND tc.table_name = :name
            ORDER BY tc.constraint_name
            """
        ),
        {"schema": schema, "name": name},
    ).mappings().all()
    lines = [f"CREATE TABLE {_qualified_ident(schema, name)} ("]
    column_lines = []
    for col in cols:
        line = f"    {_quote_ident(col['column_name'])} {col['data_type']}"
        if col["column_default"] is not None:
            line += f" DEFAULT {col['column_default']}"
        if col["is_nullable"] == "NO":
            line += " NOT NULL"
        column_lines.append(line)
    for c in constraints:
        c_line = f"    CONSTRAINT {_quote_ident(c['constraint_name'])} {c['constraint_def']}"
        column_lines.append(c_line)
    lines.append(",\n".join(column_lines))
    lines.append(");")
    return "\n".join(lines)


def _format_db_error(exc: Exception) -> Dict:
    out = {
        "message": str(exc),
        "type": exc.__class__.__name__,
    }
    orig = getattr(exc, "orig", None)
    if orig is not None:
        diag = getattr(orig, "diag", None)
        if diag is not None:
            primary = getattr(diag, "message_primary", None)
            detail = getattr(diag, "message_detail", None)
            position = getattr(diag, "statement_position", None)
            if primary:
                out["primary"] = primary
            if detail:
                out["detail"] = detail
            if position:
                out["position"] = position
    return out


def _collect_template_ids_from_domains(domains: List[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    for domain in domains or []:
        for skill in domain.get("skills") or []:
            for action in skill.get("actions") or []:
                tid = (action.get("template_id") or "").strip()
                if tid:
                    out.add(tid)
                for sub in action.get("subactions") or []:
                    stid = (sub.get("template_id") or "").strip()
                    if stid:
                        out.add(stid)
    return out


def _build_tree_edit_warnings(current_unified: Dict[str, Any], edited_domains: List[Dict[str, Any]]) -> Dict[str, Any]:
    current_templates = _collect_template_ids_from_domains(current_unified.get("domains") or [])
    edited_templates = _collect_template_ids_from_domains(edited_domains or [])
    removed_templates = sorted(current_templates - edited_templates)
    template_defs = current_unified.get("action_templates") or {}
    removed_literature: Set[str] = set()
    for tid in removed_templates:
        t = template_defs.get(tid) or {}
        for lit_id in t.get("resource_ids") or []:
            if lit_id:
                removed_literature.add(str(lit_id))
    return {
        "removed_template_ids": removed_templates,
        "removed_template_count": len(removed_templates),
        "affected_literature_ids": sorted(removed_literature),
        "affected_literature_count": len(removed_literature),
    }


def _literature_dir():
    """Каталог для скачанной литературы (data/library)."""
    cfg = get_meta()
    rel = cfg.get('literature_dir') or cfg.get('library_dir') or 'data/library'
    path = os.path.join(BASE_DIR, rel) if not os.path.isabs(rel) else rel
    os.makedirs(path, exist_ok=True)
    return path


def _invalidate_caches():
    """Сброс кэшей: при перезапуске или изменении источника данные перезагружаются (autoscale)."""
    global _matrix, _meta, _tree, _current_source_file
    _matrix = None
    _meta = None
    _tree = None
    _current_source_file = None
    invalidate_metadata_cache()


def _ensure_db_schema():
    global _admin_seed_checked
    if _is_db_mode():
        Base.metadata.create_all(bind=ENGINE)
        if not _admin_seed_checked:
            _ensure_admin_seed()
            _admin_seed_checked = True


def _path_config():
    """Только настройки путей (без мета из источника). Используется до загрузки данных."""
    return load_app_config()


def _source_dir_path():
    """Абсолютный путь к каталогу источников (source_dir из настроек)."""
    cfg = _meta if _meta is not None else _path_config()
    rel = cfg.get("source_dir") or "data/sources"
    path = os.path.join(BASE_DIR, rel) if not os.path.isabs(rel) else rel
    return path


def _checkpoint_path():
    """Абсолютный путь к файлу чекпоинта."""
    cfg = _meta if _meta is not None else _path_config()
    rel = cfg.get("checkpoint_file") or "data/checkpoint.yaml"
    path = os.path.join(BASE_DIR, rel) if not os.path.isabs(rel) else rel
    return path


def _list_source_files():
    """Список имён файлов-источников в source_dir (JSON, YAML, Excel)."""
    allowed = (".json", ".yaml", ".yml", ".xlsx", ".xls")
    src_dir = _source_dir_path()
    if not os.path.isdir(src_dir):
        return []
    return sorted(
        f for f in os.listdir(src_dir)
        if os.path.isfile(os.path.join(src_dir, f)) and f.lower().endswith(allowed)
    )


def _current_source_for_backup() -> str:
    """Имя текущего файла-источника для бэкапа (чекпоинт или default)."""
    global _current_source_file
    if _is_db_mode():
        return ""
    if _current_source_file:
        return _current_source_file
    cfg = _path_config()
    checkpoint = load_checkpoint(PathLib(_checkpoint_path()))
    if checkpoint and checkpoint.get("source_file"):
        return checkpoint["source_file"]
    default = cfg.get("default_source")
    candidates = _list_source_files()
    if default and default in candidates:
        return default
    return candidates[0] if candidates else ""


def _create_version_backup(change_type: str, note: str = "") -> str:
    """
    Создаёт версионный бэкап перед изменением.
    Также гарантирует наличие stable-состояния.
    """
    if _is_db_mode():
        return ""
    source_file = _current_source_for_backup()
    if not source_file:
        return ""
    base = PathLib(BASE_DIR)
    cfg = base / "config"
    src = PathLib(_source_dir_path())
    cp = _checkpoint_path()
    ensure_stable_backup(
        base_dir=base,
        config_dir=cfg,
        source_dir=src,
        source_filename=source_file,
        checkpoint_path=cp,
    )
    backup_id = create_backup(
        base_dir=base,
        config_dir=cfg,
        source_dir=src,
        source_filename=source_file,
        checkpoint_path=cp,
        change_type=change_type,
        note=note,
    )
    return backup_id or ""


def _ensure_data_loaded(force_source_filename: str = None):
    """
    Загружает данные из единого источника: при совпадении с чекпоинтом — из чекпоинта;
    иначе — из файла (структура + мета), пересборка дерева и сохранение чекпоинта.
    Мета (шаблоны, литература, стек и т.д.) берётся только из этого источника.
    """
    global _matrix, _tree, _meta, _current_source_file
    if _matrix is not None and _tree is not None and not force_source_filename:
        return
    if not _is_db_mode():
        raise RuntimeError("Runtime is DB-only; file source loading is disabled")
    _ensure_db_schema()
    path_cfg = _path_config()
    with db_session() as session:
        unified = load_unified_from_db(session, literature=load_literature_map())
    domains = unified.get("domains") or []
    _matrix = {"domains": domains}
    _tree = build_tree_from_matrix_data(_matrix)
    meta_from_source = {k: unified.get(k, {} if k != "action_examples" else []) for k in META_KEYS}
    _meta = {**path_cfg, **meta_from_source}
    _current_source_file = "db://postgres"
    return
    path_cfg = _path_config()
    source_dir = _source_dir_path()
    checkpoint_path = _checkpoint_path()
    os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
    os.makedirs(source_dir, exist_ok=True)

    checkpoint = load_checkpoint(PathLib(checkpoint_path))
    if force_source_filename:
        source_file = force_source_filename
    elif checkpoint and checkpoint.get("source_file"):
        source_file = checkpoint["source_file"]
    else:
        default = path_cfg.get("default_source")
        candidates = _list_source_files()
        source_file = default if default and default in candidates else (candidates[0] if candidates else None)

    if not source_file:
        _matrix = {"domains": []}
        _tree = []
        _meta = {**path_cfg, **{k: {} if k != "action_examples" else [] for k in META_KEYS}}
        return

    source_path = os.path.join(source_dir, source_file)
    if not os.path.isfile(source_path):
        _matrix = {"domains": []}
        _tree = []
        _meta = {**path_cfg, **{k: {} if k != "action_examples" else [] for k in META_KEYS}}
        return

    # Совпадает ли источник с чекпоинтом? Используем чекпоинт только если в нём есть полный meta (action_templates, literature).
    meta_from_checkpoint = (checkpoint or {}).get("meta")
    if isinstance(meta_from_checkpoint, dict):
        pass
    else:
        meta_from_checkpoint = {}
    has_meta = bool(meta_from_checkpoint.get("action_templates") or meta_from_checkpoint.get("literature"))
    if (
        checkpoint
        and checkpoint.get("source_file") == source_file
        and source_matches_checkpoint(PathLib(source_path), checkpoint)
        and has_meta
    ):
        _matrix = checkpoint.get("matrix") or {"domains": []}
        _tree = checkpoint.get("tree") or []
        _meta = {**path_cfg, **meta_from_checkpoint}
        _current_source_file = source_file
        return

    # Перезагрузка из единого источника: структура + мета в одном файле
    try:
        unified = load_unified_source(source_path)
    except Exception as e:
        print(f"Ошибка загрузки источника {source_path}: {e}")
        _matrix = {"domains": []}
        _tree = []
        _meta = {**path_cfg, **{k: {} if k != "action_examples" else [] for k in META_KEYS}}
        return
    domains = unified.get("domains") or []
    _matrix = {"domains": domains}
    _tree = build_tree_from_matrix_data(_matrix)
    meta_from_source = {k: unified.get(k, {} if k != "action_examples" else []) for k in META_KEYS}
    _meta = {**path_cfg, **meta_from_source}
    source_hash = get_source_content_hash(PathLib(source_path))
    checkpoint_data = build_checkpoint_data(_tree, _matrix, meta_from_source, source_file, source_hash)
    save_checkpoint(PathLib(checkpoint_path), checkpoint_data, use_yaml=checkpoint_path.lower().endswith((".yaml", ".yml")))
    _current_source_file = source_file

# ----- Вспомогательные функции для генерации иконок и цветов -----
DOMAIN_ICONS = [
    "database", "cloud", "code-branch", "check-circle", "users",
    "server", "chart-line", "cube", "cogs", "file-alt"
]
SKILL_ICONS = [
    "cube", "bolt", "layer-group", "fire", "clock", "python",
    "sync-alt", "chart-line", "check-double", "project-diagram", "file-alt",
    "comments", "tasks", "chalkboard-teacher"
]

def get_domain_icon(domain_name, index):
    return DOMAIN_ICONS[index % len(DOMAIN_ICONS)]

def get_skill_icon(skill_name, index):
    return SKILL_ICONS[index % len(SKILL_ICONS)]

def string_to_hsl(text, s=70, l=60):
    hash_obj = hashlib.md5(text.encode())
    hue = int(hash_obj.hexdigest()[:6], 16) % 360
    return f"hsl({hue}, {s}%, {l}%)"

def get_domain_color(domain_name):
    return string_to_hsl(domain_name, s=70, l=60)

def get_skill_color(skill_name, domain_color, skill_index):
    match = re.match(r'hsl\((\d+), (\d+)%, (\d+)%\)', domain_color)
    if match:
        hue = (int(match.group(1)) + skill_index * 30) % 360
        s = int(match.group(2))
        l = int(match.group(3))
        return f"hsl({hue}, {s}%, {l}%)"
    return domain_color

# ----------------------------------------------------------------

def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Файл {path} не найден. Используется значение по умолчанию.")
        return default
    except Exception as e:
        print(f"Ошибка загрузки {path}: {e}")
        return default

def get_meta():
    """Конфиг: пути из settings + данные из источника (текст) + стили/инструменты из config/metadata.yaml."""
    global _meta
    if _meta is None:
        _meta = _path_config()
        _ensure_data_loaded()
    metadata = load_metadata()
    out = {
        **_meta,
        "stack_labels": metadata.get("stack_labels", {}),
        "tools_patterns": metadata.get("tools_patterns", {}),
        "tools_groups": metadata.get("tools_groups", {}),
    }
    out.setdefault("action_templates", {})
    out.setdefault("literature", {})
    out.setdefault("action_examples", [])
    out.setdefault("ui_config", {})
    return out


def get_matrix():
    """Структура матрицы из чекпоинта или файла-источника (source_dir). Сверка по хешу при каждой загрузке."""
    _ensure_data_loaded()
    return _matrix if _matrix is not None else {"domains": []}


def get_tree():
    """Дерево матрицы (autoscale по структуре источника). Листья — узлы без children."""
    _ensure_data_loaded()
    return _tree if _tree is not None else []


def _expected_leaf_paths_from_matrix(matrix: Dict) -> list:
    """Ожидаемые leaf-path по структуре матрицы (для проверки автоскейла)."""
    out = []
    domains = (matrix or {}).get("domains") or []
    for di, d in enumerate(domains):
        for si, s in enumerate(d.get("skills") or []):
            for ai, a in enumerate(s.get("actions") or []):
                sub = a.get("subactions") or []
                if sub:
                    for subi, _ in enumerate(sub):
                        out.append(f"{di}/{si}/{ai}/{subi}")
                else:
                    out.append(f"{di}/{si}/{ai}")
    return out

def save_meta(meta_dict):
    """Сохраняет метаданные в единый источник (текущий файл в source_dir). Обновляет чекпоинт при следующей загрузке."""
    global _meta
    path_cfg = _path_config()
    _meta = {**path_cfg, **meta_dict}
    if not _is_db_mode():
        raise RuntimeError("Runtime is DB-only; file source saving is disabled")
    _ensure_db_schema()
    with db_session() as session:
        unified = load_unified_from_db(session, literature=meta_dict.get("literature", {}) or {})
        unified["domains"] = (get_matrix() or {}).get("domains", [])
        for k in META_KEYS:
            unified[k] = meta_dict.get(k, {} if k != "action_examples" else [])
        replace_unified_in_db(session, unified)
    for lit_id, item in (meta_dict.get("literature") or {}).items():
        upsert_literature_item(str(lit_id), item or {})
    _invalidate_caches()

def slugify(text):
    if not text:
        return ''
    return re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-')

def find_free_port(start_port=5000, max_attempts=10):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    return None

def enrich_action(action_obj, template, meta):
    """Обогащает действие: стек по stack_refs из шаблона (стили из config), инструменты — по паттернам в тексте."""
    stack_labels = meta.get("stack_labels", {})
    action_examples = meta.get("action_examples", [])
    literature = meta.get("literature", {})
    tools_patterns = meta.get("tools_patterns", {})
    tools_groups = meta.get("tools_groups", {})

    if not template:
        return {
            "stack_labels": [],
            "tools": [],
            "examples": [],
            "literature": [],
        }

    stack_refs = template.get("stack_refs", [])
    resolved_stack = [{"key": ref, **stack_labels[ref]} for ref in stack_refs if ref in stack_labels]

    leaf_text = (action_obj.get("text") or action_obj.get("name") or "")
    template_text = " ".join(template.get("minimal_requirements") or []) + " " + " ".join(template.get("antipatterns") or [])
    resolved_tools = get_tools_for_text(leaf_text, template_text, tools_patterns, tools_groups)

    examples_refs = template.get("examples_refs", [])
    examples_by_id = {e['id']: e for e in action_examples if 'id' in e}
    resolved_examples = []
    for ref in examples_refs:
        if ref in examples_by_id:
            ex = examples_by_id[ref]
            code = ex.get('code', '').replace('<', '&lt;').replace('>', '&gt;')
            resolved_examples.append({
                'html': f'<pre><code class="language-{ex.get("language", "sql")}">{code}</code></pre>',
                'title': ex.get('title', '')
            })
    
    resource_ids = template.get('resource_ids', [])
    resolved_literature = []
    for rid in resource_ids:
        if rid in literature:
            resolved_literature.append({"id": rid, **literature[rid]})
    
    return {
        'stack_labels': resolved_stack,
        'tools': resolved_tools,
        'examples': resolved_examples,
        'literature': resolved_literature
    }

def build_description(action_obj, template, domain, skill, meta):
    minimal = template.get('minimal_requirements', [])
    antipatterns = template.get('antipatterns', [])
    ui = meta.get('ui_config', {})
    titles = ui.get('section_titles', {})

    if not minimal and not antipatterns:
        return f"""
            <h4>📋 Действие в контексте {domain['name']}</h4>
            <p><strong>{action_obj['text']}</strong> относится к навыку <strong>{skill['name']}</strong>.</p>
            <p>Описание пока не добавлено.</p>
        """

    html = f"<h4>📋 {template.get('name', 'Действие')}</h4>"
    if minimal:
        html += f"<h5>✅ {titles.get('minimal_requirements', 'Минимальный объем')}:</h5><ul>"
        for req in minimal:
            html += f"<li>{req}</li>"
        html += "</ul>"
    if antipatterns:
        html += f"<h5>⚠️ {titles.get('antipatterns', 'Антипаттерны')}:</h5><ul>"
        for anti in antipatterns:
            html += f"<li>{anti}</li>"
        html += "</ul>"
    html += f"<p><small>Контекст: <strong>{domain['name']}</strong> → <strong>{skill['name']}</strong></small></p>"
    return html

def resolve_leaf_by_path(path_str):
    """
    По path (например "0/1/2" или "0/1/2/0") возвращает (domain, skill, action, parent_action_text)
    для рендера страницы листа. action — dict с text, template_id; domain/skill — dict с name, description у skill.
    Если узел не найден или не лист — возвращает None.
    """
    try:
        path = [int(x) for x in path_str.strip("/").split("/") if x.strip()]
    except (ValueError, AttributeError):
        return None
    if not path:
        return None
    tree = get_tree()
    node = get_node_by_path(tree, path)
    if not node or node.get("children"):
        return None
    ancestors = get_ancestors(tree, path)
    if len(ancestors) < 2:
        return None
    domain = {"name": ancestors[0].get("name", "")}
    skill = {"name": ancestors[1].get("name", ""), "description": ancestors[1].get("description", "")}
    action = {
        "text": node.get("name", ""),
        "template_id": node.get("template_id"),
        "level_tag": node.get("level_tag"),
        "review_questions": node.get("review_questions", []),
    }
    parent_action_text = ancestors[2].get("name", "") if len(ancestors) > 3 else None
    return (domain, skill, action, parent_action_text)

def find_related_skills(data, domain_idx, skill_idx, action_idx):
    related = []
    try:
        current_domain = data['domains'][domain_idx]
        current_skill = current_domain['skills'][skill_idx]
        current_action = current_skill['actions'][action_idx]
        current_text = current_action.get('text', '').lower()
        words = set(re.findall(r'\w+', current_text))
        stop_words = {'и', 'в', 'на', 'с', 'для', 'по', 'от', 'за', 'через', 'при', 'из', 'у', 'к', 'о', 'об'}
        words = words - stop_words

        for di, d in enumerate(data['domains']):
            for si, s in enumerate(d['skills']):
                if di == domain_idx and si == skill_idx:
                    continue
                for ai, a in enumerate(s['actions']):
                    a_text = a.get('text', '').lower()
                    a_words = set(re.findall(r'\w+', a_text)) - stop_words
                    common = words & a_words
                    if len(common) >= 2:
                        related.append({
                            "domain_name": d['name'],
                            "skill_name": s['name'],
                            "action": a_text[:60] + "..." if len(a_text) > 60 else a_text,
                            "url": f"/action/{di}/{si}/{ai}"
                        })
                        if len(related) >= 5:
                            break
                if len(related) >= 5:
                    break
    except Exception as e:
        print(f"Ошибка поиска связанных навыков: {e}")
    return related

# РЕГИСТРАЦИЯ ФИЛЬТРОВ JINJA2
app.jinja_env.filters['slugify'] = slugify

@app.template_filter('domain_icon')
def domain_icon_filter(domain_name, index):
    return get_domain_icon(domain_name, index)

@app.template_filter('skill_icon')
def skill_icon_filter(skill_name, index):
    return get_skill_icon(skill_name, index)

@app.template_filter('domain_color')
def domain_color_filter(domain_name):
    return get_domain_color(domain_name)

@app.template_filter('skill_color')
def skill_color_filter(skill_name, domain_color, index):
    return get_skill_color(skill_name, domain_color, index)

@app.context_processor
def inject_globals():
    current_actor, current_role = _extract_actor_role()
    domains = (get_matrix() or {}).get("domains", [])
    sidebar_domains = []
    for i, d in enumerate(domains):
        domain_color = get_domain_color(d.get("name", ""))
        skills_list = []
        for si, s in enumerate(d.get("skills", [])):
            actions = s.get("actions", [])
            skills_list.append({
                "name": s.get("name", ""),
                "index": si,
                "color": get_skill_color(s.get("name", ""), domain_color, si),
                "icon": get_skill_icon(s.get("name", ""), si),
                "actions_count": len(actions),
            })
        sidebar_domains.append({
            "name": d.get("name", ""),
            "index": i,
            "color": domain_color,
            "icon": get_domain_icon(d.get("name", ""), i),
            "skills_count": len(skills_list),
            "skills": skills_list,
        })
    return {
        'ui_config': get_meta().get('ui_config', {}),
        'sidebar_domains': sidebar_domains,
        'get_domain_icon': get_domain_icon,
        'get_skill_icon': get_skill_icon,
        'get_domain_color': get_domain_color,
        'get_skill_color': get_skill_color,
        'author_name': AUTHOR_NAME,
        'author_telegram': AUTHOR_TELEGRAM,
        'repository_url': REPOSITORY_URL,
        'current_actor': current_actor,
        'current_role': current_role,
        'is_authenticated': bool(session.get("authenticated")),
    }

# ----- ОСНОВНЫЕ МАРШРУТЫ -----


@app.route('/login', methods=['GET', 'POST'])
def login():
    _ensure_db_schema()
    next_url = (request.args.get("next") or request.form.get("next") or "/").strip() or "/"
    if session.get("authenticated") and _is_safe_next_url(next_url):
        return redirect(next_url)
    if request.method == 'GET':
        return render_template('login.html', next_url=next_url, auth_error=None)

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    if not username or not password:
        return render_template('login.html', next_url=next_url, auth_error="Введите логин и пароль"), 400

    user = _load_user(username)
    if not user or not user.is_active or not user.password_hash:
        return render_template('login.html', next_url=next_url, auth_error="Неверный логин или пароль"), 401
    if not check_password_hash(user.password_hash, password):
        return render_template('login.html', next_url=next_url, auth_error="Неверный логин или пароль"), 401

    session["authenticated"] = True
    session["actor"] = username
    session["role"] = user.role
    session["must_change_password"] = bool(user.must_change_password)
    if user.must_change_password and request.path != "/account/password":
        return redirect(url_for("account_password"))
    if not _is_safe_next_url(next_url):
        next_url = "/"
    return redirect(next_url)


@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.before_request
def enforce_authentication():
    if not AUTH_REQUIRED:
        return None
    if request.path.startswith("/static/") or request.path.startswith("/library/"):
        return None
    if request.path in ("/api/schema",):
        return None
    if request.path in ("/login", "/logout"):
        return None
    if session.get("authenticated"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Authentication required"}), 401
    return redirect(url_for("login", next=request.path))


@app.before_request
def enforce_password_change():
    if not session.get("authenticated"):
        return None
    must_change = bool(session.get("must_change_password"))
    if not must_change:
        return None
    allowed = {
        "account_password",
        "logout",
        "login",
        "static",
        "proxy_health",
    }
    endpoint = request.endpoint or ""
    if endpoint in allowed or endpoint.startswith("api_schema"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Password change required"}), 403
    return redirect(url_for("account_password"))


@app.route('/account', methods=['GET'])
def account_page():
    auth, auth_err = _require_authenticated()
    if auth_err:
        return redirect(url_for("login", next=request.path))
    user = _load_user(auth["actor"])
    if not user:
        session.clear()
        return redirect(url_for("login", next=request.path))
    return render_template("account.html", profile={
        "username": user.username,
        "full_name": user.full_name or "",
        "email": user.email or "",
        "role": user.role,
        "must_change_password": bool(user.must_change_password),
    })


@app.route('/account/profile', methods=['POST'])
def account_update_profile():
    auth, auth_err = _require_authenticated()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True) or request.form
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    if email and "@" not in email:
        return jsonify({"ok": False, "error": "Invalid email"}), 400
    with db_session() as db:
        user = db.execute(select(User).where(User.username == auth["actor"])).scalars().first()
        if not user:
            return jsonify({"ok": False, "error": "User not found"}), 404
        user.full_name = full_name
        user.email = email
    return jsonify({"ok": True})


@app.route('/account/password', methods=['GET', 'POST'])
def account_password():
    auth, auth_err = _require_authenticated()
    if auth_err:
        return redirect(url_for("login", next=request.path))
    if request.method == "GET":
        return render_template("account_password.html", auth_error=None, must_change=bool(session.get("must_change_password")))

    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    if len(new_password) < 10:
        return render_template("account_password.html", auth_error="Новый пароль слишком короткий (минимум 10 символов)", must_change=True), 400
    if new_password != confirm_password:
        return render_template("account_password.html", auth_error="Подтверждение пароля не совпадает", must_change=True), 400

    with db_session() as db:
        user = db.execute(select(User).where(User.username == auth["actor"])).scalars().first()
        if not user:
            session.clear()
            return redirect(url_for("login", next="/"))
        if not check_password_hash(user.password_hash, current_password):
            return render_template("account_password.html", auth_error="Текущий пароль неверный", must_change=bool(user.must_change_password)), 401
        user.password_hash = generate_password_hash(new_password)
        user.must_change_password = False

    session["must_change_password"] = False
    return redirect(url_for("account_page"))


@app.route('/')
def index():
    """Стартовая страница — дашборд."""
    matrix = get_matrix() or {}
    domains = matrix.get("domains") or []
    total_skills = sum(len(d.get("skills", [])) for d in domains)
    total_actions = 0
    for d in domains:
        for s in d.get("skills", []):
            total_actions += len(s.get("actions", []))
    return render_template('home.html', domains=domains, stats={
        "domains": len(domains),
        "skills": total_skills,
        "actions": total_actions,
    })


@app.route('/matrix')
def matrix_view():
    """Матрица — сетка карточек доменов."""
    return render_template('matrix.html', domains=get_matrix()['domains'])


@app.route('/domain/<int:domain_idx>')
def domain_view(domain_idx):
    """Вью домена: дерево элементов слева направо."""
    matrix = get_matrix()
    domains = (matrix or {}).get("domains") or []
    if domain_idx < 0 or domain_idx >= len(domains):
        return render_template('404.html'), 404
    domain = domains[domain_idx]
    domain_color = get_domain_color(domain.get("name", ""))
    domain_icon = get_domain_icon(domain.get("name", ""), domain_idx)
    domain_data = {
        "index": domain_idx,
        "name": domain.get("name", ""),
        "color": domain_color,
        "icon": domain_icon,
        "skills": []
    }
    for si, s in enumerate(domain.get("skills", [])):
        skill_color = get_skill_color(s.get("name", ""), domain_color, si)
        skill_icon = get_skill_icon(s.get("name", ""), si)
        skill_data = {
            "index": si,
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "color": skill_color,
            "icon": skill_icon,
            "actions": []
        }
        for ai, a in enumerate(s.get("actions", [])):
            action_data = {
                "index": ai,
                "text": a.get("text", ""),
                "template_id": a.get("template_id"),
                "level_tag": a.get("level_tag"),
                "review_questions": a.get("review_questions", []),
                "subactions": []
            }
            for subi, sub in enumerate(a.get("subactions", [])):
                action_data["subactions"].append({
                    "index": subi,
                    "text": sub.get("text", ""),
                    "level_tag": sub.get("level_tag"),
                    "review_questions": sub.get("review_questions", []),
                    "leaf_path": f"{domain_idx}/{si}/{ai}/{subi}"
                })
            if not action_data["subactions"]:
                action_data["leaf_path"] = f"{domain_idx}/{si}/{ai}"
            skill_data["actions"].append(action_data)
        domain_data["skills"].append(skill_data)
    return render_template('domain_view.html', domain=domain_data, current_domain_index=domain_idx, focus_skill=False)


@app.route('/domain/<int:domain_idx>/skill/<int:skill_idx>')
def domain_skill_view(domain_idx, skill_idx):
    """Вью навыка: дерево элементов (зависимости от выбранного в сайдбаре)."""
    matrix = get_matrix()
    domains = (matrix or {}).get("domains") or []
    if domain_idx < 0 or domain_idx >= len(domains):
        return render_template('404.html'), 404
    domain = domains[domain_idx]
    skills = domain.get("skills", [])
    if skill_idx < 0 or skill_idx >= len(skills):
        return render_template('404.html'), 404
    skill = skills[skill_idx]
    domain_color = get_domain_color(domain.get("name", ""))
    domain_icon = get_domain_icon(domain.get("name", ""), domain_idx)
    skill_color = get_skill_color(skill.get("name", ""), domain_color, skill_idx)
    skill_icon = get_skill_icon(skill.get("name", ""), skill_idx)
    domain_data = {
        "index": domain_idx,
        "name": domain.get("name", ""),
        "color": domain_color,
        "icon": domain_icon,
        "skills": [{
            "index": skill_idx,
            "name": skill.get("name", ""),
            "description": skill.get("description", ""),
            "color": skill_color,
            "icon": skill_icon,
            "actions": []
        }]
    }
    for ai, a in enumerate(skill.get("actions", [])):
        action_data = {
            "index": ai,
            "text": a.get("text", ""),
            "template_id": a.get("template_id"),
            "level_tag": a.get("level_tag"),
            "review_questions": a.get("review_questions", []),
            "subactions": []
        }
        for subi, sub in enumerate(a.get("subactions", [])):
            action_data["subactions"].append({
                "index": subi,
                "text": sub.get("text", ""),
                "level_tag": sub.get("level_tag"),
                "review_questions": sub.get("review_questions", []),
                "leaf_path": f"{domain_idx}/{skill_idx}/{ai}/{subi}"
            })
        if not action_data["subactions"]:
            action_data["leaf_path"] = f"{domain_idx}/{skill_idx}/{ai}"
        domain_data["skills"][0]["actions"].append(action_data)
    return render_template('domain_view.html', domain=domain_data, current_domain_index=domain_idx, current_skill_index=skill_idx, focus_skill=True)


@app.route('/api/matrix')
def api_matrix():
    return jsonify(get_matrix())

@app.route('/api/tree')
def api_tree():
    """Дерево матрицы (корень → листья), уровни определяются автоматически."""
    return jsonify(get_tree())

def _leaf_breadcrumb(tree_nodes, path: list) -> str:
    """Строка «Домен → Навык → Действие» для листа по path."""
    if not path:
        return ""
    parts = []
    nodes = tree_nodes
    for i, idx in enumerate(path):
        idx = int(idx)
        if idx < 0 or idx >= len(nodes):
            break
        node = nodes[idx]
        parts.append(node.get("name", ""))
        if i + 1 < len(path) and node.get("children"):
            nodes = node["children"]
    return " → ".join(p for p in parts if p)


@app.route('/api/tree-for-link')
def api_tree_for_link():
    """Дерево для модала привязки: домены → навыки → действия → листья (с path, template_id)."""
    data = get_matrix()
    domains = (data or {}).get("domains", [])
    meta = get_meta()
    templates = meta.get("action_templates", {})
    out = []
    for di, d in enumerate(domains):
        domain_node = {"name": d.get("name", ""), "skills": []}
        for si, s in enumerate(d.get("skills", [])):
            skill_node = {"name": s.get("name", ""), "actions": []}
            for ai, a in enumerate(s.get("actions", [])):
                if a.get("subactions"):
                    for subi, sub in enumerate(a["subactions"]):
                        path = [di, si, ai, subi]
                        node = get_node_by_path(get_tree(), path)
                        tid = (node or {}).get("template_id")
                        if tid and tid in templates:
                            skill_node["actions"].append({
                                "name": sub.get("text", ""),
                                "path": path,
                                "path_str": "/".join(map(str, path)),
                                "template_id": tid,
                            })
                else:
                    path = [di, si, ai]
                    node = get_node_by_path(get_tree(), path)
                    tid = (node or {}).get("template_id")
                    if tid and tid in templates:
                        skill_node["actions"].append({
                            "name": a.get("text", ""),
                            "path": path,
                            "path_str": "/".join(map(str, path)),
                            "template_id": tid,
                        })
            if skill_node["actions"]:
                domain_node["skills"].append(skill_node)
        if domain_node["skills"]:
            out.append(domain_node)
    return jsonify(out)


@app.route('/api/leaves')
def api_leaves():
    """Список всех листьев с path, template_id, url и иерархией (домен → навык → дерево)."""
    tree = get_tree()
    hierarchy = request.args.get("hierarchy", "").lower() in ("1", "true", "yes")
    leaves = collect_leaves(tree)
    out = []
    for n in leaves:
        p = n.get("path", [])
        item = {
            "path": p,
            "name": n.get("name"),
            "url": path_to_url(p),
            "template_id": n.get("template_id"),
        }
        if hierarchy:
            item["breadcrumb"] = _leaf_breadcrumb(tree, p)
        out.append(item)
    return jsonify(out)

@app.route('/api/leaf-literature')
def api_leaf_literature():
    """Мапа path_str -> список названий привязанной литературы для отображения в матрице."""
    meta = get_meta()
    templates = meta.get("action_templates", {})
    literature = meta.get("literature", {})
    tree = get_tree()
    leaves = collect_leaves(tree)
    out = {}
    for n in leaves:
        p = n.get("path", [])
        tid = n.get("template_id")
        if not tid or tid not in templates:
            continue
        rids = templates[tid].get("resource_ids", [])
        titles = [literature.get(rid, {}).get("title", rid) for rid in rids if rid in literature]
        if titles:
            path_str = "/".join(str(x) for x in p)
            out[path_str] = titles
    return jsonify(out)


@app.route('/api/meta')
def api_meta():
    return jsonify(get_meta())

@app.route('/graph')
def graph():
    return render_template('graph.html')

@app.route('/api/graph-data')
def graph_data():
    data = get_matrix()
    nodes = [{"id": "root", "name": "Middle Data Engineer", "type": "root", "level": 0}]
    links = []
    
    for di, d in enumerate(data['domains']):
        domain_color = get_domain_color(d['name'])
        domain_icon = get_domain_icon(d['name'], di)
        did = f"d{di}"
        nodes.append({
            "id": did,
            "name": d['name'],
            "type": "domain",
            "level": 1,
            "color": domain_color,
            "icon": domain_icon
        })
        links.append({"source": "root", "target": did})
        
        for si, s in enumerate(d['skills']):
            skill_color = get_skill_color(s['name'], domain_color, si)
            skill_icon = get_skill_icon(s['name'], si)
            sid = f"d{di}s{si}"
            nodes.append({
                "id": sid,
                "name": s['name'],
                "type": "skill",
                "level": 2,
                "domain_idx": di,
                "skill_idx": si,
                "color": skill_color,
                "icon": skill_icon,
                "description": s.get('description', '')
            })
            links.append({"source": did, "target": sid})
            
            for ai, a in enumerate(s['actions']):
                aid = f"d{di}s{si}a{ai}"
                leaf_path = f"{di}/{si}/{ai}"
                nodes.append({
                    "id": aid,
                    "name": a['text'],
                    "full_name": a['text'],
                    "type": "action",
                    "level": 3,
                    "domain_idx": di,
                    "skill_idx": si,
                    "action_idx": ai,
                    "leaf_path": leaf_path if 'subactions' not in a else None,
                    "level_tag": a.get("level_tag"),
                })
                links.append({"source": sid, "target": aid})
                
                if 'subactions' in a:
                    for sub_idx, sub in enumerate(a['subactions']):
                        subid = f"d{di}s{si}a{ai}sub{sub_idx}"
                        nodes.append({
                            "id": subid,
                            "name": sub['text'],
                            "full_name": sub['text'],
                            "type": "subaction",
                            "level": 4,
                            "domain_idx": di,
                            "skill_idx": si,
                            "action_idx": ai,
                            "sub_idx": sub_idx,
                            "leaf_path": f"{di}/{si}/{ai}/{sub_idx}",
                            "level_tag": sub.get("level_tag"),
                        })
                        links.append({"source": aid, "target": subid, "label": "содержит"})
    
    return jsonify({"nodes": nodes, "links": links})

# ----- Универсальный маршрут листа (произвольная глубина) -----

@app.route('/leaf/<path:path>')
def leaf_page(path):
    """Страница листа по path (например 0/1/2 или 0/1/2/0)."""
    resolved = resolve_leaf_by_path(path)
    if not resolved:
        abort(404)
    domain, skill, action, parent_action_text = resolved
    path_parts = path.strip("/").split("/")
    di = int(path_parts[0]) if len(path_parts) > 0 else 0
    si = int(path_parts[1]) if len(path_parts) > 1 else 0
    ai = int(path_parts[2]) if len(path_parts) > 2 else 0
    sub_idx = int(path_parts[3]) if len(path_parts) > 3 else None
    domain_color = get_domain_color(domain["name"])
    skill_color = get_skill_color(skill["name"], domain_color, si)
    ctx = {
        "domain": domain,
        "skill": skill,
        "action": action,
        "action_text": action["text"],
        "di": di, "si": si, "ai": ai,
        "domain_color": domain_color,
        "skill_color": skill_color,
        "domain_icon": get_domain_icon(domain["name"], di),
        "skill_icon": get_skill_icon(skill["name"], si),
        "leaf_path": path,
    }
    if sub_idx is not None:
        ctx["sub_idx"] = sub_idx
        ctx["parent_action_text"] = parent_action_text
    return render_template("action_detail.html", **ctx)

@app.route('/api/leaf/<path:path>')
def leaf_api(path):
    """API листа: те же данные, что /api/action или /api/subaction."""
    resolved = resolve_leaf_by_path(path)
    if not resolved:
        return jsonify({"error": "Not found"}), 404
    domain, skill, action, _parent_action_text = resolved
    meta = get_meta()
    template_id = action.get("template_id")
    template = meta.get("action_templates", {}).get(template_id or "", {})
    if template.get("is_parent"):
        return jsonify({"error": "Node is not a leaf"}), 400
    enriched = enrich_action(action, template, meta)
    description = build_description(action, template, domain, skill, meta)
    path_parts = [int(x) for x in path.strip("/").split("/") if x.strip()]
    related = find_related_skills_by_path(path_parts) if len(path_parts) >= 3 else []
    return jsonify({
        "title": action["text"],
        "description": description,
        "examples": enriched["examples"],
        "tools": enriched["tools"],
        "stack_labels": enriched["stack_labels"],
        "literature": enriched["literature"],
        "level_tag": action.get("level_tag"),
        "review_questions": action.get("review_questions", []),
        "related_skills": related,
        "domain_color": get_domain_color(domain["name"]),
        "skill_color": get_skill_color(skill["name"], get_domain_color(domain["name"]), path_parts[1] if len(path_parts) > 1 else 0),
        "domain_icon": get_domain_icon(domain["name"], path_parts[0] if path_parts else 0),
        "skill_icon": get_skill_icon(skill["name"], path_parts[1] if len(path_parts) > 1 else 0),
        "leaf_path": path,
    })

def find_related_skills_by_path(path_parts):
    """По path листа возвращает связанные навыки (делегирует find_related_skills по di, si, ai)."""
    data = get_matrix()
    if "domains" not in data or len(path_parts) < 3:
        return []
    return find_related_skills(data, path_parts[0], path_parts[1], path_parts[2])

# ----- МАРШРУТЫ ДЛЯ ДЕЙСТВИЙ (обратная совместимость) -----

@app.route('/action/<int:di>/<int:si>/<int:ai>')
def action_page(di, si, ai):
    data = get_matrix()
    try:
        domain = data['domains'][di]
        skill = domain['skills'][si]
        action = skill['actions'][ai]
        domain_color = get_domain_color(domain['name'])
        skill_color = get_skill_color(skill['name'], domain_color, si)
        
        return render_template('action_detail.html',
                             domain=domain,
                             skill=skill,
                             action=action,
                             action_text=action['text'],
                             di=di, si=si, ai=ai,
                             domain_color=domain_color,
                             skill_color=skill_color,
                             domain_icon=get_domain_icon(domain['name'], di),
                             skill_icon=get_skill_icon(skill['name'], si))
    except (IndexError, KeyError) as e:
        print(f"Ошибка при загрузке действия: {e}")
        abort(404)

@app.route('/api/action/<int:di>/<int:si>/<int:ai>')
def action_api(di, si, ai):
    data = get_matrix()
    meta = get_meta()
    try:
        domain = data['domains'][di]
        skill = domain['skills'][si]
        action = skill['actions'][ai]
        template_id = action.get('template_id')
        template = meta['action_templates'].get(template_id, {})
        
        # Если это родительский элемент, возвращаем информацию о поддействиях
        if template.get('is_parent', False):
            subactions_data = []
            if 'subactions' in action:
                for sub_idx, sub in enumerate(action['subactions']):
                    sub_template = meta['action_templates'].get(sub['template_id'], {})
                    subactions_data.append({
                        "text": sub['text'],
                        "template_id": sub['template_id'],
                        "level_tag": sub.get('level_tag'),
                        "review_questions": sub.get('review_questions', []),
                        "name": sub_template.get('name', ''),
                        "url": f"/subaction/{di}/{si}/{ai}/{sub_idx}"
                    })
            
            domain_color = get_domain_color(domain['name'])
            skill_color = get_skill_color(skill['name'], domain_color, si)
            
            return jsonify({
                "title": action['text'],
                "description": "<p>Это группа компетенций. Выберите конкретный навык из списка ниже:</p>",
                "is_parent": True,
                "subactions": subactions_data,
                "level_tag": action.get('level_tag'),
                "review_questions": action.get('review_questions', []),
                "domain_color": domain_color,
                "skill_color": skill_color,
                "domain_icon": get_domain_icon(domain['name'], di),
                "skill_icon": get_skill_icon(skill['name'], si)
            })
        
        enriched = enrich_action(action, template, meta)
        description = build_description(action, template, domain, skill, meta)
        domain_color = get_domain_color(domain['name'])
        skill_color = get_skill_color(skill['name'], domain_color, si)
        
        result = {
            "title": action['text'],
            "description": description,
            "examples": enriched['examples'],
            "tools": enriched['tools'],
            "stack_labels": enriched['stack_labels'],
            "literature": enriched['literature'],
            "level_tag": action.get('level_tag'),
            "review_questions": action.get('review_questions', []),
            "related_skills": find_related_skills(data, di, si, ai),
            "domain_color": domain_color,
            "skill_color": skill_color,
            "domain_icon": get_domain_icon(domain['name'], di),
            "skill_icon": get_skill_icon(skill['name'], si)
        }
        
        return jsonify(result)
    except (IndexError, KeyError) as e:
        print(f"Ошибка API: {e}")
        return jsonify({"error": "Not found"}), 404

# ----- МАРШРУТЫ ДЛЯ ПОДДЕЙСТВИЙ -----

@app.route('/subaction/<int:di>/<int:si>/<int:ai>/<int:sub_idx>')
def subaction_page(di, si, ai, sub_idx):
    data = get_matrix()
    try:
        domain = data['domains'][di]
        skill = domain['skills'][si]
        action = skill['actions'][ai]
        
        if 'subactions' not in action or sub_idx >= len(action['subactions']):
            abort(404)
            
        sub = action['subactions'][sub_idx]
        domain_color = get_domain_color(domain['name'])
        skill_color = get_skill_color(skill['name'], domain_color, si)
        
        return render_template('action_detail.html',
                             domain=domain,
                             skill=skill,
                             action=sub,
                             action_text=sub['text'],
                             di=di, si=si, ai=ai, sub_idx=sub_idx,
                             parent_action_text=action['text'],
                             domain_color=domain_color,
                             skill_color=skill_color,
                             domain_icon=get_domain_icon(domain['name'], di),
                             skill_icon=get_skill_icon(skill['name'], si))
    except (IndexError, KeyError) as e:
        print(f"Ошибка при загрузке поддействия: {e}")
        abort(404)

@app.route('/api/subaction/<int:di>/<int:si>/<int:ai>/<int:sub_idx>')
def subaction_api(di, si, ai, sub_idx):
    data = get_matrix()
    meta = get_meta()
    try:
        domain = data['domains'][di]
        skill = domain['skills'][si]
        action = skill['actions'][ai]
        
        if 'subactions' not in action or sub_idx >= len(action['subactions']):
            return jsonify({"error": "Subaction not found"}), 404
            
        sub = action['subactions'][sub_idx]
        template_id = sub.get('template_id')
        template = meta['action_templates'].get(template_id, {})
        
        if template.get('is_parent', False):
            return jsonify({"error": "Cannot view parent template directly"}), 400
        
        enriched = enrich_action(sub, template, meta)
        description = build_description(sub, template, domain, skill, meta)
        domain_color = get_domain_color(domain['name'])
        skill_color = get_skill_color(skill['name'], domain_color, si)
        
        result = {
            "title": sub['text'],
            "description": description,
            "examples": enriched['examples'],
            "tools": enriched['tools'],
            "stack_labels": enriched['stack_labels'],
            "literature": enriched['literature'],
            "level_tag": sub.get('level_tag'),
            "review_questions": sub.get('review_questions', []),
            "domain_color": domain_color,
            "skill_color": skill_color,
            "domain_icon": get_domain_icon(domain['name'], di),
            "skill_icon": get_skill_icon(skill['name'], si),
            "parent_action": action['text']
        }
        
        return jsonify(result)
    except (IndexError, KeyError) as e:
        print(f"Ошибка API поддействия: {e}")
        return jsonify({"error": "Not found"}), 404

# ----- МАРШРУТЫ ДЛЯ ГРАФОВ ДОМЕНОВ -----

@app.route('/domain-graph/<int:domain_idx>')
def domain_graph(domain_idx):
    data = get_matrix()
    meta = get_meta()
    try:
        if domain_idx >= len(data["domains"]):
            abort(404)
        domain = data["domains"][domain_idx]
        return render_template('domain_graph.html',
                             domain=domain,
                             domain_idx=domain_idx,
                             current_domain_index=domain_idx,
                             ui_config=meta.get('ui_config', {}))
    except (IndexError, KeyError, TypeError) as e:
        print(f"Ошибка при загрузке графа домена: {e}")
        abort(404)

@app.route('/api/domain-graph/<int:domain_idx>')
def domain_graph_data(domain_idx):
    data = get_matrix()
    meta = get_meta()
    try:
        if domain_idx >= len(data["domains"]):
            return jsonify({"error": "Domain not found"}), 404
        
        domain = data["domains"][domain_idx]
        nodes = []
        links = []
        
        domain_color = get_domain_color(domain['name'])
        domain_icon = get_domain_icon(domain['name'], domain_idx)
        domain_root_id = f"dg_root_{domain_idx}"
        
        nodes.append({
            "id": domain_root_id,
            "name": domain["name"],
            "type": "domain_root",
            "color": domain_color,
            "icon": domain_icon,
            "level": 0,
            "description": f"Домен: {domain['name']}"
        })
        
        for skill_idx, skill in enumerate(domain["skills"]):
            skill_id = f"dg_skill_{domain_idx}_{skill_idx}"
            skill_color = get_skill_color(skill['name'], domain_color, skill_idx)
            skill_icon = get_skill_icon(skill['name'], skill_idx)
            
            nodes.append({
                "id": skill_id,
                "name": skill["name"],
                "type": "skill",
                "icon": skill_icon,
                "color": skill_color,
                "level": 1,
                "description": skill.get("description", ""),
                "domain_idx": domain_idx,
                "skill_idx": skill_idx
            })
            links.append({"source": domain_root_id, "target": skill_id, "label": "содержит"})
            
            for action_idx, action in enumerate(skill["actions"]):
                action_id = f"dg_action_{domain_idx}_{skill_idx}_{action_idx}"
                template_id = action.get('template_id')
                template = meta['action_templates'].get(template_id, {})
                enriched = enrich_action(action, template, meta)
                stack_labels = enriched['stack_labels']
                
                action_leaf_path = f"{domain_idx}/{skill_idx}/{action_idx}" if 'subactions' not in action else None
                nodes.append({
                    "id": action_id,
                    "name": action['text'],
                    "full_name": action['text'],
                    "type": "action",
                    "level": 2,
                    "domain_idx": domain_idx,
                    "skill_idx": skill_idx,
                    "action_idx": action_idx,
                    "stack": stack_labels,
                    "color": "#f39c12",
                    "leaf_path": action_leaf_path,
                    "level_tag": action.get("level_tag"),
                })
                links.append({"source": skill_id, "target": action_id, "label": "выполняет"})
                
                if 'subactions' in action:
                    for sub_idx, sub in enumerate(action['subactions']):
                        sub_id = f"dg_sub_{domain_idx}_{skill_idx}_{action_idx}_{sub_idx}"
                        nodes.append({
                            "id": sub_id,
                            "name": sub['text'],
                            "full_name": sub['text'],
                            "type": "subaction",
                            "level": 3,
                            "domain_idx": domain_idx,
                            "skill_idx": skill_idx,
                            "action_idx": action_idx,
                            "sub_idx": sub_idx,
                            "color": "#f39c12",
                            "leaf_path": f"{domain_idx}/{skill_idx}/{action_idx}/{sub_idx}",
                            "level_tag": sub.get("level_tag"),
                        })
                        links.append({"source": action_id, "target": sub_id, "label": "содержит"})
                
                if stack_labels:
                    for stack_idx, stack in enumerate(stack_labels):
                        stack_id = f"dg_stack_{domain_idx}_{skill_idx}_{action_idx}_{stack_idx}"
                        if not any(node["id"] == stack_id for node in nodes):
                            nodes.append({
                                "id": stack_id,
                                "name": stack.get("name", stack.get("key", "Technology")),
                                "type": "stack",
                                "icon": stack.get("icon", "cube"),
                                "color": stack.get("color", "#9b59b6"),
                                "level": 4,
                                "description": stack.get("description", "")
                            })
                        links.append({"source": action_id, "target": stack_id, "label": "использует"})
        
        return jsonify({
            "domain": {"name": domain["name"], "color": domain_color, "icon": domain_icon},
            "nodes": nodes,
            "links": links
        })
    except Exception as e:
        print(f"Ошибка при создании графа домена: {e}")
        return jsonify({"error": str(e)}), 500

# ----- МАРШРУТ ДЛЯ ЭКСПОРТА -----

@app.route('/export')
def export():
    return render_template('export.html')

# ----- СХЕМА И ВАЛИДАЦИЯ -----

@app.route('/api/schema')
def api_schema():
    """Информация о схеме источника (для догрузки и валидации)."""
    return jsonify({"ok": True, **get_schema_info()})


@app.route('/api/validate', methods=["POST"])
def api_validate():
    """Валидация структуры источника. Body: {domains: [...], action_templates: {...}, ...}."""
    data = request.get_json() or {}
    vr = validate_source(data)
    return jsonify({"ok": vr.ok, **vr.to_dict()})


# ----- НАСТРОЙКИ: бэкапы и восстановление -----

@app.route('/import')
def import_page():
    """Импорт данных — догрузка JSON/Excel."""
    return render_template('import.html')


@app.route('/about')
def about_page():
    """Раздел «О приложении»."""
    return render_template('about.html')


@app.route('/settings')
def settings_page():
    return render_template('settings.html')


@app.route('/changes')
def changes_page():
    return render_template('changes.html')


@app.route('/admin/users')
def admin_users_page():
    actor, role = _extract_actor_role()
    if role != "admin":
        return redirect(url_for("login", next=request.path))
    return render_template('admin_users.html', actor=actor, role=role)


@app.route('/api/admin/users', methods=["GET"])
def api_admin_users_list():
    actor, admin_err = _require_admin()
    if admin_err:
        return admin_err
    _ensure_db_schema()
    with db_session() as session:
        rows = session.execute(select(User).order_by(User.id.asc())).scalars().all()
        items = [
            {
                "id": u.id,
                "username": u.username,
                "role": u.role,
                "full_name": u.full_name or "",
                "email": u.email or "",
                "must_change_password": bool(u.must_change_password),
                "is_active": bool(u.is_active),
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "requested_by": actor,
            }
            for u in rows
        ]
    return jsonify({
        "ok": True,
        "items": items,
    })


@app.route('/api/admin/users', methods=["POST"])
def api_admin_users_create():
    data = request.get_json(silent=True) or {}
    _, admin_err = _require_admin()
    if admin_err:
        return admin_err
    username = (data.get("username") or "").strip()
    role = (data.get("role") or "user").strip().lower()
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    temp_password = (data.get("temp_password") or "").strip()
    if not username:
        return jsonify({"ok": False, "error": "username required"}), 400
    if role not in ("user", "admin"):
        return jsonify({"ok": False, "error": "role must be user or admin"}), 400
    if email and "@" not in email:
        return jsonify({"ok": False, "error": "invalid email"}), 400
    if len(temp_password) < 10:
        return jsonify({"ok": False, "error": "temp_password must be at least 10 characters"}), 400
    _ensure_db_schema()
    with db_session() as session:
        exists = session.execute(select(User).where(User.username == username)).scalars().first()
        if exists:
            return jsonify({"ok": False, "error": "username already exists"}), 409
        user = User(
            username=username,
            role=role,
            full_name=full_name,
            email=email,
            password_hash=generate_password_hash(temp_password),
            must_change_password=True,
            is_active=True,
        )
        session.add(user)
        session.flush()
        created_id = user.id
    return jsonify({"ok": True, "id": created_id, "must_change_password": True})


@app.route('/api/admin/users/<int:user_id>', methods=["PATCH"])
def api_admin_users_update(user_id: int):
    data = request.get_json(silent=True) or {}
    _, admin_err = _require_admin()
    if admin_err:
        return admin_err
    new_username = data.get("username")
    new_role = data.get("role")
    new_full_name = data.get("full_name")
    new_email = data.get("email")
    new_active = data.get("is_active")
    reset_temp_password = data.get("reset_temp_password")
    _ensure_db_schema()
    with db_session() as session:
        user = session.get(User, user_id)
        if not user:
            return jsonify({"ok": False, "error": "user not found"}), 404
        if new_username is not None:
            username = (new_username or "").strip()
            if not username:
                return jsonify({"ok": False, "error": "username cannot be empty"}), 400
            exists = session.execute(
                select(User).where(User.username == username, User.id != user_id)
            ).scalars().first()
            if exists:
                return jsonify({"ok": False, "error": "username already exists"}), 409
            user.username = username
        if new_role is not None:
            role = (new_role or "").strip().lower()
            if role not in ("user", "admin"):
                return jsonify({"ok": False, "error": "role must be user or admin"}), 400
            if user.role == "admin" and role != "admin":
                admins = session.execute(select(User).where(User.role == "admin", User.is_active == True)).scalars().all()
                if len(admins) <= 1:
                    return jsonify({"ok": False, "error": "cannot demote last active admin"}), 409
            user.role = role
        if new_full_name is not None:
            user.full_name = (new_full_name or "").strip()
        if new_email is not None:
            email = (new_email or "").strip()
            if email and "@" not in email:
                return jsonify({"ok": False, "error": "invalid email"}), 400
            user.email = email
        if new_active is not None:
            active = bool(new_active)
            if user.role == "admin" and user.is_active and not active:
                admins = session.execute(select(User).where(User.role == "admin", User.is_active == True)).scalars().all()
                if len(admins) <= 1:
                    return jsonify({"ok": False, "error": "cannot deactivate last active admin"}), 409
            user.is_active = active
        if reset_temp_password is not None:
            temp_password = (reset_temp_password or "").strip()
            if len(temp_password) < 10:
                return jsonify({"ok": False, "error": "reset_temp_password must be at least 10 characters"}), 400
            user.password_hash = generate_password_hash(temp_password)
            user.must_change_password = True
    return jsonify({"ok": True})


@app.route('/api/admin/users/<int:user_id>', methods=["DELETE"])
def api_admin_users_delete(user_id: int):
    _, admin_err = _require_admin()
    if admin_err:
        return admin_err
    _ensure_db_schema()
    with db_session() as session:
        user = session.get(User, user_id)
        if not user:
            return jsonify({"ok": False, "error": "user not found"}), 404
        if user.role == "admin":
            admins = session.execute(select(User).where(User.role == "admin", User.is_active == True)).scalars().all()
            if len(admins) <= 1:
                return jsonify({"ok": False, "error": "cannot delete last admin"}), 409
        session.delete(user)
    return jsonify({"ok": True})


@app.route('/admin/sql-console', methods=["GET"])
def admin_sql_console_page():
    actor, role = _extract_actor_role()
    if role != "admin":
        return redirect(url_for("login", next=request.path))
    return render_template('admin_sql_console.html', actor=actor, role=role)


@app.route('/admin/tree-editor', methods=["GET"])
def admin_tree_editor_page():
    actor, role = _extract_actor_role()
    if role != "admin":
        return redirect(url_for("login", next=request.path))
    return render_template('admin_tree_editor.html', actor=actor, role=role)


@app.route('/admin/notifications', methods=["GET"])
def admin_notifications_page():
    actor, role = _extract_actor_role()
    if role != "admin":
        return redirect(url_for("login", next=request.path))
    return render_template('admin_notifications.html', actor=actor, role=role)


@app.route('/api/admin/tree-editor/data', methods=["GET"])
def api_admin_tree_editor_data():
    _, admin_err = _require_admin()
    if admin_err:
        return admin_err
    _ensure_db_schema()
    with db_session() as session:
        unified = load_unified_from_db(session, literature=load_literature_map())
    return jsonify(
        {
            "ok": True,
            "domains": unified.get("domains") or [],
            "action_templates": unified.get("action_templates") or {},
            "literature": unified.get("literature") or {},
        }
    )


@app.route('/api/admin/tree-editor/preview', methods=["POST"])
def api_admin_tree_editor_preview():
    payload = request.get_json(silent=True) or {}
    actor, admin_err = _require_admin(payload)
    if admin_err:
        return admin_err
    edited_domains = payload.get("domains")
    if not isinstance(edited_domains, list):
        return jsonify({"ok": False, "error": "domains array is required"}), 400
    _ensure_db_schema()
    with db_session() as session:
        current = load_unified_from_db(session, literature=load_literature_map())
    proposed = dict(current)
    proposed["domains"] = edited_domains
    warnings = _build_tree_edit_warnings(current, edited_domains)
    revision_payload = build_revision_payload(
        base_snapshot=current,
        upload_payload={"domains": edited_domains},
        proposed_snapshot=proposed,
        merge_mode="replace_all",
    )
    return jsonify(
        {
            "ok": True,
            "requested_by": actor,
            "warnings": warnings,
            "diff": revision_payload.get("structural_diff"),
            "json_patch_ops": len(revision_payload.get("json_patch") or []),
            "upsert_plan": revision_payload.get("upsert_plan") or {},
        }
    )


@app.route('/api/admin/tree-editor/submit', methods=["POST"])
def api_admin_tree_editor_submit():
    payload = request.get_json(silent=True) or {}
    actor, admin_err = _require_admin(payload)
    if admin_err:
        return admin_err
    edited_domains = payload.get("domains")
    if not isinstance(edited_domains, list):
        return jsonify({"ok": False, "error": "domains array is required"}), 400
    title = (payload.get("title") or "").strip() or "Admin tree edit"
    confirm_rel = bool(payload.get("confirm_relations"))
    _ensure_db_schema()
    with db_session() as session:
        current = load_unified_from_db(session, literature=load_literature_map())
    warnings = _build_tree_edit_warnings(current, edited_domains)
    if warnings["removed_template_count"] > 0 and not confirm_rel:
        return jsonify(
            {
                "ok": False,
                "error": "relations_confirmation_required",
                "warnings": warnings,
                "message": "Tree edit removes template bindings. Confirm relation override.",
            }
        ), 409
    proposed = dict(current)
    proposed["domains"] = edited_domains
    revision_payload = build_revision_payload(
        base_snapshot=current,
        upload_payload={"domains": edited_domains},
        proposed_snapshot=proposed,
        merge_mode="replace_all",
    )
    with db_session() as session:
        cr = create_change_request(
            session=session,
            title=title,
            merge_mode="replace_all",
            payload=revision_payload,
            created_by=actor,
        )
        approval_set_status(session, cr.id, "submitted", actor=actor, comment="Admin tree edit submitted")
        _notify_cr_submitted(session, cr)
        change_id = cr.id
    return jsonify(
        {
            "ok": True,
            "change_id": change_id,
            "status": "submitted",
            "warnings": warnings,
            "message": "Changes submitted for approval with diff.",
        }
    )


@app.route('/api/admin/db/objects', methods=["GET"])
def api_admin_db_objects():
    actor, admin_err = _require_admin()
    if admin_err:
        return admin_err
    _ensure_db_schema()
    with db_session() as session:
        tables = session.execute(
            text(
                """
                SELECT table_schema AS schema, table_name AS name, table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """
            )
        ).mappings().all()
        sequences = session.execute(
            text(
                """
                SELECT sequence_schema AS schema, sequence_name AS name
                FROM information_schema.sequences
                WHERE sequence_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY sequence_schema, sequence_name
                """
            )
        ).mappings().all()
        functions = session.execute(
            text(
                """
                SELECT n.nspname AS schema, p.proname AS name, pg_get_function_identity_arguments(p.oid) AS args
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY n.nspname, p.proname
                """
            )
        ).mappings().all()
    items = []
    for row in tables:
        table_type = row["table_type"]
        if table_type == "BASE TABLE":
            obj_type = "table"
        elif table_type == "VIEW":
            obj_type = "view"
        else:
            obj_type = "table_like"
        items.append(
            {
                "type": obj_type,
                "schema": row["schema"],
                "name": row["name"],
                "qualified_name": f"{row['schema']}.{row['name']}",
            }
        )
    for row in sequences:
        items.append(
            {
                "type": "sequence",
                "schema": row["schema"],
                "name": row["name"],
                "qualified_name": f"{row['schema']}.{row['name']}",
            }
        )
    for row in functions:
        args = row["args"] or ""
        items.append(
            {
                "type": "function",
                "schema": row["schema"],
                "name": row["name"],
                "args": args,
                "qualified_name": f"{row['schema']}.{row['name']}({args})",
            }
        )
    return jsonify({"ok": True, "requested_by": actor, "items": items})


@app.route('/api/admin/db/object/details', methods=["POST"])
def api_admin_db_object_details():
    payload = request.get_json(silent=True) or {}
    _, admin_err = _require_admin(payload)
    if admin_err:
        return admin_err
    schema = (payload.get("schema") or "").strip()
    name = (payload.get("name") or "").strip()
    obj_type = (payload.get("type") or "table").strip().lower()
    row_limit = int(payload.get("row_limit") or 25)
    row_limit = min(max(row_limit, 1), 200)
    if not schema or not name:
        return jsonify({"ok": False, "error": "schema and name are required"}), 400
    try:
        _quote_ident(schema)
        _quote_ident(name)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    _ensure_db_schema()
    ddl = ""
    columns = []
    rows = []
    try:
        with db_session() as session:
            if obj_type == "table":
                ddl = _build_table_ddl(session, schema, name)
                qname = _qualified_ident(schema, name)
                rows_result = session.execute(text(f"SELECT * FROM {qname} LIMIT {row_limit}"))
                columns = list(rows_result.keys())
                rows = [list(r) for r in rows_result.fetchall()]
            elif obj_type == "view":
                ddl_row = session.execute(
                    text(
                        """
                        SELECT pg_get_viewdef((quote_ident(:schema) || '.' || quote_ident(:name))::regclass, true) AS ddl
                        """
                    ),
                    {"schema": schema, "name": name},
                ).mappings().first()
                ddl = f"CREATE VIEW {_qualified_ident(schema, name)} AS\n{(ddl_row or {}).get('ddl') or '-- view not found'}"
                qname = _qualified_ident(schema, name)
                rows_result = session.execute(text(f"SELECT * FROM {qname} LIMIT {row_limit}"))
                columns = list(rows_result.keys())
                rows = [list(r) for r in rows_result.fetchall()]
            elif obj_type == "sequence":
                ddl = f"-- Sequence: {_qualified_ident(schema, name)}"
                qname = _qualified_ident(schema, name)
                rows_result = session.execute(text(f"SELECT * FROM {qname}"))
                columns = list(rows_result.keys())
                rows = [list(r) for r in rows_result.fetchall()]
            elif obj_type == "function":
                ddl = f"-- Function scanner entry: {schema}.{name}"
            else:
                return jsonify({"ok": False, "error": f"Unsupported object type: {obj_type}"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": _format_db_error(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "object": {"type": obj_type, "schema": schema, "name": name},
            "ddl": ddl,
            "columns": columns,
            "rows": rows,
        }
    )


@app.route('/api/admin/db/execute', methods=["POST"])
def api_admin_db_execute():
    payload = request.get_json(silent=True) or {}
    _, admin_err = _require_admin(payload)
    if admin_err:
        return admin_err
    sql = (payload.get("sql") or "").strip()
    if not sql:
        return jsonify({"ok": False, "error": "sql is required"}), 400
    _ensure_db_schema()
    try:
        with db_session() as session:
            result = session.execute(text(sql))
            if result.returns_rows:
                columns = list(result.keys())
                rows = [list(r) for r in result.fetchall()]
                return jsonify(
                    {
                        "ok": True,
                        "returns_rows": True,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                    }
                )
            return jsonify(
                {
                    "ok": True,
                    "returns_rows": False,
                    "row_count": int(result.rowcount or 0),
                }
            )
    except Exception as exc:
        return jsonify({"ok": False, "error": _format_db_error(exc)}), 400


@app.route('/api/admin/db/diagram', methods=["GET"])
def api_admin_db_diagram():
    _, admin_err = _require_admin()
    if admin_err:
        return admin_err
    _ensure_db_schema()
    with db_session() as session:
        tables = session.execute(
            text(
                """
                SELECT table_schema AS schema, table_name AS name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
        ).mappings().all()
        edges = session.execute(
            text(
                """
                SELECT
                    tc.table_name AS from_table,
                    ccu.table_name AS to_table,
                    tc.constraint_name AS constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
                ORDER BY tc.table_name, ccu.table_name
                """
            )
        ).mappings().all()
    table_names = [row["name"] for row in tables]
    mermaid_lines = ["erDiagram"]
    for t in table_names:
        mermaid_lines.append(f"  {t} {{")
        mermaid_lines.append("    int id")
        mermaid_lines.append("  }")
    for edge in edges:
        left = edge["to_table"]
        right = edge["from_table"]
        label = (edge["constraint_name"] or "fk").replace('"', "")
        mermaid_lines.append(f"  {left} ||--o{{ {right} : \"{label}\"")
    return jsonify(
        {
            "ok": True,
            "tables": table_names,
            "edges": [dict(e) for e in edges],
            "mermaid": "\n".join(mermaid_lines),
        }
    )


@app.route('/api/admin/notifications', methods=["GET"])
def api_admin_notifications_list():
    _, admin_err = _require_admin()
    if admin_err:
        return admin_err
    status_filter = (request.args.get("status") or "").strip().lower()
    q_filter = (request.args.get("q") or "").strip()
    only_failed = (request.args.get("only_failed") or "").strip().lower() in ("1", "true", "yes")
    try:
        limit_value = int((request.args.get("limit") or "100").strip())
    except ValueError:
        limit_value = 100
    limit = max(1, min(500, limit_value))
    _ensure_db_schema()
    with db_session() as session:
        stmt = select(NotificationLog).order_by(NotificationLog.id.desc())
        if only_failed and not status_filter:
            stmt = stmt.where(NotificationLog.status.in_(["failed", "skipped"]))
        if status_filter:
            stmt = stmt.where(NotificationLog.status == status_filter)
        if q_filter:
            like = f"%{q_filter}%"
            stmt = stmt.where(
                or_(
                    NotificationLog.event_type.ilike(like),
                    NotificationLog.subject.ilike(like),
                    NotificationLog.error.ilike(like),
                )
            )
        rows = session.execute(stmt.limit(limit)).scalars().all()
        if q_filter:
            ql = q_filter.lower()
            rows = [
                n
                for n in rows
                if ql in ",".join(n.recipients or []).lower() or ql in str(n.context or {}).lower() or ql in (n.created_by or "").lower()
            ]
        items = [
            {
                "id": n.id,
                "event_type": n.event_type,
                "status": n.status,
                "subject": n.subject,
                "recipients": n.recipients or [],
                "error": n.error,
                "attempts": n.attempts,
                "created_by": n.created_by,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "last_attempt_at": n.last_attempt_at.isoformat() if n.last_attempt_at else None,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "context": n.context or {},
            }
            for n in rows
        ]
    return jsonify({"ok": True, "items": items})


@app.route('/api/admin/notifications/<int:notification_id>/retry', methods=["POST"])
def api_admin_notifications_retry(notification_id: int):
    actor, admin_err = _require_admin()
    if admin_err:
        return admin_err
    _ensure_db_schema()
    with db_session() as session:
        row = session.get(NotificationLog, notification_id)
        if not row:
            return jsonify({"ok": False, "error": "Notification not found"}), 404
        ok, err = _deliver_notification_log(row)
        row.context = {**(row.context or {}), "last_retry_by": actor}
        out_status = row.status
    return jsonify({"ok": ok, "status": out_status, "error": err})


@app.route('/api/changes', methods=["GET"])
def api_changes_list():
    _ensure_db_schema()
    actor, _ = _extract_actor_role()
    with db_session() as session:
        items = list_change_requests(session)
        ids = [int(i["id"]) for i in items if i.get("id") is not None]
        summary_map: Dict[int, Dict[str, int]] = {}
        thread_map: Dict[int, List[ChangeDiscussionThread]] = {}
        if ids:
            thread_rows = session.execute(
                select(ChangeDiscussionThread).where(ChangeDiscussionThread.change_request_id.in_(ids))
            ).scalars().all()
            for thread in thread_rows:
                change_request_id = int(thread.change_request_id)
                bucket = summary_map.setdefault(int(change_request_id), {"threads_total": 0, "threads_blocking": 0})
                bucket["threads_total"] += 1
                if bool(thread.requires_resolution) and thread.status != "resolved":
                    bucket["threads_blocking"] += 1
                thread_map.setdefault(change_request_id, []).append(thread)
        for item in items:
            sid = int(item.get("id"))
            summary = summary_map.get(sid, {"threads_total": 0, "threads_blocking": 0})
            item["threads_total"] = summary["threads_total"]
            item["threads_blocking"] = summary["threads_blocking"]
            actor_mentions = 0
            actor_needs_response = 0
            if actor:
                for thread in thread_map.get(sid, []):
                    if thread.status == "needs_author_response":
                        cr_author = (item.get("created_by") or "").strip()
                        if actor == cr_author:
                            actor_needs_response += 1
                    for msg in thread.messages or []:
                        if actor in _extract_mentions(msg.body or ""):
                            actor_mentions += 1
            item["my_mentions"] = actor_mentions
            item["my_needs_response"] = actor_needs_response
    return jsonify({"ok": True, "items": items})


@app.route('/api/changes', methods=["POST"])
def api_changes_create():
    _ensure_db_schema()
    data = request.get_json(silent=True) or {}
    actor, _ = _extract_actor_role(data)
    title = (data.get("title") or "Change request").strip()
    merge_mode = (data.get("merge_mode") or "append").strip()
    payload = data.get("payload") or {}
    target_domain = data.get("target_domain")
    target_skill = data.get("target_skill")
    with db_session() as session:
        current = load_unified_from_db(session, literature=load_literature_map())
        merged = merge_upload_into_source(
            current,
            payload,
            merge_mode=merge_mode,
            target_domain=target_domain,
            target_skill=target_skill,
        )
        revision_payload = build_revision_payload(
            base_snapshot=current,
            upload_payload=payload,
            proposed_snapshot=merged,
            merge_mode=merge_mode,
            target_domain=target_domain,
            target_skill=target_skill,
        )
        cr = create_change_request(
            session=session,
            title=title,
            merge_mode=merge_mode,
            payload=revision_payload,
            staging_batch_id=revision_payload.get("staging_batch_id"),
            created_by=actor,
            target_domain=target_domain,
            target_skill=target_skill,
        )
        approval_set_status(session, cr.id, "submitted", actor=actor, comment="Created and submitted")
        _notify_cr_submitted(session, cr)
        change_id = cr.id
    return jsonify({"ok": True, "id": change_id})


@app.route('/api/changes/<int:change_id>', methods=["GET"])
def api_changes_get(change_id):
    _ensure_db_schema()
    with db_session() as session:
        details = get_change_request_details(session, change_id)
        thread_rows = session.execute(
            select(ChangeDiscussionThread).where(ChangeDiscussionThread.change_request_id == change_id)
        ).scalars().all()
    if not details:
        return jsonify({"ok": False, "error": "Change request not found"}), 404
    details["discussion_summary"] = {
        "threads_total": len(thread_rows),
        "threads_blocking": len([t for t in thread_rows if t.requires_resolution and t.status != "resolved"]),
    }
    return jsonify({"ok": True, "change": details})


@app.route('/api/changes/<int:change_id>/discussion', methods=["GET"])
def api_changes_discussion(change_id: int):
    _ensure_db_schema()
    auth, auth_err = _require_authenticated()
    if auth_err:
        return auth_err
    with db_session() as session:
        cr = session.get(ChangeRequest, change_id)
        if not cr:
            return jsonify({"ok": False, "error": "Change request not found"}), 404
        rows = session.execute(
            select(ChangeDiscussionThread).where(ChangeDiscussionThread.change_request_id == change_id)
        ).scalars().all()
        status_filter = (request.args.get("status") or "").strip().lower()
        mentions_only = (request.args.get("mentions_only") or "").strip().lower() in ("1", "true", "yes")
        payload_threads = []
        for t in sorted(rows, key=lambda x: x.id or 0):
            if status_filter and status_filter != "all" and t.status != status_filter:
                continue
            serialized = _serialize_discussion_thread(t)
            mentioned = any(auth["actor"] in _extract_mentions(m.get("body") or "") for m in serialized.get("messages") or [])
            needs_author_response = (t.status == "needs_author_response" and (cr.created_by or "") == auth["actor"])
            serialized["mentioned_me"] = mentioned
            serialized["needs_my_response"] = needs_author_response
            if mentions_only and not mentioned and not needs_author_response:
                continue
            payload_threads.append(serialized)
    return jsonify({"ok": True, "requested_by": auth["actor"], "threads": payload_threads})


@app.route('/api/changes/<int:change_id>/timeline', methods=["GET"])
def api_changes_timeline(change_id: int):
    _ensure_db_schema()
    auth, auth_err = _require_authenticated()
    if auth_err:
        return auth_err
    with db_session() as session:
        cr = session.get(ChangeRequest, change_id)
        if not cr:
            return jsonify({"ok": False, "error": "Change request not found"}), 404
        revisions = session.execute(
            select(ChangeRevision).where(ChangeRevision.change_request_id == change_id).order_by(ChangeRevision.revision_no.asc())
        ).scalars().all()
        decisions = session.execute(
            select(ApprovalDecision).where(ApprovalDecision.change_request_id == change_id).order_by(ApprovalDecision.id.asc())
        ).scalars().all()
        threads = session.execute(
            select(ChangeDiscussionThread).where(ChangeDiscussionThread.change_request_id == change_id)
        ).scalars().all()
        events: List[Dict[str, Any]] = []
        events.append({
            "kind": "change_created",
            "at": cr.created_at.isoformat() if cr.created_at else None,
            "actor": cr.created_by,
            "body": f"Change request created: {cr.title}",
        })
        for rev in revisions:
            events.append({
                "kind": "revision",
                "at": rev.created_at.isoformat() if rev.created_at else None,
                "actor": rev.created_by,
                "body": f"Revision #{rev.revision_no}. {rev.note or ''}".strip(),
            })
        for d in decisions:
            events.append({
                "kind": "status",
                "at": d.created_at.isoformat() if d.created_at else None,
                "actor": d.actor,
                "body": f"Status -> {d.decision}. {d.comment or ''}".strip(),
            })
        for t in threads:
            events.append({
                "kind": "thread",
                "at": t.created_at.isoformat() if t.created_at else None,
                "actor": t.created_by,
                "body": f"Thread #{t.id}: {t.subject}",
            })
            for m in sorted(t.messages or [], key=lambda x: x.id or 0):
                events.append({
                    "kind": "thread_message",
                    "at": m.created_at.isoformat() if m.created_at else None,
                    "actor": m.author,
                    "body": f"[thread #{t.id}] {m.body}",
                    "mentions_me": auth["actor"] in _extract_mentions(m.body or ""),
                })
        events.sort(key=lambda e: e.get("at") or "")
    return jsonify({"ok": True, "requested_by": auth["actor"], "events": events})


@app.route('/api/changes/<int:change_id>/discussion/threads', methods=["POST"])
def api_changes_discussion_create_thread(change_id: int):
    _ensure_db_schema()
    auth, auth_err = _require_authenticated()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip() or "Комментарий к изменению"
    body = (data.get("body") or "").strip()
    requires_resolution = bool(data.get("requires_resolution", True))
    if not body:
        return jsonify({"ok": False, "error": "body required"}), 400
    with db_session() as session:
        cr = session.get(ChangeRequest, change_id)
        if not cr:
            return jsonify({"ok": False, "error": "Change request not found"}), 404
        thread = ChangeDiscussionThread(
            change_request_id=change_id,
            subject=subject,
            status="open",
            requires_resolution=requires_resolution,
            created_by=auth["actor"],
            created_role=auth["role"],
            resolved_by=None,
            resolved_at=None,
        )
        session.add(thread)
        session.flush()
        session.add(
            ChangeDiscussionMessage(
                thread_id=thread.id,
                author=auth["actor"],
                author_role=auth["role"],
                body=body,
                kind="comment",
            )
        )
        _notify_mentions(session, change_id=change_id, actor=auth["actor"], text_value=body)
        cr.updated_at = thread.updated_at
        thread_id = thread.id
    return jsonify({"ok": True, "thread_id": thread_id})


@app.route('/api/changes/<int:change_id>/discussion/threads/<int:thread_id>/messages', methods=["POST"])
def api_changes_discussion_add_message(change_id: int, thread_id: int):
    _ensure_db_schema()
    auth, auth_err = _require_authenticated()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"ok": False, "error": "body required"}), 400
    with db_session() as session:
        thread = session.get(ChangeDiscussionThread, thread_id)
        if not thread or thread.change_request_id != change_id:
            return jsonify({"ok": False, "error": "Thread not found"}), 404
        session.add(
            ChangeDiscussionMessage(
                thread_id=thread.id,
                author=auth["actor"],
                author_role=auth["role"],
                body=body,
                kind="comment",
            )
        )
        _notify_mentions(session, change_id=change_id, actor=auth["actor"], text_value=body)
        # Any new reply reopens resolution loop unless it was already fully resolved by admin decision.
        if thread.status != "resolved":
            thread.status = "open"
            thread.resolved_by = None
            thread.resolved_at = None
    return jsonify({"ok": True})


@app.route('/api/changes/<int:change_id>/discussion/threads/<int:thread_id>/status', methods=["POST"])
def api_changes_discussion_set_status(change_id: int, thread_id: int):
    _ensure_db_schema()
    data = request.get_json(silent=True) or {}
    actor, admin_err = _require_admin(data)
    if admin_err:
        return admin_err
    action = (data.get("action") or "").strip().lower()
    comment = (data.get("comment") or "").strip()
    mapping = {
        "accept": "resolved",
        "resolve": "resolved",
        "reject": "needs_author_response",
        "request_info": "needs_author_response",
        "reopen": "open",
    }
    new_status = mapping.get(action)
    if new_status not in DISCUSSION_THREAD_STATUSES:
        return jsonify({"ok": False, "error": "Invalid action"}), 400
    if action in {"reject", "request_info"} and not comment:
        return jsonify({"ok": False, "error": "comment required for reject/request_info"}), 400
    with db_session() as session:
        thread = session.get(ChangeDiscussionThread, thread_id)
        if not thread or thread.change_request_id != change_id:
            return jsonify({"ok": False, "error": "Thread not found"}), 404
        thread.status = new_status
        if new_status == "resolved":
            thread.resolved_by = actor
            thread.resolved_at = datetime.now(timezone.utc)
        else:
            thread.resolved_by = None
            thread.resolved_at = None
        session.add(
            ChangeDiscussionMessage(
                thread_id=thread.id,
                author=actor,
                author_role="admin",
                body=comment or f"Status changed: {new_status}",
                kind="status",
            )
        )
        _notify_mentions(session, change_id=change_id, actor=actor, text_value=comment or "")
        if new_status == "needs_author_response":
            cr = session.get(ChangeRequest, change_id)
            if cr:
                _notify_cr_status_to_author(
                    session,
                    cr,
                    status="needs_author_response",
                    actor=actor,
                    comment=comment or "Admin requested additional details in discussion",
                )
    return jsonify({"ok": True, "status": new_status})


@app.route('/api/changes/<int:change_id>/revise', methods=["POST"])
def api_changes_revise(change_id):
    _ensure_db_schema()
    data = request.get_json(silent=True) or {}
    payload = data.get("payload") or {}
    actor, _ = _extract_actor_role(data)
    note = (data.get("note") or "").strip()
    with db_session() as session:
        cr = session.get(ChangeRequest, change_id)
        if not cr:
            return jsonify({"ok": False, "error": "Change request not found"}), 404
        current = load_unified_from_db(session, literature=load_literature_map())
        merged = merge_upload_into_source(
            current,
            payload,
            merge_mode=cr.merge_mode,
            target_domain=cr.target_domain,
            target_skill=cr.target_skill,
        )
        revision_payload = build_revision_payload(
            base_snapshot=current,
            upload_payload=payload,
            proposed_snapshot=merged,
            merge_mode=cr.merge_mode,
            target_domain=cr.target_domain,
            target_skill=cr.target_skill,
        )
        rev = add_revision(
            session,
            change_id,
            payload=revision_payload,
            actor=actor,
            note=note,
            staging_batch_id=revision_payload.get("staging_batch_id"),
        )
    return jsonify({"ok": True, "revision_no": rev.revision_no})


@app.route('/api/changes/<int:change_id>/status', methods=["POST"])
def api_changes_status(change_id):
    _ensure_db_schema()
    data = request.get_json(silent=True) or {}
    actor, admin_err = _require_admin(data)
    if admin_err:
        return admin_err
    status = (data.get("status") or "").strip()
    comment = (data.get("comment") or "").strip()
    with db_session() as session:
        cr = approval_set_status(session, change_id, status=status, actor=actor, comment=comment)
        if not cr:
            return jsonify({"ok": False, "error": "Invalid status or change request not found"}), 400
        if status in {"approved", "rejected", "in_review"}:
            _notify_cr_status_to_author(session, cr, status=status, actor=actor, comment=comment)
    return jsonify({"ok": True, "status": status})


@app.route('/api/changes/<int:change_id>/apply', methods=["POST"])
def api_changes_apply(change_id):
    _ensure_db_schema()
    data = request.get_json(silent=True) or {}
    actor, admin_err = _require_admin(data)
    if admin_err:
        return admin_err
    with db_session() as session:
        cr = session.get(ChangeRequest, change_id)
        if not cr:
            return jsonify({"ok": False, "error": "Change request not found"}), 404
        blocking_threads = session.execute(
            select(func.count(ChangeDiscussionThread.id)).where(
                ChangeDiscussionThread.change_request_id == change_id,
                ChangeDiscussionThread.requires_resolution == True,
                ChangeDiscussionThread.status != "resolved",
            )
        ).scalar_one()
        if int(blocking_threads or 0) > 0:
            return jsonify({"ok": False, "error": "There are unresolved discussion threads"}), 409
        if cr.status != "approved":
            return jsonify({"ok": False, "error": "Only approved changes can be applied"}), 409
        payload = get_latest_payload(session, change_id) or {}
        proposed = payload.get("proposed_snapshot") if isinstance(payload, dict) else None
        if not isinstance(proposed, dict):
            upload_payload = payload.get("upload_payload") if isinstance(payload, dict) else payload
            current = load_unified_from_db(session, literature=load_literature_map())
            proposed = merge_upload_into_source(
                current,
                upload_payload or {},
                merge_mode=cr.merge_mode,
                target_domain=cr.target_domain,
                target_skill=cr.target_skill,
            )
        upsert_from_staging_projection(session, {"domains": (proposed or {}).get("domains") or []})
        # Keep metadata in sync using existing compatibility writer.
        current_unified = load_unified_from_db(session, literature=load_literature_map())
        current_unified["domains"] = (proposed or {}).get("domains") or []
        replace_unified_in_db(session, current_unified)
        cr.applied = True
        approval_set_status(session, change_id, "applied", actor=actor, comment="Applied to storage")
        _notify_cr_status_to_author(session, cr, status="applied", actor=actor, comment="Applied to storage")
    _invalidate_caches()
    _ensure_data_loaded()
    return jsonify({"ok": True, "applied": True})


# ----- ЛИТЕРАТУРА: каталог, привязка к листам -----

@app.route('/literature')
def literature_page():
    return render_template('literature.html')

@app.route('/api/literature')
def api_literature_list():
    """Список литературы с привязкой к компетенциям (листам)."""
    meta = get_meta()
    lit = meta.get('literature', {})
    templates = meta.get('action_templates', {})
    template_to_lit = {}
    for tid, t in templates.items():
        for rid in t.get('resource_ids', []):
            template_to_lit.setdefault(rid, []).append({"template_id": tid, "name": t.get('name', tid)})
    out = []
    for rid, item in lit.items():
        local_path = item.get("local_path") or item.get("file_path", "")
        if local_path:
            abs_local = local_path if os.path.isabs(local_path) else os.path.join(BASE_DIR, local_path)
            if not os.path.isfile(abs_local):
                local_path = ""
        out.append({
            "id": rid,
            "title": item.get("title", rid),
            "chapter": item.get("chapter", ""),
            "pages": item.get("pages", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "local_path": local_path,
            "linked_templates": template_to_lit.get(rid, []),
        })
    return jsonify(out)

@app.route('/api/literature', methods=['POST'])
def api_literature_add():
    """Ручное добавление литературы."""
    global _meta
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    meta = get_meta()
    lit = meta.setdefault('literature', {})
    lid = slugify(title)[:40] + '_' + hashlib.md5(title.encode()).hexdigest()[:6]
    if lid in lit:
        return jsonify({"error": "already exists", "id": lid}), 409
    _create_version_backup("literature_add", f"Добавление источника: {title}")
    lit[lid] = {
        "title": title,
        "chapter": (data.get('chapter') or '').strip(),
        "pages": (data.get('pages') or '').strip(),
        "url": (data.get('url') or '').strip(),
        "description": (data.get('description') or '').strip(),
    }
    save_meta(meta)
    return jsonify({"id": lid, "title": title})


@app.route('/api/literature/upload', methods=['POST'])
def api_literature_upload():
    """Загрузка физического файла (PDF и т.д.) в data/library с созданием записи литературы."""
    global _meta
    if "file" not in request.files:
        return jsonify({"error": "файл не выбран"}), 400
    f = request.files["file"]
    if f.filename == "" or not f.filename:
        return jsonify({"error": "файл не выбран"}), 400
    title = (request.form.get("title") or "").strip() or PathLib(f.filename).stem
    chapter = (request.form.get("chapter") or "").strip()
    pages = (request.form.get("pages") or "").strip()
    description = (request.form.get("description") or "").strip()
    lib_dir = _literature_dir()
    orig = PathLib(f.filename)
    suffix = (orig.suffix.lower() or ".pdf")
    if not suffix.startswith("."):
        suffix = "." + suffix
    stem = re.sub(r"[^\w\-]", "_", orig.stem)[:60]
    filepath = os.path.join(lib_dir, stem + suffix)
    n = 0
    while os.path.exists(filepath):
        n += 1
        filepath = os.path.join(lib_dir, f"{stem}_{n}{suffix}")
    try:
        f.save(filepath)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    rel_path = os.path.relpath(filepath, BASE_DIR)
    meta = get_meta()
    lit = meta.setdefault("literature", {})
    lid = slugify(title)[:40] + "_" + hashlib.md5((title + rel_path).encode()).hexdigest()[:6]
    if lid in lit:
        lid = lid + "_" + hashlib.md5(rel_path.encode()).hexdigest()[:4]
    _create_version_backup("literature_upload", f"Загрузка файла литературы: {title}")
    lit[lid] = {
        "title": title,
        "chapter": chapter,
        "pages": pages,
        "url": "",
        "description": description,
        "local_path": rel_path,
    }
    if _is_db_mode():
        mongo_add_literature_file(lid, os.path.basename(filepath), rel_path, suffix.lstrip("."))
    save_meta(meta)
    return jsonify({"id": lid, "title": title, "local_path": rel_path})


@app.route('/api/literature/<lit_id>', methods=['PATCH'])
def api_literature_edit(lit_id):
    """Редактирование литературы: title/chapter/pages/url/description/local_path."""
    global _meta
    data = request.get_json() or {}
    meta = get_meta()
    lit = meta.get('literature', {})
    if lit_id not in lit:
        return jsonify({"error": "literature not found"}), 404
    _create_version_backup("literature_edit", f"Редактирование литературы: {lit_id}")
    item = lit[lit_id]
    if 'title' in data:
        item['title'] = (data.get('title') or '').strip()
    if 'chapter' in data:
        item['chapter'] = (data.get('chapter') or '').strip()
    if 'pages' in data:
        item['pages'] = (data.get('pages') or '').strip()
    if 'url' in data:
        item['url'] = (data.get('url') or '').strip()
    if 'description' in data:
        item['description'] = (data.get('description') or '').strip()
    if 'local_path' in data:
        item['local_path'] = (data.get('local_path') or '').strip()
    save_meta(meta)
    return jsonify({"id": lit_id, "title": item.get("title", lit_id)})


@app.route('/api/literature/<lit_id>', methods=['DELETE'])
def api_literature_delete(lit_id):
    """Удаление литературы: удаляет из каталога и убирает привязки (resource_ids) из всех шаблонов."""
    global _meta
    meta = get_meta()
    lit = meta.get('literature', {})
    if lit_id not in lit:
        return jsonify({"error": "literature not found"}), 404
    _create_version_backup("literature_delete", f"Удаление литературы: {lit_id}")
    templates = meta.get('action_templates', {})
    removed = 0
    for tid, t in templates.items():
        rids = t.get('resource_ids', [])
        if lit_id in rids:
            t['resource_ids'] = [r for r in rids if r != lit_id]
            removed += 1
    del lit[lit_id]
    if _is_db_mode():
        mongo_delete_literature_item(lit_id)
    save_meta(meta)
    return jsonify({"id": lit_id, "removed_from_templates": removed})


@app.route('/api/literature/<lit_id>/link', methods=['POST'])
def api_literature_link(lit_id):
    """Привязка литературы к листам (по path). Добавляет lit_id в resource_ids шаблонов этих листов."""
    global _meta
    data = request.get_json() or {}
    leaf_paths = data.get('leaf_paths') or []
    if not leaf_paths:
        return jsonify({"error": "leaf_paths required"}), 400
    meta = get_meta()
    if lit_id not in meta.get('literature', {}):
        return jsonify({"error": "literature not found"}), 404
    _create_version_backup("literature_link", f"Привязка литературы: {lit_id}")
    templates = meta.setdefault('action_templates', {})
    tree = get_tree()
    updated = 0
    for path_str in leaf_paths:
        try:
            path = [int(x) for x in str(path_str).strip("/").split("/") if x.strip()]
        except ValueError:
            continue
        node = get_node_by_path(tree, path)
        if not node or node.get('children'):
            continue
        tid = node.get('template_id')
        if not tid or tid not in templates:
            continue
        rids = templates[tid].setdefault('resource_ids', [])
        if lit_id not in rids:
            rids.append(lit_id)
            updated += 1
    save_meta(meta)
    return jsonify({"updated": updated})


@app.route('/api/literature/<lit_id>/unlink', methods=['POST'])
def api_literature_unlink(lit_id):
    """Отвязка литературы от листов (по path): удаляет lit_id из resource_ids шаблонов."""
    global _meta
    data = request.get_json() or {}
    leaf_paths = data.get('leaf_paths') or []
    if not leaf_paths:
        return jsonify({"error": "leaf_paths required"}), 400
    meta = get_meta()
    if lit_id not in meta.get('literature', {}):
        return jsonify({"error": "literature not found"}), 404
    _create_version_backup("literature_unlink", f"Отвязка литературы: {lit_id}")
    templates = meta.setdefault('action_templates', {})
    tree = get_tree()
    updated = 0
    for path_str in leaf_paths:
        try:
            path = [int(x) for x in str(path_str).strip("/").split("/") if x.strip()]
        except ValueError:
            continue
        node = get_node_by_path(tree, path)
        if not node or node.get('children'):
            continue
        tid = node.get('template_id')
        if not tid or tid not in templates:
            continue
        rids = templates[tid].setdefault('resource_ids', [])
        if lit_id in rids:
            templates[tid]['resource_ids'] = [rid for rid in rids if rid != lit_id]
            updated += 1
    save_meta(meta)
    return jsonify({"updated": updated})


# Типы контента, которые считаем файлами для скачивания (не веб-страницы)
_DOWNLOADABLE_CONTENT_TYPES = (
    'application/pdf', 'application/octet-stream', 'application/x-pdf',
    'application/msword', 'application/vnd.openxmlformats-officedocument.',
    'application/zip', 'application/x-rar', 'application/epub+zip',
    'image/', 'audio/', 'video/', 'text/csv', 'text/plain',
)


def _is_downloadable_content_type(ct):
    """Проверяет, является ли Content-Type скачиваемым файлом (не веб-страница)."""
    if not ct:
        return False
    ct_lower = ct.lower().split(';')[0].strip()
    if ct_lower.startswith(('text/html', 'application/xhtml', 'text/xml')):
        return False
    for prefix in _DOWNLOADABLE_CONTENT_TYPES:
        if ct_lower.startswith(prefix):
            return True
    return False


@app.route('/api/literature/<lit_id>/download', methods=['POST'])
def api_literature_download(lit_id):
    """Скачивает файл по URL в каталог data/library и проставляет local_path у записи литературы."""
    import urllib.request
    import urllib.parse
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    meta = get_meta()
    if lit_id not in meta.get('literature', {}):
        return jsonify({"error": "literature not found"}), 404
    _create_version_backup("literature_download", f"Скачивание литературы по URL: {lit_id}")
    lib_dir = _literature_dir()
    try:
        import ssl
        cfg = load_app_config()
        ssl_verify = cfg.get("ssl_verify", True)
        if os.environ.get("DE_MATRIX_SSL_VERIFY", "").lower() in ("0", "false", "no"):
            ssl_verify = False
        ssl_ca_bundle = cfg.get("ssl_ca_bundle") or os.environ.get("DE_MATRIX_SSL_CA_BUNDLE")

        if not ssl_verify:
            ctx = ssl._create_unverified_context()
        elif ssl_ca_bundle and os.path.isfile(ssl_ca_bundle):
            ctx = ssl.create_default_context(cafile=ssl_ca_bundle)
        else:
            # Системные сертификаты (включая корпоративные CA в корпоративных сетях)
            ctx = ssl.create_default_context()

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            content_type = resp.headers.get('Content-Type', '')
            if not _is_downloadable_content_type(content_type):
                resp.read()  # consume and close
                return jsonify({
                    "error": "Файлов для скачивания не найдено. Ссылка ведёт на веб-страницу.",
                    "preview_url": url,
                }), 400
            content = resp.read()
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".pdf"
        safe_id = re.sub(r'[^\w\-]', '_', lit_id)[:50]
        filename = f"{safe_id}{ext}"
        filepath = os.path.join(lib_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(content)
        rel_path = os.path.relpath(filepath, BASE_DIR)
        meta['literature'][lit_id]['local_path'] = rel_path
        save_meta(meta)
        return jsonify({"local_path": rel_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/domains')
def api_domains():
    """Структура доменов и навыков для выбора целевой ветки при догрузке."""
    _ensure_db_schema()
    with db_session() as session:
        out = list_domains_from_db(session)
    return jsonify({"ok": True, "domains": out})


@app.route('/api/domain/<int:domain_idx>')
def api_domain(domain_idx):
    """Полные данные домена для вью дерева (слева направо)."""
    matrix = get_matrix()
    domains = (matrix or {}).get("domains") or []
    if domain_idx < 0 or domain_idx >= len(domains):
        return jsonify({"ok": False, "error": "Domain not found"}), 404
    d = domains[domain_idx]
    domain_color = get_domain_color(d.get("name", ""))
    domain_icon = get_domain_icon(d.get("name", ""), domain_idx)
    out = {
        "ok": True,
        "domain": {
            "index": domain_idx,
            "name": d.get("name", ""),
            "color": domain_color,
            "icon": domain_icon,
            "skills": []
        }
    }
    for si, s in enumerate(d.get("skills", [])):
        skill_color = get_skill_color(s.get("name", ""), domain_color, si)
        skill_icon = get_skill_icon(s.get("name", ""), si)
        skill_data = {
            "index": si,
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "color": skill_color,
            "icon": skill_icon,
            "actions": []
        }
        for ai, a in enumerate(s.get("actions", [])):
            action_data = {
                "index": ai,
                "text": a.get("text", ""),
                "template_id": a.get("template_id"),
                "subactions": []
            }
            for subi, sub in enumerate(a.get("subactions", [])):
                action_data["subactions"].append({
                    "index": subi,
                    "text": sub.get("text", ""),
                    "leaf_path": f"{domain_idx}/{si}/{ai}/{subi}"
                })
            if not action_data["subactions"]:
                action_data["leaf_path"] = f"{domain_idx}/{si}/{ai}"
            skill_data["actions"].append(action_data)
        out["domain"]["skills"].append(skill_data)
    return jsonify(out)


@app.route('/api/sources')
def api_sources():
    """DB-only источник данных для рантайма."""
    return jsonify({
        "source_dir": "db://postgres",
        "files": ["db://postgres"],
        "current": "db://postgres",
    })


@app.route('/api/import/template')
def api_import_template():
    """Скачивание пустого шаблона Excel для импорта (единый формат с экспортом)."""
    try:
        from openpyxl import Workbook
        from io import BytesIO
    except ImportError:
        return jsonify({"error": "openpyxl не установлен (pip install openpyxl)"}), 500
    wb = Workbook()
    ws = wb.active
    ws.title = "Матрица навыков"
    ws.append(["Domain", "Skill", "Action", "Subaction", "Description", "Template ID", "Level Tag", "Review Questions"])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    from flask import send_file
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="matrix_import_template.xlsx",
    )


@app.route('/api/source/upload/preview', methods=["POST"])
def api_source_upload_preview():
    """Предпросмотр догрузки: парсинг файла без сохранения, возврат preview + validation."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Файл не передан"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Файл не выбран"}), 400
    ext = (os.path.splitext(f.filename)[1] or "").lower()
    if ext not in (".json", ".xlsx", ".xls"):
        return jsonify({"ok": False, "error": "Поддерживаются только JSON и Excel"}), 400

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        try:
            if ext == ".json":
                with open(tmp_path, "r", encoding="utf-8") as fp:
                    upload_data = json.load(fp)
            else:
                upload_data = load_excel(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "validation": {"ok": False, "errors": [str(e)]}}), 400

    from core.loaders import _normalize_unified
    from core.schema import validate_source
    upload_data = _normalize_unified(upload_data)
    vr = validate_source(upload_data)

    # Preview: плоская таблица для отображения
    preview_rows = []
    for d in upload_data.get("domains") or []:
        d_name = d.get("name") or ""
        for s in d.get("skills") or []:
            s_name = s.get("name") or ""
            for a in s.get("actions") or []:
                preview_rows.append({
                    "domain": d_name,
                    "skill": s_name,
                    "action": a.get("text") or "",
                    "subaction": "",
                    "template_id": a.get("template_id"),
                    "level_tag": a.get("level_tag") or "",
                    "review_questions": "; ".join(a.get("review_questions") or []),
                })
                for sub in a.get("subactions") or []:
                    preview_rows.append({
                        "domain": d_name,
                        "skill": s_name,
                        "action": a.get("text") or "",
                        "subaction": sub.get("text") or "",
                        "template_id": sub.get("template_id"),
                        "level_tag": sub.get("level_tag") or "",
                        "review_questions": "; ".join(sub.get("review_questions") or []),
                    })

    return jsonify({
        "ok": True,
        "preview": preview_rows,
        "validation": vr.to_dict(),
        "domains_count": len(upload_data.get("domains") or []),
    })


@app.route('/api/source/upload', methods=["POST"])
def api_source_upload():
    """Догрузка данных из JSON/Excel только в approval pipeline (submit-only)."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Файл не передан (ожидается поле 'file')"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Файл не выбран"}), 400
    ext = (os.path.splitext(f.filename)[1] or "").lower()
    if ext not in (".json", ".xlsx", ".xls"):
        return jsonify({"ok": False, "error": "Поддерживаются только JSON и Excel (.json, .xlsx, .xls)"}), 400

    merge_mode = (request.form.get("merge_mode") or "append").strip()
    target_domain = (request.form.get("target_domain") or "").strip() or None
    target_skill = (request.form.get("target_skill") or "").strip() or None
    if merge_mode not in ("append", "append_to_domain", "append_to_skill", "replace_domain", "replace_skill", "replace_all"):
        merge_mode = "append"
    if merge_mode == "append_to_domain" and not target_domain:
        return jsonify({"ok": False, "error": "Для режима «В домен» укажите target_domain"}), 400
    if merge_mode == "append_to_skill" and (not target_domain or not target_skill):
        return jsonify({"ok": False, "error": "Для режима «В навык» укажите target_domain и target_skill"}), 400

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        try:
            if ext == ".json":
                with open(tmp_path, "r", encoding="utf-8") as fp:
                    upload_data = json.load(fp)
            else:
                upload_data = load_excel(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка чтения файла: {e}"}), 400

    try:
        _ensure_db_schema()
        actor, _ = _extract_actor_role()
        with db_session() as session:
            current_unified = load_unified_from_db(session, literature=load_literature_map())
            current_projection = load_tree_projection(session)
            staging_batch = create_staging_batch(
                session,
                source_filename=f.filename or "upload",
                merge_mode=merge_mode,
                created_by=actor,
                payload=upload_data,
                target_domain=target_domain,
                target_skill=target_skill,
            )
            staging_batch_id = staging_batch.id
            staging_projection = load_staging_tree_projection(session, staging_batch_id)
            merged = merge_upload_into_source(
                current_unified, upload_data,
                merge_mode=merge_mode,
                target_domain=target_domain,
                target_skill=target_skill,
            )
        revision_payload = build_revision_payload(
            base_snapshot={"domains": current_projection.get("domains") or []},
            upload_payload=upload_data,
            proposed_snapshot={"domains": merged.get("domains") or []},
            merge_mode=merge_mode,
            target_domain=target_domain,
            target_skill=target_skill,
        )
        revision_payload["staging_batch_id"] = staging_batch_id
        revision_payload["staging_tree"] = staging_projection
        title = f"Upload {f.filename}"
        with db_session() as session:
            cr = create_change_request(
                session=session,
                title=title,
                merge_mode=merge_mode,
                payload=revision_payload,
                staging_batch_id=staging_batch_id,
                created_by=actor,
                target_domain=target_domain,
                target_skill=target_skill,
            )
            approval_set_status(session, cr.id, "submitted", actor=actor, comment="Uploaded and submitted for review")
            _notify_cr_submitted(session, cr)
            change_id = cr.id
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({
        "ok": True,
        "queued_for_approval": True,
        "message": "Изменения отправлены на апрув и еще не применены к матрице",
        "change_id": change_id,
        "staging_batch_id": staging_batch_id,
        "merge_mode": merge_mode,
        "approval_required": storage_approval_required(),
    })


@app.route('/api/source/load', methods=["POST"])
def api_source_load():
    """DB-only рантайм: выбор file source отключен."""
    return jsonify({"ok": False, "error": "DB-only mode: source file switching is disabled"}), 400


@app.route('/api/backups')
def api_backups():
    """Список бэкапов конфига и источника."""
    if _is_db_mode():
        return jsonify({
            "ok": True,
            "backups": [],
            "mode": "db",
            "message": "Use scripts/db_backup.sh for PostgreSQL+Mongo backups",
        })
    source_file = _current_source_for_backup()
    if source_file:
        ensure_stable_backup(
            base_dir=PathLib(BASE_DIR),
            config_dir=PathLib(BASE_DIR) / "config",
            source_dir=PathLib(_source_dir_path()),
            source_filename=source_file,
            checkpoint_path=_checkpoint_path(),
        )
    backups = list_backups(PathLib(BASE_DIR))
    return jsonify({"ok": True, "backups": backups})


@app.route('/api/backups/<backup_id>/compatibility')
def api_backup_compatibility(backup_id):
    """Проверка совместимости бэкапа с текущей схемой."""
    if _is_db_mode():
        return jsonify({
            "ok": False,
            "error": "DB mode: file backup compatibility is not applicable",
        }), 400
    compatible, warning = check_backup_compatibility(PathLib(BASE_DIR), backup_id)
    return jsonify({
        "ok": True,
        "backup_id": backup_id,
        "compatible": compatible,
        "warning": warning,
    })


@app.route('/api/backups/<backup_id>/mark-stable', methods=["POST"])
def api_mark_stable(backup_id):
    """Помечает выбранный бэкап как стабильное состояние."""
    if _is_db_mode():
        return jsonify({
            "ok": False,
            "error": "DB mode: use database-level backup policies",
        }), 400
    backups = list_backups(PathLib(BASE_DIR))
    exists = any(b.get("id") == backup_id for b in backups)
    if not exists:
        return jsonify({"ok": False, "error": "Backup not found"}), 404
    if not set_stable_backup_id(PathLib(BASE_DIR), backup_id):
        return jsonify({"ok": False, "error": "Не удалось сохранить stable-состояние"}), 500
    return jsonify({"ok": True, "stable_backup_id": backup_id})


@app.route('/api/restore', methods=["POST"])
def api_restore():
    """Восстановление из бэкапа: перезапись config и source, перезагрузка данных."""
    if _is_db_mode():
        return jsonify({
            "ok": False,
            "error": "DB mode: use scripts/db_restore.sh",
        }), 400
    data = request.get_json() or {}
    backup_id = (data.get("backup_id") or data.get("id") or "").strip()
    force = bool(data.get("force"))
    if not backup_id:
        return jsonify({"ok": False, "error": "backup_id required"}), 400

    compatible, warning = check_backup_compatibility(PathLib(BASE_DIR), backup_id)
    if not compatible and not force:
        return jsonify({
            "ok": False,
            "error": "Несовместимость схемы",
            "warning": warning,
            "force_required": True,
        }), 409

    config_dir = PathLib(BASE_DIR) / "config"
    source_dir = PathLib(_source_dir_path())
    _create_version_backup("restore_before", f"Перед восстановлением backup_{backup_id}")
    if not restore_backup(PathLib(BASE_DIR), config_dir, source_dir, backup_id):
        return jsonify({"ok": False, "error": "Backup not found or restore failed"}), 404
    invalidate_metadata_cache()
    _invalidate_caches()
    get_matrix()
    get_tree()
    return jsonify({
        "ok": True,
        "message": "Данные восстановлены из бэкапа, конфиг и источник обновлены",
        "backup_id": backup_id,
    })


@app.route('/api/restore/stable', methods=["POST"])
def api_restore_stable():
    """Откат к стабильному состоянию (stable backup)."""
    if _is_db_mode():
        return jsonify({
            "ok": False,
            "error": "DB mode: use scripts/db_restore.sh",
        }), 400
    stable_id = get_stable_backup_id(PathLib(BASE_DIR))
    if not stable_id:
        return jsonify({"ok": False, "error": "Стабильное состояние не задано"}), 404
    force = bool((request.get_json() or {}).get("force"))
    # Повторяем логику api_restore для стабильного backup id
    compatible, warning = check_backup_compatibility(PathLib(BASE_DIR), stable_id)
    if not compatible and not force:
        return jsonify({
            "ok": False,
            "error": "Несовместимость схемы",
            "warning": warning,
            "force_required": True,
        }), 409
    config_dir = PathLib(BASE_DIR) / "config"
    source_dir = PathLib(_source_dir_path())
    _create_version_backup("restore_before", f"Перед восстановлением stable backup_{stable_id}")
    if not restore_backup(PathLib(BASE_DIR), config_dir, source_dir, stable_id):
        return jsonify({"ok": False, "error": "Stable backup not found or restore failed"}), 404
    invalidate_metadata_cache()
    _invalidate_caches()
    get_matrix()
    get_tree()
    return jsonify({"ok": True, "backup_id": stable_id, "message": "Восстановлено стабильное состояние"})


@app.route('/api/restore/last-change', methods=["POST"])
def api_restore_last_change():
    if _is_db_mode():
        return jsonify({
            "ok": False,
            "error": "DB mode: use approval rollback/change flow instead",
        }), 400
    """
    Откат последнего изменения.
    Так как бэкап создаётся перед мутацией, достаточно восстановить самый свежий бэкап.
    """
    backups = list_backups(PathLib(BASE_DIR))
    if not backups:
        return jsonify({"ok": False, "error": "Нет доступных бэкапов"}), 404
    last_id = backups[0]["id"]
    compatible, warning = check_backup_compatibility(PathLib(BASE_DIR), last_id)
    force = bool((request.get_json() or {}).get("force"))
    if not compatible and not force:
        return jsonify({
            "ok": False,
            "error": "Несовместимость схемы",
            "warning": warning,
            "force_required": True,
        }), 409
    config_dir = PathLib(BASE_DIR) / "config"
    source_dir = PathLib(_source_dir_path())
    _create_version_backup("restore_before", f"Перед откатом последнего изменения backup_{last_id}")
    if not restore_backup(PathLib(BASE_DIR), config_dir, source_dir, last_id):
        return jsonify({"ok": False, "error": "Backup not found or restore failed"}), 404
    invalidate_metadata_cache()
    _invalidate_caches()
    get_matrix()
    get_tree()
    return jsonify({"ok": True, "backup_id": last_id, "message": "Откат выполнен по последнему изменению"})


@app.route('/api/reload')
def api_reload():
    """Перезагрузка: сброс кэша и повторная сверка источника с чекпоинтом (при изменении файла или для autoscale)."""
    source_file = _current_source_for_backup()
    if source_file:
        _create_version_backup("reload", "Ручная перезагрузка данных")
    _invalidate_caches()
    get_matrix()
    get_tree()
    return jsonify({"ok": True, "message": "Кэш сброшен, данные загружены из источника/чекпоинта"})


@app.route('/api/autoscale/check')
def api_autoscale_check():
    """Проверка согласованности leaf-структуры matrix и tree (автоскейл)."""
    matrix = get_matrix() or {"domains": []}
    tree = get_tree() or []
    expected = sorted(_expected_leaf_paths_from_matrix(matrix))
    actual = sorted("/".join(str(x) for x in (leaf.get("path") or [])) for leaf in collect_leaves(tree))
    expected_set = set(expected)
    actual_set = set(actual)
    missing_in_tree = sorted(expected_set - actual_set)
    extra_in_tree = sorted(actual_set - expected_set)
    return jsonify({
        "ok": len(missing_in_tree) == 0 and len(extra_in_tree) == 0,
        "expected_leaf_count": len(expected),
        "actual_leaf_count": len(actual),
        "missing_in_tree_count": len(missing_in_tree),
        "extra_in_tree_count": len(extra_in_tree),
        "missing_in_tree_sample": missing_in_tree[:20],
        "extra_in_tree_sample": extra_in_tree[:20],
    })


# ----- ОТЛАДОЧНЫЕ МАРШРУТЫ -----

@app.route('/debug')
def debug():
    cfg = get_meta()
    checkpoint = load_checkpoint(PathLib(_checkpoint_path()))
    return jsonify({
        "source_dir": cfg.get("source_dir"),
        "checkpoint_file": cfg.get("checkpoint_file"),
        "current_source": checkpoint.get("source_file") if checkpoint else None,
        "literature_dir": cfg.get("literature_dir"),
        "config": "config/settings.yaml (пути); мета — из единого источника (файл в source_dir)",
        "matrix_keys": list(get_matrix().keys()),
        "meta_keys": [k for k in cfg.keys() if k not in ("source_dir", "checkpoint_file", "literature_dir", "flexible")],
    })

# ----- СТАТИЧЕСКИЕ ФАЙЛЫ И ОБРАБОТКА ОШИБОК -----

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory('static', path)


@app.route('/library/<path:filename>')
def library_file(filename):
    """Раздача файлов из data/library для предпросмотра."""
    if ".." in filename:
        abort(404)
    lib_dir = PathLib(_literature_dir())
    path = (lib_dir / filename).resolve()
    lib_resolved = lib_dir.resolve()
    if not str(path).startswith(str(lib_resolved)) or path == lib_resolved:
        abort(404)
    if not path.exists() or not path.is_file():
        abort(404)
    rel = path.relative_to(lib_resolved)
    return send_from_directory(lib_dir, str(rel))

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Data Engineer Matrix')
    parser.add_argument('--port', type=int, default=5001, help='Port to run on (5000 on macOS often used by AirPlay)')
    parser.add_argument('--auto-port', action='store_true', help='Find free port automatically')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()

    os.makedirs('data', exist_ok=True)
    os.makedirs('data/sources', exist_ok=True)
    os.makedirs('data/backups', exist_ok=True)
    os.makedirs('config', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('templates', exist_ok=True)

    # Единый источник: data/sources/matrix.json (или другой файл из source_dir). Чекпоинт — data/checkpoint.yaml
    if _is_db_mode():
        _ensure_db_schema()

    port = args.port
    if args.auto_port:
        port = find_free_port(args.port)
        if not port:
            print("❌ Не найдено свободных портов")
            sys.exit(1)

    debug_mode = args.debug or os.environ.get("DE_MATRIX_DEBUG", "0").strip().lower() in ("1", "true", "yes")
    print(f"\n🚀 Запуск на порту {port}")
    print(f"📊 Матрица: http://localhost:{port}")
    print(f"📈 Граф: http://localhost:{port}/graph")
    print(f"📋 Экспорт: http://localhost:{port}/export")
    print(f"🔧 Отладка: http://localhost:{port}/debug\n")

    app.run(debug=debug_mode, use_reloader=debug_mode, host='0.0.0.0', port=port)