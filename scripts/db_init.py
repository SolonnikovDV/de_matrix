#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.db import ENGINE
from storage.models import Base


def main():
    Base.metadata.create_all(bind=ENGINE)
    print("Database schema initialized.")


if __name__ == "__main__":
    main()

