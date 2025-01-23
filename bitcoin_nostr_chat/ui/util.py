import hashlib
import os
from pathlib import Path

from PyQt6.QtGui import QColor, QIcon, QPalette
from PyQt6.QtWidgets import QApplication


def resource_path(*parts):
    pkg_dir = os.path.split(os.path.realpath(__file__))[0]
    return os.path.join(pkg_dir, *parts)


def resource_path_auto_darkmode(*parts: str):
    if is_dark_mode():
        filename = parts[-1]
        name, extension = os.path.splitext(filename)
        modified_parts = list(parts)[:-1] + [f"{name}_darkmode{extension}"]
        combined_path = resource_path(*modified_parts)
        if Path(combined_path).exists():
            return combined_path

    return resource_path(*parts)


def icon_path(icon_basename: str):
    return resource_path_auto_darkmode("icons", icon_basename)


def read_QIcon(icon_basename: str) -> QIcon:
    if not icon_basename:
        return QIcon()
    return QIcon(icon_path(icon_basename))


def short_key(pub_key_bech32: str):
    return f"{pub_key_bech32[:12]}"


def is_dark_mode() -> bool:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return False

    palette = app.palette()
    background_color = palette.color(QPalette.ColorRole.Window)
    text_color = palette.color(QPalette.ColorRole.WindowText)

    # Check if the background color is darker than the text color
    return background_color.lightness() < text_color.lightness()


def hash_string(text: str) -> str:
    return hashlib.sha256(str(text).encode()).hexdigest()


def chat_color(pubkey: str) -> QColor:
    # Generate color from hash
    seed = int(hash_string(pubkey), 16)
    hue = seed % 360  # Map to a hue value between 0-359

    # Set saturation and lightness to create vivid, readable colors
    saturation = 255  # High saturation for vividness
    lightness = 180 if is_dark_mode() else 90  # Adjust for dark/light mode

    # Convert HSL to QColor
    color = QColor.fromHsl(hue, saturation, lightness)
    return color
