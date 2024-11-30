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

import bdkpython as bdk

from bitcoin_nostr_chat.nostr import BitcoinDM
from bitcoin_nostr_chat.signals_min import SignalsMin
from bitcoin_nostr_chat.ui.chat_gui import ChatGui, FileObject
from bitcoin_nostr_chat.ui.util import short_key

from ..signals_min import SignalsMin

logger = logging.getLogger(__name__)

from collections import deque


class BitcoinDmChatGui(ChatGui):
    def __init__(self, signals_min: SignalsMin):
        super().__init__(signals_min)
        self.dms: deque[BitcoinDM] = deque(maxlen=10000)

    def add_dm(self, dm: BitcoinDM, is_me: bool):
        if not dm.author:
            return

        text = dm.description
        file_object = FileObject(path=dm.description, data=dm.data) if dm.data else None
        if (not text) and dm.data:
            if isinstance(dm.data.data, bdk.Transaction):
                text = f"Tx: {dm.data.data.txid()}"
            elif isinstance(dm.data.data, bdk.PartiallySignedTransaction):
                text = f"PSBT: {dm.data.data.txid()}"

        if is_me:
            self.add_own(
                text=text,
                file_object=file_object,
                created_at=dm.created_at if dm.created_at else datetime.now(),
            )
        else:
            self.add_other(
                text=text,
                file_object=file_object,
                other_name=short_key(dm.author.to_bech32()) if dm.author else "Unknown",
                created_at=dm.created_at if dm.created_at else datetime.now(),
            )

        self.dms.append(dm)
