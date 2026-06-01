from __future__ import annotations

import glob
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import serial

START_BYTE = 0x02
END_BYTE = 0x03


class serialCommands:
    def __init__(self, port: Optional[str] = None, baud: int = 115200, timeout: float = 0.05) -> None:
        self.port = port or self._auto_detect_port()
        if self.port is None:
            raise ValueError("No serial port found")

        self._serial = serial.Serial(self.port, baud, timeout=timeout)
        self._buffer = bytearray()

    def _auto_detect_port(self) -> Optional[str]:
        candidates = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
        return candidates[0] if candidates else None

    def send_command(self, command: str, data: Optional[Sequence[int]] = None) -> None:
        if not command or len(command) != 1:
            raise ValueError("Command must be a single character")

        payload = bytearray()
        payload.append(START_BYTE)
        payload.append((len(data or []) + 1) & 0xFF)
        payload.append(ord(command))

        if data is not None:
            for value in data:
                payload.append(int(value) & 0xFF)

        payload.append(END_BYTE)
        self._serial.write(payload)
        self._serial.flush()

    def read_command_feedback(self) -> List[Dict[str, List[int]]]:
        self._read_raw()
        packets: List[Dict[str, List[int]]] = []

        while True:
            start_index = self._buffer.find(START_BYTE)
            if start_index == -1:
                break

            if start_index > 0:
                # Preserve non-framed bytes for plain text reads.
                self._buffer = self._buffer[start_index:]

            if len(self._buffer) < 3:
                break

            frame_length = self._buffer[1]
            total_length = 2 + frame_length + 1
            if len(self._buffer) < total_length:
                break

            if self._buffer[total_length - 1] != END_BYTE:
                self._buffer.pop(0)
                continue

            frame = self._buffer[:total_length]
            self._buffer = self._buffer[total_length:]

            command = chr(frame[2])
            data_bytes = list(frame[3:-1])
            packets.append({"command": command, "data": data_bytes})

        return packets

    def read_serial(self) -> List[str]:
        self._read_raw()
        lines: List[str] = []

        while True:
            newline_index = self._buffer.find(b"\n")
            if newline_index == -1:
                break

            line_bytes = self._buffer[:newline_index]
            del self._buffer[: newline_index + 1]
            try:
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r")
            except Exception:
                line = ""

            if line:
                lines.append(line)

        return lines

    def close_serial(self) -> None:
        try:
            self._serial.close()
        except Exception:
            pass

    def _read_raw(self) -> None:
        if self._serial.in_waiting:
            data = self._serial.read(self._serial.in_waiting)
            self._buffer.extend(data)

    def __del__(self) -> None:
        self.close_serial()
