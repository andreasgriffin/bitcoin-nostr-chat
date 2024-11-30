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

logger = logging.getLogger(__name__)


from bitcoin_qr_tools.data import Data, DataType
from nostr_sdk import PublicKey
from PyQt6.QtCore import QObject, pyqtSignal

from .nostr import BitcoinDM, GroupChat
from .signals_min import SignalsMin

logger = logging.getLogger(__name__)


from nostr_sdk import PublicKey
from PyQt6.QtCore import QObject, pyqtSignal


class LabelConnector(QObject):
    signal_label_bip329_received = pyqtSignal(Data, PublicKey)  # Data, Author

    def __init__(
        self,
        group_chat: GroupChat,
        signals_min: SignalsMin,
        debug=False,
    ) -> None:
        super().__init__()
        self.signals_min = signals_min
        self.group_chat = group_chat
        self.debug = debug

        # connect signals
        self.group_chat.signal_dm.connect(self.on_dm)

    def on_dm(self, dm: BitcoinDM):
        if not dm.author:
            logger.debug(f"Dropping {dm}, because not author, and with that author can be determined.")
            return

        if dm.data and dm.data.data_type == DataType.LabelsBip329:
            # only emit a signal if I didn't send it
            self.signal_label_bip329_received.emit(dm.data, dm.author)
