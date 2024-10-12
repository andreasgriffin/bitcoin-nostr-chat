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

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QTextEdit, QVBoxLayout, QWidget

from bitcoin_nostr_chat.connected_devices.util import read_QIcon

from ..html import html_f
from ..nostr import RelayList
from ..signals_min import SignalsMin

logger = logging.getLogger(__name__)

from typing import Callable, Generic, List, Optional, Type, TypeVar

from nostr_sdk import Keys
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QResizeEvent

from .chat_gui import ChatGui


def short_key(pub_key_bech32: str):
    return f"{pub_key_bech32[:12]}"


import uuid

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class RelayDialog(QDialog):
    signal_set_relays = pyqtSignal(RelayList)

    def __init__(self, relay_list: RelayList | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Enter custom Nostr Relays"))

        self._layout = QVBoxLayout(self)

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText(
            "Enter relays, one per line like:\nwss://nostr.mom\nws://umbrel:4848"
        )
        if relay_list:
            self.text_edit.setText("\n".join(relay_list.relays))
        self._layout.addWidget(self.text_edit)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Reset,
            self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        if reset_button := self.button_box.button(QDialogButtonBox.StandardButton.Reset):
            reset_button.clicked.connect(self.on_reset)
        self._layout.addWidget(self.button_box)

        self.accepted.connect(self.on_accepted)

    def on_reset(self):
        relay_list = RelayList.from_internet()
        self.text_edit.setText("\n".join(relay_list.relays))

    def on_accepted(self):
        self.signal_set_relays.emit(RelayList.from_text(self.text_edit.toPlainText()))


class InvisibleScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.unique_id = uuid.uuid4()

        self.setObjectName(f"{self.unique_id}")
        self.setStyleSheet(f"#{self.unique_id}" + " { background: transparent; border: none; }")

        self.content_widget = QWidget()
        self.content_widget_layout = QVBoxLayout(self.content_widget)
        self.content_widget.setObjectName(f"{self.unique_id}_content")
        self.content_widget.setStyleSheet(
            f"#{self.unique_id}_content" + " { background: transparent; border: none; }"
        )

        self.setWidget(self.content_widget)


class CloseButton(QtWidgets.QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            """
            background-color: red;
            """
        )
        self.setText("X")
        self.setFixedSize(15, 15)  # adjust size as needed


class BaseDevice(QWidget):
    signal_close = QtCore.pyqtSignal(QWidget)

    def __init__(self, pub_key_bech32: str):
        super().__init__()
        self.pub_key_bech32 = pub_key_bech32
        self.close_button: Optional[QPushButton] = None

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        if self.close_button:
            self.close_button.move(self.width() - self.close_button.width(), 0)

    def create_close_button(self):

        self.close_button = CloseButton(self)
        self.close_button.clicked.connect(lambda: self.signal_close.emit(self))


class UnTrustedDevice(BaseDevice):
    signal_trust_me = QtCore.pyqtSignal(str)

    def __init__(self, pub_key_bech32: str, signals_min: SignalsMin):
        super().__init__(pub_key_bech32)
        self.signals_min = signals_min

        self.button_add_trusted = QPushButton()
        self.button_add_trusted.clicked.connect(lambda: self.signal_trust_me.emit(pub_key_bech32))
        self._layout.addWidget(self.button_add_trusted)
        self.setMinimumHeight(self.button_add_trusted.sizeHint().height())
        self.timer = QTimer(self)
        self.updateUi()

        # signals
        signals_min.language_switch.connect(self.updateUi)

    def updateUi(self):
        self.button_add_trusted.setText(self.tr("Trust {id}").format(id=short_key(self.pub_key_bech32)))

    def trust_request_active(self) -> bool:
        return self.timer.isActive()

    def set_button_status_to_accept(self):
        # Change the button's color to green and text to "Green"
        self.button_add_trusted.setStyleSheet("background-color: green;")
        self.button_add_trusted.setText(
            self.tr("Accept trust request from {other}").format(other=short_key(self.pub_key_bech32))
        )

        self.timer.timeout.connect(self.reset_button)
        seconds = 60
        self.timer.start(seconds * 1000)  # convert to milliseconds

    def reset_button(self):
        # Reset the button's style to default and text to "Click me"
        self.button_add_trusted.setStyleSheet("")
        # Stop the timer to avoid it running indefinitely
        self.timer.stop()


class TrustedDevice(BaseDevice):
    def __init__(
        self,
        pub_key_bech32: str,
        signals_min: SignalsMin,
        on_send: Optional[Callable[[str], None]] = None,
        chat_visible=True,
    ):
        super().__init__(pub_key_bech32)
        self.signals_min = signals_min

        self.groupbox = QGroupBox()
        self.groupbox_layout = QVBoxLayout(self.groupbox)

        self._layout.addWidget(self.groupbox)

        self.groupbox.setLayout(QtWidgets.QVBoxLayout())
        current_margins = self.groupbox_layout.contentsMargins()

        self.groupbox_layout.setContentsMargins(
            current_margins.left(),
            int(current_margins.top() * 2),
            current_margins.right(),
            current_margins.bottom(),
        )  # Left, Top, Right, Bottom margins

        self.groupbox.setStyleSheet(
            """
            QGroupBox {
                border: 1px solid rgba(128, 128, 128, 0.7); /* Border styling */
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px; /* Horizontal position of the title */
                top: 3px; /* Move the title a few pixels down */
                background-color: transparent; /* Make the title background transparent */
            }            
        """
        )

        # Create a QFont object with the desired properties
        boldFont = QFont()
        boldFont.setBold(True)

        # Apply the QFont to the QGroupBox's title
        self.groupbox.setFont(boldFont)

        self.label = QLabel()
        self.groupbox_layout.addWidget(self.label)
        self.chat_gui = ChatGui(signals_min=self.signals_min)
        self.chat_gui.setVisible(chat_visible)
        self.groupbox_layout.addWidget(self.chat_gui)
        self.setMinimumHeight(self.groupbox.sizeHint().height())

        self.create_close_button()

        self.updateUi()

        # signals
        if on_send:
            self.chat_gui.signal_on_message_send.connect(on_send)
        signals_min.language_switch.connect(self.updateUi)

    def updateUi(self):
        self.groupbox.setTitle(self.tr("Connected to {id}").format(id=short_key(self.pub_key_bech32)))
        self.label = QLabel(
            f""" <ul>
                        <li>{self.tr('Syncing Address labels')}</li>
                        <li>{self.tr('Can share Transactions')}</li>
                    </ul>      
                    """
        )

    @classmethod
    def from_untrusted(cls, untrusted_device: UnTrustedDevice, chat_visible=True) -> "TrustedDevice":
        return TrustedDevice(
            untrusted_device.pub_key_bech32,
            signals_min=untrusted_device.signals_min,
            chat_visible=chat_visible,
        )


T = TypeVar("T", bound=BaseDevice)


class DeviceList(Generic[T], QtWidgets.QWidget):
    signal_added_device = QtCore.pyqtSignal(TrustedDevice)

    def __init__(
        self,
        device_class: Type[T],
    ):
        super().__init__()
        self.device_class = device_class

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.scrollarea = InvisibleScrollArea(parent=self)
        self.scrollarea.setWidgetResizable(True)

        self.scrollarea.content_widget_layout.setContentsMargins(0, 0, 0, 0)  # Set all margins to zero
        self.scrollarea.content_widget_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.main_layout.addWidget(self.scrollarea)

    def add_device(self, device: T) -> bool:
        if self.device_already_present(device.pub_key_bech32):
            return False
        device.signal_close.connect(self.remove_device)

        self.scrollarea.content_widget_layout.addWidget(device)
        self.signal_added_device.emit(device)
        return True

    def remove_device(self, device: T):
        device.setParent(None)
        self.scrollarea.content_widget_layout.removeWidget(device)

        device.close()
        device.deleteLater()

    def device_already_present(self, pub_key_bech32: str) -> bool:
        for device in self.get_devices():
            if device.pub_key_bech32 == pub_key_bech32:
                return True
        return False

    def get_device(self, pub_key_bech32: str) -> Optional[T]:
        for device in self.get_devices():
            if device.pub_key_bech32 == pub_key_bech32:
                return device
        return None

    def get_devices(self) -> List[T]:
        return self.scrollarea.content_widget.findChildren(self.device_class)


class ConnectedDevices(QtWidgets.QWidget):
    signal_trust_device = QtCore.pyqtSignal(UnTrustedDevice)
    signal_untrust_device = QtCore.pyqtSignal(TrustedDevice)
    signal_set_keys = QtCore.pyqtSignal()
    signal_reset_keys = QtCore.pyqtSignal()
    signal_set_relays = QtCore.pyqtSignal(RelayList)
    signal_close_event = QtCore.pyqtSignal()

    def __init__(
        self,
        my_keys: Keys,
        signals_min: SignalsMin,
        individual_chats_visible=True,
        get_relay_list: Callable[[], Optional[RelayList]] | None = None,
    ) -> None:
        super().__init__()
        self.signals_min = signals_min
        self.individual_chats_visible = individual_chats_visible
        self.my_keys = my_keys
        self.get_relay_list = get_relay_list

        self._layout = QHBoxLayout(self)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self._layout.addWidget(self.splitter)

        left_side = QWidget()
        left_side_layout = QVBoxLayout(left_side)
        self.splitter.addWidget(left_side)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins
        left_side_layout.addWidget(header)

        self.title_label = QLabel()
        header_layout.addWidget(self.title_label)

        toolbar_button = QToolButton()
        toolbar_button.setIcon(read_QIcon("preferences.png"))
        header_layout.addWidget(toolbar_button)

        menu = QMenu(self)
        self.action_export_identity = menu.addAction("", self.export_sync_key)
        self.action_set_keys = menu.addAction("", self.signal_set_keys.emit)
        self.action_reset_identity = menu.addAction("", self.signal_reset_keys.emit)
        self.action_set_relays = menu.addAction("", self.ask_for_nostr_relays)
        toolbar_button.setMenu(menu)
        toolbar_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.group_trusted = QGroupBox()
        self.group_trusted_layout = QVBoxLayout(self.group_trusted)
        left_side_layout.addWidget(self.group_trusted)

        self.trusted_devices = DeviceList(TrustedDevice)
        self.group_trusted_layout.addWidget(self.trusted_devices)

        self.group_untrusted = QGroupBox()
        self.group_untrusted_layout = QVBoxLayout(self.group_untrusted)
        left_side_layout.addWidget(self.group_untrusted)

        self.untrusted_devices = DeviceList(UnTrustedDevice)
        self.group_untrusted_layout.addWidget(self.untrusted_devices)

        self.groupchat_gui = ChatGui(signals_min=self.signals_min)

        self.updateUi()
        self.splitter.addWidget(self.groupchat_gui)

        self.signals_min.language_switch.connect(self.updateUi)

    def export_sync_key(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            self.tr(
                "Your sync key is:\n\n{sync_key}\n\n Save it, and when you click 'import sync key', it should restore your labels from the nostr relays."
            ).format(sync_key=self.my_keys.secret_key().to_bech32())
        )
        msg.setWindowTitle(self.tr("Sync key Export"))
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def ask_for_nostr_relays(self):
        dialog = RelayDialog(relay_list=self.get_relay_list() if self.get_relay_list else None)
        dialog.signal_set_relays.connect(self.signal_set_relays.emit)
        dialog.exec()

    def updateUi(self):
        if self.action_export_identity:
            self.action_export_identity.setText(self.tr("Export sync key"))
        if self.action_set_keys:
            self.action_set_keys.setText(self.tr("Import sync key"))
        if self.action_reset_identity:
            self.action_reset_identity.setText(self.tr("Reset sync key"))
        if self.action_set_relays:
            self.action_set_relays.setText(self.tr("Set custom Relay list"))
        self.group_trusted.setTitle(self.tr("Trusted"))
        self.group_untrusted.setTitle(self.tr("UnTrusted"))
        if not self.my_keys:
            self.title_label.setText("")
        else:
            self.title_label.setText(
                html_f(
                    self.tr("My Device: {id}").format(id=short_key(self.my_keys.public_key().to_bech32())),
                    bf=True,
                )
            )

    def set_my_keys(self, my_keys: Keys):
        self.my_keys = my_keys
        self.updateUi()

    def add_trusted_device(self, device: TrustedDevice):
        if self.trusted_devices.device_already_present(device.pub_key_bech32):
            return

        self.trusted_devices.add_device(device)
        device.signal_close.connect(lambda s: self.signal_untrust_device.emit(device))

    def add_untrusted_device(self, untrusted_device: UnTrustedDevice) -> bool:
        if self.untrusted_devices.device_already_present(untrusted_device.pub_key_bech32):
            return False
        if self.trusted_devices.device_already_present(untrusted_device.pub_key_bech32):
            # no need to add an untrusted device if i am trusting it already
            return False

        success = self.untrusted_devices.add_device(untrusted_device)
        if not success:
            return success

        def add_to_trusted(pub_key_bech32: str):
            assert pub_key_bech32 == untrusted_device.pub_key_bech32
            self.signal_trust_device.emit(untrusted_device)
            # self.trust_device(untrusted_device)

        untrusted_device.signal_trust_me.connect(add_to_trusted)
        return True

    def trust_device(
        self,
        untrusted_device: UnTrustedDevice,
        callback_on_message_send: Callable | None = None,
        callback_share_filepath: Callable | None = None,
        callback_attachement_clicked: Callable | None = None,
        callback_clear_chat: Callable | None = None,
    ) -> TrustedDevice:
        self.untrusted_devices.remove_device(untrusted_device)

        device = self.trusted_devices.get_device(untrusted_device.pub_key_bech32)
        if device:
            return device

        trusted_device = TrustedDevice.from_untrusted(
            untrusted_device, chat_visible=self.individual_chats_visible
        )
        self.add_trusted_device(trusted_device)

        if callback_on_message_send:
            trusted_device.chat_gui.signal_on_message_send.connect(callback_on_message_send)
        if callback_share_filepath:
            trusted_device.chat_gui.signal_share_filepath.connect(callback_share_filepath)
        if callback_attachement_clicked:
            trusted_device.chat_gui.chat_list_display.signal_attachement_clicked.connect(
                callback_attachement_clicked
            )
        if callback_clear_chat:
            trusted_device.chat_gui.chat_list_display.signal_clear.connect(callback_clear_chat)

        return trusted_device

    def untrust_device(self, trusted_device: TrustedDevice) -> UnTrustedDevice:
        self.trusted_devices.remove_device(trusted_device)

        device = self.untrusted_devices.get_device(trusted_device.pub_key_bech32)
        if device:
            return device

        untrusted_device = UnTrustedDevice(
            pub_key_bech32=trusted_device.pub_key_bech32, signals_min=self.signals_min
        )
        self.add_untrusted_device(untrusted_device)
        return untrusted_device

    def closeEvent(self, event):
        self.signal_close_event.emit()
        super().closeEvent(event)
