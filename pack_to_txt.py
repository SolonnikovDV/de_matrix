"""
Скрипт 1: упаковывает директорию в zip, сохраняя структуру,
создаёт мапу «файл → расширение» и в архиве все файлы имеют расширение .txt.
Служебные каталоги (.venv, .git, __pycache__ и др.) не включаются в архив.
"""

import os
import sys
import json
import zipfile
from pathlib import Path

# Каталоги, которые не упаковываются (сокращают размер архива и мапы)
EXCLUDE_DIRS = {
    ".venv",
    ".git",
    ".qodo",
    "__pycache__",
    "node_modules",
    ".cursor",
    ".idea",
    ".vscode",
    "venv",
    "env",
    ".eggs",
    "dist",
    "build",
}


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

    with zipfile.ZipFile(
        output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zf:
        for root, dirs, files in os.walk(source_path):
            # Не спускаемся в исключённые каталоги
            dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

            root_path = Path(root)
            for name in files:
                file_path = root_path / name
                try:
                    rel = file_path.relative_to(source_path)
                except ValueError:
                    continue
                rel_str = rel.as_posix()
                _, ext = os.path.splitext(name)
                original_ext = (ext or "").lstrip(".")
                if not original_ext:
                    original_ext = "txt"

                # В архиве храним с расширением .txt
                rel_txt = Path(rel_str).with_suffix(".txt").as_posix()
                extension_map[rel_txt] = original_ext

                zf.write(file_path, rel_txt)

        # Мапу кладём в корень архива
        map_json = json.dumps(extension_map, ensure_ascii=False, indent=2)
        zf.writestr("extension_map.json", map_json.encode("utf-8"))

    print(f"Упаковано в: {output_zip}")
    print(f"Записей в мапе расширений: {len(extension_map)}")


def main():
    if len(sys.argv) < 2:
        print("Использование: python pack_to_txt.py <исходная_директория> [выходной.zip]")
        print("  По умолчанию выходной архив: packed.zip в текущей директории.")
        print("  Служебные каталоги (.venv, .git, __pycache__, node_modules и др.) не включаются.")
        sys.exit(1)

    source_dir = sys.argv[1]
    output_zip = sys.argv[2] if len(sys.argv) > 2 else "packed.zip"

    pack_directory_to_txt(source_dir, output_zip)


if __name__ == "__main__":
    main()
