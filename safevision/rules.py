from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel


Equipment = Literal["helmet", "vest"]
State = Literal["present", "missing", "unknown"]
Box = tuple[float, float, float, float]
EQUIPMENT: tuple[Equipment, ...] = ("helmet", "vest")


class Detection(BaseModel):
    label: str
    confidence: float
    box: Box
    track_id: int | None = None


class Assessment(BaseModel):
    state: State
    confidence: float | None = None


class Person(BaseModel):
    detection_index: int
    track_id: int | None
    helmet: Assessment
    vest: Assessment


def overlap_ratio(item: Box, zone: Box) -> float:
    x1, y1, x2, y2 = item
    a, b, c, d = zone
    intersection = max(0, min(x2, c) - max(x1, a)) * max(0, min(y2, d) - max(y1, b))
    return intersection / max(1, (x2 - x1) * (y2 - y1))


def associate(detections: list[Detection], width: int, height: int) -> list[Person]:
    people = [(index, det) for index, det in enumerate(detections) if det.label == "person"]
    states: dict[int, dict[str, Assessment]] = {index: {} for index, _ in people}

    for equipment, start, end in (("helmet", 0, 0.32), ("vest", 0.17, 0.72)):
        zones = {}
        visible = {}
        for index, person in people:
            x1, y1, x2, y2 = person.box
            body_width, body_height = x2 - x1, y2 - y1
            top, bottom = y1 + start * body_height, y1 + end * body_height
            zones[index] = (x1 - body_width * 0.06, top - 0.04 * body_height, x2 + body_width * 0.06, bottom)
            visible[index] = (
                2 < x1 < x2 < width - 2 and 2 < top < bottom < height - 2
                and body_width >= 22 and body_height >= 45
                and (equipment != "vest" or y2 < height - 2)
            )

        matches: dict[tuple[int, str], float] = {}
        ambiguous = set()
        for item in detections:
            if item.label not in (equipment, f"no_{equipment}"):
                continue
            x1, _, x2, _ = item.box
            center = (x1 + x2) / 2
            scores = []
            for index, zone in zones.items():
                coverage = overlap_ratio(item.box, zone)
                if coverage >= 0.6:
                    midpoint = (zone[0] + zone[2]) / 2
                    distance = abs(center - midpoint) / max(1, zone[2] - zone[0])
                    scores.append((coverage - 0.55 * distance, index))
            scores.sort(reverse=True)
            if scores:
                score, owner = scores[0]
                if len(scores) > 1 and score - scores[1][0] < 0.07:
                    ambiguous.update(index for candidate, index in scores if score - candidate < 0.07)
                    continue
                key = (owner, item.label)
                matches[key] = max(matches.get(key, 0), item.confidence)

        for index, person in people:
            positive = matches.get((index, equipment))
            negative = matches.get((index, f"no_{equipment}"))
            if positive and negative:
                assessment = Assessment(state="unknown")
            elif positive:
                assessment = Assessment(state="present", confidence=positive)
            elif negative:
                assessment = Assessment(state="missing", confidence=min(negative, person.confidence))
            elif visible[index] and index not in ambiguous:
                assessment = Assessment(state="missing", confidence=person.confidence)
            else:
                assessment = Assessment(state="unknown")
            states[index][equipment] = assessment

    return [
        Person(detection_index=index, track_id=person.track_id, **states[index])
        for index, person in people
    ]


@dataclass
class Episode:
    started: float | None = None
    last_missing: float = 0
    present_since: float | None = None
    active: bool = False
    last_seen: float = 0
    observed: float = 0
    was_missing: bool = False


@dataclass(frozen=True)
class Violation:
    track_id: int
    equipment: Equipment
    started: float
    duration: float
    confidence: float


@dataclass
class ViolationEngine:
    minimum: float
    gap: float
    recovery: float
    forget_after: float = 15
    episodes: dict[tuple[int, Equipment], Episode] = field(default_factory=dict)

    def update(self, people: list[Person], now: float) -> list[Violation]:
        reports = []
        sampled = set()
        for person in people:
            if person.track_id is None:
                continue
            for equipment in EQUIPMENT:
                key = (person.track_id, equipment)
                sampled.add(key)
                episode = self.episodes.setdefault(key, Episode())
                assessment = getattr(person, equipment)
                episode.last_seen = now
                if assessment.state == "missing":
                    episode.present_since = None
                    if (episode.started is None or now - episode.last_missing > self.gap + 1e-6) and not episode.active:
                        episode.started = now
                        episode.observed = 0
                    elif episode.was_missing and now - episode.last_missing <= self.gap + 1e-6:
                        episode.observed += now - episode.last_missing
                    episode.last_missing = now
                    episode.was_missing = True
                    if episode.active or episode.observed + 1e-6 >= self.minimum:
                        episode.active = True
                        reports.append(Violation(
                            person.track_id, equipment, episode.started,
                            episode.observed, assessment.confidence or 0,
                        ))
                else:
                    episode.was_missing = False
                    if assessment.state == "present":
                        if episode.present_since is None:
                            episode.present_since = now
                        if not episode.active or now - episode.present_since + 1e-6 >= self.recovery:
                            episode.started = None
                            episode.active = False
                    else:
                        episode.present_since = None

        for key, episode in list(self.episodes.items()):
            if key not in sampled:
                episode.was_missing = False
                episode.present_since = None
            if now - episode.last_seen > self.forget_after:
                del self.episodes[key]
        return reports
