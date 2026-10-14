# hum-to-tab

Turn humming and audio recordings into guitar tabs.

Hum a melody, record it as a `.wav` file, and hum-to-tab works out which notes you sang and where to play them on the guitar.

```
Notes: E3 G3 A3 B3 A3 G3 E3

e|---------------|
B|-------0-------|
G|---0-2---2-0---|
D|-2-----------2-|
A|---------------|
E|---------------|
```

## Features

- **Pitch detection.** Finds the notes in a recording of a single melody (humming, singing, or one instrument).
- **Smart fret choice.** Picks positions close to each other so the result is comfortable to play.
- **Out-of-range notes.** Shifts notes that are too high or too low for a guitar by an octave.
- **Desktop app.** Open a file, see the tab, and copy it with one click.

## How it works

1. **Detect the pitch.** The audio is split into tiny slices (about 23 ms each), and [librosa](https://librosa.org)'s pYIN algorithm estimates the frequency of each slice.
2. **Turn frequencies into notes.** Each frequency is converted to the nearest note name (440 Hz → A4). Consecutive slices with the same note are grouped together, and blips shorter than 0.1 s are ignored.
3. **Map notes to the fretboard.** For each note, every string where it can be played is considered, and the fret closest to the previous one is chosen.
4. **Draw the tab.** The fret numbers are written onto six lines of ASCII tab, one per string.

## Getting started

You need **Python 3.10 or newer**. Install the libraries with:

```
pip install numpy librosa soundfile
```

Then download this project (green **Code** button → **Download ZIP**, or clone it).

## Usage

### Desktop app

```
python app.py
```

Click **Open audio file...**, choose a `.wav` file, and the tab appears. Click **Copy tab** to paste it anywhere.

### Command line

```
python tab.py
```

This prints the tab for `test_melody.wav`. To use your own recording, change the file name at the bottom of `tab.py`.

### Recording your own humming

1. Record yourself with a free tool like [Audacity](https://www.audacityteam.org).
2. Export as WAV (**File → Export → Export as WAV**).
3. Open it in the app.

For the best results:
- **Hum slowly,** with a clear break between notes.
- **Record somewhere quiet.**
- **Stick to one note at a time.** Chords aren't supported.

## Project structure

| File | What it does |
|---|---|
| `notes.py` | Converts a frequency in Hz to a note name |
| `detect.py` | Finds the sequence of notes in an audio file |
| `tab.py` | Chooses fret positions and draws the tab |
| `app.py` | The desktop window (built with tkinter) |
| `make_test_audio.py` | Generates `test_melody.wav`, a test file with known notes |

## Limitations

- **One note at a time.** Recordings with chords, several instruments, or a full band won't work.
- **No rhythm yet.** The tab shows which notes to play, not how long to hold each one.
- **WAV files only.**
- **Real humming is messy.** Expect the odd extra or split note.

## Roadmap

- [ ] Record humming directly from the microphone
- [ ] Show note durations in the tab
- [ ] Support MP3 and other audio formats
- [ ] Export the tab to a text file

## License

[MIT](LICENSE). Free to use, change, and share.
