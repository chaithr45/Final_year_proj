"""Doctor alert: the five measured details of an alarm, sent to an ESP32 over its USB serial port.

The ESP32 (esp32/seizelut_alert/seizelut_alert.ino) turns them into a phone push notification (ntfy) and a live
web page. Every value is measured by the front end (the C streaming front end on the ARM, bit-exact with the feature
engine in the fabric); nothing is a diagnosis.

  1 alarm: start, duration, detector confidence (seizure-group LUTs that are 1)
  2 heart rate: before the alarm vs now (ECG R-peak intervals; fast if > 100 bpm or a rise of 20 % or more)
  3 movement: chest accelerometer (or gyroscope) activity vs before; "motor pattern likely" when it rose 2.6-fold
    or more. That threshold was chosen on training patients 1-48 against the doctors' motor / non-motor labels and
    agreed with them in 64 % (balanced accuracy) on training patients 49-96 (results/tables/alert_signs.json):
    a hint for the doctor, not a seizure type
  4 muscle: EMG power vs before
  5 brain: EEG line length vs before, and whether slow (delta/theta) or fast (beta) activity rose most
  plus: patient button (pressed = the patient was aware enough to press it), sensors worn, alarm end and duration.
For acting at once: danger flags (heart rate above 150 or below 40 bpm, ECG unreadable for 5 s: check pulse and
breathing by hand), escalation messages when the alarm has lasted 2 min and 5 min (5 min: emergency, the ILAE 2015
time point t1 for status epilepticus in convulsive seizures) and every minute after, the number of alarms in the
last hour (clusters), and the doctor's acknowledgement coming back from the ESP32 ({"event": "ack"}).

"Before" is the 60 s ending 30 s before the alarm started; "now" is the last 10 s. An alarm that stops and
restarts within 30 s is the same event (the end message waits for 30 s without alarm). Messages are one JSON object per
line at 115200 baud: {"event": "hello" | "start" | "update" | "end" | "button", "title": ..., "body": ..., ...}.
"""
from __future__ import annotations

import glob
import json
import os
import termios
import time
from collections import deque

import numpy as np

MOTOR_RATIO = 2.6      # results/tables/alert_signs.json["motor_hint"]["threshold_ratio"] (2.59), rounded


def _unlog(v: float) -> float:
    """Inverse of the front end's log2 (leading-one position + 3 mantissa bits, 2^-3 steps)."""
    v = int(round(v))
    lp, m = v >> 3, v & 7
    return (1 << lp) * (1 + m / 8.0)


def _ratio(now: float, before: float) -> float:
    return float(2 ** ((now - before) / 8.0))


class AlertBuilder:
    """Keeps the last 100 windows of the 117 front-end features and builds the alarm messages."""

    def __init__(self, feature_names: list[str], bed: str = "Bed 1", update_s: int = 15, hold_s: int = 30):
        self.ix = {n: i for i, n in enumerate(feature_names)}
        self.hist: deque = deque(maxlen=100)
        self.bed, self.update_s, self.hold_s = bed, update_s, hold_s
        self.last_on = None
        self.active = False
        self.t0 = None
        self.peak_hr = None
        self.aware = False
        self.last_update = None
        self.next_esc = None
        self.starts: deque = deque(maxlen=50)        # alarm start times (cluster count)

    def _col(self, rows, name):
        return np.array([r[self.ix[name]] for r in rows], dtype=np.float64)

    def _hr(self, rows):
        if not rows:
            return None
        ok = [r for r in rows if r[self.ix["present_ecg"]] and not r[self.ix["ecg_quality_bad"]]]
        if len(ok) < max(2, len(rows) // 3):
            return None
        return float(np.median([60.0 * 256.0 / _unlog(r[self.ix["ecg_log_rr"]]) for r in ok]))

    def signs(self) -> dict:
        rows = list(self.hist)
        now, before = rows[-10:], rows[-90:-30] if len(rows) >= 40 else rows[:max(1, len(rows) - 10)]
        s = {}
        pres = {k: bool(now[-1][self.ix[f"present_{k}"]]) for k in ("ecg", "emg", "mov_acc", "mov_gyr")}
        s["sensors"] = " ".join(["EEG"] + [n for k, n in (("ecg", "ECG"), ("emg", "EMG"), ("mov_acc", "ACC"),
                                                         ("mov_gyr", "GYR")) if pres[k]])
        # 2 heart rate
        hb, hn = (self._hr(before), self._hr(now)) if pres["ecg"] else (None, None)
        if hn is None:
            s["hr"], s["hr_text"] = None, ("not measurable now (ECG disturbed, often by movement)" if pres["ecg"]
                                           else "ECG not worn")
        else:
            rise = 100.0 * (hn / hb - 1) if hb else None
            flag = "fast" if hn > 100 or (rise is not None and rise >= 20) else "slow" if hn < 50 else "normal"
            s["hr"] = [None if hb is None else round(hb), round(hn)]
            s["hr_text"] = (f"{round(hb)} -> {round(hn)} bpm ({'+' if rise >= 0 else ''}{rise:.0f} %), {flag}"
                            if hb else f"{round(hn)} bpm, {flag}")
            self.peak_hr = max(self.peak_hr or 0, hn)
        danger = []
        if hn is not None and hn > 150:
            danger.append(f"very fast heart rate ({hn:.0f} bpm)")
        if hn is not None and hn < 40:
            danger.append(f"very slow heart rate ({hn:.0f} bpm)")
        if pres["ecg"] and all(r[self.ix["ecg_quality_bad"]] for r in rows[-5:]):
            danger.append("ECG unreadable for 5 s: check pulse and breathing by hand")
        s["danger"] = danger
        # 3 movement
        mk = "mov_acc" if pres["mov_acc"] else "mov_gyr" if pres["mov_gyr"] else None
        if mk:
            r = _ratio(np.median(self._col(now, f"{mk}_mag")), np.median(self._col(before, f"{mk}_mag")))
            act = float(np.mean(self._col(now, f"{mk}_act")) / 50.0)
            level = "strong" if r >= MOTOR_RATIO else "some" if r >= 1.5 else "little"
            s["mov_ratio"], s["mov_active"] = round(r, 1), round(act, 2)
            s["mov_text"] = f"{level} movement (x{r:.1f} vs before)"
            s["hint"] = ("motor pattern likely (strong movement)" if r >= MOTOR_RATIO
                         else "little movement (non-motor pattern possible)")
        else:
            s["mov_ratio"], s["mov_text"], s["hint"] = None, "motion sensor not worn", "no movement data"
        # 4 muscle
        if pres["emg"]:
            r = _ratio(np.median(self._col(now, "emg_mav")), np.median(self._col(before, "emg_mav")))
            s["emg_ratio"] = round(r, 1)
            s["emg_text"] = f"{'increased' if r >= 2 else 'normal'} (x{r:.1f} vs before)"
        else:
            s["emg_ratio"], s["emg_text"] = None, "EMG not worn"
        # 5 brain
        r = _ratio(np.median(self._col(now, "eeg_ll_mean")), np.median(self._col(before, "eeg_ll_mean")))
        rise = {k: np.median(self._col(now, f"eeg_{k}_mean")) - np.median(self._col(before, f"eeg_{k}_mean"))
                for k in ("delta", "theta", "beta")}
        top = max(rise, key=rise.get)
        rhythm = "slow waves (delta/theta)" if top in ("delta", "theta") else "fast activity (beta)"
        s["eeg_ratio"] = round(r, 1)
        s["eeg_text"] = f"{'strong' if r >= 1.5 else 'mild'} change (x{r:.1f} vs before), mostly {rhythm}"
        return s

    def window(self, X, alarm: int, n_sz_luts: int, n_luts_group: int, t_rec: float) -> dict | None:
        """One classified window: X = the 117 front-end features. Returns a message to send, or None."""
        self.hist.append(np.asarray(X, dtype=np.int64))
        if alarm:
            self.last_on = t_rec
        if alarm and not self.active:
            self.active, self.t0, self.peak_hr, self.aware, self.last_update = True, t_rec, None, False, t_rec
            self.next_esc = t_rec + 120
            self.starts.append(t_rec)
            return self._msg("start", t_rec, n_sz_luts, n_luts_group)
        if self.active and not alarm and t_rec - self.last_on >= self.hold_s:   # quiet for hold_s: event over
            self.active = False
            s = self.signs()
            d = self.last_on - self.t0 + 1
            body = (f"Alarm ended after {d:.0f} s.\nPeak heart rate: "
                    f"{'n/a' if self.peak_hr is None else f'{self.peak_hr:.0f} bpm'}\n"
                    f"Patient button: {'pressed' if self.aware else 'not pressed'}\nNow: {s['mov_text']}")
            return {"event": "end", "bed": self.bed, "dur_s": round(d), "title": f"Alarm ended - {self.bed}",
                    "body": body, **s}
        if self.active and alarm and t_rec >= self.next_esc:      # 2 min, 5 min, then every minute (alarm on)
            d = t_rec - self.t0
            self.next_esc = self.t0 + (300 if d < 300 else 60 * (int(d // 60) + 1))
            self.last_update = t_rec
            return self._msg("escalate", t_rec, n_sz_luts, n_luts_group)
        if self.active and t_rec - self.last_update >= self.update_s:
            self.last_update = t_rec
            return self._msg("update", t_rec, n_sz_luts, n_luts_group)
        return None

    def button(self, t_rec: float) -> dict:
        self.aware = True
        return {"event": "button", "bed": self.bed, "title": f"Patient button - {self.bed}",
                "body": "The patient pressed the button (aware enough to press it)." if self.active
                else "The patient pressed the button (no alarm on)."}

    def cluster(self, t_rec: float) -> tuple[int, str]:
        n = sum(1 for t in self.starts if t_rec - t <= 3600)
        nth = {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")
        return n, (f"{nth} alarm in the last hour" + (" (cluster)" if n >= 2 else ""))

    def _msg(self, ev: str, t_rec: float, n_sz: int, n_grp: int) -> dict:
        s = self.signs()
        d = t_rec - self.t0
        level = "emergency" if d >= 300 else "long" if d >= 120 else "alarm"
        n1h, ctext = self.cluster(t_rec)
        if ev == "escalate" and level == "emergency":
            title = f"EMERGENCY: seizure alarm over {int(d // 60)} min - {self.bed}"
            head = ("Alarm on for 5 min or more (the seizure began before the alarm). Treat as an emergency "
                    "(status epilepticus time point, ILAE 2015) and follow the patient's rescue plan.\n")
        elif ev == "escalate":
            title = f"Long seizure alarm (over 2 min) - {self.bed}"
            head = "Alarm on for 2 min. Be ready to start the emergency plan at 5 min.\n"
        else:
            title = f"SEIZURE ALARM - {self.bed}" if ev == "start" else f"Seizure alarm ongoing ({d:.0f} s) - {self.bed}"
            head = ""
        if s["danger"]:
            head = "!! " + "; ".join(s["danger"]) + "\n" + head
        body = (head + f"Detector: {n_sz} of {n_grp} seizure units active; alarm for {d:.0f} s; {ctext}\n"
                f"1 Heart rate: {s['hr_text']}\n2 Movement: {s['mov_text']}\n3 Muscle (EMG): {s['emg_text']}\n"
                f"4 Brain (EEG): {s['eeg_text']}\n5 Pattern hint: {s['hint']}\n"
                f"Patient button: {'pressed' if self.aware else 'not pressed'}. Sensors: {s['sensors']}.\n"
                "Measured signs for the doctor, not a diagnosis.")
        return {"event": ev, "bed": self.bed, "dur_s": round(d), "conf": f"{n_sz}/{n_grp}", "aware": self.aware,
                "level": level, "alarms_1h": n1h, "cluster": ctext, "title": title, "body": body, **s}


class Esp32Link:
    """The ESP32's USB serial port on the board (/dev/ttyUSB* or /dev/ttyACM*), 115200 baud, one JSON per line.
    Opened once and kept open (opening it may reset the ESP32, which then reconnects to Wi-Fi in a few seconds)."""

    def __init__(self, port: str = "auto"):
        self.fd, self.port, self.sent, self.error = None, None, 0, ""
        if port == "off":
            return
        cands = [port] if port != "auto" else sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
        for p in cands:
            try:
                fd = os.open(p, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                a = termios.tcgetattr(fd)
                a[0] = 0                                             # iflag: raw
                a[1] = 0                                             # oflag: raw
                a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag: 8N1, no HUPCL
                a[3] = 0                                             # lflag: raw
                a[4] = a[5] = termios.B115200
                termios.tcsetattr(fd, termios.TCSANOW, a)
                self.fd, self.port = fd, p
                break
            except OSError as e:
                self.error = f"{p}: {e}"
        if self.fd is None and not self.error:
            self.error = "no /dev/ttyUSB* or /dev/ttyACM* (ESP32 not plugged into the board's USB?)"

    @property
    def ok(self) -> bool:
        return self.fd is not None

    def read_lines(self) -> list[dict]:
        """Messages coming back from the ESP32 (the doctor's acknowledgement); its debug lines start with '#'."""
        if self.fd is None:
            return []
        try:
            self._rx = getattr(self, "_rx", b"") + os.read(self.fd, 4096)
        except (BlockingIOError, OSError):
            return []
        out = []
        while b"\n" in self._rx:
            line, self._rx = self._rx.split(b"\n", 1)
            line = line.strip()
            if line.startswith(b"{"):
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
        return out

    def send(self, msg: dict) -> bool:
        if self.fd is None:
            return False
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode()
        try:
            t_end = time.monotonic() + 1.0
            while data and time.monotonic() < t_end:
                try:
                    n = os.write(self.fd, data)
                    data = data[n:]
                except BlockingIOError:
                    time.sleep(0.005)
            self.sent += 1
            return not data
        except OSError as e:
            self.error = str(e)
            return False


if __name__ == "__main__":       # test the chain board -> ESP32 -> phone with a made-up alarm (clearly labelled)
    import argparse
    ap = argparse.ArgumentParser(description="Send a TEST alarm to the ESP32 (phone notification and web page)")
    ap.add_argument("--port", default="auto")
    ap.add_argument("--bed", default="Bed 1")
    a = ap.parse_args()
    link = Esp32Link(a.port)
    if not link.ok:
        raise SystemExit(f"ESP32 not found: {link.error}")
    print(f"ESP32 on {link.port}; waiting 3 s (opening the port may reset it)")
    time.sleep(3.0)
    common = {"bed": a.bed, "conf": "15/25", "aware": False, "sensors": "EEG ECG EMG ACC",
              "hr_text": "72 -> 118 bpm (+64 %), fast", "mov_text": "strong movement (x4.8 vs before)",
              "emg_text": "increased (x2.1 vs before)", "eeg_text": "strong change (x2.6 vs before), mostly slow waves",
              "hint": "motor pattern likely (strong movement)"}
    body = ("TEST MESSAGE - no patient.\n1 Heart rate: 72 -> 118 bpm (+64 %), fast\n2 Movement: strong movement (x4.8)\n"
            "3 Muscle (EMG): increased (x2.1)\n4 Brain (EEG): strong change, slow waves\n5 Pattern hint: motor pattern likely")
    link.send({"event": "start", "dur_s": 0, "level": "alarm", "alarms_1h": 2,
               "cluster": "2nd alarm in the last hour (cluster)", "danger": [],
               "title": f"TEST seizure alarm - {a.bed}", "body": body, **common})
    print("sent: TEST alarm start; the phone should ring now (tap 'On my way' to acknowledge)")
    time.sleep(15)
    link.send({"event": "escalate", "dur_s": 300, "level": "emergency", "alarms_1h": 2,
               "cluster": "2nd alarm in the last hour (cluster)",
               "danger": ["very fast heart rate (156 bpm)"],
               "title": f"TEST EMERGENCY: seizure alarm over 5 min - {a.bed}",
               "body": "TEST MESSAGE - no patient.\n!! very fast heart rate (156 bpm)\nAlarm on for 5 min or more. "
                       "Treat as an emergency and follow the patient's rescue plan.", **common})
    print("sent: TEST emergency escalation (5 min)")
    for _ in range(30):
        for m in link.read_lines():
            if m.get("event") == "ack":
                print(f"ACK received from the ESP32: the doctor is on the way ({m.get('time', '')})")
        time.sleep(0.5)
    link.send({"event": "end", "dur_s": 330, "level": "alarm", "danger": [], "title": f"TEST alarm ended - {a.bed}",
               "body": "TEST MESSAGE - no patient. Alarm ended after 330 s.", **common})
    print("sent: TEST alarm end")
