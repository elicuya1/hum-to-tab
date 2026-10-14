import os
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np
import sounddevice as sd
import soundfile as sf

import playback
from detect import analyse
from tab import tab_text

SAMPLE_RATE = 22050                 # samples per second when recording
recording = []                      # chunks of audio collected while recording
stream = None                       # the microphone stream (None = not recording)
last_notes = []                     # the Notes from the latest analysis


# --- Turning a .wav file into tab ---

def analyse_file(path, label):
    """Detect the notes in a .wav file and show the tab in the window."""
    global last_notes
    status.config(text="Analysing... this can take a few seconds")
    root.update()                   # refresh the window so the message shows
    try:
        last_notes = analyse(path)
        text = tab_text(last_notes)
    except Exception as e:
        last_notes = []
        messagebox.showerror("Something went wrong", str(e))
        status.config(text="")
        return
    output.delete("1.0", tk.END)
    output.insert(tk.END, text)
    status.config(text=f"Done: {len(last_notes)} notes from {label}")


def open_file():
    path = filedialog.askopenfilename(
        title="Choose an audio file",
        filetypes=[("WAV files", "*.wav")],
    )
    if path:                        # empty if the user clicked Cancel
        analyse_file(path, os.path.basename(path))


# --- Recording from the microphone ---

def audio_callback(indata, frames, time, status_flags):
    """Called by sounddevice every few milliseconds with a new chunk of audio."""
    recording.append(indata.copy())


def toggle_recording():
    global stream
    if stream is None:
        # Start recording
        playback.stop()                     # stop any playback so it isn't recorded
        recording.clear()
        try:
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                    callback=audio_callback)
            stream.start()
        except Exception as e:
            stream = None
            messagebox.showerror("Microphone problem", str(e))
            return
        record_button.config(text="■ Stop")
        status.config(text="Recording... hum or play now, then click Stop")
    else:
        # Stop recording and analyse what was captured
        stream.stop()
        stream.close()
        stream = None
        record_button.config(text="● Record")
        if not recording:
            status.config(text="Nothing was recorded")
            return
        audio = np.concatenate(recording)
        path = os.path.join(tempfile.gettempdir(), "hum_to_tab_recording.wav")
        sf.write(path, audio, SAMPLE_RATE)
        analyse_file(path, "your recording")


# --- Playing the detected notes back ---

def play_notes():
    """Play the notes (with their slides, bends and hammer-ons) so you can check them by ear."""
    if not last_notes:
        status.config(text="Nothing to play yet: open a file or record first")
        return
    try:
        playback.play(playback.notes_to_audio(last_notes))
    except Exception as e:
        messagebox.showerror("Playback problem", str(e))
        return
    status.config(text=f"Playing {len(last_notes)} notes...")


def copy_tab():
    root.clipboard_clear()
    root.clipboard_append(output.get("1.0", tk.END))
    status.config(text="Tab copied to clipboard")


# --- Build the window ---

root = tk.Tk()
root.title("Hum to Tab")
root.geometry("900x620")

buttons = tk.Frame(root)
buttons.pack(pady=10)
record_button = tk.Button(buttons, text="● Record", width=12, command=toggle_recording)
record_button.pack(side="left", padx=5)
tk.Button(buttons, text="Open audio file...", command=open_file).pack(side="left", padx=5)
tk.Button(buttons, text="▶ Play notes", command=play_notes).pack(side="left", padx=5)
tk.Button(buttons, text="Copy tab", command=copy_tab).pack(side="left", padx=5)

status = tk.Label(root, text="Click Record and hum or play, or open a .wav file")
status.pack()

box = tk.Frame(root)
box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
output = tk.Text(box, font=("Consolas", 12), wrap="none")
down = tk.Scrollbar(box, orient="vertical", command=output.yview)
across = tk.Scrollbar(box, orient="horizontal", command=output.xview)
output.config(yscrollcommand=down.set, xscrollcommand=across.set)
down.pack(side="right", fill="y")
across.pack(side="bottom", fill="x")
output.pack(side="left", fill="both", expand=True)

root.mainloop()
