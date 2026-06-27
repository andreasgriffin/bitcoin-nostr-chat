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
from datetime import datetime

import bdkpython as bdk
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QListWidgetItem

from bitcoin_nostr_chat.group_chat import ChatDM
from bitcoin_nostr_chat.signals_min import SignalsMin
from bitcoin_nostr_chat.ui.chat_gui import ChatGui, FileObject
from bitcoin_nostr_chat.ui.util import svg_tools

logger = logging.getLogger(__name__)


class BitcoinDmChatGui(ChatGui):
    def __init__(self, signals_min: SignalsMin):
        super().__init__(signals_min)
        self.dms: deque[ChatDM] = deque(maxlen=10000)
        self._local_id_to_item: dict[str, QListWidgetItem] = {}
        self._local_id_to_dm: dict[str, ChatDM] = {}

    def clear_local_state(self):
        self._local_id_to_item.clear()
        self._local_id_to_dm.clear()

    def _drop_local_id(self, local_id: str):
        self._local_id_to_item.pop(local_id, None)
        self._local_id_to_dm.pop(local_id, None)

    def add_dm(
        self,
        dm: ChatDM,
        is_me: bool,
        color: QColor,
        alias: str | None,
        local_id: str | None = None,
        status_icon_name: str | None = None,
        status_tooltip: str | None = None,
    ):
        if not dm.author and not is_me:
            return

        text = dm.description
        file_object = FileObject(path=dm.description, data=dm.data) if dm.data else None
        if (not text) and dm.data:
            if isinstance(dm.data.data, bdk.Transaction):
                text = f"Tx: {dm.data.data.compute_txid()}"
            elif isinstance(dm.data.data, bdk.Psbt):
                text = f"PSBT: {dm.data.data.extract_tx().compute_txid()}"

        item = self.add(
            is_me=is_me,
            text=text,
            file_object=file_object,
            author_name=self.tr("Me") if is_me else (alias if alias else "Unknown"),
            created_at=dm.created_at if dm.created_at else datetime.now(),
            color=color,
            icon=svg_tools.get_QIcon(status_icon_name) if status_icon_name else None,
        )
        if status_tooltip:
            item.setToolTip(status_tooltip)

        self.dms.append(dm)
        if local_id:
            self._local_id_to_item[local_id] = item
            self._local_id_to_dm[local_id] = dm

        return item

    def update_outgoing_status(self, local_id: str, icon_name: str | None, tooltip: str | None = None):
        item = self._local_id_to_item.get(local_id)
        if not item:
            return
        try:
            item.setIcon(svg_tools.get_QIcon(icon_name) if icon_name else QIcon())
            if tooltip is not None:
                item.setToolTip(tooltip)
        except RuntimeError:
            self._drop_local_id(local_id)

    def replace_local_dm(self, local_id: str, dm: ChatDM):
        old_dm = self._local_id_to_dm.get(local_id)
        if old_dm is None:
            return

        for index, existing_dm in enumerate(self.dms):
            if existing_dm is old_dm:
                self.dms[index] = dm
                break
        self._local_id_to_dm[local_id] = dm
