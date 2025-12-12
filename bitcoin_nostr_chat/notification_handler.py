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
from collections.abc import Callable, Iterable
from typing import Any, Generic

import requests
from bitcoin_safe_lib.gui.qt.signal_tracker import SignalProtocol, SignalTracker
from nostr_sdk import (
    Event,
    HandleNotification,
    Keys,
    KindStandard,
    NostrSigner,
    PublicKey,
    RelayMessage,
    UnsignedEvent,
    UnwrappedGift,
)

from bitcoin_nostr_chat.base_dm import BaseDM, T_BaseDM

logger = logging.getLogger(__name__)

DM_KIND = KindStandard.PRIVATE_DIRECT_MESSAGE
GIFTWRAP = KindStandard.GIFT_WRAP


def fetch_and_parse_json(url: str) -> Any | None:
    """
    Fetches data from the given URL and parses it as JSON.

    Args:
    url (str): The URL to fetch the data from.

    Returns:
    dict or None: Parsed JSON data if successful, None otherwise.
    """
    try:
        logger.debug(f"fetch_and_parse_json requests.get({url=})")
        response = requests.get(url, timeout=2)
        # Raises an HTTPError if the HTTP request returned an unsuccessful status code
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"An error occurred: {e}")
        return None


class PrintHandler(HandleNotification):
    def __init__(self, name) -> None:
        super().__init__()
        self.name = name

    async def handle(self, relay_url, subscription_id, event: Event):
        logger.debug(f"{self.name}: Received new {event.kind()} event from {relay_url}:   {event.as_json()}")


class NotificationHandler(HandleNotification, Generic[T_BaseDM]):
    def __init__(
        self,
        my_keys: Keys,
        get_currently_allowed: Callable[[], set[str]],
        processed_dms: deque[T_BaseDM],
        signal_dm: SignalProtocol[[T_BaseDM]],
        from_serialized: Callable[[str], T_BaseDM],
    ) -> None:
        super().__init__()
        self.signal_tracker = SignalTracker()
        self.processed_dms: deque[T_BaseDM] = processed_dms
        self.untrusted_events: deque[Event] = deque(maxlen=10000)
        self.get_currently_allowed = get_currently_allowed
        self.my_keys = my_keys
        self.signal_dm = signal_dm
        self.from_serialized = from_serialized
        self.signer = NostrSigner.keys(self.my_keys)
        self.signal_tracker.connect(signal_dm, self.on_signal_dm)

    def is_allowed_message(self, recipient_public_key: PublicKey, author: PublicKey) -> bool:
        logger.debug(f"{recipient_public_key.to_bech32()=}   ")
        if not recipient_public_key:
            logger.debug("recipient_public_key not set")
            return False
        if not author:
            logger.debug("author public_key not set")
            return False

        if recipient_public_key.to_bech32() != self.my_keys.public_key().to_bech32():
            logger.debug(f"dm is not for me, {recipient_public_key.to_bech32()=}")
            return False

        if author.to_bech32() not in self.get_currently_allowed():
            logger.debug(f"author {author.to_bech32()=} is not in {self.get_currently_allowed()=}")
            return False

        logger.debug(f"valid dm: {recipient_public_key.to_bech32()=}, {author.to_bech32()=}")
        return True

    async def handle(self, relay_url: "str", subscription_id: "str", event: "Event"):  # type: ignore
        logger.debug(
            f"Received new {event.kind().as_std()} event from {relay_url}:   {event.id().to_bech32()=}"
        )
        if event.kind().as_std() == KindStandard.GIFT_WRAP:
            logger.debug("Decrypting NIP59 event")
            try:
                # Extract rumor
                # from_gift_wrap verifies the seal (encryption) was done correctly
                # from_gift_wrap should fail, if it is not
                # encrypted with my public key (so it is guaranteed to be for me)
                unwrapped_gift: UnwrappedGift = await UnwrappedGift.from_gift_wrap(self.signer, event)
                sender = unwrapped_gift.sender()

                recipient_public_key = event.tags().public_keys()[0]
                if not self.is_allowed_message(author=sender, recipient_public_key=recipient_public_key):
                    self.untrusted_events.append(event)
                    return

                logger.debug(f"unwrapped_gift inside {event.id().to_bech32()=} , {sender.to_bech32()=}")
                rumor: UnsignedEvent = unwrapped_gift.rumor()

                # Check timestamp of rumor
                if rumor.kind().as_std() == KindStandard.PRIVATE_DIRECT_MESSAGE:
                    msg = rumor.content()
                    logger.debug(f"Received new msg [sealed]: inside {event.id().to_bech32()=}")
                    self.handle_trusted_dm_for_me(event, sender, msg)
                else:
                    logger.error(
                        f"Do not know how to handle {rumor.kind().as_std()}.  {event.id().to_bech32()=}"
                    )
            except Exception as e:
                logger.debug(f"Error during content NIP59 decryption: {e}")

    def handle_trusted_dm_for_me(self, event: Event, author: PublicKey, base85_encoded_data: str):
        nostr_dm: T_BaseDM = self.from_serialized(base85_encoded_data)
        nostr_dm.event = event
        nostr_dm.author = author

        if self.dm_is_alreay_processed(nostr_dm):
            logger.debug(f"This nostr dm of {event.id().to_bech32()=} is already in the processed_dms")
            return

        self.emit_signal_dm(nostr_dm)

        logger.debug(f"Processed dm of {event.id().to_bech32()=}")

    def emit_signal_dm(self, dm: T_BaseDM):
        # ensure that this is not reprocessed again
        self.add_to_processed_dms(dm)
        self.signal_dm.emit(dm)

    def add_to_processed_dms(self, dm: T_BaseDM):
        if self.dm_is_alreay_processed(dm):
            return
        self.processed_dms.append(dm)

    def on_signal_dm(self, dm: T_BaseDM):
        self.add_to_processed_dms(dm)

    def dm_is_alreay_processed(self, dm: T_BaseDM) -> bool:
        for item in list(self.processed_dms):
            if not isinstance(item, BaseDM):
                continue  # type: ignore
            if item == dm:
                return True
        return False

    async def handle_msg(self, relay_url: "str", msg: "RelayMessage"):  # type: ignore
        return

    async def replay_events(
        self, events: Iterable[Event], relay_url="from_storage", subscription_id="replay"
    ):
        # now handle the dms_from_dump as if they came from a relay
        for event in events:
            await self.handle(relay_url=relay_url, event=event, subscription_id=subscription_id)

    async def replay_untrusted_events(self):
        await self.replay_events([event for event in self.untrusted_events])

    def close(self):
        self.signal_tracker.disconnect_all()
