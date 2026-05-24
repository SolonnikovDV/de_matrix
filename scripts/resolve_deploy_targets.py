#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, NoReturn


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _fail(message: str) -> NoReturn:
    print(f"[resolve-deploy-targets] {message}", file=sys.stderr)
    raise SystemExit(1)


def _normalize_port(value: str, *, field_name: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "22"
    try:
        port = int(raw)
    except ValueError:
        _fail(f"{field_name} must be an integer, got: {raw!r}")
    if port < 1 or port > 65535:
        _fail(f"{field_name} out of range 1..65535: {port}")
    return str(port)


def _normalize_target(raw: Dict[str, Any], *, index: int, default_port: str) -> Dict[str, str]:
    if not isinstance(raw, dict):
        _fail(f"Target #{index} must be an object")
    host = str(raw.get("host") or "").strip()
    user = str(raw.get("user") or "").strip()
    app_dir = str(raw.get("app_dir") or "").strip()
    port = _normalize_port(str(raw.get("port") or default_port), field_name=f"target[{index}].port")
    if not host:
        _fail(f"Target #{index} missing required field: host")
    if not user:
        _fail(f"Target #{index} missing required field: user")
    if not app_dir:
        _fail(f"Target #{index} missing required field: app_dir")
    return {
        "host": host,
        "user": user,
        "port": port,
        "app_dir": app_dir,
    }


def _from_json_secret(secret: str, default_port: str) -> List[Dict[str, str]]:
    try:
        payload = json.loads(secret)
    except json.JSONDecodeError as exc:
        _fail(f"PROD_DEPLOY_TARGETS_JSON is not valid JSON: {exc}")
    if not isinstance(payload, list) or not payload:
        _fail("PROD_DEPLOY_TARGETS_JSON must be a non-empty JSON array")
    return [_normalize_target(item, index=i, default_port=default_port) for i, item in enumerate(payload)]


def _from_legacy(default_port: str) -> List[Dict[str, str]]:
    host = _env("PROD_SSH_HOST")
    user = _env("PROD_SSH_USER")
    app_dir = _env("PROD_APP_DIR")
    if not host or not user or not app_dir:
        _fail(
            "Missing legacy target settings: PROD_SSH_HOST, PROD_SSH_USER, PROD_APP_DIR "
            "(or provide PROD_DEPLOY_TARGETS_JSON)"
        )
    return [
        {
            "host": host,
            "user": user,
            "port": default_port,
            "app_dir": app_dir,
        }
    ]


def main() -> int:
    default_port = _normalize_port(_env("PROD_SSH_PORT"), field_name="PROD_SSH_PORT")
    targets_json = _env("PROD_DEPLOY_TARGETS_JSON")
    targets = _from_json_secret(targets_json, default_port) if targets_json else _from_legacy(default_port)
    print(json.dumps(targets, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
