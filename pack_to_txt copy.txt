"""
Скрипт 1: упаковывает директорию в zip, сохраняя структуру,
создаёт мапу «файл → расширение» и в архиве все файлы имеют расширение .txt.
Служебные каталоги (.venv, .git, __pycache__ и др.) не включаются в архив.
"""

import base64
import os
import sys
import json
import zipfile
from pathlib import Path

# Корень проекта — директория, где лежит этот скрипт
PROJECT_ROOT = Path(__file__).resolve().parent

# Каталоги, которые не упаковываются (кеш, служебные)
EXCLUDE_DIRS = {
    ".venv",
    ".git",
    ".qodo",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".cursor",
    ".idea",
    ".vscode",
    "venv",
    "env",
    ".eggs",
    "dist",
    "build",
    "htmlcov",
}

# Расширения и имена файлов кеша, которые не упаковываются
EXCLUDE_FILE_EXTENSIONS = {".pyc", ".pyo", ".pyd"}
EXCLUDE_FILE_NAMES = {".coverage", "coverage.xml", ".DS_Store"}


def _should_skip_dir(dirname: str) -> bool:
    if dirname in EXCLUDE_DIRS:
        return True
    if dirname.endswith(".egg-info"):
        return True
    return False


def pack_directory_to_txt(source_dir: str, output_zip: str) -> None:
    """
    Упаковывает source_dir в output_zip по структуре каталогов.
    Для каждого файла запоминает исходное расширение в мапе.
    В архиве все файлы сохраняются с расширением .txt.
    Каталоги из EXCLUDE_DIRS (например .venv) пропускаются.
    """
    source_path = Path(source_dir).resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(f"Директория не найдена: {source_dir}")

    extension_map = {}  # путь в архиве (с .txt) -> исходное расширение без точки

    output_path = Path(output_zip).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ZIP_STORED — без сжатия, максимальная совместимость с корпоративными
    # почтовыми системами (ZIP_DEFLATED иногда помечается как «повреждённый»)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_STORED) as zf:
        for root, dirs, files in os.walk(source_path):
            # Не спускаемся в исключённые каталоги
            dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

            root_path = Path(root)
            for name in files:
                if name in EXCLUDE_FILE_NAMES:
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in EXCLUDE_FILE_EXTENSIONS:
                    continue
                file_path = root_path / name
                try:
                    rel = file_path.relative_to(source_path)
                except ValueError:
                    continue
                rel_str = rel.as_posix()
                rel_path = Path(rel_str)
                _, ext = os.path.splitext(name)
                original_ext = (ext or "").lstrip(".") or ""  # "" для файлов без расширения

                # Заменяем расширение на .txt (не дописываем!), чтобы службы безопасности
                # не видели реальные расширения (.py, .exe и т.д.)
                rel_txt = (rel_path.parent / (rel_path.stem + ".txt")).as_posix()
                extension_map[rel_txt] = original_ext

                # Base64 — всё содержимое в текстовом виде, сканер не находит бинарник/код
                content = file_path.read_bytes()
                encoded = base64.b64encode(content).decode("ascii")
                zf.writestr(rel_txt, encoded)

        extension_map["_format"] = "base64"
        map_json = json.dumps(extension_map, ensure_ascii=False, indent=2)
        zf.writestr("extension_map.json", map_json.encode("utf-8"))

    # Проверка: архив должен открываться и содержать extension_map
    try:
        with zipfile.ZipFile(output_path, "r") as zf:
            zf.testzip()
            if "extension_map.json" not in zf.namelist():
                raise ValueError("extension_map.json отсутствует в архиве")
    except zipfile.BadZipFile as e:
        raise RuntimeError(f"Архив повреждён: {e}") from e

    print(f"Упаковано в: {output_path}")
    print(f"Записей в мапе расширений: {len(extension_map)}")


def main():
    # По умолчанию: упаковываем корень проекта, архив в корне проекта
    source_dir = sys.argv[1] if len(sys.argv) > 1 else str(PROJECT_ROOT)
    output_zip = sys.argv[2] if len(sys.argv) > 2 else str(PROJECT_ROOT / "packed.zip")

    pack_directory_to_txt(source_dir, output_zip)


if __name__ == "__main__":
    main()
