import os
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np
import sounddevice as sd
import soundfile as sf

from detect import detect_notes
from tab import choose_frets, render_tab

SAMPLE_RATE = 22050                 # samples per second when recording
recording = []                      # chunks of audio collected while recording
stream = None                       # the microphone stream (None = not recording)


# --- Turning a .wav file into tab ---

def analyse(path, label):
    """Detect the notes in a .wav file and show the tab in the window."""
    status.config(text="Analysing... this can take a few seconds")
    root.update()                   # refresh the window so the message shows
    try:
        notes = [note for note, start, dur in detect_notes(path)]
        tab_text = render_tab(choose_frets(notes)) if notes else "No notes found."
    except Exception as e:
        messagebox.showerror("Something went wrong", str(e))
        status.config(text="")
        return
    output.delete("1.0", tk.END)
    output.insert(tk.END, f"Notes: {' '.join(notes)}\n\n{tab_text}")
    status.config(text=f"Done: {len(notes)} notes from {label}")


def open_file():
    path = filedialog.askopenfilename(
        title="Choose an audio file",
        filetypes=[("WAV files", "*.wav")],
    )
    if path:                        # empty if the user clicked Cancel
        analyse(path, os.path.basename(path))


# --- Recording from the microphone ---

def audio_callback(indata, frames, time, status_flags):
    """Called by sounddevice every few milliseconds with a new chunk of audio."""
    recording.append(indata.copy())


def toggle_recording():
    global stream
    if stream is None:
        # Start recording
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
        status.config(text="Recording... hum now, then click Stop")
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
        analyse(path, "your recording")


def copy_tab():
    root.clipboard_clear()
    root.clipboard_append(output.get("1.0", tk.END))
    status.config(text="Tab copied to clipboard")


# --- Build the window ---

root = tk.Tk()
root.title("Hum to Tab")
root.geometry("700x350")

buttons = tk.Frame(root)
buttons.pack(pady=10)
record_button = tk.Button(buttons, text="● Record", width=12, command=toggle_recording)
record_button.pack(side="left", padx=5)
tk.Button(buttons, text="Open audio file...", command=open_file).pack(side="left", padx=5)
tk.Button(buttons, text="Copy tab", command=copy_tab).pack(side="left", padx=5)

status = tk.Label(root, text="Click Record and hum, or open a .wav file")
status.pack()

output = tk.Text(root, font=("Consolas", 12), wrap="none", height=10)
scroll = tk.Scrollbar(root, orient="horizontal", command=output.xview)
output.config(xscrollcommand=scroll.set)
output.pack(fill="both", expand=True, padx=10)
scroll.pack(fill="x", padx=10, pady=(0, 10))

root.mainloop()
