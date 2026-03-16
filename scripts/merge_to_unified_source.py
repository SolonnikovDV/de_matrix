#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт однократной миграции: объединяет data/sources/matrix_data.json (структура)
и config/meta.json (метаданные) в один файл data/sources/matrix.json — единый источник.
После запуска приложение использует только matrix.json; meta.json больше не нужен для загрузки.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MATRIX_SOURCE = BASE / "data" / "sources" / "matrix_data.json"
META_SOURCE = BASE / "config" / "meta.json"
OUTPUT = BASE / "data" / "sources" / "matrix.json"

# В источник только текст; stack_labels и action_tools — в config/metadata.yaml
META_KEYS = ("action_examples", "literature", "action_templates", "ui_config")


def main():
    if not MATRIX_SOURCE.exists():
        print(f"Файл не найден: {MATRIX_SOURCE}")
        sys.exit(1)
    if not META_SOURCE.exists():
        print(f"Файл не найден: {META_SOURCE}")
        sys.exit(1)
    with open(MATRIX_SOURCE, "r", encoding="utf-8") as f:
        matrix = json.load(f)
    with open(META_SOURCE, "r", encoding="utf-8") as f:
        meta = json.load(f)
    unified = {"domains": matrix.get("domains", [])}
    for k in META_KEYS:
        if k in meta:
            unified[k] = meta[k]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(unified, f, ensure_ascii=False, indent=2)
    print(f"Создан единый источник: {OUTPUT}")
    checkpoint = BASE / "data" / "checkpoint.yaml"
    if checkpoint.exists():
        print("Подсказка: удалите data/checkpoint.yaml, чтобы приложение перезагрузило данные из matrix.json")


if __name__ == "__main__":
    main()
