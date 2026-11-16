import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from safevision.api import app
from safevision.config import settings
from safevision.db import engine, sessions
from safevision.vision import Analysis, detector


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SAFEVISION_DEMO", "true")
    settings.cache_clear()
    with TestClient(app) as test:
        yield test
    sessions.cache_clear()
    engine.cache_clear()
    settings.cache_clear()


def test_detect_contract_without_loading_the_model(client, monkeypatch):
    def analyze(image, **kwargs):
        assert image.shape == (32, 64, 3)
        return Analysis(width=64, height=32, detections=[], people=[], inference_ms=0.5)

    monkeypatch.setattr(detector, "analyze", analyze)
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32)).save(buffer, format="PNG")
    result = client.post("/detect", files={"file": ("frame.png", buffer.getvalue(), "image/png")})
    assert result.status_code == 200
    assert result.json() == {"width": 64, "height": 32, "detections": [], "people": [], "inference_ms": 0.5}
    assert result.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(("content_type", "content", "status"), [
    ("image/svg+xml", b"<svg></svg>", 415),
    ("image/jpeg", b"falso", 422),
])
def test_detect_rejects_invalid_media(client, content_type, content, status):
    result = client.post("/detect", files={"file": ("frame", content, content_type)})
    assert result.status_code == status
    assert isinstance(result.json()["error"]["message"], str)


def test_detect_rejects_large_requests_and_cross_origin_mutation(client):
    assert client.post("/detect", headers={"content-length": str(9 * 1024 * 1024)}).status_code == 413
    assert client.post("/auth/logout", headers={"origin": "https://other.example"}).status_code == 403


def test_dashboard_summary_matches_filtered_events(client):
    params = {"camera_id": "cam-01", "equipment": "helmet"}
    response = client.get("/analytics/summary", params={**params, "bucket": "week"})
    assert response.status_code == 200
    data = response.json()
    event_page = client.get("/events", params={**params, "limit": 3}).json()
    assert data["total"] == event_page["total"] == sum(i["helmet"] for i in data["timeline"])
    assert data["vest"] == 0
    assert all(i["camera_id"] == "cam-01" and i["equipment"] == "helmet" for i in event_page["items"])
    assert client.get("/events/" + event_page["items"][0]["id"]).status_code == 200
    assert client.get("/events", params={"start": "2025-03-03", "end": "2025-03-02"}).status_code == 422


def test_demo_cannot_create_persistent_events_or_cameras(client):
    assert client.post("/cameras", json={"name": "Teste", "location": "Lugar"}).status_code == 403
    assert client.post("/videos", files={"file": ("clip.mp4", b"content", "video/mp4")}).status_code == 403
    with client.websocket_connect("/events/live") as connection:
        assert connection.receive_json() == {"type": "ready"}
