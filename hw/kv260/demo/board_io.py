"""The KV260's own LEDs and button, driven from Linux (no extra parts; used by Demo 1).

The K26 module's device tree (upstream Linux, zynqmp-sm-k26-revA.dts) declares two gpio-leds on PS MIO pins,
DS35 "heartbeat" (gpio 7; blinks while Linux runs) and DS36 "vbus_det" (gpio 8; normally on), and one gpio-key,
the FWUEN push button (gpio 12, code BTN_MISC). Linux exposes the LEDs in /sys/class/leds/<name>/ and the button as
an input event device. Writing them needs root (the demo runs with sudo on the board).

BoardLeds takes over both LEDs while the demo runs and gives them back (trigger and brightness) at exit:
  heartbeat LED: one short flash per window classified; fast strobe while the alarm is on
  second LED:    on while the classifier says "seizure-like" for the current window, steady on during the alarm
"""
from __future__ import annotations

import os
import struct
import threading
import time
from pathlib import Path

LEDS = Path(os.environ.get("SEIZELUT_LEDS_DIR", "/sys/class/leds"))   # override for tests


def _trigger(p: Path) -> str | None:
    try:
        txt = (p / "trigger").read_text()
    except OSError:
        return None
    for tok in txt.split():
        if tok.startswith("[") and tok.endswith("]"):
            return tok[1:-1]
    return txt.strip() if txt.strip() and " " not in txt.strip() else None


class BoardLeds:
    def __init__(self, names: list[str] | None = None):
        self.ok, self.reason, self.saved = False, "", {}
        self.names: list[str] = []
        avail = sorted(p.name for p in LEDS.iterdir()) if LEDS.exists() else []
        if not avail:
            self.reason = "no LEDs in /sys/class/leds (not a board, or the kernel exposes none)"
            return

        def pick(keys):
            return next((n for n in avail if any(k in n.lower() for k in keys)), None)

        if names:
            chosen = [n for n in names if n in avail]
        else:   # only the K26 LEDs; never other LEDs of a laptop (keyboard, camera)
            chosen = [n for n in (pick(["heartbeat", "ds35"]), pick(["vbus", "ds36"])) if n]
        if not chosen:
            self.reason = (f"none of {names} in /sys/class/leds ({avail})" if names else
                           f"no heartbeat/vbus_det LED in /sys/class/leds ({', '.join(avail[:6])}); use --leds NAME NAME")
            return
        try:
            for n in chosen:
                p = LEDS / n
                self.saved[n] = (_trigger(p), (p / "brightness").read_text().strip())
                (p / "trigger").write_text("none")
                (p / "brightness").write_text("0")
        except OSError as e:
            self.reason = f"cannot write /sys/class/leds ({e}); run the demo with sudo"
            self.restore()
            return
        self.names = chosen
        self.available = avail
        self.ok = True
        self.state = {"flash_until": 0.0, "decision": 0, "alarm": 0}
        self.current = [None] * len(chosen)
        self.walk_until, self.walk_idx = 0.0, -1
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def window(self, decision: int, alarm: int) -> None:
        """Called once per classified window."""
        if self.ok:
            self.state.update(flash_until=time.monotonic() + 0.09, decision=int(decision), alarm=int(alarm))

    def idle(self) -> None:
        if self.ok:
            self.state.update(decision=0, alarm=0)

    def walk(self) -> None:
        """LED test: each LED on for 0.6 s in turn."""
        if self.ok:
            self.walk_until = time.monotonic() + 0.6 * len(self.names)

    def lit(self) -> list[int]:
        return [int(bool(c)) for c in self.current] if self.ok else []

    def _set(self, i: int, on: bool) -> None:
        if self.current[i] == on:
            return
        try:
            (LEDS / self.names[i] / "brightness").write_text("1" if on else "0")
            self.current[i] = on
        except OSError:
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            st = self.state
            if now < self.walk_until:
                k = int((self.walk_until - now) / 0.6)
                idx = len(self.names) - 1 - k
                want = [i == idx for i in range(len(self.names))]
            else:
                hb = (now < st["flash_until"]) if not st["alarm"] else (int(now * 10) % 2 == 0)
                want = [hb, bool(st["decision"] or st["alarm"])][: len(self.names)]
            for i, w in enumerate(want):
                self._set(i, w)
            time.sleep(0.02)

    def restore(self) -> None:
        if getattr(self, "_stop", None):
            self._stop.set()
            self.thread.join(timeout=1)
        for n, (trig, bright) in self.saved.items():
            p = LEDS / n
            try:
                (p / "trigger").write_text(trig or "none")
                if not trig or trig == "none":
                    (p / "brightness").write_text(bright or "0")
            except OSError:
                pass
        self.saved = {}


class BoardButton(threading.Thread):
    """The board's FWUEN push button as a Linux input device (gpio-keys). Calls callback() on every press.
    Pressing FWUEN while Linux runs only sends a key event; do not press it together with RESET (that combination
    starts the firmware recovery tool)."""

    def __init__(self, callback):
        super().__init__(daemon=True)
        self.callback, self.dev, self.reason = callback, None, ""
        try:
            blocks = Path("/proc/bus/input/devices").read_text().split("\n\n")
        except OSError:
            self.reason = "no /proc/bus/input/devices"
            return
        for b in blocks:
            if "gpio-keys" in b or "gpio_keys" in b:
                for line in b.splitlines():
                    if line.startswith("H: Handlers="):
                        ev = [t for t in line.split("=", 1)[1].split() if t.startswith("event")]
                        if ev:
                            self.dev = f"/dev/input/{ev[0]}"
        if not self.dev:
            self.reason = "no gpio-keys input device"

    def run(self) -> None:
        if not self.dev:
            return
        size = struct.calcsize("llHHi")
        try:
            fd = os.open(self.dev, os.O_RDONLY)
        except OSError as e:
            self.reason = f"cannot open {self.dev} ({e})"
            return
        while True:
            try:
                data = os.read(fd, size)
            except OSError:
                return
            if len(data) < size:
                continue
            _, _, typ, code, value = struct.unpack("llHHi", data)
            if typ == 1 and value == 1:        # EV_KEY, pressed
                try:
                    self.callback()
                except Exception:
                    pass
