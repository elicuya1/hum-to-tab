import os
import tkinter as tk
from tkinter import filedialog, messagebox
from detect import detect_notes
from tab import choose_frets, render_tab

def open_file():
    path = filedialog.askopenfilename(
        title="Choose an audio file",
        filetypes=[("WAV files", "*.wav")],
    )
    if not path:            # user clicked Cancel
        return
    status.config(text="Analysing... this can take a few seconds")
    root.update()           # refresh the window so the message shows
    try:
        notes = [note for note, start, dur in detect_notes(path)]
        tab_text = render_tab(choose_frets(notes)) if notes else "No notes found."
    except Exception as e:
        messagebox.showerror("Something went wrong", str(e))
        status.config(text="")
        return
    output.delete("1.0", tk.END)
    output.insert(tk.END, f"Notes: {' '.join(notes)}\n\n{tab_text}")
    status.config(text=f"Done: {len(notes)} notes from {os.path.basename(path)}")

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
tk.Button(buttons, text="Open audio file...", command=open_file).pack(side="left", padx=5)
tk.Button(buttons, text="Copy tab", command=copy_tab).pack(side="left", padx=5)

status = tk.Label(root, text="Choose a .wav file to begin")
status.pack()

output = tk.Text(root, font=("Consolas", 12), wrap="none", height=10)
scroll = tk.Scrollbar(root, orient="horizontal", command=output.xview)
output.config(xscrollcommand=scroll.set)
output.pack(fill="both", expand=True, padx=10)
scroll.pack(fill="x", padx=10, pady=(0, 10))
root.mainloop()
