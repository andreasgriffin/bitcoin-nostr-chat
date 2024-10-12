import pytest
import websocket

from bitcoin_nostr_chat.default_relays import get_preferred_relays


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
