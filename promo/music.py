"""Hoard's looping music track (issue #291), written out note by note and synthesised here: no samples, no
recordings, no diffusion or any other generated sound. 16 bars at 96 beats a minute (40 seconds): soft electric
piano chords, a round bass, light drums and a bell melody, in D minor's relative F major. What rings on past the
last beat is added back onto the first, so the track loops with no seam: any video can use as much of it as it needs.

    python3 promo/music.py [OUT_FOLDER]     writes hoard-loop.wav (and .m4a and .ogg, with ffmpeg) into promo/out/

Standard library only (and ffmpeg, for the smaller copies).
"""
from __future__ import annotations

import array
import math
import random
import shutil
import subprocess
import sys
import wave
from pathlib import Path

RATE = 44100
BPM = 96
BEAT = 60 / BPM
BARS = 16
LOOP = BARS * 4 * BEAT   # seconds

A4 = 440.0
NAMES = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}


def hz(note: str) -> float:
    """A note's frequency: "F#3", "Bb4", "C5"."""
    name, rest = note[0], note[1:]
    shift = 0
    while rest and rest[0] in "#b":
        shift += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return A4 * 2 ** ((NAMES[name] + shift + (int(rest) - 4) * 12) / 12)


# two bars for each chord: its notes for the piano, its root for the bass, and the bell's tune over it
# (beat, note, beats long)
CHORDS = [
    (("F3", "A3", "C4", "E4"), "F2", [(0, "C5", 1), (1, "A4", 0.5), (1.5, "C5", 0.5), (2, "E5", 1.5), (4.5, "D5", 0.5), (5, "C5", 1), (6, "A4", 2)]),
    (("E3", "G3", "B3", "D4"), "E2", [(0, "B4", 1), (1.5, "D5", 0.5), (2, "E5", 1), (3, "G5", 1), (4, "E5", 1), (5, "D5", 1), (6, "B4", 2)]),
    (("D3", "F3", "A3", "C4", "E4"), "D2", [(0, "A4", 1.5), (1.5, "C5", 0.5), (2, "D5", 1), (3, "F5", 1), (4, "E5", 1.5), (5.5, "D5", 0.5), (6, "C5", 2)]),
    (("C3", "E3", "G3", "B3"), "C2", [(0, "G4", 1), (1, "B4", 1), (2, "C5", 1), (3, "E5", 1), (4.5, "D5", 0.5), (5, "B4", 1), (6, "G4", 2)]),
    (("Bb2", "D3", "F3", "A3"), "Bb1", [(0, "F5", 1), (1, "D5", 0.5), (1.5, "F5", 0.5), (2, "A5", 1.5), (4, "G5", 1), (5, "F5", 1), (6, "D5", 2)]),
    (("A2", "C3", "E3", "G3"), "A1", [(0, "E5", 1), (1.5, "G5", 0.5), (2, "A5", 1), (3, "G5", 1), (4, "E5", 1), (5, "C5", 1), (6, "A4", 2)]),
    (("G2", "Bb2", "D3", "F3"), "G1", [(0, "D5", 1), (1, "F5", 1), (2, "G5", 1), (3, "Bb5", 1), (4, "A5", 1), (5, "G5", 1), (6, "F5", 2)]),
    (("C3", "E3", "G3", "A3"), "C2", [(0, "E5", 1.5), (1.5, "G5", 0.5), (2, "A5", 1), (3, "G5", 1), (4, "E5", 2), (6, "C5", 1), (7, "D5", 1)]),
]


class Track:
    """The loop, being written: two channels of the loop's length, with what rings past its end added at its start."""

    def __init__(self, seconds: float = LOOP):
        self.n = round(seconds * RATE)
        self.left = [0.0] * self.n
        self.right = [0.0] * self.n

    def add(self, start: float, samples: list[float], gain: float = 1.0, pan: float = 0.0) -> None:
        """Mix samples in from start (seconds), panned (-1 left to 1 right), wrapping round the loop's end."""
        at = round(start * RATE)
        lg, rg = gain * math.cos((pan + 1) * math.pi / 4), gain * math.sin((pan + 1) * math.pi / 4)
        left, right, n = self.left, self.right, self.n
        for i, s in enumerate(samples):
            j = (at + i) % n
            left[j] += s * lg
            right[j] += s * rg


def envelope(i: int, n: int, attack: float, decay: float) -> float:
    """A note's loudness at sample i of n: a quick rise, then a fall, and a short fade at its very end."""
    t = i / RATE
    rise = min(1.0, t / attack) if attack else 1.0
    tail = min(1.0, (n - i) / (0.02 * RATE))
    return rise * math.exp(-t / decay) * tail


def piano(f: float, seconds: float) -> list[float]:
    """A soft electric piano note: a sine with a bell-like second partial that fades first."""
    n, w = round(seconds * RATE), 2 * math.pi * f / RATE
    return [envelope(i, n, 0.004, 1.6) * (math.sin(w * i) + 0.25 * math.sin(2 * w * i) * math.exp(-i / (0.25 * RATE))
                                           + 0.08 * math.sin(3 * w * i) * math.exp(-i / (0.12 * RATE))) for i in range(n)]


def bass(f: float, seconds: float) -> list[float]:
    """A round bass note: a sine with a little of its octave, plucked."""
    n, w = round(seconds * RATE), 2 * math.pi * f / RATE
    return [envelope(i, n, 0.006, 0.9) * (math.sin(w * i) + 0.3 * math.sin(2 * w * i)) for i in range(n)]


def bell(f: float, seconds: float) -> list[float]:
    """The melody's bell: a sine, frequency-modulated a little, ringing on."""
    n, w = round(seconds * RATE), 2 * math.pi * f / RATE
    return [envelope(i, n, 0.002, 0.7) * math.sin(w * i + 1.2 * math.exp(-i / (0.18 * RATE)) * math.sin(3.5 * w * i))
            for i in range(n)]


def kick() -> list[float]:
    """A soft kick: a sine falling in pitch."""
    n, phase, out = round(0.35 * RATE), 0.0, []
    for i in range(n):
        t = i / RATE
        phase += 2 * math.pi * (48 + 90 * math.exp(-t / 0.035)) / RATE
        out.append(math.sin(phase) * math.exp(-t / 0.13))
    return out


def noise_hit(seconds: float, decay: float, bright: float, seed: int) -> list[float]:
    """A burst of noise (a snare or a hat), the same every time (seeded), made brighter by taking its differences."""
    rnd = random.Random(seed)
    n, out, last = round(seconds * RATE), [], 0.0
    for i in range(n):
        x = rnd.uniform(-1, 1)
        y = x - bright * last   # (a simple high-pass: brighter as bright nears 1)
        last = x
        out.append(y * math.exp(-i / (decay * RATE)))
    return out


def render(bars: int = BARS) -> Track:
    """The loop (or its first bars, for a quick check), every note in its place."""
    track = Track(bars * 4 * BEAT)
    hat, snare, thump = noise_hit(0.06, 0.012, 0.95, 7), noise_hit(0.25, 0.06, 0.6, 11), kick()
    for bar in range(bars):
        chord, root, tune = CHORDS[(bar // 2) % len(CHORDS)]
        start = bar * 4 * BEAT
        first = bar % 2 == 0
        if first:   # the chord, spread a little, on each half of its two bars; the bell's tune over them
            for k, note in enumerate(chord):
                for half in (0, 4):
                    track.add(start + half * BEAT + k * 0.012, piano(hz(note), 3.6 * BEAT), 0.10, (k - 2) * 0.25)
            for beat, note, beats in tune:
                track.add(start + beat * BEAT, bell(hz(note), beats * BEAT + 0.8), 0.075, 0.2)
        for beat, length in ((0, 1.5), (1.5, 0.5), (2, 1), (3, 0.75), (3.75, 0.25)):   # the bass's pattern
            note = root if beat != 3.75 else root[:-1] + str(int(root[-1]) + 1)
            track.add(start + beat * BEAT, bass(hz(note), length * BEAT), 0.20)
        for beat in (0, 2) + ((2.5,) if bar % 4 == 3 else ()):   # drums
            track.add(start + beat * BEAT, thump, 0.38)
        for beat in (1, 3):
            track.add(start + beat * BEAT, snare, 0.09, 0.1)
        for eighth in range(8):
            swing = 0.06 * BEAT if eighth % 2 else 0.0
            track.add(start + eighth * BEAT / 2 + swing, hat, 0.028 if eighth % 2 else 0.045, -0.3)   # (soft: under the rest)
    return track


def master(track: Track) -> tuple[list[float], list[float]]:
    """The two channels, gently limited and brought up to just under full."""
    peak = max(max(map(abs, track.left)), max(map(abs, track.right))) or 1.0
    gain = 1.15 / peak   # (a little warmth from tanh, and room left: about -14 LUFS, as streaming sites play)
    return [math.tanh(s * gain) * 0.72 for s in track.left], [math.tanh(s * gain) * 0.72 for s in track.right]


def seam(left: list[float]) -> float:
    """How big a jump the loop makes from its last sample to its first, against its usual step (well under 1:
    no click)."""
    steps = [abs(left[i + 1] - left[i]) for i in range(0, len(left) - 1, 97)]
    usual = sorted(steps)[int(len(steps) * 0.99)] or 1.0
    return abs(left[0] - left[-1]) / usual


def write_wav(path: Path, left: list[float], right: list[float]) -> None:
    """A 16-bit stereo WAV."""
    data = array.array("h", (max(-32767, min(32767, round(s * 32767))) for pair in zip(left, right) for s in pair))
    if sys.byteorder == "big":
        data.byteswap()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def main(argv: list[str]) -> int:
    """Write the loop, and its smaller copies."""
    out = Path(argv[0]) if argv else Path(__file__).resolve().parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    left, right = master(render())
    print(f"The seam: {seam(left):.3f} of a usual step (no click under 1)")
    wav = out / "hoard-loop.wav"
    write_wav(wav, left, right)
    if shutil.which("ffmpeg"):
        for name, codec in (("hoard-loop.m4a", ["-c:a", "aac", "-b:a", "192k"]), ("hoard-loop.ogg", ["-c:a", "libvorbis", "-q:a", "6"])):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), *codec, str(out / name)], check=True)
    print(f"{wav} ({LOOP:.1f} s, {BPM} bpm)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
