import pytest
from dataclasses import FrozenInstanceError
from dataset.interaction_event import InteractionEvent

def test_interaction_event_fields():
    event = InteractionEvent(
        timestamp=1.0,
        action_type="commit",
        artifact_ids=("repo1", "commit1"),
        metadata=("m1",)
    )
    assert event.timestamp == 1.0
    assert event.action_type == "commit"
    assert event.artifact_ids == ("repo1", "commit1")
    assert event.metadata == ("m1",)

def test_interaction_event_equalty():
    e1 = InteractionEvent(1.0, "commit", ("a",))
    e2 = InteractionEvent(1.0, "commit", ("a",))
    e3 = InteractionEvent(2.0, "commit", ("a",))
    e4 = InteractionEvent(2.0, "commit", ("b",))
    e5 = InteractionEvent(2.0, "pull", ("a",))

    assert e1 == e2
    assert e1 != e3
    assert e3 != e4
    assert e3 != e5
