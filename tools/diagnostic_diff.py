#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def load_report(path):
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    if not isinstance(report, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return report


def module_map(report):
    return {
        item["name"]: item
        for item in report.get("modules", [])
        if isinstance(item, dict) and "name" in item
    }


def compare(before, after, threshold=None):
    old_modules = module_map(before)
    new_modules = module_map(after)
    modules = []
    regressions = []
    slowdowns = []

    for name in sorted(old_modules.keys() | new_modules.keys()):
        old = old_modules.get(name)
        new = new_modules.get(name)
        old_status = old.get("status") if old else None
        new_status = new.get("status") if new else None
        old_time = old.get("elapsed_seconds") if old else None
        new_time = new.get("elapsed_seconds") if new else None
        delta = None
        if isinstance(old_time, (int, float)) and isinstance(new_time, (int, float)):
            delta = round(new_time - old_time, 3)

        regression = old_status == "PASS" and new_status == "FAIL"
        slow = threshold is not None and delta is not None and delta > threshold
        if regression:
            regressions.append(name)
        if slow:
            slowdowns.append(name)

        modules.append({
            "name": name,
            "before": old_status,
            "after": new_status,
            "elapsed_delta": delta,
            "artifact_changed": bool(old and new and old.get("artifact") != new.get("artifact")),
            "regression": regression,
            "slowdown": slow,
        })

    return {
        "commit_before": before.get("commit"),
        "commit_after": after.get("commit"),
        "regressions": regressions,
        "slowdowns": slowdowns,
        "modules": modules,
    }


def markdown(diff):
    lines = [
        "# Diagnostic diff",
        "",
        f"`{diff['commit_before'] or 'unknown'}` → `{diff['commit_after'] or 'unknown'}`",
        "",
        "| Module | Status | Time change | Notes |",
        "| --- | --- | ---: | --- |",
    ]
    for item in diff["modules"]:
        status = f"{item['before'] or 'missing'} → {item['after'] or 'missing'}"
        elapsed = "-" if item["elapsed_delta"] is None else f"{item['elapsed_delta']:+.3f}s"
        notes = []
        if item["regression"]:
            notes.append("regression")
        if item["slowdown"]:
            notes.append("slowdown")
        if item["artifact_changed"]:
            notes.append("artifact changed")
        lines.append(f"| {item['name']} | {status} | {elapsed} | {', '.join(notes) or '-'} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare two build diagnostic reports")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--elapsed-threshold", type=float)
    args = parser.parse_args(argv)

    try:
        diff = compare(load_report(args.before), load_report(args.after), args.elapsed_threshold)
    except ValueError as error:
        parser.error(str(error))

    if args.format == "json":
        print(json.dumps(diff, indent=2))
    else:
        print(markdown(diff), end="")
    return 1 if diff["regressions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
