from safevision.rules import Assessment, Detection, Person, ViolationEngine, associate


def box(label, coordinates, confidence=0.9, track_id=None):
    return Detection(label=label, box=coordinates, confidence=confidence, track_id=track_id)


def observation(state="missing", ident=1):
    return Person(
        detection_index=0, track_id=ident, helmet=Assessment(state=state, confidence=0.92),
        vest=Assessment(state="present", confidence=0.9),
    )


def test_equipment_has_one_owner_and_requires_the_correct_body_region():
    detections = [
        box("person", (25, 20, 105, 200)),
        box("person", (85, 20, 165, 200)),
        box("helmet", (102, 21, 121, 39)),
        box("helmet", (55, 136, 67, 154)),
        box("vest", (39, 58, 86, 118)),
    ]
    left, right = associate(detections, 240, 240)
    assert (left.helmet.state, left.vest.state) == ("missing", "present")
    assert (right.helmet.state, right.vest.state) == ("present", "missing")


def test_matching_conflicting_or_ambiguous_detections_is_inconclusive():
    people = [
        box("person", (25, 20, 105, 200)),
        box("person", (55, 20, 135, 200)),
    ]
    both = associate(people + [box("helmet", (74, 24, 86, 40))], 200, 230)
    assert all(person.helmet.state == "unknown" for person in both)
    one = associate(people[:1] + [box("helmet", (54, 24, 69, 40)), box("no_helmet", (54, 24, 69, 40))], 200, 230)
    assert one[0].helmet.state == "unknown"


def test_clipped_regions_are_inconclusive_without_direct_detection():
    [person] = associate([box("person", (20, 0, 95, 180))], 250, 230)
    assert person.helmet.state == "unknown"


def test_temporal_threshold_prevents_alerts_for_single_misses():
    engine = ViolationEngine(minimum=2, gap=0.7, recovery=1)
    for index in range(9):
        assert not engine.update([observation("missing" if index % 2 == 0 else "present")], index / 4)
    assert not engine.update([observation()], 7)


def test_occlusion_pauses_duration_and_a_stable_recovery_rearms_the_event():
    engine = ViolationEngine(minimum=2, gap=0.8, recovery=1)
    for time in (0, 0.25, 0.5, 0.75, 1):
        assert not engine.update([observation()], time)
    assert not engine.update([], 1.25)
    for time in (1.5, 1.75, 2, 2.25):
        assert not engine.update([observation()], time)
    [event] = engine.update([observation()], 2.5)
    assert (event.started, event.duration, event.equipment) == (0, 2, "helmet")
    engine.update([observation("present")], 2.75)
    [same] = engine.update([observation()], 3)
    assert same.started == event.started
    for time in (3.25, 3.5, 3.75, 4, 4.25):
        assert not engine.update([observation("present")], time)
    for time in (4.5, 5, 5.5, 6):
        assert not engine.update([observation()], time)
    [new] = engine.update([observation()], 6.5)
    assert new.started == 4.5


def test_large_gap_resets_an_unconfirmed_episode():
    engine = ViolationEngine(minimum=2, gap=0.8, recovery=1)
    for time in (0, 0.5, 1, 1.5, 3, 3.5, 4, 4.5):
        assert not engine.update([observation()], time)
    [event] = engine.update([observation()], 5)
    assert event.started == 3
