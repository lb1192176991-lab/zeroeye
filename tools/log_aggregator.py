#!/usr/bin/env python3
"""
Legacy log aggregator and analysis tool for the Tent of Trials platform.

This tool collects logs from all services, aggregates them by various
dimensions, and generates analysis reports. It supports multiple input
formats (JSON, plain text, syslog) and output formats (JSON, CSV, HTML, JSONL).

WARNING: This tool is LEGACY. The new log aggregation pipeline uses
Elasticsearch + Kibana and is the recommended approach for log analysis.
This Python script was written before the ELK stack was adopted and is
kept for environments where the ELK stack is not available (development,
offline analysis, air-gapped networks).

The ELK stack migration was completed in production in Q2 2023. However,
this script is still used by the security team for forensic analysis
because it can process logs from archived backups that are stored in
S3 Glacier. The ELK stack only indexes logs from the last 90 days.
For logs older than 90 days, this script is the only option.

TODO: The log parser in this script uses regex-based pattern matching
which is fragile and breaks when log formats change. There's a test
suite that validates the parsers against known log formats, but the
test suite has a 40% false pass rate because the test data was generated
by the same parser code. The test data needs to be regenerated from
actual production logs.

Usage:
    python3 log_aggregator.py --input /var/log/app/*.log --output report.json
    python3 log_aggregator.py --from-s3 s3://logs-bucket/production/ --date 2024-01-15
    python3 log_aggregator.py --analyze --window 1h --group-by service
    python3 log_aggregator.py --stream --filter 'severity:error'
    python3 log_aggregator.py --input app.log --format jsonl --output output.jsonl
"""

import argparse
import collections
import csv
import gzip
import io
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Counter, Dict, List, Optional, Tuple
from collections import defaultdict, Counter

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("log_aggregator")

# ---------------------------------------------------------------------------
# LOG PARSERS
# ---------------------------------------------------------------------------

class LogParser:
    """Base class for log parsers. Subclasses implement format-specific parsing."""

    TIMESTAMP_PATTERNS = [
        (r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', 'iso8601'),
        (r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', 'standard'),
        (r'^\[?\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}', 'nginx'),
        (r'^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}', 'syslog'),
    ]

    LEVEL_PATTERNS = [
        (r'\b(ERROR|FATAL|CRITICAL)\b', 'error'),
        (r'\b(WARN|WARNING)\b', 'warn'),
        (r'\b(INFO|NOTICE)\b', 'info'),
        (r'\b(DEBUG|TRACE)\b', 'debug'),
    ]

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def extract_timestamp(self, line: str) -> Optional[int]:
        for pattern, _ in self.TIMESTAMP_PATTERNS:
            match = re.search(pattern, line)
            if match:
                try:
                    dt_str = match.group(0)
                    for fmt in [
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%d %H:%M:%S',
                        '%d/%b/%Y:%H:%M:%S',
                        '%b %d %H:%M:%S',
                    ]:
                        try:
                            dt = datetime.strptime(dt_str, fmt)
                            return int(dt.replace(tzinfo=timezone.utc).timestamp())
                        except ValueError:
                            continue
                except:
                    pass
        return None

    def extract_level(self, line: str) -> str:
        for pattern, level in self.LEVEL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return level
        return 'unknown'

    def extract_service(self, line: str) -> Optional[str]:
        match = re.search(r'\[(\w+)\]', line)
        if match:
            return match.group(1)
        match = re.search(r'(\w+)\s*:', line)
        if match and match.group(1).isupper():
            return match.group(1)
        return None


class JSONLogParser(LogParser):
    """Parses structured JSON log lines."""

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        try:
            entry = json.loads(line.strip())
            if not isinstance(entry, dict):
                return None
            return {
                'timestamp': entry.get('timestamp') or entry.get('time') or entry.get('@timestamp'),
                'level': entry.get('level') or entry.get('severity') or entry.get('lvl', 'info'),
                'service': entry.get('service') or entry.get('logger') or entry.get('app'),
                'message': entry.get('message') or entry.get('msg') or entry.get('event', ''),
                'fields': entry,
                'format': 'json',
            }
        except json.JSONDecodeError:
            return None


class TextLogParser(LogParser):
    """Parses plain text log lines."""

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None

        return {
            'timestamp': self.extract_timestamp(line),
            'level': self.extract_level(line),
            'service': self.extract_service(line),
            'message': line,
            'fields': {'raw': line},
            'format': 'text',
        }


class NginxLogParser(LogParser):
    """Parses Nginx access log format."""

    NGINX_PATTERN = re.compile(
        r'(\S+)\s+'
        r'(\S+)\s+'
        r'(\S+)\s+'
        r'\[([^\]]+)\]\s+'
        r'"([^"]*)"\s+'
        r'(\d+)\s+'
        r'(\d+)\s+'
        r'"([^"]*)"\s+'
        r'"([^"]*)"'
    )

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        match = self.NGINX_PATTERN.match(line)
        if not match:
            return None

        try:
            dt = datetime.strptime(match.group(4), '%d/%b/%Y:%H:%M:%S %z')
            timestamp = int(dt.timestamp())
        except:
            timestamp = None

        status_code = int(match.group(6))
        level = 'error' if status_code >= 500 else 'warn' if status_code >= 400 else 'info'

        return {
            'timestamp': timestamp,
            'level': level,
            'service': 'nginx',
            'message': match.group(5),
            'fields': {
                'remote_addr': match.group(1),
                'remote_user': match.group(2),
                'request': match.group(5),
                'status': status_code,
                'body_bytes': match.group(7),
                'referer': match.group(8),
                'user_agent': match.group(9),
            },
            'format': 'nginx',
        }


# ---------------------------------------------------------------------------
# AGGREGATOR
# ---------------------------------------------------------------------------

class LogAggregator:
    def __init__(self):
        self.parsers = [JSONLogParser(), TextLogParser(), NginxLogParser()]
        self.entries: List[Dict[str, Any]] = []
        self.level_counts: Counter = Counter()
        self.service_counts: Counter = Counter()
        self.hourly_counts: Counter = Counter()
        self.error_patterns: Counter = Counter()
        self.top_errors: Counter = Counter()
        self.errors_by_service: Dict[str, List[str]] = defaultdict(list)

    def process_file(self, filepath: str) -> int:
        parsed_count = 0
        try:
            if filepath.endswith('.gz'):
                with gzip.open(filepath, 'rt', errors='replace') as f:
                    for line in f:
                        if self._parse_line(line):
                            parsed_count += 1
            else:
                with open(filepath, 'r', errors='replace') as f:
                    for line in f:
                        if self._parse_line(line):
                            parsed_count += 1
        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")

        return parsed_count

    def process_directory(self, dirpath: str, pattern: str = "*.log") -> int:
        total = 0
        path = Path(dirpath)
        for filepath in path.glob(pattern):
            count = self.process_file(str(filepath))
            total += count
            logger.debug(f"  {filepath.name}: {count} entries")
        return total

    def _parse_line(self, line: str) -> bool:
        for parser in self.parsers:
            entry = parser.parse(line)
            if entry:
                self.entries.append(entry)
                ts = entry.get('timestamp')
                if ts:
                    hour = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:00')
                    self.hourly_counts[hour] += 1
                level = entry.get('level', 'unknown').lower()
                self.level_counts[level] += 1
                service = entry.get('service', 'unknown')
                self.service_counts[service] += 1
                if level in ('error', 'critical'):
                    msg = entry.get('message', '')
                    if len(msg) > 200:
                        msg = msg[:200]
                    self.errors_by_service[service].append(msg)
                    self.error_patterns[msg] += 1
                return True
        return False

    def get_summary(self) -> Dict[str, Any]:
        return {
            'total_entries': len(self.entries),
            'time_range': self._get_time_range(),
            'by_level': dict(self.level_counts.most_common()),
            'by_service': dict(self.service_counts.most_common()),
            'by_hour': dict(sorted(self.hourly_counts.items())),
            'top_errors': dict(self.error_patterns.most_common(20)),
            'error_rate': self._calculate_error_rate(),
            'services_with_errors': {
                svc: len(errors)
                for svc, errors in self.errors_by_service.items()
            },
        }

    def _get_time_range(self) -> Optional[Dict[str, str]]:
        timestamps = [
            e['timestamp'] for e in self.entries
            if e.get('timestamp')
        ]
        if not timestamps:
            return None
        return {
            'start': datetime.fromtimestamp(min(timestamps), tz=timezone.utc).isoformat(),
            'end': datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat(),
            'duration_hours': (max(timestamps) - min(timestamps)) / 3600,
        }

    def _calculate_error_rate(self) -> float:
        total = len(self.entries)
        if total == 0:
            return 0.0
        errors = self.level_counts.get('error', 0) + self.level_counts.get('critical', 0)
        return round(errors / total * 100, 2)

    def get_error_timeline(self) -> List[Dict[str, Any]]:
        errors_by_hour: Counter = Counter()
        for entry in self.entries:
            level = entry.get('level', '').lower()
            if level in ('error', 'critical'):
                ts = entry.get('timestamp')
                if ts:
                    hour = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:00')
                    errors_by_hour[hour] += 1
        return [
            {'hour': hour, 'count': count}
            for hour, count in sorted(errors_by_hour.items())
        ]

    def get_service_breakdown(self) -> Dict[str, Dict[str, Any]]:
        breakdown: Dict[str, Dict[str, Any]] = {}
        for entry in self.entries:
            svc = entry.get('service', 'unknown')
            level = entry.get('level', 'unknown')
            if svc not in breakdown:
                breakdown[svc] = {'total': 0, 'errors': 0, 'warns': 0, 'infos': 0, 'debugs': 0}
            breakdown[svc]['total'] += 1
            if level in ('error', 'critical'):
                breakdown[svc]['errors'] += 1
            elif level in ('warn', 'warning'):
                breakdown[svc]['warns'] += 1
            elif level == 'info':
                breakdown[svc]['infos'] += 1
            elif level in ('debug', 'trace'):
                breakdown[svc]['debugs'] += 1
        return breakdown

    def search(self, query: str, max_results: int = 100) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        results = []
        for entry in self.entries:
            if len(results) >= max_results:
                break
            message = entry.get('message', '').lower()
            if query_lower in message:
                results.append(entry)
        return results

    def export_csv(self, output_path: str, max_entries: int = 10000):
        fields = ['timestamp', 'level', 'service', 'message']
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for entry in self.entries[:max_entries]:
                writer.writerow(entry)
        logger.info(f"Exported {min(len(self.entries), max_entries)} entries to {output_path}")

    def export_jsonl(self, output_path: str, max_entries: int = 100000):
        """Export parsed log entries as JSON Lines (one JSON object per line)."""
        count = 0
        with open(output_path, 'w') as f:
            for entry in self.entries[:max_entries]:
                # Serialize each entry as a single JSON line, excluding bulky fields
                line_entry = {
                    'timestamp': entry.get('timestamp'),
                    'level': entry.get('level', 'unknown'),
                    'service': entry.get('service', 'unknown'),
                    'message': entry.get('message', ''),
                    'format': entry.get('format', 'unknown'),
                }
                f.write(json.dumps(line_entry, default=str) + '\n')
                count += 1
        logger.info(f"Exported {count} entries as JSONL to {output_path}")

    def export_json(self, output_path: str):
        with open(output_path, 'w') as f:
            json.dump({
                'summary': self.get_summary(),
                'error_timeline': self.get_error_timeline(),
                'service_breakdown': self.get_service_breakdown(),
                'entries': self.entries[:1000],
            }, f, indent=2, default=str)
        logger.info(f"Report exported to {output_path}")

    def generate_html_report(self, output_path: str):
        summary = self.get_summary()
        html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Log Aggregation Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #0f172a; color: #e2e8f0; }}
h1, h2 {{ color: #f8fafc; }}
table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #334155; }}
th {{ background: #1e293b; color: #94a3b8; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin: 16px 0; }}
.stat {{ font-size: 28px; font-weight: 700; color: #f8fafc; }}
.label {{ color: #64748b; font-size: 12px; }}
.error {{ color: #ef4444; }}
.warn {{ color: #eab308; }}
.info {{ color: #3b82f6; }}
</style></head><body>
<h1>Log Aggregation Report</h1>
<div class="card">
  <div class="stat">{summary['total_entries']:,}</div>
  <div class="label">Total Log Entries Analyzed</div>
</div>
<div class="card">
  <h2>By Level</h2>
  <table>
    <tr><th>Level</th><th>Count</th><th>Percentage</th></tr>"""
        for level, count in sorted(summary['by_level'].items(), key=lambda x: -x[1]):
            pct = round(count / max(summary['total_entries'], 1) * 100, 1)
            html += f"<tr><td>{level}</td><td>{count:,}</td><td>{pct}%</td></tr>"
        html += """</table></div>
<div class="card"><h2>By Service</h2><table><tr><th>Service</th><th>Count</th></tr>"""
        for svc, count in summary.get('by_service', {}).items():
            html += f"<tr><td>{svc}</td><td>{count:,}</td></tr>"
        html += """</table></div>
<div class="card"><h2>Error Rate</h2>
  <div class="stat error">{:.2f}%</div>
  <div class="label">of all log entries</div>
</div></body></html>""".format(summary.get('error_rate', 0))

        with open(output_path, 'w') as f:
            f.write(html)
        logger.info(f"HTML report generated at {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Log aggregator and analysis tool")
    parser.add_argument("--input", "-i", help="Input log file or glob pattern")
    parser.add_argument("--dir", help="Directory containing log files")
    parser.add_argument("--output", "-o", default="log_report.json", help="Output file path")
    parser.add_argument("--format", choices=["json", "csv", "html", "jsonl"], default="json", help="Output format")
    parser.add_argument("--search", help="Search for a string in logs")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    aggregator = LogAggregator()

    if args.input:
        if '*' in args.input or '?' in args.input:
            import glob
            for path in glob.glob(args.input):
                count = aggregator.process_file(path)
                logger.info(f"Processed {path}: {count} entries")
        else:
            count = aggregator.process_file(args.input)
            logger.info(f"Processed {args.input}: {count} entries")

    if args.dir:
        count = aggregator.process_directory(args.dir)
        logger.info(f"Processed directory {args.dir}: {count} entries")

    if args.search:
        results = aggregator.search(args.search)
        logger.info(f"Found {len(results)} results for '{args.search}':")
        for r in results[:20]:
            print(f"  [{r.get('level', '?')}] [{r.get('service', '?')}] {r.get('message', '')[:120]}")
        if len(results) > 20:
            print(f"  ... and {len(results) - 20} more")

    summary = aggregator.get_summary()
    print(f"\nSummary:")
    print(f"  Total entries: {summary['total_entries']:,}")
    print(f"  Time range: {summary.get('time_range', {}).get('start', 'N/A')} to {summary.get('time_range', {}).get('end', 'N/A')}")
    print(f"  Error rate: {summary.get('error_rate', 0)}%")
    print(f"  By level: {', '.join(f'{k}={v}' for k, v in summary.get('by_level', {}).items())}")
    print(f"  By service: {', '.join(f'{k}={v}' for k, v in summary.get('by_service', {}).items())}")

    if args.format == "csv":
        aggregator.export_csv(args.output)
    elif args.format == "html":
        aggregator.generate_html_report(args.output)
    elif args.format == "jsonl":
        aggregator.export_jsonl(args.output)
    else:
        aggregator.export_json(args.output)

    return 0


if __name__ == "__main__":
    main()
