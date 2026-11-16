"""Sweep grids of Phase 1 (MS_SPEC.md 1.2 step 5), fixed before the sweeps run.

A job = {"name", "seed", "impair": {modality: Impairment kwargs}}; one parameter changes at a time, everything else
clean. Units: biopotentials (eeg, ecg, emg) in uV, white_density in uV/sqrt(Hz); motion in input LSBs (2^-12 g).
Noise levels are given as rms over 0.5-100 Hz (density = rms / sqrt(99.5 Hz)), the band the front end analyses.
Deterministic impairments (q, C, gain, offset, filters) need one seed; random ones (noise, drift, mains phase) use
the seeds passed on the command line.
"""
from __future__ import annotations

import math

BAND_HZ = 100.0 - 0.5
BIO_LSB = [0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256]          # q, uV (C = 8192 uV: 15 down to 6 bits)
BIO_CLIP = [4096, 2048, 1024, 512, 256]                     # C, uV, at q = 0.25 uV
BIO_NOISE = [0.25, 0.5, 1, 2, 4, 8, 16]                     # uV rms in 0.5-100 Hz
PINK_CORNER = [1, 3, 10, 30]                                # Hz, white part 1 uV rms
GAIN = [-0.5, -0.2, -0.1, -0.05, 0.05, 0.1, 0.2, 0.5]
OFFSET_FRAC = [0.1, 0.3, 0.6, 0.9]                          # of C = 8192 uV, DC-coupled
DRIFT = [10, 100, 1000]                                     # uV rms, tau 64 s
MAINS_50 = [1, 10, 100, 1000]                               # uV peak at 50 Hz
MAINS_250 = [1, 10, 100]                                    # uV peak at 250 Hz (aliases to 6 Hz), no anti-alias filter
HP = [0.05, 0.1, 0.3, 0.5, 1.0]                             # Hz, 2nd-order Butterworth (AC-coupled front end)
LP = [100, 70, 50, 40, 30]                                  # Hz, 2nd-order Butterworth
MOV_LSB = [2, 4, 8, 16, 32, 64, 128, 256]                   # input LSBs (2^-12 g each)
MOV_NOISE = [1, 2, 4, 8, 16, 32]                            # LSB rms over 0-12.5 Hz
GAUSS_AB_UVRMS = 2.0     # EEG level for the generator A/B; to be moved to the level nearest the EEG noise limit


def _job(name, seed, **impair):
    return {"name": name, "seed": seed, "impair": impair}


def dens(rms_band: float) -> float:
    return rms_band / math.sqrt(BAND_HZ)


def bio(mod: str, seeds: list[int]) -> list[dict]:
    J = []
    s0 = seeds[:1]
    for q in BIO_LSB:
        J += [_job(f"{mod}_lsb_{q}uV", s, **{mod: {"lsb": float(q)}}) for s in s0]
    for c in BIO_CLIP:
        J += [_job(f"{mod}_clip_{c}uV", s, **{mod: {"clip": float(c)}}) for s in s0]
    for r in BIO_NOISE:
        J += [_job(f"{mod}_white_{r}uVrms", s, **{mod: {"white_density": dens(r)}}) for s in seeds]
    for fc in PINK_CORNER:
        J += [_job(f"{mod}_pink_{fc}Hz_white1uV", s, **{mod: {"white_density": dens(1.0), "pink_corner_hz": float(fc)}})
              for s in seeds[:3]]
    for g in GAIN:
        J += [_job(f"{mod}_gain_{g:+}", s, **{mod: {"gain_err": g}}) for s in s0]
    for f in OFFSET_FRAC:
        J += [_job(f"{mod}_offset_{f}C", s, **{mod: {"offset": f * 8192.0}}) for s in s0]
    for d in DRIFT:
        J += [_job(f"{mod}_drift_{d}uVrms", s, **{mod: {"drift_rms": float(d), "drift_tau_s": 64.0}}) for s in seeds[:3]]
    for a in MAINS_50:
        J += [_job(f"{mod}_mains50_{a}uV", s, **{mod: {"mains_peak": (float(a),)}}) for s in seeds[:3]]
    for a in MAINS_250:
        J += [_job(f"{mod}_mains250_{a}uV", s, **{mod: {"mains_peak": (0.0, 0.0, 0.0, 0.0, float(a))}}) for s in seeds[:3]]
    for f in HP:
        J += [_job(f"{mod}_hp_{f}Hz", s, **{mod: {"hp_hz": f}}) for s in s0]
    for f in LP:
        J += [_job(f"{mod}_lp_{f}Hz", s, **{mod: {"lp_hz": float(f)}}) for s in s0]
    return J


def mov(seeds: list[int]) -> list[dict]:
    J = []
    for q in MOV_LSB:
        J.append(_job(f"mov_lsb_{q}LSB", seeds[0], mov={"lsb": float(q)}))
    for r in MOV_NOISE:
        J += [_job(f"mov_white_{r}LSBrms", s, mov={"white_density": r / math.sqrt(12.5)}) for s in seeds]
    for g in GAIN:
        J.append(_job(f"mov_gain_{g:+}", seeds[0], mov={"gain_err": g}))
    return J


def get(grid: str, seeds: list[int]) -> list[dict]:
    if grid == "clean":
        return []
    if grid == "smoke":          # pipeline check: one deterministic and one random job on EEG
        return [_job("eeg_lsb_4uV", 0, eeg={"lsb": 4.0}),
                _job("eeg_white_1uVrms", 0, eeg={"white_density": dens(1.0)})]
    if grid == "gauss_ab":       # generator A/B (LOG L12): 64-uniform sum vs exact Gaussian, 5 seeds each
        r = GAUSS_AB_UVRMS
        return [j for s in range(5) for j in (
            _job(f"eeg_white_{r}uVrms", s, eeg={"white_density": dens(r)}),
            _job(f"eeg_white_{r}uVrms_refgauss", s, eeg={"white_density": dens(r), "reference_gaussian": True}))]
    if grid in ("eeg", "ecg", "emg"):
        return bio(grid, seeds)
    if grid == "mov":
        return mov(seeds)
    raise KeyError(f"unknown grid {grid}")
