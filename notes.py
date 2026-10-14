import math

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def freq_to_note(freq):
    """Convert a frequency in Hz to the nearest note name, e.g. 440 -> 'A4'."""
    midi = round(69 + 12 * math.log2(freq / 440))
    name = NOTE_NAMES[midi % 12]
    octave = midi // 12 - 1
    return f"{name}{octave}"

if __name__ == "__main__":
    for f in [440, 261.63, 82.41, 329.63]:
        print(f, "Hz ->", freq_to_note(f))