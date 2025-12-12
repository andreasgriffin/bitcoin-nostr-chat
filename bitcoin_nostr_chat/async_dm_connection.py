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


import asyncio
import logging
from collections import deque
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Generic

import bdkpython as bdk
from bitcoin_qr_tools.data import DataType
from bitcoin_safe_lib.async_tools.loop_in_thread import LoopInThread
from bitcoin_safe_lib.gui.qt.signal_tracker import SignalProtocol
from nostr_sdk import (
    Client,
    EventId,
    Filter,
    Keys,
    Kind,
    NostrSigner,
    PublicKey,
    Relay,
    RelayStatus,
    RelayUrl,
    SecretKey,
    Timestamp,
)
from PyQt6.QtCore import QObject, QTimer

from bitcoin_nostr_chat.annoucement_dm import AccouncementDM
from bitcoin_nostr_chat.base_dm import BaseDM, T_BaseDM
from bitcoin_nostr_chat.chat_dm import ChatDM
from bitcoin_nostr_chat.notification_handler import (
    DM_KIND,
    GIFTWRAP,
    NotificationHandler,
)
from bitcoin_nostr_chat.relay_list import RelayList
from bitcoin_nostr_chat.ui.util import short_key
from bitcoin_nostr_chat.utils import filtered_for_init

logger = logging.getLogger(__name__)


class AsyncDmConnection(QObject, Generic[T_BaseDM]):
    def __init__(
        self,
        signal_dm: SignalProtocol[[T_BaseDM]],
        from_serialized: Callable[[str], T_BaseDM],
        keys: Keys,
        get_currently_allowed: Callable[[], set[str]],
        loop_in_thread: LoopInThread,
        use_timer: bool = False,
        dms_from_dump: Iterable[T_BaseDM] | None = None,
        relay_list: RelayList | None = None,
    ) -> None:
        super().__init__()
        self.signal_dm = signal_dm
        self.use_timer = use_timer
        self.get_currently_allowed = get_currently_allowed
        self.loop_in_thread = loop_in_thread
        self.from_serialized = from_serialized
        self.minimum_connect_relays = 8
        self.relay_list = relay_list if relay_list else RelayList.from_internet()
        self.counter_no_connected_relay = 0

        # self.dms_from_dump is used for replaying events from dump
        self.dms_from_dump: deque[BaseDM] = deque(dms_from_dump) if dms_from_dump else deque()
        self.current_subscription_dict: dict[str, PublicKey] = {}  # subscription_id: PublicKey
        self.timer = QTimer()

        self._clients_connected = False
        self._connect_clients_lock = asyncio.Lock()
        self.create_clients(keys)

    def create_clients(self, keys: Keys, processed_dms: deque | None = None):
        self._clients_connected = False
        self._connect_clients_lock = asyncio.Lock()
        self.keys = keys
        signer = NostrSigner.keys(self.keys)
        self.client = Client(signer)

        self.task_handle_notifications: asyncio.Task | None = None

        self.notification_handler = NotificationHandler(
            my_keys=self.keys,
            processed_dms=(
                processed_dms if processed_dms else deque()
            ),  # do  not set here the dms_from_dump, otherwise the replaying messages are all ignored
            signal_dm=self.signal_dm,
            get_currently_allowed=self.get_currently_allowed,
            from_serialized=self.from_serialized,
        )

    def close(self):
        self.notification_handler.close()

    async def disconnect_client(self, client: Client):
        # if self.task_handle_notifications:
        #     try:
        #         self.task_handle_notifications.cancel()
        #         await self.task_handle_notifications
        #     except Exception as e:
        #         logger.warning(str(e))
        #     finally:
        #         self.task_handle_notifications = None

        await client.disconnect()
        self._clients_connected = False
        logger.debug(f"disconnect_client {client=}")

    async def connect_notification(self):
        await self.ensure_connected_to_relays()

        logger.debug(f"{self.__class__.__name__} Starting handle_notifications")
        self.loop_in_thread.run_background(self.client.handle_notifications(self.notification_handler))
        await asyncio.sleep(0)

    async def connect_clients(self):
        if self._clients_connected:
            return

        async with self._connect_clients_lock:
            await self.ensure_connected_to_relays()
            await self.connect_notification()
            self._clients_connected = True

    def public_key_was_published(self, public_key: PublicKey) -> bool:
        for dm in list(self.notification_handler.processed_dms):
            if isinstance(dm, AccouncementDM):
                if dm.public_key_bech32 == public_key.to_bech32():
                    return True
        return False

    async def get_connected_relays(self) -> list[Relay]:
        relays = await self.client.relays()
        connected_relays: list[Relay] = [
            relay for relay in relays.values() if relay.status() == RelayStatus.CONNECTED
        ]
        return connected_relays

    async def send(self, dm: T_BaseDM, receiver: PublicKey) -> EventId | None:
        await self.connect_clients()
        try:
            serialized_dm = dm.serialize()
            send_event_output = await self.client.send_private_msg(receiver, serialized_dm)
            logger.debug(f"sent dm to {short_key(receiver.to_bech32())} with {len(serialized_dm)=}")
            return send_event_output.id
        except Exception as e:
            logger.error(f"Error sending direct message: {e}")
            return None

    def _get_filter(self, recipient: PublicKey, start_time: datetime | None = None) -> Filter:
        this_filter = Filter().pubkey(recipient).kinds([Kind.from_std(DM_KIND), Kind.from_std(GIFTWRAP)])

        if start_time:
            timestamp = Timestamp.from_secs(int(start_time.timestamp()))
            logger.error(
                f"Subscribe to {short_key(recipient.to_bech32())} from {timestamp.to_human_datetime()}"
            )
            this_filter = this_filter.since(timestamp=timestamp)

        return this_filter

    async def subscribe(self, start_time: datetime | None = None) -> str | None:
        "overwrites previous filters"

        await self.connect_clients()
        self._start_timer()

        filters = self._get_filter(self.keys.public_key(), start_time=start_time)
        logger.debug(f"Subscribe to {filters}")
        subscribe_output = await self.client.subscribe(filters, opts=None)
        if subscribe_output.failed:
            return None

        self.current_subscription_dict[subscribe_output.id] = self.keys.public_key()
        logger.debug(
            f"Added subscription_id {subscribe_output.id} for public_key {self.keys.public_key().to_bech32()}"
        )

        return subscribe_output.id

    async def unsubscribe_all(self):
        if not self._clients_connected:
            self.current_subscription_dict.clear()
            return

        await self.unsubscribe(list(self.current_subscription_dict.values()))

    async def unsubscribe(self, public_keys: list[PublicKey]):
        for subscription_id, pub_key in list(self.current_subscription_dict.items()):
            if pub_key in public_keys:
                await self.client.unsubscribe(subscription_id)
                del self.current_subscription_dict[subscription_id]

    def _start_timer(self, delay_retry_connect=10):
        if not self.use_timer:
            return
        if self.timer.isActive():
            return
        self.timer.setInterval(delay_retry_connect * 1000)
        self.timer.timeout.connect(self._timer_ensure_connected)
        self.timer.start()

    def _timer_ensure_connected(self):
        asyncio.create_task(self.ensure_connected_to_relays())

    async def ensure_connected_to_relays(self):
        await self._ensure_connected_to_relays()

    async def _ensure_connected_to_relays(self):
        logger.debug("ensure_connected_to_relays")
        client_name = "client"
        org_connections = await self.get_connected_relays()
        logger.debug(f"{client_name} has {len(org_connections)} connected relays")

        if len(org_connections) >= min(self.minimum_connect_relays, len(list(self.relay_list.relays))):
            return

        self.relay_list.update_if_stale()

        relay_subset = self.relay_list.get_subset(
            self.minimum_connect_relays + self.counter_no_connected_relay
        )
        for relay in relay_subset:
            await self.client.add_relay(RelayUrl.parse(relay))
        await self.client.connect()
        await self.client.wait_for_connection(timeout=timedelta(seconds=1))
        # sleep so get_connected_relays is accurate
        new_connections = await self.get_connected_relays()
        logger.debug(f"{client_name} has {len(new_connections)} connected relays")

        # assume the connections are successfull
        # however if not, then next time try 1 more connection
        # sleep(0.1)
        self.counter_no_connected_relay += 1

    def dump(
        self,
        forbidden_data_types: list[DataType] | None = None,
    ):
        def include_item(item: T_BaseDM) -> bool:
            if isinstance(item, ChatDM):
                if forbidden_data_types is not None:
                    if item.data and item.data.data_type in forbidden_data_types:
                        return False
            if isinstance(item, AccouncementDM):
                return False
            return True

        return {
            "use_timer": self.use_timer,
            "keys": self.keys.secret_key().to_bech32(),
            "dms_from_dump": [
                item.dump() for item in self.notification_handler.processed_dms if item and include_item(item)
            ],
            # TODO: This might be added in the future,
            # to allow restoring labels from devices that are connected after the wallet has been shut down
            # "untrusted_events": [
            #     item.dump() for item in self.notification_handler.untrusted_events
            #                             if item and include_item(item)
            # ],
            "relay_list": self.relay_list.dump(),
        }

    @classmethod
    def from_dump(
        cls,
        d: dict,
        signal_dm: SignalProtocol[[T_BaseDM]],
        from_serialized: Callable[[str], T_BaseDM],
        get_currently_allowed: Callable[[], set[str]],
        network: bdk.Network,
        loop_in_thread: LoopInThread,
    ) -> "AsyncDmConnection":
        d["keys"] = Keys(secret_key=SecretKey.parse(d["keys"]))

        d["dms_from_dump"] = [ChatDM.from_dump(d, network=network) for d in d.get("dms_from_dump", [])]
        d["relay_list"] = RelayList.from_dump(d["relay_list"]) if "relay_list" in d else None

        return cls(
            **filtered_for_init(d, cls),
            signal_dm=signal_dm,
            from_serialized=from_serialized,
            get_currently_allowed=get_currently_allowed,
            loop_in_thread=loop_in_thread,
        )

    async def replay_events_from_dump(self):
        # now handle the dms_from_dump as if they came from a relay
        events = [dm.event for dm in self.dms_from_dump if dm.event]
        await self.notification_handler.replay_events(events)
