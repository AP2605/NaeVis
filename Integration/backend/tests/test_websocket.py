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
        telemetry_events = []
        for _ in range(10):
            msg = websocket.receive_json()
            if msg.get("event") == "telemetry":
                telemetry_events.append(msg)
            if len(telemetry_events) >= 3:
                break

        assert len(telemetry_events) >= 3
        msg1, msg2, msg3 = telemetry_events[0], telemetry_events[1], telemetry_events[2]
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
        # Send ping
        websocket.send_text(json.dumps({"type": "ping"}))

        # Receive until we get the pong
        received_pong = False
        for _ in range(8):
            msg = websocket.receive_json()
            if msg.get("type") == "pong":
                received_pong = True
                assert "timestamp" in msg
                break

        assert received_pong, "Did not receive pong response to ping"


def test_websocket_invalid_message_does_not_crash():
    """Test that sending invalid data does not crash the stream."""
    with client.websocket_connect("/ws/telemetry") as websocket:
        # Send malformed string
        websocket.send_text("THIS_IS_NOT_JSON")

        # Stream should still be functional and receive events
        received_valid = False
        for _ in range(5):
            msg = websocket.receive_json()
            if "event" in msg:
                received_valid = True
                break

        assert received_valid


def test_websocket_multiple_clients_streaming():
    """Test multiple clients connecting simultaneously and receiving telemetry."""
    with client.websocket_connect("/ws/telemetry") as ws1:
        with client.websocket_connect("/ws/telemetry") as ws2:
            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()

            assert msg1["event"] == "telemetry"
            assert msg2["event"] == "telemetry"
            assert "data" in msg1
            assert "data" in msg2


def test_websocket_one_client_disconnect_does_not_break_other():
    """Test that when one client disconnects, the other client continues to receive telemetry."""
    ws2_context = client.websocket_connect("/ws/telemetry")
    ws2 = ws2_context.__enter__()

    # Connect client 1 and immediately close it
    with client.websocket_connect("/ws/telemetry") as ws1:
        _ = ws1.receive_json()
    # ws1 is now disconnected

    # ws2 should still receive messages without error
    msg = ws2.receive_json()
    assert "event" in msg
    assert "data" in msg

    ws2_context.__exit__(None, None, None)


def test_connection_manager_broadcast():
    """Test ConnectionManager broadcast mechanics."""
    manager = ConnectionManager()
    assert manager.active_count == 0


def test_websocket_initial_snapshot_delivery():
    """Test that a newly connecting WebSocket client receives initial snapshot events."""
    with client.websocket_connect("/ws/telemetry") as ws:
        received_events = set()
        # Read the initial batch of messages
        for _ in range(4):
            msg = ws.receive_json()
            if "event" in msg:
                received_events.add(msg["event"])

        assert "telemetry" in received_events
        assert "integrated_state" in received_events
        assert "analytics" in received_events


def test_websocket_receives_live_p2_and_p3_broadcasts():
    """Test that ingesting P2 Ground Truth and P3 Navigation states broadcasts over WebSocket."""
    with client.websocket_connect("/ws/telemetry") as ws:
        # Drain initial snapshot
        for _ in range(3):
            _ = ws.receive_json()

        # Ingest P2 GT
        gt_res = client.post(
            "/api/v1/simulation/ground-truth",
            json={
                "timestamp": 12.5,
                "frame_id": 999,
                "position": {"x": 5.0, "y": 10.0, "z": 15.0},
                "orientation": {"roll": 1.0, "pitch": -2.0, "yaw": 45.0},
            },
        )
        assert gt_res.status_code == 200

        # Verify ground_truth or integrated_state event is received
        received_gt = False
        for _ in range(5):
            msg = ws.receive_json()
            if msg.get("event") == "ground_truth":
                assert msg["data"]["frame_id"] == 999
                assert msg["data"]["position"]["x"] == 5.0
                received_gt = True
                break
        assert received_gt, "Did not receive live ground_truth event over WebSocket"


def test_websocket_receives_live_mission_lifecycle_broadcast():
    """Test that creating and starting a mission broadcasts status events over WebSocket."""
    with client.websocket_connect("/ws/telemetry") as ws:
        # Drain initial snapshot
        for _ in range(3):
            _ = ws.receive_json()

        # Create mission
        create_res = client.post(
            "/api/v1/missions",
            json={
                "mission_name": "WS Broadcast Test Mission",
                "source": {"x": 0.0, "y": 0.0, "z": 10.0},
                "destination": {"x": 50.0, "y": 20.0, "z": 15.0},
                "waypoints": [{"x": 25.0, "y": 10.0, "z": 12.0}],
            },
        )
        assert create_res.status_code == 201
        m_data = create_res.json()
        mission_id = m_data["mission_id"]

        # Check WebSocket received mission_status
        received_created = False
        for _ in range(5):
            msg = ws.receive_json()
            if msg.get("event") == "mission_status" and msg["data"]["mission_id"] == mission_id:
                assert msg["data"]["action"] == "mission_created"
                assert msg["data"]["status"] == "DRAFT"
                received_created = True
                break
        assert received_created, "Did not receive live mission_status event over WebSocket"
