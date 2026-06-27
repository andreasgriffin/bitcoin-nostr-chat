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


import os
import sys
from datetime import datetime, timedelta
from typing import cast

from bitcoin_qr_tools.data import Data
from bitcoin_safe_lib.gui.qt.signal_tracker import SignalProtocol
from bitcoin_safe_lib.util import insert_invisible_spaces_for_wordwrap
from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from .util import svg_tools


class FileObject:
    def __init__(self, path: str, data: Data | None = None) -> None:
        self.path = path
        self.data = data


class SortedListWidgetItem(QListWidgetItem):
    def __lt__(self, other: QListWidgetItem) -> bool:
        # Retrieve the stored creation datetime using the custom role.
        self_dt = self.data(ChatListWidget.ROLE_SORT)
        other_dt = other.data(ChatListWidget.ROLE_SORT)
        if isinstance(self_dt, datetime) and isinstance(other_dt, datetime):
            return self_dt < other_dt
        # Fallback to string comparison if datetimes are not available.
        return self.text() < other.text()


class ChatListWidget(QListWidget):
    #  role for storing additional data
    ROLE_DATA: int = 1000

    # Custom data role used to store the datetime the item was created.
    ROLE_SORT: int = 1001
    ROLE_CLIPBOARD: int = 1002

    signal_clear = cast(SignalProtocol[[]], pyqtSignal())

    def __init__(
        self,
    ) -> None:
        # The chat_component is passed explicitly for static type checking.
        super().__init__()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def keyPressEvent(self, e: QKeyEvent | None) -> None:
        if not e:
            return
        # When CTRL+C is pressed, copy selected items in display order to the clipboard.
        if e.key() == Qt.Key.Key_C and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selected_items()
        else:
            super().keyPressEvent(e)

    def copy_selected_items(self) -> None:
        texts: list[str] = []
        # Iterate over items in display order.
        for i in range(self.count()):
            if (item := self.item(i)) and item.isSelected():
                texts.append(str(item.data(ChatListWidget.ROLE_CLIPBOARD)))
        combined_text: str = "\n".join(texts)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(combined_text)

    def show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        clear_action = menu.addAction("Clear All")
        action = menu.exec(self.mapToGlobal(pos))
        if action == copy_action:
            self.copy_selected_items()
        elif action == clear_action:
            self.clear()
            # Use the statically-typed reference to emit the clear signal.
            self.signal_clear.emit()


class ChatItemDelegate(QStyledItemDelegate):
    ICON_TEXT_SPACING = 6

    @classmethod
    def vertically_centered_alignment(cls, alignment: Qt.AlignmentFlag) -> Qt.AlignmentFlag:
        return alignment | Qt.AlignmentFlag.AlignVCenter

    @classmethod
    def right_aligned_icon_rect(cls, text_rect: QRect, content_rect: QRect, icon_size: QSize) -> QRect:
        return QRect(
            text_rect.left() - cls.ICON_TEXT_SPACING - icon_size.width(),
            content_rect.top() + (content_rect.height() - icon_size.height()) // 2,
            icon_size.width(),
            icon_size.height(),
        )

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        if not painter:
            return
        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)

        is_right_aligned = bool(item_option.displayAlignment & Qt.AlignmentFlag.AlignRight)
        if item_option.icon.isNull() or not is_right_aligned:
            super().paint(painter, option, index)
            return

        widget = item_option.widget
        style = widget.style() if widget else QApplication.style()

        text_option = QStyleOptionViewItem(item_option)
        text_option.icon = QIcon()
        text_option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasDecoration
        text_option.displayAlignment = self.vertically_centered_alignment(text_option.displayAlignment)

        if not style:
            return
        # Let Qt paint the text so foreground and selection colors stay identical to default rendering.
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, text_option, painter, widget)

        icon_size = item_option.decorationSize
        if not icon_size.isValid() or icon_size.isEmpty():
            extent = style.pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, item_option, widget)
            icon_size = QSize(extent, extent)

        icon_mode = QIcon.Mode.Normal
        if not item_option.state & QStyle.StateFlag.State_Enabled:
            icon_mode = QIcon.Mode.Disabled
        elif item_option.state & QStyle.StateFlag.State_Selected:
            icon_mode = QIcon.Mode.Selected

        icon_state = QIcon.State.On if item_option.state & QStyle.StateFlag.State_Open else QIcon.State.Off
        icon_pixmap = item_option.icon.pixmap(icon_size, icon_mode, icon_state)

        content_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, text_option, widget)
        reserved_icon_width = icon_pixmap.width() + self.ICON_TEXT_SPACING
        text_available_rect = QRect(content_rect)
        text_available_rect.adjust(reserved_icon_width, 0, 0, 0)

        text_flags = int(
            self.vertically_centered_alignment(item_option.displayAlignment) | Qt.TextFlag.TextWordWrap
        )
        text_rect = item_option.fontMetrics.boundingRect(text_available_rect, text_flags, item_option.text)

        painter.save()
        icon_rect = self.right_aligned_icon_rect(
            text_rect=text_rect,
            content_rect=content_rect,
            icon_size=icon_pixmap.size(),
        )
        style.drawItemPixmap(painter, icon_rect, Qt.AlignmentFlag.AlignCenter, icon_pixmap)
        painter.restore()


class ChatComponent(QWidget):
    # Custom signals
    itemClicked = cast(SignalProtocol[[QListWidgetItem]], pyqtSignal(QListWidgetItem))
    # New signal emitted when an attachment is clicked
    signal_attachement_clicked = cast(SignalProtocol[[FileObject]], pyqtSignal(FileObject))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins
        # Create our custom list widget, providing self as its owner.
        self.list_widget = ChatListWidget()
        self.list_widget.signal_clear.connect(self.clearItems)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setWordWrap(True)
        self.list_widget.setIconSize(QSize(12, 12))
        self.list_widget.setItemDelegate(ChatItemDelegate(self.list_widget))
        # Enable automatic sorting.
        self.list_widget.setSortingEnabled(True)
        layout.addWidget(self.list_widget)

        # Connect the internal itemClicked signal to our custom signal.
        self.list_widget.itemClicked.connect(self.on_item_clicked)

    def on_item_clicked(self, item: QListWidgetItem) -> None:
        self.itemClicked.emit(item)
        file_obj: FileObject | None = item.data(ChatListWidget.ROLE_DATA)
        if file_obj is not None:
            self.signal_attachement_clicked.emit(file_obj)

    def addItem(self, text: str, created_at: datetime, icon: QIcon | None = None) -> SortedListWidgetItem:
        """
        Adds an item with the given text, stores the creation datetime in ROLE_SORT,
        and optionally sets an icon. The item is automatically sorted.
        """
        item = SortedListWidgetItem()
        item.setText(insert_invisible_spaces_for_wordwrap(text))
        item.setData(ChatListWidget.ROLE_CLIPBOARD, text)
        item.setData(ChatListWidget.ROLE_SORT, created_at)
        if icon is not None:
            item.setIcon(icon)
        self.list_widget.addItem(item)
        self.scroll_to_item(item)
        return item
        # No need to call sortItems() explicitly since sorting is enabled.

    def add_text_message(self, text: str, created_at: datetime) -> SortedListWidgetItem:
        """
        Convenience method to add a text message (without an icon).
        """
        return self.addItem(text, created_at)

    def add_custom_widget(self, widget: QWidget, created_at: datetime) -> SortedListWidgetItem:
        """
        Adds a custom widget to the list. The widget can be any QWidget.
        The creation datetime is stored in the associated item.
        """
        item = SortedListWidgetItem()
        item.setData(ChatListWidget.ROLE_SORT, created_at)
        item.setSizeHint(widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)
        self.scroll_to_item(item)
        return item

    def add_file(
        self,
        file: FileObject,
        created_at: datetime,
        text: str | None = None,
        icon_path: str | None = None,
        icon: QIcon | None = None,
    ) -> SortedListWidgetItem:
        """
        Adds a file entry. It displays the file's basename and adds a standard file icon.
        """
        text = text if text else os.path.basename(file.path)
        icon = (
            icon
            if icon is not None
            else (QIcon(icon_path) if icon_path else svg_tools.get_QIcon("bi--upload.svg"))
        )
        item = self.addItem(text, created_at, icon)
        item.setData(ChatListWidget.ROLE_DATA, file)

        return item

    def scroll_to_item(self, item: QListWidgetItem) -> None:
        """
        Scrolls the view so that the specified item is visible.
        """
        self.list_widget.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtBottom)

    def clearItems(self) -> None:
        """
        Clears all items from the list.
        """
        self.list_widget.clear()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Chat Component Example")

    # Create an instance of ChatComponent.
    chat_component = ChatComponent()

    # Add sample text messages.
    chat_component.add_text_message("User: Hello!", datetime.now())
    chat_component.add_text_message("Bot: Hi there!", datetime.now())

    # Add a custom widget message.
    custom_widget = QWidget()
    custom_layout = QHBoxLayout(custom_widget)
    custom_label = QLabel("Custom widget content")
    custom_button = QPushButton("Action")
    custom_layout.addWidget(custom_label)
    custom_layout.addWidget(custom_button)
    chat_component.add_custom_widget(custom_widget, datetime.now())

    # Add a file message.
    file_obj = FileObject("/path/to/somefile.txt")
    chat_component.add_file(file_obj, datetime.now() - timedelta(seconds=1))

    # Connect signals to demonstrate their usage.
    def on_item_clicked(item: QListWidgetItem) -> None:
        created_at: datetime = item.data(ChatListWidget.ROLE_SORT)
        print("Item clicked:", item.text(), "Created at:", created_at)

    chat_component.itemClicked.connect(on_item_clicked)

    def on_clear() -> None:
        print("Chat cleared")

    chat_component.list_widget.signal_clear.connect(on_clear)

    window.setCentralWidget(chat_component)
    window.resize(400, 600)
    window.show()
    sys.exit(app.exec())
