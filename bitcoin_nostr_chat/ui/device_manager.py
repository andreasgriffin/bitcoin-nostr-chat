import logging
import sys
from typing import Generic, TypeVar

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from bitcoin_nostr_chat.ui.util import chat_color, get_input_text, short_key

logger = logging.getLogger(__name__)


class BaseDeviceItem(QWidget):
    signal_set_alias = pyqtSignal(str, str)
    signal_untrust_device = pyqtSignal(str)
    signal_trust_device = pyqtSignal(str)

    def __init__(self, pub_key_bech32: str, alias: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pub_key_bech32 = pub_key_bech32
        self.alias = alias
        self.label = QLabel()

        # Enable the custom context menu on the label
        self.label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Connect the customContextMenuRequested signal to the function
        self.label.customContextMenuRequested.connect(self.show_label_context_menu)

    def updateUi(self):
        pass

    def get_label_text(self) -> str:
        return self.alias if self.alias else short_key(self.pub_key_bech32)

    def set_alias_text(self, alias: str):
        self.alias = alias
        self.updateUi()

    # Define a function to display the context menu
    def show_label_context_menu(self, point: QPoint):
        # Create a QMenu with the label as its parent
        menu = QMenu(self.label)
        action_rename = menu.addAction(self.tr("Rename"))

        # Map the local point to a global position and display the menu
        selected_action = menu.exec(self.label.mapToGlobal(point))

        # Handle the selected action
        if selected_action == action_rename:
            alias = get_input_text(
                placeholder_text=self.tr("Enter a name of device with {npub}").format(
                    npub=self.pub_key_bech32
                ),
                title=self.tr("Device name"),
                textcolor=chat_color(self.pub_key_bech32),
            )
            if alias:
                self.signal_set_alias.emit(self.pub_key_bech32, alias)


class TrustedDeviceItem(BaseDeviceItem):
    def __init__(self, pub_key_bech32: str, alias: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(pub_key_bech32=pub_key_bech32, alias=alias, parent=parent)

        main_layout = QVBoxLayout(self)
        # main_layout.setContentsMargins(5, 5, 5, 5)  # Add some padding

        # 3) Add a horizontal layout for the top part (label and close button)
        top_layout = QHBoxLayout()
        # top_layout.setContentsMargins(0, 0, 0, 0)  # Tighten spacing

        # Label (top-left)
        top_layout.addWidget(self.label)

        # Close button (top-right)
        self.close_button = QPushButton()
        self.close_button.setIcon(
            (self.style() or QStyle()).standardIcon(QStyle.StandardPixmap.SP_TabCloseButton)
        )
        self.close_button.setFixedSize(24, 24)  # Set button size
        self.close_button.setFlat(True)  # Optional: make the button flat
        top_layout.addWidget(self.close_button)

        # Add the top layout to the main layout
        main_layout.addLayout(top_layout)

        self.updateUi()

        # 7) Connect the button click to remove the item
        self.close_button.clicked.connect(lambda: self.signal_untrust_device.emit(self.pub_key_bech32))

    def updateUi(self):
        self.label.setText(self.get_label_text())
        self.label.setToolTip(self.pub_key_bech32)
        palette = self.label.palette()
        palette.setColor(self.label.foregroundRole(), chat_color(self.pub_key_bech32))
        self.label.setPalette(palette)

        self.close_button.setToolTip(self.tr("Untrust device"))


class UntrustedDeviceItem(BaseDeviceItem):
    def __init__(self, pub_key_bech32: str, alias: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(pub_key_bech32=pub_key_bech32, alias=alias, parent=parent)
        self.timer = QTimer(self)

        main_layout = QVBoxLayout(self)
        # main_layout.setContentsMargins(0, 0, 0, 0)

        # 3) Add a horizontal layout for the top part (label and close button)
        top_layout = QHBoxLayout()
        # top_layout.setContentsMargins(0, 0, 0, 0)  # Tighten spacing

        # Label (top-left)
        top_layout.addWidget(self.label)

        # Close button (top-right)
        self.button_trust = QPushButton()
        top_layout.addWidget(self.button_trust)

        # Add the top layout to the main layout
        main_layout.addLayout(top_layout)

        self.updateUi()
        # 7) Connect the button click to remove the item
        self.button_trust.clicked.connect(lambda: self.signal_trust_device.emit(self.pub_key_bech32))

    def updateUi(self):
        self.label.setText(self.get_label_text())
        self.label.setToolTip(self.pub_key_bech32)
        palette = self.label.palette()
        palette.setColor(self.label.foregroundRole(), chat_color(self.pub_key_bech32))
        self.label.setPalette(palette)

        self.button_trust.setText(self.tr("Trust"))
        self.button_trust.setToolTip(self.tr("Trust this device"))

    def trust_request_active(self) -> bool:
        return self.timer.isActive()

    def set_button_status_to_accept(self):
        # Change the button's color to green and text to "Green"
        self.button_trust.setStyleSheet("background-color: green;")

        self.timer.timeout.connect(self.reset_button)
        seconds = 15
        self.timer.start(seconds * 1000)  # convert to milliseconds

    def reset_button(self):
        # Reset the button's style to default and text to "Click me"
        self.button_trust.setStyleSheet("")
        # Stop the timer to avoid it running indefinitely
        self.timer.stop()


T = TypeVar("T", bound=BaseDeviceItem)  # Represents the type of the result returned by the coroutine


class DeviceList(QListWidget, Generic[T]):
    signal_untrust_device = pyqtSignal(str)
    signal_trust_device = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

    def add_list_item(self, device_item: T):
        if self.get_device(device_item.pub_key_bech32):
            logger.debug(f"Duplicate {device_item.pub_key_bech32}")
            return

        list_item = QListWidgetItem()

        self.addItem(list_item)
        self.setItemWidget(list_item, device_item)

        list_item.setSizeHint(device_item.sizeHint())
        device_item.signal_untrust_device.connect(lambda: self.remove_list_item(list_item))
        device_item.signal_trust_device.connect(lambda: self.remove_list_item(list_item))
        device_item.signal_untrust_device.connect(self.signal_untrust_device)
        device_item.signal_trust_device.connect(self.signal_trust_device)
        self.updateUi()

    def get_device(self, pub_key_bech32: str) -> T | None:
        for i in range(self.count()):
            item = self.item(i)
            if not item:
                continue
            device: T = self.itemWidget(item)  # type: ignore
            if device.pub_key_bech32 == pub_key_bech32:
                return device
        return None

    def remove(self, pub_key_bech32: str):
        for i in range(self.count()):
            item = self.item(i)
            if not item:
                continue
            device = self.get_device(pub_key_bech32)
            if device and device.pub_key_bech32 == pub_key_bech32:
                self.remove_list_item(item)

    def remove_list_item(self, item: QListWidgetItem):
        """
        Removes the given item from the QListWidget.
        """
        row = self.row(item)
        if row >= 0:
            self.takeItem(row)

    def updateUi(self):
        for i in range(self.count()):
            item = self.item(i)
            if not item:
                continue
            device: T = self.itemWidget(item)  # type: ignore
            device.updateUi()


class DeviceManager(QWidget):
    signal_set_alias = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins

        self.group_trusted = QGroupBox()
        self.group_trusted_layout = QVBoxLayout(self.group_trusted)
        self._layout.addWidget(self.group_trusted)

        self.trusted = DeviceList[TrustedDeviceItem]()
        self.group_trusted_layout.addWidget(self.trusted)

        self.group_untrusted = QGroupBox()
        self.group_untrusted_layout = QVBoxLayout(self.group_untrusted)
        self._layout.addWidget(self.group_untrusted)

        self.untrusted = DeviceList[UntrustedDeviceItem]()
        self.group_untrusted_layout.addWidget(self.untrusted)

        self.trusted.signal_untrust_device.connect(self.create_untrusted_device)
        self.untrusted.signal_trust_device.connect(self.create_trusted_device)

        self.updateUi()

    def create_untrusted_device(
        self,
        pub_key_bech32: str,
        alias: str | None = None,
    ):
        device = UntrustedDeviceItem(pub_key_bech32=pub_key_bech32, alias=alias)
        device.signal_set_alias.connect(self.signal_set_alias)
        self.untrusted.add_list_item(device)

    def create_trusted_device(
        self,
        pub_key_bech32: str,
        alias: str | None = None,
    ):
        device = TrustedDeviceItem(pub_key_bech32=pub_key_bech32, alias=alias)
        device.signal_set_alias.connect(self.signal_set_alias)
        self.trusted.add_list_item(device)

    def updateUi(self):
        self.group_trusted.setTitle(self.tr("Trusted"))
        self.group_untrusted.setTitle(self.tr("Untrusted"))

        self.trusted.updateUi()
        self.untrusted.updateUi()

    def untrust(self, pub_key_bech32: str):
        self.trusted.remove(pub_key_bech32=pub_key_bech32)
        self.create_untrusted_device(pub_key_bech32=pub_key_bech32)

    def remove_from_all(self, pub_key_bech32: str):
        self.trusted.remove(pub_key_bech32=pub_key_bech32)
        self.untrusted.remove(pub_key_bech32=pub_key_bech32)

    def on_set_alias(self, npub: str, alias: str):
        trusted = self.trusted.get_device(npub)
        if trusted:
            trusted.set_alias_text(alias)

        untrusted = self.untrusted.get_device(npub)
        if untrusted:
            untrusted.set_alias_text(alias)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = QWidget()
    layout = QVBoxLayout(widget)

    lists = DeviceManager()
    layout.addWidget(lists)
    lists.trusted.add_list_item(TrustedDeviceItem("A"))
    lists.trusted.add_list_item(TrustedDeviceItem("B"))
    lists.trusted.add_list_item(TrustedDeviceItem("C"))

    lists.untrusted.add_list_item(UntrustedDeviceItem("D"))
    lists.untrusted.add_list_item(UntrustedDeviceItem("E"))
    lists.untrusted.add_list_item(UntrustedDeviceItem("F"))

    widget.show()
    sys.exit(app.exec())
