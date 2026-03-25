#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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

BASE_URL = (os.environ.get("DE_MATRIX_E2E_BASE_URL") or "http://127.0.0.1:5001").rstrip("/")
API_DOMAINS_PATH = "/api/domains"
AUTH_USERNAME = (os.environ.get("DE_MATRIX_E2E_USERNAME") or "e2e_admin").strip()
AUTH_PASSWORD = os.environ.get("DE_MATRIX_E2E_PASSWORD") or "E2E_Admin_ChangeMe_123!"
AUTH_NEW_PASSWORD = os.environ.get("DE_MATRIX_E2E_NEW_PASSWORD") or "E2E_Admin_ChangeMe_456!"
AUTH_FULL_NAME = "E2E Admin"
AUTH_EMAIL = "e2e-admin@localhost"
TIMEOUT_SEC = int(os.environ.get("DE_MATRIX_E2E_TIMEOUT") or "90")


def _build_http_opener():
    cj = CookieJar()
    handlers: List[Any] = [request.HTTPCookieProcessor(cj)]
    if BASE_URL.startswith("https://"):
        handlers.append(request.HTTPSHandler())
    return request.build_opener(*handlers)


OPENER = _build_http_opener()


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
    code, text = _http_request("GET", path, headers={"Accept": "application/json"})
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
            "Accept": "application/json",
            "Content-Type": "application/json",
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
            b"Content-Type: application/json\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    body = b"".join(parts)
    code, text = _http_request(
        "POST",
        path,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
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


def _ensure_authenticated_session() -> None:
    _ensure_e2e_user()
    code, text = _http_post_form(
        "/login",
        {
            "username": AUTH_USERNAME,
            "password": AUTH_PASSWORD,
            "next": "/",
        },
    )
    if code >= 400:
        raise RuntimeError(f"login failed ({code}): {text[:800]}")

    probe_code, probe_text = _http_request("GET", API_DOMAINS_PATH, headers={"Accept": "application/json"})
    if probe_code == 200:
        return

    if probe_code == 403 and "Password change required" in probe_text:
        pwd_code, pwd_text = _http_post_form(
            "/account/password",
            {
                "old_password": AUTH_PASSWORD,
                "new_password": AUTH_NEW_PASSWORD,
                "confirm_password": AUTH_NEW_PASSWORD,
            },
        )
        if pwd_code >= 400:
            raise RuntimeError(f"password change failed ({pwd_code}): {pwd_text[:800]}")
        probe_code, probe_text = _http_request("GET", API_DOMAINS_PATH, headers={"Accept": "application/json"})
        if probe_code == 200:
            return

    raise RuntimeError(f"Authentication failed. domains status={probe_code}, body={probe_text[:800]}")


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
    approved_ok: bool
    apply_ok: bool
    final_status: str
    applied: bool
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
        approved_ok=bool(in_review.get("ok")) and bool(approved.get("ok")),
        apply_ok=bool(apply.get("ok")),
        final_status=str(final_change.get("status") or ""),
        applied=bool(final_change.get("applied")),
        notes="ok",
    )


def main() -> int:
    _ensure_authenticated_session()
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

    ok = True
    for res in results:
        passed = (
            res.upload_ok
            and res.has_diff
            and res.has_patch
            and res.has_upsert_plan
            and res.approved_ok
            and res.apply_ok
            and res.final_status == "applied"
            and res.applied
        )
        if not passed:
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
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
