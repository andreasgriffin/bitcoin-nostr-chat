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
from typing import Any, Callable, Iterable, Optional

import requests
from nostr_sdk import (
    Event,
    HandleNotification,
    Keys,
    KindEnum,
    NostrSigner,
    PublicKey,
    RelayMessage,
    TagKind,
    UnsignedEvent,
    UnwrappedGift,
    nip04_decrypt,
)
from PyQt6.QtCore import pyqtBoundSignal

from bitcoin_nostr_chat.base_dm import BaseDM

logger = logging.getLogger(__name__)

DM_KIND = KindEnum.PRIVATE_DIRECT_MESSAGE()
GIFTWRAP = KindEnum.GIFT_WRAP()


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
    tags = event.tags()
    tag_standart = tags.find_standardized(TagKind.ENCRYPTED())
    if tag_standart and tag_standart.is_public_key_tag():
        recipient_public_key: PublicKey = tag_standart.PUBLIC_KEY_TAG.public_key
        return recipient_public_key
    return None


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

    async def handle(self, relay_url: "str", subscription_id: "str", event: "Event"):
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
                unwrapped_gift: UnwrappedGift = await UnwrappedGift.from_gift_wrap(
                    NostrSigner.keys(self.my_keys), event
                )
                sender = unwrapped_gift.sender()

                recipient_public_key = event.tags().public_keys()[0]
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

    async def handle_msg(self, relay_url: "str", msg: "RelayMessage"):
        # logger.debug(f"handle_msg {relay_url}: {msg}")
        return

    async def replay_events(
        self, events: Iterable[Event], relay_url="from_storage", subscription_id="replay"
    ):
        # now handle the dms_from_dump as if they came from a relay
        for event in events:
            await self.handle(relay_url=relay_url, event=event, subscription_id=subscription_id)

    async def replay_untrusted_events(self):
        await self.replay_events([event for event in self.untrusted_events])
