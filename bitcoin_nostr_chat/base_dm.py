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


import base64
import json
import logging
import zlib
from datetime import datetime, timedelta
from typing import TypeVar

import bdkpython as bdk
import cbor2
from nostr_sdk import Event, PublicKey
from typing_extensions import Self

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.utils import filtered_for_init

logger = logging.getLogger(__name__)


class BaseDM:
    def __init__(
        self,
        created_at: datetime,
        event: Event | None = None,
        author: PublicKey | None = None,
        use_compression=DEFAULT_USE_COMPRESSION,
    ) -> None:
        super().__init__()
        self.event = event
        self.author = author
        self.created_at = created_at
        self.use_compression = use_compression

    @staticmethod
    def delete_none_entries(d: dict) -> dict:
        for key, value in list(d.items()):
            if value is None:
                del d[key]
        return d

    def dump(self) -> dict:
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
            base85_encoded_data = base64.b85encode(compressed_data).decode()
            logger.debug(f"{100 * (1 - len(compressed_data) / (1 + len(cbor_serialized))):.1f}% compression")
            return base85_encoded_data
        else:
            return json.dumps(d)

    @classmethod
    def from_dump(cls, d: dict, network: bdk.Network) -> Self:
        # decode the data from the string and ensure the type is
        event = Event.from_json(d["event"]) if d.get("event") else None
        d["event"] = event
        d["author"] = PublicKey.parse(d["author"]) if d.get("author") else None
        try:
            # in the old format created_at was optional. So i have to catch this.
            d["created_at"] = datetime.fromtimestamp(d["created_at"])
        except Exception:
            d["created_at"] = datetime.now() - timedelta(
                days=30
            )  # assume the legacy format is at least 30 days old

        logger.info(f"decoded_dict  with id={event.id().to_bech32() if event else None}")
        return cls(**filtered_for_init(d, cls))

    @classmethod
    def from_serialized(cls, base85_encoded_data: str, network: bdk.Network):
        if base85_encoded_data.startswith("{"):
            # if it is likely a json string, try this method first
            try:
                logger.debug("from_serialized json")
                decoded_dict = json.loads(base85_encoded_data)
                return cls.from_dump(decoded_dict, network=network)
            except Exception:
                pass

        try:
            # try first the compressed decoding
            logger.debug("from_serialized compressed")
            decoded_data = base64.b85decode(base85_encoded_data)
            decompressed_data = zlib.decompress(decoded_data)
            decoded_dict = cbor2.loads(decompressed_data)
            return cls.from_dump(decoded_dict, network=network)
        except Exception:
            logger.error("from_serialized failed")
            raise

    def __str__(self) -> str:
        return str(self.dump())

    def __eq__(self, other) -> bool:
        if isinstance(other, BaseDM):
            if bool(self.event) != bool(other.event):
                return False
            if self.event and other.event and self.event.as_json() != other.event.as_json():
                return False
            return True
        return False


T_BaseDM = TypeVar("T_BaseDM", bound=BaseDM)
