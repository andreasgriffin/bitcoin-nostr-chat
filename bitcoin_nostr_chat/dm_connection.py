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
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set

import bdkpython as bdk
from bitcoin_qr_tools.data import DataType
from nostr_sdk import EventId, Keys, PublicKey
from PyQt6.QtCore import QObject, pyqtBoundSignal

from bitcoin_nostr_chat.async_dm_connection import AsyncDmConnection
from bitcoin_nostr_chat.async_thread import AsyncThread
from bitcoin_nostr_chat.base_dm import BaseDM
from bitcoin_nostr_chat.bitcoin_dm import BitcoinDM
from bitcoin_nostr_chat.relay_list import RelayList
from bitcoin_nostr_chat.utils import filtered_for_init

logger = logging.getLogger(__name__)


class DmConnection(QObject):
    def __init__(
        self,
        signal_dm: pyqtBoundSignal,
        from_serialized: Callable[[str], BaseDM],
        keys: Keys,
        get_currently_allowed: Callable[[], Set[str]],
        use_timer: bool = False,
        dms_from_dump: deque[BitcoinDM] | None = None,
        relay_list: RelayList | None = None,
        async_dm_connection: AsyncDmConnection | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent=parent)

        self.async_thread = AsyncThread(parent=self)
        self.async_thread.result_ready.connect(
            lambda result, coro_func, callback: (
                callback(result) if callback else (logger.debug(f"Finished {coro_func} with result {result}"))
            )
        )

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
            )
        )
        self.connect_clients()

    def connect_clients(self):
        self.async_thread.queue_coroutine(self.async_dm_connection.ensure_connected_to_relays())
        self.async_thread.queue_coroutine(self.async_dm_connection.connect_notification())

    @classmethod
    def from_dump(
        cls,
        d: Dict,
        signal_dm: pyqtBoundSignal,
        from_serialized: Callable[[str], BaseDM],
        get_currently_allowed: Callable[[], Set[str]],
        network: bdk.Network,
        parent: QObject | None = None,
    ) -> "DmConnection":
        async_dm_connection = AsyncDmConnection.from_dump(
            d,
            signal_dm=signal_dm,
            from_serialized=from_serialized,
            get_currently_allowed=get_currently_allowed,
            network=network,
        )

        return cls(
            **filtered_for_init(d, cls),
            signal_dm=signal_dm,
            from_serialized=from_serialized,
            async_dm_connection=async_dm_connection,
            get_currently_allowed=get_currently_allowed,
        )

    def dump(
        self,
        forbidden_data_types: List[DataType] | None = None,
    ):
        return self.async_dm_connection.dump(forbidden_data_types=forbidden_data_types)

    def send(
        self, dm: BaseDM, receiver: PublicKey, on_done: Callable[[Optional[EventId]], None] | None = None
    ):
        self.async_thread.queue_coroutine(self.async_dm_connection.send(dm, receiver), on_done=on_done)

    def get_connected_relays(self) -> RelayList:
        list_send = self.async_thread.run_coroutine_blocking(
            self.async_dm_connection.get_connected_relays(self.async_dm_connection.client_send)
        )
        list_notification = self.async_thread.run_coroutine_blocking(
            self.async_dm_connection.get_connected_relays(self.async_dm_connection.client_notification)
        )

        return RelayList(
            relays=list(set([relay.url() for relay in list_send + list_notification])),
            last_updated=datetime.now(),
        )

    def unsubscribe_all(self, on_done: Callable[[], None] | None = None):
        self.async_thread.queue_coroutine(self.async_dm_connection.unsubscribe_all(), on_done=on_done)

    def subscribe(self, start_time: datetime | None = None, on_done: Callable[[str], None] | None = None):
        self.async_thread.queue_coroutine(self.async_dm_connection.subscribe(start_time), on_done=on_done)

    def unsubscribe(self, public_keys: List[PublicKey], on_done: Callable[[], None] | None = None):
        self.async_thread.queue_coroutine(self.async_dm_connection.unsubscribe(public_keys), on_done=on_done)

    def replay_events_from_dump(self, on_done: Callable[[], None] | None = None):
        self.async_thread.queue_coroutine(self.async_dm_connection.replay_events_from_dump(), on_done=on_done)

    def disconnect_clients(self):
        self.async_thread.run_coroutine_blocking(
            self.async_dm_connection.disconnect_client(self.async_dm_connection.client_send)
        )
        self.async_thread.run_coroutine_blocking(
            self.async_dm_connection.disconnect_client(self.async_dm_connection.client_notification)
        )

    def stop(self):
        self.disconnect_clients()
        self.async_thread.stop()
        self.async_thread.wait()

    def queue_coroutine(self, coro, on_done: Callable[[], None] | None = None):
        self.async_thread.queue_coroutine(coro, on_done=on_done)

    def run_blocking(self, coro):
        self.async_thread.run_coroutine_blocking(coro)
