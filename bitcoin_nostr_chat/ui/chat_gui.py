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
import os
import sys
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QResizeEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bitcoin_nostr_chat.dialogs import file_to_str
from bitcoin_nostr_chat.signals_min import SignalsMin
from bitcoin_nostr_chat.ui.chat_component import ChatComponent, FileObject

from .util import svg_tools

logger = logging.getLogger(__name__)


class ChatGui(QWidget):
    # signal_set_relay_list = pyqtSignal(ChatDataRelayList)
    signal_on_message_send = pyqtSignal(str)
    signal_share_filecontent = pyqtSignal(str, str)  # file_content, filename

    def __init__(self, signals_min: SignalsMin):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self.chat_component = ChatComponent()
        # self._layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins
        self._layout.addWidget(self.chat_component)

        self.textInput = QLineEdit()
        self.textInput.textChanged.connect(self.textChanged)

        self.sendButton = QPushButton()
        self.shareButton = QPushButton()
        self.textChanged("")
        os.path.dirname(os.path.abspath(__file__))
        self.shareButton.setIcon(svg_tools.get_QIcon("bi--upload.svg"))
        self.shareButton.clicked.connect(self.on_share_button_click)

        # Placeholder for the dynamic layout
        self.dynamicLayout = QVBoxLayout()
        self.updateDynamicLayout()
        self.updateUi()

        # Connect signals
        self.sendButton.clicked.connect(self.on_send_hit)
        self.textInput.returnPressed.connect(self.on_send_hit)
        signals_min.language_switch.connect(self.updateUi)

    def updateUi(self):
        self.textInput.setPlaceholderText(self.tr("Type your message here..."))
        self.shareButton.setToolTip(self.tr("Share a PSBT"))
        self.sendButton.setText(self.tr("Send"))

    def textChanged(self, text: str):
        there_is_text = bool(self.textInput.text())
        self.sendButton.setVisible(there_is_text)
        self.shareButton.setVisible(not there_is_text)

    def on_share_button_click(
        self,
    ):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Open Transaction/PSBT"),
            "",
            self.tr("All Files (*);;PSBT (*.psbt);;Transation (*.tx)"),
        )
        if not file_path:
            logger.debug("No file selected")
            return

        logger.debug(f"Selected file: {file_path}")
        self.signal_share_filecontent.emit(file_to_str(file_path), os.path.basename(file_path))

    def updateDynamicLayout(self):
        threashold = 200
        expected_layout_class = QHBoxLayout if self.width() > threashold else QVBoxLayout
        if isinstance(self.dynamicLayout, expected_layout_class):
            return

        # Clear the dynamic layout first
        while self.dynamicLayout.count():
            layout_item = self.dynamicLayout.takeAt(0)
            if layout_item and (_widget := layout_item.widget()):
                _widget.setParent(None)

        self.dynamicLayout = expected_layout_class()
        self.dynamicLayout.addWidget(self.textInput)
        self.dynamicLayout.addWidget(self.sendButton)
        self.dynamicLayout.addWidget(self.shareButton)

        self._layout.addLayout(self.dynamicLayout)

    def resizeEvent(self, a0: Optional[QResizeEvent]) -> None:
        self.updateDynamicLayout()
        super().resizeEvent(a0)

    def on_send_hit(self):
        text = self.textInput.text().strip()
        if not text:
            return
        self.signal_on_message_send.emit(text)
        self.textInput.clear()
        # self.add_own(text)

    def _add_message(self, text: str, alignment: Qt.AlignmentFlag, color: QColor, created_at: datetime):
        item = self.chat_component.addItem(text, created_at=created_at)
        item.setTextAlignment(alignment)
        item.setForeground(QBrush(color))

    def _add_file(
        self,
        text: str,
        file_object: FileObject,
        alignment: Qt.AlignmentFlag,
        color: QColor,
        created_at: datetime,
    ):
        item = self.chat_component.add_file(file_object, created_at=created_at, text=text)
        item.setTextAlignment(alignment)
        item.setForeground(QBrush(color))

    def add(
        self,
        created_at: datetime,
        color: QColor,
        is_me: bool,
        author_name: str,
        text: str = "",
        file_object: FileObject | None = None,
    ):
        if file_object:
            self._add_file(
                text=f"{author_name}: {text}",
                file_object=file_object,
                alignment=Qt.AlignmentFlag.AlignRight if is_me else Qt.AlignmentFlag.AlignLeft,
                color=color,
                created_at=created_at,
            )
        else:
            self._add_message(
                text=f"{author_name}: {text}",
                alignment=Qt.AlignmentFlag.AlignRight if is_me else Qt.AlignmentFlag.AlignLeft,
                color=color,
                created_at=created_at,
            )


if __name__ == "__main__":
    import sys

    from PyQt6.QtWidgets import QApplication, QMainWindow

    class DemoApp(QMainWindow):
        def __init__(self):
            super().__init__()
            self.chatGui = ChatGui(signals_min=SignalsMin())
            self.setCentralWidget(self.chatGui)
            self.setWindowTitle("Demo Chat App")
            self.chatGui.signal_on_message_send.connect(self.handleMessage)

        def handleMessage(self, text):
            self.chatGui.add(
                datetime.now(),
                text=f"you said {text}",
                file_object=None,
                color=QColor(),
                is_me=False,
                author_name="Other",
            )
            self.chatGui.add(
                datetime.now(),
                text=f"you said {text}",
                file_object=None,
                color=QColor(),
                is_me=False,
                author_name="Other",
            )

    if __name__ == "__main__":
        app = QApplication(sys.argv)
        demoApp = DemoApp()
        demoApp.show()

        demoApp.chatGui.add(
            datetime.now(),
            text="sending relay list",
            file_object=None,
            color=QColor(),
            is_me=False,
            author_name="Other",
        )
        sys.exit(app.exec())
