"""Tests for Mock Producers data generation and schemas."""

from app.schemas.p1 import P1VisionResult
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import NavigationStatePacket
from mocks.mock_camera import MockCameraProducer
from mocks.mock_p1 import MockP1Producer
from mocks.mock_p2 import MockP2Producer
from mocks.mock_p3 import MockP3Producer


def test_mock_p1_producer_packet_validity():
    """Verify MockP1Producer generates schema-compliant P1VisionResult packets."""
    producer = MockP1Producer(fps=5.0)
    packet_dict = producer.generate_packet()
    packet = P1VisionResult.model_validate(packet_dict)
    assert packet.frame_id == 1
    assert packet.timestamp >= 0.0
    assert packet.terrain.terrain_type in producer.terrain_types
    assert isinstance(packet.landmarks, list)
    assert packet.segmentation is not None


def test_mock_p2_producer_packet_validity():
    """Verify MockP2Producer generates schema-compliant SimulationGroundTruthPacket."""
    producer = MockP2Producer(fps=20.0)
    packet_dict = producer.generate_packet()
    packet = SimulationGroundTruthPacket.model_validate(packet_dict)
    assert packet.frame_id == 1
    assert packet.position.z > 0
    assert packet.lidar is not None
    assert packet.camera is not None


def test_mock_p3_producer_packet_validity():
    """Verify MockP3Producer generates schema-compliant NavigationStatePacket."""
    producer = MockP3Producer(fps=20.0)
    packet_dict = producer.generate_packet()
    packet = NavigationStatePacket.model_validate(packet_dict)
    assert packet.frame_id == 1
    assert 0.0 <= packet.confidence <= 1.0
    assert packet.tracking_state == "TRACKING_GOOD"
    assert packet.velocity is not None


def test_mock_camera_producer_frame_generation():
    """Verify MockCameraProducer generates valid JPEG byte frames."""
    producer = MockCameraProducer(fps=15.0, width=320, height=240)
    frame_bytes = producer.generate_frame_bytes()
    assert isinstance(frame_bytes, bytes)
    assert len(frame_bytes) > 500  # JPEG header + content
    # Check JPEG SOI (Start of Image) marker: \xff\xd8
    assert frame_bytes[:2] == b"\xff\xd8"
