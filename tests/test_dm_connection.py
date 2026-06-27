from __future__ import annotations

from datetime import datetime
from typing import cast

import bdkpython as bdk
from bitcoin_safe_lib.gui.qt.signal_tracker import SignalProtocol
from nostr_sdk import Keys
from PyQt6.QtCore import QObject, QCoreApplication, pyqtSignal

from bitcoin_nostr_chat.annoucement_dm import AccouncementDM
from bitcoin_nostr_chat.dm_connection import DmConnection


class _SignalEmitter(QObject):
    signal_dm = cast(SignalProtocol[[AccouncementDM]], pyqtSignal(AccouncementDM))


def _ensure_app() -> QCoreApplication:
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def _from_serialized(_: str) -> AccouncementDM:
    return AccouncementDM(public_key_bech32=Keys.generate().public_key().to_bech32(), created_at=datetime.now())


def _allowed_keys(keys: Keys) -> set[str]:
    return {keys.public_key().to_bech32()}


def _cleanup(dm_connection: DmConnection[AccouncementDM]) -> None:
    dm_connection.async_dm_connection.close()
    dm_connection.async_thread.stop()
    if dm_connection.async_thread.loop_in_thread is not dm_connection.async_dm_connection.loop_in_thread:
        dm_connection.async_dm_connection.loop_in_thread.stop()


def test_from_dump_reuses_the_same_loop_for_dm_connection_and_async_client() -> None:
    _ensure_app()
    emitter = _SignalEmitter()
    keys = Keys.generate()

    original = DmConnection(
        signal_dm=emitter.signal_dm,
        from_serialized=_from_serialized,
        keys=keys,
        get_currently_allowed=lambda: _allowed_keys(keys),
        loop_in_thread=None,
    )

    restored = DmConnection.from_dump(
        d=original.dump(),
        signal_dm=emitter.signal_dm,
        from_serialized=_from_serialized,
        get_currently_allowed=lambda: _allowed_keys(keys),
        network=bdk.Network.REGTEST,
        loop_in_thread=None,
    )

    try:
        assert restored.async_thread.loop_in_thread is restored.async_dm_connection.loop_in_thread
    finally:
        _cleanup(original)
        _cleanup(restored)
