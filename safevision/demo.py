from collections import Counter
from datetime import datetime, time, timedelta
from random import Random
from uuid import NAMESPACE_URL, uuid5

from .db import utcnow
from .reporting import day_zone
from .schemas import CameraInfo, EventInfo


def cameras():
    return [
        CameraInfo(id="cam-01", name="Obra principal", location="Setor A · Construção", last_seen=utcnow()),
        CameraInfo(id="cam-02", name="Doca de carga", location="Setor B · Logística", last_seen=utcnow()),
        CameraInfo(id="cam-03", name="Pátio externo", location="Setor C · Operações", last_seen=utcnow()),
        CameraInfo(id="cam-04", name="Oficina", location="Setor D · Manutenção"),
    ]


def events():
    now = utcnow().astimezone(day_zone())
    catalog = cameras()
    files = ["estrutura", "doca", "patio", "oficina"]
    daily_counts = [8, 20, 16, 21, 14, 11, 6, 15, 9, 17, 15, 10, 11, 8]
    result = []
    for offset in range(90):
        day = now.date() - timedelta(days=offset)
        rng = Random(day.toordinal())
        for index in range(daily_counts[offset % len(daily_counts)]):
            camera_index = rng.choices(range(4), (41, 28, 19, 12))[0]
            camera = catalog[camera_index]
            equipment = rng.choices(("helmet", "vest"), (63, 37))[0]
            status = rng.choices(("open", "reviewed", "dismissed"), (24, 70, 6))[0]
            clock = time(rng.choices(range(7, 18), (2, 3, 4, 6, 4, 2, 3, 6, 4, 3, 1))[0], rng.randrange(60))
            stamp = datetime.combine(day, clock, now.tzinfo)
            if offset == 0:
                stamp = now - timedelta(minutes=6 + index * 19)
                if stamp.date() != day:
                    continue
                camera_index = (0, 1, 2, 0, 3, 1, 0, 2)[index]
                camera = catalog[camera_index]
                equipment = "vest" if index in (1, 3, 6) else "helmet"
                status = ("open", "reviewed", "reviewed", "open", "dismissed")[index % 5]
            result.append(EventInfo(
                id=str(uuid5(NAMESPACE_URL, f"safevision-demo-{day}-{index}")),
                camera_id=camera.id, camera_name=camera.name, occurred_at=stamp,
                equipment=equipment, track_id=rng.randint(3, 59), confidence=rng.randint(80, 99) / 100,
                duration=round(rng.uniform(2, 14), 1), status=status,
                evidence_url=f"/examples/{files[camera_index]}.jpg", frame_seconds=rng.uniform(3, 45),
            ))
    return sorted(result, key=lambda event: event.occurred_at, reverse=True)


def filtered(criteria):
    start, end = criteria.bounds()
    return [
        e for e in events()
        if start <= e.occurred_at < end
        and (not criteria.camera_id or criteria.camera_id == e.camera_id)
        and (not criteria.equipment or criteria.equipment == e.equipment)
        and (not criteria.status or criteria.status == e.status)
    ]


def groups(criteria):
    counts = Counter(
        (e.occurred_at.date(), e.occurred_at.hour, e.camera_id, e.equipment, e.status)
        for e in filtered(criteria)
    )
    return ((*key, count) for key, count in counts.items())
