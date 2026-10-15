"""Hum to Tab: the desktop window.

Run it with:  python app.py
"""
import math
import os
import queue
import re
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

import numpy as np
import sounddevice as sd
import soundfile as sf

import playback
from detect import analyse
from tab import tab_text

SAMPLE_RATE = 22050                 # samples per second when recording

# --- Look and feel: black, white and greys only ---

BG = "#0f0f0f"              # window background
SURFACE = "#181818"         # the card the tab sits on
RAISED = "#242424"          # buttons
HOVER = "#303030"           # buttons under the mouse
BORDER = "#2b2b2b"          # thin outlines
TEXT = "#f2f2f2"            # main text
MUTED = "#8f8f8f"           # secondary text
FAINT = "#4a4a4a"           # tab dashes, disabled text
WHITE_HOVER = "#d6d6d6"     # the white button under the mouse

WINDOWS = sys.platform == "win32"
UI_FONT = "Segoe UI" if WINDOWS else "Inter"
MONO_FONT = "Consolas" if WINDOWS else "DejaVu Sans Mono"

SCALE = 1.0                 # set from the screen's DPI so sizes look right on any screen


def px(n):
    """Turn a size in 'normal screen' pixels into pixels for this screen."""
    return int(round(n * SCALE))


def blend(a, b, t):
    """Colour part-way between a and b (t=0 gives a, t=1 gives b). Used for smooth fades."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def rounded_rect(canvas, x1, y1, x2, y2, r, **options):
    """Draw a rectangle with rounded corners (a smoothed polygon)."""
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **options)


class RoundButton(tk.Canvas):
    """A flat, rounded button that fades smoothly when you hover over it."""

    def __init__(self, parent, text, command, icon=None, primary=False, width=120):
        self.w, self.h = px(width), px(40)
        super().__init__(parent, width=self.w, height=self.h, bg=parent["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.icon, self.command, self.primary = text, icon, command, primary
        self.font = tkfont.Font(family=UI_FONT, size=10, weight="bold")
        self.enabled = True
        self.pressed = False
        self.hover = 0.0            # 0 = resting, 1 = fully hovered
        self.target = 0.0
        self.icon_colour = None     # lets the record button pulse its icon
        self._job = None
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.draw()

    def colours(self):
        """Fill, text colour and outline for the button's current state."""
        if not self.enabled:
            return SURFACE, FAINT, BORDER
        if self.primary:
            fill = WHITE_HOVER if self.pressed else blend(TEXT, WHITE_HOVER, self.hover)
            return fill, BG, fill
        fill = BORDER if self.pressed else blend(RAISED, HOVER, self.hover)
        return fill, TEXT, blend(BORDER, "#3d3d3d", self.hover)

    def draw(self):
        self.delete("all")
        fill, ink, outline = self.colours()
        rounded_rect(self, 1, 1, self.w - 1, self.h - 1, (self.h - 2) / 2, fill=fill, outline=outline)
        cx, cy = self.w / 2, self.h / 2
        if not self.icon:
            self.create_text(cx, cy, text=self.text, fill=ink, font=self.font)
            return
        size, gap = px(4), px(8)                     # icon radius and space before the text
        total = 2 * size + gap + self.font.measure(self.text)
        ix = cx - total / 2 + size                   # centre of the icon
        colour = self.icon_colour or ink
        if self.icon == "dot":
            self.create_oval(ix - size, cy - size, ix + size, cy + size, fill=colour, outline="")
        elif self.icon == "square":
            self.create_rectangle(ix - size, cy - size, ix + size, cy + size, fill=colour, outline="")
        elif self.icon == "play":
            self.create_polygon(ix - size, cy - size - 1, ix + size + 1, cy, ix - size, cy + size + 1,
                                fill=colour, outline="")
        self.create_text(ix + size + gap, cy, text=self.text, fill=ink, font=self.font, anchor="w")

    def set_label(self, text, icon=None):
        self.text, self.icon = text, icon
        self.draw()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self.draw()

    # --- Mouse handling ---

    def _enter(self, event):
        self._fade_to(1)

    def _leave(self, event):
        self.pressed = False
        self._fade_to(0)

    def _press(self, event):
        if self.enabled:
            self.pressed = True
            self.draw()

    def _release(self, event):
        clicked = self.pressed and 0 <= event.x <= self.w and 0 <= event.y <= self.h
        self.pressed = False
        self.draw()
        if clicked and self.enabled:
            self.command()

    def _fade_to(self, target):
        self.target = target
        if self._job is None:
            self._step()

    def _step(self):
        """Move the hover colour a little closer to its target, about 60 times a second."""
        gap = self.target - self.hover
        if abs(gap) < 0.02:
            self.hover, self._job = self.target, None
            self.draw()
            return
        self.hover += gap * 0.35
        self.draw()
        self._job = self.after(16, self._step)


class App:
    def __init__(self, root):
        self.root = root
        self.notes = []                 # the Notes from the latest analysis
        self.plain_tab = ""             # the tab as plain text, for copying
        self.stream = None              # the microphone stream (None = not recording)
        self.chunks = []                # pieces of audio collected while recording
        self.record_started = 0.0
        self.busy = False               # True while a recording is being analysed
        self.closing = False
        self.results = queue.Queue()    # the analysis thread puts its answer here
        self.status_job = None
        self.build()
        self.show_message("No tab yet", "Record yourself humming or playing, or open a .wav file.")
        root.protocol("WM_DELETE_WINDOW", self.close)   # what happens when you click X

    # --- Building the window ---

    def build(self):
        root = self.root
        root.title("Hum to Tab")
        root.configure(bg=BG)
        root.geometry(f"{px(980)}x{px(700)}")
        root.minsize(px(760), px(520))
        self.style_scrollbars()

        page = tk.Frame(root, bg=BG)
        page.pack(fill="both", expand=True, padx=px(32), pady=px(28))

        tk.Label(page, text="Hum to Tab", bg=BG, fg=TEXT,
                 font=(UI_FONT, 22, "bold")).pack(anchor="w")
        tk.Label(page, text="Hum a melody or play a riff, and get the guitar tab.",
                 bg=BG, fg=MUTED, font=(UI_FONT, 11)).pack(anchor="w", pady=(px(2), 0))

        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(px(22), px(16)))
        self.record_btn = RoundButton(bar, "Record", self.toggle_recording, icon="dot",
                                      primary=True, width=128)
        self.open_btn = RoundButton(bar, "Open file", self.open_file, width=116)
        self.play_btn = RoundButton(bar, "Play", self.play_notes, icon="play", width=96)
        self.copy_btn = RoundButton(bar, "Copy tab", self.copy_tab, width=112)
        for button in (self.record_btn, self.open_btn, self.play_btn, self.copy_btn):
            button.pack(side="left", padx=(0, px(10)))
        self.status = tk.Label(bar, text="", bg=BG, fg=MUTED, font=(UI_FONT, 10))
        self.status.pack(side="right")

        card = tk.Frame(page, bg=SURFACE, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        card.pack(fill="both", expand=True)
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        self.output = tk.Text(card, bg=SURFACE, fg=TEXT, font=(MONO_FONT, 12), wrap="none",
                              relief="flat", bd=0, highlightthickness=0, cursor="arrow",
                              padx=px(26), pady=px(22), insertbackground=SURFACE,
                              selectbackground="#3a3a3a", selectforeground=TEXT)
        down = ttk.Scrollbar(card, orient="vertical", command=self.output.yview,
                             style="Slim.Vertical.TScrollbar")
        across = ttk.Scrollbar(card, orient="horizontal", command=self.output.xview,
                               style="Slim.Horizontal.TScrollbar")
        self.output.configure(yscrollcommand=self.auto_hide(down), xscrollcommand=self.auto_hide(across))
        self.output.grid(row=0, column=0, sticky="nsew")
        down.grid(row=0, column=1, sticky="ns", padx=(0, px(4)), pady=px(4))
        across.grid(row=1, column=0, sticky="ew", padx=px(4), pady=(0, px(4)))

        o = self.output                 # text styles used when showing the tab
        o.tag_configure("label", foreground=MUTED, font=(UI_FONT, 9, "bold"))
        o.tag_configure("notes", foreground=TEXT, font=(UI_FONT, 12), spacing1=px(4))
        o.tag_configure("heading", foreground=TEXT, font=(UI_FONT, 11, "bold"))
        o.tag_configure("frets", foreground=MUTED, font=(UI_FONT, 10))
        o.tag_configure("gap", font=(UI_FONT, 6))
        o.tag_configure("string", foreground=MUTED)
        o.tag_configure("rule", foreground=FAINT)
        o.tag_configure("legend", foreground=MUTED, font=(UI_FONT, 10), spacing1=px(3))
        o.tag_configure("title", foreground=TEXT, font=(UI_FONT, 15, "bold"),
                        justify="center", spacing1=px(150))
        o.tag_configure("hint", foreground=MUTED, font=(UI_FONT, 11),
                        justify="center", spacing1=px(6))

    @staticmethod
    def auto_hide(scrollbar):
        """Only show a scrollbar when there's something to scroll."""
        def update(first, last):
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.grid_remove()
            else:
                scrollbar.grid()
            scrollbar.set(first, last)
        return update

    def style_scrollbars(self):
        """Thin grey scrollbars with no arrows."""
        style = ttk.Style(self.root)
        style.theme_use("clam")
        for orient in ("Vertical", "Horizontal"):
            name = f"Slim.{orient}.TScrollbar"
            style.layout(name, [(f"{orient}.Scrollbar.trough", {"sticky": "nswe", "children": [
                (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
            style.configure(name, troughcolor=SURFACE, background="#363636", bordercolor=SURFACE,
                            lightcolor="#363636", darkcolor="#363636", arrowsize=px(7), gripcount=0)
            style.map(name, background=[("pressed", "#5a5a5a"), ("active", "#4a4a4a")],
                      lightcolor=[("pressed", "#5a5a5a"), ("active", "#4a4a4a")],
                      darkcolor=[("pressed", "#5a5a5a"), ("active", "#4a4a4a")])

    # --- Showing results ---

    def show_message(self, title, hint):
        o = self.output
        o.configure(state="normal")
        o.delete("1.0", "end")
        o.insert("end", title + "\n", "title")
        o.insert("end", hint + "\n", "hint")
        o.configure(state="disabled")

    def show_tab(self, text):
        """Show the tab with quiet dashes and bright fret numbers, so the notes stand out."""
        o = self.output
        o.configure(state="normal")
        o.delete("1.0", "end")
        for line in text.splitlines():
            if line.startswith("Notes: "):
                o.insert("end", "NOTES\n", "label")
                o.insert("end", "   ".join(line[7:].split()) + "\n", "notes")
            elif line.startswith("Box "):
                name, _, frets = line.partition(" (")
                o.insert("end", "\n", "gap")
                o.insert("end", name, "heading")
                o.insert("end", "    " + frets.rstrip(")") + "\n", "frets")
                o.insert("end", "\n", "gap")
            elif re.match(r"^[eBGDAE]\|", line):
                start = o.index("end-1c")
                o.insert("end", line + "\n")
                o.tag_add("string", start, f"{start}+1c")
                for dashes in re.finditer(r"[-|]+", line):
                    o.tag_add("rule", f"{start}+{dashes.start()}c", f"{start}+{dashes.end()}c")
            elif line.strip():
                o.insert("end", line + "\n", "legend")
            else:
                o.insert("end", "\n", "gap")
        o.configure(state="disabled")
        o.yview_moveto(0)
        o.xview_moveto(0)

    def set_status(self, text, temporary=False):
        """Small text at the top right. Temporary messages fade back after a moment."""
        if self.status_job:
            self.root.after_cancel(self.status_job)
            self.status_job = None
        self.status.configure(text=text)
        if temporary:
            self.status_job = self.root.after(2500, self._resting_status)

    def _resting_status(self):
        self.status_job = None
        self.status.configure(text=f"{len(self.notes)} notes" if self.notes else "")

    def set_buttons(self, record=True, others=True):
        self.record_btn.set_enabled(record)
        for button in (self.open_btn, self.play_btn, self.copy_btn):
            button.set_enabled(others)

    # --- Analysing (in the background, so the window never freezes) ---

    def analyse_file(self, path, label):
        self.busy = True
        self.set_buttons(record=False, others=False)
        self.spinner = 0
        self._spin()
        worker = threading.Thread(target=self._work, args=(path, label), daemon=True)
        worker.start()
        self.root.after(100, self._check_results)

    def _work(self, path, label):
        """Runs on a separate thread. Never touches the window, just hands back the answer."""
        try:
            notes = analyse(path)
            self.results.put((label, notes, tab_text(notes) if notes else "", None))
        except Exception as error:
            self.results.put((label, [], "", error))

    def _check_results(self):
        if self.closing:
            return
        try:
            label, notes, text, error = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._check_results)
            return
        self.busy = False
        self.set_buttons()
        self.notes, self.plain_tab = notes, text
        if error:
            self.set_status("")
            messagebox.showerror("Something went wrong", str(error), parent=self.root)
        elif notes:
            self.show_tab(text)
            self.set_status(f"{len(notes)} notes from {label}")
        else:
            self.set_status("")
            self.show_message("No notes found", "Try again a little louder, one note at a time.")

    def _spin(self):
        """Three dots that light up in turn while analysing."""
        if not self.busy or self.closing:
            return
        dots = ["•" if i == self.spinner % 3 else "◦" for i in range(3)]
        self.status.configure(text="Analysing  " + " ".join(dots))
        self.spinner += 1
        self.root.after(280, self._spin)

    def open_file(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose an audio file",
                                          filetypes=[("WAV files", "*.wav")])
        if path:                        # empty if you clicked Cancel
            self.analyse_file(path, os.path.basename(path))

    # --- Recording from the microphone ---

    def toggle_recording(self):
        if self.stream is None:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        try:
            playback.stop()             # so the playback isn't recorded
        except Exception:
            pass
        self.chunks = []
        try:
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                         callback=self._on_audio)
            self.stream.start()
        except Exception as error:
            self.stream = None
            messagebox.showerror("Microphone problem", str(error), parent=self.root)
            return
        self.record_started = time.time()
        self.record_btn.set_label("Stop", "square")
        self.set_buttons(record=True, others=False)
        self._pulse()

    def _on_audio(self, indata, frames, time_info, status_flags):
        """Called by sounddevice every few milliseconds with a new piece of audio."""
        self.chunks.append(indata.copy())

    def _pulse(self):
        """Gently pulse the stop icon and count the seconds while recording."""
        if self.stream is None or self.closing:
            return
        elapsed = time.time() - self.record_started
        glow = (math.sin(elapsed * 2 * math.pi / 1.4) + 1) / 2
        self.record_btn.icon_colour = blend(BG, "#8a8a8a", glow)
        self.record_btn.draw()
        self.status.configure(text=f"Recording   {int(elapsed) // 60}:{int(elapsed) % 60:02d}")
        self.root.after(40, self._pulse)

    def stop_recording(self):
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.record_btn.icon_colour = None
        self.record_btn.set_label("Record", "dot")
        self.set_buttons()
        if not self.chunks:
            self.set_status("Nothing was recorded", temporary=True)
            return
        audio = np.concatenate(self.chunks)
        if len(audio) < SAMPLE_RATE * 0.3:
            self.set_status("Too short, try again", temporary=True)
            return
        path = os.path.join(tempfile.gettempdir(), "hum_to_tab_recording.wav")
        sf.write(path, audio, SAMPLE_RATE)
        self.analyse_file(path, "your recording")

    # --- Playing back and copying ---

    def play_notes(self):
        """Play the notes (with their slides, bends and hammer-ons) so you can check them by ear."""
        if not self.notes:
            self.set_status("Nothing to play yet", temporary=True)
            return
        try:
            playback.play(playback.notes_to_audio(self.notes))
        except Exception as error:
            messagebox.showerror("Playback problem", str(error), parent=self.root)
            return
        self.set_status(f"Playing {len(self.notes)} notes", temporary=True)

    def copy_tab(self):
        if not self.plain_tab:
            self.set_status("Nothing to copy yet", temporary=True)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.plain_tab)
        self.set_status("Copied to clipboard", temporary=True)

    # --- Closing ---

    def close(self):
        """Stop the microphone and any sound, then close the window for good."""
        self.closing = True
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        try:
            playback.stop()
        except Exception:
            pass
        self.root.quit()                # end mainloop
        self.root.destroy()             # and remove the window


def sharp_on_windows():
    """Stop Windows blurring the window on high-resolution screens."""
    if WINDOWS:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def dark_title_bar(root):
    """Make the Windows title bar dark to match the app."""
    if WINDOWS:
        try:
            import ctypes
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            on = ctypes.c_int(1)
            for attribute in (20, 19):          # the number differs between Windows versions
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(on), 4) == 0:
                    break
        except Exception:
            pass


def main():
    global SCALE
    sharp_on_windows()
    root = tk.Tk()
    SCALE = max(1.0, root.winfo_fpixels("1i") / 96)
    App(root)
    dark_title_bar(root)
    root.mainloop()


# Only open the window when this file is run directly, never when it's imported.
if __name__ == "__main__":
    main()