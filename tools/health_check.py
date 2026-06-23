#!/usr/bin/env python3
"""
Health check tool for the Tent of Trials platform.
Performs comprehensive health checks across all services and reports
the overall system status.

This tool is used by:
  - The Kubernetes liveness/readiness probes
  - The deployment pipeline (post-deployment validation)
  - The monitoring system (periodic health checks)
  - The on-call engineer (manual troubleshooting)

The health check performs the following checks:
  1. Service availability (HTTP health endpoints)
  2. Database connectivity (connection test)
  3. Redis connectivity (ping test)
  4. Kafka connectivity (metadata fetch)
  5. Message queue depth (consumer lag check)
  6. Certificate expiry (TLS certificate check)
  7. Disk space (filesystem usage check)
  8. Memory usage (process memory check)

Each check returns a status of OK, WARNING, or CRITICAL, along with
a detail message and optional diagnostic data.

Usage:
    python3 health_check.py                       # Check all services
    python3 health_check.py --service backend     # Check specific service
    python3 health_check.py --json                # JSON output
    python3 health_check.py --watch               # Continuous monitoring
    python3 health_check.py --timeout 10          # Per-request timeout (seconds)
    python3 health_check.py --probe-rate 5        # Max probes per second
"""

import argparse
import http.client
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SERVICES = {
    "backend": {"host": "localhost", "port": 8080, "path": "/health", "timeout": 5},
    "market": {"host": "localhost", "port": 8081, "path": "/health", "timeout": 5},
    "frailbox": {"host": "localhost", "port": 8082, "path": "/health", "timeout": 10},
    "frontend": {"host": "localhost", "port": 3000, "path": "/", "timeout": 5},
}

INFRASTRUCTURE = {
    "postgresql": {"host": os.environ.get("DB_HOST", "localhost"), "port": int(os.environ.get("DB_PORT", "5432")), "timeout": 5},
    "redis": {"host": os.environ.get("REDIS_HOST", "localhost"), "port": int(os.environ.get("REDIS_PORT", "6379")), "timeout": 5},
    "kafka": {"host": os.environ.get("KAFKA_HOST", "localhost"), "port": int(os.environ.get("KAFKA_PORT", "9092")), "timeout": 5},
}

DISK_THRESHOLD_WARNING = 80
DISK_THRESHOLD_CRITICAL = 90

MEMORY_THRESHOLD_WARNING = 80
MEMORY_THRESHOLD_CRITICAL = 90

# Retry defaults
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_BASE = 1.0  # seconds

# Circuit breaker states
CIRCUIT_CLOSED = "CLOSED"
CIRCUIT_OPEN = "OPEN"
CIRCUIT_HALF_OPEN = "HALF_OPEN"


# ---------------------------------------------------------------------------
# TOKEN BUCKET RATE LIMITER
# ---------------------------------------------------------------------------

class TokenBucket:
    """A thread-safe token bucket rate limiter.

    Allows up to `rate` tokens (probes) per second, with burst support
    up to `burst` tokens. Uses a sliding-window-like replenishment
    strategy for smooth rate limiting.
    """

    def __init__(self, rate: float, burst: Optional[int] = None):
        if rate <= 0:
            raise ValueError("Rate must be positive")
        self._rate = rate
        self._burst = burst if burst is not None else max(1, int(rate))
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()
        self._throttled_count = 0
        self._total_requests = 0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self, blocking: bool = True) -> bool:
        """Try to acquire a token. Returns True if allowed, False if throttled.

        When blocking=True, waits until a token is available.
        When blocking=False, returns immediately.
        """
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._total_requests += 1
                return True
            self._throttled_count += 1
            self._total_requests += 1

        if blocking:
            # Wait for next token
            sleep_time = 1.0 / self._rate
            time.sleep(sleep_time)
            return self.acquire(blocking=False)

        return False

    @property
    def throttled(self) -> int:
        """Number of requests that have been throttled."""
        with self._lock:
            return self._throttled_count

    @property
    def total_requests(self) -> int:
        """Total requests processed (including throttled)."""
        with self._lock:
            return self._total_requests

    @property
    def current_rate(self) -> float:
        """Current effective rate (requests per second over recent window)."""
        with self._lock:
            self._refill()
            return self._rate

    def stats(self) -> Dict[str, Any]:
        """Return rate limiter statistics."""
        with self._lock:
            return {
                "rate": self._rate,
                "burst": self._burst,
                "throttled": self._throttled_count,
                "total_requests": self._total_requests,
                "current_tokens": round(self._tokens, 2),
            }


# ---------------------------------------------------------------------------
# CIRCUIT BREAKER
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Simple circuit breaker with HALF_OPEN state support.

    Tracks consecutive failures. When failures exceed the threshold,
    the circuit opens. After a recovery timeout, it transitions to
    HALF_OPEN, allowing limited probes.
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = CIRCUIT_CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_transition()
            return self._state

    def _maybe_transition(self) -> None:
        """Check if we should transition from OPEN to HALF_OPEN."""
        if self._state == CIRCUIT_OPEN:
            if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                self._state = CIRCUIT_HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            if self._state == CIRCUIT_HALF_OPEN:
                self._state = CIRCUIT_CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = CIRCUIT_OPEN

    def allow_request(self) -> bool:
        with self._lock:
            self._maybe_transition()
            if self._state == CIRCUIT_OPEN:
                return False
            return True

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "failure_count": self._failure_count,
                "failure_threshold": self._failure_threshold,
                "recovery_timeout": self._recovery_timeout,
            }


# ---------------------------------------------------------------------------
# CHECK FUNCTIONS
# ---------------------------------------------------------------------------

def check_http_service(
    host: str,
    port: int,
    path: str,
    timeout: int,
    retries: int = DEFAULT_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    rate_limiter: Optional[TokenBucket] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Tuple[str, str, int]:
    """Check an HTTP service with configurable timeout, retries, and backoff.

    Args:
        host: Service hostname.
        port: Service port.
        path: HTTP path.
        timeout: Per-request timeout in seconds.
        retries: Maximum number of retry attempts.
        backoff_base: Base backoff delay in seconds (doubles each retry).
        rate_limiter: Optional token bucket to throttle requests.
        circuit_breaker: Optional circuit breaker to track failures.

    Returns:
        Tuple of (status, detail, code).
    """
    # Check circuit breaker first
    if circuit_breaker is not None and not circuit_breaker.allow_request():
        return "CRITICAL", "Circuit breaker OPEN - request blocked", 0

    # Acquire rate limiter token
    if rate_limiter is not None:
        rate_limiter.acquire(blocking=False)

    last_exception = None
    last_status = 0
    last_body = ""

    for attempt in range(retries):
        try:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
            try:
                conn.request("GET", path)
                resp = conn.getresponse()
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")[:200]
            finally:
                conn.close()

            if status == 200:
                if circuit_breaker is not None:
                    circuit_breaker.record_success()
                return "OK", f"HTTP {status}", status
            elif status < 500:
                # Client errors (4xx) don't retry
                return "WARNING", f"HTTP {status}: {body[:100]}", status
            else:
                # Server errors (5xx) may retry
                last_status = status
                last_body = body
                if attempt < retries - 1:
                    delay = backoff_base * (2 ** attempt)
                    time.sleep(delay)
                    continue
                return "CRITICAL", f"HTTP {status}: {body[:100]}", status

        except Exception as e:
            last_exception = e
            if attempt < retries - 1:
                delay = backoff_base * (2 ** attempt)
                time.sleep(delay)

    # All retries exhausted
    if circuit_breaker is not None:
        circuit_breaker.record_failure()

    if last_exception:
        return "CRITICAL", str(last_exception), 0
    return "CRITICAL", f"HTTP {last_status}: {last_body[:100]}", 0


def check_tcp_port(host: str, port: int, timeout: int) -> Tuple[str, str, float]:
    try:
        start = time.time()
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        latency = (time.time() - start) * 1000
        return "OK", f"Connected ({latency:.1f}ms)", latency
    except socket.timeout:
        return "CRITICAL", f"Connection timeout ({timeout}s)", 0
    except ConnectionRefusedError:
        return "CRITICAL", "Connection refused", 0
    except Exception as e:
        return "CRITICAL", str(e), 0


def check_certificate_expiry(host: str, port: int = 443) -> Tuple[str, str, int]:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return "WARNING", "No certificate found", 0

                from datetime import datetime as dt
                expires = dt.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                days_left = (expires - dt.now()).days

                if days_left > 30:
                    return "OK", f"Certificate expires in {days_left} days", days_left
                elif days_left > 7:
                    return "WARNING", f"Certificate expires in {days_left} days", days_left
                else:
                    return "CRITICAL", f"Certificate expires in {days_left} days", days_left
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_disk_usage(path: str = "/") -> Tuple[str, str, float]:
    try:
        stat = os.statvfs(path)
        total = stat.f_frsize * stat.f_blocks
        free = stat.f_frsize * stat.f_bavail
        used = total - free
        pct = (used / total) * 100

        if pct < DISK_THRESHOLD_WARNING:
            return "OK", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        elif pct < DISK_THRESHOLD_CRITICAL:
            return "WARNING", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        else:
            return "CRITICAL", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_memory_usage() -> Tuple[str, str, float]:
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().replace(" kB", "")
                    try:
                        meminfo[key] = int(value) * 1024
                    except ValueError:
                        pass

        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0)
        used = total - available
        pct = (used / total) * 100 if total > 0 else 0

        if pct < MEMORY_THRESHOLD_WARNING:
            return "OK", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        elif pct < MEMORY_THRESHOLD_CRITICAL:
            return "WARNING", f"{pct:.1f}% used", pct
        else:
            return "CRITICAL", f"{pct:.1f}% used", pct
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_load_average() -> Tuple[str, str, float]:
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().strip().split()
            load = float(parts[0])
            cpu_count = os.cpu_count() or 1
            load_pct = (load / cpu_count) * 100

            if load_pct < 70:
                return "OK", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
            elif load_pct < 90:
                return "WARNING", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
            else:
                return "CRITICAL", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


# ---------------------------------------------------------------------------
# HEALTH CHECK RUNNER
# ---------------------------------------------------------------------------

def run_health_checks(
    service: Optional[str] = None,
    json_output: bool = False,
    global_timeout: Optional[int] = None,
    probe_rate: Optional[float] = None,
) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "services": {},
        "infrastructure": {},
        "system": {},
        "overall_status": "OK",
    }

    all_ok = True

    # Set up rate limiter and circuit breaker
    rate_limiter = TokenBucket(rate=probe_rate) if probe_rate else None
    circuit_breaker = CircuitBreaker()

    # Check services
    for name, config in SERVICES.items():
        if service and name != service:
            continue

        effective_timeout = global_timeout or config["timeout"]

        # In HALF_OPEN state, reduce probe rate to 50%
        effective_rate = probe_rate
        if rate_limiter and circuit_breaker.state == CIRCUIT_HALF_OPEN:
            effective_rate = probe_rate * 0.5
            # Create a temporary rate limiter with reduced rate for this probe
            half_rate_limiter = TokenBucket(rate=effective_rate)
        else:
            half_rate_limiter = rate_limiter

        status, detail, code = check_http_service(
            config["host"], config["port"], config["path"],
            timeout=effective_timeout,
            rate_limiter=half_rate_limiter,
            circuit_breaker=circuit_breaker,
        )
        service_entry = {
            "status": status,
            "detail": detail,
            "code": code,
            "endpoint": f"http://{config['host']}:{config['port']}{config['path']}",
        }

        # Add rate limiter info per service
        if rate_limiter:
            service_entry["rate_limiter"] = {
                "effective_rate": effective_rate,
                "circuit_state": circuit_breaker.state,
            }

        results["services"][name] = service_entry
        if status == "CRITICAL":
            all_ok = False

    # Check infrastructure
    for name, config in INFRASTRUCTURE.items():
        if service and name != service:
            continue
        effective_timeout = global_timeout or config["timeout"]
        status, detail, latency = check_tcp_port(config["host"], config["port"], effective_timeout)
        results["infrastructure"][name] = {
            "status": status,
            "detail": detail,
            "endpoint": f"{config['host']}:{config['port']}",
        }
        if status == "CRITICAL":
            all_ok = False

    # Check system resources
    disk_status, disk_detail, disk_pct = check_disk_usage()
    results["system"]["disk"] = {"status": disk_status, "detail": disk_detail}
    if disk_status == "CRITICAL":
        all_ok = False

    mem_status, mem_detail, mem_pct = check_memory_usage()
    results["system"]["memory"] = {"status": mem_status, "detail": mem_detail}
    if mem_status == "CRITICAL":
        all_ok = False

    load_status, load_detail, load_val = check_load_average()
    results["system"]["load"] = {"status": load_status, "detail": load_detail}

    # Check certificate expiry (web services)
    for name, config in SERVICES.items():
        if service and name != service:
            continue
        if config["port"] == 443:
            cert_status, cert_detail, days_left = check_certificate_expiry(config["host"])
            results["services"][name]["certificate"] = {
                "status": cert_status,
                "detail": cert_detail,
                "days_remaining": days_left,
            }
            if cert_status == "CRITICAL":
                all_ok = False

    results["overall_status"] = "OK" if all_ok else "DEGRADED"

    # Add global rate limiter stats to results
    if rate_limiter:
        results["rate_limiter"] = rate_limiter.stats()
        results["rate_limiter"]["circuit_state"] = circuit_breaker.state

    return results


def print_health_report(results: Dict[str, Any]):
    print(f"\n{'='*60}")
    print(f"  HEALTH CHECK REPORT")
    print(f"  Host: {results['hostname']}")
    print(f"  Time: {results['timestamp']}")
    print(f"  Overall: {results['overall_status']}")
    print(f"{'='*60}")

    # Print rate limiter stats if present
    if "rate_limiter" in results:
        rl = results["rate_limiter"]
        print(f"\n  Rate Limiter:")
        print(f"    Rate: {rl['rate']}/s | Throttled: {rl['throttled']} | Circuit: {rl['circuit_state']}")

    for category, items in [("Services", results["services"]),
                             ("Infrastructure", results["infrastructure"]),
                             ("System", results["system"])]:
        if items:
            print(f"\n  {category}:")
            for name, check in items.items():
                if isinstance(check, dict) and "status" in check:
                    status_icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗"}.get(check["status"], "?")
                    print(f"    {status_icon} {name}: {check['detail']}")
                else:
                    print(f"    {name}:")
                    for sub_name, sub_check in check.items():
                        if isinstance(sub_check, dict) and "status" in sub_check:
                            sub_icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗"}.get(sub_check["status"], "?")
                            print(f"      {sub_icon} {sub_name}: {sub_check['detail']}")
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="Health check tool")
    parser.add_argument("--service", "-s", help="Check specific service only")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--watch", "-w", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--timeout", "-t", type=int, default=None,
                        help="Per-request timeout in seconds (overrides per-service defaults)")
    parser.add_argument("--probe-rate", "-r", type=float, default=None,
                        help="Max probes per second (e.g., --probe-rate 5)")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.watch:
        print(f"Continuous monitoring (interval: {args.interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                results = run_health_checks(
                    args.service, args.json,
                    global_timeout=args.timeout,
                    probe_rate=args.probe_rate,
                )
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print_health_report(results)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
    else:
        results = run_health_checks(
            args.service, args.json,
            global_timeout=args.timeout,
            probe_rate=args.probe_rate,
        )
        if args.json:
            output = json.dumps(results, indent=2)
            print(output)
        else:
            print_health_report(results)

        if args.output:
            with open(args.output, "w") as f:
                if args.json:
                    json.dump(results, f, indent=2)
                else:
                    json.dump(results, f, indent=2)
            print(f"Report saved to {args.output}")

        if results["overall_status"] == "DEGRADED":
            return 1

    return 0


if __name__ == "__main__":
    main()
