#!/usr/bin/env python3
"""Diagnostic metadata diff tool (Kickama #307).

Compares two build diagnostic JSON reports (diagnostic/build-*.json)
and generates text, JSON, or Markdown diffs detailing module status
transitions, elapsed time deltas, regressions, and artifact changes.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


def load_report(path: Path | str) -> dict[str, Any]:
    """Load and validate a diagnostic metadata report JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Diagnostic report not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Report at {p} must be a JSON object")
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in report {p}: {e}") from e


def diff_reports(
    before: dict[str, Any],
    after: dict[str, Any],
    elapsed_threshold: Optional[float] = None,
) -> dict[str, Any]:
    """Compare two diagnostic reports and compute structured differences."""
    commit_before = before.get("commit", "unknown")
    commit_after = after.get("commit", "unknown")

    modules_before = {m["name"]: m for m in before.get("modules", []) if isinstance(m, dict) and "name" in m}
    modules_after = {m["name"]: m for m in after.get("modules", []) if isinstance(m, dict) and "name" in m}

    all_module_names = sorted(set(modules_before.keys()) | set(modules_after.keys()))

    module_diffs = []
    regressions = []
    fixes = []
    slowdowns = []

    for name in all_module_names:
        m_before = modules_before.get(name)
        m_after = modules_after.get(name)

        status_before = m_before.get("status") if m_before else None
        status_after = m_after.get("status") if m_after else None

        elapsed_before = float(m_before.get("elapsed_seconds", 0.0)) if m_before else None
        elapsed_after = float(m_after.get("elapsed_seconds", 0.0)) if m_after else None

        artifact_before = m_before.get("artifact") if m_before else None
        artifact_after = m_after.get("artifact") if m_after else None

        if m_before and not m_after:
            change = "REMOVED"
        elif not m_before and m_after:
            change = "ADDED"
        elif status_before == "PASS" and status_after == "FAIL":
            change = "REGRESSION"
            regressions.append(name)
        elif status_before == "FAIL" and status_after == "PASS":
            change = "FIXED"
            fixes.append(name)
        else:
            change = "UNCHANGED"

        elapsed_delta = None
        elapsed_alert = False
        if elapsed_before is not None and elapsed_after is not None:
            elapsed_delta = round(elapsed_after - elapsed_before, 3)
            if elapsed_threshold is not None and elapsed_delta > elapsed_threshold:
                elapsed_alert = True
                slowdowns.append(name)

        module_diffs.append(
            {
                "name": name,
                "status_before": status_before,
                "status_after": status_after,
                "status_change": change,
                "elapsed_before": elapsed_before,
                "elapsed_after": elapsed_after,
                "elapsed_delta": elapsed_delta,
                "elapsed_alert": elapsed_alert,
                "artifact_before": artifact_before,
                "artifact_after": artifact_after,
            }
        )

    total_passed_before = before.get("passed", sum(1 for m in modules_before.values() if m.get("status") == "PASS"))
    total_passed_after = after.get("passed", sum(1 for m in modules_after.values() if m.get("status") == "PASS"))
    total_failed_before = before.get("failed", sum(1 for m in modules_before.values() if m.get("status") == "FAIL"))
    total_failed_after = after.get("failed", sum(1 for m in modules_after.values() if m.get("status") == "FAIL"))

    return {
        "commit_before": commit_before,
        "commit_after": commit_after,
        "total_modules_before": len(modules_before),
        "total_modules_after": len(modules_after),
        "passed_before": total_passed_before,
        "passed_after": total_passed_after,
        "passed_delta": total_passed_after - total_passed_before,
        "failed_before": total_failed_before,
        "failed_after": total_failed_after,
        "failed_delta": total_failed_after - total_failed_before,
        "regressions": regressions,
        "fixes": fixes,
        "slowdowns": slowdowns,
        "has_regressions": len(regressions) > 0,
        "module_diffs": module_diffs,
    }


def format_text(diff: dict[str, Any], only_regressions: bool = False) -> str:
    """Format the diff as readable terminal text."""
    lines = [
        f"Diagnostic Diff: {diff['commit_before']} -> {diff['commit_after']}",
        "=" * 60,
        f"Passed: {diff['passed_before']} -> {diff['passed_after']} ({'+' if diff['passed_delta'] >= 0 else ''}{diff['passed_delta']})",
        f"Failed: {diff['failed_before']} -> {diff['failed_after']} ({'+' if diff['failed_delta'] >= 0 else ''}{diff['failed_delta']})",
        "",
        "Module Details:",
        "-" * 60,
    ]

    modules = diff["module_diffs"]
    if only_regressions:
        modules = [m for m in modules if m["status_change"] == "REGRESSION"]
        if not modules:
            lines.append("No regressions detected.")
            return "\n".join(lines)

    for m in modules:
        change = m["status_change"]
        st_before = m["status_before"] or "N/A"
        st_after = m["status_after"] or "N/A"
        time_str = ""
        if m["elapsed_delta"] is not None:
            time_str = f" | {m['elapsed_before']}s -> {m['elapsed_after']}s ({'+' if m['elapsed_delta'] >= 0 else ''}{m['elapsed_delta']}s)"
            if m["elapsed_alert"]:
                time_str += " [SLOWDOWN ALERT]"

        tag = f"[{change}]"
        lines.append(f"  {m['name']:<18} {st_before:>4} -> {st_after:<4} {tag:<12}{time_str}")

    if diff["regressions"]:
        lines.extend(["", f"⚠ WARNING: {len(diff['regressions'])} regression(s) found: {', '.join(diff['regressions'])}"])
    else:
        lines.extend(["", "✓ No regressions detected."])

    return "\n".join(lines)


def format_markdown(diff: dict[str, Any], only_regressions: bool = False) -> str:
    """Format the diff as a GitHub Flavored Markdown summary table."""
    lines = [
        f"## 📊 Diagnostic Diff: `{diff['commit_before']}` ➔ `{diff['commit_after']}`",
        "",
        "| Metric | Baseline | Target | Delta |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Passed Modules** | {diff['passed_before']} | {diff['passed_after']} | {'+' if diff['passed_delta'] >= 0 else ''}{diff['passed_delta']} |",
        f"| **Failed Modules** | {diff['failed_before']} | {diff['failed_after']} | {'+' if diff['failed_delta'] >= 0 else ''}{diff['failed_delta']} |",
        "",
        "### Module Status & Timing Breakdown",
        "",
        "| Module | Status Transition | Elapsed Time | Note |",
        "| :--- | :---: | :---: | :--- |",
    ]

    modules = diff["module_diffs"]
    if only_regressions:
        modules = [m for m in modules if m["status_change"] == "REGRESSION"]
        if not modules:
            lines.append("| *All* | ✅ No regressions | — | Clean |")
            return "\n".join(lines)

    status_icons = {
        "PASS": "🟢 PASS",
        "FAIL": "🔴 FAIL",
        None: "⚪ N/A",
    }

    for m in modules:
        icon_b = status_icons.get(m["status_before"], m["status_before"])
        icon_a = status_icons.get(m["status_after"], m["status_after"])
        trans = f"{icon_b} ➔ {icon_a}"

        time_str = "—"
        if m["elapsed_delta"] is not None:
            time_str = f"{m['elapsed_after']}s (`{'+' if m['elapsed_delta'] >= 0 else ''}{m['elapsed_delta']}s`)"

        note = m["status_change"]
        if m["status_change"] == "REGRESSION":
            note = "⚠️ **REGRESSION**"
        elif m["status_change"] == "FIXED":
            note = "🎉 **FIXED**"
        elif m["elapsed_alert"]:
            note = "⏳ **Slowdown**"

        lines.append(f"| **`{m['name']}`** | {trans} | {time_str} | {note} |")

    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostic metadata diff tool (Kickama #307)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("before", help="Path to baseline build-*.json report")
    parser.add_argument("after", help="Path to candidate build-*.json report")
    parser.add_argument(
        "-f", "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--only-regressions",
        action="store_true",
        help="Only display regressions/failures in output",
    )
    parser.add_argument(
        "--elapsed-threshold",
        type=float,
        default=None,
        help="Flag elapsed time slowdowns exceeding this threshold in seconds",
    )
    parser.add_argument(
        "--no-fail-on-regression",
        action="store_true",
        help="Exit with 0 even if regressions are present",
    )

    args = parser.parse_args(argv)

    try:
        before = load_report(args.before)
        after = load_report(args.after)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 2

    diff = diff_reports(before, after, elapsed_threshold=args.elapsed_threshold)

    if args.format == "json":
        if args.only_regressions:
            diff_to_print = dict(diff)
            diff_to_print["module_diffs"] = [
                m for m in diff["module_diffs"] if m["status_change"] == "REGRESSION"
            ]
            print(json.dumps(diff_to_print, indent=2))
        else:
            print(json.dumps(diff, indent=2))
    elif args.format == "markdown":
        print(format_markdown(diff, only_regressions=args.only_regressions))
    else:
        print(format_text(diff, only_regressions=args.only_regressions))

    if diff["has_regressions"] and not args.no_fail_on_regression:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
