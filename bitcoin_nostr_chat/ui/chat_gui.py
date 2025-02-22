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
from datetime import datetime

from bitcoin_qr_tools.data import Data
from PyQt6.QtCore import QModelIndex, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QContextMenuEvent,
    QIcon,
    QResizeEvent,
    QStandardItem,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bitcoin_nostr_chat.dialogs import file_to_str
from bitcoin_nostr_chat.signals_min import SignalsMin
from bitcoin_nostr_chat.ui.util import read_QIcon

from ..signals_min import SignalsMin

logger = logging.getLogger(__name__)


class MultiLineListView(QWidget):
    signal_clear = pyqtSignal()

    ROLE_SORT = 1001
    itemClicked = pyqtSignal(QStandardItemModel)

    def __init__(self):
        super().__init__()
        self.listView = QListView(self)
        self.listView.setWordWrap(True)
        self.listView.clicked.connect(lambda qmodel_index: self.onItemClicked(qmodel_index))

        self.model = QStandardItemModel(self.listView)
        self.listView.setModel(self.model)

        # Enable sorting
        self.model.setSortRole(self.ROLE_SORT)  # Use the display text for sorting

        self._layout = QVBoxLayout(self)
        self._layout.addWidget(self.listView)
        self._layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        menu = QMenu(self)

        # Add actions to the menu
        action1 = QAction(self.tr("Delete all messages"), self)
        menu.addAction(action1)

        # Connect actions to slots (functions)
        action1.triggered.connect(self.on_delete_all_messages)

        # Pop up the menu at the current mouse position.
        if event:
            menu.exec(event.globalPos())
        super().contextMenuEvent(event)

    def on_delete_all_messages(self):
        self.clearItems()
        self.update()
        self.signal_clear.emit()

    def addItem(self, text: str, created_at: datetime, icon=None) -> QStandardItem:
        """Add an item with the specified text and an optional icon to the list."""
        item = QStandardItem()
        item.setText(text)
        if icon:
            item.setIcon(QIcon(icon))
        item.setEditable(False)
        self.model.appendRow(item)
        item.setData(created_at, self.ROLE_SORT)

        # Sort the model initially
        self.model.sort(0)  # Sort by the first (and only) column
        self.scroll_to_item(item)
        return item

    def scroll_to_item(self, item):
        # Get the index of the item
        index = self.model.indexFromItem(item)
        # Scroll to the item
        self.listView.scrollTo(index, QListView.ScrollHint.EnsureVisible)

    def clearItems(self):
        """Clear all items from the list."""
        self.model.clear()

    def getItemTextAtIndex(self, index: QModelIndex):
        """Get the text of the item at the specified index."""
        item = self.model.itemFromIndex(index)
        if item:
            return item.text()
        return None

    def onItemClicked(self, index: QModelIndex):
        self.itemClicked.emit(self.model.itemFromIndex(index))


class FileObject:
    def __init__(self, path: str, data: Data | None = None):
        self.path = path
        self.data = data


class ChatListWidget(MultiLineListView):
    ROLE_DATA = 1000
    signal_attachement_clicked = pyqtSignal(FileObject)

    def __init__(self, parent=None):
        super().__init__()
        self.itemClicked.connect(self.onItemClicked)

    def add_file(
        self, fileObject: FileObject, created_at: datetime, icon_path: str | None = None
    ) -> QStandardItem:
        icon = QIcon(icon_path) if icon_path else read_QIcon("clip.svg")

        item = self.addItem(
            os.path.basename(fileObject.path),
            icon=icon,
            created_at=created_at,
        )
        item.setData(fileObject, role=self.ROLE_DATA)
        return item

    def onItemClicked(self, item: QStandardItem):  # type: ignore[override]
        # Retrieve the FileObject associated with the clicked item
        fileObject = item.data(self.ROLE_DATA)
        if fileObject:
            self.signal_attachement_clicked.emit(fileObject)

    def sizeHint(self):
        # Get the original size hint from the superclass
        originalSizeHint = super().sizeHint()
        # Return a new QSize with the original width and a custom height
        return QSize(originalSizeHint.width(), 50)  # Keep original width, custom height


class ChatGui(QWidget):
    signal_on_message_send = pyqtSignal(str)
    signal_share_filecontent = pyqtSignal(str, str)  # file_content, filename

    def __init__(self, signals_min: SignalsMin):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self.chat_list_display = ChatListWidget()
        # self._layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins
        self._layout.addWidget(self.chat_list_display)

        self.textInput = QLineEdit()
        self.textInput.textChanged.connect(self.textChanged)

        self.sendButton = QPushButton()
        self.shareButton = QPushButton()
        self.textChanged("")
        os.path.dirname(os.path.abspath(__file__))
        self.shareButton.setIcon(read_QIcon("clip.svg"))
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

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        self.updateDynamicLayout()
        super().resizeEvent(event)

    def on_send_hit(self):
        text = self.textInput.text().strip()
        if not text:
            return
        self.signal_on_message_send.emit(text)
        self.textInput.clear()
        # self.add_own(text)

    def _add_message(self, text: str, alignment: Qt.AlignmentFlag, color: QColor, created_at: datetime):
        item = self.chat_list_display.addItem(text, created_at=created_at)
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
        item = self.chat_list_display.add_file(file_object, created_at=created_at)
        item.setTextAlignment(alignment)
        item.setForeground(QBrush(color))
        item.setText(text)

    def add_own(
        self, created_at: datetime, color: QColor, text: str = "", file_object: FileObject | None = None
    ):
        if file_object:
            self._add_file(
                text=self.tr("Me: {text}").format(text=text),
                file_object=file_object,
                alignment=Qt.AlignmentFlag.AlignRight,
                color=color,
                created_at=created_at,
            )
        else:
            self._add_message(
                text=self.tr("Me: {text}").format(text=text),
                alignment=Qt.AlignmentFlag.AlignRight,
                color=color,
                created_at=created_at,
            )

    def add_other(
        self,
        created_at: datetime,
        color: QColor,
        text: str = "",
        file_object: FileObject | None = None,
        other_name: str = "Other",
    ):
        if file_object:
            self._add_file(
                text=f"{other_name}: {text}",
                file_object=file_object,
                alignment=Qt.AlignmentFlag.AlignLeft,
                color=color,
                created_at=created_at,
            )
        else:
            self._add_message(
                text=f"{other_name}: {text}",
                alignment=Qt.AlignmentFlag.AlignLeft,
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
            self.chatGui.add_own(datetime.now(), text)
            # Simulate other party response
            self.chatGui.add_other(datetime.now(), text)

    if __name__ == "__main__":
        app = QApplication(sys.argv)
        demoApp = DemoApp()
        demoApp.show()
        sys.exit(app.exec())
