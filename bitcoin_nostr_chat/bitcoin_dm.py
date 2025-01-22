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


import enum
import json
import logging
from datetime import datetime
from typing import Dict, Optional

import bdkpython as bdk
from bitcoin_qr_tools.data import Data
from nostr_sdk import Event, PublicKey

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.base_dm import BaseDM

logger = logging.getLogger(__name__)


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
