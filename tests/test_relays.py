import inspect
import logging
from datetime import datetime
from typing import List

import bdkpython as bdk
import pytest
import websocket
from nostr_sdk import Keys
from PyQt6.QtCore import QObject, pyqtSignal
from pytestqt.qtbot import QtBot

from bitcoin_nostr_chat.default_relays import get_default_delays, get_preferred_relays
from bitcoin_nostr_chat.nostr import (
    BaseDM,
    BitcoinDM,
    ChatLabel,
    DmConnection,
    RelayList,
)

logger = logging.getLogger(__name__)


@pytest.mark.parametrize("url", get_preferred_relays())
def test_preferred_relays(url):
    """Test each relay to ensure WebSocket connection is established."""
    try:
        # Timeout for the WebSocket connection
        ws = websocket.create_connection(url, timeout=10)
        ws.close()  # Close the connection after successful connection
    except websocket.WebSocketTimeoutException:
        pytest.fail(f"Connection timed out for {url}")
    except websocket.WebSocketException as e:
        pytest.fail(f"WebSocket connection failed for {url}: {str(e)}")


class TestClass(QObject):
    signal_dm = pyqtSignal(BaseDM)


@pytest.mark.testrelays
def test_send_dms(
    qtbot: QtBot,
) -> None:
    frame = inspect.currentframe()
    network = bdk.Network.REGTEST
    assert frame

    test_instance = TestClass()
    from_serialized = lambda base64_encoded_data: BaseDM.from_serialized(base64_encoded_data, network=network)
    keys = Keys.generate()
    get_currently_allowed = lambda: set([keys.public_key().to_bech32()])

    successful_relays = []

    dm_connections: List[DmConnection] = []
    for relay in get_default_delays():
        logger.info(f"*" * 50)
        logger.info(f"relay: {relay}")

        dm_connection = DmConnection(
            test_instance.signal_dm,
            from_serialized=from_serialized,
            keys=keys,
            get_currently_allowed=get_currently_allowed,
            relay_list=RelayList(relays=[relay], last_updated=datetime.now(), max_age=5000),
        )
        dm_connections.append(dm_connection)
        dm_connection.subscribe()

        dm = BitcoinDM(
            label=ChatLabel.GroupChat,
            created_at=datetime.now(),
            description=f"Test: {relay}",
        )

        def add_to_chat(dm: BitcoinDM):
            logger.info(f"Success: {dm.description}")
            successful_relays.append(relay)

        test_instance.signal_dm.connect(add_to_chat)

        try:
            with qtbot.waitSignal(test_instance.signal_dm, timeout=10000):
                dm_connection.send(dm, receiver=keys.public_key())
        except:
            logger.error(f"not working: {relay}")

        finally:
            dm_connection.disconnect()
            dm_connection.stop()
            test_instance.signal_dm.disconnect(add_to_chat)

    logger.info(f"=" * 50)
    logger.info(f"Good relays: {successful_relays}")
    logger.info(f"=" * 50)
