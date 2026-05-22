from __future__ import annotations

import ctypes
import os
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from .capture import capture_monitor_region, capture_window_region, list_monitors
from .config import AppConfig, Rect, load_config, save_config
from .hotkeys import HotkeyManager, listen_for_hotkey
from .llm import load_api_key_file, process_image_with_llm, process_text_with_llm
from .ocr import extract_ocr_text
from .region_picker import RegionPicker
from .resources import resource_path
from .tesseract import find_tesseract
from .tts import PocketTTSStreamer, UvxPocketTTSServer
from .voices import VoiceProfile, load_voice_profiles, save_voice_profiles, upsert_voice_profile, voice_profile_by_name
from .windows import WindowInfo, find_window_by_title, list_visible_windows

DEFAULT_VOICES = [
    "alba",
    "marius",
    "javert",
    "jean",
    "anna",
    "vera",
    "fantine",
    "charles",
    "paul",
    "george",
    "mary",
    "jane",
    "michael",
    "eve",
    "giovanni",
    "lola",
    "juergen",
    "rafael",
    "estelle",
]


class SeshatTtsApp(tk.Tk):
    def __init__(self) -> None:
        _set_windows_app_user_model_id()
        super().__init__()
        self.title("Seshat TTS")
        self.geometry("1060x920")
        self.minsize(900, 720)
        self.resizable(True, True)
        self.configure(bg="#07090d")
        self._set_window_icon()

        self.config_model = load_config()
        self.voice_profiles = load_voice_profiles()
        self.hotkeys = HotkeyManager()
        self.tts: PocketTTSStreamer | UvxPocketTTSServer | None = None
        self._recording_hotkey = False
        self._capture_lock = threading.Lock()
        self._monitor_values: dict[str, int] = {}
        self._window_values: dict[str, WindowInfo] = {}
        self._responsive_labels: list[tk.Widget] = []

        self._configure_theme()
        self._build_ui()
        self._load_values()
        self._refresh_targets()
        self._register_hotkey()
        self.after(250, self._poll_tts_status)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self) -> None:
        icon_path = resource_path("resources/seshat-tts.ico")
        png_path = resource_path("resources/character.png")
        try:
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
                self.iconbitmap(default=str(icon_path))
                self.wm_iconbitmap(str(icon_path))
            if png_path.exists():
                image = Image.open(png_path).convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
                self._icon_photo = ImageTk.PhotoImage(image)
                self.iconphoto(True, self._icon_photo)
        except (tk.TclError, OSError):
            pass

    def _build_ui(self) -> None:
        shell = ttk.Frame(self)
        shell.pack(fill=tk.BOTH, expand=True)
        self._scroll_canvas = tk.Canvas(shell, bg="#07090d", highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        root = ttk.Frame(self._scroll_canvas, padding=22)
        self._scroll_window = self._scroll_canvas.create_window((0, 0), window=root, anchor=tk.NW)
        root.bind("<Configure>", self._on_scroll_content_configure)
        self._scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        self._scroll_canvas.bind("<Enter>", lambda _event: self._bind_canvas_scroll())
        self._scroll_canvas.bind("<Leave>", lambda _event: self._unbind_canvas_scroll())
        root.bind("<Enter>", lambda _event: self._bind_canvas_scroll())

        header = ttk.Frame(root, style="Hero.TFrame", padding=18)
        header.pack(fill=tk.X, pady=(0, 18))
        header_icon = self._load_header_icon()
        if header_icon is not None:
            ttk.Label(header, image=header_icon, style="HeroIcon.TLabel").pack(side=tk.LEFT, padx=(0, 16))
        header_text = ttk.Frame(header, style="Hero.TFrame")
        header_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(header_text, text="Seshat TTS", style="Title.TLabel").pack(anchor=tk.W)
        self._wrap_label(
            header_text,
            text="One-hotkey OCR capture with Pocket TTS playback",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, fill=tk.X, pady=(2, 0))
        self._wrap_label(
            header_text,
            text="Developed by Scriptriva Inc. | support@scriptriva.com",
            style="Meta.TLabel",
        ).pack(anchor=tk.W, fill=tk.X, pady=(6, 0))
        ttk.Button(header, text="i", width=3, command=self.show_about, style="IconButton.TButton").pack(
            side=tk.RIGHT,
            padx=(12, 0),
        )

        capture_frame = self._section(root, "Capture", "Choose the active window or monitor and bind hotkeys.")
        capture_frame.columnconfigure(1, weight=1)

        ttk.Label(capture_frame, text="Mode", style="Field.TLabel").grid(row=0, column=0, sticky=tk.W, padx=8, pady=7)
        self.capture_mode_var = tk.StringVar()
        mode_box = ttk.Combobox(
            capture_frame,
            textvariable=self.capture_mode_var,
            state="readonly",
            values=["monitor", "window"],
        )
        mode_box.grid(row=0, column=1, sticky=tk.EW, padx=8, pady=7)

        ttk.Label(capture_frame, text="Monitor", style="Field.TLabel").grid(row=1, column=0, sticky=tk.W, padx=8, pady=7)
        self.monitor_var = tk.StringVar()
        self.monitor_box = ttk.Combobox(capture_frame, textvariable=self.monitor_var, state="readonly")
        self.monitor_box.grid(row=1, column=1, sticky=tk.EW, padx=8, pady=7)
        ttk.Button(capture_frame, text="Refresh", command=self._refresh_targets).grid(row=1, column=2, padx=8, pady=7)

        ttk.Label(capture_frame, text="Window", style="Field.TLabel").grid(row=2, column=0, sticky=tk.W, padx=8, pady=7)
        self.window_var = tk.StringVar()
        self.window_box = ttk.Combobox(capture_frame, textvariable=self.window_var, state="readonly")
        self.window_box.grid(row=2, column=1, sticky=tk.EW, padx=8, pady=7)

        ttk.Label(capture_frame, text="Read Hotkey", style="Field.TLabel").grid(row=3, column=0, sticky=tk.W, padx=8, pady=7)
        self.hotkey_var = tk.StringVar()
        self.hotkey_entry = self._hotkey_entry(capture_frame, self.hotkey_var, "read")
        self.hotkey_entry.grid(row=3, column=1, sticky=tk.EW, padx=8, pady=7)

        ttk.Label(capture_frame, text="Region Hotkey", style="Field.TLabel").grid(row=4, column=0, sticky=tk.W, padx=8, pady=7)
        self.capture_region_hotkey_var = tk.StringVar()
        self.capture_region_hotkey_entry = self._hotkey_entry(
            capture_frame, self.capture_region_hotkey_var, "capture-region"
        )
        self.capture_region_hotkey_entry.grid(row=4, column=1, sticky=tk.EW, padx=8, pady=7)

        ttk.Label(capture_frame, text="Stop Hotkey", style="Field.TLabel").grid(row=5, column=0, sticky=tk.W, padx=8, pady=7)
        self.stop_hotkey_var = tk.StringVar()
        self.stop_hotkey_entry = self._hotkey_entry(capture_frame, self.stop_hotkey_var, "stop-playback")
        self.stop_hotkey_entry.grid(row=5, column=1, sticky=tk.EW, padx=8, pady=7)

        ttk.Button(capture_frame, text="Apply", command=self._save_and_register, style="Accent.TButton").grid(
            row=5, column=2, padx=8, pady=7
        )

        rect_frame = self._section(root, "Capture Region", "Drag a precise reading region over the text to parse.")
        for col in range(8):
            rect_frame.columnconfigure(col, weight=1)

        self.left_var = tk.IntVar()
        self.top_var = tk.IntVar()
        self.width_var = tk.IntVar()
        self.height_var = tk.IntVar()
        self._number_field(rect_frame, "Left", self.left_var, 0, 0)
        self._number_field(rect_frame, "Top", self.top_var, 0, 2)
        self._number_field(rect_frame, "Width", self.width_var, 0, 4)
        self._number_field(rect_frame, "Height", self.height_var, 0, 6)
        ttk.Button(rect_frame, text="Select Region", command=self.select_region, style="Accent.TButton").grid(
            row=1, column=0, columnspan=2, sticky=tk.W, padx=8, pady=6
        )

        tts_frame = self._section(root, "OCR and Voice", "Select OCR, voice, playback, and backend settings.")
        tts_frame.columnconfigure(1, weight=1)

        ttk.Label(tts_frame, text="Tesseract", style="Field.TLabel").grid(row=0, column=0, sticky=tk.W, padx=8, pady=6)
        self.tesseract_var = tk.StringVar()
        ttk.Entry(tts_frame, textvariable=self.tesseract_var).grid(row=0, column=1, sticky=tk.EW, padx=8, pady=6)
        tesseract_buttons = ttk.Frame(tts_frame)
        tesseract_buttons.grid(row=0, column=2, sticky=tk.E, padx=8, pady=6)
        ttk.Button(tesseract_buttons, text="Detect", command=self._detect_tesseract).pack(side=tk.LEFT)
        ttk.Button(tesseract_buttons, text="Browse", command=self._browse_tesseract).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(tts_frame, text="Voice Source", style="Field.TLabel").grid(row=1, column=0, sticky=tk.W, padx=8, pady=6)
        self.voice_source_var = tk.StringVar()
        ttk.Combobox(
            tts_frame,
            textvariable=self.voice_source_var,
            state="readonly",
            values=["default", "custom-wav"],
        ).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=6)

        ttk.Label(tts_frame, text="Default Voice", style="Field.TLabel").grid(row=2, column=0, sticky=tk.W, padx=8, pady=6)
        self.default_voice_var = tk.StringVar()
        ttk.Combobox(
            tts_frame,
            textvariable=self.default_voice_var,
            state="readonly",
            values=DEFAULT_VOICES,
        ).grid(row=2, column=1, sticky=tk.EW, padx=8, pady=6)

        ttk.Label(tts_frame, text="Custom Voice", style="Field.TLabel").grid(row=3, column=0, sticky=tk.W, padx=8, pady=6)
        self.custom_voice_name_var = tk.StringVar()
        self.custom_voice_box = ttk.Combobox(
            tts_frame,
            textvariable=self.custom_voice_name_var,
            state="readonly",
        )
        self.custom_voice_box.grid(row=3, column=1, sticky=tk.EW, padx=8, pady=6)
        self.custom_voice_box.bind("<<ComboboxSelected>>", lambda _event: self._apply_selected_voice_profile())
        voice_buttons = ttk.Frame(tts_frame)
        voice_buttons.grid(row=3, column=2, sticky=tk.E, padx=8, pady=6)
        ttk.Button(voice_buttons, text="Manage", command=self.open_voice_manager).pack(side=tk.LEFT)

        ttk.Label(tts_frame, text="Voice File", style="Field.TLabel").grid(row=4, column=0, sticky=tk.W, padx=8, pady=6)
        self.voice_var = tk.StringVar()
        ttk.Entry(tts_frame, textvariable=self.voice_var).grid(row=4, column=1, sticky=tk.EW, padx=8, pady=6)
        ttk.Button(tts_frame, text="Browse", command=self._browse_voice).grid(row=4, column=2, padx=8, pady=6)

        ttk.Label(tts_frame, text="Language", style="Field.TLabel").grid(row=5, column=0, sticky=tk.W, padx=8, pady=6)
        self.language_var = tk.StringVar()
        ttk.Entry(tts_frame, textvariable=self.language_var, state="readonly").grid(
            row=5,
            column=1,
            sticky=tk.EW,
            padx=8,
            pady=6,
        )
        self.quantize_var = tk.BooleanVar()
        ttk.Checkbutton(tts_frame, text="Quantize", variable=self.quantize_var).grid(
            row=5, column=2, sticky=tk.W, padx=8, pady=6
        )

        ttk.Label(tts_frame, text="Volume", style="Field.TLabel").grid(row=6, column=0, sticky=tk.W, padx=8, pady=6)
        self.volume_var = tk.DoubleVar(value=100.0)
        volume_frame = ttk.Frame(tts_frame)
        volume_frame.grid(row=6, column=1, sticky=tk.EW, padx=8, pady=6)
        volume_frame.columnconfigure(0, weight=1)
        ttk.Scale(
            volume_frame,
            variable=self.volume_var,
            from_=0,
            to=300,
            command=lambda _value: self._update_volume_label(),
        ).grid(row=0, column=0, sticky=tk.EW)
        self.volume_label_var = tk.StringVar(value="100%")
        ttk.Label(volume_frame, textvariable=self.volume_label_var, width=6).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(tts_frame, text="Backend", style="Field.TLabel").grid(row=7, column=0, sticky=tk.W, padx=8, pady=6)
        self.tts_backend_var = tk.StringVar()
        ttk.Combobox(
            tts_frame,
            textvariable=self.tts_backend_var,
            state="readonly",
            values=_tts_backend_options(),
        ).grid(row=7, column=1, sticky=tk.EW, padx=8, pady=6)

        server_frame = ttk.Frame(tts_frame)
        server_frame.grid(row=7, column=2, sticky=tk.E, padx=8, pady=6)
        self.tts_port_var = tk.IntVar()
        ttk.Label(server_frame, text="Port", style="Field.TLabel").pack(side=tk.LEFT)
        ttk.Entry(server_frame, textvariable=self.tts_port_var, width=6).pack(side=tk.LEFT, padx=(6, 0))

        llm_frame = self._section(
            root,
            "Local LLM",
            "Optional OpenAI-compatible text cleanup or image-based text extraction before speech.",
            expanded=False,
        )
        llm_frame.columnconfigure(1, weight=1)

        self.llm_enabled_var = tk.BooleanVar()
        self._wrap_checkbutton(llm_frame, text="Route OCR through local OpenAI-compatible LLM", variable=self.llm_enabled_var).grid(
            row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=6
        )

        ttk.Label(llm_frame, text="Base URL", style="Field.TLabel").grid(row=1, column=0, sticky=tk.W, padx=8, pady=6)
        self.llm_base_url_var = tk.StringVar()
        ttk.Entry(llm_frame, textvariable=self.llm_base_url_var).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=6)

        ttk.Label(llm_frame, text="API Key", style="Field.TLabel").grid(row=2, column=0, sticky=tk.W, padx=8, pady=6)
        self.llm_api_key_var = tk.StringVar()
        ttk.Entry(llm_frame, textvariable=self.llm_api_key_var, show="*").grid(
            row=2, column=1, sticky=tk.EW, padx=8, pady=6
        )
        ttk.Button(llm_frame, text="Load api_key.txt", command=self._load_llm_api_key_file).grid(
            row=2, column=2, padx=8, pady=6
        )

        ttk.Label(llm_frame, text="Model", style="Field.TLabel").grid(row=3, column=0, sticky=tk.W, padx=8, pady=6)
        self.llm_model_var = tk.StringVar()
        ttk.Entry(llm_frame, textvariable=self.llm_model_var).grid(row=3, column=1, sticky=tk.EW, padx=8, pady=6)
        llm_limits = ttk.Frame(llm_frame)
        llm_limits.grid(row=3, column=2, sticky=tk.E, padx=8, pady=6)
        self.llm_timeout_var = tk.DoubleVar()
        self.llm_max_tokens_var = tk.IntVar()
        self.llm_disable_thinking_var = tk.BooleanVar()
        ttk.Label(llm_limits, text="Timeout", style="Field.TLabel").pack(side=tk.LEFT)
        ttk.Entry(llm_limits, textvariable=self.llm_timeout_var, width=5).pack(side=tk.LEFT, padx=(6, 10))
        ttk.Label(llm_limits, text="Tokens", style="Field.TLabel").pack(side=tk.LEFT)
        ttk.Entry(llm_limits, textvariable=self.llm_max_tokens_var, width=5).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Checkbutton(llm_frame, text="Disable thinking", variable=self.llm_disable_thinking_var).grid(
            row=4, column=0, columnspan=3, sticky=tk.W, padx=8, pady=6
        )
        self.llm_image_extraction_var = tk.BooleanVar()
        self._wrap_checkbutton(
            llm_frame,
            text="Use local LLM vision instead of Tesseract OCR",
            variable=self.llm_image_extraction_var,
        ).grid(row=5, column=0, columnspan=3, sticky=tk.W, padx=8, pady=6)

        ttk.Label(llm_frame, text="Prompt", style="Field.TLabel").grid(row=6, column=0, sticky=tk.NW, padx=8, pady=6)
        self.llm_prompt_box = tk.Text(
            llm_frame,
            height=3,
            wrap=tk.WORD,
            bg="#0b0f14",
            fg="#f4f7fb",
            insertbackground="#f4f7fb",
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#263241",
            highlightcolor="#4ea1ff",
            padx=8,
            pady=6,
            font=("Segoe UI", 10),
        )
        self.llm_prompt_box.grid(row=6, column=1, columnspan=2, sticky=tk.EW, padx=8, pady=6)

        actions = ttk.Frame(root, style="ActionBar.TFrame", padding=(12, 12))
        actions.pack(fill=tk.X, pady=(0, 12))
        ttk.Button(actions, text="Save Settings", command=self._save_and_register).pack(side=tk.LEFT)
        ttk.Button(actions, text="Capture Now", command=self.capture_now, style="Accent.TButton").pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(actions, text="Preload TTS", command=self.preload_tts).pack(side=tk.LEFT)
        ttk.Button(actions, text="Test TTS", command=self.test_tts).pack(side=tk.LEFT, padx=8)

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel").pack(fill=tk.X, pady=(0, 12))

        output_frame = self._section(root, "Last Extracted Text", "Parsed text and long status messages.", expanded=True)
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        self.text_box = tk.Text(
            output_frame,
            height=12,
            wrap=tk.WORD,
            bg="#0b0f14",
            fg="#f4f7fb",
            insertbackground="#f4f7fb",
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#263241",
            highlightcolor="#4ea1ff",
            padx=12,
            pady=10,
            font=("Segoe UI", 10),
        )
        self.text_box.grid(row=0, column=0, sticky=tk.NSEW)

    def _on_scroll_content_configure(self, _event: tk.Event) -> None:
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _on_scroll_canvas_configure(self, event: tk.Event) -> None:
        self._scroll_canvas.itemconfigure(self._scroll_window, width=event.width)
        wraplength = max(260, event.width - 180)
        for label in self._responsive_labels:
            try:
                label.configure(wraplength=wraplength)
            except tk.TclError:
                pass

    def _section(
        self,
        parent: ttk.Frame,
        title: str,
        description: str = "",
        *,
        expanded: bool = True,
    ) -> ttk.Frame:
        outer = ttk.Frame(parent, style="Card.TFrame", padding=1)
        outer.pack(fill=tk.X, pady=(0, 14))
        header = ttk.Frame(outer, style="CardHeader.TFrame", padding=(14, 12))
        header.pack(fill=tk.X)
        header.columnconfigure(0, weight=1)
        title_stack = ttk.Frame(header, style="CardHeader.TFrame")
        title_stack.grid(row=0, column=0, sticky=tk.EW)
        ttk.Label(title_stack, text=title, style="CardTitle.TLabel").pack(anchor=tk.W)
        if description:
            self._wrap_label(title_stack, text=description, style="CardSubtitle.TLabel").pack(
                anchor=tk.W,
                fill=tk.X,
                pady=(3, 0),
            )
        body = ttk.Frame(outer, style="CardBody.TFrame", padding=(14, 10, 14, 14))

        def toggle() -> None:
            if body.winfo_manager():
                body.pack_forget()
                toggle_button.configure(text="Show")
            else:
                body.pack(fill=tk.X)
                toggle_button.configure(text="Hide")
                self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

        toggle_button = ttk.Button(
            header,
            text="Hide" if expanded else "Show",
            width=7,
            command=toggle,
            style="Secondary.TButton",
        )
        toggle_button.grid(row=0, column=1, sticky=tk.NE, padx=(12, 0))
        if expanded:
            body.pack(fill=tk.X)
        return body

    def _wrap_label(self, parent: ttk.Frame, **kwargs: object) -> ttk.Label:
        label = ttk.Label(parent, **kwargs)
        self._responsive_labels.append(label)
        return label

    def _wrap_checkbutton(self, parent: ttk.Frame, **kwargs: object) -> ttk.Checkbutton:
        return ttk.Checkbutton(parent, **kwargs)

    def _on_mousewheel(self, event: tk.Event) -> None:
        widget_class = event.widget.winfo_class()
        if widget_class in {"Listbox", "TCombobox"}:
            return
        self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_canvas_scroll(self) -> None:
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_canvas_scroll(self) -> None:
        self._scroll_canvas.unbind_all("<MouseWheel>")

    def _configure_theme(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        self.option_add("*Font", ("Segoe UI", 10))
        self.option_add("*TCombobox*Listbox.background", "#101721")
        self.option_add("*TCombobox*Listbox.foreground", "#f4f7fb")
        self.option_add("*TCombobox*Listbox.selectBackground", "#255f99")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        bg = "#07090d"
        panel = "#101721"
        panel_alt = "#151d28"
        border = "#263241"
        border_soft = "#1b2734"
        text = "#f4f7fb"
        muted = "#99a6b8"
        muted_deep = "#6f7f92"
        accent = "#4ea1ff"
        accent_active = "#74b8ff"

        style.configure(".", background=bg, foreground=text, bordercolor=border, lightcolor=border, darkcolor=border)
        style.configure("TFrame", background=bg)
        style.configure("Hero.TFrame", background="#0d131d", borderwidth=1, relief=tk.SOLID)
        style.configure("Card.TFrame", background=border_soft, borderwidth=1, relief=tk.SOLID)
        style.configure("CardHeader.TFrame", background="#111a26")
        style.configure("CardBody.TFrame", background=panel)
        style.configure("ActionBar.TFrame", background="#0d131d", borderwidth=1, relief=tk.SOLID)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("HeroIcon.TLabel", background="#0d131d")
        style.configure("Title.TLabel", background="#0d131d", foreground=text, font=("Segoe UI Semibold", 23))
        style.configure("Subtitle.TLabel", background="#0d131d", foreground=muted, font=("Segoe UI", 10))
        style.configure("Meta.TLabel", background="#0d131d", foreground=muted_deep, font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 10))
        style.configure("Status.TLabel", background="#0c131c", foreground="#c9d5e3", padding=(10, 7))
        style.configure("CardTitle.TLabel", background="#111a26", foreground=text, font=("Segoe UI Semibold", 12))
        style.configure("CardSubtitle.TLabel", background="#111a26", foreground=muted, font=("Segoe UI", 9))
        style.configure("Field.TLabel", background=panel, foreground="#dce7f4", font=("Segoe UI Semibold", 9))
        style.configure("AboutPanel.TFrame", background=bg)
        style.configure("AboutFooter.TFrame", background=bg)
        style.configure("AboutTitle.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 20))
        style.configure("AboutSubtitle.TLabel", background=bg, foreground=muted, font=("Segoe UI", 10))
        style.configure("AboutSection.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 10))
        style.configure("AboutBody.TLabel", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("AboutLink.TLabel", background=bg, foreground="#74b8ff", font=("Segoe UI", 10))

        style.configure("TLabelframe", background=panel, foreground=text, bordercolor=border, relief=tk.SOLID)
        style.configure("TLabelframe.Label", background=bg, foreground=text, font=("Segoe UI Semibold", 10))
        style.configure(
            "TEntry",
            fieldbackground="#0b0f14",
            foreground=text,
            bordercolor=border,
            insertcolor=text,
            padding=(8, 6),
        )
        style.map("TEntry", fieldbackground=[("readonly", "#0b0f14")], foreground=[("readonly", text)])
        style.configure(
            "TCombobox",
            fieldbackground="#0b0f14",
            background=panel_alt,
            foreground=text,
            bordercolor=border,
            arrowcolor=accent,
            padding=(8, 6),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#0b0f14")],
            foreground=[("readonly", text)],
            selectbackground=[("readonly", "#0b0f14")],
            selectforeground=[("readonly", text)],
        )
        style.configure("TCheckbutton", background=panel, foreground=text, focuscolor=panel, padding=(2, 4))
        style.map("TCheckbutton", background=[("active", panel)], foreground=[("active", text)])
        style.configure(
            "TButton",
            background="#192231",
            foreground=text,
            bordercolor=border,
            focusthickness=0,
            padding=(12, 7),
        )
        style.map("TButton", background=[("active", "#243248"), ("pressed", "#0f1722")])
        style.configure(
            "Secondary.TButton",
            background="#121b28",
            foreground="#c9d5e3",
            bordercolor=border,
            focusthickness=0,
            padding=(10, 6),
        )
        style.map("Secondary.TButton", background=[("active", "#1d2a3d"), ("pressed", "#0d131d")])
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#06101a",
            bordercolor=accent,
            padding=(12, 7),
        )
        style.map("Accent.TButton", background=[("active", accent_active), ("pressed", "#2e83d1")])
        style.configure(
            "IconButton.TButton",
            background="#192231",
            foreground=text,
            bordercolor=border,
            focusthickness=0,
            padding=(8, 5),
            font=("Segoe UI Semibold", 10),
        )
        style.map("IconButton.TButton", background=[("active", "#243248"), ("pressed", "#0f1722")])

    def show_about(self) -> None:
        about = tk.Toplevel(self)
        about.title("About Seshat TTS")
        about.transient(self)
        about.configure(bg="#07090d")
        about.geometry("640x520")
        about.minsize(640, 520)
        about.maxsize(640, 520)
        about.resizable(False, False)
        try:
            about.iconbitmap(default=str(resource_path("resources/seshat-tts.ico")))
        except tk.TclError:
            pass

        frame = ttk.Frame(about, padding=22)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(4, weight=1)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Seshat TTS", style="AboutTitle.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(frame, text="Maintainer: Scriptriva Inc.", style="AboutSubtitle.TLabel").grid(
            row=1,
            column=0,
            sticky=tk.W,
            pady=(8, 0),
        )
        ttk.Label(
            frame,
            text="For support inquiries email: support@scriptriva.com",
            style="AboutSubtitle.TLabel",
            wraplength=580,
        ).grid(
            row=2,
            column=0,
            sticky=tk.W,
            pady=(3, 18),
        )
        ttk.Label(
            frame,
            text="Project license: Scriptriva Public Source License 1.0",
            style="AboutSection.TLabel",
            wraplength=580,
        ).grid(row=3, column=0, sticky=tk.W)

        content = ttk.Frame(frame, style="AboutPanel.TFrame", padding=(0, 12, 0, 0))
        content.grid(row=4, column=0, sticky=tk.NSEW)
        content.columnconfigure(0, weight=1)

        self._about_link(content, "Open Seshat TTS license", resource_path("LICENSE"))
        self._about_link(
            content,
            "Open Pocket TTS MIT license",
            "https://github.com/kyutai-labs/pocket-tts/blob/main/LICENSE",
        )
        self._about_link(
            content,
            "Open third-party notices",
            resource_path("THIRD_PARTY_NOTICES.md"),
        )

        ttk.Label(content, text="Reuse Notes", style="AboutSection.TLabel").pack(anchor=tk.W, pady=(18, 6))
        details = (
            "capture.py and ocr.py isolate OCR capture and preprocessing.\n"
            "tts.py isolates Pocket TTS playback and stream cancellation.\n"
            "llm.py isolates OpenAI-compatible local LLM cleanup.\n"
            "config.py isolates persisted GUI/runtime settings.\n\n"
            "Third-party components retain their own licenses. See README.md, LICENSE, and THIRD_PARTY_NOTICES.md."
        )
        ttk.Label(content, text=details, wraplength=580, justify=tk.LEFT, style="AboutBody.TLabel").pack(
            anchor=tk.W,
            fill=tk.X,
        )

        footer = ttk.Frame(frame, style="AboutFooter.TFrame")
        footer.grid(row=5, column=0, sticky=tk.EW, pady=(18, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Close", command=about.destroy, style="Accent.TButton").grid(row=0, column=1, sticky=tk.E)
        about.update_idletasks()
        self._center_child_window(about, 640, 520)

    def _about_link(self, parent: ttk.Frame, text: str, target: str | Path) -> None:
        label = ttk.Label(parent, text=text, foreground="#74b8ff", cursor="hand2", style="AboutLink.TLabel")
        label.pack(anchor=tk.W, pady=(6, 0))
        label.bind("<Button-1>", lambda _event: self._open_about_target(target))

    def _open_about_target(self, target: str | Path) -> None:
        if isinstance(target, Path):
            if target.exists():
                os.startfile(target)
            return
        webbrowser.open(target)

    def _center_child_window(self, window: tk.Toplevel, width: int, height: int) -> None:
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - width) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _load_header_icon(self) -> ImageTk.PhotoImage | None:
        path = resource_path("resources/logo.png")
        if not path.exists():
            return None
        try:
            image = Image.open(path).convert("RGBA").resize((56, 56), Image.Resampling.LANCZOS)
            self._header_icon = ImageTk.PhotoImage(image)
            return self._header_icon
        except Exception:
            return None

    def _number_field(self, parent: ttk.Frame, label: str, variable: tk.IntVar, row: int, column: int) -> None:
        ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=column, sticky=tk.W, padx=8, pady=6)
        ttk.Entry(parent, textvariable=variable, width=8).grid(row=row, column=column + 1, sticky=tk.EW, padx=8, pady=6)

    def _hotkey_entry(self, parent: ttk.Frame, variable: tk.StringVar, name: str) -> ttk.Entry:
        entry = ttk.Entry(parent, textvariable=variable, state="readonly")
        entry.bind("<Button-1>", lambda _event: self._start_hotkey_recording(name, variable))
        entry.bind("<FocusIn>", lambda _event: self._start_hotkey_recording(name, variable))
        return entry

    def _load_values(self) -> None:
        cfg = self.config_model
        self.capture_mode_var.set(cfg.capture_mode)
        self.hotkey_var.set(cfg.hotkey)
        self.capture_region_hotkey_var.set(cfg.capture_region_hotkey)
        self.stop_hotkey_var.set(cfg.stop_hotkey)
        self.left_var.set(cfg.dialogue_rect.left)
        self.top_var.set(cfg.dialogue_rect.top)
        self.width_var.set(cfg.dialogue_rect.width)
        self.height_var.set(cfg.dialogue_rect.height)
        self.tesseract_var.set(cfg.tesseract_cmd)
        self.voice_source_var.set(cfg.voice_source)
        self.default_voice_var.set(cfg.default_voice)
        self._refresh_voice_profiles()
        self.custom_voice_name_var.set(cfg.custom_voice_name)
        self.voice_var.set(cfg.voice_path)
        self.language_var.set("english")
        self.quantize_var.set(cfg.quantize_tts)
        self.volume_var.set(cfg.volume_gain * 100)
        self._update_volume_label()
        backend = cfg.tts_backend if cfg.tts_backend in _tts_backend_options() else "uvx-server"
        self.tts_backend_var.set(backend)
        self.tts_port_var.set(cfg.tts_port)
        self.llm_enabled_var.set(cfg.llm_enabled)
        self.llm_base_url_var.set(cfg.llm_base_url)
        self.llm_api_key_var.set(cfg.llm_api_key)
        self.llm_model_var.set(cfg.llm_model)
        self.llm_timeout_var.set(cfg.llm_timeout)
        self.llm_max_tokens_var.set(cfg.llm_max_tokens)
        self.llm_disable_thinking_var.set(cfg.llm_disable_thinking)
        self.llm_image_extraction_var.set(cfg.llm_image_extraction)
        self.llm_prompt_box.delete("1.0", tk.END)
        self.llm_prompt_box.insert("1.0", cfg.llm_system_prompt)
        self._set_text(cfg.last_text)

    def _refresh_targets(self) -> None:
        self._refresh_monitors()
        self._refresh_windows()

    def _refresh_monitors(self) -> None:
        monitors = list_monitors()
        self._monitor_values = {monitor.label: monitor.index for monitor in monitors}
        values = list(self._monitor_values)
        self.monitor_box["values"] = values
        selected = next((label for label, index in self._monitor_values.items() if index == self.config_model.monitor_index), "")
        if not selected and values:
            selected = values[0]
        self.monitor_var.set(selected)

    def _refresh_windows(self) -> None:
        windows = list_visible_windows()
        self._window_values = {window.label: window for window in windows}
        values = list(self._window_values)
        self.window_box["values"] = values
        selected = next(
            (label for label, window in self._window_values.items() if window.title == self.config_model.window_title),
            "",
        )
        if not selected:
            selected = next(
                (label for label, window in self._window_values.items() if "neverwinter nights" in window.title.casefold()),
                "",
            )
        if not selected and values:
            selected = values[0]
        self.window_var.set(selected)

    def _browse_tesseract(self) -> None:
        path = filedialog.askopenfilename(title="Select tesseract.exe", filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if path:
            self.tesseract_var.set(path)

    def _detect_tesseract(self) -> None:
        path = find_tesseract()
        if path:
            self.tesseract_var.set(path)
            self.status_var.set(f"Tesseract found: {path}")
        else:
            self.status_var.set("Tesseract not found. Install it or browse to tesseract.exe.")

    def _load_llm_api_key_file(self) -> None:
        key = load_api_key_file()
        if key:
            self.llm_api_key_var.set(key)
            self.status_var.set("Loaded api_key.txt.")
        else:
            self.status_var.set("api_key.txt was not found or was empty.")

    def _browse_voice(self) -> None:
        path = filedialog.askopenfilename(
            title="Select voice audio",
            filetypes=[("Audio", "*.wav *.mp3"), ("Wave", "*.wav"), ("MP3", "*.mp3"), ("All", "*.*")],
        )
        if path:
            self.voice_var.set(path)
            self.voice_source_var.set("custom-wav")
            name = simpledialog.askstring(
                "Custom voice name",
                "Name this custom voice:",
                initialvalue=Path(path).stem,
                parent=self,
            )
            if name:
                self._save_voice_profile(name.strip(), path)
            else:
                self.custom_voice_name_var.set(Path(path).stem)

    def _refresh_voice_profiles(self) -> None:
        self.voice_profiles = load_voice_profiles()
        values = [profile.name for profile in self.voice_profiles]
        if hasattr(self, "custom_voice_box"):
            self.custom_voice_box["values"] = values

    def _save_voice_profile(self, name: str, path: str) -> None:
        if not name:
            return
        self.voice_profiles = upsert_voice_profile(VoiceProfile(name=name, path=path))
        self._refresh_voice_profiles()
        self.custom_voice_name_var.set(name)
        self.voice_var.set(path)

    def _apply_selected_voice_profile(self) -> None:
        profile = voice_profile_by_name(self.custom_voice_name_var.get(), self.voice_profiles)
        if profile is not None:
            self.voice_var.set(profile.path)
            self.voice_source_var.set("custom-wav")

    def open_voice_manager(self) -> None:
        manager = tk.Toplevel(self)
        manager.title("Custom Voices")
        manager.transient(self)
        manager.configure(bg="#07090d")
        manager.geometry("700x420")
        manager.minsize(620, 360)
        try:
            manager.iconbitmap(default=str(resource_path("resources/seshat-tts.ico")))
        except tk.TclError:
            pass

        frame = ttk.Frame(manager, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        voice_list = tk.Listbox(
            frame,
            bg="#0b0f14",
            fg="#f4f7fb",
            selectbackground="#255f99",
            selectforeground="#ffffff",
            highlightthickness=1,
            highlightbackground="#263241",
            relief=tk.FLAT,
            exportselection=False,
        )
        voice_list.grid(row=0, column=0, rowspan=5, sticky=tk.NSEW, padx=(0, 12))
        frame.columnconfigure(0, minsize=200)

        name_var = tk.StringVar()
        path_var = tk.StringVar()
        ttk.Label(frame, text="Name").grid(row=0, column=1, sticky=tk.SW, pady=(0, 4))
        ttk.Entry(frame, textvariable=name_var).grid(row=1, column=1, sticky=tk.EW, pady=(0, 10))
        ttk.Label(frame, text="WAV, MP3, or cached safetensors").grid(row=2, column=1, sticky=tk.SW, pady=(0, 4))
        ttk.Entry(frame, textvariable=path_var).grid(row=3, column=1, sticky=tk.EW)
        ttk.Button(
            frame,
            text="Browse",
            command=lambda: self._browse_voice_for_manager(path_var, name_var),
        ).grid(row=3, column=2, padx=(8, 0))

        def refresh_list() -> None:
            self._refresh_voice_profiles()
            voice_list.delete(0, tk.END)
            for profile in self.voice_profiles:
                voice_list.insert(tk.END, profile.name)

        def on_select(_event: tk.Event | None = None) -> None:
            selection = voice_list.curselection()
            if not selection:
                return
            profile = self.voice_profiles[selection[0]]
            name_var.set(profile.name)
            path_var.set(profile.path)

        def save_current() -> None:
            name = name_var.get().strip()
            path = path_var.get().strip()
            if not name or not path:
                messagebox.showerror("Custom voice", "Name and path are required.", parent=manager)
                return
            self._save_voice_profile(name, path)
            refresh_list()

        def use_current() -> None:
            save_current()
            self.custom_voice_name_var.set(name_var.get().strip())
            self.voice_var.set(path_var.get().strip())
            self.voice_source_var.set("custom-wav")
            manager.destroy()

        def delete_current() -> None:
            selection = voice_list.curselection()
            if not selection:
                return
            selected_name = self.voice_profiles[selection[0]].name
            self.voice_profiles = [profile for profile in self.voice_profiles if profile.name != selected_name]
            save_voice_profiles(self.voice_profiles)
            refresh_list()
            name_var.set("")
            path_var.set("")

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=1, columnspan=2, sticky=tk.EW, pady=(16, 0))
        ttk.Button(buttons, text="Save", command=save_current).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Use Selected", command=use_current, style="Accent.TButton").pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="Delete", command=delete_current).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Close", command=manager.destroy).pack(side=tk.RIGHT)

        voice_list.bind("<<ListboxSelect>>", on_select)
        refresh_list()

    def _browse_voice_for_manager(self, path_var: tk.StringVar, name_var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Select voice audio or cache",
            filetypes=[
                ("Voice files", "*.wav *.mp3 *.safetensors"),
                ("Audio", "*.wav *.mp3"),
                ("Cached voice", "*.safetensors"),
                ("All", "*.*"),
            ],
        )
        if path:
            path_var.set(path)
            if not name_var.get().strip():
                name_var.set(Path(path).stem)

    def _read_config_from_ui(self) -> AppConfig:
        monitor_index = self._monitor_values.get(self.monitor_var.get(), self.config_model.monitor_index)
        selected_window = self._window_values.get(self.window_var.get())
        return AppConfig(
            capture_mode=self.capture_mode_var.get().strip() or "monitor",
            monitor_index=monitor_index,
            window_title=selected_window.title if selected_window else self.config_model.window_title,
            hotkey=self.hotkey_var.get().strip() or "ctrl+alt+n",
            capture_region_hotkey=self.capture_region_hotkey_var.get().strip() or "ctrl+alt+r",
            stop_hotkey=self.stop_hotkey_var.get().strip() or "ctrl+alt+s",
            dialogue_rect=Rect(
                left=self.left_var.get(),
                top=self.top_var.get(),
                width=self.width_var.get(),
                height=self.height_var.get(),
            ),
            tesseract_cmd=self.tesseract_var.get().strip(),
            voice_source=self.voice_source_var.get().strip() or "default",
            default_voice=self.default_voice_var.get().strip() or "alba",
            custom_voice_name=self.custom_voice_name_var.get().strip(),
            voice_path=self.voice_var.get().strip(),
            language="english",
            quantize_tts=self.quantize_var.get(),
            volume_gain=self.volume_var.get() / 100,
            tts_backend=self.tts_backend_var.get().strip() or "uvx-server",
            tts_host="localhost",
            tts_port=self.tts_port_var.get(),
            llm_enabled=self.llm_enabled_var.get(),
            llm_base_url=self.llm_base_url_var.get().strip() or "http://127.0.0.1:8000/v1",
            llm_api_key=self.llm_api_key_var.get().strip(),
            llm_model=self.llm_model_var.get().strip() or "unsloth",
            llm_timeout=self.llm_timeout_var.get(),
            llm_max_tokens=self.llm_max_tokens_var.get(),
            llm_disable_thinking=self.llm_disable_thinking_var.get(),
            llm_image_extraction=self.llm_image_extraction_var.get(),
            llm_system_prompt=self.llm_prompt_box.get("1.0", tk.END).strip(),
            last_text=self.text_box.get("1.0", tk.END).strip(),
        )

    def _save_and_register(self) -> None:
        try:
            self.config_model = self._read_config_from_ui()
            save_config(self.config_model)
            self._register_hotkey()
            self.tts = None
            self.status_var.set("Settings saved.")
        except Exception as exc:
            messagebox.showerror("Settings error", str(exc))

    def _register_hotkey(self) -> None:
        try:
            self.hotkeys.register("read", self.config_model.hotkey, self.capture_now)
            self.hotkeys.register(
                "capture-region",
                self.config_model.capture_region_hotkey,
                lambda: self.after(0, self.select_region),
            )
            self.hotkeys.register(
                "stop-playback",
                self.config_model.stop_hotkey,
                lambda: self.after(0, self.stop_playback),
            )
            self.status_var.set(
                "Listening for "
                f"{self.config_model.hotkey}, "
                f"{self.config_model.capture_region_hotkey}, "
                f"{self.config_model.stop_hotkey}."
            )
        except Exception as exc:
            self.status_var.set(f"Hotkey error: {exc}")

    def _start_hotkey_recording(self, name: str, variable: tk.StringVar) -> None:
        if self._recording_hotkey:
            return
        self._recording_hotkey = True
        self.hotkeys.unregister()
        variable.set("Press keys...")
        self.status_var.set(f"Listening for {name} hotkey input...")
        threading.Thread(target=self._record_hotkey_worker, args=(variable,), daemon=True).start()

    def _record_hotkey_worker(self, variable: tk.StringVar) -> None:
        try:
            hotkey = listen_for_hotkey()
            self.after(0, lambda: self._finish_hotkey_recording(variable, hotkey))
        except Exception as exc:
            self.after(0, lambda: self._cancel_hotkey_recording(str(exc)))

    def _finish_hotkey_recording(self, variable: tk.StringVar, hotkey: str) -> None:
        variable.set(hotkey)
        self._recording_hotkey = False
        self._save_and_register()
        self.status_var.set(f"Hotkey set to {hotkey}.")

    def _cancel_hotkey_recording(self, reason: str) -> None:
        self._recording_hotkey = False
        self._register_hotkey()
        self.status_var.set(f"Hotkey recording failed: {reason}")

    def capture_now(self) -> None:
        if self._capture_lock.locked():
            return
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def stop_playback(self) -> None:
        if self.tts is not None:
            self.tts.stop()
        self.status_var.set("Playback stopped.")

    def select_region(self) -> None:
        try:
            cfg = self._read_config_from_ui()
            bounds = self._target_bounds(cfg)
            self.status_var.set("Drag over the capture region. Press Escape to cancel.")
            RegionPicker(self, bounds, self._apply_selected_region)
        except Exception as exc:
            messagebox.showerror("Region selection error", str(exc))

    def _apply_selected_region(self, rect: Rect) -> None:
        relative = self._relative_to_target(rect, self._read_config_from_ui())
        self.left_var.set(relative.left)
        self.top_var.set(relative.top)
        self.width_var.set(relative.width)
        self.height_var.set(relative.height)
        self._save_and_register()
        self.status_var.set(f"Selected region {relative.width}x{relative.height} at {relative.left},{relative.top}.")

    def preload_tts(self) -> None:
        try:
            cfg = self._read_config_from_ui()
            self.config_model = cfg
            save_config(cfg)
            self._ensure_tts(cfg).preload_async()
            self.status_var.set("TTS preload started.")
        except Exception as exc:
            messagebox.showerror("TTS preload error", str(exc))

    def test_tts(self) -> None:
        try:
            cfg = self._read_config_from_ui()
            self.config_model = cfg
            save_config(cfg)
            self._ensure_tts(cfg).test_async()
            self.status_var.set("TTS test started.")
        except Exception as exc:
            messagebox.showerror("TTS test error", str(exc))

    def _capture_worker(self) -> None:
        with self._capture_lock:
            try:
                cfg = self._read_config_from_ui()
                if self.tts is not None:
                    self.tts.stop()
                self._set_status("Capturing selected region...")
                image = self._capture_image(cfg)
                if cfg.llm_image_extraction:
                    self._set_status("Extracting text from image with local LLM...")
                    text = process_image_with_llm(
                        image,
                        base_url=cfg.llm_base_url,
                        api_key=cfg.llm_api_key,
                        model=cfg.llm_model,
                        timeout=cfg.llm_timeout,
                        max_tokens=cfg.llm_max_tokens,
                        disable_thinking=cfg.llm_disable_thinking,
                    )
                else:
                    self._set_status("Running OCR...")
                    text = extract_ocr_text(image, cfg.tesseract_cmd)
                    if cfg.llm_enabled:
                        self._set_status("Routing OCR text through local LLM...")
                        text = process_text_with_llm(
                            text,
                            enabled=True,
                            base_url=cfg.llm_base_url,
                            api_key=cfg.llm_api_key,
                            model=cfg.llm_model,
                            system_prompt=cfg.llm_system_prompt,
                            timeout=cfg.llm_timeout,
                            max_tokens=cfg.llm_max_tokens,
                            disable_thinking=cfg.llm_disable_thinking,
                        )
                if not text:
                    self._set_status("No dialogue text found.")
                    return
                cfg.last_text = text
                self.config_model = cfg
                save_config(cfg)
                self.after(0, lambda: self._set_text(text))
                self._ensure_tts(cfg).speak_async(text)
            except Exception as exc:
                self._set_status(f"Capture error: {exc}")

    def _capture_image(self, cfg: AppConfig):
        if cfg.capture_mode == "window":
            selected = self._window_values.get(self.window_var.get())
            window = selected or find_window_by_title(cfg.window_title)
            if window is None:
                raise ValueError("Selected window is not available. Refresh windows and select it again.")
            return capture_window_region(window.hwnd, cfg.dialogue_rect)
        return capture_monitor_region(cfg.monitor_index, cfg.dialogue_rect)

    def _target_bounds(self, cfg: AppConfig) -> Rect:
        if cfg.capture_mode == "window":
            selected = self._window_values.get(self.window_var.get())
            window = selected or find_window_by_title(cfg.window_title)
            if window is None:
                raise ValueError("Selected window is not available. Refresh windows and select it again.")
            return Rect(left=window.left, top=window.top, width=window.width, height=window.height)
        monitor_index = self._monitor_values.get(self.monitor_var.get(), cfg.monitor_index)
        monitor = next((item for item in list_monitors() if item.index == monitor_index), None)
        if monitor is None:
            raise ValueError(f"Monitor {monitor_index} is not available.")
        return Rect(left=monitor.left, top=monitor.top, width=monitor.width, height=monitor.height)

    def _relative_to_target(self, absolute: Rect, cfg: AppConfig) -> Rect:
        target = self._target_bounds(cfg)
        return Rect(
            left=absolute.left - target.left,
            top=absolute.top - target.top,
            width=absolute.width,
            height=absolute.height,
        )

    def _ensure_tts(self, cfg: AppConfig) -> PocketTTSStreamer | UvxPocketTTSServer:
        voice_path: str | Path = cfg.voice_path.strip()
        if voice_path:
            path = Path(voice_path)
            voice_path = path if path.is_absolute() else Path.cwd() / path
        if self.tts is None:
            if cfg.tts_backend == "python-api":
                self.tts = PocketTTSStreamer(
                    voice_path,
                    cfg.language,
                    cfg.quantize_tts,
                    cfg.voice_source,
                    cfg.default_voice,
                    cfg.custom_voice_name,
                    cfg.volume_gain,
                )
            else:
                self.tts = UvxPocketTTSServer(
                    voice_path,
                    cfg.language,
                    cfg.quantize_tts,
                    cfg.tts_host,
                    cfg.tts_port,
                    cfg.voice_source,
                    cfg.default_voice,
                    cfg.custom_voice_name,
                    cfg.volume_gain,
                )
        else:
            self.tts.volume_gain = cfg.volume_gain
        return self.tts

    def _update_volume_label(self) -> None:
        if hasattr(self, "volume_label_var"):
            self.volume_label_var.set(f"{int(round(self.volume_var.get()))}%")

    def _set_text(self, text: str) -> None:
        self.text_box.delete("1.0", tk.END)
        self.text_box.insert("1.0", text)

    def _set_status(self, status: str) -> None:
        self.after(0, lambda: self.status_var.set(status))

    def _poll_tts_status(self) -> None:
        if self.tts is not None:
            while not self.tts.status_queue.empty():
                status = self.tts.status_queue.get_nowait()
                self.status_var.set(status.splitlines()[0])
                if "\n" in status or len(status) > 180:
                    self._set_text(status)
        self.after(250, self._poll_tts_status)

    def _on_close(self) -> None:
        self.hotkeys.unregister()
        if self.tts is not None:
            self.tts.close()
        self.destroy()


def main() -> None:
    app = SeshatTtsApp()
    app.mainloop()


def _set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Seshat.TTS.Desktop")
    except Exception:
        pass


def _tts_backend_options() -> list[str]:
    if getattr(sys, "frozen", False):
        return ["uvx-server"]
    return ["uvx-server", "python-api"]


if __name__ == "__main__":
    main()
