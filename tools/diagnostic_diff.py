#!/usr/bin/env python3
"""Compare two build diagnostic metadata JSON files."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


MISSING = object()
REGRESSION_STATUSES = {"FAIL", "FAILED", "ERROR"}
PASS_STATUSES = {"PASS", "PASSED", "OK", "SUCCESS"}


def load_metadata(path: str | Path) -> dict[str, Any]:
    metadata_path = Path(path)
    try:
        with metadata_path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{metadata_path} is not valid JSON: {exc.msg}") from exc
    except OSError as exc:
        raise ValueError(f"could not read {metadata_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{metadata_path} must contain a JSON object")
    return data


def _format_path(parts: list[str]) -> str:
    return ".".join(parts) if parts else "$"


def _record_diff(
    before: Any,
    after: Any,
    parts: list[str],
    added: dict[str, Any],
    removed: dict[str, Any],
    changed: dict[str, dict[str, Any]],
) -> None:
    path = _format_path(parts)

    if before is MISSING:
        added[path] = after
        return
    if after is MISSING:
        removed[path] = before
        return

    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            _record_diff(
                before.get(key, MISSING),
                after.get(key, MISSING),
                [*parts, str(key)],
                added,
                removed,
                changed,
            )
        return

    if isinstance(before, list) and isinstance(after, list):
        max_len = max(len(before), len(after))
        for index in range(max_len):
            old_item = before[index] if index < len(before) else MISSING
            new_item = after[index] if index < len(after) else MISSING
            _record_diff(old_item, new_item, [*parts, str(index)], added, removed, changed)
        return

    if before != after:
        changed[path] = {"from": before, "to": after}


def _module_map(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    modules = metadata.get("modules", [])
    if not isinstance(modules, list):
        return {}

    mapped: dict[str, dict[str, Any]] = {}
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            continue
        name = module.get("name") or f"module[{index}]"
        mapped[str(name)] = module
    return mapped


def _normalize_status(status: Any) -> str | None:
    if status is None:
        return None
    return str(status).strip().upper()


def _is_regression(old_status: str | None, new_status: str | None) -> bool:
    return old_status in PASS_STATUSES and new_status in REGRESSION_STATUSES


def compare_modules(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_modules = _module_map(before)
    after_modules = _module_map(after)
    status_changes: list[dict[str, Any]] = []
    elapsed_changes: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []

    for name in sorted(set(before_modules) | set(after_modules)):
        old_module = before_modules.get(name, {})
        new_module = after_modules.get(name, {})
        old_status = _normalize_status(old_module.get("status"))
        new_status = _normalize_status(new_module.get("status"))

        if old_status != new_status:
            change = {
                "name": name,
                "from": old_status,
                "to": new_status,
                "regression": _is_regression(old_status, new_status),
            }
            status_changes.append(change)
            if change["regression"]:
                regressions.append(
                    {
                        "type": "module_status",
                        "name": name,
                        "from": old_status,
                        "to": new_status,
                    }
                )

        old_elapsed = old_module.get("elapsed_seconds")
        new_elapsed = new_module.get("elapsed_seconds")
        if old_elapsed != new_elapsed and (old_elapsed is not None or new_elapsed is not None):
            elapsed_changes.append(
                {
                    "name": name,
                    "from": old_elapsed,
                    "to": new_elapsed,
                    "delta_seconds": (
                        round(float(new_elapsed) - float(old_elapsed), 3)
                        if old_elapsed is not None and new_elapsed is not None
                        else None
                    ),
                }
            )

    return {
        "status_changes": status_changes,
        "elapsed_changes": elapsed_changes,
        "regressions": regressions,
    }


def compare_metadata(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    added: dict[str, Any] = {}
    removed: dict[str, Any] = {}
    changed: dict[str, dict[str, Any]] = {}
    _record_diff(before, after, [], added, removed, changed)
    modules = compare_modules(before, after)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "module_status_changes": modules["status_changes"],
        "module_elapsed_changes": modules["elapsed_changes"],
        "regressions": modules["regressions"],
        "has_regressions": bool(modules["regressions"]),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two diagnostic/build-*.json metadata reports"
    )
    parser.add_argument("before", help="Baseline diagnostic metadata JSON")
    parser.add_argument("after", help="New diagnostic metadata JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        before = load_metadata(args.before)
        after = load_metadata(args.after)
    except ValueError as exc:
        print(f"diagnostic_diff: {exc}", file=sys.stderr)
        return 2

    result = compare_metadata(before, after)
    output = json.dumps(
        result,
        indent=2 if args.pretty else None,
        sort_keys=True,
        default=str,
    )
    print(output)
    return 1 if result["has_regressions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
