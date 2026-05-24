#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash

from storage.db import db_session
from storage.models import User
from sqlalchemy import select

JSON_MIME = "application/json"
DEFAULT_BASE_CANDIDATES = [
    "http://127.0.0.1:5001",
    "https://127.0.0.1",
    "http://127.0.0.1",
]
BASE_URL_ENV = (os.environ.get("DE_MATRIX_E2E_BASE_URL") or "").strip()
INSECURE_TLS = (os.environ.get("DE_MATRIX_E2E_INSECURE_TLS") or "1").strip().lower() in ("1", "true", "yes")
DB_BOOTSTRAP_ENABLED = (os.environ.get("DE_MATRIX_E2E_DB_BOOTSTRAP") or "0").strip().lower() in ("1", "true", "yes")
API_DOMAINS_PATH = "/api/domains"
AUTH_USERNAME = (os.environ.get("DE_MATRIX_E2E_USERNAME") or "e2e_admin").strip()
AUTH_PASSWORD = os.environ.get("DE_MATRIX_E2E_PASSWORD") or "E2E_Admin_ChangeMe_123!"
AUTH_NEW_PASSWORD = os.environ.get("DE_MATRIX_E2E_NEW_PASSWORD") or "E2E_Admin_ChangeMe_456!"
AUTH_FULL_NAME = "E2E Admin"
AUTH_EMAIL = "e2e-admin@localhost"
TIMEOUT_SEC = int(os.environ.get("DE_MATRIX_E2E_TIMEOUT") or "90")
FALLBACK_ADMIN_USERNAME = (os.environ.get("DE_MATRIX_ADMIN_USERNAME") or "admin").strip()
FALLBACK_ADMIN_PASSWORD = os.environ.get("DE_MATRIX_ADMIN_PASSWORD") or ""


def _build_ssl_context() -> Optional[ssl.SSLContext]:
    if not INSECURE_TLS:
        return None
    return ssl._create_unverified_context()


def _build_http_opener(base_url: str):
    cj = CookieJar()
    handlers: List[Any] = [request.HTTPCookieProcessor(cj)]
    if base_url.startswith("https://"):
        handlers.append(request.HTTPSHandler(context=_build_ssl_context()))
    return request.build_opener(*handlers)


def _probe_base_url(url: str) -> bool:
    opener = _build_http_opener(url)
    req = request.Request(f"{url}/api/schema", headers={"Accept": JSON_MIME}, method="GET")
    try:
        with opener.open(req, timeout=8) as resp:
            return int(getattr(resp, "status", 0)) in (200, 401, 403)
    except error.HTTPError as exc:
        return int(exc.code) in (200, 401, 403)
    except Exception:
        return False


def _resolve_base_url() -> str:
    if BASE_URL_ENV:
        return BASE_URL_ENV.rstrip("/")
    for candidate in DEFAULT_BASE_CANDIDATES:
        c = candidate.rstrip("/")
        if _probe_base_url(c):
            return c
    return DEFAULT_BASE_CANDIDATES[0]


BASE_URL = _resolve_base_url()
OPENER = _build_http_opener(BASE_URL)


def _http_request(
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
) -> Tuple[int, str]:
    req = request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=headers or {},
        method=method.upper(),
    )
    try:
        with OPENER.open(req, timeout=TIMEOUT_SEC) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def _http_get_json(path: str) -> Dict[str, Any]:
    code, text = _http_request("GET", path, headers={"Accept": JSON_MIME})
    if code >= 400:
        raise RuntimeError(f"GET {path} failed ({code}): {text[:800]}")
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GET {path} returned non-JSON: {text[:800]}") from exc


def _http_post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    code, text = _http_request(
        "POST",
        path,
        headers={
            "Accept": JSON_MIME,
            "Content-Type": JSON_MIME,
        },
        body=body,
    )
    if code >= 400:
        raise RuntimeError(f"POST {path} failed ({code}): {text[:800]}")
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"POST {path} returned non-JSON: {text[:800]}") from exc


def _http_post_form(path: str, fields: Dict[str, str]) -> Tuple[int, str]:
    body = parse.urlencode(fields).encode("utf-8")
    return _http_request(
        "POST",
        path,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body,
    )


def _http_post_multipart(path: str, file_name: str, file_bytes: bytes, fields: Dict[str, str]) -> Dict[str, Any]:
    boundary = f"----de-matrix-e2e-{uuid.uuid4().hex}"
    parts: List[bytes] = []

    for key, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                f"{value}\r\n".encode("utf-8"),
            ]
        )

    parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode("utf-8"),
            f"Content-Type: {JSON_MIME}\r\n\r\n".encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    body = b"".join(parts)
    code, text = _http_request(
        "POST",
        path,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": JSON_MIME},
        body=body,
    )
    if code >= 400:
        raise RuntimeError(f"POST {path} failed ({code}): {text[:800]}")
    return json.loads(text or "{}")


def _ensure_e2e_user() -> None:
    with db_session() as session:
        user = session.execute(select(User).where(User.username == AUTH_USERNAME)).scalars().first()
        if not user:
            session.add(
                User(
                    username=AUTH_USERNAME,
                    role="admin",
                    full_name=AUTH_FULL_NAME,
                    email=AUTH_EMAIL,
                    password_hash=generate_password_hash(AUTH_PASSWORD),
                    must_change_password=False,
                    is_active=True,
                )
            )
            return

        user.role = "admin"
        user.full_name = user.full_name or AUTH_FULL_NAME
        user.email = user.email or AUTH_EMAIL
        user.is_active = True
        user.password_hash = generate_password_hash(AUTH_PASSWORD)
        user.must_change_password = False


def _try_login(username: str, password: str) -> Tuple[bool, str]:
    uname = (username or "").strip()
    if not uname:
        return False, "username is empty"
    code, text = _http_post_form(
        "/login",
        {
            "username": uname,
            "password": password,
            "next": "/",
        },
    )
    if code >= 400:
        return False, f"login failed ({code}): {text[:200]}"

    probe_code, probe_text = _http_request("GET", API_DOMAINS_PATH, headers={"Accept": JSON_MIME})
    if probe_code == 200:
        return True, "ok"

    if probe_code == 403 and "Password change required" in probe_text:
        pwd_code, pwd_text = _http_post_form(
            "/account/password",
            {
                "old_password": password,
                "new_password": AUTH_NEW_PASSWORD,
                "confirm_password": AUTH_NEW_PASSWORD,
            },
        )
        if pwd_code >= 400:
            return False, f"password change failed ({pwd_code}): {pwd_text[:200]}"
        probe_code, probe_text = _http_request("GET", API_DOMAINS_PATH, headers={"Accept": JSON_MIME})
        if probe_code == 200:
            return True, "ok (password changed)"

    return False, f"domains probe status={probe_code}, body={probe_text[:200]}"


def _ensure_authenticated_session() -> None:
    attempts: List[str] = []
    login_candidates: List[Tuple[str, str, str]] = [
        ("e2e", AUTH_USERNAME, AUTH_PASSWORD),
    ]
    if FALLBACK_ADMIN_USERNAME and FALLBACK_ADMIN_PASSWORD:
        if not (
            FALLBACK_ADMIN_USERNAME == AUTH_USERNAME
            and FALLBACK_ADMIN_PASSWORD == AUTH_PASSWORD
        ):
            login_candidates.append(("admin_fallback", FALLBACK_ADMIN_USERNAME, FALLBACK_ADMIN_PASSWORD))

    for label, username, password in login_candidates:
        ok, reason = _try_login(username, password)
        attempts.append(f"{label}:{username}:{reason}")
        if ok:
            return

    if DB_BOOTSTRAP_ENABLED:
        _ensure_e2e_user()
        ok, reason = _try_login(AUTH_USERNAME, AUTH_PASSWORD)
        attempts.append(f"db_bootstrap:{AUTH_USERNAME}:{reason}")
        if ok:
            return
    else:
        attempts.append("db_bootstrap:disabled")

    raise RuntimeError("Authentication failed. Attempts: " + " | ".join(attempts))


def _upload_json_payload(
    payload: Dict[str, Any],
    merge_mode: str,
    target_domain: Optional[str],
    target_skill: Optional[str],
) -> Dict[str, Any]:
    fields = {"merge_mode": merge_mode}
    if target_domain:
        fields["target_domain"] = target_domain
    if target_skill:
        fields["target_skill"] = target_skill
    return _http_post_multipart(
        "/api/source/upload",
        "e2e_payload.json",
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        fields,
    )


@dataclass
class ScenarioResult:
    mode: str
    change_id: Optional[int]
    staging_batch_id: Optional[int]
    upload_ok: bool
    has_diff: bool
    has_patch: bool
    has_upsert_plan: bool
    has_structure_change: bool
    approved_ok: bool
    apply_ok: bool
    final_status: str
    applied: bool
    notes: str


@dataclass
class RollbackScenarioResult:
    ok: bool
    source_change_id: Optional[int]
    rollback_change_id: Optional[int]
    source_apply_ok: bool
    rollback_create_ok: bool
    rollback_apply_ok: bool
    source_structure_changed: bool
    rollback_structure_changed: bool
    source_signature_before: str
    source_signature_after: str
    rollback_signature_after: str
    signatures_match: bool
    source_final_status: str
    rollback_final_status: str
    notes: str


def _run_scenario(
    mode: str,
    payload: Dict[str, Any],
    target_domain: Optional[str] = None,
    target_skill: Optional[str] = None,
) -> ScenarioResult:
    upload = _upload_json_payload(payload, mode, target_domain, target_skill)
    change_id = upload.get("change_id")
    if not upload.get("ok") or not change_id:
        return ScenarioResult(
            mode=mode,
            change_id=change_id,
            staging_batch_id=upload.get("staging_batch_id"),
            upload_ok=False,
            has_diff=False,
            has_patch=False,
            has_upsert_plan=False,
            has_structure_change=False,
            approved_ok=False,
            apply_ok=False,
            final_status="unknown",
            applied=False,
            notes=f"upload failed: {upload}",
        )

    details = _http_get_json(f"/api/changes/{change_id}")
    revs = details.get("change", {}).get("revisions") or []
    latest = revs[-1] if revs else {}
    payload_latest = latest.get("payload") or {}
    has_diff = isinstance(payload_latest.get("structural_diff"), dict)
    has_patch = isinstance(payload_latest.get("json_patch"), list)
    has_upsert_plan = isinstance(payload_latest.get("upsert_plan"), dict)
    has_structure_change = isinstance(payload_latest.get("structure_change"), dict)

    in_review = _http_post_json(
        f"/api/changes/{change_id}/status",
        {"status": "in_review", "comment": f"{mode} in_review"},
    )
    approved = _http_post_json(
        f"/api/changes/{change_id}/status",
        {"status": "approved", "comment": f"{mode} approved"},
    )
    apply = _http_post_json(f"/api/changes/{change_id}/apply", {})
    final_details = _http_get_json(f"/api/changes/{change_id}")
    final_change = final_details.get("change") or {}

    return ScenarioResult(
        mode=mode,
        change_id=change_id,
        staging_batch_id=latest.get("staging_batch_id"),
        upload_ok=bool(upload.get("ok")),
        has_diff=has_diff,
        has_patch=has_patch,
        has_upsert_plan=has_upsert_plan,
        has_structure_change=has_structure_change,
        approved_ok=bool(in_review.get("ok")) and bool(approved.get("ok")),
        apply_ok=bool(apply.get("ok")),
        final_status=str(final_change.get("status") or ""),
        applied=bool(final_change.get("applied")),
        notes="ok",
    )


def _latest_change_payload(change_id: int) -> Dict[str, Any]:
    details = _http_get_json(f"/api/changes/{change_id}")
    revs = details.get("change", {}).get("revisions") or []
    latest = revs[-1] if revs else {}
    payload_latest = latest.get("payload") or {}
    if not isinstance(payload_latest, dict):
        return {}
    return payload_latest


def _promote_change_to_applied(change_id: int, label: str) -> Tuple[bool, str]:
    in_review = _http_post_json(
        f"/api/changes/{change_id}/status",
        {"status": "in_review", "comment": f"{label} in_review"},
    )
    approved = _http_post_json(
        f"/api/changes/{change_id}/status",
        {"status": "approved", "comment": f"{label} approved"},
    )
    apply = _http_post_json(f"/api/changes/{change_id}/apply", {})
    final_details = _http_get_json(f"/api/changes/{change_id}")
    final_change = final_details.get("change") or {}
    final_status = str(final_change.get("status") or "")
    applied = bool(final_change.get("applied"))
    ok = bool(in_review.get("ok")) and bool(approved.get("ok")) and bool(apply.get("ok")) and final_status == "applied" and applied
    return ok, final_status


def _run_structure_rollback_scenario() -> RollbackScenarioResult:
    ts = int(time.time())
    source_change_id: Optional[int] = None
    rollback_change_id: Optional[int] = None
    source_apply_ok = False
    rollback_create_ok = False
    rollback_apply_ok = False
    source_structure_changed = False
    rollback_structure_changed = False
    source_signature_before = ""
    source_signature_after = ""
    rollback_signature_after = ""
    signatures_match = False
    source_final_status = "unknown"
    rollback_final_status = "unknown"
    notes = "ok"

    try:
        tree_data = _http_get_json("/api/admin/tree-editor/data")
        nodes = tree_data.get("nodes") or []
        if not isinstance(nodes, list):
            raise RuntimeError("constructor tree returned invalid nodes payload")

        mutated_nodes = json.loads(json.dumps(nodes, ensure_ascii=False))
        mutated_nodes.append(
            {
                "name": f"E2E Rollback Root {ts}",
                "children": [
                    {
                        "name": "E2E Rollback Leaf",
                        "children": [],
                    }
                ],
            }
        )

        submit = _http_post_json(
            "/api/admin/tree-editor/submit",
            {
                "nodes": mutated_nodes,
                "title": f"E2E structure change {ts}",
                "confirm_relations": True,
            },
        )
        source_change_id = int(submit.get("change_id") or 0) or None
        if not source_change_id:
            raise RuntimeError(f"tree-editor submit failed: {submit}")

        source_payload = _latest_change_payload(source_change_id)
        source_sc = source_payload.get("structure_change") if isinstance(source_payload.get("structure_change"), dict) else {}
        source_structure_changed = bool(source_sc.get("is_changed"))
        source_signature_before = str(source_sc.get("signature_before") or "")
        source_signature_after = str(source_sc.get("signature_after") or "")

        source_apply_ok, source_final_status = _promote_change_to_applied(source_change_id, "structure-change")
        if not source_apply_ok:
            notes = f"source apply failed: status={source_final_status}"
            return RollbackScenarioResult(
                ok=False,
                source_change_id=source_change_id,
                rollback_change_id=rollback_change_id,
                source_apply_ok=source_apply_ok,
                rollback_create_ok=rollback_create_ok,
                rollback_apply_ok=rollback_apply_ok,
                source_structure_changed=source_structure_changed,
                rollback_structure_changed=rollback_structure_changed,
                source_signature_before=source_signature_before,
                source_signature_after=source_signature_after,
                rollback_signature_after=rollback_signature_after,
                signatures_match=signatures_match,
                source_final_status=source_final_status,
                rollback_final_status=rollback_final_status,
                notes=notes,
            )

        rollback_resp = _http_post_json(f"/api/changes/{source_change_id}/structure-rollback", {})
        rollback_change_id = int(rollback_resp.get("change_id") or 0) or None
        rollback_create_ok = bool(rollback_resp.get("ok")) and bool(rollback_change_id)
        if not rollback_create_ok:
            notes = f"rollback create failed: {rollback_resp}"
            return RollbackScenarioResult(
                ok=False,
                source_change_id=source_change_id,
                rollback_change_id=rollback_change_id,
                source_apply_ok=source_apply_ok,
                rollback_create_ok=rollback_create_ok,
                rollback_apply_ok=rollback_apply_ok,
                source_structure_changed=source_structure_changed,
                rollback_structure_changed=rollback_structure_changed,
                source_signature_before=source_signature_before,
                source_signature_after=source_signature_after,
                rollback_signature_after=rollback_signature_after,
                signatures_match=signatures_match,
                source_final_status=source_final_status,
                rollback_final_status=rollback_final_status,
                notes=notes,
            )

        rollback_payload = _latest_change_payload(rollback_change_id)
        rollback_sc = rollback_payload.get("structure_change") if isinstance(rollback_payload.get("structure_change"), dict) else {}
        rollback_structure_changed = bool(rollback_sc.get("is_changed"))
        rollback_signature_after = str(rollback_sc.get("signature_after") or "")
        signatures_match = bool(source_signature_before) and (source_signature_before == rollback_signature_after)

        rollback_apply_ok, rollback_final_status = _promote_change_to_applied(rollback_change_id, "structure-rollback")
        ok = (
            source_apply_ok
            and rollback_create_ok
            and rollback_apply_ok
            and source_structure_changed
            and rollback_structure_changed
            and signatures_match
        )
        if not ok:
            notes = (
                f"rollback validation failed: source_changed={source_structure_changed}, "
                f"rollback_changed={rollback_structure_changed}, signatures_match={signatures_match}, "
                f"rollback_status={rollback_final_status}"
            )
        return RollbackScenarioResult(
            ok=ok,
            source_change_id=source_change_id,
            rollback_change_id=rollback_change_id,
            source_apply_ok=source_apply_ok,
            rollback_create_ok=rollback_create_ok,
            rollback_apply_ok=rollback_apply_ok,
            source_structure_changed=source_structure_changed,
            rollback_structure_changed=rollback_structure_changed,
            source_signature_before=source_signature_before,
            source_signature_after=source_signature_after,
            rollback_signature_after=rollback_signature_after,
            signatures_match=signatures_match,
            source_final_status=source_final_status,
            rollback_final_status=rollback_final_status,
            notes=notes,
        )
    except Exception as exc:
        return RollbackScenarioResult(
            ok=False,
            source_change_id=source_change_id,
            rollback_change_id=rollback_change_id,
            source_apply_ok=source_apply_ok,
            rollback_create_ok=rollback_create_ok,
            rollback_apply_ok=rollback_apply_ok,
            source_structure_changed=source_structure_changed,
            rollback_structure_changed=rollback_structure_changed,
            source_signature_before=source_signature_before,
            source_signature_after=source_signature_after,
            rollback_signature_after=rollback_signature_after,
            signatures_match=signatures_match,
            source_final_status=source_final_status,
            rollback_final_status=rollback_final_status,
            notes=str(exc),
        )


def _ensure_minimum_domain_skill() -> None:
    domains = _http_get_json(API_DOMAINS_PATH).get("domains") or []
    if domains:
        first = domains[0]
        if first.get("name") and (first.get("skills") or []):
            return

    ts = int(time.time())
    bootstrap_payload = {
        "domains": [
            {
                "name": f"E2E Bootstrap Domain {ts}",
                "skills": [
                    {
                        "name": "E2E Bootstrap Skill",
                        "description": "Created automatically for e2e precondition",
                        "actions": [{"text": "E2E Bootstrap Action", "template_id": f"tpl_bootstrap_{ts}"}],
                    }
                ],
            }
        ]
    }
    upload = _upload_json_payload(bootstrap_payload, "append", None, None)
    change_id = upload.get("change_id")
    if not upload.get("ok") or not change_id:
        raise RuntimeError(f"Failed to bootstrap minimum domain/skill: {upload}")
    _http_post_json(f"/api/changes/{change_id}/status", {"status": "in_review", "comment": "bootstrap in_review"})
    _http_post_json(f"/api/changes/{change_id}/status", {"status": "approved", "comment": "bootstrap approved"})
    _http_post_json(f"/api/changes/{change_id}/apply", {})


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E checks for merge modes and structure rollback")
    parser.add_argument(
        "--only-structure-rollback",
        action="store_true",
        help="Run only structure change + rollback scenario",
    )
    args = parser.parse_args()

    _ensure_authenticated_session()
    if args.only_structure_rollback:
        rollback_result = _run_structure_rollback_scenario()
        ok = bool(rollback_result.ok)
        print(
            json.dumps(
                {
                    "ok": ok,
                    "base_url": BASE_URL,
                    "auth_username": AUTH_USERNAME,
                    "structure_rollback": asdict(rollback_result),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if ok else 1

    _ensure_minimum_domain_skill()
    base_domains = _http_get_json(API_DOMAINS_PATH).get("domains") or []
    if not base_domains:
        print("No domains available for append_to_domain/append_to_skill tests", file=sys.stderr)
        return 2

    domain_name = base_domains[0].get("name") or ""
    skills = base_domains[0].get("skills") or []
    if not domain_name or not skills:
        print("Need at least one domain with one skill for mode-specific tests", file=sys.stderr)
        return 2
    skill_name = skills[0]

    ts = int(time.time())
    results: List[ScenarioResult] = []

    append_payload = {
        "domains": [
            {
                "name": f"E2E Append Domain {ts}",
                "skills": [{"name": "Append Skill", "description": "", "actions": [{"text": "Append Action", "template_id": f"tpl_append_{ts}"}]}],
            }
        ]
    }
    results.append(_run_scenario("append", append_payload))

    append_domain_payload = {
        "domains": [
            {
                "name": "Ignored Domain",
                "skills": [{"name": f"E2E Skill In Domain {ts}", "description": "", "actions": [{"text": "Domain Mode Action", "template_id": f"tpl_domain_{ts}"}]}],
            }
        ]
    }
    results.append(_run_scenario("append_to_domain", append_domain_payload, target_domain=domain_name))

    append_skill_payload = {
        "domains": [
            {
                "name": "Ignored Domain",
                "skills": [{"name": "Ignored Skill", "description": "", "actions": [{"text": f"E2E Skill Mode Action {ts}", "template_id": f"tpl_skill_{ts}"}]}],
            }
        ]
    }
    results.append(_run_scenario("append_to_skill", append_skill_payload, target_domain=domain_name, target_skill=skill_name))

    replace_payload = {
        "domains": [
            {
                "name": f"E2E Replace Domain {ts}",
                "skills": [{"name": "Replace Skill", "description": "", "actions": [{"text": "Replace Action", "template_id": f"tpl_replace_{ts}"}]}],
            }
        ]
    }
    results.append(_run_scenario("replace_all", replace_payload))
    rollback_result = _run_structure_rollback_scenario()

    ok = True
    for res in results:
        passed = (
            res.upload_ok
            and res.has_diff
            and res.has_patch
            and res.has_upsert_plan
            and res.has_structure_change
            and res.approved_ok
            and res.apply_ok
            and res.final_status == "applied"
            and res.applied
        )
        if not passed:
            ok = False
    if not rollback_result.ok:
        ok = False

    print(
        json.dumps(
            {
                "ok": ok,
                "base_url": BASE_URL,
                "auth_username": AUTH_USERNAME,
                "domain_for_tests": domain_name,
                "skill_for_tests": skill_name,
                "results": [asdict(r) for r in results],
                "structure_rollback": asdict(rollback_result),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
