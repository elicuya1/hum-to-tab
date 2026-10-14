from notes import NOTE_NAMES
from detect import detect_notes

# Strings from top line of the tab (high e) to bottom (low E), with their open-string MIDI number
STRINGS = [("e", 64), ("B", 59), ("G", 55), ("D", 50), ("A", 45), ("E", 40)]
MAX_FRET = 20

def note_to_midi(note):
    """'A4' -> 69"""
    name, octave = note[:-1], int(note[-1])
    return NOTE_NAMES.index(name) + 12 * (octave + 1)

def positions(midi):
    """All (string, fret) spots where this note can be played."""
    return [(i, midi - open_note)
            for i, (_, open_note) in enumerate(STRINGS)
            if 0 <= midi - open_note <= MAX_FRET]

def choose_frets(notes):
    """Pick one spot per note, staying close to the previous fret so it's easy to play."""
    chosen = []
    last_fret = 0
    for note in notes:
        midi = note_to_midi(note)
        while midi < 40:                    # too low for guitar: move up an octave
            midi += 12
        while midi > 64 + MAX_FRET:         # too high: move down an octave
            midi -= 12
        string, fret = min(positions(midi), key=lambda p: abs(p[1] - last_fret))
        chosen.append((string, fret))
        last_fret = fret
    return chosen

def render_tab(chosen):
    """Turn (string, fret) pairs into ASCII tab."""
    lines = [name + "|-" for name, _ in STRINGS]
    for string, fret in chosen:
        width = len(str(fret))              # fret 12 takes 2 characters, fret 3 takes 1
        for i in range(len(STRINGS)):
            lines[i] += (str(fret) if i == string else "-" * width) + "-"
    return "\n".join(line + "|" for line in lines)

if __name__ == "__main__":
    notes = [note for note, start, dur in detect_notes("test_melody.wav")]
    print("Notes:", notes)
    print(render_tab(choose_frets(notes)))