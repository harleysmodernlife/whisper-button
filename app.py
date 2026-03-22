#!/usr/bin/env python3
import sys
import os
import signal
import threading
import tempfile
import time

# Add system path for GI (GTK bindings) on Ubuntu
system_gi_path = '/usr/lib/python3/dist-packages'
if system_gi_path not in sys.path:
    sys.path.insert(0, system_gi_path)

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
    GTK_AVAILABLE = True
except Exception as e:
    print(f"GTK not available: {e}")
    GTK_AVAILABLE = False
    sys.exit(1)

# Try to import audio dependencies
try:
    import sounddevice as sd
    import numpy as np
    from scipy.io.wavfile import write
    AUDIO_AVAILABLE = True
except (ImportError, OSError) as e:
    print(f"Audio dependencies not available: {e}")
    AUDIO_AVAILABLE = False
    # Create dummy modules to prevent NameError
    class DummySD:
        class CallbackStop(Exception):
            pass
        class InputStream:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
    sd = DummySD()
    np = None
    write = None

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

try:
    from pynput import keyboard
    KEYBOARD_CONTROL_AVAILABLE = True
except ImportError:
    print("pynput not available - keyboard simulation disabled")
    KEYBOARD_CONTROL_AVAILABLE = False
    # Create a dummy controller
    class DummyController:
        def type(self, text):
            pass
        def press(self, key):
            pass
        def release(self, key):
            pass
    keyboard = type('keyboard', (), {'Controller': DummyController, 'Key': type('Key', (), {})})()

TEMP_AUDIO_FILE = None

class WhisperHandler:
    def __init__(self):
        self.model = None
        self.is_loading = False
        self.whisper_available = WHISPER_AVAILABLE
        self.keyboard_controller = keyboard.Controller() if KEYBOARD_CONTROL_AVAILABLE else None
        
    def load_model(self, model_name="tiny"):
        if not self.whisper_available:
            return False
        if self.is_loading or self.model is not None:
            return True
        
        self.is_loading = True
        def loader():
            try:
                self.model = whisper.load_model(model_name)
                GLib.idle_add(self.model_loaded_callback, True)
            except Exception as e:
                GLib.idle_add(self.model_loaded_callback, False)
            finally:
                self.is_loading = False
                
        threading.Thread(target=loader, daemon=True).start()
        return True
    
    def model_loaded_callback(self, success):
        pass
    
    def transcribe_and_type(self, audio_file):
        if self.model is None:
            return False
        if not KEYBOARD_CONTROL_AVAILABLE:
            print("Keyboard control not available")
            return False
        try:
            result = self.model.transcribe(audio_file)
            text = result["text"].strip()
            if text:
                # Add a space at the end for natural typing flow
                text_to_type = text + " "
                # Use GLib to schedule keyboard typing in main thread
                GLib.idle_add(self.type_text, text_to_type)
                # Clean up temp file
                try:
                    os.unlink(audio_file)
                except Exception:
                    pass
                return True
            else:
                try:
                    os.unlink(audio_file)
                except Exception:
                    pass
                return False
        except Exception as e:
            print(f"Transcription/typing error: {e}")
            try:
                os.unlink(audio_file)
            except Exception:
                pass
            return False
    
    def type_text(self, text):
        if self.keyboard_controller:
            try:
                self.keyboard_controller.type(text)
                return False  # Don't repeat
            except Exception as e:
                print(f"Keyboard typing error: {e}")
        return False

class StatusIndicator(Gtk.DrawingArea):
    def __init__(self, size=14):
        super().__init__()
        self.size = size
        self.set_size_request(size, size)
        self.color = "gray"  # default
        self.connect("draw", self.on_draw)
    
    def set_color(self, color_name):
        self.color = color_name
        self.queue_draw()
    
    def on_draw(self, widget, cr):
        rgba = Gdk.RGBA()
        rgba.parse(self.color)
        Gdk.cairo_set_source_rgba(cr, rgba)
        cr.arc(self.size/2, self.size/2, self.size/2 - 2, 0, 2 * 3.14159)
        cr.fill()

class WhisperControlWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Whisper Control")
        self.set_default_size(280, 180)
        self.set_resizable(False)
        self.set_keep_above(True)  # Always on top
        self.set_accept_focus(False)  # Never steal focus from target window
        self.set_border_width(12)
        self.set_icon_name("audio-input-microphone")
        
        # Connect events
        self.connect("delete-event", self.on_delete_event)
        self.connect("key-press-event", self.on_key_press)
        
        # Apply theme
        self.apply_theme()
        
        # Build UI
        self.build_ui()
        
        # Initialize state
        self.recording = False
        self.recording_thread = None
        self.whisper_handler = WhisperHandler()
        self.temp_audio_file = None
        
        # Start periodic status update
        GLib.timeout_add_seconds(1, self.update_status)
        
        # Show window by default
        self.show_all()

        # Set up global hotkey to toggle recording without clicking
        self.setup_global_hotkey()
    
    def apply_theme(self):
        css = b"""
        window { background-color: #2b2b2b; }
        .title-label { color: #4FC3F7; font-weight: bold; }
        .status-label { color: white; }
        .button { background-color: #424242; color: white; }
        .button:hover { background-color: #616161; }
        .mic-button { background-color: #00695C; }
        .mic-button:hover { background-color: #00897B; }
        .stop-button { background-color: #8E24AA; }
        .stop-button:hover { background-color: #AB47BC; }
        .hide-button { background-color: #616161; }
        .hide-button:hover { background-color: #757575; }
        .hint-label { color: #B0BEC5; font-size: 8pt; }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    def build_ui(self):
        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        self.add(vbox)
        
        # Title bar
        title_label = Gtk.Label(label="🎤 Whisper Button")
        title_label.get_style_context().add_class("title-label")
        title_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(title_label, False, False, 0)
        
        # Status bar
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(status_box, False, False, 0)
        
        self.status_label = Gtk.Label(label="Status: Initializing...")
        self.status_label.get_style_context().add_class("status-label")
        status_box.pack_start(self.status_label, True, True, 0)
        
        self.status_indicator = StatusIndicator()
        status_box.pack_end(self.status_indicator, False, False, 0)
        
        # Hint about usage
        hint_text = "💡 Use your system shortcut or click buttons | Esc: hide"
        hint_label = Gtk.Label(label=hint_text)
        hint_label.get_style_context().add_class("hint-label")
        hint_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(hint_label, False, False, 6)
        
        # Instructions
        instructions = Gtk.Label(label="Click 🎤 to record, then ⏹️ to stop\nor bind a system shortcut to toggle")
        instructions.set_justify(Gtk.Justification.CENTER)
        instructions.set_line_wrap(True)
        vbox.pack_start(instructions, False, False, 8)
        
        # Button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(button_box, False, False, 0)
        
        # Mic button (changes based on state)
        self.mic_button = Gtk.Button(label="🎤 Start")
        self.mic_button.get_style_context().add_class("mic-button")
        if AUDIO_AVAILABLE:
            self.mic_button.connect("clicked", self.on_mic_clicked)
        else:
            self.mic_button.set_sensitive(False)
            self.mic_button.set_tooltip_text("Install libportaudio2 and python3-sounddevice for recording")
        button_box.pack_start(self.mic_button, False, False, 0)
        
        # Hide button
        hide_button = Gtk.Button(label="❌ Hide")
        hide_button.get_style_context().add_class("hide-button")
        hide_button.connect("clicked", self.on_hide_clicked)
        button_box.pack_start(hide_button, False, False, 0)
        
        self.show_all()
    
    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        elif event.keyval == Gdk.KEY_w and event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            # Ctrl+Alt+W to show window
            if not self.get_visible():
                self.show()
                self.present()
            return True
        return False
    
    def on_delete_event(self, widget, event):
        Gtk.main_quit()
        return False
    
    def update_status(self):
        if not self.whisper_handler.whisper_available:
            self.status_label.set_text("Status: Whisper NOT installed")
            self.status_indicator.set_color("red")
            self.mic_button.set_sensitive(False)
            return True
        
        if self.whisper_handler.is_loading:
            self.status_label.set_text("Status: Loading model...")
            self.status_indicator.set_color("yellow")
        elif self.whisper_handler.model is not None:
            self.status_label.set_text("Status: Ready")
            self.status_indicator.set_color("green")
            if AUDIO_AVAILABLE and not self.mic_button.get_sensitive():
                self.mic_button.set_sensitive(True)
                self.mic_button.set_label("🎤 Start")
                self.mic_button.get_style_context().remove_class("stop-button")
                self.mic_button.get_style_context().add_class("mic-button")
        else:
            self.status_label.set_text("Status: Model not loaded")
            self.status_indicator.set_color("orange")
            # Trigger model load
            self.whisper_handler.load_model()
        
        return True  # Continue timeout
    
    def on_mic_clicked(self, button):
        if not AUDIO_AVAILABLE:
            return
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()
    
    def start_recording(self):
        if self.whisper_handler.model is None:
            self.status_label.set_text("Status: Model loading...")
            self.status_indicator.set_color("yellow")
            return
        
        self.recording = True
        self.mic_button.set_label("⏹️ Stop")
        self.mic_button.get_style_context().remove_class("mic-button")
        self.mic_button.get_style_context().add_class("stop-button")
        self.status_indicator.set_color("red")
        
        # Create temp file
        try:
            fd, self.temp_audio_file = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
        except Exception as e:
            print(f"Error creating temp file: {e}")
            return
        
        # Start recording thread
        self.recording_thread = threading.Thread(target=self.record_audio, daemon=True)
        self.recording_thread.start()
    
    def stop_recording(self):
        self.recording = False
        self.mic_button.set_label("🎤 Start")
        self.mic_button.get_style_context().remove_class("stop-button")
        self.mic_button.get_style_context().add_class("mic-button")
        self.status_indicator.set_color("gray" if not self.whisper_handler.model else "green")
        
        if self.temp_audio_file and os.path.exists(self.temp_audio_file) and AUDIO_AVAILABLE:
            # Transcribe and type in background
            self.status_label.set_text("Status: Processing...")
            self.status_indicator.set_color("yellow")
            threading.Thread(target=self.transcribe_audio, daemon=True).start()
    
    def record_audio(self):
        if not AUDIO_AVAILABLE:
            return
        try:
            fs = 16000
            channels = 1
            frames = []
            
            def callback(indata, frames_count, time, status):
                if status:
                    print(status)
                if self.recording:
                    frames.append(indata.copy())
                else:
                    raise sd.CallbackStop()
            
            try:
                with sd.InputStream(samplerate=fs, channels=channels, callback=callback):
                    while self.recording:
                        sd.sleep(100)
            except Exception as e:
                print(f"Recording error: {e}")
                GLib.idle_add(self.stop_recording)
                return
            
            if frames:
                audio = np.concatenate(frames, axis=0)
                write(self.temp_audio_file, fs, audio)
                
        except Exception as e:
            GLib.idle_add(self.status_label.set_text, f"Recording error: {e}")
            GLib.idle_add(self.status_indicator.set_color, "red")
        finally:
            GLib.idle_add(self.stop_recording)
    
    def transcribe_audio(self):
        def worker():
            try:
                success = self.whisper_handler.transcribe_and_type(self.temp_audio_file)
                if success:
                    GLib.idle_add(self.status_label.set_text, "Status: Typed at cursor!")
                    GLib.idle_add(self.status_indicator.set_color, "lightgreen")
                else:
                    GLib.idle_add(self.status_label.set_text, "Status: Ready")
                    GLib.idle_add(self.status_indicator.set_color, "green" if self.whisper_handler.model else "gray")
                # Reset mic button after a moment
                GLib.timeout_add(1500, lambda: (
                    self.mic_button.set_label("🎤 Start") if self.recording == False else None,
                    self.mic_button.get_style_context().remove_class("stop-button") if self.recording == False else None,
                    self.mic_button.get_style_context().add_class("mic-button") if self.recording == False else None,
                    False
                ))[2]
            except Exception as e:
                print(f"Transcribe audio error: {e}")
                GLib.idle_add(self.status_label.set_text, "Status: Ready")
                GLib.idle_add(self.status_indicator.set_color, "green" if self.whisper_handler.model else "gray")
        threading.Thread(target=worker, daemon=True).start()
    
    def toggle_recording(self):
        if not AUDIO_AVAILABLE:
            return False
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()
        return False  # For GLib.idle_add

    def setup_global_hotkey(self):
        # On Wayland, pynput GlobalHotKeys can't intercept global keypresses.
        # Instead we listen for SIGUSR1 so the user can bind any system shortcut
        # (e.g. GNOME Settings → Keyboard → Custom Shortcuts) to:
        #   pkill -USR1 -f whisper_button_app/app.py
        signal.signal(signal.SIGUSR1, lambda sig, frame: GLib.idle_add(self.toggle_recording))
        print(f"✓ Signal handler ready. PID: {os.getpid()}")
        print("  To trigger from a terminal:  kill -USR1 " + str(os.getpid()))
        print("  Add a GNOME custom shortcut with command:")
        print("    pkill -USR1 -f whisper_button_app/app.py")

    def on_hide_clicked(self, button):
        self.hide()

def main():
    print("\n🚀 Whisper Button application is starting...")
    
    # Check for dependencies and warn if missing
    missing = []
    if not AUDIO_AVAILABLE:
        missing.append("portaudio library and/or python sounddevice/numpy/scipy")
    
    if missing:
        print(f"Warning: Missing dependencies for audio recording: {', '.join(missing)}")
        print("The app will start but recording will be disabled.")
        print("To enable recording, install:")
        print("  sudo apt-get install libportaudio2")
        print("  pip install sounddevice numpy scipy")
    
    if not KEYBOARD_CONTROL_AVAILABLE:
        print("Warning: pynput not available - keyboard simulation disabled")
        print("To enable typing at cursor, install:")
        print("  pip install pynput")
    
    print("Initializing Whisper Button application...")
    
    try:
        app = WhisperControlWindow()
        print("✓ Application initialized successfully")
        print("📝 HOW TO USE:")
        print("   - Click in any text field you want to type into")
        print("   - Press Ctrl+Alt+R to start recording (focus stays where it is!)")
        print("   - Speak your text")
        print("   - Press Ctrl+Alt+R again to stop and transcribe")
        print("   - Text will be typed at your cursor position!")
        print("   - Press Escape to hide the control window")
        print("   - Press Ctrl+Alt+W to show the control window again")
        print("")
        print("💡 TIPS:")
        print("   - First run downloads Whisper model (~75MB) - one time only")
        print("   - Window is always-on-top when visible")
        print("   - Press Escape to hide window when focused")
        print("")
        print("Press Ctrl+C in this terminal to quit the application\n")
        
        Gtk.main()
    except Exception as e:
        print(f"Failed to start application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
