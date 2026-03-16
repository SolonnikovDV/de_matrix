# -*- coding: utf-8 -*-
"""
Чекпоинт структуры матрицы: сравнение источника с сохранённым состоянием.
При совпадении (hash) структура не перезагружается; при расхождении — пересборка и перезапись чекпоинта.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _content_hash(path: Path) -> str:
    """Хеш содержимого файла для сравнения с чекпоинтом."""
    path = Path(path)
    if not path.exists():
        return ""
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest()


def load_checkpoint(checkpoint_path: Path) -> Optional[Dict]:
    """Загружает чекпоинт из YAML или JSON. Возвращает None если файла нет или ошибка."""
    path = Path(checkpoint_path)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml"):
            if HAS_YAML:
                return yaml.safe_load(raw) or {}
            return json.loads(raw)  # fallback
        return json.loads(raw)
    except Exception:
        return None


def save_checkpoint(checkpoint_path: Path, data: Dict, use_yaml: bool = True) -> None:
    """Сохраняет чекпоинт (tree, source_file, source_hash, updated)."""
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if use_yaml and path.suffix.lower() in (".yaml", ".yml") and HAS_YAML:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def source_matches_checkpoint(source_path: Path, checkpoint: Dict) -> bool:
    """True, если текущий файл-источник совпадает с тем, по которому построен чекпоинт (по хешу)."""
    if not checkpoint or not source_path or not Path(source_path).exists():
        return False
    saved_hash = checkpoint.get("source_hash") or ""
    current_hash = _content_hash(Path(source_path))
    return bool(current_hash and saved_hash == current_hash)


def build_checkpoint_data(
    tree: List[Dict],
    matrix: Dict,
    meta: Dict,
    source_file: str,
    source_hash: str,
) -> Dict:
    """Формирует данные для сохранения в чекпоинт: tree, matrix, meta (единый источник)."""
    from datetime import datetime, timezone
    return {
        "source_file": source_file,
        "source_hash": source_hash,
        "updated": datetime.now(timezone.utc).isoformat(),
        "tree": tree,
        "matrix": matrix,
        "meta": meta,
    }


def get_source_content_hash(path: Path) -> str:
    """Возвращает хеш содержимого файла-источника."""
    return _content_hash(Path(path))
