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
import json
import logging
from abc import abstractmethod
from datetime import datetime, timedelta

from nostr_sdk import (
    Client,
    Event,
    Filter,
    HandleNotification,
    Keys,
    Kind,
    KindEnum,
    NostrSigner,
    Timestamp,
    UnsignedEvent,
    UnwrappedGift,
    nip04_decrypt,
)

from bitcoin_nostr_chat.default_relays import default_delays
from bitcoin_nostr_chat.utils import filtered_for_init

logger = logging.getLogger(__name__)

import base64
import enum
import zlib
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

import bdkpython as bdk
import cbor2
import requests
from bitcoin_qr_tools.data import Data, DataType
from nostr_sdk import (
    Client,
    Event,
    EventId,
    Filter,
    HandleNotification,
    Keys,
    Kind,
    KindEnum,
    NostrSigner,
    PublicKey,
    Relay,
    RelayMessage,
    RelayStatus,
    SecretKey,
    Timestamp,
    nip04_decrypt,
)
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

DM_KIND = KindEnum.PRIVATE_DIRECT_MESSAGE()


def fetch_and_parse_json(url: str) -> Optional[Any]:
    """
    Fetches data from the given URL and parses it as JSON.

    Args:
    url (str): The URL to fetch the data from.

    Returns:
    dict or None: Parsed JSON data if successful, None otherwise.
    """
    try:
        logger.debug(f"fetch_and_parse_json requests.get({url})")
        response = requests.get(url, timeout=2)
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
        return response.json()
    except requests.RequestException as e:
        logger.error(f"An error occurred: {e}")
        return None


def get_recipient_public_key_of_nip04(event: Event) -> Optional[PublicKey]:
    if event.kind().as_enum() != DM_KIND:
        return None
    for tag in event.tags():
        tag_enum = tag.as_enum()
        if tag_enum.is_public_key_tag():
            recipient_public_key: PublicKey = tag_enum.public_key
            return recipient_public_key
    return None


@dataclass
class RelayList:
    relays: List[str]
    last_updated: datetime
    max_age: Optional[int] = 30  # days,  "None" means it is disabled

    @classmethod
    def from_internet(cls) -> "RelayList":
        return RelayList(relays=cls.get_relays(), last_updated=datetime.now())

    @classmethod
    def from_text(cls, text: str, max_age=None) -> "RelayList":
        text = text.replace('"', "").replace(",", "")
        relays = [line.strip() for line in text.strip().split("\n")]
        relays = [line for line in relays if line]
        return RelayList(relays=relays, last_updated=datetime.now(), max_age=max_age)

    def get_subset(self, size: int) -> List[str]:
        return self.relays[: min(len(self.relays), size)]

    def dump(self) -> Dict:
        d = self.__dict__.copy()
        d["last_updated"] = self.last_updated.timestamp()
        return d

    @classmethod
    def from_dump(cls, d: Dict) -> "RelayList":
        d["last_updated"] = datetime.fromtimestamp(d["last_updated"])
        return cls(**filtered_for_init(d, cls))

    def update_relays(self):
        self.relays = self.get_relays()
        self.last_updated = datetime.now()

    def is_stale(self) -> bool:
        if not self.max_age:
            return False
        return self.last_updated < datetime.now() - timedelta(days=self.max_age)

    def update_if_stale(self):
        if self.is_stale():
            self.update_relays()

    @classmethod
    def preferred_relays(cls) -> List[str]:
        return [
            "wss://relay1.nostrchat.io",
            "wss://relay.nostrati.com",
            "wss://relay.minibits.cash",
            "wss://us.nostr.wine",
            "wss://nostr.koning-degraaf.nl",
            "wss://nostr.mom",
        ]

    @classmethod
    def _postprocess_relays(cls, relays) -> List[str]:
        preferred_relays = cls.preferred_relays()
        return preferred_relays + [r for r in relays if r not in preferred_relays]

    @classmethod
    def get_relays(cls, nip: str = "4") -> List[str]:
        result = fetch_and_parse_json(f"https://api.nostr.watch/v1/nip/{nip}")
        logger.debug(f"fetch_and_parse_json returned {result}")
        if result:
            return cls._postprocess_relays(result)
        logger.debug(f"Return default list")
        return cls._postprocess_relays(default_delays())


class BaseDM:
    def __init__(
        self,
        event: Optional[Event] = None,
        author: Optional[PublicKey] = None,
        created_at: Optional[Timestamp] = None,
        use_compression=True,
    ) -> None:
        super().__init__()
        self.event = event
        self.author = author
        self.created_at = created_at
        self.use_compression = use_compression

    @staticmethod
    def delete_none_entries(d: Dict) -> Dict:
        for key, value in list(d.items()):
            if value is None:
                del d[key]
        return d

    def dump(self) -> Dict:
        d = self.__dict__.copy()
        del d["use_compression"]
        d["event"] = self.event.as_json() if self.event else None
        d["author"] = self.author.to_bech32() if self.author else None
        d["created_at"] = self.created_at.as_secs() if self.created_at else None
        return self.delete_none_entries(d)

    def serialize(self) -> str:
        d = self.dump()
        if self.use_compression:
            # try to use as little space as possible
            # first encode the dict into cbor2, then compress,
            # which helps especially for repetative data
            # and then use base85 to (hopefully) use the space as best as possible
            cbor_serialized = cbor2.dumps(d)
            compressed_data = zlib.compress(cbor_serialized)
            base64_encoded_data = base64.b85encode(compressed_data).decode()
            return base64_encoded_data
        else:
            return json.dumps(d)

    @classmethod
    def from_dump(cls, decoded_dict: Dict, network: bdk.Network):
        # decode the data from the string and ensure the type is
        decoded_dict["event"] = Event.from_json(decoded_dict["event"]) if decoded_dict.get("event") else None
        decoded_dict["author"] = (
            PublicKey.from_bech32(decoded_dict["author"]) if decoded_dict.get("author") else None
        )
        decoded_dict["created_at"] = (
            Timestamp.from_secs(decoded_dict["created_at"]) if decoded_dict.get("created_at") else None
        )
        return cls(**filtered_for_init(decoded_dict, cls))

    @classmethod
    def from_serialized(cls, base64_encoded_data: str, network: bdk.Network):

        if base64_encoded_data.startswith("{"):
            # if it is likely a json string, try this method first
            try:
                logger.debug(f"from_serialized json {base64_encoded_data}")
                decoded_dict = json.loads(base64_encoded_data)
                return cls.from_dump(decoded_dict, network=network)
            except Exception:
                pass
                # logger.debug(f"from_serialized: json.loads failed with {base64_encoded_data},  {network}. Trying ")

        try:
            # try first the compressed decoding
            logger.debug(f"from_serialized compressed {base64_encoded_data}")
            decoded_data = base64.b85decode(base64_encoded_data)
            decompressed_data = zlib.decompress(decoded_data)
            decoded_dict = cbor2.loads(decompressed_data)
            return cls.from_dump(decoded_dict, network=network)
        except Exception:
            logger.error(f"from_serialized failed with {base64_encoded_data},  {network}")
            raise

    def __str__(self) -> str:
        return str(self.dump())

    def __eq__(self, other) -> bool:
        if isinstance(other, BaseDM):
            if bool(self.event) != bool(other.event):
                return False
            if self.event and other.event and self.event.as_json() != other.event.as_json():
                # logger.debug(str((self.event.as_json(),  other.event.as_json())))
                return False
            return True
        return False


class ProtocolDM(BaseDM):
    def __init__(
        self,
        public_key_bech32: str,
        please_trust_public_key_bech32: str = None,
        event: Optional[Event] = None,
        author: Optional[PublicKey] = None,
        created_at: Optional[Timestamp] = None,
        use_compression=True,
    ) -> None:
        super().__init__(event=event, author=author, created_at=created_at, use_compression=use_compression)
        self.public_key_bech32 = public_key_bech32
        # this is only when I want the recipient to trust me back
        self.please_trust_public_key_bech32 = please_trust_public_key_bech32

    def __eq__(self, other) -> bool:
        if not super().__eq__(other):
            return False
        if isinstance(other, ProtocolDM):
            return (
                self.public_key_bech32 == other.public_key_bech32
                and self.please_trust_public_key_bech32 == other.please_trust_public_key_bech32
            )
        return False


class ChatLabel(enum.Enum):
    GroupChat = enum.auto()
    SingleRecipient = enum.auto()
    DistrustMeRequest = enum.auto()
    DeleteMeRequest = enum.auto()

    @classmethod
    def from_value(cls, value: int):
        return cls._value2member_map_.get(value)

    @classmethod
    def from_name(cls, name: str):
        return cls._member_map_.get(name)


class BitcoinDM(BaseDM):
    def __init__(
        self,
        label: ChatLabel,
        description: str,
        data: Data = None,
        intended_recipient: str = None,
        event: Optional[Event] = None,
        author: Optional[PublicKey] = None,
        created_at: Optional[Timestamp] = None,
        use_compression=True,
    ) -> None:
        super().__init__(event=event, author=author, created_at=created_at, use_compression=use_compression)
        self.label = label
        self.description = description
        self.data = data
        self.intended_recipient = intended_recipient

    def dump(self) -> Dict:
        d = super().dump()
        d["label"] = self.label.value
        d["data"] = self.data.dump() if self.data else None
        return self.delete_none_entries(d)

    @classmethod
    def from_dump(cls, d: Dict, network: bdk.Network) -> "BitcoinDM":
        d["label"] = ChatLabel.from_value(d.get("label", ChatLabel.GroupChat.value))
        d["data"] = Data.from_dump(d["data"], network=network) if d.get("data") else None
        return cls(**filtered_for_init(d, cls))

    def __eq__(self, other) -> bool:
        if not super().__eq__(other):
            return False
        if isinstance(other, BitcoinDM):
            if self.label != other.label:
                return False
            if self.description != other.description:
                return False
            if bool(self.data) != bool(other.data):
                return False
            if self.data and other.data and self.data.data_as_string() != other.data.data_as_string():
                return False
            return True
        return False


class NotificationHandler(HandleNotification):
    def __init__(
        self,
        my_keys: Keys,
        get_currently_allowed: Callable[[], set[str]],
        queue: deque,
        signal_dm: pyqtSignal,
        from_serialized: Callable[[str], BaseDM],
    ) -> None:
        super().__init__()
        self.queue = queue
        self.get_currently_allowed = get_currently_allowed
        self.my_keys = my_keys
        self.signal_dm = signal_dm
        self.from_serialized = from_serialized

    def is_allowed_message(self, recipient_public_key: PublicKey, author: PublicKey) -> bool:
        logger.debug(f"recipient_public_key = {recipient_public_key}   ")
        if not recipient_public_key:
            logger.debug("recipient_public_key not set")
            return False
        if not author:
            logger.debug("author public_key not set")
            return False

        if recipient_public_key.to_bech32() != self.my_keys.public_key().to_bech32():
            logger.debug("dm is not for me")
            return False

        if author.to_bech32() not in self.get_currently_allowed():
            logger.debug(
                f"author {author.to_bech32()} is not in get_currently_allowed {self.get_currently_allowed()}"
            )
            return False

        logger.debug(f"valid dm: recipient {recipient_public_key.to_bech32()}, author {author.to_bech32()}")
        return True

    async def handle(self, relay_url, subscription_id, event: Event):
        logger.debug(f"Received new {event.kind().as_enum()} event from {relay_url}:   {event.as_json()}")
        if event.kind().as_enum() == KindEnum.ENCRYPTED_DIRECT_MESSAGE():
            try:
                self.handle_nip04_event(event)
            except Exception as e:
                logger.debug(f"Error during content NIP04 decryption: {e}")
        elif event.kind().as_enum() == KindEnum.GIFT_WRAP():
            logger.debug("Decrypting NIP59 event")
            try:
                # Extract rumor
                # from_gift_wrap verifies the seal (encryption) was done correctly
                # from_gift_wrap should fail, if it is not encrypted with my public key (so it is guaranteed to be for me)
                unwrapped_gift = UnwrappedGift.from_gift_wrap(self.my_keys, event)
                sender = unwrapped_gift.sender()

                recipient_public_key = event.public_keys()[0]
                if not self.is_allowed_message(author=sender, recipient_public_key=recipient_public_key):
                    return

                logger.debug(f"unwrapped_gift {unwrapped_gift} sender={sender}")
                rumor: UnsignedEvent = unwrapped_gift.rumor()

                # Check timestamp of rumor
                if rumor.kind().as_enum() == KindEnum.PRIVATE_DIRECT_MESSAGE():
                    msg = rumor.content()
                    logger.debug(f"Received new msg [sealed]: {msg}")
                    self.handle_trusted_dm_for_me(event, sender, msg)
                else:
                    logger.error(f"Do not know how to handle {rumor.kind().as_enum()}.  {rumor.as_json()}")
            except Exception as e:
                logger.debug(f"Error during content NIP59 decryption: {e}")

    def handle_nip04_event(self, event: Event):
        assert event.kind().as_enum() == KindEnum.ENCRYPTED_DIRECT_MESSAGE()
        recipient_public_key = get_recipient_public_key_of_nip04(event)

        if not self.is_allowed_message(recipient_public_key=recipient_public_key, author=event.author()):
            return

        base64_encoded_data = nip04_decrypt(self.my_keys.secret_key(), event.author(), event.content())
        # logger.debug(f"Decrypted dm to: {base64_encoded_data}")
        self.handle_trusted_dm_for_me(event, event.author(), base64_encoded_data)

    def handle_trusted_dm_for_me(self, event: Event, author: PublicKey, base64_encoded_data: str):

        nostr_dm = self.from_serialized(base64_encoded_data)
        nostr_dm.event = event
        nostr_dm.author = author

        if self.dm_is_alreay_in_queue(nostr_dm):
            logger.debug(f"This nostr dm is already in the queue")
            return

        self.queue.append(nostr_dm)
        self.signal_dm.emit(nostr_dm)

        logger.debug(f"Processed dm: {nostr_dm}")

    def dm_is_alreay_in_queue(self, dm: BaseDM) -> bool:
        for item in list(self.queue):
            if not isinstance(item, BaseDM):
                continue
            if item == dm:
                return True
        return False

    async def handle_msg(self, relay_url: str, msg: RelayMessage):
        # logger.debug(f"handle_msg {relay_url}: {msg}")
        None


class AsyncDmConnection(QObject):
    def __init__(
        self,
        signal_dm: pyqtSignal,
        from_serialized: Callable[[str], BaseDM],
        keys: Keys,
        get_currently_allowed: Callable[[], Set[str]],
        use_timer: bool = False,
        events: list[Event] = None,
        relay_list: RelayList = None,
    ) -> None:
        super().__init__()
        self.signal_dm = signal_dm
        self.use_timer = use_timer
        self.get_currently_allowed = get_currently_allowed
        self.from_serialized = from_serialized
        self.minimum_connect_relays = 2
        self.relay_list = relay_list if relay_list else RelayList.from_internet()
        self.counter_no_connected_relay = 0

        self.keys: Keys = keys
        self.client: Client = None
        # self.queue stores received events and is also used for self.dump
        self.queue: deque[BaseDM] = deque(maxlen=10000)
        # self.events is used for replaying events from dump
        self.events: list[Event] = events if events else []
        self.current_subscription_dict: Dict[str, PublicKey] = {}  # subscription_id: PublicKey
        self.timer = QTimer()

        # Initialize the client with the private key
        self.client = None

    async def init_client(self):
        return await self.refresh_client()

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()

    async def refresh_client(self):
        if self.client:
            await self.client.disconnect()

        signer = NostrSigner.keys(self.keys)
        self.client = Client(signer)

        self.notification_handler = NotificationHandler(
            my_keys=self.keys,
            queue=self.queue,
            signal_dm=self.signal_dm,
            get_currently_allowed=self.get_currently_allowed,
            from_serialized=self.from_serialized,
        )
        await self.client.handle_notifications(self.notification_handler)

    def public_key_was_published(self, public_key: PublicKey) -> bool:
        for dm in list(self.queue):
            if isinstance(dm, ProtocolDM):
                if dm.public_key_bech32 == public_key.to_bech32():
                    return True
        return False

    async def get_connected_relays(self) -> List[Relay]:
        relays = await self.client.relays()
        connected_relays: List[Relay] = [
            relay for relay in relays.values() if await relay.status() == RelayStatus.CONNECTED
        ]
        logger.debug(f"connected_relays = {connected_relays} of all relays {relays}")
        return connected_relays

    async def send(self, dm: BaseDM, receiver: PublicKey) -> Optional[EventId]:
        await self.ensure_connected()
        try:
            event_id = await self.client.send_private_msg(receiver, dm.serialize(), reply_to=None)
            logger.debug(f"sent {dm}")
            return event_id
        except Exception as e:
            logger.error(f"Error sending direct message: {e}")
            return None

    def _get_filters(self, recipient: PublicKey, start_time: datetime = None) -> List[Filter]:
        this_filter = (
            Filter().pubkey(recipient).kinds([Kind.from_enum(DM_KIND), Kind.from_enum(KindEnum.GIFT_WRAP())])
        )

        if start_time:
            this_filter = this_filter.since(timestamp=Timestamp.from_secs(int(start_time.timestamp())))

        return [this_filter]

    async def subscribe(self, start_time: datetime = None) -> str:
        "overwrites previous filters"
        if not await self.get_connected_relays():
            await self.ensure_connected()

        self._start_timer()

        filters = self._get_filters(self.keys.public_key(), start_time=start_time)
        logger.debug(f"Subscribe to {filters}")
        subscription_id = await self.client.subscribe(filters, opts=None)

        self.current_subscription_dict[subscription_id] = self.keys.public_key()
        logger.debug(
            f"Added subscription_id {subscription_id} for public_key {self.keys.public_key().to_bech32()}"
        )
        return subscription_id

    async def unsubscribe_all(self):
        await self.unsubscribe(list(self.current_subscription_dict.values()))

    async def unsubscribe(self, public_keys: List[PublicKey]):
        for subscription_id, pub_key in list(self.current_subscription_dict.items()):
            if pub_key in public_keys:
                await self.client.unsubscribe(subscription_id)
                del self.current_subscription_dict[subscription_id]

    def _start_timer(self, delay_retry_connect=5):
        if not self.use_timer:
            return
        if self.timer.isActive():
            return
        self.timer.setInterval(delay_retry_connect * 1000)
        self.timer.timeout.connect(self.ensure_connected)
        self.timer.start()

    async def ensure_connected(self):
        if len(await self.get_connected_relays()) >= min(
            self.minimum_connect_relays, len(self.relay_list.relays)
        ):
            return

        self.relay_list.update_if_stale()

        relay_subset = self.relay_list.get_subset(
            self.minimum_connect_relays + self.counter_no_connected_relay
        )
        await self.client.add_relays(relay_subset)
        await self.client.connect()
        logger.debug(
            f"add_relay {relay_subset}, currently get_connected_relays={await self.get_connected_relays()}"
        )
        # assume the connections are successfull
        # however if not, then next time try 1 more connection
        # sleep(0.1)
        self.counter_no_connected_relay += 1

    def dump(
        self,
        forbidden_data_types: List[DataType] = None,
    ):
        def include_item(item: BaseDM) -> bool:
            if isinstance(item, BitcoinDM):
                if forbidden_data_types is not None:
                    if item.data and item.data.data_type in forbidden_data_types:
                        return False
            if isinstance(item, ProtocolDM):
                return False
            return True

        return {
            "use_timer": self.use_timer,
            "keys": self.keys.secret_key().to_bech32(),
            "events": [item.event.as_json() for item in self.queue if item.event and include_item(item)],
            "relay_list": self.relay_list.dump(),
        }

    @classmethod
    def from_dump(
        cls,
        d: Dict,
        signal_dm: pyqtSignal,
        from_serialized: Callable[[str], BaseDM],
        get_currently_allowed: Callable[[], Set[str]],
    ) -> "AsyncDmConnection":
        d["keys"] = Keys(secret_key=SecretKey.from_bech32(d["keys"]))

        d["events"] = [Event.from_json(json_item) for json_item in d["events"]]
        d["relay_list"] = RelayList.from_dump(d["relay_list"]) if "relay_list" in d else None

        return cls(
            **filtered_for_init(d, cls),
            signal_dm=signal_dm,
            from_serialized=from_serialized,
            get_currently_allowed=get_currently_allowed,
        )

    async def replay_events(self):
        # now handle the events as if they came from a relay
        for event in self.events:
            await self.notification_handler.handle(
                relay_url="from_storage", event=event, subscription_id="replay"
            )


class AsyncThread(QThread):
    result_ready = pyqtSignal(object, object)  # Signal to return result with a callback

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def run(self):
        self.loop.run_forever()

    def run_coroutine(self, coro, on_done=None):
        """Run coroutine and attach callback if provided."""

        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        future.add_done_callback(lambda f: self._handle_result(f, on_done))

    def _handle_result(self, future, callback):
        """Handle the result of the coroutine and emit signal with result and callback."""
        result = future.result()
        logger.debug(f"_handle_result {result, callback}")
        self.result_ready.emit(result, callback)

    @classmethod
    def run_coroutine_blocking(cls, coro):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.close()
        return result


class DmConnection(QObject):
    def __init__(
        self,
        signal_dm: pyqtSignal,
        from_serialized: Callable[[str], BaseDM],
        keys: Keys,
        get_currently_allowed: Callable[[], Set[str]],
        use_timer: bool = False,
        events: list[Event] = None,
        relay_list: RelayList = None,
        async_dm_connection: AsyncDmConnection = None,
    ) -> None:
        super().__init__()

        self.async_thread = AsyncThread()
        self.async_thread.result_ready.connect(
            lambda result, callback: callback(result)
            if callback
            else (logger.debug(f"Finished {callback} with result {result}" if result else None))
        )
        self.async_thread.start()

        self.async_dm_connection = (
            async_dm_connection
            if async_dm_connection
            else AsyncDmConnection(
                signal_dm=signal_dm,
                from_serialized=from_serialized,
                keys=keys,
                use_timer=use_timer,
                events=events,
                get_currently_allowed=get_currently_allowed,
                relay_list=relay_list,
            )
        )

        self.async_thread.run_coroutine(self.async_dm_connection.init_client(), on_done=None)

    @classmethod
    def from_dump(
        cls,
        d: Dict,
        signal_dm: pyqtSignal,
        from_serialized: Callable[[str], BaseDM],
        get_currently_allowed: Callable[[], Set[str]],
    ) -> "DmConnection":
        async_dm_connection = AsyncDmConnection.from_dump(
            d,
            signal_dm=signal_dm,
            from_serialized=from_serialized,
            get_currently_allowed=get_currently_allowed,
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
        forbidden_data_types: List[DataType] = None,
    ):
        return self.async_dm_connection.dump(forbidden_data_types=forbidden_data_types)

    def send(self, dm: BaseDM, receiver: PublicKey, on_done: Callable[[Optional[EventId]], None] = None):
        self.async_thread.run_coroutine(self.async_dm_connection.send(dm, receiver), on_done=on_done)

    def get_connected_relays(self) -> List[Relay]:
        return self.async_thread.run_coroutine_blocking(self.async_dm_connection.get_connected_relays())

    def unsubscribe_all(self, on_done: Callable[[], None] = None):
        self.async_thread.run_coroutine(self.async_dm_connection.unsubscribe_all(), on_done=on_done)

    def disconnect(self, on_done: Callable[[], None] = None):
        self.async_thread.run_coroutine(self.async_dm_connection.disconnect(), on_done=on_done)

    def refresh_client(self, on_done: Callable[[], None] = None):
        self.async_thread.run_coroutine(self.async_dm_connection.refresh_client(), on_done=on_done)

    def subscribe(self, start_time: datetime = None, on_done: Callable[[str], None] = None):
        self.async_thread.run_coroutine(self.async_dm_connection.subscribe(start_time), on_done=on_done)

    def unsubscribe(self, public_keys: List[PublicKey], on_done: Callable[[], None] = None):
        self.async_thread.run_coroutine(self.async_dm_connection.unsubscribe(public_keys), on_done=on_done)

    def replay_events(self, on_done: Callable[[], None] = None):
        self.async_thread.run_coroutine(self.async_dm_connection.replay_events(), on_done=on_done)


class BaseProtocol(QObject):
    signal_dm = pyqtSignal(BaseDM)

    def __init__(
        self,
        keys: Keys = None,
        dm_connection_dump: dict = None,
        start_time: datetime = None,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        super().__init__()
        self.start_time = start_time

        self.dm_connection = (
            DmConnection.from_dump(
                d=dm_connection_dump,
                signal_dm=self.signal_dm,
                from_serialized=self.from_serialized,
                get_currently_allowed=self.get_currently_allowed,
            )
            if dm_connection_dump
            else DmConnection(
                self.signal_dm,
                from_serialized=self.from_serialized,
                keys=keys,
                get_currently_allowed=self.get_currently_allowed,
            )
        )

    @abstractmethod
    def subscribe(self):
        pass

    @abstractmethod
    def from_serialized(self, base64_encoded_data) -> BaseDM:
        pass

    def refresh_dm_connection(self, keys: Keys = None, relay_list: RelayList = None):
        keys = keys if keys else self.dm_connection.async_dm_connection.keys
        relay_list = relay_list if relay_list else self.dm_connection.async_dm_connection.relay_list

        self.dm_connection.disconnect()
        self.dm_connection.async_dm_connection.keys = keys
        self.dm_connection.async_dm_connection.relay_list = relay_list
        self.start_time = None
        self.dm_connection.refresh_client()
        self.subscribe()

    def set_relay_list(self, relay_list: RelayList):
        self.refresh_dm_connection(relay_list=relay_list)

    @abstractmethod
    def get_currently_allowed(self) -> Set[str]:
        pass


class NostrProtocol(BaseProtocol):
    signal_dm = pyqtSignal(ProtocolDM)

    def __init__(
        self,
        network: bdk.Network,
        keys: Keys = None,
        dm_connection_dump: Dict = None,
        start_time: datetime = None,
        use_compression=True,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        self.network = network
        super().__init__(keys=keys, dm_connection_dump=dm_connection_dump, start_time=start_time)
        self.use_compression = use_compression

    def get_currently_allowed(self) -> Set[str]:
        return set([self.dm_connection.async_dm_connection.keys.public_key().to_bech32()])

    def from_serialized(self, base64_encoded_data) -> ProtocolDM:
        return ProtocolDM.from_serialized(base64_encoded_data=base64_encoded_data, network=self.network)

    def list_public_keys(self):
        pass

    def publish_public_key(self, author_public_key: PublicKey, force=False):
        logger.debug(
            f"starting publish_public_key {self.dm_connection.async_dm_connection.keys.public_key().to_bech32()}"
        )
        if not force and self.dm_connection.async_dm_connection.public_key_was_published(author_public_key):
            logger.debug(f"{author_public_key.to_bech32()} was published already. No need to do it again")
            return
        dm = ProtocolDM(
            public_key_bech32=author_public_key.to_bech32(), event=None, use_compression=self.use_compression
        )
        self.dm_connection.send(dm, self.dm_connection.async_dm_connection.keys.public_key())
        logger.debug(
            f"done publish_public_key {self.dm_connection.async_dm_connection.keys.public_key().to_bech32()}"
        )

    def publish_trust_me_back(self, author_public_key: PublicKey, recipient_public_key: PublicKey):
        dm = ProtocolDM(
            public_key_bech32=author_public_key.to_bech32(),
            please_trust_public_key_bech32=recipient_public_key.to_bech32(),
            event=None,
            use_compression=self.use_compression,
        )
        self.dm_connection.send(dm, self.dm_connection.async_dm_connection.keys.public_key())

    def subscribe(self):
        def on_done(subscription_id: str):
            logger.debug(f"Successfully subscribed to {subscription_id}")

        self.dm_connection.subscribe(start_time=None, on_done=on_done)

    def dump(self):
        return {
            # the next starttime is the current time
            "start_time": datetime.now().timestamp(),
            "dm_connection_dump": self.dm_connection.dump(),
        }

    @classmethod
    def from_dump(cls, d: Dict, network: bdk.Network, use_compression=True) -> "NostrProtocol":
        d["start_time"] = datetime.fromtimestamp(d["start_time"])

        return cls(**filtered_for_init(d, cls), network=network, use_compression=use_compression)


class GroupChat(BaseProtocol):
    signal_dm = pyqtSignal(BitcoinDM)

    def __init__(
        self,
        network: bdk.Network,
        keys: Keys = None,
        dm_connection_dump: dict = None,
        start_time: datetime = None,
        members: List[PublicKey] = None,
        use_compression=True,
    ) -> None:
        "Either keys or dm_connection_dump must be given"
        self.members: List[PublicKey] = members if members else []
        self.network = network
        self.use_compression = use_compression
        super().__init__(
            keys=keys,
            dm_connection_dump=dm_connection_dump,
            start_time=start_time,
        )

    def get_currently_allowed(self) -> Set[str]:
        return set([member.to_bech32() for member in self.members_including_me()])

    def from_serialized(self, base64_encoded_data: str) -> BitcoinDM:
        return BitcoinDM.from_serialized(base64_encoded_data, network=self.network)

    def add_member(self, new_member: PublicKey):
        if new_member.to_bech32() not in [k.to_bech32() for k in self.members]:
            self.members.append(new_member)
            self.dm_connection.subscribe(new_member)
            logger.debug(f"Add {new_member.to_bech32()} as trusted")

    def remove_member(self, remove_member: PublicKey):
        members_bech32 = [k.to_bech32() for k in self.members]
        if remove_member.to_bech32() in members_bech32:
            self.members.pop(members_bech32.index(remove_member.to_bech32()))
            self.dm_connection.unsubscribe([remove_member])
            logger.debug(f"Removed {remove_member.to_bech32()}")

    def send(self, dm: BitcoinDM, send_also_to_me=True):
        recipients = self.members_including_me() if send_also_to_me else self.members
        for public_key in recipients:
            self.dm_connection.send(dm, public_key)
            logger.debug(f"Send to {public_key.to_bech32()}")

        if not self.members:
            logger.debug(f"Sending not done, since self.members is empty")

    def members_including_me(self):
        return self.members + [self.dm_connection.async_dm_connection.keys.public_key()]

    def subscribe(self):
        self.dm_connection.subscribe(start_time=self.start_time)

    def dump(self):
        forbidden_data_types = [DataType.LabelsBip329]
        return {
            # the next starttime is the current time
            "start_time": datetime.now().timestamp(),
            "dm_connection_dump": self.dm_connection.dump(forbidden_data_types=forbidden_data_types),
            "members": [member.to_bech32() for member in self.members],
        }

    @classmethod
    def from_dump(cls, d: Dict, network: bdk.Network, use_compression=True) -> "NostrProtocol":
        d["start_time"] = datetime.fromtimestamp(d["start_time"])

        d["members"] = [PublicKey.from_bech32(pk) for pk in d["members"]]
        return cls(**filtered_for_init(d, cls), network=network, use_compression=use_compression)

    def renew_own_key(self):
        # send new key to memebers
        for member in self.members:
            self.dm_connection.send(
                BitcoinDM(
                    event=None,
                    label=ChatLabel.DeleteMeRequest,
                    description="",
                    use_compression=self.use_compression,
                ),
                member,
            )
            # self.dm_connection.send(ProtocolDM(event=None, public_key_bech32=keys.public_key().to_bech32(),please_trust_public_key_bech32=True), member)
            # logger.debug(f"Send my new public key {keys.public_key().to_bech32()} to {member.to_bech32()}")

        self.refresh_dm_connection(Keys.generate())
