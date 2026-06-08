#!/usr/bin/env python3
"""DCI vector sync v9: delta-first handoff, incremental sync, local TEI embeddings."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_DIR = REPO_ROOT / ".cursor" / "context"
DIALOGS_DIR = CONTEXT_DIR / "dialogs"
PROJECT_CATALOG = CONTEXT_DIR / "project_catalog.md"
PROJECTS_REGISTRY = REPO_ROOT / ".cursor" / "dci" / "projects.registry"
PROJECT_LOCK = CONTEXT_DIR / ".project_lock"
WINDOW_LOCK = CONTEXT_DIR / ".dialog_window_lock"
LEGACY_INDEX = CONTEXT_DIR / "dialog_index.md"
FALLBACK_PATH = CONTEXT_DIR / "vector_fallback.jsonl"
EMBED_DIM = 384
MASTER_EV_ID = "EV-PROJECT"
DEFAULT_WINDOW = "DW-001"


@dataclass
class LedgerRecord:
    ledger_id: str
    ledger_type: str
    content: str
    team: str = "none"
    branch_state: str = ""
    status: str = "active"
    domain: str = ""
    scope: str = "window"
    metadata: Dict[str, Any] | None = None

    def embed_text(self) -> str:
        return self.content.strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def resolve_project_id() -> str:
    explicit = env("DCI_PROJECT_ID") or env("DCI_DIALOG_ID")
    if explicit:
        return explicit
    try:
        import subprocess

        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return Path(root).name
    except Exception:  # noqa: BLE001
        return REPO_ROOT.name


def parse_header_field(text: str, field: str, limit: int = 40) -> str:
    pattern = rf"^{re.escape(field)}:\s*(\S+)"
    for line in text.splitlines()[:limit]:
        m = re.match(pattern, line.strip())
        if m:
            return m.group(1)
    return ""


def parse_header_value(text: str, field: str, limit: int = 40) -> str:
    pattern = rf"^{re.escape(field)}:\s*(.+)$"
    for line in text.splitlines()[:limit]:
        m = re.match(pattern, line.strip())
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def parse_session_slug(text: str) -> str:
    for line in text.splitlines()[:40]:
        if line.strip().startswith("session:"):
            body = line.split(":", 1)[1].strip()
            return body.split("|")[0].strip()
    return ""


def humanize_slug(slug: str) -> str:
    if not slug or slug.lower() in ("new", "none", "—", "-"):
        return ""
    words = slug.replace("_", "-").split("-")
    return " ".join(w.capitalize() if w.isascii() else w for w in words if w)


def truncate_text(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def parse_project_id_text(text: str) -> str:
    return parse_header_field(text, "project_id")


def read_project_lock() -> str:
    if not PROJECT_LOCK.is_file():
        return ""
    return parse_project_id_text(PROJECT_LOCK.read_text(encoding="utf-8"))


def write_project_lock(project_id: str) -> None:
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_LOCK.write_text(
        f"project_id: {project_id}\nlocked_at: {utc_now()}\n",
        encoding="utf-8",
    )


def read_window_lock() -> str:
    if not WINDOW_LOCK.is_file():
        return ""
    return parse_header_field(WINDOW_LOCK.read_text(encoding="utf-8"), "dialog_window_id")


def write_window_lock(dialog_window_id: str) -> None:
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    WINDOW_LOCK.write_text(
        f"dialog_window_id: {dialog_window_id}\nlocked_at: {utc_now()}\n",
        encoding="utf-8",
    )


def resolve_dialog_window_id() -> str:
    explicit = env("DCI_DIALOG_WINDOW_ID")
    if explicit:
        return explicit
    locked = read_window_lock()
    if locked:
        return locked
    if PROJECT_CATALOG.is_file():
        active = parse_header_field(PROJECT_CATALOG.read_text(encoding="utf-8"), "active_window")
        if active:
            return active
    return DEFAULT_WINDOW


def project_root_path(root: Optional[Path] = None) -> Path:
    return root or REPO_ROOT


def catalog_path_for_root(root: Optional[Path] = None) -> Path:
    return project_root_path(root) / ".cursor" / "context" / "project_catalog.md"


def dialogs_dir_for_root(root: Optional[Path] = None) -> Path:
    return project_root_path(root) / ".cursor" / "context" / "dialogs"


def window_dir(dialog_window_id: Optional[str] = None, root: Optional[Path] = None) -> Path:
    return dialogs_dir_for_root(root) / (dialog_window_id or resolve_dialog_window_id())


def window_index_path(dialog_window_id: Optional[str] = None, root: Optional[Path] = None) -> Path:
    return window_dir(dialog_window_id, root) / "dialog_index.md"


def window_bundle_path(dialog_window_id: Optional[str] = None) -> Path:
    return window_dir(dialog_window_id) / "dialog_bundle.md"


def window_meta_path(dialog_window_id: Optional[str] = None) -> Path:
    return window_dir(dialog_window_id) / "vector_index.meta.md"


def project_scope_id() -> str:
    return resolve_project_id()


def vector_namespace(dialog_window_id: Optional[str] = None) -> str:
    return f"{project_scope_id()}/{dialog_window_id or resolve_dialog_window_id()}"


def project_vector_namespace() -> str:
    return f"{project_scope_id()}/__project__"


def _fail_scope(action: str, detail: str) -> None:
    print(
        f"ERROR scope mismatch on {action}: {detail}. "
        f"Refuse cross-project/window context. Do not load foreign index into chat.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def parse_index_project_id(path: Optional[Path] = None) -> str:
    if PROJECT_CATALOG.is_file():
        pid = parse_project_id_text(PROJECT_CATALOG.read_text(encoding="utf-8"))
        if pid:
            return pid
    idx = path or window_index_path()
    if idx.is_file():
        return parse_project_id_text(idx.read_text(encoding="utf-8"))
    if LEGACY_INDEX.is_file():
        return parse_project_id_text(LEGACY_INDEX.read_text(encoding="utf-8"))
    return ""


def parse_index_window_id(path: Optional[Path] = None) -> str:
    idx = path or window_index_path()
    if not idx.is_file():
        return ""
    return parse_header_field(idx.read_text(encoding="utf-8"), "dialog_window_id")


def validate_project_scope(action: str = "access") -> str:
    current = resolve_project_id()
    indexed = parse_index_project_id()
    locked = read_project_lock()
    if indexed and indexed != current:
        _fail_scope(action, f"index={indexed} current={current}")
    if locked and locked != current:
        _fail_scope(action, f"lock={locked} current={current}")
    if indexed and locked and indexed != locked:
        _fail_scope(action, f"index={indexed} lock={locked}")
    if indexed == current and not locked:
        write_project_lock(current)
    return current


def validate_window_scope(action: str = "access", dialog_window_id: Optional[str] = None) -> str:
    validate_project_scope(action)
    current = dialog_window_id or resolve_dialog_window_id()
    locked = read_window_lock()
    indexed = parse_index_window_id(window_index_path(current))
    if locked and locked != current:
        _fail_scope(action, f"window_lock={locked} current={current}")
    if indexed and indexed != current:
        _fail_scope(action, f"window_index={indexed} current={current}")
    if indexed == current and not locked:
        write_window_lock(current)
    return current


def assert_project_scope(action: str = "access") -> str:
    return validate_project_scope(action)


def assert_window_scope(action: str = "access", dialog_window_id: Optional[str] = None) -> str:
    return validate_window_scope(action, dialog_window_id)


def project_dialog_ids() -> List[str]:
    """All valid pgvector dialog_id namespaces for the current repo."""
    pid = project_scope_id()
    ids: List[str] = [project_vector_namespace(), pid]
    if DIALOGS_DIR.is_dir():
        for child in sorted(DIALOGS_DIR.iterdir()):
            if re.match(r"DW-\d+$", child.name):
                ids.append(vector_namespace(child.name))
    return sorted(set(ids))


def cleanup_stale_vectors() -> int:
    """Drop orphan rows for **current project only** (safe on shared pgvector)."""
    pid = project_scope_id()
    prefix = f"{pid}/"
    allowed = project_dialog_ids()
    ok, _ = db_ping()
    if not ok:
        return 0
    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM dci_embeddings
                    WHERE (dialog_id = %s OR dialog_id LIKE %s)
                      AND NOT (dialog_id = ANY(%s))
                    """,
                    (pid, prefix + "%", allowed),
                )
                deleted = cur.rowcount
            conn.commit()
        if deleted:
            print(f"cleaned stale vector namespaces for {pid}: {deleted} row(s)")
        return deleted
    except Exception as exc:  # noqa: BLE001
        print(f"WARN cleanup stale vectors: {exc}", file=sys.stderr)
        return 0


def load_dotenv_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def db_config() -> dict:
    return {
        "host": env("DCI_VECTOR_HOST", "localhost"),
        "port": int(env("DCI_VECTOR_PORT", "5433")),
        "dbname": env("DCI_VECTOR_DB", "dci_vectors"),
        "user": env("DCI_VECTOR_USER", "dci"),
        "password": env("DCI_VECTOR_PASSWORD", "dci_local"),
        "connect_timeout": int(env("DCI_DB_CONNECT_TIMEOUT", "3")),
    }


def window_delta_path(dialog_window_id: Optional[str] = None) -> Path:
    return window_dir(dialog_window_id) / "dialog_delta.md"


def window_snapshot_path(dialog_window_id: Optional[str] = None) -> Path:
    return window_dir(dialog_window_id) / ".compress_snapshot.json"


def project_snapshot_path() -> Path:
    return CONTEXT_DIR / ".compress_snapshot.project.json"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_records(records: List[LedgerRecord]) -> Dict[str, Dict[str, str]]:
    snap: Dict[str, Dict[str, str]] = {}
    for rec in records:
        snap[rec.ledger_id] = {
            "ledger_type": rec.ledger_type,
            "content": rec.content,
            "status": rec.status,
            "hash": content_hash(rec.content),
        }
    return snap


def load_snapshot(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_snapshot(path: Path, snapshot: Dict[str, Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_delta(
    before: Dict[str, Dict[str, str]],
    after: Dict[str, Dict[str, str]],
) -> Dict[str, List[str]]:
    new_or_updated: List[str] = []
    superseded: List[str] = []
    unchanged: List[str] = []
    all_ids = set(before) | set(after)
    for lid in sorted(all_ids):
        if lid not in before:
            new_or_updated.append(lid)
        elif lid not in after:
            superseded.append(lid)
        elif before[lid].get("hash") != after[lid].get("hash"):
            new_or_updated.append(lid)
        else:
            unchanged.append(lid)
    return {
        "new_or_updated": new_or_updated,
        "superseded": superseded,
        "unchanged": unchanged,
    }


def index_checksum(snapshot: Dict[str, Dict[str, str]]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    return f"sha256:{content_hash(canonical)[:16]}"


def parse_delta_list(text: str, field: str) -> List[str]:
    m = re.search(rf"^{re.escape(field)}:\s*\[(.*)\]", text, re.M)
    if not m:
        return []
    inner = m.group(1).strip()
    if not inner:
        return []
    return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]


def write_dialog_delta(
    dialog_window_id: str,
    window_delta: Dict[str, List[str]],
    project_delta: Dict[str, List[str]],
    checksum: str,
    since: str,
) -> Path:
    changed = sorted(set(window_delta["new_or_updated"] + project_delta.get("new_or_updated", [])))
    restore_cmd = f"/custom-rule: dci restore {dialog_window_id}"
    now = utc_now()
    body = f"""# Dialog Delta

since: {since}
compressed_at: {now}
dialog_window_id: {dialog_window_id}
handoff_ready: true
handoff_at: {now}
restore_command: "{restore_cmd}"
index_checksum: {checksum}
changed_ids: [{", ".join(changed)}]

## new_or_updated
{fmt_list(changed if changed else ["none"])}

## superseded
{fmt_list(window_delta.get("superseded", []) + project_delta.get("superseded", []))}

## project_delta
{fmt_list(project_delta.get("new_or_updated", []))}

## open_risks
- none
"""
    path = window_delta_path(dialog_window_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def hash_embed(text: str, dim: int = EMBED_DIM) -> List[float]:
    vec = [0.0] * dim
    for token in re.findall(r"[\w\u0400-\u04FF]+", text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for i, b in enumerate(digest):
            idx = (b + i) % dim
            vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def openai_embed(text: str, model: str, api_key: str) -> List[float]:
    payload = json.dumps({"input": text, "model": model, "dimensions": EMBED_DIM}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    vec = data["data"][0]["embedding"]
    if len(vec) != EMBED_DIM:
        raise ValueError(f"Expected {EMBED_DIM} dims, got {len(vec)}")
    return vec


def tei_ping() -> Tuple[bool, str]:
    base = env("DCI_EMBED_URL")
    if not base:
        return False, "DCI_EMBED_URL not set"
    base = base.rstrip("/")
    if base.endswith("/embed"):
        health_url = base[: -len("/embed")] + "/health"
    else:
        health_url = base + "/health"
    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, "ok"
            return False, f"status {resp.status}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def tei_embed(text: str) -> List[float]:
    url = env("DCI_EMBED_URL", "http://localhost:8081/embed")
    payload = json.dumps({"inputs": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    vec: List[float]
    if isinstance(data, list) and data:
        if isinstance(data[0], list):
            vec = [float(x) for x in data[0]]
        else:
            vec = [float(x) for x in data]
    else:
        raise ValueError(f"unexpected TEI response: {type(data)}")
    if len(vec) > EMBED_DIM:
        vec = vec[:EMBED_DIM]
    if len(vec) != EMBED_DIM:
        raise ValueError(f"Expected {EMBED_DIM} dims, got {len(vec)}")
    return vec


def embed_text(text: str) -> Tuple[List[float], str]:
    if env("DCI_EMBED_URL"):
        try:
            model = env("DCI_EMBED_MODEL", "intfloat/multilingual-e5-small")
            return tei_embed(text), f"tei:{model}"
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as exc:
            print(f"WARN tei embed failed ({exc}); trying next backend", file=sys.stderr)
    api_key = env("OPENAI_API_KEY")
    model = env("DCI_EMBEDDING_MODEL", "text-embedding-3-small")
    if api_key:
        try:
            return openai_embed(text, model, api_key), f"openai:{model}"
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
            print(f"WARN openai embed failed ({exc}); fallback to hash_embed", file=sys.stderr)
    return hash_embed(text), "hash_embed:384"


def desired_embed_source() -> str:
    if env("DCI_EMBED_URL"):
        ok, _ = tei_ping()
        if ok:
            model = env("DCI_EMBED_MODEL", "intfloat/multilingual-e5-small")
            return f"tei:{model}"
    api_key = env("OPENAI_API_KEY")
    if api_key:
        model = env("DCI_EMBEDDING_MODEL", "text-embedding-3-small")
        return f"openai:{model}"
    return "hash_embed:384"


def needs_reembed(stored_source: Optional[str], desired: str, force: bool) -> bool:
    if force:
        return True
    if not stored_source:
        return True
    if stored_source == desired:
        return False
    weak = stored_source.startswith("hash_embed")
    strong = desired.startswith("tei:") or desired.startswith("openai:")
    if weak and strong:
        return True
    return stored_source != desired


def last_embed_source(namespace: Optional[str] = None) -> str:
    rows = read_fallback(namespace)
    sources = {r.get("embed_source", "") for r in rows if r.get("embed_source")}
    if not sources:
        return desired_embed_source()
    for pref in ("tei:", "openai:", "hash_embed"):
        for src in sources:
            if src.startswith(pref) or src == pref:
                return src
    return next(iter(sources))


def get_db_content_hash(namespace: str, ledger_id: str) -> Optional[str]:
    hashes = get_db_content_hashes(namespace, [ledger_id])
    return hashes.get(ledger_id)


def get_db_embed_sources(namespace: str, ledger_ids: List[str]) -> Dict[str, str]:
    if not ledger_ids:
        return {}
    ok, _ = db_ping()
    if not ok:
        return {}
    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ledger_id, source FROM dci_embeddings "
                    "WHERE dialog_id = %s AND ledger_id = ANY(%s)",
                    (namespace, ledger_ids),
                )
                return {row[0]: row[1] for row in cur.fetchall() if row[1]}
    except Exception:  # noqa: BLE001
        return {}


def get_db_content_hashes(namespace: str, ledger_ids: List[str]) -> Dict[str, str]:
    if not ledger_ids:
        return {}
    ok, _ = db_ping()
    if not ok:
        return {}
    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ledger_id, metadata->>'content_hash' FROM dci_embeddings "
                    "WHERE dialog_id = %s AND ledger_id = ANY(%s)",
                    (namespace, ledger_ids),
                )
                return {str(row[0]): str(row[1]) for row in cur.fetchall() if row[1]}
    except Exception:  # noqa: BLE001
        return {}


def db_connect():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    return psycopg2.connect(**db_config())


def db_ping() -> Tuple[bool, str]:
    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                row = cur.fetchone()
                if not row:
                    return False, "vector extension missing"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def upsert_db(record: LedgerRecord, embedding: Sequence[float], source: str, namespace: str) -> None:
    meta = dict(record.metadata or {})
    meta["project_id"] = project_scope_id()
    meta["scope"] = record.scope
    meta["content_hash"] = content_hash(record.content)
    if record.scope == "window":
        meta["dialog_window_id"] = namespace.split("/", 1)[-1]
    vec_literal = "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"
    sql = """
        INSERT INTO dci_embeddings (
            ledger_id, dialog_id, ledger_type, team, branch_state, status, domain,
            content, embedding, metadata, source, updated_at
        ) VALUES (
            %(ledger_id)s, %(dialog_id)s, %(ledger_type)s, %(team)s, %(branch_state)s,
            %(status)s, %(domain)s, %(content)s, %(embedding)s::vector, %(metadata)s::jsonb,
            %(source)s, now()
        )
        ON CONFLICT (dialog_id, ledger_id) DO UPDATE SET
            ledger_type = EXCLUDED.ledger_type,
            team = EXCLUDED.team,
            branch_state = EXCLUDED.branch_state,
            status = EXCLUDED.status,
            domain = EXCLUDED.domain,
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            metadata = EXCLUDED.metadata,
            source = EXCLUDED.source,
            updated_at = now()
    """
    params = {
        "ledger_id": record.ledger_id,
        "dialog_id": namespace,
        "ledger_type": record.ledger_type,
        "team": record.team,
        "branch_state": record.branch_state,
        "status": record.status,
        "domain": record.domain,
        "content": record.content,
        "embedding": vec_literal,
        "metadata": json.dumps(meta, ensure_ascii=False),
        "source": source,
    }
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cur.execute(
                "INSERT INTO dci_sync_log (action, detail) VALUES (%s, %s::jsonb)",
                ("upsert", json.dumps({"ledger_id": record.ledger_id, "namespace": namespace})),
            )
        conn.commit()


def to_fallback_row(
    record: LedgerRecord,
    embedding: Sequence[float],
    namespace: str,
    synced_to_db: bool = False,
    embed_source: str = "hash_embed:384",
) -> dict:
    dw = namespace.split("/", 1)[-1] if record.scope == "window" else ""
    meta = dict(record.metadata or {})
    meta["content_hash"] = content_hash(record.content)
    return {
        "ledger_id": record.ledger_id,
        "ledger_type": record.ledger_type,
        "dialog_id": namespace,
        "project_id": project_scope_id(),
        "dialog_window_id": dw,
        "scope": record.scope,
        "team": record.team,
        "branch_state": record.branch_state,
        "status": record.status,
        "domain": record.domain,
        "content": record.content,
        "embedding": list(embedding),
        "metadata": meta,
        "embed_source": embed_source,
        "synced_to_db": synced_to_db,
        "updated_at": utc_now(),
    }


def read_fallback(namespace: Optional[str] = None) -> List[dict]:
    if not FALLBACK_PATH.is_file():
        return []
    pid = project_scope_id()
    ns = namespace
    rows = []
    for line in FALLBACK_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        row_pid = row.get("project_id") or pid
        if row_pid != pid:
            continue
        if ns and row.get("dialog_id") != ns:
            continue
        rows.append(row)
    return rows


def write_fallback(rows: List[dict]) -> None:
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    with FALLBACK_PATH.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_or_update_fallback(row: dict) -> None:
    pid = row.get("project_id") or project_scope_id()
    row.setdefault("project_id", pid)
    all_rows: List[dict] = []
    if FALLBACK_PATH.is_file():
        for line in FALLBACK_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                all_rows.append(json.loads(line))
    replaced = False
    for i, existing in enumerate(all_rows):
        if existing.get("project_id") != pid:
            continue
        if existing.get("dialog_id") == row.get("dialog_id") and existing.get("ledger_id") == row.get("ledger_id"):
            all_rows[i] = row
            replaced = True
            break
    if not replaced:
        all_rows.append(row)
    write_fallback(all_rows)


def parse_table_records(
    text: str,
    section: str,
    ledger_type: str,
    content_cols: List[int],
    allowed_prefixes: Tuple[str, ...],
    session_team: str,
    scope: str,
) -> List[LedgerRecord]:
    records: List[LedgerRecord] = []
    block = re.search(rf"### {section}\n(\|.*?(?=\n### |\n## |\Z))", text, re.S)
    if not block:
        return records
    lines = [ln.strip() for ln in block.group(1).splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return records
    for line in lines[2:]:
        cols = [c.strip() for c in line.strip("|").split("|")]
        if not cols or not cols[0].startswith(allowed_prefixes):
            continue
        ledger_id = cols[0]
        parts = [cols[i] for i in content_cols if i < len(cols)]
        content = " ".join(parts)
        rec = LedgerRecord(
            ledger_id=ledger_id,
            ledger_type=ledger_type,
            content=content,
            team=session_team,
            scope=scope,
            metadata={"links": cols[-1] if len(cols) > 1 else ""},
        )
        if ledger_type == "CL":
            rec.status = cols[3] if len(cols) > 3 else "active"
            rec.metadata["evidence"] = cols[4] if len(cols) > 4 else ""
        elif ledger_type == "EV":
            rec.domain = cols[2] if len(cols) > 2 else ""
            rec.branch_state = cols[3] if len(cols) > 3 else ""
            rec.status = rec.branch_state
        elif ledger_type == "CP":
            rec.status = cols[3] if len(cols) > 3 else "open"
        elif ledger_type == "TH":
            rec.status = cols[2] if len(cols) > 2 else "open"
            rec.metadata["parent"] = cols[3] if len(cols) > 3 else ""
        elif ledger_type == "Q":
            rec.status = cols[2] if len(cols) > 2 else "open"
        records.append(rec)
    return records


def parse_dialog_index(path: Path, include_ev: bool = False) -> List[LedgerRecord]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    session_team = "none"
    m = re.search(r"team:\s*(\S+)", text)
    if m:
        session_team = m.group(1)
    records: List[LedgerRecord] = []
    records.extend(parse_table_records(text, "Q", "Q", [1], ("Q-",), session_team, "window"))
    records.extend(parse_table_records(text, "CL", "CL", [1, 2], ("CL-",), session_team, "window"))
    records.extend(parse_table_records(text, "TH", "TH", [1], ("TH-",), session_team, "window"))
    records.extend(parse_table_records(text, "CP", "CP", [1, 4], ("CP-",), session_team, "window"))
    if include_ev:
        records.extend(parse_table_records(text, "EV", "EV", [1, 2, 5], ("EV-",), session_team, "project"))
    return records


def parse_catalog_table(
    text: str,
    section: str,
    ledger_type: str,
    content_cols: List[int],
    allowed_prefixes: Tuple[str, ...],
    scope: str,
) -> List[LedgerRecord]:
    block = re.search(rf"## {section}\n+(\|.*?(?=\n## |\Z))", text, re.S)
    if not block:
        return []
    session_team = "none"
    records: List[LedgerRecord] = []
    lines = [ln.strip() for ln in block.group(1).splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return records
    for line in lines[2:]:
        cols = [c.strip() for c in line.strip("|").split("|")]
        if not cols or not cols[0].startswith(allowed_prefixes):
            continue
        ledger_id = cols[0]
        parts = [cols[i] for i in content_cols if i < len(cols)]
        content = " ".join(parts)
        rec = LedgerRecord(
            ledger_id=ledger_id,
            ledger_type=ledger_type,
            content=content,
            team=session_team,
            scope=scope,
            metadata={"links": cols[-1] if len(cols) > 1 else ""},
        )
        if ledger_type == "CL":
            rec.status = cols[3] if len(cols) > 3 else "active"
        elif ledger_type == "EV":
            rec.domain = cols[2] if len(cols) > 2 else ""
            rec.branch_state = cols[1] if len(cols) > 1 else ""
            rec.status = rec.branch_state
        elif ledger_type == "CP":
            rec.status = cols[3] if len(cols) > 3 else "open"
        elif ledger_type == "TH":
            rec.status = cols[2] if len(cols) > 2 else "open"
        elif ledger_type == "Q":
            rec.status = cols[2] if len(cols) > 2 else "open"
        records.append(rec)
    return records


def parse_project_catalog() -> List[LedgerRecord]:
    if not PROJECT_CATALOG.is_file():
        return []
    text = PROJECT_CATALOG.read_text(encoding="utf-8")
    records: List[LedgerRecord] = []
    records.extend(
        parse_catalog_table(text, "branch_registry", "EV", [3, 4], ("EV-",), "project")
    )
    records.extend(
        parse_catalog_table(text, "checkpoint_registry", "CP", [1, 4], ("CP-",), "project")
    )
    return records


def fmt_list(items: Iterable[str]) -> str:
    items = list(items)
    if not items:
        return "- none"
    return "\n".join(f"- {x}" for x in items)


def update_meta(
    meta_path: Path,
    backend_status: str,
    access_mode: str,
    embedded_ids: List[str],
    pending_ids: List[str],
    fallback_count: int,
    last_action: str,
    embed_source: str,
    namespace: str,
) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    body = f"""# Vector Index Meta

backend: pgvector
backend_status: {backend_status}
access_mode: {access_mode}
last_sync: {utc_now()}
last_action: {last_action}
embed_source: {embed_source}
docker_compose: .cursor/dci/docker-compose.yml
project_id: {project_scope_id()}
vector_namespace: {namespace}

## embedded_ids
{fmt_list(embedded_ids)}

## pending_ids
{fmt_list(pending_ids)}

## fallback_store
path: .cursor/context/vector_fallback.jsonl
rows: {fallback_count}
unsynced_policy: migrate on `dci-vector.sh migrate` or `sync --migrate`

## superseded_ids
- none

embedding_model: {env("DCI_EMBED_MODEL", env("DCI_EMBEDDING_MODEL", "text-embedding-3-small"))}
embedding_dims: {EMBED_DIM}
embed_backend: tei (DCI_EMBED_URL) → openai → hash_embed fallback
fallback_embedder: hash_embed:384 (when no TEI/OpenAI)

## notes
Primary: pgvector @ {env("DCI_VECTOR_HOST", "localhost")}:{env("DCI_VECTOR_PORT", "5433")}.
Fallback: JSONL when DB unavailable; auto-migrate when DB returns.
"""
    meta_path.write_text(body, encoding="utf-8")


def sync_records(
    records: List[LedgerRecord],
    namespace: str,
    meta_path: Path,
    migrate: bool,
    reembed: bool = False,
) -> Tuple[List[str], List[str], str]:
    ok, reason = db_ping()
    if migrate and ok:
        migrated = migrate_fallback_to_db(namespace)
        print(f"migrated {migrated} fallback row(s) to pgvector for {namespace}")

    embedded: List[str] = []
    pending: List[str] = []
    skipped: List[str] = []
    reembedded: List[str] = []
    desired = desired_embed_source()
    embed_source = desired
    ledger_ids = [r.ledger_id for r in records]
    stored_hashes = get_db_content_hashes(namespace, ledger_ids) if ok else {}
    stored_sources = get_db_embed_sources(namespace, ledger_ids) if ok else {}
    fb_rows = read_fallback(namespace)

    for record in records:
        rec_hash = content_hash(record.content)
        meta = dict(record.metadata or {})
        meta["content_hash"] = rec_hash
        record.metadata = meta
        stored_hash = stored_hashes.get(record.ledger_id)
        fb_match = next((r for r in fb_rows if r.get("ledger_id") == record.ledger_id), None)
        if fb_match and fb_match.get("metadata", {}).get("content_hash") == rec_hash:
            stored_hash = stored_hash or rec_hash
        stored_source = stored_sources.get(record.ledger_id) or (
            fb_match.get("embed_source") if fb_match else None
        )
        if ok and stored_hash == rec_hash and not needs_reembed(stored_source, desired, reembed):
            skipped.append(record.ledger_id)
            embedded.append(record.ledger_id)
            continue
        if stored_hash == rec_hash and needs_reembed(stored_source, desired, reembed):
            reembedded.append(record.ledger_id)
        embedding, embed_source = embed_text(record.embed_text())
        if ok:
            try:
                upsert_db(record, embedding, embed_source, namespace)
                embedded.append(record.ledger_id)
                append_or_update_fallback(
                    to_fallback_row(record, embedding, namespace, synced_to_db=True, embed_source=embed_source)
                )
            except Exception as exc:  # noqa: BLE001
                print(f"WARN db upsert {record.ledger_id}: {exc}", file=sys.stderr)
                append_or_update_fallback(
                    to_fallback_row(record, embedding, namespace, synced_to_db=False, embed_source=embed_source)
                )
                pending.append(record.ledger_id)
        else:
            append_or_update_fallback(
                to_fallback_row(record, embedding, namespace, synced_to_db=False, embed_source=embed_source)
            )
            pending.append(record.ledger_id)

    if skipped:
        print(f"DCI sync [{namespace}]: skipped unchanged={len(skipped)}")
    if reembedded:
        print(f"DCI sync [{namespace}]: reembedded backend upgrade={len(reembedded)}")

    fallback_rows = read_fallback(namespace)
    unsynced = sum(1 for r in fallback_rows if not r.get("synced_to_db"))
    if ok and unsynced:
        migrated = migrate_fallback_to_db(namespace)
        print(f"migrated {migrated} fallback row(s) after sync for {namespace}")
        embedded = list({*embedded, *(r["ledger_id"] for r in read_fallback(namespace) if r.get("synced_to_db"))})

    access_mode = "hybrid" if ok else "structured-only"
    backend_status = "ok" if ok else "unavailable"
    update_meta(
        meta_path=meta_path,
        backend_status=backend_status,
        access_mode=access_mode,
        embedded_ids=sorted(set(embedded)),
        pending_ids=sorted(set(pending)),
        fallback_count=len(read_fallback(namespace)),
        last_action="sync",
        embed_source=embed_source,
        namespace=namespace,
    )
    print(
        f"DCI sync [{namespace}]: db={backend_status}, embedded={len(embedded)}, "
        f"pending={len(pending)}, fallback_rows={len(read_fallback(namespace))}"
    )
    if not ok:
        print(f"DB unavailable ({reason}); records saved to {FALLBACK_PATH}", file=sys.stderr)
    return embedded, pending, embed_source


def migrate_fallback_to_db(namespace: Optional[str] = None) -> int:
    ok, reason = db_ping()
    if not ok:
        print(f"Cannot migrate: DB unavailable ({reason})", file=sys.stderr)
        return 0
    rows = read_fallback(namespace)
    migrated = 0
    all_rows: List[dict] = []
    if FALLBACK_PATH.is_file():
        for line in FALLBACK_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                all_rows.append(json.loads(line))
    for row in rows:
        if row.get("synced_to_db"):
            continue
        ns = row.get("dialog_id") or namespace or vector_namespace()
        rec = LedgerRecord(
            ledger_id=row["ledger_id"],
            ledger_type=row["ledger_type"],
            content=row["content"],
            team=row.get("team", "none"),
            branch_state=row.get("branch_state", ""),
            status=row.get("status", "active"),
            domain=row.get("domain", ""),
            scope=row.get("scope", "window"),
            metadata=row.get("metadata") or {},
        )
        embedding = row.get("embedding") or embed_text(rec.embed_text())[0]
        source = row.get("embed_source", "hash_embed:384")
        try:
            upsert_db(rec, embedding, source, ns)
            row["synced_to_db"] = True
            row["updated_at"] = utc_now()
            migrated += 1
        except Exception as exc:  # noqa: BLE001
            print(f"WARN migrate {rec.ledger_id}: {exc}", file=sys.stderr)
    write_fallback(all_rows)
    return migrated


def cmd_sync_window(
    migrate: bool,
    dialog_window_id: Optional[str] = None,
    reembed: bool = False,
) -> int:
    dw = dialog_window_id or resolve_dialog_window_id()
    assert_window_scope("sync", dw)
    path = window_index_path(dw)
    records = parse_dialog_index(path)
    if not records:
        print(f"WARN no window records parsed from {path}", file=sys.stderr)
    sync_records(records, vector_namespace(dw), window_meta_path(dw), migrate, reembed=reembed)
    write_project_lock(project_scope_id())
    write_window_lock(dw)
    ok, _ = db_ping()
    if ok:
        cleanup_stale_vectors()
    return 0


def cmd_sync_project(migrate: bool, reembed: bool = False) -> int:
    assert_project_scope("sync-project")
    records = parse_project_catalog()
    if not records:
        print(f"WARN no project records parsed from {PROJECT_CATALOG}", file=sys.stderr)
    sync_records(
        records,
        project_vector_namespace(),
        CONTEXT_DIR / "vector_index.meta.md",
        migrate,
        reembed=reembed,
    )
    write_project_lock(project_scope_id())
    ok, _ = db_ping()
    if ok:
        cleanup_stale_vectors()
    return 0


def cmd_lookup(query: str, top_k: int = 5, scope: str = "window", quiet: bool = False) -> int:
    results, access = lookup_results(query, top_k, scope)
    if not quiet:
        print(access)
        for score, lid, summary in results:
            print(f"{lid}\t{score:.4f}\t{summary}")
    return 0


def lookup_results(
    query: str,
    top_k: int = 5,
    scope: str = "window",
) -> Tuple[List[Tuple[float, str, str]], str]:
    assert_window_scope("lookup")
    dw = resolve_dialog_window_id()
    namespace = project_vector_namespace() if scope == "project" else vector_namespace(dw)
    records = (
        parse_project_catalog()
        if scope == "project"
        else parse_dialog_index(window_index_path(dw))
    )
    ok, _ = db_ping()
    embedding, _ = embed_text(query)
    results: List[Tuple[float, str, str]] = []

    if ok:
        vec_literal = "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"
        sql = """
            SELECT ledger_id, ledger_type, content,
                   1 - (embedding <=> %s::vector) AS score
            FROM dci_embeddings
            WHERE dialog_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        try:
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (vec_literal, namespace, vec_literal, top_k))
                    for row in cur.fetchall():
                        results.append((float(row[3]), row[0], row[2]))
        except Exception as exc:  # noqa: BLE001
            print(f"WARN db lookup: {exc}", file=sys.stderr)
            ok = False

    if not results:
        q = query.lower()
        for rec in records:
            score = sum(1 for t in re.findall(r"[\w\u0400-\u04FF]+", q) if t in rec.content.lower())
            if score:
                results.append((score, rec.ledger_id, rec.content[:120]))
        results.sort(key=lambda x: x[0], reverse=True)
        results = results[:top_k]
        access = f"access: structured-only (SI fallback lookup, scope={scope})"
    else:
        access = f"access: hybrid (pgvector, scope={scope}, namespace={namespace})"
    return results, access


def parse_thread_rows(text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    block = re.search(r"## thread_map\n+(\|.*?(?=\n## |\Z))", text, re.S)
    if not block:
        return rows
    lines = [ln.strip() for ln in block.group(1).splitlines() if ln.strip().startswith("|")]
    for line in lines[2:]:
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) >= 4 and cols[0].startswith("TH-"):
            rows.append(
                {
                    "id": cols[0],
                    "status": cols[1],
                    "topic": cols[2],
                    "next_action": cols[3],
                }
            )
    return rows


def parse_open_risk_refs(text: str) -> List[str]:
    refs: List[str] = []
    block = re.search(r"## open_risks\n+(\|.*?(?=\n## |\Z))", text, re.S)
    if not block:
        return refs
    for line in block.group(1).splitlines():
        if not line.strip().startswith("|") or line.startswith("| ref"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if cols and cols[0] not in ("—", "-", "none", ""):
            refs.append(cols[0])
    return refs


def materialize_checkpoint_rows(dialog_window_id: str) -> Tuple[int, int]:
    """Materialize minimal project CP-* entries from open TH-* in active window.

    Returns (created_count, open_threads_count). Idempotent and safe on repeated calls.
    """
    index_path = window_index_path(dialog_window_id)
    if not index_path.is_file() or not PROJECT_CATALOG.is_file():
        return (0, 0)

    index_text = index_path.read_text(encoding="utf-8")
    threads = parse_thread_rows(index_text)
    open_threads = [t for t in threads if t.get("status", "").lower() in ("open", "in_progress")]
    if not open_threads:
        return (0, 0)

    catalog_text = PROJECT_CATALOG.read_text(encoding="utf-8")
    block = re.search(r"(## checkpoint_registry\n+)(\|.*?)(?=\n## |\Z)", catalog_text, re.S)
    if not block:
        return (0, len(open_threads))

    table = block.group(2)
    existing_ids = set(re.findall(r"\|\s*(CP-[A-Z0-9-]+)\s*\|", table))
    branch = parse_header_field(catalog_text, "master_branch") or MASTER_EV_ID
    evidence = f".cursor/context/dialogs/{dialog_window_id}/dialog_index.md"
    created = 0
    rows_to_add: List[str] = []
    for th in open_threads:
        th_id = th["id"]
        cp_id = f"CP-AUTO-{dialog_window_id}-{th_id}"
        if cp_id in existing_ids:
            continue
        label = f"Materialized checkpoint for {th_id}"
        status = "in_progress" if th.get("status", "").lower() == "in_progress" else "open"
        rows_to_add.append(f"| {cp_id} | {label} | {branch} | {status} | {evidence} |")
        existing_ids.add(cp_id)
        created += 1

    if rows_to_add:
        # Remove default placeholder row once we have real CP entries.
        table = re.sub(r"\n\|\s*—\s*\|\s*none\s*\|\s*—\s*\|\s*—\s*\|\s*—\s*\|", "", table)
        table = table.rstrip("\n") + "\n" + "\n".join(rows_to_add) + "\n"
        new_text = catalog_text[: block.start(2)] + table + catalog_text[block.end(2):]
        PROJECT_CATALOG.write_text(new_text, encoding="utf-8")

    return (created, len(open_threads))


def cmd_materialize(dialog_window_id: Optional[str] = None) -> int:
    """Collect reusable checkpoint data from active window into project catalog."""
    validate_window_scope("materialize")
    dw = dialog_window_id or resolve_dialog_window_id()
    created, open_count = materialize_checkpoint_rows(dw)
    if open_count == 0:
        print(f"materialize: no open TH in {dw}; nothing to sync")
        return 0
    if created == 0:
        print(f"materialize: checkpoints already up-to-date ({dw}, open_th={open_count})")
        return 0
    print(f"materialize: created {created} checkpoint(s) from {open_count} open TH in {dw}")
    return 0


def resolve_evidence_path(evidence: str) -> Path:
    ev = evidence.strip()
    if not ev or ev in ("—", "-", "none"):
        return Path()
    if ev.startswith("."):
        return REPO_ROOT / ev
    return REPO_ROOT / ev


def cmd_doctor(dialog_window_id: Optional[str] = None) -> int:
    """Self-heal window ledger to satisfy validate invariants (V-01/V-02).

    Idempotent: only patches open TH rows that lack next_action and have no
    CL link / open_risks entry. Safe to run on any project; no-op when clean.
    """
    validate_window_scope("doctor")
    dw = dialog_window_id or resolve_dialog_window_id()
    index_path = window_index_path(dw)
    if not index_path.is_file():
        print(f"ERROR: missing index {index_path}", file=sys.stderr)
        return 1

    text = index_path.read_text(encoding="utf-8")
    original = text
    records = parse_dialog_index(index_path)
    threads = parse_thread_rows(text)
    open_risks = set(parse_open_risk_refs(text))
    fixes: List[str] = []

    open_threads = [t for t in threads if t["status"].lower() in ("open", "in_progress")]

    # V-01: open TH must have a next_action in thread_map.
    for th in open_threads:
        if th.get("next_action", "").strip() in ("", "—", "-", "none"):
            pattern = (
                r"(\|\s*" + re.escape(th["id"]) + r"\s*\|\s*(?:open|in_progress)\s*\|[^|]*\|\s*)"
                r"(—|-|none|)(\s*\|)"
            )
            new_text, n = re.subn(
                pattern,
                r"\1record first CL/EV on session start\3",
                text,
                flags=re.IGNORECASE,
            )
            if n:
                text = new_text
                fixes.append(f"V-01 {th['id']}: set next_action")

    # V-02: open TH needs CL link or open_risks entry.
    def has_cl_link(th_id: str) -> bool:
        return any(
            th_id in ((r.metadata or {}).get("links", ""))
            for r in records
            if r.ledger_type == "CL"
        )

    missing_risk = [
        t["id"]
        for t in open_threads
        if t["id"] not in open_risks and not has_cl_link(t["id"])
    ]
    if missing_risk:
        block = re.search(r"(## open_risks\n+)(\|.*?)(?=\n## |\Z)", text, re.S)
        if block:
            table = block.group(2)
            rows = [
                f"| {tid} | fresh window, no conclusions yet | — | record CL/EV on first session |"
                for tid in missing_risk
            ]
            # drop default 'none' placeholder row if present
            table = re.sub(r"\n\|\s*—\s*\|\s*none\s*\|\s*—\s*\|\s*—\s*\|", "", table)
            table = table.rstrip("\n") + "\n" + "\n".join(rows) + "\n"
            text = text[: block.start(2)] + table + text[block.end(2):]
            fixes.append(f"V-02: open_risks += {', '.join(missing_risk)}")

    if text != original:
        index_path.write_text(text, encoding="utf-8")
        for f in fixes:
            print(f"doctor: fixed {f}")
        print(f"doctor: ledger normalized ({dw})")
    else:
        print(f"doctor: ledger already valid ({dw})")
    return 0


def cmd_validate() -> int:
    """Pre-compress ledger integrity gate (V-01..V-06)."""
    validate_window_scope("validate")
    dw = resolve_dialog_window_id()
    index_path = window_index_path(dw)
    if not index_path.is_file():
        print(f"ERROR: missing index {index_path}", file=sys.stderr)
        return 1
    text = index_path.read_text(encoding="utf-8")
    records = parse_dialog_index(index_path)
    threads = parse_thread_rows(text)
    open_risks = parse_open_risk_refs(text)
    errors: List[str] = []
    warnings: List[str] = []

    th_by_id = {r.ledger_id: r for r in records if r.ledger_type == "TH"}
    thread_by_id = {t["id"]: t for t in threads}

    for th in threads:
        if th["status"].lower() not in ("open", "in_progress"):
            continue
        rec = th_by_id.get(th["id"])
        parent = (rec.metadata or {}).get("parent", "") if rec else ""
        if not parent or not parent.startswith("Q-"):
            errors.append(f"V-01: {th['id']} open without Q parent")
        next_action = th.get("next_action", "").strip()
        if next_action in ("", "—", "-", "none"):
            errors.append(f"V-01: {th['id']} open without next_action")
        has_cl = any(
            th["id"] in ((r.metadata or {}).get("links", "")) for r in records if r.ledger_type == "CL"
        )
        if not has_cl and th["id"] not in open_risks:
            errors.append(f"V-02: {th['id']} open without CL link or open_risks entry")

    for rec in records:
        if rec.ledger_type == "CL" and not rec.content.strip():
            errors.append(f"V-03: {rec.ledger_id} empty content")
        if rec.ledger_type == "CL":
            evidence = (rec.metadata or {}).get("evidence", "")
            ev_path = resolve_evidence_path(evidence)
            if evidence and evidence not in ("—", "-", "none") and ev_path and not ev_path.is_file():
                errors.append(f"V-04: {rec.ledger_id} evidence missing: {evidence}")

    embed_src = last_embed_source(vector_namespace(dw))
    if embed_src.startswith("hash_embed"):
        warnings.append("V-05: embedding backend is hash_embed (pass_with_risk)")
    elif not (embed_src.startswith("tei:") or embed_src.startswith("openai:")):
        warnings.append(f"V-05: embedding backend unknown ({embed_src})")

    before = load_snapshot(window_snapshot_path(dw))
    after = snapshot_records(records)
    delta = compute_delta(before, after)
    if before and after:
        if index_checksum(before) != index_checksum(after) and not delta["new_or_updated"]:
            errors.append("V-06: checksum changed but delta empty")

    for msg in warnings:
        print(f"WARN {msg}", file=sys.stderr)
    for msg in errors:
        print(f"ERROR {msg}", file=sys.stderr)

    if errors:
        print(f"validate: fail ({len(errors)} blocking)", file=sys.stderr)
        return 1
    if warnings:
        print(f"validate: pass_with_risk ({len(warnings)} warnings)")
        return 0
    print("validate: pass")
    return 0


def hot_open_query(index_text: str, records: List[LedgerRecord]) -> str:
    hot = re.search(r"### hot_open\n- (.+)", index_text)
    if not hot:
        return ""
    val = hot.group(1).strip()
    if not val or val.lower() == "none":
        return ""
    th_by_id = {r.ledger_id: r for r in records if r.ledger_type == "TH"}
    if val in th_by_id:
        return th_by_id[val].content
    return val


def cmd_export(dialog_window_id: Optional[str] = None) -> int:
    assert_project_scope("export")
    dw = dialog_window_id or resolve_dialog_window_id()
    if dialog_window_id:
        if not window_index_path(dw).is_file():
            print(f"ERROR: missing {window_index_path(dw)}", file=sys.stderr)
            return 1
    else:
        assert_window_scope("export", dw)
    index_path = window_index_path(dw)
    if not index_path.is_file():
        print(f"ERROR: missing {index_path}", file=sys.stderr)
        return 1
    project_id = project_scope_id()
    index_body = index_path.read_text(encoding="utf-8")
    if not parse_header_field(index_body, "dialog_window_id"):
        index_body = f"dialog_window_id: {dw}\n\n{index_body}"
    bundle = (
        f"# Dialog Bundle\n\n"
        f"project_id: {project_id}\n"
        f"dialog_window_id: {dw}\n"
        f"exported_at: {utc_now()}\n"
        f"archive: true\n"
        f"load_policy: do not load by default; use dialog_delta.md + restore\n"
        f"id_remap: none\n"
        f"source: dialogs/{dw}/dialog_index.md\n\n"
        f"---\n\n"
        f"{index_body}"
    )
    out = window_bundle_path(dw)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(bundle, encoding="utf-8")
    write_project_lock(project_id)
    if not dialog_window_id:
        write_window_lock(dw)
    print(f"exported full bundle -> {out}")
    return 0


def cmd_import(source: str, target_window: Optional[str] = None) -> int:
    current_project = resolve_project_id()
    current_window = target_window or resolve_dialog_window_id()
    src = Path(source)
    if not src.is_file():
        print(f"ERROR: missing import source {src}", file=sys.stderr)
        return 1
    text = src.read_text(encoding="utf-8")
    bundle_pid = parse_project_id_text(text)
    bundle_dw = parse_header_field(text, "dialog_window_id")
    if not bundle_pid:
        print("ERROR: import source missing project_id header", file=sys.stderr)
        return 1
    if bundle_pid != current_project:
        print(
            f"ERROR: cross-project import forbidden: source={bundle_pid} current={current_project}",
            file=sys.stderr,
        )
        return 2
    if bundle_dw and bundle_dw != current_window:
        print(
            f"ERROR: cross-window import forbidden: source={bundle_dw} target={current_window}",
            file=sys.stderr,
        )
        return 2
    if "---" in text:
        body = text.split("---", 1)[1].strip()
    else:
        body = text
    body_pid = parse_project_id_text(body)
    body_dw = parse_header_field(body, "dialog_window_id")
    if body_pid and body_pid != current_project:
        print(
            f"ERROR: import body project_id mismatch: body={body_pid} current={current_project}",
            file=sys.stderr,
        )
        return 2
    if body_dw and body_dw != current_window:
        print(
            f"ERROR: import body dialog_window_id mismatch: body={body_dw} target={current_window}",
            file=sys.stderr,
        )
        return 2
    if not body_dw:
        body = f"dialog_window_id: {current_window}\n\n{body}"
    if not body_pid:
        body = f"project_id: {current_project}\n\n{body}"
    index_path = window_index_path(current_window)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(body, encoding="utf-8")
    write_project_lock(current_project)
    write_window_lock(current_window)
    print(f"imported ledger index for {current_project}/{current_window} from {src}")
    records = parse_dialog_index(index_path)
    if records:
        sync_records(records, vector_namespace(current_window), window_meta_path(current_window), migrate=True)
    return 0


def window_lifecycle_from_text(text: str) -> str:
    open_statuses = {"open", "in_progress"}
    for section in ("Q", "TH"):
        block = re.search(rf"### {section}\n(\|.*?(?=\n### |\n## |\Z))", text, re.S)
        if not block:
            continue
        for line in block.group(1).splitlines():
            if not line.strip().startswith("|") or line.startswith("| id"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 3 and cols[2].lower() in open_statuses:
                return "open"
    block = re.search(r"## thread_map\n+(\|.*?(?=\n## |\Z))", text, re.S)
    if block:
        for line in block.group(1).splitlines():
            if not line.strip().startswith("|") or line.startswith("| th"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 2 and cols[1].lower() in open_statuses:
                return "open"
    hot = re.search(r"### hot_open\n- (.+)", text)
    if hot:
        val = hot.group(1).strip().lower()
        if val and val != "none":
            return "open"
    return "resolved"


def window_lifecycle(dialog_window_id: str, root: Optional[Path] = None) -> str:
    index_path = window_index_path(dialog_window_id, root)
    if not index_path.is_file():
        return "unknown"
    return window_lifecycle_from_text(index_path.read_text(encoding="utf-8"))


def window_display_meta(dialog_window_id: str, root: Optional[Path] = None) -> Dict[str, str]:
    index_path = window_index_path(dialog_window_id, root)
    empty = {
        "name": "",
        "description": "",
        "summary": "",
        "lifecycle": "unknown",
        "updated": "",
        "linked_branches": "[]",
    }
    if not index_path.is_file():
        return empty
    text = index_path.read_text(encoding="utf-8")
    updated = ""
    m = re.search(r"refreshed:\s*(\S+)", text)
    if m:
        updated = m.group(1)[:10]
    links = "[]"
    m = re.search(r"linked_branches:\s*(\[[^\]]*\])", text)
    if m:
        links = m.group(1)

    q_text = ""
    th_topic = ""
    q_block = re.search(r"### Q\n(\|.*?(?=\n### |\n## |\Z))", text, re.S)
    if q_block:
        for line in q_block.group(1).splitlines():
            if line.strip().startswith("| Q-"):
                cols = [c.strip() for c in line.strip("|").split("|")]
                if len(cols) > 1:
                    q_text = cols[1]
                    break
    th_block = re.search(r"### TH\n(\|.*?(?=\n### |\n## |\Z))", text, re.S)
    if th_block:
        for line in th_block.group(1).splitlines():
            if line.strip().startswith("| TH-"):
                cols = [c.strip() for c in line.strip("|").split("|")]
                if len(cols) > 1:
                    th_topic = cols[1]
                    break

    name = parse_header_value(text, "window_name")
    description = parse_header_value(text, "window_description")
    if not name:
        slug = parse_session_slug(text)
        name = humanize_slug(slug) or th_topic or truncate_text(q_text, 60)
    if not description:
        description = q_text or th_topic or name

    return {
        "name": name,
        "description": description,
        "summary": q_text or name,
        "lifecycle": window_lifecycle_from_text(text),
        "updated": updated,
        "linked_branches": links,
    }


def window_index_meta(dialog_window_id: str) -> Dict[str, str]:
    meta = window_display_meta(dialog_window_id)
    return {
        "summary": meta["summary"],
        "lifecycle": meta["lifecycle"],
        "updated": meta["updated"],
        "linked_branches": meta["linked_branches"],
        "name": meta["name"],
        "description": meta["description"],
    }


def sync_window_registry(active_dw: str) -> None:
    if not PROJECT_CATALOG.is_file():
        return
    dw_ids: List[str] = []
    if DIALOGS_DIR.is_dir():
        for child in sorted(DIALOGS_DIR.iterdir()):
            if child.is_dir() and re.match(r"DW-\d+$", child.name):
                dw_ids.append(child.name)
    text = PROJECT_CATALOG.read_text(encoding="utf-8")
    block = re.search(r"## window_registry\n+(\|.*?(?=\n## |\Z))", text, re.S)
    if block:
        for line in block.group(1).splitlines():
            cols = [c.strip() for c in line.strip("|").split("|")]
            if cols and cols[0].startswith("DW-") and cols[0] not in dw_ids:
                dw_ids.append(cols[0])
    dw_ids = sorted(set(dw_ids))
    header = (
        "## window_registry\n\n"
        "| id | slot | lifecycle | name | description | updated | path | linked_branches |\n"
        "|----|------|-----------|------|-------------|---------|------|-----------------|\n"
    )
    body_rows: List[str] = []
    for dw in dw_ids:
        meta = window_index_meta(dw)
        slot = "active" if dw == active_dw else "stored"
        rel_path = f".cursor/context/dialogs/{dw}/"
        name = meta.get("name") or meta["summary"] or dw
        description = meta.get("description") or meta["summary"] or f"Dialog window {dw}"
        body_rows.append(
            f"| {dw} | {slot} | {meta['lifecycle']} | {name} | {description} | "
            f"{meta['updated'] or utc_now()[:10]} | {rel_path} | {meta['linked_branches']} |"
        )
    new_block = header + "\n".join(body_rows) + "\n"
    if block:
        text = re.sub(
            r"## window_registry\n+.*?(?=\n## |\Z)",
            new_block.rstrip() + "\n",
            text,
            count=1,
            flags=re.S,
        )
    else:
        text = text.rstrip() + "\n\n" + new_block
    PROJECT_CATALOG.write_text(text, encoding="utf-8")


def list_dialog_windows(
    catalog_path: Optional[Path] = None,
    root: Optional[Path] = None,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    catalog = catalog_path or PROJECT_CATALOG
    proj_root = project_root_path(root)
    dialogs_dir = dialogs_dir_for_root(proj_root)
    if catalog.is_file():
        text = catalog.read_text(encoding="utf-8")
        block = re.search(r"## window_registry\n+(\|.*?(?=\n## |\Z))", text, re.S)
        if block:
            lines = [ln.strip() for ln in block.group(1).splitlines() if ln.strip().startswith("|")]
            header = lines[0].lower() if lines else ""
            v9 = "name" in header and "description" in header
            v8 = "lifecycle" in header and not v9
            for line in lines[2:]:
                cols = [c.strip() for c in line.strip("|").split("|")]
                if cols and cols[0].startswith("DW-"):
                    if v9:
                        rows.append(
                            {
                                "id": cols[0],
                                "slot": cols[1] if len(cols) > 1 else "",
                                "lifecycle": cols[2] if len(cols) > 2 else "",
                                "name": cols[3] if len(cols) > 3 else "",
                                "description": cols[4] if len(cols) > 4 else "",
                                "summary": cols[4] if len(cols) > 4 else "",
                                "updated": cols[5] if len(cols) > 5 else "",
                                "path": cols[6] if len(cols) > 6 else "",
                                "links": cols[7] if len(cols) > 7 else "",
                                "status": cols[1] if len(cols) > 1 else "",
                            }
                        )
                    elif v8:
                        rows.append(
                            {
                                "id": cols[0],
                                "slot": cols[1] if len(cols) > 1 else "",
                                "lifecycle": cols[2] if len(cols) > 2 else "",
                                "name": "",
                                "description": cols[3] if len(cols) > 3 else "",
                                "summary": cols[3] if len(cols) > 3 else "",
                                "updated": cols[4] if len(cols) > 4 else "",
                                "path": cols[5] if len(cols) > 5 else "",
                                "links": cols[6] if len(cols) > 6 else "",
                                "status": cols[1] if len(cols) > 1 else "",
                            }
                        )
                    else:
                        legacy = cols[1] if len(cols) > 1 else ""
                        slot = "active" if legacy == "active" else "stored"
                        rows.append(
                            {
                                "id": cols[0],
                                "slot": slot,
                                "lifecycle": window_lifecycle(cols[0], proj_root),
                                "name": "",
                                "description": cols[2] if len(cols) > 2 else "",
                                "summary": cols[2] if len(cols) > 2 else "",
                                "updated": cols[3] if len(cols) > 3 else "",
                                "path": cols[4] if len(cols) > 4 else "",
                                "links": cols[5] if len(cols) > 5 else "",
                                "status": slot,
                            }
                        )
    for row in rows:
        meta = window_display_meta(row["id"], proj_root)
        if not row.get("name"):
            row["name"] = meta["name"]
        if not row.get("description"):
            row["description"] = meta["description"]
        if not row.get("summary"):
            row["summary"] = meta["summary"] or meta["description"]
        if not row.get("lifecycle") or row["lifecycle"] == "unknown":
            row["lifecycle"] = meta["lifecycle"]
    if not rows and dialogs_dir.is_dir():
        for child in sorted(dialogs_dir.iterdir()):
            if child.is_dir() and child.name.startswith("DW-"):
                meta = window_display_meta(child.name, proj_root)
                rows.append(
                    {
                        "id": child.name,
                        "slot": "unknown",
                        "lifecycle": meta["lifecycle"],
                        "status": "unknown",
                        "name": meta["name"],
                        "description": meta["description"],
                        "summary": meta["summary"] or meta["description"],
                        "updated": meta["updated"],
                        "path": str(child.relative_to(proj_root)),
                        "links": meta["linked_branches"],
                    }
                )
    return rows


def list_branches(catalog_path: Optional[Path] = None) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    catalog = catalog_path or PROJECT_CATALOG
    if not catalog.is_file():
        return rows
    text = catalog.read_text(encoding="utf-8")
    block = re.search(r"## branch_registry\n+(\|.*?(?=\n## |\Z))", text, re.S)
    if not block:
        return rows
    lines = [ln.strip() for ln in block.group(1).splitlines() if ln.strip().startswith("|")]
    for line in lines[2:]:
        cols = [c.strip() for c in line.strip("|").split("|")]
        if cols and cols[0].startswith("EV-"):
            rows.append(
                {
                    "id": cols[0],
                    "state": cols[1] if len(cols) > 1 else "",
                    "parent": cols[2] if len(cols) > 2 else "",
                    "name": cols[3] if len(cols) > 3 else "",
                    "summary": cols[3] if len(cols) > 3 else "",
                    "delta": cols[4] if len(cols) > 4 else "",
                }
            )
    return rows


def parse_catalog_header(catalog_path: Path) -> Dict[str, str]:
    if not catalog_path.is_file():
        return {}
    text = catalog_path.read_text(encoding="utf-8")
    return {
        "project_id": parse_header_field(text, "project_id"),
        "active_window": parse_header_field(text, "active_window"),
        "master_branch": parse_header_field(text, "master_branch") or MASTER_EV_ID,
        "refreshed": parse_header_field(text, "refreshed"),
    }


def discover_projects() -> List[Dict[str, Any]]:
    found: Dict[str, Path] = {project_scope_id(): REPO_ROOT}
    if PROJECTS_REGISTRY.is_file():
        for line in PROJECTS_REGISTRY.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|", 1)
            pid = parts[0].strip()
            path = Path(parts[1].strip()) if len(parts) > 1 else REPO_ROOT
            if not path.is_absolute():
                path = (REPO_ROOT / path).resolve()
            catalog = catalog_path_for_root(path)
            if catalog.is_file():
                header = parse_catalog_header(catalog)
                found[header.get("project_id") or pid] = path
    scan_root = env("DCI_PROJECTS_ROOT")
    if scan_root:
        base = Path(scan_root)
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if not child.is_dir():
                    continue
                catalog = catalog_path_for_root(child)
                if not catalog.is_file():
                    continue
                header = parse_catalog_header(catalog)
                pid = header.get("project_id") or child.name
                if pid not in found:
                    found[pid] = child.resolve()
    current = project_scope_id()
    items = [{"project_id": pid, "root": root} for pid, root in found.items()]
    items.sort(key=lambda x: (0 if x["project_id"] == current else 1, x["project_id"]))
    return items


def format_branch_line(row: Dict[str, str], prefix: str = "") -> str:
    name = row.get("name") or row.get("summary") or row["id"]
    desc = row.get("delta") or row.get("summary") or name
    return (
        f"{prefix}{row['id']} [{row['state']}] | "
        f"name: «{name}» | desc: «{desc}»"
    )


def format_window_line(row: Dict[str, str], active_window: str, prefix: str = "") -> str:
    marker = " *" if row["id"] == active_window else ""
    slot = row.get("slot", row.get("status", ""))
    lifecycle = row.get("lifecycle", "unknown")
    name = row.get("name") or row.get("summary") or row["id"]
    desc = row.get("description") or row.get("summary") or name
    return (
        f"{prefix}{row['id']}{marker} | "
        f"name: «{name}» | desc: «{desc}» | "
        f"[{slot}][{lifecycle}]"
    )


def format_branch_tree(branches: List[Dict[str, str]], indent: str = "    ") -> List[str]:
    lines: List[str] = []
    if not branches:
        lines.append(f"{indent}(none)")
        return lines
    roots = [
        row
        for row in branches
        if row["id"] == MASTER_EV_ID
        or row.get("parent", "").strip() in ("", "—", "-", "none")
        or row.get("parent") not in {r["id"] for r in branches}
    ]
    if not roots:
        roots = [branches[0]]
    seen: set[str] = set()
    for root in roots:
        if root["id"] in seen:
            continue
        seen.add(root["id"])
        lines.append(f"{indent}{format_branch_line(root)}")
        children = [row for row in branches if row.get("parent") == root["id"]]
        for idx, child in enumerate(sorted(children, key=lambda r: r["id"])):
            branch = "└─ " if idx == len(children) - 1 else "├─ "
            lines.append(f"{indent}  {branch}{format_branch_line(child).lstrip()}")
    return lines


def format_dialog_tree(
    windows: List[Dict[str, str]],
    active_window: str,
    indent: str = "  ",
) -> List[str]:
    lines: List[str] = []
    if not windows:
        lines.append(f"{indent}(none)")
        return lines
    for idx, row in enumerate(windows):
        branch = "└─ " if idx == len(windows) - 1 else "├─ "
        lines.append(f"{indent}{format_window_line(row, active_window, prefix=branch)}")
    return lines


def print_project_tree(
    project_id: str,
    root: Path,
    active_window: str,
    marker: str = "",
    compact: bool = False,
) -> None:
    catalog = catalog_path_for_root(root)
    header = parse_catalog_header(catalog)
    active = header.get("active_window") or active_window or "—"
    proj_marker = f" *{marker}" if marker else ""
    print(f"{project_id}{proj_marker}")
    if not compact:
        print(f"  path: {root}")
    print(f"  active_window: {active}")
    print("  format: id | name: «…» | desc: «…» | [slot][lifecycle]")
    print("  branches/")
    for line in format_branch_tree(list_branches(catalog)):
        print(f"  {line}")
    print("  dialogs/")
    for line in format_dialog_tree(list_dialog_windows(catalog, root), active):
        print(f"  {line}")


def cmd_catalog(mode: str = "all") -> int:
    assert_project_scope("catalog")
    active = resolve_dialog_window_id()
    print(f"project_id: {project_scope_id()}")
    print(f"active_window: {active}")
    print(f"master_branch: {MASTER_EV_ID}")
    if mode in ("all", "branches"):
        print("\n## Branches (project)")
        print("| id | state | summary |")
        print("|----|-------|---------|")
        for row in list_branches():
            print(f"| {row['id']} | {row['state']} | {row['summary']} |")
    if mode in ("all", "windows"):
        print("\n## Windows (dialogs)")
        print("| id | slot | lifecycle | name | description | updated | links |")
        print("|----|------|-----------|------|-------------|---------|-------|")
        for row in list_dialog_windows():
            marker = " *" if row["id"] == active else ""
            print(
                f"| {row['id']}{marker} | {row.get('slot', row.get('status', ''))} | "
                f"{row.get('lifecycle', '')} | {row.get('name', '')} | "
                f"{row.get('description', row.get('summary', ''))} | "
                f"{row['updated']} | {row['links']} |"
            )
    return 0


def next_window_id() -> str:
    max_n = 0
    if DIALOGS_DIR.is_dir():
        for child in DIALOGS_DIR.iterdir():
            m = re.match(r"DW-(\d+)$", child.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    for row in list_dialog_windows():
        m = re.match(r"DW-(\d+)$", row["id"])
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"DW-{max_n + 1:03d}"


def update_catalog_active_window(dialog_window_id: str) -> None:
    if not PROJECT_CATALOG.is_file():
        return
    text = PROJECT_CATALOG.read_text(encoding="utf-8")
    text = re.sub(r"^active_window:\s*\S+", f"active_window: {dialog_window_id}", text, count=1, flags=re.M)
    text = re.sub(r"^refreshed:\s*.*", f"refreshed: {utc_now()}", text, count=1, flags=re.M)
    PROJECT_CATALOG.write_text(text, encoding="utf-8")
    sync_window_registry(dialog_window_id)


def append_window_registry(dialog_window_id: str, summary: str) -> None:
    del dialog_window_id, summary
    sync_window_registry(resolve_dialog_window_id())


def new_window_index_template(dialog_window_id: str, summary: str) -> str:
    pid = project_scope_id()
    short_name = truncate_text(summary, 60)
    return f"""# Dialog Index

project_id: {pid}
dialog_window_id: {dialog_window_id}
window_name: {short_name}
window_description: {summary}
master_branch: {MASTER_EV_ID}
linked_branches: []
session: new | team: none | refreshed: {utc_now()}

## ledger_map

### Q
| id | text | status | links |
|----|------|--------|-------|
| Q-001 | {summary} | open | — |

### CL
| id | scope | verdict | status | evidence | links |
|----|-------|---------|--------|----------|-------|

### TH
| id | topic | status | parent | links |
|----|-------|--------|--------|-------|
| TH-001 | {summary[:80]} | open | Q-001 | — |

## thread_map

| th | status | topic | next_action |
|----|--------|-------|-------------|
| TH-001 | open | {summary[:60]} | — |

## lookup_index

### by_id
- Q-001, TH-001: open

### by_status
- open: [Q-001, TH-001]

### hot_open
- TH-001

## open_risks

| ref | risk | owner | next_action |
|-----|------|-------|-------------|
| — | none | — | — |
"""


def cmd_window_new(summary: str) -> int:
    assert_project_scope("window-new")
    dw = next_window_id()
    summary = summary.strip() or f"Dialog window {dw}"
    path = window_dir(dw)
    path.mkdir(parents=True, exist_ok=True)
    index_path = path / "dialog_index.md"
    index_path.write_text(new_window_index_template(dw, summary), encoding="utf-8")
    (path / "dialog_delta.md").write_text(
        f"# Dialog Delta\n\nsince: {utc_now()}\ndialog_window_id: {dw}\n\n## new_or_updated\n- Q-001\n- TH-001\n",
        encoding="utf-8",
    )
    write_window_lock(dw)
    update_catalog_active_window(dw)
    write_project_lock(project_scope_id())
    print(f"created {dw}: {summary}")
    print(f"index: {index_path}")
    sync_records(
        parse_dialog_index(index_path),
        vector_namespace(dw),
        window_meta_path(dw),
        migrate=False,
    )
    cmd_export(dw)
    return 0


def print_accompaniment(
    load_mode: str,
    changed: Optional[List[str]] = None,
    handoff_ready: Optional[bool] = None,
) -> None:
    dw = resolve_dialog_window_id()
    ok, _ = db_ping()
    delta_path = window_delta_path(dw)
    if changed is None and delta_path.is_file():
        changed = parse_delta_list(delta_path.read_text(encoding="utf-8"), "changed_ids")
    changed = changed or []
    access = "hybrid" if ok else "structured-only"
    print("---")
    print(f"project: {project_scope_id()}")
    print(f"window: {dw}")
    print(f"master: {MASTER_EV_ID}")
    print(f"load_mode: {load_mode}")
    print(f"changed: {', '.join(changed) if changed else 'none'}")
    if handoff_ready is not None:
        print(f"handoff_ready: {'true' if handoff_ready else 'false'}")
    print(f"access: {access}")
    print(f"embed_backend: {last_embed_source(vector_namespace(dw))}")
    print("---")


def cmd_restore(dialog_window_id: str, migrate: bool = True) -> int:
    assert_project_scope("restore")
    dw = dialog_window_id.strip()
    if not dw.startswith("DW-"):
        print(f"ERROR: invalid dialog window id {dw}", file=sys.stderr)
        return 1
    index_path = window_index_path(dw)
    if not index_path.is_file():
        print(f"ERROR: missing window index {index_path}", file=sys.stderr)
        return 1
    write_window_lock(dw)
    update_catalog_active_window(dw)
    validate_window_scope("restore", dw)
    index_text = index_path.read_text(encoding="utf-8")
    records = parse_dialog_index(index_path)
    sync_records(records, vector_namespace(dw), window_meta_path(dw), migrate)
    summary = ""
    for row in list_dialog_windows():
        if row["id"] == dw:
            summary = row["summary"]
            break
    delta_path = window_delta_path(dw)
    changed = parse_delta_list(delta_path.read_text(encoding="utf-8"), "changed_ids") if delta_path.is_file() else []
    print(f"restored active window: {dw}")
    print(f"index: {index_path}")
    print("load_mode: delta")
    print(f"delta: {delta_path}")
    if changed:
        print(f"changed: {', '.join(changed)}")
    print(f"archive_bundle: {window_bundle_path(dw)} (do not load by default)")
    print("expand: /custom-rule: dci expand CL-NNN | EV-NNN")
    if summary:
        print(f"summary: {summary}")
    hot_val = hot_open_query(index_text, records)
    if hot_val:
        print(f"hot_open: {hot_val}")
        try:
            results, _ = lookup_results(hot_val, top_k=3, scope="window")
            if results:
                print("hydrate:")
                for score, lid, snippet in results:
                    print(f"  {lid}\t{score:.4f}\t{snippet[:120]}")
        except SystemExit:
            pass
    print_accompaniment(load_mode="restore", changed=changed, handoff_ready=False)
    return 0


def cmd_compress(force: bool = False) -> int:
    """User command: /custom-rule: dci compress — materialize, doctor, validate, sync, handoff."""
    validate_window_scope("compress")
    dw = resolve_dialog_window_id()
    index_path = window_index_path(dw)

    mat_rc = cmd_materialize(dw)
    if mat_rc != 0 and not force:
        print("ERROR materialize failed; fix ledger and retry compress", file=sys.stderr)
        return 1

    val_rc = cmd_validate()
    if val_rc == 1 and not force:
        # Self-heal known structural defects (legacy bootstrap), then re-validate.
        cmd_doctor(dw)
        val_rc = cmd_validate()
    if val_rc == 1 and not force:
        print(
            "ERROR validate gate failed; fix ledger (`dci-vector.sh doctor`) or use --force",
            file=sys.stderr,
        )
        return 1
    embed_src = last_embed_source(vector_namespace(dw))
    if embed_src.startswith("hash_embed") and not force:
        tei_ok, tei_reason = tei_ping()
        print(
            "ERROR compress requires tei|openai embedding backend; pass_with_risk only with --force",
            file=sys.stderr,
        )
        print("blocker: embed_backend=hash_embed:384 (semantic lookup not guaranteed)", file=sys.stderr)
        print("recovery:", file=sys.stderr)
        print("  1) bash scripts/dci-vector.sh up", file=sys.stderr)
        print("  2) uncomment DCI_EMBED_URL in .cursor/dci/dci.env", file=sys.stderr)
        print("  3) bash scripts/dci-vector.sh compress", file=sys.stderr)
        print(f"  tei: {'ok' if tei_ok else 'unavailable'} ({tei_reason})", file=sys.stderr)
        return 1

    window_records = parse_dialog_index(index_path)
    project_records = parse_project_catalog()
    before_w = load_snapshot(window_snapshot_path(dw))
    before_p = load_snapshot(project_snapshot_path())
    after_w = snapshot_records(window_records)
    after_p = snapshot_records(project_records)
    delta_w = compute_delta(before_w, after_w)
    delta_p = compute_delta(before_p, after_p)
    since = parse_header_field(
        window_delta_path(dw).read_text(encoding="utf-8"),
        "compressed_at",
    ) if window_delta_path(dw).is_file() else utc_now()

    cmd_sync_project(migrate=True)
    cmd_sync_window(migrate=True, dialog_window_id=None)
    save_snapshot(window_snapshot_path(dw), after_w)
    save_snapshot(project_snapshot_path(), after_p)
    cmd_export(None)

    checksum = index_checksum(after_w)
    changed = sorted(set(delta_w["new_or_updated"] + delta_p.get("new_or_updated", [])))
    write_dialog_delta(dw, delta_w, delta_p, checksum, since)
    sync_window_registry(dw)

    ok, _ = db_ping()
    fb = read_fallback(vector_namespace(dw))
    pending = sum(1 for r in fb if not r.get("synced_to_db"))
    restore_cmd = f"/custom-rule: dci restore {dw}"
    print(f"compressed: project {project_scope_id()} (EV/CP/catalog) + window {dw}")
    print(f"project: {project_scope_id()}")
    print(f"window: {dw}")
    print(f"namespace: {vector_namespace(dw)}")
    print(f"access: {'hybrid' if ok else 'structured-only'}")
    print(f"embedded_window: {len([r for r in fb if r.get('synced_to_db')])}")
    print(f"pending: {pending}")
    print(f"delta: {window_delta_path(dw)}")
    print(f"index_checksum: {checksum}")
    print("handoff_ready: true")
    print("next_chat: откройте новый Cursor chat")
    print(f"restore: {restore_cmd}")
    print(f"delta_since: {since}")
    if changed:
        print(f"changed: {', '.join(changed)}")
    else:
        print("changed: none")
    print_accompaniment(load_mode="delta", changed=changed, handoff_ready=True)
    return 0


def cmd_windows() -> int:
    """User command: /custom-rule: dci windows — project branch tree + dialog/history windows."""
    validate_project_scope("windows")
    active = resolve_dialog_window_id()
    locked = read_window_lock()
    print(f"project: {project_scope_id()}")
    print(f"master: {MASTER_EV_ID}")
    print(f"active_window: {active}")
    print(f"lock_window: {locked or active}")
    print("format: id | name: «…» | desc: «…» | [slot][lifecycle]")
    print("")
    print("tree:")
    print("  branches/")
    for line in format_branch_tree(list_branches()):
        print(f"  {line}")
    print("  dialogs/")
    for line in format_dialog_tree(list_dialog_windows(), active):
        print(f"  {line}")
    print("")
    print("restore: /custom-rule: dci restore <DW-NNN>")
    return 0


def cmd_projects() -> int:
    """User command: /custom-rule: dci projects — multi-project tree with dialog summaries."""
    current = project_scope_id()
    print(f"current_project: {current}")
    print("")
    print("projects:")
    for item in discover_projects():
        pid = item["project_id"]
        root = item["root"]
        marker = "active" if pid == current else ""
        print("")
        print_project_tree(pid, root, "", marker=marker, compact=(pid != current))
    print("")
    print("switch project: set DCI_PROJECT_ID + open repo; restore window: /custom-rule: dci restore <DW-NNN>")
    return 0


def cmd_user_restore(target: str, summary: str = "") -> int:
    """User command: /custom-rule: dci restore DW-NNN | restore-new \"summary\"."""
    validate_project_scope("restore")
    t = target.strip()
    if t.lower() in ("новое", "new", "__new__"):
        if not summary.strip():
            print("ERROR: summary required for new window", file=sys.stderr)
            return 1
        cmd_window_new(summary.strip())
        dw = resolve_dialog_window_id()
        print(f"created_and_active: {dw}")
        return 0
    if not t.startswith("DW-"):
        print(f"ERROR: invalid window id {t}", file=sys.stderr)
        return 1
    return cmd_restore(t, migrate=True)


def cmd_status() -> int:
    validate_window_scope("status")
    current = project_scope_id()
    dw = resolve_dialog_window_id()
    indexed = parse_index_project_id()
    locked = read_project_lock()
    wlocked = read_window_lock()
    ok, reason = db_ping()
    tei_ok, tei_reason = tei_ping()
    print(f"project_id: {current}")
    print(f"dialog_window_id: {dw}")
    print(f"index_project_id: {indexed or 'none'}")
    print(f"lock_project_id: {locked or 'none'}")
    print(f"lock_window_id: {wlocked or 'none'}")
    print(f"master_branch: {MASTER_EV_ID}")
    print(f"vector_namespace: {vector_namespace(dw)}")
    print(f"project_namespace: {project_vector_namespace()}")
    print(f"pgvector: {'ok' if ok else 'unavailable'} ({reason})")
    print(f"tei: {'ok' if tei_ok else 'unavailable'} ({tei_reason})")
    print(f"embed_backend: {last_embed_source(vector_namespace(dw))}")
    print(f"fallback: {FALLBACK_PATH} ({len(read_fallback())} rows for project)")
    update_meta(
        meta_path=window_meta_path(dw),
        backend_status="ok" if ok else "unavailable",
        access_mode="hybrid" if ok else "structured-only",
        embedded_ids=[r["ledger_id"] for r in read_fallback(vector_namespace(dw)) if r.get("synced_to_db")],
        pending_ids=[r["ledger_id"] for r in read_fallback(vector_namespace(dw)) if not r.get("synced_to_db")],
        fallback_count=len(read_fallback(vector_namespace(dw))),
        last_action="status",
        embed_source=env("DCI_EMBEDDING_MODEL", "hash_embed:384"),
        namespace=vector_namespace(dw),
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="DCI vector sync v9 (delta handoff + local TEI)")
    parser.add_argument(
        "command",
        choices=[
            "status",
            "sync",
            "migrate",
            "lookup",
            "export",
            "import",
            "catalog",
            "restore",
            "window-new",
            "compress",
            "materialize",
            "windows",
            "projects",
            "validate",
            "doctor",
            "user-restore",
        ],
    )
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="force re-embed all records (also auto on hash_embed→tei upgrade)",
    )
    parser.add_argument("--force", action="store_true", help="bypass validate/hash gate on compress")
    parser.add_argument("--project", action="store_true", help="sync/lookup project EV namespace")
    parser.add_argument("--all", action="store_true", help="sync both window and project")
    parser.add_argument("--query", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--summary", default="", help="window-new summary text")
    parser.add_argument("--window", default="", help="target dialog window id")
    parser.add_argument("--scope", choices=["window", "project"], default="window")
    parser.add_argument("--mode", choices=["all", "branches", "windows"], default="all")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)

    load_dotenv_file(REPO_ROOT / ".env")
    load_dotenv_file(REPO_ROOT / ".cursor" / "dci" / "dci.env")
    if not (REPO_ROOT / ".cursor" / "dci" / "dci.env").is_file():
        load_dotenv_file(REPO_ROOT / ".cursor" / "dci" / "dci.env.example")

    if args.command == "status":
        return cmd_status()

    if args.command == "catalog":
        return cmd_catalog(args.mode)

    if args.command == "window-new":
        return cmd_window_new(args.summary)

    if args.command == "restore":
        if not args.window:
            print("ERROR: --window required for restore", file=sys.stderr)
            return 1
        return cmd_restore(args.window, migrate=args.migrate)

    if args.command == "compress":
        return cmd_compress(force=args.force)

    if args.command == "materialize":
        return cmd_materialize(args.window or None)

    if args.command == "validate":
        return cmd_validate()

    if args.command == "doctor":
        return cmd_doctor(args.window or None)

    if args.command == "windows":
        return cmd_windows()

    if args.command == "projects":
        return cmd_projects()

    if args.command == "user-restore":
        if not args.window and not args.summary:
            print("ERROR: --window or --summary required for user-restore", file=sys.stderr)
            return 1
        target = args.window or "новое"
        return cmd_user_restore(target, args.summary)

    if args.command == "migrate":
        assert_window_scope("migrate")
        n = migrate_fallback_to_db(vector_namespace())
        n += migrate_fallback_to_db(project_vector_namespace())
        print(f"migrated {n} row(s)")
        return 0

    if args.command == "lookup":
        if not args.query:
            print("ERROR: --query required", file=sys.stderr)
            return 1
        scope = "project" if args.project or args.scope == "project" else "window"
        assert_window_scope("lookup")
        return cmd_lookup(args.query, args.top_k, scope=scope)

    if args.command == "export":
        return cmd_export(args.window or None)

    if args.command == "import":
        if not args.source:
            print("ERROR: --source required for import", file=sys.stderr)
            return 1
        return cmd_import(args.source, args.window or None)

    if args.command == "sync":
        rc = 0
        if args.all or not args.project:
            rc = cmd_sync_window(args.migrate, args.window or None, reembed=args.reembed)
        if args.all or args.project:
            rc = cmd_sync_project(args.migrate, reembed=args.reembed) or rc
        return rc

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
