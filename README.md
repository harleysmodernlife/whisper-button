# Whisper Button

A small floating desktop app that records your voice and types the transcription wherever your cursor is. Everything runs **offline** — no internet required after the first setup.

---

## How It Works

1. You click into any text field (browser, text editor, terminal, anything)
2. Press **Ctrl+Alt+R** (or click the Start button)
3. Speak
4. Press **Ctrl+Alt+R** again (or click Stop)
5. The transcribed text is typed at your cursor automatically

The app window floats on top of everything else and **never steals focus** from your text field — that's the whole point.

---

## Installation

### Step 1 — Install system audio library

```bash
sudo apt-get install libportaudio2
```

### Step 2 — Install Python dependencies

```bash
pip3 install --user -r requirements.txt
```

> **First run** will download the Whisper speech model (~75 MB). This only happens once and requires an internet connection. After that, everything is offline.

### Step 3 — Add to your app launcher (optional)

The app should already appear in your application menu as **Whisper Button**. If it doesn't:

```bash
cp whisper-button.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/
```

### Step 4 — Set up the keyboard shortcut

The `Ctrl+Alt+R` shortcut works by sending a signal to the running app process. It's registered as a GNOME custom shortcut automatically when the app starts, but you can also check/set it manually:

- Open **Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts**
- Look for **Whisper Toggle**
- It should have the command: `pkill -USR1 -f whisper_button_app/app.py`
- And the binding: `Ctrl+Alt+R`

If it's missing, add it there manually with those values.

---

## Running the App

```bash
./run.sh
```

Or launch it from your application menu. The terminal will print the app's process ID and confirm the signal handler is ready.

**Status indicator colors:**

| Color | Meaning |
|-------|---------|
| Orange | Whisper model not loaded yet |
| Yellow | Loading model or processing audio |
| Green | Ready to record |
| Red | Recording in progress |
| Light green | Just typed transcription at cursor |

---

## Controls

| Action | How |
|--------|-----|
| Start/stop recording | `Ctrl+Alt+R` (recommended) or click the button |
| Hide the window | `Escape` (app keeps running in the background) |
| Show the window again | `Ctrl+Alt+W` |
| Quit the app | Click the **X** button to close the window |

---

## Troubleshooting

**Transcription types in the wrong place**
The app types wherever keyboard focus is when transcription finishes. Make sure you clicked into your target text field *before* starting the recording, and don't click away while it's processing.

**Ctrl+Alt+R does nothing**
Check that the app is actually running first. Then verify the custom shortcut exists in GNOME Settings (see Step 4 above). You can also test by opening a terminal and running:
```bash
pkill -USR1 -f whisper_button_app/app.py
```
If the app toggles recording, the shortcut just needs to be configured in GNOME Settings.

**"Whisper not installed" (red status)**
```bash
pip3 install --user openai-whisper
```

**No audio / recording errors**
```bash
sudo apt-get install libportaudio2
pip3 install --user sounddevice numpy scipy
```
Also check that your microphone is not muted in system sound settings.

**Model download stuck or fails**
The first-run model download needs an internet connection. Run the app from a terminal (`./run.sh`) to see the download progress. Once downloaded, the model is cached and the app works offline forever.

---

## Files

```
whisper_button_app/
├── app.py                    Main application
├── run.sh                    Launch script
├── requirements.txt          Python dependencies
├── whisper-button.desktop    App launcher entry (for application menu)
├── whisper_button_icon.svg   App icon
└── README.md                 This file
```
