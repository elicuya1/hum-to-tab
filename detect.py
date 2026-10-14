"""Find the notes in a recording of a single melody, and how each one is played.

The steps:
  1. Track the pitch of the sound about 86 times a second (librosa's pYIN).
  2. Correct for singing or tuning that is a little sharp or flat overall.
  3. Smooth out tiny wobbles.
  4. Find "plateaus": stretches where the pitch sits steadily on one note.
  5. Find "attacks": moments where the sound gets suddenly louder (a new pick or a new sung note).
  6. Look at what happens between plateaus to work out the technique:
       new attack                  -> a separately picked note
       instant jump, no attack     -> hammer-on (up) or pull-off (down), if 5 frets or less
       smooth glide up 1-2 notes   -> bend (and a glide back down is the release)
       any other smooth glide      -> slide
  7. Check each note for vibrato (a regular wobble around the note).
"""
from dataclasses import dataclass

import numpy as np
import librosa
from scipy.ndimage import median_filter

from notes import NOTE_NAMES

SR = 22050          # we resample everything to this
HOP = 256           # samples between pitch measurements (about 11.6 ms)
FRAME = 1024        # samples per pitch measurement (about 46 ms)

# Tuning knobs. Make these bigger or smaller if real recordings come out wrong.
STABLE_DEVIATION = 0.4    # how far from a note (in semitones) still counts as "on" it
STABLE_SLOPE = 0.12       # how fast the pitch may move (semitones per frame) and still be steady
MIN_NOTE_FRAMES = 5       # shortest note we keep (about 60 ms)
ATTACK_DB = 3.0           # how much louder (in dB) the sound must get to count as a new pick
GLIDE_FRAMES = 4          # a change passing through at least this many in-between frames is a glide
MAX_HAMMER = 5            # hammer-ons and pull-offs bigger than this (in frets) are really new picks
MAX_BEND = 2              # glides up by this many semitones or fewer count as bends


@dataclass
class Note:
    midi: int                       # MIDI note number, e.g. 69 = A4
    start: float                    # seconds
    duration: float                 # seconds
    technique: str = ""             # how you get here from the previous note without picking:
                                    #   "h" hammer-on, "p" pull-off, "/" slide up, "\\" slide down
    bend: int = 0                   # how many semitones the note is bent up (0 = no bend)
    bend_at: float = 0.0            # seconds after the start that the bend happens
    release_at: float | None = None # seconds after the start that the bend is released
    vibrato: bool = False

    @property
    def name(self):
        return f"{NOTE_NAMES[self.midi % 12]}{self.midi // 12 - 1}"

    @property
    def end(self):
        return self.start + self.duration


# --- Small helpers ---

def frames_to_time(frame):
    return frame * HOP / SR


def runs(mask):
    """Start and end (exclusive) of each stretch where mask is True."""
    padded = np.concatenate([[False], mask, [False]]).astype(int)
    edges = np.flatnonzero(np.diff(padded))
    return list(zip(edges[::2], edges[1::2]))


# --- Steps 1-3: pitch ---

def pitch_track(y):
    """Pitch of each frame as a MIDI number (with decimals). NaN where there's no note."""
    f0, voiced, prob = librosa.pyin(
        y, sr=SR, frame_length=FRAME, hop_length=HOP, fill_na=None,
        fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
    )
    n = len(f0)
    rms = librosa.feature.rms(y=y, frame_length=FRAME, hop_length=HOP)[0][:n]
    db = 20 * np.log10(rms + 1e-9)
    # pYIN sometimes gives up on quieter notes; keep its guess when it's fairly sure and
    # the sound is still reasonably loud. Very quiet frames are background noise.
    keep = (voiced & (db > db.max() - 35)) | ((prob > 0.1) & (db > db.max() - 20))
    midi = librosa.hz_to_midi(f0)
    midi[~keep | (midi < 37.5)] = np.nan               # below D2 is almost always noise
    for s, e in runs(~np.isnan(midi)):          # drop blips of sound shorter than 3 frames
        if e - s < 3:
            midi[s:e] = np.nan
    return midi


def tuning_offset(midi):
    """How sharp (+) or flat (-) the whole recording is, in semitones (between -0.5 and 0.5)."""
    m = midi[~np.isnan(midi)]
    if len(m) == 0:
        return 0.0
    steady = np.abs(np.gradient(m)) < 0.05      # ignore frames where the pitch is moving
    if steady.sum() > 10:
        m = m[steady]
    # first guess: average on a circle, so being +0.49 and -0.49 off count as nearly the same
    angles = 2 * np.pi * (m - np.round(m))
    guess = np.angle(np.mean(np.exp(1j * angles))) / (2 * np.pi)
    # then take the median distance from that guess, which ignores stray frames
    off_by = (m - guess + 0.5) % 1 - 0.5
    offset = guess + np.median(off_by)
    return float((offset + 0.5) % 1 - 0.5)


def smooth(midi, size=5):
    """Median-smooth each stretch of sound separately (keeps sudden jumps sharp)."""
    out = midi.copy()
    for s, e in runs(~np.isnan(midi)):
        out[s:e] = median_filter(midi[s:e], size=min(size, e - s), mode="nearest")
    return out


# --- Step 4: plateaus ---

def find_plateaus(m):
    """Stretches where the pitch sits steadily on one note: list of [start, end, midi]."""
    n = len(m)
    rounded = np.round(m)
    slope = np.full(n, np.inf)
    if n > 4:
        slope[2:-2] = np.abs(m[4:] - m[:-4]) / 4
    with np.errstate(invalid="ignore"):
        stable = (np.abs(m - rounded) < STABLE_DEVIATION) & (slope < STABLE_SLOPE)
    plateaus = []
    for s, e in runs(stable):
        # a stable run might cross from one note to the next; split where the note changes
        start = s
        for i in range(s + 1, e + 1):
            if i == e or rounded[i] != rounded[start]:
                plateaus.append([start, i, int(rounded[start])])
                start = i
    return plateaus


# --- Step 5: attacks ---

def attack_frames(y, n):
    """Frames where the sound suddenly gets louder: new picks or new sung notes."""
    rms = librosa.feature.rms(y=y, frame_length=512, hop_length=HOP)[0]
    rms = np.pad(rms, (0, max(0, n - len(rms))))[:n]
    db = 20 * np.log10(rms + 1e-5)
    rise = np.zeros(n)
    for i in range(1, n):
        rise[i] = db[i] - db[max(0, i - 6):i].min()
    attacks = []
    for i in range(1, n - 1):
        if rise[i] >= ATTACK_DB and rise[i] >= rise[i - 1] and rise[i] > rise[i + 1]:
            if not attacks or i - attacks[-1] > 6:
                attacks.append(i)
    return np.array(attacks, dtype=int)


def has_attack(attacks, lo, hi):
    return bool(np.any((attacks >= lo) & (attacks <= hi)))


# --- Steps 4-6 together ---

def merge_and_split(plateaus, m, attacks):
    """Join pieces of the same note broken up by wobbles; split one note picked twice."""
    merged = []
    for p in plateaus:
        if merged:
            q = merged[-1]
            gap = m[q[1]:p[0]]
            same_note = p[2] == q[2]
            heard = gap[~np.isnan(gap)]
            wobble_only = p[0] - q[1] <= 20 and (len(heard) == 0 or np.abs(heard - q[2]).max() < 0.9)
            if same_note and wobble_only and not has_attack(attacks, q[1] - 2, p[0] + 8):
                q[1] = p[1]
                continue
        merged.append(list(p))
    # split where a note is picked again without its pitch changing
    result = []
    for s, e, r in merged:
        cuts = [a for a in attacks if s + 8 <= a <= e - 8]   # ignore the note's own attack
        for cut in cuts:
            result.append([s, cut, r])
            s = cut
        result.append([s, e, r])
    result = [p for p in result if p[1] - p[0] >= MIN_NOTE_FRAMES]
    return drop_passing_notes(result, m, attacks)


def drop_passing_notes(plateaus, m, attacks):
    """A slow slide or bend can pause briefly on the notes in between. Remove those pauses.

    A plateau is a passing note if it sits between its neighbours in pitch, nothing is
    picked, the pitch keeps moving the same way, and it is either a small part of the
    glide or still drifting (a real held note stays put).
    """
    changed = True
    while changed:
        changed = False
        for i in range(1, len(plateaus) - 1):
            a, p, b = plateaus[i - 1], plateaus[i], plateaus[i + 1]
            between = min(a[2], b[2]) < p[2] < max(a[2], b[2])
            span = m[a[1]:b[0]]
            if not between or np.isnan(span).any() or has_attack(attacks, a[1] - 2, b[0] + 2):
                continue
            steps = np.diff(span)
            direction = np.sign(b[2] - a[2])
            moving_same_way = np.mean(steps * direction < -0.1) < 0.1   # hardly ever backwards
            drifting = abs(np.polyfit(np.arange(p[1] - p[0]), m[p[0]:p[1]], 1)[0]) > 0.04
            brief = (p[1] - p[0]) < 0.6 * (b[0] - a[1])
            if moving_same_way and (drifting or brief) and b[0] - a[1] <= 45:
                del plateaus[i]
                changed = True
                break
    return plateaus


def has_vibrato(segment):
    """A regular wobble of at least a tenth of a semitone, between 3 and 9 times a second."""
    segment = segment[~np.isnan(segment)]
    if len(segment) < 20:
        return False
    wobble = segment - median_filter(segment, size=min(len(segment), 31), mode="nearest")
    if np.std(wobble) < 0.1:
        return False
    # regular means it lines up with itself when shifted by one wobble (autocorrelation)
    wobble = wobble - wobble.mean()
    corr = np.correlate(wobble, wobble, mode="full")[len(wobble) - 1:]
    corr = corr / corr[0]
    per_second = SR / HOP
    lo, hi = int(per_second / 9), min(int(per_second / 3), len(corr) - 1)
    return lo < hi and corr[lo:hi + 1].max() > 0.4


def analyse(path):
    """Return the list of Notes found in an audio file."""
    y, _ = librosa.load(path, sr=SR, mono=True)
    if len(y) == 0 or np.max(np.abs(y)) == 0:
        return []
    raw = pitch_track(y)
    m = smooth(raw - tuning_offset(raw))
    attacks = attack_frames(y, len(m))
    plateaus = merge_and_split(find_plateaus(m), m, attacks)

    notes, frames = [], []          # frames[i] = (first frame, last frame) of notes[i]
    i = 0
    while i < len(plateaus):
        s, e, r = plateaus[i]
        prev = plateaus[i - 1] if i > 0 else None
        link = connection(prev, plateaus[i], m, attacks) if prev else "pick"

        # a picked note starts at its attack (or where the sound begins), not where it settles
        start = s
        if link == "pick":
            lowest = max(prev[1] if prev else 0, s - 8)
            earlier = attacks[(attacks <= s) & (attacks >= lowest)]
            if len(earlier):
                start = int(earlier[-1])
            else:
                while start - 1 >= lowest and not np.isnan(m[start - 1]):
                    start -= 1

        if link == "bend":
            note = notes[-1]
            note.bend = r - note.midi
            note.bend_at = frames_to_time(prev[1]) - note.start
            note.duration = frames_to_time(e) - note.start
            # does it come back down to where it started? that's the release
            if i + 1 < len(plateaus):
                nxt = plateaus[i + 1]
                if nxt[2] == note.midi and connection(plateaus[i], nxt, m, attacks) == "/glide-down":
                    note.release_at = frames_to_time(e) - note.start
                    note.duration = frames_to_time(nxt[1]) - note.start
                    frames[-1] = (frames[-1][0], nxt[1])
                    i += 2
                    continue
            frames[-1] = (frames[-1][0], e)
            i += 1
            continue

        technique = {"pick": "", "hammer": "h", "pull": "p", "/glide-up": "/",
                     "/glide-down": "\\"}[link]
        notes.append(Note(midi=r, start=frames_to_time(start),
                          duration=frames_to_time(e - start), technique=technique))
        frames.append((s, e))
        i += 1

    for note, (s, e) in zip(notes, frames):
        if not note.bend:
            note.vibrato = has_vibrato(m[s:e])
    return notes


def connection(a, b, m, attacks):
    """How do we get from plateau a to plateau b? pick, hammer, pull, bend, or a glide up/down."""
    gap = m[a[1]:b[0]]
    # a new attack can show up a little after the new pitch begins (e.g. a sung "d")
    if np.isnan(gap).sum() >= 2 or has_attack(attacks, a[1] - 2, min(b[0] + 8, b[1] - 1)):
        return "pick"
    step = b[2] - a[2]
    if step == 0:
        return "pick"
    low, high = sorted((a[2], b[2]))
    in_between = np.sum((gap > low + 0.3) & (gap < high - 0.3))
    if in_between < GLIDE_FRAMES:                       # it jumped straight there
        if abs(step) > MAX_HAMMER:
            return "pick"
        return "hammer" if step > 0 else "pull"
    if 0 < step <= MAX_BEND:
        return "bend"
    return "/glide-up" if step > 0 else "/glide-down"


def detect_notes(path, min_duration=0.06):
    """Simple version: a list of (note name, start time, duration)."""
    return [(n.name, round(n.start, 2), round(n.duration, 2))
            for n in analyse(path) if n.duration >= min_duration]


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "test_melody.wav"
    for n in analyse(path):
        extra = n.technique or ""
        if n.bend:
            extra += f" bend +{n.bend}" + (" & release" if n.release_at is not None else "")
        if n.vibrato:
            extra += " vibrato"
        print(f"{n.name:4} at {n.start:5.2f}s for {n.duration:.2f}s  {extra}")
