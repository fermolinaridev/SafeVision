import asyncio
import json
import os
from pathlib import Path
from time import monotonic

import httpx
import pytest
from pydantic import SecretStr
from websockets.asyncio.client import connect


@pytest.mark.integration
def test_video_processing_creates_evidence_and_delivers_live_event():
    password = os.getenv("SAFEVISION_TEST_PASSWORD")
    if not password:
        pytest.skip("Configure SAFEVISION_TEST_PASSWORD para testar a instalação.")
    base = os.getenv("SAFEVISION_TEST_URL", "http://127.0.0.1:7860")
    asyncio.run(check_pipeline(base, SecretStr(password)))


async def check_pipeline(base, password):
    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        assert (await client.get("/events")).status_code == 401
        login = await client.post("/auth/login", json={"password": password.get_secret_value()})
        assert login.status_code == 200
        cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
        async with connect(base.replace("http", "ws", 1) + "/events/live",
                           additional_headers={"Cookie": cookie}) as feed:
            assert json.loads(await feed.recv()) == {"type": "ready"}
            path = Path("frontend/public/examples/teste-ocorrencia.mp4")
            with path.open("rb") as video:
                response = await client.post(
                    "/videos", files={"file": (path.name, video, "video/mp4")},
                )
            assert response.status_code == 202
            job_id = response.json()["id"]
            until = monotonic() + 120
            while monotonic() < until:
                status = (await client.get(f"/videos/{job_id}/status")).json()
                if status["status"] in {"completed", "failed"}:
                    break
                await asyncio.sleep(1)
            assert status["status"] == "completed", status
            assert status["progress"] == 100
            assert status["processed_frames"] >= 20
            async with asyncio.timeout(15):
                while True:
                    message = json.loads(await feed.recv())
                    if message["event"]["video_id"] == job_id:
                        event = message["event"]
                        break
        assert event["equipment"] == "vest"
        assert event["duration"] >= 2
        evidence = await client.get(event["evidence_url"])
        assert evidence.status_code == 200 and evidence.content.startswith(b"\xff\xd8")
        review = await client.patch(f"/events/{event['id']}", json={"status": "reviewed"})
        assert review.json()["status"] == "reviewed"
        filtered = await client.get("/events", params={"camera_id": event["camera_id"], "status": "reviewed"})
        assert event["id"] in {row["id"] for row in filtered.json()["items"]}
        unfiltered = (await client.get("/events", params={"limit": 100})).json()
        assert len([row for row in unfiltered["items"] if row["video_id"] == job_id]) == 1
        summary = (await client.get("/analytics/summary")).json()
        assert summary["total"] >= 1
        assert (await client.delete(event["evidence_url"])).status_code == 204
        assert (await client.get(event["evidence_url"])).status_code == 404
        assert (await client.get(f"/events/{event['id']}")).json()["evidence_url"] is None
