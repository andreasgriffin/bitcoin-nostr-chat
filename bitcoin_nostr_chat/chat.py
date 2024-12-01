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
from datetime import datetime
from typing import List

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.dialogs import create_custom_message_box
from bitcoin_nostr_chat.nostr import GroupChat
from bitcoin_nostr_chat.signals_min import SignalsMin

logger = logging.getLogger(__name__)


import bdkpython as bdk
from bitcoin_qr_tools.data import Data, DataType
from nostr_sdk import PublicKey
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.dialogs import create_custom_message_box
from bitcoin_nostr_chat.ui.bitcoin_dm_chat_gui import BitcoinDmChatGui
from bitcoin_nostr_chat.ui.chat_gui import FileObject

from .nostr import BitcoinDM, ChatLabel, GroupChat
from .signals_min import SignalsMin

logger = logging.getLogger(__name__)


from nostr_sdk import PublicKey
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox


class BaseChat(QObject):
    signal_attachement_clicked = pyqtSignal(FileObject)
    signal_add_dm_to_chat = pyqtSignal(BitcoinDM)
    signal_send_dm = pyqtSignal(BitcoinDM)

    def __init__(
        self,
        network: bdk.Network,
        group_chat: GroupChat,
        signals_min: SignalsMin,
        use_compression=DEFAULT_USE_COMPRESSION,
    ) -> None:
        super().__init__()
        self.signals_min = signals_min
        self.group_chat = group_chat
        self.use_compression = use_compression
        self.network = network

        self.gui = BitcoinDmChatGui(signals_min=self.signals_min)

        # connect signals
        self.gui.chat_list_display.signal_attachement_clicked.connect(self.signal_attachement_clicked)
        self.signal_attachement_clicked.connect(self.on_signal_attachement_clicked)
        self.gui.chat_list_display.signal_clear.connect(self.clear_chat_from_memory)

    def is_me(self, public_key: PublicKey) -> bool:
        return public_key.to_bech32() == self.group_chat.my_public_key().to_bech32()

    def _file_to_dm(self, file_content: str, label: ChatLabel, file_name: str) -> BitcoinDM:
        bitcoin_data = Data.from_str(file_content, network=self.network)
        if not bitcoin_data:
            raise Exception(
                self.tr("Could not recognize {file_content} as BitcoinData").format(file_content=file_content)
            )
        dm = BitcoinDM(
            label=label,
            description=file_name,
            event=None,
            data=bitcoin_data,
            use_compression=self.use_compression,
            created_at=datetime.now(),
        )
        return dm

    def on_signal_attachement_clicked(self, file_object: FileObject):
        logger.debug(f"clicked: {file_object.__dict__}")

    def clear_chat_from_memory(self):
        processed_dms = self.group_chat.dm_connection.async_dm_connection.notification_handler.processed_dms
        for dm in self.gui.dms:
            if dm in processed_dms:
                processed_dms.remove(dm)


class Chat(BaseChat):
    def __init__(
        self,
        network: bdk.Network,
        group_chat: GroupChat,
        signals_min: SignalsMin,
        restrict_to_counterparties: List[PublicKey] | None = None,
        use_compression=DEFAULT_USE_COMPRESSION,
        display_labels=[ChatLabel.GroupChat, ChatLabel.SingleRecipient],
        display_file_types=[DataType.PSBT, DataType.Tx],
        send_label=ChatLabel.GroupChat,
    ) -> None:
        super().__init__(network, group_chat, signals_min, use_compression)
        self.display_labels = display_labels
        self.send_label = send_label
        self.restrict_to_counterparties = restrict_to_counterparties
        self.display_file_types = display_file_types

        # signals
        self.group_chat.signal_dm.connect(self.add_to_chat)
        self.gui.signal_on_message_send.connect(self.on_send_message_in_groupchat)
        self.gui.signal_share_filecontent.connect(self.on_share_file_in_groupchat)

    def add_to_chat(self, dm: BitcoinDM):
        if not dm.author:
            logger.debug(
                f"{self.__class__.__name__}: Dropping {dm}, because not author, and with that author can be determined."
            )
            return

        if dm.label not in self.display_labels:
            return

        if dm.data and dm.data.data_type not in self.display_file_types:
            return

        self.gui.add_dm(dm, is_me=self.is_me(dm.author))
        self.signal_add_dm_to_chat.emit(dm)

    def _send(self, dm: BitcoinDM):
        if self.restrict_to_counterparties:
            self.group_chat.send_to(dm, recipients=self.restrict_to_counterparties)
        else:
            self.group_chat.send(dm)

    def on_send_message_in_groupchat(self, text: str):
        dm = BitcoinDM(
            label=self.send_label,
            description=text,
            event=None,
            use_compression=self.use_compression,
            created_at=datetime.now(),
        )
        self._send(dm)
        self.signal_send_dm.emit(dm)

    def on_share_file_in_groupchat(self, file_content: str, file_name: str):
        try:
            dm = self._file_to_dm(file_content=file_content, label=self.send_label, file_name=file_name)
        except Exception:
            create_custom_message_box(
                QMessageBox.Icon.Warning, "Error", self.tr("You can only send only PSBTs or transactions")
            )
            return
        self._send(dm)
        self.signal_send_dm.emit(dm)
