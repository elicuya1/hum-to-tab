"""Turn detected notes into guitar tab, in every part of the neck where the riff fits.

A riff can usually be played in several places ("boxes"). For each possible hand
position we find the easiest fingering, then keep the positions that really fit.
"""
from dataclasses import dataclass

from notes import NOTE_NAMES

# Strings from top line of the tab (high e) to bottom (low E), with their open-string MIDI number
STRINGS = [("e", 64), ("B", 59), ("G", 55), ("D", 50), ("A", 45), ("E", 40)]
MAX_FRET = 22
HAND_SPAN = 4           # frets the hand covers without moving: lo to lo + 4
LEGATO = ("h", "p", "/", "\\")
LEGEND = {
    "h": "h = hammer-on", "p": "p = pull-off", "/": "/ = slide up", "\\": "\\ = slide down",
    "b": "b = bend (to the pitch of that fret)", "r": "r = release the bend", "~": "~ = vibrato",
}
INF = float("inf")


@dataclass
class Box:
    path: list          # (string index, fret) for each note
    low: int            # lowest fret used
    high: int           # highest fret used
    cost: float

    @property
    def label(self):
        return f"frets {self.low}-{self.high}" if self.low != self.high else f"fret {self.low}"


def note_to_midi(note):
    """'A4' -> 69"""
    name, octave = note[:-1], int(note[-1])
    return NOTE_NAMES.index(name) + 12 * (octave + 1)


def octave_shift(notes):
    """Move the whole riff up by octaves if it's too low for a guitar (keeps its shape)."""
    lowest = min(n.midi for n in notes)
    shift = 0
    while lowest + shift < 40:
        shift += 12
    return shift


def options(note, shift):
    """Every (string, fret) where this note can be played."""
    midi = note.midi + shift
    while midi > 64 + MAX_FRET:                 # too high: move down an octave
        midi -= 12
    spots = []
    for s, (_, open_note) in enumerate(STRINGS):
        fret = midi - open_note
        if 0 <= fret <= MAX_FRET:
            if note.bend and (fret == 0 or fret + note.bend > MAX_FRET):
                continue                        # you can't bend an open string
            spots.append((s, fret))
    if not spots:                               # bends at the very edge: just play the note
        spots = [(s, midi - o) for s, (_, o) in enumerate(STRINGS) if 0 <= midi - o <= MAX_FRET]
    return spots


def fingering(notes, shift, lo):
    """Easiest way to play the notes with the hand around frets lo..lo+HAND_SPAN.

    Works like a sat-nav finding the cheapest route: every note has a few possible spots,
    and moving between spots costs something (big jumps, changing strings, leaving the box).
    """
    hi = lo + HAND_SPAN

    def place_cost(fret):
        if fret == 0:
            return 0.5 if lo <= 1 else 3.0      # open strings belong to the open position
        if lo <= fret <= hi:
            return 0.0
        return 2.0 * (lo - fret if fret < lo else fret - hi)

    def move_cost(a, b, note):
        (s1, f1), (s2, f2) = a, b
        if note.technique in LEGATO and s1 != s2:
            return INF                          # hammer-ons, pull-offs and slides stay on one string
        if note.technique in ("/", "\\") and (f1 == 0 or f2 == 0):
            return INF                          # you can't slide from or to an open string
        if note.technique in ("h", "p") and abs(f1 - f2) > 5:
            return INF
        cost = 0.15 * abs(s1 - s2)
        if f1 and f2:
            cost += 0.3 * abs(f1 - f2)
        return cost

    spots = [options(n, shift) for n in notes]
    best = [{spot: (place_cost(spot[1]), None) for spot in spots[0]}]
    for i in range(1, len(notes)):
        layer = {}
        for spot in spots[i]:
            choices = [(cost + move_cost(prev, spot, notes[i]) + place_cost(spot[1]), prev)
                       for prev, (cost, _) in best[-1].items()]
            layer[spot] = min(choices)
        best.append(layer)
    end, (total, _) = min(best[-1].items(), key=lambda item: item[1][0])
    if total == INF:
        return None, INF
    path = [end]
    for i in range(len(notes) - 1, 0, -1):
        path.append(best[i][path[-1]][1])
    return path[::-1], total


def find_boxes(notes, max_boxes=4):
    """The different places on the neck the riff can be played, lowest first."""
    if not notes:
        return []
    shift = octave_shift(notes)
    candidates = []
    for lo in range(0, MAX_FRET - HAND_SPAN + 1):
        path, cost = fingering(notes, shift, lo)
        if path is None:
            continue
        if not all(f == 0 or lo - 1 <= f <= lo + HAND_SPAN + 1 for _, f in path):
            continue                            # notes outside the box: not really this box
        candidates.append(Box(path, 0, 0, cost))

    boxes = []
    for box in sorted(candidates, key=lambda b: (b.cost, b.low)):
        if any(box.path == other.path for other in boxes):
            continue
        centre = middle(box)
        if any(abs(centre - middle(other)) < 3 for other in boxes):
            continue
        boxes.append(box)
        if len(boxes) == max_boxes:
            break

    if not boxes:                               # riff too wide for one hand position
        path, cost = min((fingering(notes, shift, lo) for lo in range(0, MAX_FRET - HAND_SPAN + 1)),
                         key=lambda pc: pc[1])
        if path is None:
            return []
        frets = [f for _, f in path]
        boxes = [Box(path, min(frets), max(frets), cost)]
    for box in boxes:
        frets = [f for _, f in box.path]
        box.low, box.high = min(frets), max(frets)
    return sorted(boxes, key=middle)


def middle(box):
    fretted = [f for _, f in box.path if f > 0]
    return sum(fretted) / len(fretted) if fretted else 0


def render_tab(notes, path):
    """Draw ASCII tab, with technique symbols like 5h7, 7b9r7, 5/9 and 7~."""
    columns = []                                # [string, text] for each thing played
    for note, (string, fret) in zip(notes, path):
        text = str(fret)
        if note.bend:
            text += f"b{fret + note.bend}"
            if note.release_at is not None:
                text += f"r{fret}"
        if note.vibrato:
            text += "~"
        if note.technique in LEGATO and columns and columns[-1][0] == string:
            columns[-1][1] += note.technique + text     # e.g. "5" becomes "5h7"
        else:
            columns.append([string, text])
    lines = [name + "|-" for name, _ in STRINGS]
    for string, text in columns:
        for i in range(len(STRINGS)):
            lines[i] += (text if i == string else "-" * len(text)) + "-"
    return "\n".join(line + "|" for line in lines)


def legend(notes):
    """Explain only the symbols this tab uses."""
    used = {n.technique for n in notes if n.technique}
    if any(n.bend for n in notes):
        used.add("b")
    if any(n.release_at is not None for n in notes):
        used.add("r")
    if any(n.vibrato for n in notes):
        used.add("~")
    items = [LEGEND[k] for k in LEGEND if k in used]
    return "\n".join("   ".join(items[i:i + 3]) for i in range(0, len(items), 3))


def tab_text(notes):
    """Everything the app shows: the notes, each box's tab, and a legend."""
    if not notes:
        return "No notes found."
    parts = ["Notes: " + " ".join(n.name for n in notes)]
    boxes = find_boxes(notes)
    for i, box in enumerate(boxes, start=1):
        parts.append(f"Box {i} ({box.label})\n{render_tab(notes, box.path)}")
    key = legend(notes)
    if key:
        parts.append(key)
    return "\n\n".join(parts)


if __name__ == "__main__":
    import sys
    from detect import analyse
    print(tab_text(analyse(sys.argv[1] if len(sys.argv) > 1 else "test_melody.wav")))
