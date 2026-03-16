# -*- coding: utf-8 -*-
"""
Конфиг: config/settings.yaml (пути), config/metadata.yaml (стили и инструменты).
Источник данных — только текст (domains + action_templates, literature и т.д.);
name, icon, color и списки инструментов — в metadata.yaml, инструменты к листьям — по паттернам в тексте.
При загрузке: приоритет по дате модификации; fallback YAML -> JSON; синхронизация файлов при перезапуске.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DEFAULT_SOURCE_DIR = "data/sources"
DEFAULT_CHECKPOINT_FILE = "data/checkpoint.yaml"
DEFAULT_LIBRARY_DIR = "data/library"

_metadata_cache: Optional[Dict] = None


def invalidate_metadata_cache() -> None:
    """Сброс кэша метаданных (при перезагрузке приложения)."""
    global _metadata_cache
    _metadata_cache = None


def _get_mtime(path: Path) -> float:
    """Время модификации файла или 0 если не существует."""
    try:
        return path.stat().st_mtime if path.exists() else 0.0
    except OSError:
        return 0.0


def _load_yaml(path) -> Optional[Dict]:
    try:
        import yaml
        p = Path(path) if not isinstance(path, Path) else path
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        import sys
        print(f"[config] Ошибка загрузки {path}: {e}", file=sys.stderr)
        return None


def _save_yaml(path: Path, data: Dict[str, Any]) -> bool:
    """Сохранение metadata в YAML (требует PyYAML)."""
    try:
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        import sys
        print(f"[config] Ошибка сохранения {path}: {e}", file=sys.stderr)
        return False


def _load_metadata_json(path: Path) -> Optional[Dict]:
    """Загрузка metadata из JSON (fallback при отсутствии PyYAML)."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _save_metadata_json(path: Path, data: Dict[str, Any]) -> bool:
    """Сохранение metadata в JSON."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        import sys
        print(f"[config] Ошибка сохранения {path}: {e}", file=sys.stderr)
        return False


def load_app_config() -> Dict[str, Any]:
    """Настройки путей из config/settings.yaml."""
    settings_path = CONFIG_DIR / "settings.yaml"
    cfg = _load_yaml(settings_path) if settings_path.exists() else {}
    cfg = dict(cfg) if cfg else {}
    cfg.setdefault("source_dir", DEFAULT_SOURCE_DIR)
    cfg.setdefault("checkpoint_file", DEFAULT_CHECKPOINT_FILE)
    cfg.setdefault("default_source", None)
    cfg.setdefault("literature_dir", cfg.get("library_dir", DEFAULT_LIBRARY_DIR))
    cfg.setdefault("flexible", True)
    return cfg


def load_metadata() -> Dict[str, Any]:
    """
    Стили (stack_labels) и инструменты (tools_patterns, tools_groups) из config/metadata.yaml
    или config/metadata.json. Приоритет по дате модификации — используется более свежий файл,
    остальной синхронизируется при перезапуске.
    """
    global _metadata_cache
    if _metadata_cache is not None:
        return _metadata_cache
    meta_dir = CONFIG_DIR if isinstance(CONFIG_DIR, Path) else Path(CONFIG_DIR)
    yaml_path = meta_dir / "metadata.yaml"
    json_path = meta_dir / "metadata.json"
    yaml_mtime = _get_mtime(yaml_path)
    json_mtime = _get_mtime(json_path)

    data: Optional[Dict] = None
    source_format: Optional[str] = None

    # Используем более свежий файл; при равных датах — YAML приоритетнее
    if yaml_mtime >= json_mtime and yaml_path.exists():
        data = _load_yaml(yaml_path)
        if isinstance(data, dict) and data:
            source_format = "yaml"
    if (data is None or not isinstance(data, dict) or not data) and json_path.exists():
        data = _load_metadata_json(json_path)
        if isinstance(data, dict) and data:
            source_format = "json"
    # Если более свежий не загрузился — пробуем второй файл (fallback)
    if not source_format and yaml_path.exists():
        data = _load_yaml(yaml_path)
        if isinstance(data, dict) and data:
            source_format = "yaml"
    if not source_format and json_path.exists():
        data = _load_metadata_json(json_path)
        if isinstance(data, dict) and data:
            source_format = "json"

    # Синхронизация: всегда обновляем второй файл данными из источника
    if isinstance(data, dict) and data and source_format:
        if source_format == "yaml":
            _save_metadata_json(json_path, data)
        else:
            _save_yaml(yaml_path, data)

    _metadata_cache = dict(data) if isinstance(data, dict) else {}
    _metadata_cache.setdefault("stack_labels", {})
    _metadata_cache.setdefault("tools_patterns", {})
    _metadata_cache.setdefault("tools_groups", {})
    return _metadata_cache
