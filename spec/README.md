# spec/

Interface notes for Phase 2.

* `fixed_point.md`: one row per signal (raw samples, filter states, features, logs, moving averages,
  thermometer inputs, scores) with width, signedness, scale, rounding and saturation. Written in M3.
* Input facts already fixed by the M1 audit: EEG/ECG/EMG arrive as int16 at **256 Hz** (gain per file
  in the EDF header, about 0.04 uV/LSB for EEG); motion int16 at 25 Hz in units of g.
