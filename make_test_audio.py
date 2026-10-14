import numpy as np
import soundfile as sf
import librosa

melody = ["E3", "G3", "A3", "B3", "A3", "G3", "E3"]
sr = 22050          # samples per second
note_len = 0.5      # seconds per note

t = np.linspace(0, note_len, int(sr * note_len), endpoint=False)
audio = np.concatenate([0.5 * np.sin(2 * np.pi * librosa.note_to_hz(n) * t) for n in melody])

sf.write("test_melody.wav", audio, sr)
print("Saved test_melody.wav")
