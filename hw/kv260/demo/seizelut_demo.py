#!/usr/bin/env python3
"""SeizeLUT live demo: recorded patient signals stream second by second through the integer front end (C, on this
computer's CPU) and the LUT classifier (in the KV260's FPGA fabric, or its software model), and a web dashboard on
the laptop shows every stage as it happens.

  Demo 1 (no extra parts):  sudo ... python3 seizelut_demo.py --demo 1     the board's own LEDs DS35/DS36 react
  Demo 2 (parts connected): sudo ... python3 seizelut_demo.py --demo 2     plus PMOD LEDs, buzzer and push button
  Rehearsal (no board):     python3 seizelut_demo.py --backend emu         same dashboard, classifier emulated
Open http://<board address>:8080 (or http://localhost:8080 for the rehearsal) in the laptop's browser.

Classifier backends: fpga (PYNQ overlay board/seizelut.bit + .hwh), emu (register-level software model of the same
core: used for the rehearsal, or on the board when no bitstream has been built yet; the dashboard says which one
runs). Every window is also run through the software model and the two are compared (bit-exact check).

Only the Python standard library and numpy are needed (plus PYNQ on the board for the FPGA backend).
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BOARD = HERE.parent / "board"
sys.path.insert(0, str(BOARD))
sys.path.insert(0, str(BOARD / "frontend"))
sys.path.insert(0, str(HERE))

BIO = ("eeg1", "eeg2", "ecg", "emg")
MOTION = ("acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z")
WEB = HERE / "web"
CTYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png"}


def platform_name() -> str:
    try:
        m = Path("/proc/device-tree/model").read_text(errors="ignore").strip("\x00 \n")
        if m:
            return m
    except OSError:
        pass
    import platform
    return f"{platform.system()} {platform.machine()} (no board)"


# ---------------------------------------------------------------------------------------------- engine
class Engine(threading.Thread):
    def __init__(self, core, model, backend_label, segs_index, leds, demo, args):
        super().__init__(daemon=True)
        self.core, self.model, self.leds, self.demo, self.args = core, model, leds, demo, args
        self.backend_label = backend_label
        self.index = segs_index
        self.cmds: queue.Queue = queue.Queue()
        self.clients: list[queue.Queue] = []
        self.lock = threading.Lock()
        self.frozen_thr = int(core.cfg["decision_threshold"])
        self.ops = {k: dict(v) for k, v in segs_index["operating_points"].items()}
        self.op = args.op
        self.speed = float(args.speed)
        self.seg = None
        self.phase = "idle"
        self.playing = False
        self.btn_count = None
        self.walking = False
        self.status_msg = ""
        self.last_tick = 0.0
        self.names = [f["name"] for f in model.thresholds["features"]]
        self.gate = model.head.get("artefact_gate", "none")

    # ---- clients
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=400)
        with self.lock:
            self.clients.append(q)
        self.cmds.put({"cmd": "_hello", "q": q})
        return q

    def unsubscribe(self, q) -> None:
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def send(self, msg: dict, only=None) -> None:
        data = json.dumps(msg, separators=(",", ":"))
        with self.lock:
            targets = [only] if only is not None else list(self.clients)
        for q in targets:
            try:
                q.put_nowait(data)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(data)
                except (queue.Empty, queue.Full):
                    pass

    # ---- segment
    def load(self, sid: str) -> None:
        meta = next((s for s in self.index["segments"] if s["id"] == sid), None)
        if meta is None:
            raise KeyError(sid)
        d = np.load(HERE / "segments" / f"{sid}.npz")
        raw = {k: d[k] for k in d.files}
        import frontend as fe
        self.seg = {"meta": meta, "raw": raw, "n": int(meta["seconds"])}
        self.stream = fe.Stream()
        self.pos = 0
        self.watch = int(meta["watch_from_s"])
        self.timeline: list[list] = []
        self.events: list[dict] = []
        self.hist_f: deque = deque(maxlen=int(self.core.cfg["n"]))
        self.hist_p: deque = deque(maxlen=int(self.core.cfg["n"]))
        self.n_win = self.n_match = 0
        self.rtt = deque(maxlen=200)
        self.alarm_on = 0
        self.last_alarm_end = None
        self.first_alarm = None
        self.ff_to = None
        self.core.soft_reset()
        self.apply_op()
        self.phase = "warmup"
        self.playing = False
        self.warm_t0 = time.monotonic()
        self.send({"type": "load", "segment": meta, "op": self.op})

    def apply_op(self) -> None:
        op = self.ops[self.op]
        prog = self.op != "strict"
        if prog:
            self.core.set_operating_point(op["threshold"], op["k"])
        self.core.set_io(auto=True, follow_programmable=prog, buzzer=not self.args.no_buzzer,
                         buzzer_active_low=self.args.buzzer_active_low)

    def truth(self, t: float) -> int:
        return int(any(on <= t < off for on, off in self.seg["meta"]["seizures_s"]))

    # ---- one second
    def step(self, live: bool) -> dict | None:
        b = self.pos
        raw = self.seg["raw"]
        blk = {k: v[b * 256:(b + 1) * 256] if k in BIO else v[b * 25:(b + 1) * 25] for k, v in raw.items()}
        w, X, art, viz = self.stream.push(blk)
        self.pos += 1
        wins = []
        if w is not None:
            wins.append(self.classify(w, X, art))
        if self.pos >= self.seg["n"]:        # last second: the final window has no look-ahead block
            w, X, art = self.stream.flush()
            if w is not None:
                wins.append(self.classify(w, X, art))
            self.phase = "ended"
            self.playing = False
            self.ended_pending = True
        win = wins[-1] if wins else None
        if not live:
            return {"wins": wins} if wins else None
        sig = {k: blk[k].tolist() for k in ("eeg1", "eeg2", "ecg") if k in blk}
        for k, v in viz.items():
            if v is not None:
                sig[k] = v.tolist()
        return {"type": "frame", "b": b, "t": self.seg["meta"]["record_start_s"] + b, "truth": self.truth(b + 0.5),
                "sig": sig, "win": win, "speed": self.speed,
                "prev": [[x["t_end"], x["score"], x["dec"], x["alarm"], sum(x["art"]), x["truth"], x["thr"]]
                         for x in wins[:-1]]}

    def classify(self, w: int, X: np.ndarray, art: np.ndarray) -> dict:
        model, core = self.model, self.core
        f = X[self.col]                         # the 38 classifier inputs, in register order
        a = int(art[0]) | (int(art[1]) << 1)
        t0 = time.perf_counter()
        s, d, al = core.classify(f, a)
        rtt = time.perf_counter() - t0
        res = core.read("RESULT")
        d2, al2 = (res >> 10) & 1, (res >> 11) & 1
        bits, luts = core.debug_taps()
        # software model of the same window, same history
        B, L, S = model.forward(f[None, :])
        gate = False
        if self.gate == "both":
            gate = bool(art[0] and art[1])
        elif self.gate == "any":
            gate = bool(art[0] or art[1])
        sd = int(S[0] >= self.frozen_thr and not gate)
        self.hist_f.append(sd)
        sa = int(sum(self.hist_f) >= int(self.core.cfg["k"]))
        opp = self.ops[self.op] if self.op != "strict" else None
        thr_p = self.core.read("OP_THR") & 0xFF
        thr_p = thr_p - 256 if thr_p & 0x80 else thr_p
        k_p = self.core.read("OP_K")
        sd2 = int(S[0] >= thr_p)
        self.hist_p.append(sd2)
        sa2 = int(sum(self.hist_p) >= k_p)
        ok = (s == int(S[0]) and d == sd and al == sa and d2 == sd2 and al2 == sa2
              and np.array_equal(bits, B[0]) and np.array_equal(luts, L[0]))
        self.n_win += 1
        self.n_match += int(ok)
        self.rtt.append(rtt)
        dec, alarm = (d2, al2) if opp else (d, al)
        thr = thr_p if opp else self.frozen_thr
        t_end = w + 2
        tr = self.truth(t_end - 0.5)
        self.timeline.append([t_end, s, dec, alarm, int(a), tr, int(thr)])
        if self.leds:
            self.leds.window(dec, alarm)
        if alarm and not self.alarm_on:
            merge = int(self.model.head.get("merge_s", 90))
            if self.last_alarm_end is not None and t_end - self.last_alarm_end <= merge:
                pass        # same alarm event (alarms closer than merge_s are merged, as in the evaluation)
            else:
                sz = self.seg["meta"]["seizures_s"]
                on = next((s0 for s0, s1 in sz if s0 - 10 <= t_end <= s1 + 60), None)
                ev = {"kind": "alarm", "t": t_end, "true": on is not None,
                      "after_onset": (t_end - on) if on is not None else None, "watched": t_end > self.watch}
                self.events.append(ev)
                if self.first_alarm is None and t_end > self.watch:
                    self.first_alarm = ev
                self.send({"type": "event", **ev})
        elif not alarm and self.alarm_on:
            self.last_alarm_end = t_end
            self.send({"type": "event", "kind": "alarm_end", "t": t_end})
        self.alarm_on = alarm
        return {"w": w, "t_end": t_end, "f": f.tolist(), "art": [int(art[0]), int(art[1])],
                "bits": "".join("1" if x else "0" for x in bits), "luts": "".join("1" if x else "0" for x in luts),
                "score": int(s), "dec": int(dec), "alarm": int(alarm), "thr": int(thr), "k": int(k_p if opp else self.core.cfg["k"]),
                "frozen": [int(d), int(al)], "prog": [int(d2), int(al2)], "ok": bool(ok),
                "n_win": self.n_win, "n_match": self.n_match, "rtt_us": round(rtt * 1e6, 1),
                "truth": tr, "hist": list(self.hist_p if opp else self.hist_f)}

    def summary(self) -> dict:
        meta = self.seg["meta"]
        watched = [e for e in self.timeline if e[0] > self.watch]
        alarms = [e for e in self.events if e.get("kind") == "alarm" and e.get("watched")]
        return {"segment": meta["id"], "op": self.op, "windows": self.n_win, "match": self.n_match,
                "seizures": meta["seizures_s"], "alarms": alarms,
                "alarm_windows": int(sum(e[3] for e in watched)),
                "detected": any(e["true"] for e in alarms), "false_alarms": sum(1 for e in alarms if not e["true"])}

    # ---- state for a new client
    def snapshot(self) -> dict:
        st = {"type": "state", "phase": self.phase, "playing": self.playing, "speed": self.speed, "op": self.op}
        if self.seg:
            st.update(segment=self.seg["meta"], pos=self.pos, timeline=self.timeline,
                      events=self.events, n_win=getattr(self, "n_win", 0), n_match=getattr(self, "n_match", 0))
        return st

    def tick_msg(self) -> dict:
        m = {"type": "tick", "phase": self.phase, "playing": self.playing, "speed": self.speed, "op": self.op}
        try:
            m["io"] = self.core.io_state()
            pressed, cnt = self.core.button()
            m["btn"] = pressed
            if self.btn_count is not None and cnt != self.btn_count:
                self.cmds.put({"cmd": "button", "source": "PMOD button"})
            self.btn_count = cnt
            m["nwin_hw"] = self.core.read("NWIN")
            m["lat"] = self.core.read("LATENCY")
        except Exception as e:      # an older bitstream without the demo registers
            m["io_err"] = str(e)
        if self.leds:
            m["board_leds"] = self.leds.lit()
        if self.seg:
            m["pos"] = self.pos
            if self.phase == "warmup":
                m["warm"] = [self.pos, self.watch]
        if getattr(self, "rtt", None):
            m["rtt_us"] = round(float(np.median(self.rtt)) * 1e6, 1)
        return m

    # ---- commands
    def handle(self, c: dict) -> None:
        cmd = c.get("cmd")
        if cmd == "_hello":
            self.send(self.snapshot(), only=c["q"])
        elif cmd == "load":
            self.load(c["id"])
        elif cmd == "play":
            if self.seg and self.phase in ("live",):
                self.playing = True
                self.next_t = time.monotonic()
            elif self.seg and self.phase == "ended":
                self.load(self.seg["meta"]["id"])
                self.autoplay = True
            elif self.seg and self.phase == "warmup":
                self.autoplay = True
        elif cmd == "pause":
            self.playing = False
            self.autoplay = False
        elif cmd == "speed":
            self.speed = max(0.25, min(60.0, float(c["value"])))
            self.next_t = time.monotonic()
        elif cmd == "op":
            if c["value"] in self.ops:
                self.op = c["value"]
                self.apply_op()
                self.send({"type": "op", "op": self.op, "t": self.pos})
        elif cmd == "skip":
            if self.seg and self.phase == "live":
                sz = self.seg["meta"]["seizures_s"]
                target = (sz[0][0] - float(c.get("before", 30))) if sz else self.pos + 120
                if target > self.pos:
                    self.ff_to = int(target)
        elif cmd == "restart":
            if self.seg:
                self.load(self.seg["meta"]["id"])
        elif cmd == "button":
            t = self.pos if self.seg else 0
            ev = {"kind": "button", "t": t, "source": c.get("source", "screen")}
            if self.seg:
                self.events.append(ev)
            self.send({"type": "event", **ev})
            if self.seg and self.phase == "live" and not self.playing:
                self.playing = True
                self.next_t = time.monotonic()
        elif cmd == "ledtest":
            threading.Thread(target=self.led_walk, daemon=True).start()
            if self.leds:
                self.leds.walk()

    def led_walk(self) -> None:
        if self.walking:
            return
        self.walking = True
        try:
            for i in range(7):
                self.core.set_leds_manual(1 << i)
                self.core.set_io(auto=False)
                time.sleep(0.45)
            self.core.set_leds_manual(0x7F & ~(1 << 5))
            time.sleep(0.6)
            self.core.set_leds_manual(0)
        finally:
            self.walking = False
            self.apply_op()

    # ---- main loop
    def run(self) -> None:
        self.next_t = time.monotonic()
        self.autoplay = False
        while True:
            try:
                while True:
                    c = self.cmds.get_nowait()
                    try:
                        self.handle(c)
                    except Exception as e:
                        self.send({"type": "error", "msg": f"{c.get('cmd')}: {e}"})
            except queue.Empty:
                pass
            now = time.monotonic()
            if self.seg and self.phase == "warmup":
                # the seconds before the watched part: real processing, paced at about 200x real time
                n = 0
                while self.pos < self.watch and n < 8:
                    self.step(live=False)
                    n += 1
                if self.pos >= self.watch:
                    self.phase = "live"
                    self.send({"type": "live", "pos": self.pos, "timeline": self.timeline})
                    if self.autoplay or self.args.autoplay:
                        self.playing = True
                        self.autoplay = False
                    self.next_t = time.monotonic()
                time.sleep(0.03)
            elif self.seg and self.phase == "live" and self.ff_to is not None:
                batch = []
                n = 0
                while self.pos < min(self.ff_to, self.seg["n"]) and n < 10:
                    r = self.step(live=False)
                    if r:
                        batch.extend(r["wins"])
                    n += 1
                self.send({"type": "ff", "pos": self.pos, "wins": [[x["t_end"], x["score"], x["dec"], x["alarm"],
                                                                    sum(x["art"]), x["truth"], x["thr"]] for x in batch],
                           "last": batch[-1] if batch else None})
                if self.pos >= self.ff_to or self.phase != "live":
                    self.ff_to = None
                    self.next_t = time.monotonic()
                time.sleep(0.02)
            elif self.seg and self.phase == "live" and self.playing:
                if now >= self.next_t:
                    fr = self.step(live=True)
                    if fr:
                        self.send(fr)
                    self.next_t += 1.0 / self.speed
                    if self.next_t < now - 0.5:
                        self.next_t = now
                time.sleep(max(0.0, min(0.01, self.next_t - time.monotonic())))
            else:
                if self.leds and not self.playing:
                    self.leds.idle()
                time.sleep(0.02)
            if getattr(self, "ended_pending", False):
                self.ended_pending = False
                self.send({"type": "ended", "summary": self.summary()})
            if now - self.last_tick > 0.1:
                self.last_tick = now
                self.send(self.tick_msg())


# ---------------------------------------------------------------------------------------------- HTTP
def make_handler(engine: Engine, info: dict):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/info":
                return self._send(200, json.dumps(info).encode(), "application/json")
            if path == "/api/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                q = engine.subscribe()
                try:
                    self.wfile.write(b"retry: 1000\n\n")
                    while True:
                        try:
                            data = q.get(timeout=10)
                            self.wfile.write(b"data: " + data.encode() + b"\n\n")
                        except queue.Empty:
                            self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    engine.unsubscribe(q)
                return
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            p = (WEB / name).resolve()
            if WEB.resolve() in p.parents and p.is_file():
                return self._send(200, p.read_bytes(), CTYPES.get(p.suffix, "application/octet-stream"))
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path.split("?")[0] != "/api/cmd":
                return self._send(404, b"not found", "text/plain")
            n = int(self.headers.get("Content-Length", 0))
            try:
                c = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, b"bad json", "text/plain")
            if not isinstance(c, dict) or str(c.get("cmd", "")).startswith("_"):
                return self._send(400, b"bad command", "text/plain")
            engine.cmds.put(c)
            return self._send(200, b'{"ok":true}', "application/json")

    return H


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", type=int, choices=(1, 2), default=1,
                    help="1: board LEDs only (no parts); 2: PMOD LEDs, buzzer and button connected")
    ap.add_argument("--backend", choices=("auto", "fpga", "emu"), default="auto",
                    help="auto: FPGA if PYNQ and board/seizelut.bit are available, else the software model")
    ap.add_argument("--bit", default=str(BOARD / "seizelut.bit"))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--segment", default="seizure_all_sensors")
    ap.add_argument("--op", default="strict", choices=("strict", "balanced", "sensitive"))
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--autoplay", action="store_true")
    ap.add_argument("--no-board-leds", action="store_true", help="leave the board's DS35/DS36 LEDs to Linux")
    ap.add_argument("--leds", nargs="*", help="names in /sys/class/leds to use (default: heartbeat and vbus_det)")
    ap.add_argument("--board-button", action="store_true", help="use the board's FWUEN button as the patient button")
    ap.add_argument("--no-buzzer", action="store_true")
    ap.add_argument("--buzzer-active-low", action="store_true", help="for buzzer modules that beep when I/O is low")
    args = ap.parse_args()

    from seizelut_kv260 import SeizeLUT
    from seizelut_model import SeizeLUTModel
    model = SeizeLUTModel(BOARD / "model")
    backend = args.backend
    note = ""
    if backend in ("auto", "fpga"):
        have_bit = Path(args.bit).exists() and Path(args.bit).with_suffix(".hwh").exists()
        try:
            import pynq  # noqa: F401
            have_pynq = True
        except Exception:
            have_pynq = False
        if have_bit and have_pynq:
            backend = "fpga"
        elif backend == "fpga":
            print(f"FPGA backend needs PYNQ ({'ok' if have_pynq else 'missing'}) and {args.bit} + .hwh "
                  f"({'ok' if have_bit else 'missing'})")
            return 2
        else:
            backend = "emu"
            note = ("no bitstream yet (board/seizelut.bit)" if have_pynq else "no PYNQ on this computer")
    if backend == "fpga":
        core = SeizeLUT("pynq", bitfile=args.bit)
        ident = core.identify()
        if not ident["id_ok"]:
            print("the loaded bitstream does not answer with the SeizeLUT ID:", ident)
            return 2
        try:
            core.read("IO_STATE")
            core.debug_taps()
        except Exception:
            print("this bitstream has no demo registers (built before kit v4): rebuild with vivado/build.sh")
            return 2
        label = "FPGA: SeizeLUT core in the KV260 fabric, 100 MHz"
    else:
        core = SeizeLUT("emu")
        label = "Software model of the FPGA core" + (f" ({note})" if note else "")
    segs = json.loads((HERE / "segments" / "index.json").read_text())

    leds = None
    led_note = "disabled"
    if not args.no_board_leds:
        from board_io import BoardLeds
        bl = BoardLeds(args.leds)
        if bl.ok:
            leds = bl
            led_note = ", ".join(bl.names)
        else:
            led_note = bl.reason
    engine = Engine(core, model, label, segs, leds, args.demo, args)
    import frontend as fe
    hdr = (BOARD / "frontend" / "seizelut_fe_params.h").read_text()
    names = hdr.split("FEATURE_NAMES[N_FEATURES] = {", 1)[1].split("};", 1)[0]
    spec_names = [x.strip().strip('"') for x in names.replace("\n", " ").split(",") if x.strip()]
    assert len(spec_names) == fe._lib().fe_n_features(), "feature name table"
    engine.col = [spec_names.index(n) for n in engine.names]
    btn_note = "off"
    if args.board_button:
        from board_io import BoardButton
        bb = BoardButton(lambda: engine.cmds.put({"cmd": "button", "source": "board button (FWUEN)"}))
        if bb.dev:
            bb.start()
            btn_note = bb.dev
        else:
            btn_note = bb.reason

    bits = model.thresholds["input_bits"]
    feats = []
    for i, f in enumerate(model.thresholds["features"]):
        idx = [j for j, b in enumerate(bits) if b["feature"] == f["name"]]
        feats.append({"name": f["name"], "bits": idx, "thr": [int(bits[j]["threshold"]) for j in idx]})
    info = {"backend": backend, "backend_label": label, "platform": platform_name(), "demo": args.demo,
            "board_leds": led_note, "board_leds_on": bool(leds), "board_button": btn_note,
            "segments": segs["segments"], "operating_points": segs["operating_points"],
            "features": feats, "n_bits": len(bits), "groups": model.head["groups"],
            "frozen_threshold": int(core.cfg["decision_threshold"]), "k": int(core.cfg["k"]),
            "n": int(core.cfg["n"]), "latency_cycles": int(core.cfg["latency_cycles"]), "clock_mhz": 100,
            "pmod": core.cfg.get("pmod"), "default_segment": args.segment, "default_op": args.op}

    def bye(*_):
        try:
            core.set_leds_manual(0)
            core.set_io(auto=False)
        except Exception:
            pass
        if leds:
            leds.restore()
        os._exit(0)

    signal.signal(signal.SIGINT, bye)
    signal.signal(signal.SIGTERM, bye)
    engine.start()
    engine.cmds.put({"cmd": "load", "id": args.segment})
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(engine, info))
    srv.daemon_threads = True
    print(f"SeizeLUT live demo {args.demo}: {label}")
    print(f"  platform: {info['platform']}; board LEDs: {led_note}; board button: {btn_note}")
    print(f"  open http://<this board's address>:{args.port} on the laptop "
          f"(rehearsal: http://localhost:{args.port}); Ctrl+C stops")
    try:
        srv.serve_forever()
    finally:
        bye()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
