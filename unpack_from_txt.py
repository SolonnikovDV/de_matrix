"""
Скрипт 2: распаковывает zip в целевую директорию по структуре,
читает мапу расширений и переименовывает все .txt обратно в исходные расширения.
"""

import os
import sys
import json
import zipfile
from pathlib import Path


def unpack_and_restore_extensions(input_zip: str, output_dir: str) -> None:
    """
    Распаковывает input_zip в output_dir, затем по extension_map.json
    заменяет расширения .txt на соответствующие из мапы.
    """
    input_path = Path(input_zip).resolve()
    out_path = Path(output_dir).resolve()

    if not input_path.is_file():
        raise FileNotFoundError(f"Архив не найден: {input_zip}")

    out_path.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(input_path, "r") as zf:
        # Сначала извлекаем extension_map.json
        if "extension_map.json" not in zf.namelist():
            raise ValueError("В архиве отсутствует extension_map.json")

        map_data = zf.read("extension_map.json").decode("utf-8")
        extension_map = json.loads(map_data)

        # Распаковываем все файлы
        for name in zf.namelist():
            if name == "extension_map.json":
                continue
            zf.extract(name, out_path)

    # Заменяем .txt на исходные расширения по мапе
    renamed = 0
    for rel_txt, original_ext in extension_map.items():
        file_path = out_path / rel_txt
        if not file_path.exists():
            continue
        new_name = Path(rel_txt).with_suffix("." + original_ext if original_ext != "txt" else ".txt").name
        new_path = file_path.parent / new_name
        if file_path != new_path:
            file_path.rename(new_path)
            renamed += 1

    print(f"Распаковано в: {out_path}")
    print(f"Восстановлено расширений: {renamed}")


def main():
    if len(sys.argv) < 2:
        print("Использование: python unpack_from_txt.py <архив.zip> [целевая_директория]")
        print("  По умолчанию распаковка в текущую директорию.")
        sys.exit(1)

    input_zip = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    unpack_and_restore_extensions(input_zip, output_dir)


if __name__ == "__main__":
    main()
