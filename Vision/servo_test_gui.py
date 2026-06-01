#!/usr/bin/env python3

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_operations.arduino_serial_commuication import serialCommands


WINDOW_BG = "#141821"
PANEL_BG = "#1f2430"
TEXT_PRIMARY = "#f4f7ff"
TEXT_MUTED = "#9aa3c2"
ACCENT = "#4a90e2"
ACCENT_ACTIVE = "#5aa0ff"
BORDER = "#31384a"

DEFAULT_ANGLE = 90
ANGLE_MIN = 0
ANGLE_MAX = 180
NUDGE_STEP = 5


class ServoTester:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Servo Test")
        self.root.geometry("520x360")
        self.root.configure(background=WINDOW_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.link: Optional[serialCommands] = None
        self.connected = False

        self._style = ttk.Style()
        self._configure_style()

        self.status_var = tk.StringVar(value="Disconnected")
        self.port_var = tk.StringVar(value="Auto-detect")
        self.angle_var = tk.IntVar(value=DEFAULT_ANGLE)

        self._build_ui()
        self.root.after(100, self._poll_serial)

    def _configure_style(self) -> None:
        try:
            if "clam" in self._style.theme_names():
                self._style.theme_use("clam")
        except tk.TclError:
            pass

        self._style.configure("Main.TFrame", background=WINDOW_BG)
        self._style.configure("Panel.TFrame", background=PANEL_BG)
        self._style.configure("TLabel", background=PANEL_BG, foreground=TEXT_PRIMARY)
        self._style.configure("Muted.TLabel", background=PANEL_BG, foreground=TEXT_MUTED)
        self._style.configure("Header.TLabel", background=PANEL_BG, foreground=TEXT_PRIMARY, font=("TkDefaultFont", 11, "bold"))
        self._style.configure("TButton", background=ACCENT, foreground="#ffffff", borderwidth=0, padding=(12, 8))
        self._style.map(
            "TButton",
            background=[("pressed", ACCENT_ACTIVE), ("active", ACCENT_ACTIVE)],
        )
        self._style.configure(
            "TEntry",
            fieldbackground="#1a1f2d",
            foreground=TEXT_PRIMARY,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, style="Main.TFrame", padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        top = ttk.Frame(main, style="Panel.TFrame", padding=12)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Servo Serial Test", style="Header.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(top, text="Port", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))

        port_entry = ttk.Entry(top, textvariable=self.port_var)
        port_entry.grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(10, 0))

        self.connect_btn = ttk.Button(top, text="Connect", command=self._toggle_connection)
        self.connect_btn.grid(row=1, column=2, sticky="e", pady=(10, 0))

        ttk.Label(top, textvariable=self.status_var, style="Muted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        controls = ttk.Frame(main, style="Panel.TFrame", padding=12)
        controls.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)

        self.angle_label = ttk.Label(controls, text=f"Angle: {DEFAULT_ANGLE}", style="Header.TLabel")
        self.angle_label.grid(row=0, column=0, columnspan=3, sticky="w")

        slider = tk.Scale(
            controls,
            from_=ANGLE_MIN,
            to=ANGLE_MAX,
            orient="horizontal",
            variable=self.angle_var,
            command=self._on_slider_change,
            resolution=1,
            background=PANEL_BG,
            foreground=TEXT_PRIMARY,
            troughcolor="#2c3446",
            highlightthickness=0,
            activebackground=ACCENT,
        )
        slider.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 6))

        ttk.Button(controls, text=f"-{NUDGE_STEP}", command=lambda: self._nudge(-NUDGE_STEP)).grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=(8, 0))
        ttk.Button(controls, text="Center", command=lambda: self._send_angle(DEFAULT_ANGLE)).grid(row=2, column=1, sticky="ew", padx=3, pady=(8, 0))
        ttk.Button(controls, text=f"+{NUDGE_STEP}", command=lambda: self._nudge(NUDGE_STEP)).grid(row=2, column=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        presets = ttk.Frame(main, style="Panel.TFrame", padding=12)
        presets.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        presets.columnconfigure(0, weight=1)

        button_row = ttk.Frame(presets, style="Panel.TFrame")
        button_row.grid(row=0, column=0, sticky="ew")
        for index, angle in enumerate((0, 45, 90, 135, 180)):
            ttk.Button(button_row, text=str(angle), command=lambda value=angle: self._send_angle(value)).grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 4, 0))
            button_row.columnconfigure(index, weight=1)

        ttk.Label(presets, text="Serial Output", style="Header.TLabel").grid(row=1, column=0, sticky="w", pady=(14, 6))
        self.log = tk.Text(
            presets,
            height=9,
            state="disabled",
            wrap="word",
            background="#10141f",
            foreground=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.log.grid(row=2, column=0, sticky="nsew")
        presets.rowconfigure(2, weight=1)

    def _toggle_connection(self) -> None:
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        try:
            port_text = self.port_var.get().strip()
            port = None if port_text in {"", "Auto-detect"} else port_text
            self.link = serialCommands(port=port)
        except Exception as exc:
            self._set_status(f"Connect failed: {exc}")
            return

        self.connected = True
        self.connect_btn.configure(text="Disconnect")
        self._set_status(f"Connected to {self.link.port}")
        self._append_log(f"Connected to {self.link.port}")
        self._send_angle(self.angle_var.get())

    def _disconnect(self) -> None:
        if self.link is not None:
            try:
                self.link.close_serial()
            except Exception:
                pass
        self.link = None
        self.connected = False
        self.connect_btn.configure(text="Connect")
        self._set_status("Disconnected")
        self._append_log("Disconnected")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_slider_change(self, _value: str) -> None:
        angle = self.angle_var.get()
        self.angle_label.configure(text=f"Angle: {angle}")
        if self.connected:
            self._send_angle(angle, update_slider=False)

    def _nudge(self, delta: int) -> None:
        self._send_angle(self.angle_var.get() + delta)

    def _send_angle(self, angle: int, update_slider: bool = True) -> None:
        clamped = max(ANGLE_MIN, min(ANGLE_MAX, int(angle)))
        if update_slider:
            self.angle_var.set(clamped)
            self.angle_label.configure(text=f"Angle: {clamped}")

        if not self.connected or self.link is None:
            return

        try:
            self.link.send_command("S", [clamped])
        except Exception as exc:
            self._append_log(f"Send failed: {exc}")
            self._disconnect()
            return

        self._append_log(f"Sent servo angle {clamped}")

    def _poll_serial(self) -> None:
        if self.link is not None and self.connected:
            try:
                feedback_packets = self.link.read_command_feedback()
                if feedback_packets:
                    for packet in feedback_packets:
                        command = packet.get("command")
                        data = packet.get("data", [])
                        self._append_log(f"Feedback {command}: {data}")

                lines = self.link.read_serial()
                if lines:
                    for line in lines:
                        self._append_log(line)
            except Exception as exc:
                self._append_log(f"Serial read failed: {exc}")
                self._disconnect()

        self.root.after(100, self._poll_serial)

    def _on_close(self) -> None:
        self._disconnect()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ServoTester(root)
    root.mainloop()


if __name__ == "__main__":
    main()
