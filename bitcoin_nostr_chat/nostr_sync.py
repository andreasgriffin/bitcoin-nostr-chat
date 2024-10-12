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

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.dialogs import SecretKeyDialog, create_custom_message_box
from bitcoin_nostr_chat.utils import filtered_for_init

from .signals_min import SignalsMin

logger = logging.getLogger(__name__)

import os
from typing import Any, Dict, Optional

import bdkpython as bdk
from bitcoin_qr_tools.data import Data, DataType
from nostr_sdk import EventId, PublicKey
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from .connected_devices.chat_gui import FileObject
from .connected_devices.connected_devices import (
    ConnectedDevices,
    TrustedDevice,
    UnTrustedDevice,
    short_key,
)
from .html import html_f
from .nostr import (
    BaseDM,
    BitcoinDM,
    ChatLabel,
    GroupChat,
    Keys,
    NostrProtocol,
    ProtocolDM,
    RelayList,
    SecretKey,
)


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


class NostrSync(QObject):
    signal_add_trusted_device = pyqtSignal(TrustedDevice)
    signal_attachement_clicked = pyqtSignal(FileObject)
    signal_label_bip329_received = pyqtSignal(Data, PublicKey)  # Data, Author

    def __init__(
        self,
        network: bdk.Network,
        nostr_protocol: NostrProtocol,
        group_chat: GroupChat,
        signals_min: SignalsMin,
        individual_chats_visible=True,
        hide_data_types_in_chat: tuple[DataType] = (DataType.LabelsBip329,),
        use_compression=DEFAULT_USE_COMPRESSION,
        debug=False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.network = network
        self.debug = debug
        self.nostr_protocol = nostr_protocol
        self.group_chat = group_chat
        self.hide_data_types_in_chat = hide_data_types_in_chat
        self.signals_min = signals_min
        self.use_compression = use_compression

        self.gui = ConnectedDevices(
            my_keys=self.group_chat.dm_connection.async_dm_connection.keys,
            individual_chats_visible=individual_chats_visible,
            signals_min=signals_min,
            get_relay_list=self.get_connected_relays,
        )
        self.gui.groupchat_gui.chat_list_display.signal_attachement_clicked.connect(
            self.signal_attachement_clicked
        )
        self.nostr_protocol.signal_dm.connect(self.on_signal_protocol_dm)
        self.group_chat.signal_dm.connect(self.on_dm)

        self.gui.signal_set_relays.connect(self.on_set_relays)
        self.gui.groupchat_gui.signal_on_message_send.connect(self.on_send_message_in_groupchat)
        self.gui.groupchat_gui.signal_share_filepath.connect(self.on_share_filepath_in_groupchat)
        self.gui.signal_trust_device.connect(self.trust_device)
        self.gui.signal_untrust_device.connect(self.untrust_device)
        self.signal_attachement_clicked.connect(self.on_signal_attachement_clicked)
        self.gui.signal_reset_keys.connect(self.reset_own_key)
        self.gui.signal_set_keys.connect(self.set_own_key)
        self.gui.groupchat_gui.chat_list_display.signal_clear.connect(
            lambda: self.on_clear_chat_from_memory(chat_label=ChatLabel.GroupChat)
        )
        self.gui.signal_close_event.connect(self.stop)

    def stop(self):
        self.nostr_protocol.dm_connection.stop()
        self.group_chat.dm_connection.stop()

    def get_connected_relays(self) -> RelayList:
        return RelayList(
            relays=[relay.url() for relay in self.group_chat.dm_connection.get_connected_relays()],
            last_updated=datetime.now(),
        )

    def on_set_relays(self, relay_list: RelayList):
        logger.info(f"Setting relay_list {relay_list} ")
        self.group_chat.set_relay_list(relay_list)
        self.nostr_protocol.set_relay_list(relay_list)
        self.publish_my_key_in_protocol(force=True)
        logger.info(f"Done Setting relay_list {relay_list} ")

    def is_me(self, public_key: PublicKey) -> bool:
        return (
            public_key.to_bech32()
            == self.group_chat.dm_connection.async_dm_connection.keys.public_key().to_bech32()
        )

    def on_clear_chat_from_memory(self, chat_label: ChatLabel, counterparty_key_bech32: str | None = None):
        def should_remove_item(item: BaseDM) -> bool:
            if isinstance(item, BitcoinDM):
                if item.label == chat_label:
                    if counterparty_key_bech32:
                        item_author = item.author
                        if not item_author:
                            return False

                        item_counterparty_public_key = self.get_singlechat_counterparty(item)
                        return item_counterparty_public_key == counterparty_key_bech32
                    else:
                        return True
            return False

        for item in list(self.group_chat.dm_connection.async_dm_connection.queue):
            if should_remove_item(item):
                self.group_chat.dm_connection.async_dm_connection.queue.remove(item)

    def set_own_key(self):
        nsec = SecretKeyDialog().get_secret_key()
        if not nsec:
            return
        try:
            keys = Keys(SecretKey.from_bech32(nsec))
            self.reset_own_key(keys=keys)
        except:
            create_custom_message_box(
                QMessageBox.Icon.Warning, "Error", f"Error in importing the nsec {nsec}"
            )
            return

    def reset_own_key(self, keys: Keys = None):
        self.group_chat.renew_own_key(keys=keys)
        self.gui.set_my_keys(self.group_chat.dm_connection.async_dm_connection.keys)
        self.publish_my_key_in_protocol()

        # ask the members to trust my new key again (they need to manually approve)
        for member in self.group_chat.members:
            self.nostr_protocol.publish_trust_me_back(
                author_public_key=self.group_chat.dm_connection.async_dm_connection.keys.public_key(),
                recipient_public_key=member,
            )

    @classmethod
    def from_keys(
        cls,
        network: bdk.Network,
        protocol_keys: Keys,
        device_keys: Keys,
        signals_min: SignalsMin,
        individual_chats_visible=True,
        use_compression=DEFAULT_USE_COMPRESSION,
        parent: QObject | None = None,
    ) -> "NostrSync":
        nostr_protocol = NostrProtocol(
            network=network,
            keys=protocol_keys,
            use_compression=use_compression,
            last_shutdown=datetime.now(),
            parent=parent,
        )
        group_chat = GroupChat(
            network=network,
            keys=device_keys,
            use_compression=use_compression,
            last_shutdown=datetime.now(),
            parent=parent,
        )
        return NostrSync(
            network=network,
            nostr_protocol=nostr_protocol,
            group_chat=group_chat,
            individual_chats_visible=individual_chats_visible,
            signals_min=signals_min,
            use_compression=use_compression,
            parent=parent,
        )

    def dump(self) -> Dict[str, Any]:
        d = {}
        # exclude my own key. It's pointless to save and
        # later replay (internally) protocol messages that i sent previously
        d["nostr_protocol"] = self.nostr_protocol.dump()
        d["group_chat"] = self.group_chat.dump()
        d["individual_chats_visible"] = self.gui.individual_chats_visible
        d["network"] = self.network.name
        d["debug"] = self.debug
        return d

    @classmethod
    def from_dump(
        cls,
        d: Dict[str, Any],
        signals_min: SignalsMin,
        parent: QObject | None = None,
    ) -> "NostrSync":
        d["nostr_protocol"] = NostrProtocol.from_dump(d["nostr_protocol"])
        d["group_chat"] = GroupChat.from_dump(d["group_chat"])
        d["network"] = bdk.Network[d["network"]]

        sync = cls(**filtered_for_init(d, NostrSync), signals_min=signals_min, parent=parent)

        # add the gui elements for the trusted members
        for member in sync.group_chat.members:
            if sync.is_me(member):
                # do not add myself as a device
                continue
            untrusted_device = UnTrustedDevice(pub_key_bech32=member.to_bech32(), signals_min=signals_min)
            sync.gui.add_untrusted_device(untrusted_device)
            sync.trust_device(untrusted_device, show_message=False)

        # restore/replay chat texts
        sync.nostr_protocol.dm_connection.replay_events()
        sync.group_chat.dm_connection.replay_events()
        return sync

    def subscribe(self):
        self.nostr_protocol.subscribe()
        self.group_chat.subscribe()
        self.publish_my_key_in_protocol()

    def unsubscribe(self):
        self.nostr_protocol.dm_connection.unsubscribe_all()
        self.group_chat.dm_connection.unsubscribe_all()

    def on_signal_attachement_clicked(self, file_object: FileObject):
        logger.debug(f"clicked: {file_object.__dict__}")

    def publish_my_key_in_protocol(self, force=False):
        self.nostr_protocol.publish_public_key(
            self.group_chat.dm_connection.async_dm_connection.keys.public_key(), force=force
        )

    def on_dm(self, dm: BitcoinDM):
        if not dm.author:
            logger.debug(f"Dropping {dm}, because not author, and with that author can be determined.")
            return

        if self.debug:
            self.add_debug_to_chat(dm)

        if dm.data and dm.data.data_type == DataType.LabelsBip329:
            # only emit a signal if I didn't send it
            self.signal_label_bip329_received.emit(dm.data, dm.author)

        if dm.data and dm.data.data_type in self.hide_data_types_in_chat:
            # do not display it in chat
            pass
        elif dm.label == ChatLabel.DistrustMeRequest and not self.is_me(dm.author):
            self.untrust_key(dm.author)
        elif dm.label == ChatLabel.DeleteMeRequest and not self.is_me(dm.author):
            self.untrust_key(dm.author)
            untrusted_device = self.gui.untrusted_devices.get_device(dm.author.to_bech32())
            if untrusted_device:
                self.gui.untrusted_devices.remove_device(untrusted_device)
        else:
            self.add_to_chat(dm)

    def untrust_key(self, member: PublicKey):
        trusted_device = self.gui.trusted_devices.get_device(member.to_bech32())
        if trusted_device:
            self.untrust_device(trusted_device)
        else:
            self.group_chat.remove_member(member)

    def add_debug_to_chat(self, dm: BitcoinDM):
        file_object = FileObject(path=dm.description, data=dm.data) if dm.data else None

        if dm.label == ChatLabel.GroupChat:
            chat_gui = self.gui.groupchat_gui
        elif dm.label == ChatLabel.SingleRecipient:
            trusted_device = self.get_trusted_device_of_single_recipient_dm(dm)
            if not trusted_device:
                return
            chat_gui = trusted_device.chat_gui

        if self.is_me(dm.author):
            chat_gui.add_own(
                text=str(dm),
                file_object=file_object,
                created_at=dm.created_at if dm.created_at else datetime.now(),
            )
        else:
            chat_gui.add_other(
                text=str(dm),
                file_object=file_object,
                other_name=short_key(dm.author.to_bech32()) if dm.author else "Unknown",
                created_at=dm.created_at if dm.created_at else datetime.now(),
            )

    def add_to_chat(self, dm: BitcoinDM):
        text = dm.description
        file_object = FileObject(path=dm.description, data=dm.data) if dm.data else None

        if dm.label == ChatLabel.GroupChat:
            chat_gui = self.gui.groupchat_gui
        elif dm.label == ChatLabel.SingleRecipient:
            trusted_device = self.get_trusted_device_of_single_recipient_dm(dm)
            if not trusted_device:
                return
            chat_gui = trusted_device.chat_gui
        else:
            logger.warning(f"Unrecognized dm.label {dm.label}")
            return

        if self.is_me(dm.author):
            chat_gui.add_own(
                text=text,
                file_object=file_object,
                created_at=dm.created_at if dm.created_at else datetime.now(),
            )
        else:
            chat_gui.add_other(
                text=text,
                file_object=file_object,
                other_name=short_key(dm.author.to_bech32()) if dm.author else "Unknown",
                created_at=dm.created_at if dm.created_at else datetime.now(),
            )

    def get_singlechat_counterparty(self, dm: BitcoinDM) -> Optional[str]:
        if dm.label != ChatLabel.SingleRecipient:
            return None

        if not dm.author:
            return None

        # if I sent it, and there is a intended_recipient
        # then the dm is a message from me to intended_recipient,
        # and should be displayed in trusted_device of the  intended_recipient
        if self.is_me(dm.author):
            if dm.intended_recipient:
                return dm.intended_recipient
            return None
        else:
            return dm.author.to_bech32()

    def get_trusted_device_of_single_recipient_dm(self, dm: BitcoinDM) -> Optional[TrustedDevice]:
        counterparty_public_key = self.get_singlechat_counterparty(dm)
        if counterparty_public_key:
            return self.gui.trusted_devices.get_device(counterparty_public_key)
        return None

    def on_send_message_in_groupchat(self, text: str):
        self.group_chat.send(
            BitcoinDM(
                label=ChatLabel.GroupChat,
                description=text,
                event=None,
                use_compression=self.use_compression,
                created_at=datetime.now(),
            )
        )

    def filepath_to_dm(self, label: ChatLabel, file_path: str) -> BitcoinDM:
        s = file_to_str(file_path)
        bitcoin_data = Data.from_str(s, network=self.network)
        if not bitcoin_data:
            raise Exception(f"Could not recognize {s} as BitcoinData")
        dm = BitcoinDM(
            label=label,
            description=os.path.basename(file_path),
            event=None,
            data=bitcoin_data,
            use_compression=self.use_compression,
            created_at=datetime.now(),
        )
        return dm

    def on_share_filepath_in_groupchat(self, file_path: str):
        try:
            dm = self.filepath_to_dm(label=ChatLabel.GroupChat, file_path=file_path)
        except Exception:
            create_custom_message_box(
                QMessageBox.Icon.Warning, "Error", f"{file_path} could not be recognized as Bitcoin data"
            )
            return
        self.group_chat.send(dm)
        # after sending add the author  (sending it in the dm would be redundant)
        dm.author = self.group_chat.dm_connection.async_dm_connection.keys.public_key()
        self.add_to_chat(dm)

    def connect_untrusted_device(self, untrusted_device: UnTrustedDevice):
        if untrusted_device.pub_key_bech32 in [k.to_bech32() for k in self.group_chat.members]:
            self.trust_device(untrusted_device, show_message=False)

    def on_signal_protocol_dm(self, dm: ProtocolDM):
        if self.is_me(PublicKey.from_bech32(dm.public_key_bech32)):
            # if I'm the autor do noting
            return

        untrusted_device = UnTrustedDevice(pub_key_bech32=dm.public_key_bech32, signals_min=self.signals_min)
        success = self.gui.add_untrusted_device(untrusted_device)
        if success:
            self.connect_untrusted_device(untrusted_device)

        if dm.please_trust_public_key_bech32:
            # the message is a request to trust the author
            untrusted_device2 = self.gui.untrusted_devices.get_device(dm.public_key_bech32)
            if not isinstance(untrusted_device2, UnTrustedDevice):
                return
            if not untrusted_device2:
                logger.warning(f"For {dm.public_key_bech32} could not be found an untrusted device")
                return
            untrusted_device2.set_button_status_to_accept()

    def untrust_device(self, trusted_device: TrustedDevice):
        self.group_chat.remove_member(PublicKey.from_bech32(trusted_device.pub_key_bech32))
        untrusted_device = self.gui.untrust_device(trusted_device)
        self.connect_untrusted_device(untrusted_device)

    def trust_device(self, untrusted_device: UnTrustedDevice, show_message=True) -> TrustedDevice:
        device_public_key = PublicKey.from_bech32(untrusted_device.pub_key_bech32)
        self.group_chat.add_member(device_public_key)

        def send_copy_to_myself(dm: BitcoinDM, receiver: PublicKey, send_to_other_event_id: EventId):
            logger.debug(
                f"Successfully sent to {receiver.to_bech32()} (eventid = {send_to_other_event_id}) and now send copy to myself"
            )
            dm.intended_recipient = untrusted_device.pub_key_bech32
            self.group_chat.dm_connection.send(
                dm, receiver=self.group_chat.dm_connection.async_dm_connection.keys.public_key()
            )

        def callback_on_message_send(text: str):
            dm = BitcoinDM(
                event=None,
                label=ChatLabel.SingleRecipient,
                description=text,
                use_compression=self.use_compression,
                created_at=datetime.now(),
            )
            receiver = PublicKey.from_bech32(untrusted_device.pub_key_bech32)
            self.group_chat.dm_connection.send(
                dm, receiver=receiver, on_done=lambda event_id: send_copy_to_myself(dm, receiver, event_id)
            )

        def callback_share_filepath(file_path: str):
            try:
                dm = self.filepath_to_dm(label=ChatLabel.SingleRecipient, file_path=file_path)
            except Exception:
                create_custom_message_box(
                    QMessageBox.Icon.Warning, "Error", f"{file_path} could not be recognized as Bitcoin data"
                )
                return
            receiver = PublicKey.from_bech32(untrusted_device.pub_key_bech32)
            self.group_chat.dm_connection.send(
                dm, receiver=receiver, on_done=lambda event_id: send_copy_to_myself(dm, receiver, event_id)
            )

        trusted_device = self.gui.trust_device(
            untrusted_device,
            callback_attachement_clicked=self.signal_attachement_clicked.emit,
            callback_on_message_send=callback_on_message_send,
            callback_share_filepath=callback_share_filepath,
            callback_clear_chat=lambda: self.on_clear_chat_from_memory(
                chat_label=ChatLabel.SingleRecipient, counterparty_key_bech32=device_public_key.to_bech32()
            ),
        )

        assert trusted_device.pub_key_bech32 == untrusted_device.pub_key_bech32

        if show_message and not untrusted_device.trust_request_active():
            QMessageBox.information(
                self.gui,
                self.tr("Go to {untrusted}").format(untrusted=short_key(untrusted_device.pub_key_bech32)),
                self.tr(
                    "To complete the connection, accept my {id} request on the other device {other}."
                ).format(
                    id=html_f(
                        short_key(
                            self.group_chat.dm_connection.async_dm_connection.keys.public_key().to_bech32()
                        ),
                        bf=True,
                    ),
                    other=html_f(short_key(untrusted_device.pub_key_bech32), bf=True),
                ),
            )

        self.signal_add_trusted_device.emit(trusted_device)

        self.nostr_protocol.publish_trust_me_back(
            author_public_key=self.group_chat.dm_connection.async_dm_connection.keys.public_key(),
            recipient_public_key=device_public_key,
        )
        return trusted_device
