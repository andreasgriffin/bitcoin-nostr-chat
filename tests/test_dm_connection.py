import asyncio
from collections.abc import Callable
from typing import Any, cast

from bitcoin_safe_lib.gui.qt.signal_tracker import SignalProtocol
from nostr_sdk import Keys
from PyQt6.QtCore import QObject, pyqtSignal

from bitcoin_nostr_chat.dm_connection import DmConnection


class DummySignals(QObject):
    signal_dm = cast(SignalProtocol[[str]], pyqtSignal(str))


class FakeAsyncThread:
    def __init__(self, events: list[str], running: bool = True) -> None:
        self.events = events
        self.running = running

    def is_running(self) -> bool:
        return self.running

    def run_coroutine_blocking(self, coro):
        return asyncio.run(coro)

    def stop(self) -> None:
        self.events.append("stop")


class FakeAsyncDmConnection:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.client = object()

    async def unsubscribe_all(self) -> None:
        self.events.append("unsubscribe_all")

    async def disconnect_client(self, client: object) -> None:
        assert client is self.client
        self.events.append("disconnect_client")

    def close(self) -> None:
        self.events.append("close")


def _make_connection(events: list[str], running: bool = True) -> DmConnection[str]:
    dummy_signals = DummySignals()
    async_thread = FakeAsyncThread(events=events, running=running)
    async_dm_connection = FakeAsyncDmConnection(events=events)
    return DmConnection[str](
        signal_dm=dummy_signals.signal_dm,
        from_serialized=lambda serialized: serialized,
        keys=Keys.generate(),
        get_currently_allowed=lambda: set(),
        loop_in_thread=None,
        async_thread=async_thread,
        async_dm_connection=async_dm_connection,
    )


def test_close_waits_for_async_cleanup() -> None:
    events: list[str] = []

    connection = _make_connection(events=events)
    connection.close()

    assert events == ["unsubscribe_all", "disconnect_client", "close", "stop"]


def test_close_skips_async_cleanup_when_thread_stopped() -> None:
    events: list[str] = []

    connection = _make_connection(events=events, running=False)
    connection.close()

    assert events == ["close", "stop"]
