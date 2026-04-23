"""
World Clock time source.

Uses the system clock for every frame (modern OSes keep this in sync with
NTP in the background). Runs an occasional background check against a
public NTP pool to detect and surface drift when the system clock can't
reach NTP (no internet, NTP blocked, etc.). When the check fails or no
internet is available, the app silently falls back to the system clock.

Drift is reported (not corrected) — we never adjust the clock our app
reports, so the operator always sees a consistent value. They just get a
warning badge if local time and NTP disagree by more than the configured
threshold.
"""
from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

NTP_SERVERS = ("pool.ntp.org", "time.google.com", "time.cloudflare.com")
NTP_PORT = 123
NTP_TIMEOUT = 2.0
NTP_EPOCH_OFFSET = 2208988800  # seconds between 1900-01-01 and 1970-01-01


def now_seconds_of_day() -> int:
    """Seconds since local midnight, 0..86399."""
    n = datetime.now()
    return n.hour * 3600 + n.minute * 60 + n.second


def now_hms() -> str:
    """Local wall clock as 'HH:MM:SS'."""
    return datetime.now().strftime("%H:%M:%S")


def _query_ntp(host: str) -> Optional[float]:
    """Returns NTP server time as unix seconds, or None on failure."""
    try:
        packet = b"\x1b" + b"\x00" * 47
        t0 = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(NTP_TIMEOUT)
        try:
            sock.sendto(packet, (host, NTP_PORT))
            data, _ = sock.recvfrom(48)
        finally:
            sock.close()
        t3 = time.time()

        # Offset 40: transmit timestamp (8 bytes: 4 sec + 4 frac)
        secs, frac = struct.unpack("!II", data[40:48])
        ntp_time = secs - NTP_EPOCH_OFFSET + frac / 2**32

        # Compensate roughly for one-way network delay
        rtt = max(0.0, t3 - t0)
        return ntp_time + rtt / 2
    except (socket.timeout, OSError) as e:
        logger.debug("NTP query to %s failed: %s", host, e)
        return None


def measure_drift_seconds(timeout_hint: float = 2.0) -> Optional[float]:
    """
    Returns `local - ntp` in seconds (positive = local is ahead).
    Returns None if no NTP server answered (no internet, blocked, etc.).
    """
    del timeout_hint  # timeout is fixed per-server; kept for API compat
    for host in NTP_SERVERS:
        ntp = _query_ntp(host)
        if ntp is not None:
            return time.time() - ntp
    return None


class DriftMonitor:
    """
    Background thread that periodically measures NTP drift and exposes the
    latest reading + last-check timestamp. Safe to start() once and read
    state() from the UI thread; never blocks callers.
    """

    DEFAULT_INTERVAL_SEC = 300  # 5 minutes

    def __init__(self, interval_sec: int = DEFAULT_INTERVAL_SEC):
        self._interval = interval_sec
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._drift: Optional[float] = None
        self._last_check: Optional[float] = None
        self._last_ok: Optional[float] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="DriftMonitor", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def state(self) -> dict:
        with self._lock:
            return {
                "drift": self._drift,
                "last_check": self._last_check,
                "last_ok": self._last_ok,
            }

    def _run(self) -> None:
        # Fast first check so the UI sees a status shortly after startup.
        self._tick()
        while not self._stop.wait(self._interval):
            self._tick()

    def _tick(self) -> None:
        drift = measure_drift_seconds()
        now = time.time()
        with self._lock:
            self._drift = drift
            self._last_check = now
            if drift is not None:
                self._last_ok = now
