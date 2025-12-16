from dataset.interaction_event import InteractionEvent
from dataset.interaction_trace import InteractionTrace

def make_event(i: int) -> InteractionEvent:
    return InteractionEvent(
        timestamp=float(i),
        action_type="action",
        artifact_ids=(f"a{i}",),
    )

def test_interaction_trace_basic_behavior():
    events = [make_event(0), make_event(1)]
    trace = InteractionTrace(events)

    assert len(trace) == 2
    assert trace[0] == events[0]
    assert trace[1] == events[1]

def test_interaction_Trace_is_ordered_and_immutable():
    events = [make_event(0), make_event(1)]
    trace = InteractionTrace(events)

    assert tuple(trace) == tuple(events)

def test_interaction_trace_equality_and_hash():
    t1 = InteractionTrace([make_event(0), make_event(1)])
    t2 = InteractionTrace([make_event(0), make_event(1)])
    t3 = InteractionTrace([make_event(1)])

    assert t1 == t2
    assert t1 != t3
    assert hash(t1) == hash(t2)
