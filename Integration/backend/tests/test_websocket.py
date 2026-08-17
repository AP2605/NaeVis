"""Tests for WebSocket real-time telemetry streaming and connection manager."""

import json
from fastapi.testclient import TestClient
from app.main import app
from app.websocket.manager import ConnectionManager
from app.schemas.websocket import TelemetryEvent, WebSocketEvent

client = TestClient(app)


def test_websocket_telemetry_connection_and_schema():
    """Test connecting to /ws/telemetry and verifying the event envelope schema."""
    with client.websocket_connect("/ws/telemetry") as websocket:
        msg = websocket.receive_json()

        # Validate event envelope
        assert "event" in msg
        assert msg["event"] == "telemetry"
        assert "timestamp" in msg
        assert "data" in msg

        # Validate telemetry payload
        data = msg["data"]
        required_fields = ["x", "y", "z", "velocity", "roll", "pitch", "yaw", "confidence", "timestamp"]
        for field in required_fields:
            assert field in data, f"Field '{field}' missing from telemetry data"

        assert isinstance(data["x"], (int, float))
        assert isinstance(data["y"], (int, float))
        assert isinstance(data["z"], (int, float))
        assert isinstance(data["velocity"], (int, float))
        assert isinstance(data["roll"], (int, float))
        assert isinstance(data["pitch"], (int, float))
        assert isinstance(data["yaw"], (int, float))
        assert 0.0 <= data["confidence"] <= 1.0


def test_websocket_telemetry_streaming_multiple_messages():
    """Test that the WebSocket continuously streams evolving telemetry messages."""
    with client.websocket_connect("/ws/telemetry") as websocket:
        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()
        msg3 = websocket.receive_json()

        assert msg1["event"] == "telemetry"
        assert msg2["event"] == "telemetry"
        assert msg3["event"] == "telemetry"

        # Timestamps or positions should evolve
        t1 = msg1["data"]["timestamp"]
        t2 = msg2["data"]["timestamp"]
        t3 = msg3["data"]["timestamp"]
        assert t1 != t2 or msg1["data"]["x"] != msg2["data"]["x"]
        assert t2 != t3 or msg2["data"]["x"] != msg3["data"]["x"]


def test_websocket_ping_pong():
    """Test client sending a ping message and receiving pong response."""
    with client.websocket_connect("/ws/telemetry") as websocket:
        # Drain initial telemetry packet
        _ = websocket.receive_json()

        # Send ping
        websocket.send_text(json.dumps({"type": "ping"}))

        # Receive until we get the pong or next message
        received_types = []
        for _ in range(5):
            msg = websocket.receive_json()
            if "type" in msg and msg["type"] == "pong":
                received_types.append("pong")
                assert "timestamp" in msg
                break
            elif msg.get("event") == "telemetry":
                received_types.append("telemetry")

        assert "pong" in received_types


def test_websocket_invalid_message_does_not_crash():
    """Test that sending invalid data does not crash the stream."""
    with client.websocket_connect("/ws/telemetry") as websocket:
        _ = websocket.receive_json()

        # Send malformed string
        websocket.send_text("THIS_IS_NOT_JSON")

        # Stream should still be functional
        msg = websocket.receive_json()
        assert msg["event"] == "telemetry" or "type" in msg


def test_websocket_multiple_clients_streaming():
    """Test multiple clients connecting simultaneously and receiving telemetry."""
    with client.websocket_connect("/ws/telemetry") as ws1:
        with client.websocket_connect("/ws/telemetry") as ws2:
            msg_client1 = ws1.receive_json()
            msg_client2 = ws2.receive_json()

            assert msg_client1["event"] == "telemetry"
            assert msg_client2["event"] == "telemetry"
            assert "data" in msg_client1
            assert "data" in msg_client2


def test_websocket_one_client_disconnect_does_not_break_other():
    """Test that when one client disconnects, the other client continues to receive telemetry."""
    ws2_context = client.websocket_connect("/ws/telemetry")
    ws2 = ws2_context.__enter__()

    # Connect client 1 and immediately close it
    with client.websocket_connect("/ws/telemetry") as ws1:
        _ = ws1.receive_json()
    # ws1 is now disconnected

    # ws2 should still receive telemetry without error
    msg = ws2.receive_json()
    assert msg["event"] == "telemetry"
    assert "data" in msg

    ws2_context.__exit__(None, None, None)


def test_connection_manager_broadcast():
    """Test ConnectionManager broadcast mechanics."""
    manager = ConnectionManager()
    assert manager.active_count == 0
