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
import threading
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

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.default_relays import get_default_delays, get_preferred_relays
from bitcoin_nostr_chat.utils import filtered_for_init

logger = logging.getLogger(__name__)

import base64
import enum
import zlib
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

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
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtBoundSignal, pyqtSignal

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
        tag_standart = tag.as_standardized()
        if tag_standart and tag_standart.is_public_key_tag():
            recipient_public_key: PublicKey = tag_standart.PUBLIC_KEY_TAG.public_key
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
    def _postprocess_relays(cls, relays) -> List[str]:
        preferred_relays = get_preferred_relays()
        return preferred_relays + [r for r in relays if r not in preferred_relays]

    # @classmethod
    # def get_relays_from_nostr_watch(cls, nips: List[int] = [17, 4]) -> List[str]:
    #     all_relays: List[str] = []
    #     for nip in nips:
    #         url = f"https://api.nostr.watch/v1/nip/{nip}"
    #         result = fetch_and_parse_json(url)
    #         logger.debug(f"fetch_and_parse_json  {url} returned {result}")
    #         if result:
    #             all_relays += result

    #     return all_relays

    @classmethod
    def get_relays(cls, nips: List[int] = [17, 4]) -> List[str]:
        # nostr.watch is not working currently
        # all_relays =  cls.get_relays_from_nostr_watch(nips=nips)
        # if all_relays:
        #     return cls._postprocess_relays(all_relays)

        logger.debug(f"Return default list")
        return cls._postprocess_relays(get_default_delays())


class BaseDM:
    def __init__(
        self,
        created_at: datetime,
        event: Optional[Event] = None,
        author: Optional[PublicKey] = None,
        use_compression=DEFAULT_USE_COMPRESSION,
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
        d = {}
        d["event"] = self.event.as_json() if self.event else None
        d["author"] = self.author.to_bech32() if self.author else None
        d["created_at"] = self.created_at.timestamp()
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
            logger.debug(f"{100*(1-len(compressed_data)/(1+len(cbor_serialized))):.1f}% compression")
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
        try:
            # in the old format created_at was optional. So i have to catch this.
            decoded_dict["created_at"] = datetime.fromtimestamp(decoded_dict["created_at"])
        except:
            decoded_dict["created_at"] = datetime.now() - timedelta(
                days=30
            )  # assume the legacy format is at least 30 days old

        logger.info(f" decoded_dict  {decoded_dict}")
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
            logger.error(f"from_serialized failed with {base64_encoded_data} ")
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
        created_at: datetime,
        please_trust_public_key_bech32: str | None = None,
        event: Optional[Event] = None,
        author: Optional[PublicKey] = None,
        use_compression=DEFAULT_USE_COMPRESSION,
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

    def dump(self) -> Dict:
        d = super().dump()
        d["public_key_bech32"] = self.public_key_bech32
        d["please_trust_public_key_bech32"] = self.please_trust_public_key_bech32
        return self.delete_none_entries(d)


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
        created_at: datetime,
        description: str,
        data: Data | None = None,
        intended_recipient: str | None = None,
        event: Optional[Event] = None,
        author: Optional[PublicKey] = None,
        use_compression=DEFAULT_USE_COMPRESSION,
    ) -> None:
        super().__init__(event=event, author=author, created_at=created_at, use_compression=use_compression)
        self.label = label
        self.description = description
        self.data = data
        self.intended_recipient = intended_recipient

    def dump(self) -> Dict:
        d = super().dump()
        d["label"] = self.label.value
        d["description"] = self.description
        d["data"] = self.data.dump() if self.data else None
        d["intended_recipient"] = self.intended_recipient
        return self.delete_none_entries(d)

    @classmethod
    def from_dump(cls, d: Dict, network: bdk.Network) -> "BitcoinDM":
        d["label"] = ChatLabel.from_value(d.get("label", ChatLabel.GroupChat.value))
        d["data"] = Data.from_dump(d["data"], network=network) if d.get("data") else None
        return super().from_dump(d, network)

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

    def __str__(self) -> str:
        "Returns relevant data in a human readable form"
        d = {}
        d["label"] = self.label.name
        d["data"] = self.data.data_as_string() if self.data else None
        # d["event"]=str(self.event)
        d["author"] = self.author.to_bech32() if self.author else None
        d["created_at"] = self.created_at.isoformat()
        d["use_compression"] = self.use_compression
        d["description"] = self.description
        d["intended_recipient"] = str(self.intended_recipient)
        return json.dumps(d, indent=2)


class PrintHandler(HandleNotification):
    def __init__(self, name) -> None:
        super().__init__()
        self.name = name

    async def handle(self, relay_url, subscription_id, event: Event):
        logger.debug(
            f"{self.name}: Received new {event.kind().as_enum()} event from {relay_url}:   {event.as_json()}"
        )


class NotificationHandler(HandleNotification):
    def __init__(
        self,
        my_keys: Keys,
        get_currently_allowed: Callable[[], set[str]],
        processed_dms: deque[BaseDM],
        signal_dm: pyqtBoundSignal,
        from_serialized: Callable[[str], BaseDM],
    ) -> None:
        super().__init__()
        self.processed_dms: deque[BaseDM] = processed_dms
        self.untrusted_events: deque[Event] = deque(maxlen=10000)
        self.get_currently_allowed = get_currently_allowed
        self.my_keys = my_keys
        self.signal_dm = signal_dm
        self.from_serialized = from_serialized
        signal_dm.connect(self.on_signal_dm)

    def is_allowed_message(self, recipient_public_key: PublicKey, author: PublicKey) -> bool:
        logger.debug(f"recipient_public_key = {recipient_public_key.to_bech32()}   ")
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
                    self.untrusted_events.append(event)
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
        if not recipient_public_key:
            logger.debug(f"event {event.id()} doesnt contain a 04 tag and public key")
            return

        if not self.is_allowed_message(recipient_public_key=recipient_public_key, author=event.author()):
            self.untrusted_events.append(event)
            return

        base64_encoded_data = nip04_decrypt(self.my_keys.secret_key(), event.author(), event.content())
        # logger.debug(f"Decrypted dm to: {base64_encoded_data}")
        self.handle_trusted_dm_for_me(event, event.author(), base64_encoded_data)

    def handle_trusted_dm_for_me(self, event: Event, author: PublicKey, base64_encoded_data: str):
        nostr_dm: BaseDM = self.from_serialized(base64_encoded_data)
        nostr_dm.event = event
        nostr_dm.author = author

        if self.dm_is_alreay_processed(nostr_dm):
            logger.debug(f"This nostr dm is already in the processed_dms")
            return

        self.signal_dm.emit(nostr_dm)

        logger.debug(f"Processed dm: {nostr_dm}")

    def on_signal_dm(self, dm: BaseDM):
        self.processed_dms.append(dm)

    def dm_is_alreay_processed(self, dm: BaseDM) -> bool:
        for item in list(self.processed_dms):
            if not isinstance(item, BaseDM):
                continue  # type: ignore
            if item == dm:
                return True
        return False

    async def handle_msg(self, relay_url: str, msg: RelayMessage):
        # logger.debug(f"handle_msg {relay_url}: {msg}")
        pass

    async def replay_events(
        self, events: Iterable[Event], relay_url="from_storage", subscription_id="replay"
    ):
        # now handle the dms_from_dump as if they came from a relay
        for event in events:
            await self.handle(relay_url=relay_url, event=event, subscription_id=subscription_id)

    async def replay_untrusted_events(self):
        await self.replay_events([event for event in self.untrusted_events])


class AsyncDmConnection(QObject):
    def __init__(
        self,
        signal_dm: pyqtBoundSignal,
        from_serialized: Callable[[str], BaseDM],
        keys: Keys,
        get_currently_allowed: Callable[[], Set[str]],
        use_timer: bool = False,
        dms_from_dump: Iterable[BaseDM] | None = None,
        relay_list: RelayList | None = None,
    ) -> None:
        super().__init__()
        self.signal_dm = signal_dm
        self.use_timer = use_timer
        self.get_currently_allowed = get_currently_allowed
        self.from_serialized = from_serialized
        self.minimum_connect_relays = 8
        self.relay_list = relay_list if relay_list else RelayList.from_internet()
        self.counter_no_connected_relay = 0

        self.keys: Keys = keys

        # self.dms_from_dump is used for replaying events from dump
        self.dms_from_dump: deque[BaseDM] = deque(dms_from_dump) if dms_from_dump else deque()
        self.current_subscription_dict: Dict[str, PublicKey] = {}  # subscription_id: PublicKey
        self.timer = QTimer()

        signer = NostrSigner.keys(self.keys)
        self.client = Client(signer)

        self.notification_handler = NotificationHandler(
            my_keys=self.keys,
            processed_dms=deque(),  # do  not set here the dms_from_dump, otherwise the replaying messages are all ignored
            signal_dm=self.signal_dm,
            get_currently_allowed=self.get_currently_allowed,
            from_serialized=self.from_serialized,
        )

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
            processed_dms=self.notification_handler.processed_dms,
            signal_dm=self.signal_dm,
            get_currently_allowed=self.get_currently_allowed,
            from_serialized=self.from_serialized,
        )
        await self.client.handle_notifications(self.notification_handler)

    def public_key_was_published(self, public_key: PublicKey) -> bool:
        for dm in list(self.notification_handler.processed_dms):
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
            serialized_dm = dm.serialize()
            event_id = await self.client.send_private_msg(receiver, serialized_dm, reply_to=None)
            logger.debug(f"sent {dm} with {len(serialized_dm)} characters")
            return event_id
        except Exception as e:
            logger.error(f"Error sending direct message: {e}")
            return None

    def _get_filters(self, recipient: PublicKey, start_time: datetime | None = None) -> List[Filter]:
        this_filter = (
            Filter().pubkey(recipient).kinds([Kind.from_enum(DM_KIND), Kind.from_enum(KindEnum.GIFT_WRAP())])
        )

        if start_time:
            timestamp = Timestamp.from_secs(int(start_time.timestamp()))
            logger.error(f"Subscribe to {recipient.to_bech32()} from {timestamp.to_human_datetime()}")
            this_filter = this_filter.since(timestamp=timestamp)

        return [this_filter]

    async def subscribe(self, start_time: datetime | None = None) -> str:
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
        self.timer.timeout.connect(self._timer_ensure_connected)
        self.timer.start()

    def _timer_ensure_connected(self):
        asyncio.create_task(self.ensure_connected())

    async def ensure_connected(self):
        if len(await self.get_connected_relays()) >= min(
            self.minimum_connect_relays, len(self.relay_list.relays)
        ):
            return

        if not self.client:
            await self.refresh_client()
            if not self.client:
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
        forbidden_data_types: List[DataType] | None = None,
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
            "dms_from_dump": [
                item.dump() for item in self.notification_handler.processed_dms if item and include_item(item)
            ],
            # TODO: This might be added in the future,
            # to allow restoring labels from devices that are connected after the wallet has been shut down
            # "untrusted_events": [
            #     item.dump() for item in self.notification_handler.untrusted_events if item and include_item(item)
            # ],
            "relay_list": self.relay_list.dump(),
        }

    @classmethod
    def from_dump(
        cls,
        d: Dict,
        signal_dm: pyqtBoundSignal,
        from_serialized: Callable[[str], BaseDM],
        get_currently_allowed: Callable[[], Set[str]],
        network: bdk.Network,
    ) -> "AsyncDmConnection":
        d["keys"] = Keys(secret_key=SecretKey.from_bech32(d["keys"]))

        d["dms_from_dump"] = [BitcoinDM.from_dump(d, network=network) for d in d.get("dms_from_dump", [])]
        d["relay_list"] = RelayList.from_dump(d["relay_list"]) if "relay_list" in d else None

        return cls(
            **filtered_for_init(d, cls),
            signal_dm=signal_dm,
            from_serialized=from_serialized,
            get_currently_allowed=get_currently_allowed,
        )

    async def replay_events_from_dump(self):
        # now handle the dms_from_dump as if they came from a relay
        await self.notification_handler.replay_events([dm.event for dm in self.dms_from_dump if dm.event])


class AsyncThread(QThread):
    result_ready = pyqtSignal(object, object)  # Signal to return result with a callback

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.loop = asyncio.new_event_loop()
        # Do not set the event loop globally here
        self.loop_started = threading.Event()  # Synchronization event

        self.start()

    def start(self, priority: QThread.Priority = QThread.Priority.NormalPriority) -> None:
        super().start(priority=priority)
        # Wait until the event loop is confirmed running,
        # otherwise self.run_coroutine calls will fail
        self.loop_started.wait()

    def run(self):
        # Set the event loop for this thread
        asyncio.set_event_loop(self.loop)
        self.loop_started.set()  # Set the event to indicate the loop is ready
        try:
            self.loop.run_forever()
        finally:
            # Clean up tasks and close the loop
            self._cleanup_loop()

    def _cleanup_loop(self):
        # Cancel all pending tasks
        tasks = [task for task in asyncio.all_tasks(self.loop) if not task.done()]
        for task in tasks:
            task.cancel()
        # Run the loop until all tasks are cancelled
        self.loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        self.loop.close()

    def run_coroutine(self, coro, on_done=None):
        """Run coroutine and attach callback if provided."""
        if not self.loop.is_running():
            logger.debug(f"{self.__class__.__name__} loop already stopped")
            return
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        if on_done:
            future.add_done_callback(lambda f: self._handle_result(f, on_done))

    def _handle_result(self, future, callback):
        """Handle the result of the coroutine and emit signal with result and callback."""
        try:
            result = future.result()
            self.result_ready.emit(result, callback)
        except Exception as e:
            # Handle exceptions in the coroutine
            self.result_ready.emit(e, callback)

    def stop(self):
        """Stop the event loop safely."""
        # Schedule the loop to stop
        if not self.loop.is_running():
            logger.debug(f"{self.__class__.__name__} loop already stopped")
            return
        self.loop.call_soon_threadsafe(self.loop.stop)
        logger.debug(f"{self.__class__.__name__} call_soon_threadsafe(self.loop.stop)")
        # Wait for the thread to finish
        self.wait()
        logger.debug(f"{self.__class__.__name__} done: self.wait()")

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
            lambda result, callback: (
                callback(result)
                if callback
                else (logger.debug(f"Finished {callback} with result {result}" if result else None))
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

        self.async_thread.run_coroutine(self.async_dm_connection.init_client(), on_done=None)

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
        self.async_thread.run_coroutine(self.async_dm_connection.send(dm, receiver), on_done=on_done)

    def get_connected_relays(self) -> List[Relay]:
        return self.async_thread.run_coroutine_blocking(self.async_dm_connection.get_connected_relays())

    def unsubscribe_all(self, on_done: Callable[[], None] | None = None):
        self.async_thread.run_coroutine(self.async_dm_connection.unsubscribe_all(), on_done=on_done)

    def disconnect(self, on_done: Callable[[], None] | None = None):
        self.async_thread.run_coroutine(self.async_dm_connection.disconnect(), on_done=on_done)

    def refresh_client(self, on_done: Callable[[], None] | None = None):
        self.async_thread.run_coroutine(self.async_dm_connection.refresh_client(), on_done=on_done)

    def subscribe(self, start_time: datetime | None = None, on_done: Callable[[str], None] | None = None):
        self.async_thread.run_coroutine(self.async_dm_connection.subscribe(start_time), on_done=on_done)

    def unsubscribe(self, public_keys: List[PublicKey], on_done: Callable[[], None] | None = None):
        self.async_thread.run_coroutine(self.async_dm_connection.unsubscribe(public_keys), on_done=on_done)

    def replay_events_from_dump(self, on_done: Callable[[], None] | None = None):
        self.async_thread.run_coroutine(self.async_dm_connection.replay_events_from_dump(), on_done=on_done)

    def stop(self):
        self.async_thread.stop()

    def run(self, coro, on_done: Callable[[], None] | None = None):
        self.async_thread.run_coroutine(coro, on_done=on_done)

    def run_blocking(self, coro):
        self.async_thread.run_coroutine_blocking(coro)


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

    def refresh_dm_connection(self, keys: Keys | None = None, relay_list: RelayList | None = None):
        keys = keys if keys else self.dm_connection.async_dm_connection.keys
        relay_list = relay_list if relay_list else self.dm_connection.async_dm_connection.relay_list

        self.dm_connection.disconnect()
        self.dm_connection.async_dm_connection.keys = keys
        self.dm_connection.async_dm_connection.relay_list = relay_list
        # prevent redownloading the messages by setting the time to now
        self.sync_start = datetime.now()
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
            logger.debug(f"{self.__class__.__name__}  Successfully subscribed to {subscription_id}")

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
        d["members"] = [PublicKey.from_bech32(pk) for pk in d["members"]]
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
