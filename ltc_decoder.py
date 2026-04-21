from __future__ import annotations

import ctypes
import ctypes.util
import mmap
import os
import struct
import threading
import time
import queue
import logging
import traceback
import numpy as np

logger = logging.getLogger(__name__)

LTC_PATHS = [
    "/opt/homebrew/lib/libltc.dylib",   # Apple Silicon
    "/usr/local/lib/libltc.dylib",      # Intel
]

SAMPLE_RATE = 48000
CHUNK       = 1024
SIGNAL_LOSS_TIMEOUT = 2.0

# Standard LTC frame rates. fps values outside this set are rejected.
_STD_FPS = (24.0, 25.0, 29.97, 30.0)


def _nearest_fps(raw: float) -> float:
    """Round raw fps to the nearest standard LTC rate. Returns 25.0 if ambiguous."""
    if raw <= 0:
        return 25.0
    best = min(_STD_FPS, key=lambda f: abs(f - raw))
    return best if abs(best - raw) < 3.0 else 25.0


def _decode_ltc_bytes(data: bytes) -> tuple:
    """
    Decode SMPTE timecode from raw LTC frame bytes (little-endian bitfield layout).
    Returns (hours, mins, secs, frame_num, drop_frame).
    """
    frame_num = (data[0] & 0x0F) + 10 * (data[1] & 0x03)
    drop      = bool(data[1] & 0x08)
    secs      = (data[2] & 0x0F) + 10 * (data[3] & 0x07)
    mins      = (data[4] & 0x0F) + 10 * (data[5] & 0x07)
    hours     = (data[6] & 0x0F) + 10 * (data[7] & 0x03)
    return hours, mins, secs, frame_num, drop


def find_libltc():
    for p in LTC_PATHS:
        if os.path.exists(p):
            return p
    return ctypes.util.find_library("ltc")


# ── ctypes structs ────────────────────────────────────────────────────────────

class LTCFrame(ctypes.Structure):
    _fields_ = [("data", ctypes.c_uint8 * 10)]


class LTCFrameExt(ctypes.Structure):
    _fields_ = [
        ("ltc",       LTCFrame),
        ("off_start", ctypes.c_int64),
        ("off_end",   ctypes.c_int64),
        ("reverse",   ctypes.c_int),
        ("fps",       ctypes.c_float),
        ("startof",   ctypes.c_int64),
        ("endof",     ctypes.c_int64),
    ]


class LTCLibError(Exception):
    pass


def load_libltc():
    lib_path = find_libltc()
    if not lib_path:
        raise LTCLibError(
            "libltc not found.\n\nInstall with:\n  brew install libltc"
        )
    logger.info("Loading libltc from: %s", lib_path)
    try:
        ltc = ctypes.CDLL(lib_path)
    except OSError as e:
        raise LTCLibError(f"Cannot load libltc from {lib_path}:\n{e}")

    sz_ext = ctypes.sizeof(LTCFrameExt)
    logger.debug(
        "ctypes struct sizes — LTCFrame: %d  LTCFrameExt: %d",
        ctypes.sizeof(LTCFrame), sz_ext,
    )
    # Expected: LTCFrame=10, LTCFrameExt=56
    if sz_ext not in (56, 40):
        logger.warning("Unexpected LTCFrameExt size %d — struct may be misaligned", sz_ext)

    # Use c_void_p for all pointer args to avoid POINTER(T) type-object bugs
    # on Python 3.9 ARM64 macOS.

    ltc.ltc_decoder_create.restype  = ctypes.c_void_p
    ltc.ltc_decoder_create.argtypes = [ctypes.c_int, ctypes.c_int]

    ltc.ltc_decoder_write_s16.restype  = None
    ltc.ltc_decoder_write_s16.argtypes = [
        ctypes.c_void_p,   # decoder handle
        ctypes.c_void_p,   # int16 buffer (raw address)
        ctypes.c_size_t,   # nsamples
        ctypes.c_int64,    # posinfo
    ]

    ltc.ltc_decoder_read.restype  = ctypes.c_int
    ltc.ltc_decoder_read.argtypes = [
        ctypes.c_void_p,   # decoder handle
        ctypes.c_void_p,   # LTCFrameExt* (raw address)
    ]

    ltc.ltc_decoder_free.restype  = None
    ltc.ltc_decoder_free.argtypes = [ctypes.c_void_p]

    return ltc


# ── Decoder thread ────────────────────────────────────────────────────────────

class LTCDecoder(threading.Thread):
    """
    Background thread: reads audio → feeds libltc → emits timecodes via queue.

    Queue messages:
      ("timecode", hours, mins, secs, frames, fps)
      ("signal_lost",)
      ("level", rms_db)
      ("error", message)
    """

    def __init__(self, device_index=None, channel_index: int = 0):
        super().__init__(daemon=True)
        self.device_index  = device_index
        self.channel_index = channel_index
        self.out_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        logger.info(
            "LTCDecoder starting — device_index=%s  channel_index=%d",
            self.device_index, self.channel_index,
        )
        try:
            self._run_inner()
        except Exception:
            tb = traceback.format_exc()
            logger.error("LTCDecoder unhandled exception:\n%s", tb)
            self.out_queue.put(("error", f"LTC decoder crashed:\n{tb}"))

    def _run_inner(self):
        try:
            ltc_lib = load_libltc()
        except LTCLibError as e:
            self.out_queue.put(("error", str(e)))
            return

        try:
            import pyaudio
        except ImportError:
            self.out_queue.put(("error",
                "pyaudio not installed.\n\nRun:  pip install pyaudio"))
            return

        pa           = pyaudio.PyAudio()
        stream       = None
        decoder      = None
        num_channels = max(1, self.channel_index + 1)

        try:
            decoder = ltc_lib.ltc_decoder_create(SAMPLE_RATE, 1920)
            if not decoder:
                self.out_queue.put(("error", "Failed to create LTC decoder."))
                return
            logger.debug("ltc_decoder_create OK  handle=0x%x", decoder)

            open_kwargs: dict = dict(
                format=pyaudio.paInt16,
                channels=num_channels,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            if self.device_index is not None:
                open_kwargs["input_device_index"] = self.device_index

            logger.info(
                "Opening audio stream: device=%s  channels=%d (using ch %d)  rate=%d  chunk=%d",
                self.device_index, num_channels, self.channel_index, SAMPLE_RATE, CHUNK,
            )
            try:
                stream = pa.open(**open_kwargs)
            except OSError as e:
                logger.error("pa.open failed: %s", e)
                self.out_queue.put(("error", f"Cannot open audio device:\n{e}"))
                return

            logger.info("Audio stream opened OK")

            last_frame_t     = time.monotonic()
            signal_lost_sent = False
            pos              = 0            # sample position counter (plain int)
            frames_decoded   = 0

            # Allocate an OVERSIZED buffer outside the Python heap for libltc
            # to write LTCFrameExt into. This prevents heap corruption if
            # libltc's actual struct is larger than our ctypes definition (56B).
            # Using mmap gives us a page-aligned buffer that won't corrupt
            # adjacent Python objects even if libltc writes beyond 56 bytes.
            _FRAME_BUF_SIZE = 4096  # one full page — way more than any LTCFrameExt
            frame_mmap = mmap.mmap(-1, _FRAME_BUF_SIZE)
            frame_buf_addr = ctypes.addressof(ctypes.c_char.from_buffer(frame_mmap))
            frame_ptr = ctypes.c_void_p(frame_buf_addr)

            while not self._stop_event.is_set():
                try:
                    raw = stream.read(CHUNK, exception_on_overflow=False)
                except OSError as e:
                    logger.warning("stream.read error: %s", e)
                    continue

                # Deinterleave: extract only the requested channel.
                all_samples = np.frombuffer(raw, dtype=np.int16)
                if num_channels > 1:
                    samples = all_samples[self.channel_index::num_channels].copy()
                else:
                    samples = all_samples

                rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
                db  = 20.0 * np.log10(rms / 32768.0) if rms > 0 else -120.0
                self.out_queue.put(("level", db))

                # Ensure contiguous C-order int16 buffer that stays alive
                # during the ctypes call. np.ascontiguousarray guarantees this.
                samples = np.ascontiguousarray(samples, dtype=np.int16)
                buf_addr = samples.ctypes.data
                n        = len(samples)
                logger.debug("write_s16: %d samples  pos=%d  rms=%.1f dB", n, pos, db)
                ltc_lib.ltc_decoder_write_s16(decoder, buf_addr, n, pos)
                pos += n

                # Drain all decoded frames from the libltc queue.
                while ltc_lib.ltc_decoder_read(decoder, frame_ptr):
                    # Read raw bytes from the mmap buffer (safe — isolated page).
                    # LTCFrameExt layout (ARM64 little-endian, 56 bytes):
                    #   offset  0: LTCFrame.data  [10 bytes]
                    #   offset 10: padding        [6 bytes]
                    #   offset 16: off_start      int64
                    #   offset 24: off_end        int64
                    #   offset 32: reverse        int32
                    #   offset 36: fps            float32 (padding to 40)
                    #   offset 40: startof        int64 (or absent in older libltc)
                    #   offset 48: endof          int64
                    frame_mmap.seek(0)
                    raw_frame = frame_mmap.read(56)

                    frame_data = raw_frame[0:10]
                    h, m, s, f, drop = _decode_ltc_bytes(frame_data)

                    off_start, off_end = struct.unpack_from("<qq", raw_frame, 16)
                    reverse_val = struct.unpack_from("<i", raw_frame, 32)[0]
                    fps_raw = struct.unpack_from("<f", raw_frame, 36)[0]

                    span = off_end - off_start
                    if span > 0:
                        fps = _nearest_fps(SAMPLE_RATE / span)
                    else:
                        fps = _nearest_fps(fps_raw)

                    frames_decoded += 1
                    logger.debug(
                        "LTC #%d  %02d:%02d:%02d:%02d  fps=%.2f  drop=%s  reverse=%d  span=%d",
                        frames_decoded, h, m, s, f, fps, drop, reverse_val, span,
                    )

                    self.out_queue.put(("timecode", h, m, s, f, fps))
                    last_frame_t     = time.monotonic()
                    signal_lost_sent = False

                if (not signal_lost_sent and
                        time.monotonic() - last_frame_t > SIGNAL_LOSS_TIMEOUT):
                    logger.info(
                        "LTC signal lost after %.1fs silence",
                        time.monotonic() - last_frame_t,
                    )
                    self.out_queue.put(("signal_lost",))
                    signal_lost_sent = True

        finally:
            logger.info(
                "LTCDecoder shutting down  frames_decoded=%d",
                frames_decoded if "frames_decoded" in dir() else 0,
            )
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if decoder:
                ltc_lib.ltc_decoder_free(decoder)
            pa.terminate()
            try:
                frame_mmap.close()
            except Exception:
                pass
