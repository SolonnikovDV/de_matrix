#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke-check автоскейла для ключевых merge-сценариев.
Проверяет, что leaf-структура matrix и tree совпадает после каждого сценария.
"""
from copy import deepcopy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tree import build_tree_from_matrix_data, collect_leaves
from core.upload_merge import merge_upload_into_source


def expected_leaf_paths(matrix):
    out = []
    for di, domain in enumerate((matrix or {}).get("domains") or []):
        for si, skill in enumerate(domain.get("skills") or []):
            for ai, action in enumerate(skill.get("actions") or []):
                subactions = action.get("subactions") or []
                if subactions:
                    for subi, _ in enumerate(subactions):
                        out.append(f"{di}/{si}/{ai}/{subi}")
                else:
                    out.append(f"{di}/{si}/{ai}")
    return sorted(out)


def actual_leaf_paths(matrix):
    tree = build_tree_from_matrix_data({"domains": (matrix or {}).get("domains") or []})
    leaves = collect_leaves(tree)
    return sorted("/".join(str(x) for x in (leaf.get("path") or [])) for leaf in leaves)


def check_scenario(name, merged):
    exp = expected_leaf_paths(merged)
    act = actual_leaf_paths(merged)
    if exp != act:
        missing = sorted(set(exp) - set(act))
        extra = sorted(set(act) - set(exp))
        raise AssertionError(
            f"{name}: autoscale mismatch\n"
            f"expected={len(exp)} actual={len(act)}\n"
            f"missing={missing}\nextra={extra}"
        )
    print(f"[OK] {name}: leaf_count={len(exp)}")


def main():
    base = {
        "domains": [
            {
                "name": "Data Platform",
                "skills": [
                    {
                        "name": "Pipelines",
                        "description": "Base skill",
                        "actions": [
                            {"text": "Build ETL job", "template_id": "tpl_etl"},
                            {
                                "text": "Testing strategy",
                                "template_id": "tpl_test_parent",
                                "subactions": [
                                    {"text": "Unit tests", "template_id": "tpl_test_unit"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }

    # 1) append: добавление домена
    upload_append = {
        "domains": [
            {
                "name": "Analytics",
                "skills": [{"name": "BI", "actions": [{"text": "Build dashboard", "template_id": "tpl_bi"}]}],
            }
        ]
    }
    merged_append = merge_upload_into_source(deepcopy(base), upload_append, merge_mode="append")
    check_scenario("append(add_domain)", merged_append)

    # 2) append_to_domain: добавление навыка в существующий домен
    upload_to_domain = {
        "domains": [
            {
                "name": "Any Source Domain",
                "skills": [{"name": "Observability", "actions": [{"text": "Monitor jobs", "template_id": "tpl_obs"}]}],
            }
        ]
    }
    merged_to_domain = merge_upload_into_source(
        deepcopy(base),
        upload_to_domain,
        merge_mode="append_to_domain",
        target_domain="Data Platform",
    )
    check_scenario("append_to_domain(add_skill)", merged_to_domain)

    # 3) append_to_skill: добавление action/subaction в существующий навык
    upload_to_skill = {
        "domains": [
            {
                "name": "External",
                "skills": [
                    {
                        "name": "External Skill",
                        "actions": [
                            {
                                "text": "Data contracts",
                                "template_id": "tpl_contracts",
                                "subactions": [{"text": "Versioning", "template_id": "tpl_contracts_versioning"}],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    merged_to_skill = merge_upload_into_source(
        deepcopy(base),
        upload_to_skill,
        merge_mode="append_to_skill",
        target_domain="Data Platform",
        target_skill="Pipelines",
    )
    check_scenario("append_to_skill(add_action_subaction)", merged_to_skill)

    # 4) replace_all: полная замена структуры
    upload_replace = {
        "domains": [
            {
                "name": "Replaced Domain",
                "skills": [
                    {
                        "name": "Replaced Skill",
                        "actions": [
                            {"text": "Replaced Action", "template_id": "tpl_replaced"},
                            {
                                "text": "Parent Action",
                                "template_id": "tpl_parent",
                                "subactions": [{"text": "Child Action", "template_id": "tpl_child"}],
                            },
                        ],
                    }
                ],
            }
        ]
    }
    merged_replace = merge_upload_into_source(deepcopy(base), upload_replace, merge_mode="replace_all")
    check_scenario("replace_all(full_replace)", merged_replace)

    print("\nAll autoscale regression scenarios passed.")


if __name__ == "__main__":
    main()
