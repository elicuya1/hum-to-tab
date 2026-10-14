"""Play the detected notes back, including slides, bends and hammer-ons, so you can check them by ear."""
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

SAMPLE_RATE = 22050
PLAYBACK_FILE = os.path.join(tempfile.gettempdir(), "hum_to_tab_playback.wav")
GLIDE = 0.08                    # seconds a bend or release takes when played back


def notes_to_audio(notes):
    """Build a sound from the notes: a pitch curve and a volume curve, turned into a tone."""
    if not notes:
        return np.zeros(0, dtype=np.float32)
    total = int((max(n.end for n in notes) + 0.1) * SAMPLE_RATE)
    pitch = np.full(total, np.nan)
    volume = np.zeros(total)
    phrases = []                                 # (start, end) sample of each picked group of notes

    for i, note in enumerate(notes):
        a = int(note.start * SAMPLE_RATE)
        b = min(int(note.end * SAMPLE_RATE), total)
        if b <= a:
            continue
        curve = np.full(b - a, float(note.midi))
        if note.bend:
            curve = bend_curve(curve, note)
        if note.vibrato:                         # wobble 5.5 times a second
            t = np.arange(b - a) / SAMPLE_RATE
            curve += 0.3 * np.sin(2 * np.pi * 5.5 * t)
        legato = note.technique and i > 0 and phrases
        if legato:
            # no new pick: fill the gap from the previous note, sliding if it's a slide
            prev_end = phrases[-1][1]
            if prev_end < a:
                before = pitch[prev_end - 1] if prev_end > 0 else note.midi
                if note.technique in ("/", "\\"):
                    pitch[prev_end:a] = np.linspace(before, note.midi, a - prev_end)
                else:
                    pitch[prev_end:a] = before
            phrases[-1] = (phrases[-1][0], b)
        else:
            phrases.append((a, b))
        pitch[a:b] = curve

    for start, end in phrases:                   # each pick starts loud and dies away
        t = np.arange(end - start) / SAMPLE_RATE
        env = 0.3 * np.exp(-t / 1.5)
        fade = min(int(0.01 * SAMPLE_RATE), (end - start) // 2)
        if fade:
            env[:fade] *= np.linspace(0, 1, fade)
            env[-fade:] *= np.linspace(1, 0, fade)
        volume[start:end] = env

    freq = np.where(np.isnan(pitch), 0.0, 440.0 * 2 ** ((np.nan_to_num(pitch, nan=69) - 69) / 12))
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    tone = np.sin(phase) + 0.3 * np.sin(2 * phase)          # a touch of overtone sounds less beepy
    return (volume * tone / 1.3).astype(np.float32)


def bend_curve(curve, note):
    """Pitch goes up by note.bend semitones at bend_at, and back down at release_at."""
    n = len(curve)
    up = min(int(note.bend_at * SAMPLE_RATE), n)
    glide = int(GLIDE * SAMPLE_RATE)
    target = note.midi + note.bend
    curve[up:] = target
    curve[up:min(up + glide, n)] = np.linspace(note.midi, target, glide)[:max(0, min(glide, n - up))]
    if note.release_at is not None:
        down = min(int(note.release_at * SAMPLE_RATE), n)
        curve[down:] = note.midi
        curve[down:min(down + glide, n)] = np.linspace(target, note.midi, glide)[:max(0, min(glide, n - down))]
    return curve


def stop():
    """Stop anything that's currently playing."""
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(None, 0)
    else:
        import sounddevice as sd
        sd.stop()


def play(audio):
    """Play a sound in the background without freezing the window."""
    stop()
    if sys.platform == "win32":
        # Windows' own player is the most reliable from inside a tkinter app
        import winsound
        sf.write(PLAYBACK_FILE, audio, SAMPLE_RATE, subtype="PCM_16")
        winsound.PlaySound(PLAYBACK_FILE, winsound.SND_FILENAME | winsound.SND_ASYNC)
    else:
        import sounddevice as sd
        sd.play(audio, SAMPLE_RATE)
