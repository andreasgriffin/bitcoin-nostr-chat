from bitcoin_safe_lib.gui.qt.icons import SvgTools
from bitcoin_safe_lib.gui.qt.util import is_dark_mode
from bitcoin_safe_lib.util import hash_string
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QVBoxLayout

from bitcoin_nostr_chat.utils import resource_path


def get_icon_path(icon_basename: str) -> str:
    return resource_path("ui", "icons", icon_basename)


svg_tools = SvgTools(get_icon_path=get_icon_path, theme_file=get_icon_path("theme.csv"))


def short_key(pub_key_bech32: str):
    return f"{pub_key_bech32[:12]}"


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
