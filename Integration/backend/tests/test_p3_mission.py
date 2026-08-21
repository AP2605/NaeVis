"""Tests for P3 Mission Client and transmission handling."""

import pytest
from app.integrations.p3.mission_client import P3MissionClient
from app.schemas.common import Position3D
from app.schemas.mission import MissionResponse, MissionStatus, WaypointResponse, WaypointStatus


@pytest.mark.anyio
async def test_p3_mission_client_handles_unreachable_endpoint():
    """Test that P3 client returns graceful UNAVAILABLE status when P3 is offline without raising unhandled exceptions."""
    client = P3MissionClient(base_url="http://localhost:59999", timeout=0.5)
    dummy_mission = MissionResponse(
        mission_id="test-mission-uuid-1",
        mission_name="Offline Test",
        source=Position3D(x=0.0, y=0.0, z=10.0),
        waypoints=[
            WaypointResponse(waypoint_index=0, x=10.0, y=10.0, z=12.0, status=WaypointStatus.PENDING)
        ],
        destination=Position3D(x=20.0, y=20.0, z=10.0),
        coordinate_frame="BLENDER_LOCAL",
        status=MissionStatus.DRAFT,
        created_at="2026-08-17T12:00:00Z",
        updated_at="2026-08-17T12:00:00Z",
    )

    result = await client.send_mission(dummy_mission)
    assert result["success"] is False
    assert result["status"] in ("UNAVAILABLE", "TIMEOUT")
