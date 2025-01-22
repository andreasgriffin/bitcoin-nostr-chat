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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from bitcoin_nostr_chat.default_relays import get_default_delays, get_preferred_relays
from bitcoin_nostr_chat.utils import filtered_for_init

logger = logging.getLogger(__name__)


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
            logger.debug(f"Update relay list, because stale.")
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
