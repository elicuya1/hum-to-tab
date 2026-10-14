# hum-to-tab

Turn humming and audio recordings into guitar tabs, including slides, bends and hammer-ons.

Hum a melody or play a riff, and hum-to-tab works out which notes you played, how you played them, and every place on the neck you could play them.

```
Notes: A3 C4 D4 C4 A3 D4 D4 A3 C4 A3 E3 E3

Box 1 (frets 2-7)
e|------------------------------|
B|------------------------------|
G|---5h7p5-2/7-7b9r7----5\2-----|
D|-7-----------------7~---------|
A|--------------------------7-7-|
E|------------------------------|

Box 2 (frets 7-12)
e|------------------------------------------|
B|------------------------------------------|
G|------------------------------------------|
D|----10h12p10-7/12-12b14r12-----10\7-------|
A|-12------------------------12~------------|
E|------------------------------------12-12-|
```

## Features

- **Note detection that copes with real voices.** Corrects for singing a little sharp or flat, smooths out wobble, and spots when the same note is sung or picked twice.
- **Techniques.** Recognises hammer-ons (`h`), pull-offs (`p`), slides (`/` and `\`), bends (`b`), bend releases (`r`) and vibrato (`~`).
- **Every box on the neck.** Shows each position where the riff fits, from the open position up the neck, with the easiest fingering in each.
- **Record straight into the app** from your microphone, or open a `.wav` file.
- **Play it back.** Hear the detected notes, slides and bends to check the result by ear.

## How it works

1. **Track the pitch.** [librosa](https://librosa.org)'s pYIN algorithm measures the pitch about 86 times a second.
2. **Correct the tuning.** If the whole recording is a bit sharp or flat, everything is shifted back into tune.
3. **Find the notes.** Notes are stretches where the pitch sits steadily on one note. Short wobbles are ignored, and brief pauses on the way through a slow slide or bend are not counted as notes.
4. **Find the picks.** A sudden jump in volume means a new pick (or a new sung note).
5. **Work out the technique** from what happens between two notes:

   | Between the notes | Result |
   |---|---|
   | A new pick | Separate notes |
   | The pitch jumps instantly, no pick | Hammer-on (up) or pull-off (down) |
   | The pitch glides up 1–2 semitones | Bend, and gliding back down is the release |
   | The pitch glides further, or down | Slide |
   | A steady wobble 3–9 times a second | Vibrato |

6. **Find the boxes.** For each hand position on the neck, the easiest fingering is worked out (like a sat-nav finding the cheapest route). Hammer-ons, pull-offs and slides are kept on one string, and open strings are only used in the open position. Positions where the riff really fits are kept.
7. **Draw the tab.**

## Getting started

You need **Python 3.10 or newer**. Install the libraries with:

```
pip install numpy scipy librosa soundfile sounddevice
```

Then download this project (green **Code** button → **Download ZIP**, or clone it).

## Usage

### Desktop app

```
python app.py
```

- **● Record**: click, hum or play, then click **■ Stop**. The tab appears.
- **Open audio file...**: pick a `.wav` file instead.
- **▶ Play notes**: hear what was detected.
- **Copy tab**: copy everything to paste anywhere.

### Command line

```
python tab.py my_recording.wav       # the tab, in every box
python detect.py my_recording.wav    # the notes, with timings and techniques
```

### Tips for good results

- **One note at a time.** Chords aren't supported.
- **Separate your notes** when humming, like "da da da", unless you mean to slide.
- **Record somewhere quiet.**

### Trying the test recordings

```
python make_test_audio.py
```

This creates three recordings where the right answer is known: `test_melody.wav` (clean beeps), `test_articulations.wav` (a riff with every technique) and `test_humming.wav` (a wobbly, slightly flat hum).

## Project structure

| File | What it does |
|---|---|
| `notes.py` | Note names, and converting a frequency to a note |
| `detect.py` | Finds the notes and techniques in a recording |
| `tab.py` | Finds the boxes on the neck and draws the tab |
| `playback.py` | Turns notes back into sound |
| `app.py` | The desktop window (built with tkinter) |
| `make_test_audio.py` | Creates the test recordings |

## Limitations

- **One note at a time.** Recordings with chords or a full band won't work.
- **No rhythm yet.** The tab shows which notes to play, not how long to hold them.
- **Bend or slide?** A small glide up is read as a bend, but on guitar it could also be a short slide.
- **WAV files only.**
- **Very noisy recordings** can miss quiet notes or techniques.

## Roadmap

- [x] Record directly from the microphone
- [x] Play back the detected notes
- [x] Recognise hammer-ons, pull-offs, slides, bends and vibrato
- [x] Show every box on the neck
- [ ] Live tuner mode
- [ ] Show note durations in the tab
- [ ] Support MP3 and other audio formats
- [ ] Export the tab to a text file

## License

[MIT](LICENSE). Free to use, change, and share.
