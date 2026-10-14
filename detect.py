import numpy as np
import librosa
from notes import freq_to_note

def detect_notes(path, min_duration=0.1):
    """Return a list of (note, start_time, duration) found in an audio file."""
    y, sr = librosa.load(path)

    # Estimate the pitch in each tiny slice ("frame") of the audio
    f0, voiced, _ = librosa.pyin(
        y, sr=sr,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C6"),
    )
    times = librosa.times_like(f0, sr=sr)

    # Group consecutive frames with the same note into one note
    notes = []
    current, start = None, 0.0
    for t, freq, is_voiced in zip(times, f0, voiced):
        note = freq_to_note(freq) if is_voiced and not np.isnan(freq) else None
        if note != current:
            if current is not None and t - start >= min_duration:
                notes.append((current, round(start, 2), round(t - start, 2)))
            current, start = note, t
    if current is not None and times[-1] - start >= min_duration:
        notes.append((current, round(start, 2), round(times[-1] - start, 2)))
    return notes

if __name__ == "__main__":
    for note, start, dur in detect_notes("test_melody.wav"):
        print(f"{note:4} at {start:5.2f}s for {dur:.2f}s")