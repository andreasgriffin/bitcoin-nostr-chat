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
from typing import Callable, Optional

from nostr_sdk import Keys
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from bitcoin_nostr_chat.ui.device_manager import DeviceManager
from bitcoin_nostr_chat.ui.util import chat_color, read_QIcon, short_key

from ..group_chat import RelayList
from ..html import html_f
from ..signals_min import SignalsMin

logger = logging.getLogger(__name__)


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


class UI(QtWidgets.QWidget):
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
        # self._layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self._layout.addWidget(self.splitter)

        left_side = QWidget()
        left_side_layout = QVBoxLayout(left_side)
        left_side_layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins

        self.splitter.addWidget(left_side)

        self.tabs = QTabWidget()
        self.splitter.addWidget(self.tabs)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins
        left_side_layout.addWidget(header)

        self.title_label = QLabel()
        header_layout.addWidget(self.title_label)

        toolbar_button = QToolButton()
        toolbar_button.setIcon(read_QIcon("preferences.png"))
        header_layout.addWidget(toolbar_button)

        self.menu = QMenu(self)
        self.action_export_identity = self.menu.addAction("", self.export_sync_key)
        self.action_set_keys = self.menu.addAction("", self.signal_set_keys.emit)
        self.action_reset_identity = self.menu.addAction("", self.signal_reset_keys.emit)
        self.action_set_relays = self.menu.addAction("", self.ask_for_nostr_relays)
        toolbar_button.setMenu(self.menu)
        toolbar_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.device_manager = DeviceManager()
        left_side_layout.addWidget(self.device_manager)

        self.updateUi()

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
        self.device_manager.updateUi()
        if not self.my_keys:
            self.title_label.setText("")
        else:
            self.title_label.setText(
                html_f(
                    self.tr("My Device: {id}").format(id=short_key(self.my_keys.public_key().to_bech32())),
                    bf=True,
                    color=chat_color(
                        self.my_keys.public_key().to_bech32(),
                    ).name(),
                )
            )

    def set_my_keys(self, my_keys: Keys):
        self.my_keys = my_keys
        self.updateUi()

    def closeEvent(self, event):
        self.signal_close_event.emit()
        super().closeEvent(event)
