import logging
from datetime import datetime
from typing import List

import bdkpython as bdk
import pytest
from nostr_sdk import Keys
from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal
from pytestqt.qtbot import QtBot

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
    signal_dm = pyqtSignal(ChatDM)


def send_dms_to_self(qtbot: QtBot, relays: List[str], raise_error: bool):
    network = bdk.Network.REGTEST

    test_instance_recipient = DummyClass()
    from_serialized = lambda base85_encoded_data: ChatDM.from_serialized(base85_encoded_data, network=network)
    keys = Keys.generate()
    get_currently_allowed = lambda: set([keys.public_key().to_bech32()])

    successful_relays = []

    dm_connections: List[DmConnection] = []
    for i, relay in enumerate(relays):
        logger.info(f"{round(i/len(relays)*100)}%  " + f"*" * 50)
        logger.info(f"relay: {relay}")

        dm_connection = DmConnection(
            test_instance_recipient.signal_dm,
            from_serialized=from_serialized,
            keys=keys,
            get_currently_allowed=get_currently_allowed,
            relay_list=RelayList(relays=[relay], last_updated=datetime.now(), max_age=5000),
        )
        dm_connection.subscribe()
        dm_connections.append(dm_connection)
        dm = ChatDM(
            label=ChatLabel.GroupChat,
            created_at=datetime.now(),
            description=f"Test: {relay}",
        )

        def add_to_chat(dm: ChatDM):
            logger.info(f"Success: {dm.description}")
            successful_relays.append(relay)

        test_instance_recipient.signal_dm.connect(add_to_chat)

        try:
            with qtbot.waitSignal(test_instance_recipient.signal_dm, timeout=10000):
                dm_connection.send(dm, receiver=keys.public_key())
        except Exception as e:
            logger.error(f"not working: {relay}")
            if raise_error:
                raise Exception(f"not working: {relay} , original_message {e}")
        finally:

            QCoreApplication.processEvents()  # Allow Qt to process events
            # sender.stop()
            dm_connection.stop()
            test_instance_recipient.signal_dm.disconnect(add_to_chat)
            QCoreApplication.processEvents()  # Allow Qt to process events

    logger.info(f"=" * 50)
    logger.info(f"Good relays: {successful_relays}")
    logger.info(f"=" * 50)


# def test_send_dms_umbrel(
#     qtbot: QtBot,
# ) -> None:
#     send_dms_to_self(qtbot, relays=["ws://umbrel:4848"], raise_error=True)


def test_send_dms_preffered(
    qtbot: QtBot,
) -> None:

    send_dms_to_self(qtbot, relays=get_preferred_relays(), raise_error=True)


@pytest.mark.testrelays
def test_send_dms(
    qtbot: QtBot,
) -> None:

    send_dms_to_self(qtbot, relays=get_default_delays(), raise_error=False)
