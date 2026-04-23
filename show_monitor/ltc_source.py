"""
LTC time source.

Thin wrapper around the shared LTCDecoder (in the repo root). Translates
incoming LTC timecode messages into seconds-of-day and tracks signal
liveness. Designed to be polled from the UI thread — never blocks.

Signal goes stale after SIGNAL_TIMEOUT without a fresh `timecode`
message, mirroring how the CUE MONITOR handles it. While stale, the
source reports no time, so scenes on `ltc` behave as inactive.
"""
from __future__ import annotations

import logging
import queue
import time
from typing import Optional, Tuple

from ltc_decoder import LTCDecoder, LTCLibError  # repo-root module

logger = logging.getLogger(__name__)

SIGNAL_TIMEOUT = 2.0   # seconds — stale threshold


class LTCSource:
    def __init__(self):
        self._decoder: Optional[LTCDecoder] = None
        self._last_tc: Optional[Tuple[int, int, int, int]] = None  # h,m,s,f
        self._last_fps: float = 25.0
        self._last_msg_time: float = 0.0
        self._last_error: Optional[str] = None
        self._last_level_db: float = -120.0

    # ── lifecycle ────
    def start(self, device_index: Optional[int], channel_index: int) -> Optional[str]:
        """Start decoding on the given device. Returns an error string, or None on success."""
        self.stop()
        try:
            self._decoder = LTCDecoder(device_index=device_index, channel_index=channel_index)
            self._decoder.start()
            self._last_error = None
            return None
        except LTCLibError as e:
            self._last_error = f"libltc not found: {e}"
            logger.error("LTC start failed: %s", e)
            self._decoder = None
            return self._last_error
        except Exception as e:
            self._last_error = str(e)
            logger.error("LTC start failed: %s", e)
            self._decoder = None
            return self._last_error

    def stop(self):
        if self._decoder is not None:
            try:
                self._decoder.stop()
                self._decoder.join(timeout=2)
            except Exception as e:
                logger.warning("LTC stop: %s", e)
        self._decoder = None
        self._last_tc = None
        self._last_msg_time = 0.0

    def is_running(self) -> bool:
        return self._decoder is not None

    # ── polling ────
    def poll(self) -> list:
        """
        Drain the decoder queue. Returns a list of `(kind, ...)` tuples the
        caller may want to surface (e.g. "error" messages for the UI log).
        Timecode messages are consumed internally.
        """
        events: list = []
        if self._decoder is None:
            return events
        try:
            while True:
                msg = self._decoder.out_queue.get_nowait()
                kind = msg[0]
                if kind == "timecode":
                    _, h, m, s, f, fps = msg
                    self._last_tc = (h, m, s, f)
                    self._last_fps = fps
                    self._last_msg_time = time.time()
                elif kind == "level":
                    self._last_level_db = float(msg[1])
                elif kind == "error":
                    self._last_error = msg[1] if len(msg) > 1 else "LTC error"
                    events.append(msg)
                else:
                    events.append(msg)
        except queue.Empty:
            pass
        return events

    # ── state accessors ────
    def has_signal(self) -> bool:
        return (
            self._decoder is not None
            and self._last_tc is not None
            and (time.time() - self._last_msg_time) < SIGNAL_TIMEOUT
        )

    def current_seconds(self) -> Optional[float]:
        """LTC time expressed as seconds since 00:00:00. None if no signal."""
        if not self.has_signal() or self._last_tc is None:
            return None
        h, m, s, f = self._last_tc
        return h * 3600 + m * 60 + s + (f / self._last_fps if self._last_fps else 0.0)

    def current_tc_string(self) -> str:
        if self._last_tc is None:
            return "--:--:--:--"
        h, m, s, f = self._last_tc
        return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

    def fps(self) -> float:
        return self._last_fps

    def level_db(self) -> float:
        return self._last_level_db

    def last_error(self) -> Optional[str]:
        return self._last_error
