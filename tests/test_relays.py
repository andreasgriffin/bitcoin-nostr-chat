import logging
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from time import monotonic

import bdkpython as bdk
import pytest
from bitcoin_safe_lib.async_tools.loop_in_thread import LoopInThread
from nostr_sdk import Keys
from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal
from PyQt6.QtTest import QSignalSpy
from pytestqt.qtbot import QtBot
from bitcoin_safe_lib.gui.qt.signal_tracker import SignalProtocol, SignalTools, SignalTracker
from typing import cast

from bitcoin_nostr_chat.default_relays import get_default_delays, get_preferred_relays
from bitcoin_nostr_chat.group_chat import ChatDM, ChatLabel, DmConnection, RelayList

logger = logging.getLogger(__name__)


# @pytest.mark.parametrize("url", get_preferred_relays())
# def test_preferred_relays(url):
#     """Test each relay to ensure WebSocket connection is established."""
#     try:
#         # Timeout for the WebSocket connection
#         ws = websocket.create_connection(url, timeout=10)
#         ws.close()  # Close the connection after successful connection
#     except websocket.WebSocketTimeoutException:
#         pytest.fail(f"Connection timed out for {url}")
#     except websocket.WebSocketException as e:
#         pytest.fail(f"WebSocket connection failed for {url}: {str(e)}")


class DummyClass(QObject):
    signal_dm = cast(SignalProtocol[[ChatDM]], pyqtSignal(ChatDM))


@dataclass
class TestResult:
    relay: str
    roundtrip_time: float
    success: bool


@dataclass
class RelayAttempt:
    relay: str
    recipient: DummyClass
    dm_connection: DmConnection[ChatDM]
    signal_spy: QSignalSpy
    prepare_future: Future[None] | None = None
    sent_at: float | None = None


def send_dms_to_self(
    qtbot: QtBot, relays: list[str], raise_error: bool, max_concurrency: int = 40
) -> list[TestResult]:
    def from_serialized(base85_encoded_data: str):
        return ChatDM.from_serialized(base85_encoded_data, network=network)

    def get_currently_allowed():
        return set([keys.public_key().to_bech32()])

    def create_attempt(relay: str, shared_loop: LoopInThread) -> RelayAttempt:
        recipient = DummyClass()
        dm_connection = DmConnection[ChatDM](
            signal_dm=recipient.signal_dm,
            from_serialized=from_serialized,
            keys=keys,
            get_currently_allowed=get_currently_allowed,
            relay_list=RelayList(relays=[relay], last_updated=datetime.now(), max_age=5000),
            loop_in_thread=shared_loop,
        )
        return RelayAttempt(
            relay=relay,
            recipient=recipient,
            dm_connection=dm_connection,
            signal_spy=QSignalSpy(recipient.signal_dm),  # type: ignore
        )

    def prepare_attempt(attempt: RelayAttempt):
        attempt.prepare_future = attempt.dm_connection.async_thread.loop_in_thread.run_background(
            attempt.dm_connection.async_dm_connection.connect_clients()
        )

    network = bdk.Network.REGTEST

    keys = Keys.generate()
    test_results: list[TestResult] = []
    failed_relays: list[str] = []
    prepare_timeout_seconds = 10.0

    with LoopInThread() as shared_loop:
        for batch_start in range(0, len(relays), max_concurrency):
            relay_batch = relays[batch_start : batch_start + max_concurrency]
            logger.info(
                f"{round(batch_start / len(relays) * 100) if relays else 100}%  "
                + "*" * 50
                + f" batch size={len(relay_batch)}"
            )
            attempts = [create_attempt(relay, shared_loop=shared_loop) for relay in relay_batch]

            try:
                for attempt in attempts:
                    logger.info(f"relay: {attempt.relay}")
                    prepare_attempt(attempt)

                prepare_deadline = monotonic() + prepare_timeout_seconds
                pending_prepare_attempts = list(attempts)
                while pending_prepare_attempts and monotonic() < prepare_deadline:
                    QCoreApplication.processEvents()
                    completed_prepares = [
                        attempt
                        for attempt in pending_prepare_attempts
                        if attempt.prepare_future is not None and attempt.prepare_future.done()
                    ]
                    for attempt in completed_prepares:
                        try:
                            if attempt.prepare_future:
                                attempt.prepare_future.result()
                        except Exception as e:
                            logger.error(f"failed to prepare relay: {attempt.relay}")
                            test_results.append(
                                TestResult(relay=attempt.relay, roundtrip_time=0.0, success=False)
                            )
                            failed_relays.append(attempt.relay)
                            if raise_error:
                                raise Exception(f"not working: {attempt.relay} , original_message {e}") from e
                        finally:
                            pending_prepare_attempts.remove(attempt)

                    if pending_prepare_attempts:
                        qtbot.wait(50)

                for attempt in pending_prepare_attempts:
                    logger.error(f"prepare timeout: {attempt.relay}")
                    if attempt.prepare_future is not None:
                        attempt.prepare_future.cancel()
                    test_results.append(
                        TestResult(
                            relay=attempt.relay,
                            roundtrip_time=prepare_timeout_seconds,
                            success=False,
                        )
                    )
                    failed_relays.append(attempt.relay)

                if pending_prepare_attempts and raise_error:
                    failed_relay_list = ", ".join(attempt.relay for attempt in pending_prepare_attempts)
                    raise Exception(f"prepare timeout: {failed_relay_list}")

                pending_attempts = [attempt for attempt in attempts if attempt.relay not in failed_relays]

                for attempt in pending_attempts:
                    dm = ChatDM(
                        label=ChatLabel.GroupChat,
                        created_at=datetime.now(),
                        description=f"Test: {attempt.relay}",
                    )
                    attempt.sent_at = monotonic()
                    attempt.dm_connection.send(dm, receiver=keys.public_key())

                deadline = monotonic() + 10
                while pending_attempts and monotonic() < deadline:
                    QCoreApplication.processEvents()
                    completed_relays = [
                        attempt for attempt in pending_attempts if len(attempt.signal_spy) > 0
                    ]
                    for attempt in completed_relays:
                        roundtrip_time = monotonic() - attempt.sent_at if attempt.sent_at is not None else 0.0
                        result = TestResult(
                            relay=attempt.relay,
                            roundtrip_time=roundtrip_time,
                            success=True,
                        )
                        logger.info(
                            f"Success: Test: {attempt.relay} roundtrip_time={result.roundtrip_time:.3f}s"
                        )
                        test_results.append(result)
                        pending_attempts.remove(attempt)

                    if pending_attempts:
                        qtbot.wait(50)

                for attempt in pending_attempts:
                    logger.error(f"not working: {attempt.relay}")
                    roundtrip_time = monotonic() - attempt.sent_at if attempt.sent_at is not None else 0.0
                    test_results.append(
                        TestResult(
                            relay=attempt.relay,
                            roundtrip_time=roundtrip_time,
                            success=False,
                        )
                    )
                    failed_relays.append(attempt.relay)

                if pending_attempts and raise_error:
                    failed_relay_list = ", ".join(attempt.relay for attempt in pending_attempts)
                    raise Exception(f"not working: {failed_relay_list}")
            finally:
                for attempt in attempts:
                    QCoreApplication.processEvents()
                    attempt.dm_connection.close()
                QCoreApplication.processEvents()

    test_results.sort(key=lambda result: result.roundtrip_time)
    logger.info("=" * 50)
    logger.info(f"Relay results: {test_results}")
    if failed_relays:
        logger.info(f"Bad relays: {failed_relays}")
    logger.info("=" * 50)
    return test_results


# def test_send_dms_umbrel(
#     qtbot: QtBot,
# ) -> None:
#     send_dms_to_self(qtbot, relays=["ws://umbrel:4848"], raise_error=True)


@pytest.mark.preferred_relays
def test_send_dms_preferred(
    qtbot: QtBot,
) -> None:
    test_results = send_dms_to_self(qtbot, relays=get_preferred_relays(), raise_error=True)
    print(f"Successful relay: {[t.relay for t in test_results if t.success]}")
    test_results


@pytest.mark.testrelays
def test_send_dms(
    qtbot: QtBot,
) -> None:
    test_results = send_dms_to_self(qtbot, relays=get_default_delays(), raise_error=False)
    print(f"Successful relay: {[t.relay for t in test_results if t.success]}")
    print(f"preferred relays: {[t.relay for t in test_results if t.success and t.roundtrip_time < 0.15]}")
    test_results
