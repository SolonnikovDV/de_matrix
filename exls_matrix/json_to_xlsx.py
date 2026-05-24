#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Compatibility shim for older openpyxl versions on newer NumPy.
if not hasattr(np, "float"):
    setattr(np, "float", float)


def _sheet_to_dataframe(sheet_data: dict) -> pd.DataFrame:
    columns = sheet_data.get("columns", [])
    rows = sheet_data.get("rows", [])

    if not isinstance(columns, list):
        columns = []
    if not isinstance(rows, list):
        rows = []

    df = pd.DataFrame(rows)
    if not columns:
        return df

    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]


def convert_json_to_xlsx(input_path: Path, output_path: Path) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    sheets = payload.get("sheets", {})
    if not isinstance(sheets, dict) or not sheets:
        raise ValueError("JSON does not contain non-empty 'sheets' object.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, sheet_data in sheets.items():
            df = _sheet_to_dataframe(sheet_data)
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert JSON workbook dump back to XLSX.",
    )
    parser.add_argument(
        "input_json",
        type=Path,
        help="Path to JSON file created by xlsx_to_json.py",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output XLSX path. Default: same name as input with .xlsx",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input_json
    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON does not exist: {input_path}")

    output_path = args.output or input_path.with_suffix(".xlsx")
    convert_json_to_xlsx(input_path, output_path)
    print(f"XLSX written to: {output_path}")


if __name__ == "__main__":
    main()
