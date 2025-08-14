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
from collections.abc import Coroutine
from typing import Any, TypeVar
import threading
from typing import Any, Awaitable, Coroutine, TypeVar

from bitcoin_safe_lib.async_tools.loop_in_thread import LoopInThread, MultipleStrategy
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Represents the type of the result returned by the coroutine


class AsyncThread(QObject):
    """Manage an asyncio event loop on a dedicated Python thread."""

    result_ready = pyqtSignal(object, object, object)  # result, coro_func, on_done

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop = LoopInThread()
        self._queue_key = "async-thread-queue"

    def _emit_result(self, result: object, coro: Coroutine[Any, Any, Any], callback):
        logger.debug("Task finished: %s", coro)
        self.result_ready.emit(result, coro, callback)

    def _emit_error(self, exc_info, coro: Coroutine[Any, Any, Any], callback):
        exc = exc_info[1] if exc_info and len(exc_info) > 1 else Exception("Unknown error")
        logger.debug("Task failed: %s", exc)
        self.result_ready.emit(exc, coro, callback)

    def stop(self):
        """Stop the event loop (if needed) and wait for the thread to finish."""
        self._loop.stop()

    def queue_coroutine(self, coro_func: Coroutine[Any, Any, T], on_done=None):
        """Schedule a coroutine to run sequentially on the worker loop."""

        def on_success(result):
            self._emit_result(result, coro_func, on_done)

        def on_error(exc_info):
            self._emit_error(exc_info, coro_func, on_done)

        logger.debug("Queue coroutine: %s", coro_func)
        self._loop.run_task(
            coro_func,
            on_success=on_success,
            on_error=on_error,
            key=self._queue_key,
            multiple_strategy=MultipleStrategy.QUEUE,
        )

    def run_coroutine_blocking(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run a coroutine synchronously and return its result."""

        logger.debug("Run coroutine blocking: %s", coro)
        return self._loop.run_foreground(coro)
