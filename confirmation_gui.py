"""
confirmation_gui.py - Native Tamil Windows GUI confirmation and notification system for Daily GitHub Agent V1.

Uses Python standard library tkinter.
Provides:
  - show_confirmation(): Tamil confirmation popup [ இயக்கவும் ] [ ரத்து ]
  - show_success(): Tamil success notification [ சரி ]
  - show_failure(): Tamil failure notification [ சரி ]
  - show_dry_run_result(): Tamil dry-run notification [ சரி ]
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional, Tuple

logger = logging.getLogger("daily_github_agent")

# Standard Tamil String Constants
APP_TITLE = "Daily GitHub Agent"

CONFIRMATION_MESSAGE = "இன்று GitHub task-ஐ இயக்கவா?"
CONFIRM_BUTTON_TEXT = "இயக்கவும்"
CANCEL_BUTTON_TEXT = "ரத்து"

SUCCESS_MESSAGE = "✅ பணி முடிந்தது!\n\nஇன்றைய GitHub task வெற்றிகரமாக\nமுடிக்கப்பட்டது."
FAILURE_MESSAGE = "❌ பணி முடியவில்லை!\n\nஇன்றைய GitHub task-ஐ முடிக்க\nமுடியவில்லை.\n\nமேலும் தகவலுக்கு log-ஐ பார்க்கவும்."
DRY_RUN_MESSAGE = "🧪 சோதனை முடிந்தது!\n\nDry-run வெற்றிகரமாக முடிந்தது.\nGitHub-க்கு எந்த மாற்றமும் அனுப்பப்படவில்லை."
OK_BUTTON_TEXT = "சரி"

# Preferred Tamil fonts on Windows
TAMIL_FONTS = ("Nirmala UI", "Latha", "Vijaya", "Segoe UI", "Arial")


def get_tamil_font(size: int = 12, weight: str = "normal") -> Tuple[str, int, str]:
    """
    Return the best available font family tuple for rendering Tamil script.
    """
    try:
        root = tk._default_root
        if root:
            available_families = tkfont.families(root)
            for f in TAMIL_FONTS:
                if f in available_families:
                    return (f, size, weight)
    except Exception:
        pass
    return ("Nirmala UI", size, weight)


def center_window(window: tk.Tk | tk.Toplevel, width: int = 420, height: int = 240) -> None:
    """
    Center a Tkinter window on the primary screen.
    """
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def show_confirmation(
    title: str = APP_TITLE,
    message: str = CONFIRMATION_MESSAGE,
    confirm_text: str = CONFIRM_BUTTON_TEXT,
    cancel_text: str = CANCEL_BUTTON_TEXT,
) -> bool:
    """
    Display a native Windows GUI confirmation popup in Tamil.

    Returns:
        True if user clicks 'இயக்கவும்' (Confirm),
        False if user clicks 'ரத்து' (Cancel) or closes the window.
    """
    user_confirmed = False

    try:
        root = tk.Tk()
        root.title(title)
        root.resizable(False, False)
        root.configure(bg="#F3F4F6")

        # Fonts
        title_font = ("Nirmala UI", 11, "bold")
        msg_font = ("Nirmala UI", 13, "normal")
        btn_font = ("Nirmala UI", 11, "bold")

        # Outer Frame
        frame = tk.Frame(root, bg="#F3F4F6", padx=24, pady=20)
        frame.pack(fill="both", expand=True)

        # Header / Icon
        header_frame = tk.Frame(frame, bg="#F3F4F6")
        header_frame.pack(fill="x", pady=(0, 10))

        app_label = tk.Label(
            header_frame,
            text=f"🚀 {title}",
            font=title_font,
            fg="#374151",
            bg="#F3F4F6",
        )
        app_label.pack(anchor="w")

        # Divider
        sep = tk.Frame(frame, height=1, bg="#E5E7EB")
        sep.pack(fill="x", pady=(0, 16))

        # Main Tamil Prompt Message
        msg_label = tk.Label(
            frame,
            text=message,
            font=msg_font,
            fg="#111827",
            bg="#F3F4F6",
            justify="center",
            wraplength=360,
        )
        msg_label.pack(pady=(5, 20), expand=True)

        # Button callbacks
        def on_confirm() -> None:
            nonlocal user_confirmed
            user_confirmed = True
            root.destroy()

        def on_cancel() -> None:
            nonlocal user_confirmed
            user_confirmed = False
            root.destroy()

        # Keyboard shortcuts
        root.bind("<Return>", lambda e: on_confirm())
        root.bind("<KP_Enter>", lambda e: on_confirm())
        root.bind("<Escape>", lambda e: on_cancel())
        root.protocol("WM_DELETE_WINDOW", on_cancel)

        # Buttons Frame
        btn_frame = tk.Frame(frame, bg="#F3F4F6")
        btn_frame.pack(fill="x", pady=(10, 0))

        # Confirm Button (Primary Blue/Indigo)
        confirm_btn = tk.Button(
            btn_frame,
            text=confirm_text,
            font=btn_font,
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#1D4ED8",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=on_confirm,
        )
        confirm_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))

        # Cancel Button (Neutral Gray)
        cancel_btn = tk.Button(
            btn_frame,
            text=cancel_text,
            font=btn_font,
            bg="#E5E7EB",
            fg="#374151",
            activebackground="#D1D5DB",
            activeforeground="#111827",
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=on_cancel,
        )
        cancel_btn.pack(side="right", expand=True, fill="x", padx=(8, 0))

        # Bring window to front
        center_window(root, width=420, height=230)
        root.lift()
        root.attributes("-topmost", True)
        root.after_idle(root.attributes, "-topmost", False)
        confirm_btn.focus_set()

        root.mainloop()
    except Exception as e:
        logger.error(f"Error displaying confirmation GUI: {e}")
        # In non-interactive environments, default to False for safety
        return False

    return user_confirmed


def _show_message_dialog(
    title: str,
    message: str,
    button_text: str = OK_BUTTON_TEXT,
    is_success: bool = True,
    is_dry_run: bool = False,
) -> None:
    """
    Helper to render a clean, styled message popup with Tamil text.
    """
    try:
        root = tk.Tk()
        root.title(title)
        root.resizable(False, False)
        root.configure(bg="#F3F4F6")

        title_font = ("Nirmala UI", 11, "bold")
        msg_font = ("Nirmala UI", 12, "normal")
        btn_font = ("Nirmala UI", 11, "bold")

        # Color schemes based on status
        if is_dry_run:
            accent_color = "#8B5CF6"  # Purple for dry run
            active_color = "#7C3AED"
            tag_text = "சோதனை முறை (Dry Run)"
        elif is_success:
            accent_color = "#059669"  # Green for success
            active_color = "#047857"
            tag_text = "வெற்றி (Success)"
        else:
            accent_color = "#DC2626"  # Red for failure
            active_color = "#B91C1C"
            tag_text = "பிழை (Failed)"

        frame = tk.Frame(root, bg="#F3F4F6", padx=24, pady=20)
        frame.pack(fill="both", expand=True)

        # Header
        header_frame = tk.Frame(frame, bg="#F3F4F6")
        header_frame.pack(fill="x", pady=(0, 8))

        app_label = tk.Label(
            header_frame,
            text=title,
            font=title_font,
            fg="#4B5563",
            bg="#F3F4F6",
        )
        app_label.pack(side="left")

        tag_label = tk.Label(
            header_frame,
            text=tag_text,
            font=("Nirmala UI", 9, "bold"),
            fg=accent_color,
            bg="#F3F4F6",
        )
        tag_label.pack(side="right")

        # Divider
        sep = tk.Frame(frame, height=1, bg="#E5E7EB")
        sep.pack(fill="x", pady=(0, 14))

        # Main Message
        msg_label = tk.Label(
            frame,
            text=message,
            font=msg_font,
            fg="#1F2937",
            bg="#F3F4F6",
            justify="center",
            wraplength=380,
        )
        msg_label.pack(pady=(4, 18), expand=True)

        def on_close() -> None:
            root.destroy()

        root.bind("<Return>", lambda e: on_close())
        root.bind("<KP_Enter>", lambda e: on_close())
        root.bind("<Escape>", lambda e: on_close())
        root.protocol("WM_DELETE_WINDOW", on_close)

        btn_frame = tk.Frame(frame, bg="#F3F4F6")
        btn_frame.pack(fill="x", pady=(8, 0))

        ok_btn = tk.Button(
            btn_frame,
            text=button_text,
            font=btn_font,
            bg=accent_color,
            fg="#FFFFFF",
            activebackground=active_color,
            activeforeground="#FFFFFF",
            relief="flat",
            padx=28,
            pady=8,
            cursor="hand2",
            command=on_close,
        )
        ok_btn.pack(side="right", padx=0)

        center_window(root, width=440, height=260)
        root.lift()
        root.attributes("-topmost", True)
        root.after_idle(root.attributes, "-topmost", False)
        ok_btn.focus_set()

        root.mainloop()
    except Exception as e:
        logger.error(f"Error displaying message GUI dialog: {e}")


def show_success(
    title: str = APP_TITLE,
    message: str = SUCCESS_MESSAGE,
    button_text: str = OK_BUTTON_TEXT,
) -> None:
    """
    Display a native Windows GUI success notification popup in Tamil.
    Shown ONLY when the entire workflow (including Git push) succeeded.
    """
    _show_message_dialog(
        title=title,
        message=message,
        button_text=button_text,
        is_success=True,
        is_dry_run=False,
    )


def show_failure(
    title: str = APP_TITLE,
    message: str = FAILURE_MESSAGE,
    button_text: str = OK_BUTTON_TEXT,
) -> None:
    """
    Display a native Windows GUI failure notification popup in Tamil.
    Shown whenever any critical step fails (loading, validation, git, push).
    """
    _show_message_dialog(
        title=title,
        message=message,
        button_text=button_text,
        is_success=False,
        is_dry_run=False,
    )


def show_dry_run_result(
    title: str = APP_TITLE,
    message: str = DRY_RUN_MESSAGE,
    button_text: str = OK_BUTTON_TEXT,
) -> None:
    """
    Display a native Windows GUI dry-run result notification popup in Tamil.
    Shown when dry_run=true finishes without performing real commit/push.
    """
    _show_message_dialog(
        title=title,
        message=message,
        button_text=button_text,
        is_success=True,
        is_dry_run=True,
    )
