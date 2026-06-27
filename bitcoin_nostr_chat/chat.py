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


import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from typing import cast
from uuid import uuid4

import bdkpython as bdk
from bitcoin_qr_tools.data import Data, DataType
from bitcoin_safe_lib.gui.qt.signal_tracker import SignalProtocol, SignalTracker
from nostr_sdk import EventId, PublicKey
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from bitcoin_nostr_chat.chat_dm import ChatLabel
from bitcoin_nostr_chat.dialogs import create_custom_message_box
from bitcoin_nostr_chat.group_chat import GroupChat
from bitcoin_nostr_chat.signals_min import SignalsMin
from bitcoin_nostr_chat.ui.bitcoin_dm_chat_gui import BitcoinDmChatGui
from bitcoin_nostr_chat.ui.chat_gui import FileObject
from bitcoin_nostr_chat.ui.util import chat_color, short_key

from .group_chat import ChatDM

logger = logging.getLogger(__name__)

PENDING_ICON_NAME = "bi--clock-history.svg"
CONFIRMED_ICON_NAME = "bi--check2.svg"


@dataclass
class OutgoingDeliveryState:
    local_id: str
    correlation_key: str
    dm: ChatDM
    recipient_pubkeys: list[str]
    publish_results: dict[str, EventId | None] = field(default_factory=dict)
    failure_messages: dict[str, str] = field(default_factory=dict)
    self_copy_received: bool = False

    @property
    def confirmed(self) -> bool:
        return self.self_copy_received and all(
            self.publish_results.get(recipient) is not None for recipient in self.recipient_pubkeys
        )


class BaseChat(QObject):
    signal_attachement_clicked = cast(SignalProtocol[[FileObject]], pyqtSignal(FileObject))
    signal_add_dm_to_chat = cast(SignalProtocol[[ChatDM]], pyqtSignal(ChatDM))
    signal_send_dm = cast(SignalProtocol[[ChatDM]], pyqtSignal(ChatDM))

    def __init__(
        self,
        network: bdk.Network,
        group_chat: GroupChat,
        signals_min: SignalsMin,
    ) -> None:
        super().__init__()
        self.signals_min = signals_min
        self.group_chat = group_chat
        self.network = network
        self.signal_tracker = SignalTracker()

        self.gui = BitcoinDmChatGui(signals_min=self.signals_min)

        # connect signals
        self.signal_tracker.connect(
            self.gui.chat_component.signal_attachement_clicked, self.signal_attachement_clicked.emit
        )
        self.signal_tracker.connect(self.signal_attachement_clicked, self.on_signal_attachement_clicked)
        self.signal_tracker.connect(
            self.gui.chat_component.list_widget.signal_clear, self.clear_chat_from_memory
        )
        self._outgoing_delivery_states: dict[str, OutgoingDeliveryState] = {}
        self._outgoing_by_correlation_key: dict[str, str] = {}

    def is_me(self, public_key: PublicKey) -> bool:
        return public_key.to_bech32() == self.group_chat.my_public_key().to_bech32()

    def _file_to_dm(self, file_content: str, label: ChatLabel, file_name: str) -> ChatDM:
        bitcoin_data = Data.from_str(file_content, network=self.network)
        if not bitcoin_data:
            raise Exception(
                self.tr("Could not recognize {file_content} as BitcoinData").format(file_content=file_content)
            )
        dm = ChatDM(
            label=label,
            description=file_name,
            event=None,
            data=bitcoin_data,
            use_compression=self.group_chat.use_compression,
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
        self._outgoing_delivery_states.clear()
        self._outgoing_by_correlation_key.clear()
        self.gui.clear_local_state()

    def close(self):
        self.signal_tracker.disconnect_all()

    def _correlation_key_for_dm(self, dm: ChatDM) -> str:
        payload = {
            "label": dm.label.name,
            "description": dm.description,
            "data": dm.data.data_as_string() if dm.data else None,
            "intended_recipient": dm.intended_recipient,
            "created_at": dm.created_at.timestamp(),
        }
        serialized_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized_payload.encode()).hexdigest()


class Chat(BaseChat):
    def __init__(
        self,
        network: bdk.Network,
        group_chat: GroupChat,
        signals_min: SignalsMin,
        restrict_to_counterparties: list[PublicKey] | None = None,
        display_labels: list[ChatLabel] | None = None,
        display_file_types: list[DataType] | None = None,
        send_label=ChatLabel.GroupChat,
    ) -> None:
        super().__init__(network=network, group_chat=group_chat, signals_min=signals_min)
        self.display_labels = display_labels or [ChatLabel.GroupChat, ChatLabel.SingleRecipient]
        self.send_label = send_label
        self.restrict_to_counterparties = restrict_to_counterparties
        self.display_file_types = display_file_types or [DataType.PSBT, DataType.Tx]

        # signals
        self.signal_tracker.connect(self.group_chat.signal_dm, self.add_to_chat)
        self.signal_tracker.connect(self.gui.signal_on_message_send, self.on_send_message_in_groupchat)
        self.signal_tracker.connect(self.gui.signal_share_filecontent, self.on_share_file_in_groupchat)

    def add_to_chat(self, dm: ChatDM):
        if not dm.author:
            logger.debug(
                f"{self.__class__.__name__}: Dropping dm, because {dm.author=},"
                " and with that author can be determined."
            )
            return

        if dm.label not in self.display_labels:
            return

        if dm.data and dm.data.data_type not in self.display_file_types:
            return

        if dm.author and self.is_me(dm.author):
            local_id = self._match_outgoing_delivery_state(dm)
            if local_id:
                self.gui.replace_local_dm(local_id, dm)
                self._mark_self_copy_received(local_id)
                self.signal_add_dm_to_chat.emit(dm)
                return

        self.gui.add_dm(
            dm,
            is_me=self.is_me(dm.author),
            color=chat_color(dm.author.to_bech32()),
            alias=self.get_alias(dm.author),
        )
        self.signal_add_dm_to_chat.emit(dm)

    def get_alias(self, npub: PublicKey) -> str | None:
        if alias := self.group_chat.aliases.get(npub.to_bech32()):
            return alias
        return short_key(npub.to_bech32())

    def _send(self, dm: ChatDM, outgoing_state: OutgoingDeliveryState):
        on_publish_result = partial(self._on_publish_result, outgoing_state.local_id)
        on_self_published = partial(self._on_self_published, outgoing_state.local_id)

        if self.restrict_to_counterparties:
            self.group_chat.send_to(
                dm,
                recipients=self.restrict_to_counterparties,
                on_publish_result=on_publish_result,
                on_self_published=on_self_published,
            )
        else:
            self.group_chat.send(dm, on_publish_result=on_publish_result, on_self_published=on_self_published)

    def _register_outgoing_delivery_state(self, dm: ChatDM) -> OutgoingDeliveryState:
        recipients = (
            self.restrict_to_counterparties if self.restrict_to_counterparties else self.group_chat.members
        )
        recipient_pubkeys = [recipient.to_bech32() for recipient in recipients]
        outgoing_state = OutgoingDeliveryState(
            local_id=uuid4().hex,
            correlation_key=self._correlation_key_for_dm(dm),
            dm=dm,
            recipient_pubkeys=recipient_pubkeys,
        )
        self._outgoing_delivery_states[outgoing_state.local_id] = outgoing_state
        self._outgoing_by_correlation_key[outgoing_state.correlation_key] = outgoing_state.local_id
        return outgoing_state

    def _send_chat_dm(self, dm: ChatDM):
        outgoing_state = self._register_outgoing_delivery_state(dm)
        self.gui.add_dm(
            dm,
            is_me=True,
            color=chat_color(self.group_chat.my_public_key().to_bech32()),
            alias=None,
            local_id=outgoing_state.local_id,
            status_icon_name=PENDING_ICON_NAME,
            status_tooltip=self._tooltip_for_outgoing_delivery_state(outgoing_state),
        )
        self._send(dm, outgoing_state=outgoing_state)
        self.signal_send_dm.emit(dm)

    def _tooltip_for_outgoing_delivery_state(self, outgoing_state: OutgoingDeliveryState) -> str:
        waiting_for = [
            short_key(recipient)
            for recipient in outgoing_state.recipient_pubkeys
            if outgoing_state.publish_results.get(recipient) is None
        ]
        if not outgoing_state.self_copy_received:
            waiting_for.append(self.tr("self-copy"))

        if outgoing_state.failure_messages:
            failures = "; ".join(outgoing_state.failure_messages.values())
            if waiting_for:
                return self.tr("Pending: {waiting_for}. Failed: {failures}").format(
                    waiting_for=", ".join(waiting_for), failures=failures
                )
            return self.tr("Pending due to failed publishes: {failures}").format(failures=failures)

        if waiting_for:
            return self.tr("Pending confirmation from {waiting_for}").format(
                waiting_for=", ".join(waiting_for)
            )

        return self.tr("Published to all recipients and self-copy received")

    def _refresh_outgoing_delivery_state(self, local_id: str):
        outgoing_state = self._outgoing_delivery_states.get(local_id)
        if not outgoing_state:
            return

        icon_name = CONFIRMED_ICON_NAME if outgoing_state.confirmed else PENDING_ICON_NAME
        self.gui.update_outgoing_status(
            local_id=local_id,
            icon_name=icon_name,
            tooltip=self._tooltip_for_outgoing_delivery_state(outgoing_state),
        )

        if outgoing_state.confirmed:
            self._outgoing_by_correlation_key.pop(outgoing_state.correlation_key, None)
            self._outgoing_delivery_states.pop(local_id, None)

    def _on_publish_result(self, local_id: str, public_key_bech32: str, event_id: EventId | Exception | None):
        outgoing_state = self._outgoing_delivery_states.get(local_id)
        if not outgoing_state:
            return

        if isinstance(event_id, Exception):
            outgoing_state.publish_results[public_key_bech32] = None
            outgoing_state.failure_messages[public_key_bech32] = self.tr(
                "Publish failed for {recipient}: {error}"
            ).format(recipient=short_key(public_key_bech32), error=str(event_id))
        elif event_id is None:
            outgoing_state.publish_results[public_key_bech32] = None
            outgoing_state.failure_messages[public_key_bech32] = self.tr(
                "Publish failed for {recipient}"
            ).format(recipient=short_key(public_key_bech32))
        else:
            outgoing_state.publish_results[public_key_bech32] = event_id
            outgoing_state.failure_messages.pop(public_key_bech32, None)

        self._refresh_outgoing_delivery_state(local_id)

    def _on_self_published(self, local_id: str, event_id: EventId | Exception | None):
        outgoing_state = self._outgoing_delivery_states.get(local_id)
        if not outgoing_state:
            return

        if isinstance(event_id, Exception):
            outgoing_state.failure_messages["self"] = self.tr("Could not publish self-copy: {error}").format(
                error=str(event_id)
            )
        elif event_id is None:
            outgoing_state.failure_messages["self"] = self.tr("Could not publish self-copy")
        else:
            outgoing_state.failure_messages.pop("self", None)

        self._refresh_outgoing_delivery_state(local_id)

    def _match_outgoing_delivery_state(self, dm: ChatDM) -> str | None:
        correlation_key = self._correlation_key_for_dm(dm)
        return self._outgoing_by_correlation_key.get(correlation_key)

    def _mark_self_copy_received(self, local_id: str):
        outgoing_state = self._outgoing_delivery_states.get(local_id)
        if not outgoing_state:
            return

        outgoing_state.self_copy_received = True
        outgoing_state.failure_messages.pop("self", None)
        self._refresh_outgoing_delivery_state(local_id)

    def on_send_message_in_groupchat(self, text: str):
        dm = ChatDM(
            label=self.send_label,
            description=text,
            event=None,
            use_compression=self.group_chat.use_compression,
            created_at=datetime.now(),
        )
        self._send_chat_dm(dm)

    def on_share_file_in_groupchat(self, file_content: str, file_name: str):
        try:
            dm = self._file_to_dm(file_content=file_content, label=self.send_label, file_name=file_name)
        except Exception:
            create_custom_message_box(
                QMessageBox.Icon.Warning, "Error", self.tr("You can only send only PSBTs or transactions")
            )
            return
        self._send_chat_dm(dm)

    def on_set_alias(self, npub: str, alias: str):
        self.group_chat.aliases[npub] = alias
