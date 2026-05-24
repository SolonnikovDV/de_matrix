#!/usr/bin/env python3
"""Rename exls matrix column headers to marker format (node_i / leaf_j / label_k)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

HEADER_RENAME = {
    "Домен": "node_1",
    "Раздел": "node_2",
    "Навык": "node_3",
    "Статус": "label_3_node_3",
    "Вопросы": "leaf_1_node_3",
    "Материалы": "leaf_2_node_3",
    "Задачи": "leaf_3_node_3",
    "Опционально для уровня": "label_4_node_3",
    "Опционально": "label_4_node_3",
    "Вопросы ревьюера": "leaf_5_node_3",
    "Автор": "label_1_node_3",
    "Ревьюер": "label_2_node_3",
}

MARKER_ORDER = [
    "node_1",
    "node_2",
    "node_3",
    "label_3_node_3",
    "leaf_1_node_3",
    "leaf_2_node_3",
    "leaf_3_node_3",
    "label_4_node_3",
    "leaf_5_node_3",
    "label_1_node_3",
    "label_2_node_3",
]


def rename_record_keys(record: dict) -> dict:
    out: dict = {}
    for old, new in HEADER_RENAME.items():
        if old in record:
            out[new] = record[old]
    for k, v in record.items():
        if k not in HEADER_RENAME and k not in out:
            out[k] = v
    return out


def rename_columns_list(columns: List[str]) -> List[str]:
    return [HEADER_RENAME.get(c, c) for c in columns]


def load_rows_from_json(path: Path) -> tuple[list[dict], list[str], str]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    fmt = "array"
    if isinstance(data, list):
        rows = [rename_record_keys(r) for r in data if isinstance(r, dict)]
        columns = MARKER_ORDER.copy()
        return rows, columns, fmt
    if isinstance(data, dict) and isinstance(data.get("sheets"), dict):
        fmt = "workbook"
        sheet = next((v for v in data["sheets"].values() if isinstance(v, dict)), None)
        if not sheet:
            raise ValueError(f"No sheets in {path}")
        columns = rename_columns_list(list(sheet.get("columns") or []))
        rows = [rename_record_keys(r) for r in (sheet.get("rows") or []) if isinstance(r, dict)]
        return rows, columns, fmt
    raise ValueError(f"Unsupported JSON format in {path}")


def save_json_workbook(path: Path, rows: list[dict], columns: list[str], source_file: str) -> None:
    payload = {
        "source_file": source_file,
        "sheets": {
            "Matrix": {
                "columns": columns,
                "row_count": len(rows),
                "rows": rows,
            }
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_json_array(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_xlsx(rows: list[dict], xlsx_path: Path) -> None:
    try:
        import numpy as np

        if not hasattr(np, "float"):
            setattr(np, "float", float)
    except ImportError:
        pass
    from openpyxl import Workbook

    columns = MARKER_ORDER.copy()
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    wb = Workbook()
    ws = wb.active
    ws.title = "Matrix"
    ws.append(columns)
    for row in rows:
        ws.append([row.get(col) for col in columns])
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)


def process_file(json_path: Path, xlsx_path: Path | None) -> None:
    rows, columns, fmt = load_rows_from_json(json_path)
    if fmt == "workbook":
        save_json_workbook(json_path, rows, columns, (xlsx_path or json_path.with_suffix(".xlsx")).name)
    else:
        save_json_array(json_path, rows)
    xlsx = xlsx_path or json_path.with_suffix(".xlsx")
    write_xlsx(rows, xlsx)
    print(f"Updated JSON: {json_path}")
    print(f"Updated XLSX: {xlsx}")
    print(f"Rows: {len(rows)}, columns: {len(MARKER_ORDER)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--xlsx", type=Path, default=None)
    args = parser.parse_args()
    process_file(args.json_path, args.xlsx)


if __name__ == "__main__":
    main()
