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
from datetime import datetime
from typing import Dict, Optional

from nostr_sdk import Event, PublicKey

from bitcoin_nostr_chat import DEFAULT_USE_COMPRESSION
from bitcoin_nostr_chat.base_dm import BaseDM

logger = logging.getLogger(__name__)


class ProtocolDM(BaseDM):
    def __init__(
        self,
        public_key_bech32: str,
        created_at: datetime,
        please_trust_public_key_bech32: str | None = None,
        name: str | None = None,
        event: Optional[Event] = None,
        author: Optional[PublicKey] = None,
        use_compression=DEFAULT_USE_COMPRESSION,
    ) -> None:
        super().__init__(event=event, author=author, created_at=created_at, use_compression=use_compression)
        self.public_key_bech32 = public_key_bech32
        # this is only when I want the recipient to trust me back
        self.please_trust_public_key_bech32 = please_trust_public_key_bech32
        self.name = name

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
