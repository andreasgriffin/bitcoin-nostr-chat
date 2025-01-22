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
from abc import abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Set

import bdkpython as bdk
from bitcoin_qr_tools.data import DataType
from nostr_sdk import EventId, Keys, PublicKey
from PyQt6.QtCore import QObject, pyqtSignal

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.base_dm import BaseDM
from bitcoin_nostr_chat.bitcoin_dm import BitcoinDM, ChatLabel
from bitcoin_nostr_chat.dm_connection import DmConnection
from bitcoin_nostr_chat.protocol_dm import ProtocolDM
from bitcoin_nostr_chat.relay_list import RelayList
from bitcoin_nostr_chat.utils import filtered_for_init

logger = logging.getLogger(__name__)


class BaseProtocol(QObject):
    signal_dm = pyqtSignal(BaseDM)

    def __init__(
        self,
        sync_start: datetime | None,
        network: bdk.Network,
        keys: Keys | None = None,
        dm_connection_dump: dict | None = None,
        parent: QObject | None = None,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        super().__init__(parent=parent)
        # start_time saves the last shutdown time
        self.sync_start = sync_start
        self.network = network

        self.dm_connection = (
            DmConnection.from_dump(
                d=dm_connection_dump,
                signal_dm=self.signal_dm,
                from_serialized=self.from_serialized,
                get_currently_allowed=self.get_currently_allowed,
                network=network,
                parent=self,
            )
            if dm_connection_dump
            else DmConnection(
                self.signal_dm,
                from_serialized=self.from_serialized,
                keys=keys,
                get_currently_allowed=self.get_currently_allowed,
                parent=self,
            )
        )

    def my_public_key(self) -> PublicKey:
        return self.dm_connection.async_dm_connection.keys.public_key()

    @abstractmethod
    def subscribe(self):
        pass

    @abstractmethod
    def from_serialized(self, base64_encoded_data) -> BaseDM:
        pass

    def refresh_dm_connection(
        self,
        keys: Keys | None = None,
        relay_list: RelayList | None = None,
        sync_start: datetime | None = None,
    ):
        keys = keys if keys else self.dm_connection.async_dm_connection.keys
        relay_list = relay_list if relay_list else self.dm_connection.async_dm_connection.relay_list

        self.dm_connection.disconnect_clients()
        self.dm_connection.async_dm_connection.relay_list = relay_list
        # prevent redownloading the messages by setting the time to now
        self.sync_start = sync_start

        self.dm_connection.async_dm_connection.create_clients(
            keys, processed_dms=self.dm_connection.async_dm_connection.notification_handler.processed_dms
        )
        self.dm_connection.connect_clients()
        self.subscribe()

    def set_relay_list(self, relay_list: RelayList):
        self.refresh_dm_connection(relay_list=relay_list, sync_start=None)

    @abstractmethod
    def get_currently_allowed(self) -> Set[str]:
        pass


class NostrProtocol(BaseProtocol):
    signal_dm = pyqtSignal(ProtocolDM)

    def __init__(
        self,
        network: bdk.Network,
        sync_start: datetime | None,
        keys: Keys | None = None,
        dm_connection_dump: Dict | None = None,
        use_compression=DEFAULT_USE_COMPRESSION,
        parent: QObject | None = None,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        super().__init__(
            keys=keys,
            dm_connection_dump=dm_connection_dump,
            sync_start=sync_start,
            parent=parent,
            network=network,
        )
        self.use_compression = use_compression

    def get_currently_allowed(self) -> Set[str]:
        return set([self.my_public_key().to_bech32()])

    def from_serialized(self, base64_encoded_data) -> ProtocolDM:
        return ProtocolDM.from_serialized(base64_encoded_data=base64_encoded_data, network=self.network)

    def list_public_keys(self):
        pass

    def publish_public_key(self, author_public_key: PublicKey, force=False):
        logger.debug(f"starting publish_public_key {self.my_public_key().to_bech32()}")
        if not force and self.dm_connection.async_dm_connection.public_key_was_published(author_public_key):
            logger.debug(f"{author_public_key.to_bech32()} was published already. No need to do it again")
            return
        dm = ProtocolDM(
            public_key_bech32=author_public_key.to_bech32(),
            event=None,
            use_compression=self.use_compression,
            created_at=datetime.now(),
        )
        self.dm_connection.send(dm, self.my_public_key())
        logger.debug(f"done publish_public_key {self.my_public_key().to_bech32()}")

    def publish_trust_me_back(self, author_public_key: PublicKey, recipient_public_key: PublicKey):
        dm = ProtocolDM(
            public_key_bech32=author_public_key.to_bech32(),
            please_trust_public_key_bech32=recipient_public_key.to_bech32(),
            event=None,
            use_compression=self.use_compression,
            created_at=datetime.now(),
        )
        self.dm_connection.send(dm, self.my_public_key())

    def subscribe(self):
        def on_done(subscription_id: str):
            logger.debug(f"{self.__class__.__name__}  Finished subscribed to: {subscription_id}")

        self.dm_connection.subscribe(start_time=self.sync_start, on_done=on_done)

    def dump(self):
        return {
            # start_time saves the last shutdown time
            # the next starttime is the current time
            "sync_start": None,  # the nostr protocol should always sync everything  #  datetime.now().timestamp(),
            "dm_connection_dump": self.dm_connection.dump(),
            "use_compression": self.use_compression,
            "network": self.network.name,
        }

    @classmethod
    def from_dump(cls, d: Dict) -> "NostrProtocol":
        # start_time saves the last shutdown time
        d["sync_start"] = (
            datetime.fromtimestamp(d["sync_start"]) if ("sync_start" in d) and d["sync_start"] else None
        )
        d["network"] = bdk.Network[d["network"]]
        return cls(**filtered_for_init(d, cls))


class GroupChat(BaseProtocol):
    signal_dm = pyqtSignal(BitcoinDM)

    def __init__(
        self,
        network: bdk.Network,
        sync_start: datetime | None,
        keys: Keys | None = None,
        dm_connection_dump: dict | None = None,
        members: List[PublicKey] | None = None,
        use_compression=DEFAULT_USE_COMPRESSION,
        parent: QObject | None = None,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        self.members: List[PublicKey] = members if members else []
        self.use_compression = use_compression
        self.nip17_time_uncertainty = timedelta(
            days=2
        )  # 2 days according to https://github.com/nostr-protocol/nips/blob/master/17.md#encrypting
        super().__init__(
            keys=keys,
            dm_connection_dump=dm_connection_dump,
            sync_start=sync_start,
            parent=parent,
            network=network,
        )

    def get_currently_allowed(self) -> Set[str]:
        return set([member.to_bech32() for member in self.members_including_me()])

    def from_serialized(self, base64_encoded_data: str) -> BitcoinDM:
        return BitcoinDM.from_serialized(base64_encoded_data, network=self.network)

    def add_member(self, new_member: PublicKey):
        if new_member.to_bech32() not in [k.to_bech32() for k in self.members]:
            self.members.append(new_member)
            # because NIP17, i only need to watch stuff that goes to me, no matter from whom
            # self.dm_connection.subscribe( new_member)
            logger.debug(f"Add {new_member.to_bech32()} as trusted")

    def remove_member(self, remove_member: PublicKey):
        members_bech32 = [k.to_bech32() for k in self.members]
        if remove_member.to_bech32() in members_bech32:
            self.members.pop(members_bech32.index(remove_member.to_bech32()))
            self.dm_connection.unsubscribe([remove_member])
            logger.debug(f"Removed {remove_member.to_bech32()}")

    def _send_copy_to_myself(self, dm: BitcoinDM, receiver: PublicKey, send_to_other_event_id: EventId):
        logger.debug(
            f"Successfully sent to {receiver.to_bech32()} (eventid = {send_to_other_event_id}) and now send copy to myself"
        )
        copy_dm = BitcoinDM.from_dump(dm.dump(), network=self.network)
        copy_dm.event = None
        self.dm_connection.send(copy_dm, receiver=self.my_public_key())

    def send_to(self, dm: BitcoinDM, recipients: List[PublicKey], send_also_to_me=True):
        for public_key in recipients:
            on_done = None
            if send_also_to_me and public_key == self.members[-1]:
                # for the last recipient, make a callback to send a copy to myself
                # such that, if the last recipient gets it, then i get a copy too
                on_done = lambda event_id: self._send_copy_to_myself(dm, public_key, event_id)
            self.dm_connection.send(dm, public_key, on_done=on_done)
            logger.debug(f"Send to {public_key.to_bech32()}")

        if not self.members:
            logger.debug(f"{self.members=}, so sending to myself only")
            self.dm_connection.send(dm, receiver=self.my_public_key())

    def send(self, dm: BitcoinDM, send_also_to_me=True):
        self.send_to(dm=dm, recipients=self.members, send_also_to_me=send_also_to_me)

    def members_including_me(self):
        return self.members + [self.my_public_key()]

    def subscribe(self):
        def on_done(subscription_id: str):
            logger.debug(f"{self.__class__.__name__}  Successfully subscribed to {subscription_id}")

        start_time = self.sync_start - self.nip17_time_uncertainty if self.sync_start else self.sync_start
        self.dm_connection.subscribe(start_time=start_time, on_done=on_done)

    def dump(self):
        forbidden_data_types = [DataType.LabelsBip329]
        return {
            # start_time saves the last shutdown time
            # the next start_time is the current time
            "sync_start": datetime.now().timestamp(),
            "dm_connection_dump": self.dm_connection.dump(forbidden_data_types=forbidden_data_types),
            "members": [member.to_bech32() for member in self.members],
            "use_compression": self.use_compression,
            "network": self.network.name,
        }

    @classmethod
    def from_dump(cls, d: Dict) -> "GroupChat":
        # start_time saves the last shutdown time
        d["sync_start"] = (
            datetime.fromtimestamp(d["sync_start"]) if ("sync_start" in d) and d["sync_start"] else None
        )
        d["network"] = bdk.Network[d["network"]]
        d["members"] = [PublicKey.parse(pk) for pk in d["members"]]
        return cls(**filtered_for_init(d, cls))

    def renew_own_key(self, keys: Keys | None = None):
        # send new key to memebers
        for member in self.members:
            # run this blocking such that you ensure the messages are out
            # before you reset the connection
            self.dm_connection.async_thread.run_coroutine_blocking(
                self.dm_connection.async_dm_connection.send(
                    BitcoinDM(
                        event=None,
                        label=ChatLabel.DeleteMeRequest,
                        description="",
                        use_compression=self.use_compression,
                        created_at=datetime.now(),
                    ),
                    member,
                )
            )

            # self.dm_connection.send(ProtocolDM(event=None, public_key_bech32=keys.public_key().to_bech32(),please_trust_public_key_bech32=True), member)
            # logger.debug(f"Send my new public key {keys.public_key().to_bech32()} to {member.to_bech32()}")

        keys = keys if keys else Keys.generate()
        self.refresh_dm_connection(keys)
