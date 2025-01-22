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


import asyncio
import logging
import threading
from typing import Awaitable, TypeVar

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Represents the type of the result returned by the coroutine


class AsyncThread(QThread):
    """A QThread running an asyncio event loop and processing tasks sequentially."""

    result_ready = pyqtSignal(object, object, object)  #  result, coro_func, on_done

    def __init__(self, parent=None):
        super().__init__(parent)
        # Create a new event loop for this thread (do not set globally yet).
        self.loop = asyncio.new_event_loop()
        self.loop_started = threading.Event()
        # We will create the queue *inside* run() after setting the event loop.
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.start()

    def run(self):
        """Entry point for the QThread; set and run the asyncio event loop."""
        # Bind this event loop to the current thread.
        asyncio.set_event_loop(self.loop)
        # Now it's safe to create the asyncio queue in this thread's loop context.

        # Signal that the event loop is ready.
        self.loop_started.set()

        # Schedule our task processor in the event loop.
        asyncio.ensure_future(self._process_tasks(), loop=self.loop)

        # Run the event loop forever (until we explicitly stop it).
        try:
            self.loop.run_forever()
        finally:
            self._cleanup_loop()

    async def _process_tasks(self):
        """Continuously process tasks from the queue in chronological order."""
        while True:
            await asyncio.sleep(0.01)
            logger.debug(f"{self.__class__.__name__}: Waiting for task...")
            coro_func, on_done = await self.task_queue.get()
            logger.debug(f"Task received: {coro_func}")
            try:
                result = await coro_func
                logger.debug(f"Task done: {coro_func}")
                self.result_ready.emit(result, coro_func, on_done)
            except Exception as e:
                logger.debug(f"Task failed: {e}")
                self.result_ready.emit(e, coro_func, on_done)
            self.task_queue.task_done()

    def _cleanup_loop(self):
        """Cancel pending tasks and close the loop."""
        # Cancel all running tasks
        tasks = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
        for task in tasks:
            task.cancel()
        self.loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        self.loop.close()

    def stop(self):
        """Stop the event loop (if needed)."""
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

    def queue_coroutine(self, coro_func: Awaitable, on_done=None):
        """
        Thread-safe scheduling of a coroutine function + arguments.
        Adds the (function, args, kwargs) tuple into the queue
        within the event loop's thread.
        """
        # Ensure the event loop is running before posting tasks.
        if not self.loop_started.is_set():
            logger.debug("Event loop not ready yet.")
            self.loop_started.wait()  # Block until the event loop is ready

        def put_item():
            logger.debug(f"Add to queue {coro_func}")
            self.task_queue.put_nowait((coro_func, on_done))

        # Schedule the queue put in a thread-safe manner.
        self.loop.call_soon_threadsafe(put_item)

    def run_coroutine_parallel(self, coro_func: Awaitable, callback=None):
        """
        Schedules a coroutine to run immediately (in parallel to other tasks),
        bypassing the queue. This means it does NOT wait for previously queued
        tasks to finish.

        :param coro_func: The coroutine object to execute.
        :param callback: An optional callback to call with the result.
        """
        if not self.loop_started.is_set():
            logging.debug("Event loop not ready yet.")
            self.loop_started.wait()  # Block until the event loop is ready

        def schedule():
            async def runner():
                try:
                    # Await the coroutine object
                    result = await coro_func
                    # Emit the result via signal
                    self.result_ready.emit(result, coro_func, callback)
                except Exception as e:
                    # Emit the exception via signal
                    self.result_ready.emit(e, coro_func, callback)

            # Ensure the coroutine is wrapped in a task
            asyncio.ensure_future(runner(), loop=self.loop)

        # Thread-safe scheduling
        self.loop.call_soon_threadsafe(schedule)

    def run_coroutine_blocking(self, coro: Awaitable[T]) -> T:
        """
        Run a coroutine *synchronously* in a fresh event loop.
        This blocks the caller until the coroutine completes,
        then returns the coroutine's result or raises its exception.

        :param coro: The coroutine object to execute.
        :return: The result of the coroutine.
        """

        # Use run_coroutine_threadsafe to submit the coroutine to the running loop
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)

        # Wait for the coroutine to complete and return its result
        return future.result()  # Blocks until the coroutine completes or raises an exception
