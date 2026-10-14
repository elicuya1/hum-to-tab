"""Make test recordings where we know the right answer, so we can check the detector.

Creates three files:
  test_melody.wav        - clean beeps, one note after another
  test_articulations.wav - a guitar-like riff with hammer-ons, pull-offs, slides,
                           a bend and release, vibrato, slightly out of tune, with noise
  test_humming.wav       - a voice-like hum: smooth, wobbly, a bit flat
"""
import numpy as np
import soundfile as sf

SR = 22050                          # samples per second


def midi_to_hz(midi):
    return 440.0 * 2 ** ((np.asarray(midi) - 69) / 12)


def build(parts, detune=0.0, wobble=0.0, seed=0):
    """Turn a list of parts into a pitch curve and a loudness curve, one value per sample.

    Each part is a tuple:
      ("pick", midi, seconds)          new plucked note
      ("legato", midi, seconds)        instant pitch change, no new pluck (hammer-on / pull-off)
      ("glide", midi, glide_s, hold_s) smooth slide or bend to a new pitch, no new pluck
      ("vibrato", midi, seconds)       plucked note with vibrato
      ("hum", midi, seconds)           sung note: short dip in volume before it, then steady
      ("rest", seconds)                silence
    """
    rng = np.random.default_rng(seed)
    pitch, amp = [], []
    current, level = None, 0.0
    for part in parts:
        kind = part[0]
        if kind == "rest":
            n = int(part[1] * SR)
            pitch.append(np.full(n, np.nan)); amp.append(np.zeros(n))
            current, level = None, 0.0
            continue
        if kind == "glide":
            _, target, glide_s, hold_s = part
            ng, nh = int(glide_s * SR), int(hold_s * SR)
            curve = np.concatenate([np.linspace(current, target, ng), np.full(nh, float(target))])
            current = target
        else:
            _, current, seconds = part
            n = int(seconds * SR)
            curve = np.full(n, float(current))
            if kind == "vibrato":
                t = np.arange(n) / SR
                curve = curve + 0.35 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.15, 0, 1)
        n = len(curve)
        t = np.arange(n) / SR
        if kind in ("pick", "vibrato"):
            if amp and level > 0:                        # the pick briefly mutes the old note
                damp = min(int(0.015 * SR), len(amp[-1]))
                amp[-1][-damp:] *= np.linspace(1, 0.3, damp)
            level = 1.0                                  # pluck: loud, then dies away
        elif kind == "legato":
            level = level * 1.15                         # hammer-on adds a little energy
        if kind == "hum":
            env = np.full(n, 0.6)
            dip = min(int(0.06 * SR), n // 3)            # brief "d" between sung notes
            env[:dip] = np.linspace(0.05, 0.6, dip)
            level = 0.6
        else:
            env = level * np.exp(-t / 0.9)               # guitar-like decay
            level = env[-1]
        pitch.append(curve); amp.append(env)
    pitch, amp = np.concatenate(pitch), np.concatenate(amp)
    pitch = pitch + detune
    if wobble:
        drift = np.cumsum(rng.normal(0, 1, len(pitch)))
        drift = np.convolve(drift, np.ones(2000) / 2000, mode="same")
        drift = drift - drift.mean()
        pitch = pitch + wobble * drift / (np.nanstd(drift) + 1e-9)
    return pitch, amp


def synthesize(pitch, amp, harmonics=5, noise_db=-40, seed=0):
    """Turn pitch + loudness curves into sound with a few harmonics, like a real instrument."""
    rng = np.random.default_rng(seed)
    freq = np.nan_to_num(midi_to_hz(np.nan_to_num(pitch, nan=60)) * ~np.isnan(pitch))
    phase = 2 * np.pi * np.cumsum(freq) / SR
    tone = sum(np.sin(k * phase) / k ** 1.2 for k in range(1, harmonics + 1))
    # short fades so each pluck starts cleanly instead of clicking
    smooth = np.convolve(amp, np.ones(64) / 64, mode="same")
    audio = 0.25 * tone * smooth
    audio += 10 ** (noise_db / 20) * rng.normal(0, 1, len(audio))
    return (audio / np.max(np.abs(audio)) * 0.8).astype(np.float32)


def clean_melody():
    melody = [52, 55, 57, 59, 57, 55, 52]            # E3 G3 A3 B3 A3 G3 E3
    t = np.arange(int(SR * 0.5)) / SR
    fade = np.minimum(1, np.minimum(t, t[-1] - t) / 0.02)    # 20 ms fade in and out per beep
    return np.concatenate([0.5 * fade * np.sin(2 * np.pi * midi_to_hz(m) * t)
                           for m in melody]).astype(np.float32)


# A minor riff. The comments say what the detector should find.
ARTICULATION_RIFF = [
    ("pick", 57, 0.40),                # A3 picked
    ("pick", 60, 0.30),                # C4 picked
    ("legato", 62, 0.30),              #   hammer-on to D4
    ("legato", 60, 0.35),              #   pull-off back to C4
    ("pick", 57, 0.35),                # A3 picked
    ("glide", 62, 0.12, 0.45),         #   slide up to D4
    ("pick", 62, 0.30),                # D4 picked
    ("glide", 64, 0.15, 0.40),         #   bend up a whole step (sounds E4)
    ("glide", 62, 0.15, 0.35),         #   release back to D4
    ("vibrato", 57, 0.90),             # A3 with vibrato
    ("pick", 60, 0.35),                # C4 picked
    ("glide", 57, 0.12, 0.45),         #   slide down to A3
    ("pick", 52, 0.30),                # E3 picked
    ("pick", 52, 0.40),                # E3 picked again
    ("rest", 0.2),
]

HUM_TUNE = [("hum", m, d) for m, d in [
    (48, 0.45), (50, 0.45), (52, 0.45), (48, 0.45),     # C3 D3 E3 C3
    (48, 0.45), (50, 0.45), (52, 0.45), (48, 0.45),     # C3 D3 E3 C3
    (52, 0.45), (53, 0.45), (55, 0.90),                 # E3 F3 G3
]] + [("rest", 0.2)]


if __name__ == "__main__":
    sf.write("test_melody.wav", clean_melody(), SR)
    sf.write("test_articulations.wav",
             synthesize(*build(ARTICULATION_RIFF, detune=0.3)), SR)
    sf.write("test_humming.wav",
             synthesize(*build(HUM_TUNE, detune=-0.25, wobble=0.12, seed=3), harmonics=3, noise_db=-35), SR)
    print("Saved test_melody.wav, test_articulations.wav and test_humming.wav")
