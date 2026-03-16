#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сброс к базовой конфигурации: объединяет источники, удаляет чекпоинт.
Используется для очистки после тестовых запусков.
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def main():
    merge_script = BASE / "scripts" / "merge_to_unified_source.py"
    if not merge_script.exists():
        print(f"Скрипт не найден: {merge_script}")
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, str(merge_script)],
        cwd=str(BASE),
    )
    if result.returncode != 0:
        sys.exit(result.returncode)

    checkpoint = BASE / "data" / "checkpoint.yaml"
    if checkpoint.exists():
        checkpoint.unlink()
        print(f"Удалён: {checkpoint}")
    else:
        print("Чекпоинт отсутствует, пропуск")
    print("Готово: базовая конфигурация восстановлена")


if __name__ == "__main__":
    main()
