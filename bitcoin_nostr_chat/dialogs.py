#
# Nostr Sync
# Copyright (C) 2024 Andreas Griffin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of version 3 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see https://www.gnu.org/licenses/gpl-3.0.html
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


def is_binary(file_path: str):
    """Check if a file is binary or text.

    Returns True if binary, False if text.
    """
    try:
        with open(file_path, "r") as f:
            for chunk in iter(lambda: f.read(1024), ""):
                if "\0" in chunk:  # found null byte
                    return True
    except UnicodeDecodeError:
        return True

    return False


def file_to_str(file_path: str):
    if is_binary(file_path):
        with open(file_path, "rb") as f:
            return bytes(f.read()).hex()
    else:
        with open(file_path, "r") as f:
            return f.read()


def create_custom_message_box(
    icon: QMessageBox.Icon,
    title: Optional[str],
    text: Optional[str],
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    parent: Optional[QWidget] = None,
    flags: Qt.WindowType = Qt.WindowType.Widget,
):
    msg_box = QMessageBox(parent)
    msg_box.setIcon(icon)
    msg_box.setWindowTitle(title if title is not None else "Message")
    msg_box.setText(text if text is not None else "Details are missing.")
    msg_box.setStandardButtons(buttons)
    msg_box.setWindowFlags(flags)
    return msg_box.exec()


class SecretKeyDialog(QDialog):
    def __init__(self, parent=None):
        super(SecretKeyDialog, self).__init__(parent)
        self.setWindowTitle("Import Sync key")

        # Layout and widgets
        layout = QVBoxLayout(self)

        # Label
        label = QLabel("Import sync key:")
        layout.addWidget(label)

        # Line edit for secret key input
        self.secret_key_input = QLineEdit(self)
        self.secret_key_input.setPlaceholderText("nsec...")
        self.secret_key_input.setEchoMode(QLineEdit.EchoMode.Password)  # Mask input for security
        layout.addWidget(self.secret_key_input)

        # Button Box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(self.button_box)

        # Connect the QDialogButtonBox to accept and reject slots
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def get_secret_key(self):
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.secret_key_input.text().strip()
        else:
            return None
