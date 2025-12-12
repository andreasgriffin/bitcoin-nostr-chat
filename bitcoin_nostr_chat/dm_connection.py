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
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any, Coroutine, Generic

import bdkpython as bdk
from bitcoin_qr_tools.data import DataType
from bitcoin_safe_lib.async_tools.loop_in_thread import LoopInThread
from bitcoin_safe_lib.gui.qt.signal_tracker import SignalProtocol
from nostr_sdk import EventId, Keys, PublicKey, make_private_msg
from PyQt6.QtCore import QObject

from bitcoin_nostr_chat.async_dm_connection import AsyncDmConnection
from bitcoin_nostr_chat.async_thread import AsyncThread, T
from bitcoin_nostr_chat.base_dm import T_BaseDM
from bitcoin_nostr_chat.relay_list import RelayList
from bitcoin_nostr_chat.utils import filtered_for_init

logger = logging.getLogger(__name__)


class DmConnection(QObject, Generic[T_BaseDM]):
    def __init__(
        self,
        from_serialized: Callable[[str], T_BaseDM],
        signal_dm: SignalProtocol[[T_BaseDM]],
        keys: Keys,
        get_currently_allowed: Callable[[], set[str]],
        loop_in_thread: LoopInThread | None,
        use_timer: bool = False,
        dms_from_dump: deque[T_BaseDM] | None = None,
        relay_list: RelayList | None = None,
        async_dm_connection: AsyncDmConnection | None = None,
        async_thread: AsyncThread | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent=parent)

        self.async_thread = (
            async_thread if async_thread else AsyncThread(parent=self, loop_in_thread=loop_in_thread)
        )
        # self.async_thread.result_ready.connect(
        #     lambda result, coro_func, callback: (
        #         callback(result) if callback else (logger.debug(f"Finished {coro_func}"))
        #     )
        # )

        self.async_dm_connection = (
            async_dm_connection
            if async_dm_connection
            else AsyncDmConnection(
                signal_dm=signal_dm,
                from_serialized=from_serialized,
                keys=keys,
                use_timer=use_timer,
                dms_from_dump=dms_from_dump,
                get_currently_allowed=get_currently_allowed,
                relay_list=relay_list,
                loop_in_thread=self.async_thread.loop_in_thread,
            )
        )

    def connect_clients(self):
        self.async_thread.queue_coroutine(self.async_dm_connection.connect_clients())

    def _ensure_clients_connected(self):
        self.connect_clients()

    @classmethod
    def from_dump(
        cls,
        d: dict,
        signal_dm: SignalProtocol[[T_BaseDM]],
        from_serialized: Callable[[str], T_BaseDM],
        get_currently_allowed: Callable[[], set[str]],
        network: bdk.Network,
        loop_in_thread: LoopInThread | None,
        parent: QObject | None = None,
    ) -> "DmConnection":
        async_thread = AsyncThread(loop_in_thread=loop_in_thread)
        async_dm_connection = AsyncDmConnection.from_dump(
            d,
            signal_dm=signal_dm,
            from_serialized=from_serialized,
            get_currently_allowed=get_currently_allowed,
            network=network,
            loop_in_thread=async_thread.loop_in_thread,
        )

        return cls(
            **filtered_for_init(d, cls),
            signal_dm=signal_dm,
            from_serialized=from_serialized,
            async_dm_connection=async_dm_connection,
            get_currently_allowed=get_currently_allowed,
            loop_in_thread=loop_in_thread,
            parent=parent,
        )

    def dump(
        self,
        forbidden_data_types: list[DataType] | None = None,
    ):
        return self.async_dm_connection.dump(forbidden_data_types=forbidden_data_types)

    async def _send_to_me(
        self,
        dm: T_BaseDM,
    ):
        event = await make_private_msg(
            signer=self.async_dm_connection.notification_handler.signer,
            receiver=self.async_dm_connection.keys.public_key(),
            message=dm.serialize(),
        )
        await self.async_dm_connection.client.send_event(event=event)
        await self.async_dm_connection.notification_handler.handle(
            relay_url="_inject_directly_no_relay", subscription_id="_inject_directly_no_relay", event=event
        )

    def send(
        self, dm: T_BaseDM, receiver: PublicKey, on_done: Callable[[EventId | None], None] | None = None
    ):
        self._ensure_clients_connected()

        if receiver.to_bech32() == self.async_dm_connection.keys.public_key().to_bech32():
            # if it is sent to me
            self.async_thread.background(self._send_to_me(dm=dm))
        else:
            self.async_thread.background(self.async_dm_connection.send(dm, receiver), on_done=on_done)

    def get_connected_relays(self) -> RelayList:
        self.async_thread.run_coroutine_blocking(self.async_dm_connection.connect_clients())
        list_relays = self.async_thread.run_coroutine_blocking(
            self.async_dm_connection.get_connected_relays()
        )

        return RelayList(
            relays=list(set([str(relay.url()) for relay in list_relays])), last_updated=datetime.now()
        )

    def unsubscribe_all(
        self,
    ):
        self.async_thread.loop_in_thread.run_background(self.async_dm_connection.unsubscribe_all())

    def subscribe(self, start_time: datetime | None = None, on_done: Callable[[str], None] | None = None):
        self._ensure_clients_connected()
        self.async_thread.queue_coroutine(self.async_dm_connection.subscribe(start_time), on_done=on_done)

    def unsubscribe(
        self,
        public_keys: list[PublicKey],
    ):
        self.async_thread.queue_coroutine(self.async_dm_connection.unsubscribe(public_keys))

    def replay_events_from_dump(self, on_done: Callable[[], None] | None = None):
        self._ensure_clients_connected()
        self.async_thread.queue_coroutine(self.async_dm_connection.replay_events_from_dump(), on_done=on_done)

    def disconnect_clients(self):
        self.async_thread.queue_coroutine(
            self.async_dm_connection.disconnect_client(self.async_dm_connection.client)
        )

    def close(self):
        self.disconnect_clients()
        self.async_thread.stop()
        self.async_dm_connection.close()

    def queue_coroutine(self, coro: Coroutine[Any, Any, T], on_done: Callable[[], None] | None = None):
        self.async_thread.queue_coroutine(coro, on_done=on_done)
