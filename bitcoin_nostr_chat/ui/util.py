import hashlib
import os
from pathlib import Path

from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPalette, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QVBoxLayout,
)


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


def get_input_text(placeholder_text: str, title: str, textcolor: QColor) -> str:
    # Create a modal dialog
    dialog = QDialog()
    dialog.setWindowTitle(title)

    # Set up the layout
    layout = QVBoxLayout(dialog)

    # Add a line edit where the user can input text and set its text color
    line_edit = QLineEdit()
    line_edit.setPlaceholderText(placeholder_text)
    line_edit.setStyleSheet(f"color: {textcolor.name()};")
    layout.addWidget(line_edit)

    # Create a button bar with an OK button
    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    if ok_button:
        ok_button.setDefault(True)
    button_box.accepted.connect(dialog.accept)
    layout.addWidget(button_box)

    # Add a shortcut for the ESC key to close the dialog
    shortcut_close = QShortcut(QKeySequence("ESC"), dialog)
    shortcut_close.activated.connect(dialog.close)

    # Execute the dialog modally
    dialog.exec()

    # Return the text that the user entered
    return line_edit.text()


def insert_invisible_spaces_for_wordwrap(s: str, max_word_length: int = 20) -> str:
    """
    Insert zero-width spaces (\u200B) into any word in `s` that exceeds max_word_length,
    so that it can be wrapped by browsers or text renderers.

    :param s: Input string.
    :param max_word_length: Maximum allowed length of a continuous word before inserting \u200B.
    :return: Modified string with \u200B inserted into long words.
    """
    words = s.split(" ")
    processed = []

    for word in words:
        if len(word) <= max_word_length:
            # Short enough, leave as-is
            processed.append(word)
        else:
            # Break the word into chunks of max_word_length
            parts = [word[i : i + max_word_length] for i in range(0, len(word), max_word_length)]
            # Rejoin with zero-width spaces between chunks
            processed.append("\u200B".join(parts))

    return " ".join(processed)
