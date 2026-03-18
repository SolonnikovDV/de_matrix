# -*- coding: utf-8 -*-
"""
Бэкап конфига (metadata.yaml, metadata.json, settings.yaml), источника и чекпоинта при перегрузке.
Восстановление — перезапись файлов и перезагрузка данных.
Проверка совместимости по schema_version.
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from .schema import SCHEMA_VERSION


def _backup_dir(base_dir: Path) -> Path:
    """Каталог для бэкапов: data/backups."""
    d = Path(base_dir) / "data" / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_id() -> str:
    """Уникальный id бэкапа по времени."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


def _stable_state_path(base_dir: Path) -> Path:
    """Файл с указателем на стабильный бэкап."""
    return _backup_dir(base_dir) / "stable_state.json"


def get_stable_backup_id(base_dir: Path) -> Optional[str]:
    """Возвращает id стабильного бэкапа, если он задан."""
    p = _stable_state_path(base_dir)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        bid = (data.get("stable_backup_id") or "").strip()
        return bid or None
    except Exception:
        return None


def set_stable_backup_id(base_dir: Path, backup_id: str) -> bool:
    """Сохраняет id стабильного бэкапа."""
    try:
        p = _stable_state_path(base_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"stable_backup_id": backup_id}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def create_backup(
    base_dir: Path,
    config_dir: Path,
    source_dir: Path,
    source_filename: str,
    checkpoint_path: str,
    change_type: str = "manual",
    note: str = "",
) -> Optional[str]:
    """
    Создаёт бэкап: config (metadata.yaml, metadata.json, settings.yaml) + источник + чекпоинт.
    Возвращает id бэкапа или None при ошибке.
    """
    backup_id = _backup_id()
    dest = _backup_dir(base_dir) / f"backup_{backup_id}"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "config").mkdir(exist_ok=True)
    (dest / "source").mkdir(exist_ok=True)
    ok = True
    try:
        for name in ("metadata.yaml", "metadata.json", "settings.yaml"):
            src = config_dir / name
            if src.exists():
                shutil.copy2(src, dest / "config" / name)
        source_path = source_dir / source_filename
        if source_path.exists():
            shutil.copy2(source_path, dest / "source" / source_filename)
        cp_path = Path(checkpoint_path) if Path(checkpoint_path).is_absolute() else Path(base_dir) / checkpoint_path
        if cp_path.exists():
            shutil.copy2(cp_path, dest / "checkpoint.yaml")
        # Сохраняем meta.json с информацией о бэкапе
        meta = {
            "backup_id": backup_id,
            "created": datetime.now(timezone.utc).isoformat(),
            "source_file": source_filename,
            "checkpoint_file": checkpoint_path,
            "schema_version": SCHEMA_VERSION,
            "change_type": change_type or "manual",
            "note": note or "",
        }
        try:
            src_path = dest / "source" / source_filename
            if src_path.exists() and src_path.suffix.lower() == ".json":
                with open(src_path, "r", encoding="utf-8") as sf:
                    src_data = json.load(sf)
                meta["schema_version"] = src_data.get("schema_version", SCHEMA_VERSION)
        except Exception:
            pass
        with open(dest / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        ok = False
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
    return backup_id if ok else None


def list_backups(base_dir: Path) -> List[Dict[str, Any]]:
    """Список бэкапов: id, created, source_file, schema_version."""
    bd = _backup_dir(base_dir)
    if not bd.exists():
        return []
    stable_id = get_stable_backup_id(base_dir)
    result = []
    for p in sorted(bd.iterdir(), reverse=True):
        if not p.is_dir() or not p.name.startswith("backup_"):
            continue
        meta_path = p / "meta.json"
        backup_id = p.name.replace("backup_", "")
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                result.append({
                    "id": backup_id,
                    "created": meta.get("created", backup_id),
                    "source_file": meta.get("source_file", ""),
                    "schema_version": meta.get("schema_version"),
                    "change_type": meta.get("change_type", "manual"),
                    "note": meta.get("note", ""),
                    "stable": bool(stable_id and backup_id == stable_id),
                })
            except Exception:
                result.append({
                    "id": backup_id,
                    "created": backup_id,
                    "source_file": "",
                    "schema_version": None,
                    "change_type": "manual",
                    "note": "",
                    "stable": bool(stable_id and backup_id == stable_id),
                })
        else:
            result.append({
                "id": backup_id,
                "created": backup_id,
                "source_file": "",
                "schema_version": None,
                "change_type": "manual",
                "note": "",
                "stable": bool(stable_id and backup_id == stable_id),
            })
    # Версия = порядковый номер изменения (1..N по времени).
    for idx, item in enumerate(reversed(result), start=1):
        item["version"] = idx
    return result


def ensure_stable_backup(
    base_dir: Path,
    config_dir: Path,
    source_dir: Path,
    source_filename: str,
    checkpoint_path: str,
) -> Optional[str]:
    """
    Гарантирует наличие stable-состояния.
    1) если уже есть валидный stable — возвращает его;
    2) иначе, если уже есть бэкапы — назначает самым ранним;
    3) иначе создаёт новый стартовый stable-бэкап.
    """
    bid = get_stable_backup_id(base_dir)
    bd = _backup_dir(base_dir)
    if bid and (bd / f"backup_{bid}").exists():
        return bid

    backups = list_backups(base_dir)
    if backups:
        oldest = backups[-1]["id"]
        set_stable_backup_id(base_dir, oldest)
        return oldest

    created = create_backup(
        base_dir=base_dir,
        config_dir=config_dir,
        source_dir=source_dir,
        source_filename=source_filename,
        checkpoint_path=checkpoint_path,
        change_type="stable_init",
        note="Автоматически зафиксированное стабильное состояние",
    )
    if created:
        set_stable_backup_id(base_dir, created)
    return created


def check_backup_compatibility(base_dir: Path, backup_id: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет совместимость бэкапа с текущей схемой.
    Возвращает (compatible, warning_message).
    compatible=True — можно восстанавливать без предупреждений.
    compatible=False и warning — при force восстановление возможно, но с риском.
    """
    bd = _backup_dir(base_dir)
    backup_path = bd / f"backup_{backup_id}"
    if not backup_path.exists() or not backup_path.is_dir():
        return False, "Бэкап не найден"

    meta_path = backup_path / "meta.json"
    backup_schema = None
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            backup_schema = meta.get("schema_version")
        except Exception:
            pass

    if backup_schema is None:
        # Пытаемся прочитать из источника
        source_dir = backup_path / "source"
        if source_dir.exists():
            for f in source_dir.iterdir():
                if f.suffix.lower() == ".json":
                    try:
                        with open(f, "r", encoding="utf-8") as sf:
                            data = json.load(sf)
                        backup_schema = data.get("schema_version")
                    except Exception:
                        pass
                    break

    if backup_schema is None:
        return True, "Версия схемы не указана (старый бэкап). Восстановление возможно, но структура может отличаться."

    if backup_schema != SCHEMA_VERSION:
        return False, (
            f"Бэкап создан со схемой v{backup_schema}, текущая версия v{SCHEMA_VERSION}. "
            "Возможны несовместимости. Используйте «Восстановить принудительно» для отката."
        )

    return True, None


def restore_backup(
    base_dir: Path,
    config_dir: Path,
    source_dir: Path,
    backup_id: str,
) -> bool:
    """
    Восстанавливает данные из бэкапа: перезаписывает config и source.
    Возвращает True при успехе.
    """
    bd = _backup_dir(base_dir)
    backup_path = bd / f"backup_{backup_id}"
    if not backup_path.exists() or not backup_path.is_dir():
        return False
    config_src = backup_path / "config"
    source_src = backup_path / "source"
    checkpoint_src = backup_path / "checkpoint.yaml"
    meta_path = backup_path / "meta.json"
    checkpoint_path = None
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            checkpoint_path = meta.get("checkpoint_file")
        except Exception:
            pass
    try:
        config_dir = Path(config_dir)
        source_dir = Path(source_dir)
        base_dir = Path(base_dir)
        config_dir.mkdir(parents=True, exist_ok=True)
        source_dir.mkdir(parents=True, exist_ok=True)
        if config_src.exists():
            for f in config_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, config_dir / f.name)
        if source_src.exists():
            for f in source_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, source_dir / f.name)
        if checkpoint_src.exists() and checkpoint_path:
            cp_dest = Path(checkpoint_path) if Path(checkpoint_path).is_absolute() else base_dir / checkpoint_path
            cp_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkpoint_src, cp_dest)
        return True
    except Exception:
        return False
