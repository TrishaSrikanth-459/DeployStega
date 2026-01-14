from dataset.routing_trace_record import RoutingTraceRecord
from dataset.routing_trace_to_interaction import build_interaction_trace


def test_build_interaction_trace_sorted():
    records = [
        RoutingTraceRecord(
            role="sender",
            epoch=0,
            artifact_class="Issue",
            identifier=(1,),
            url="u1",
            timestamp=200,
        ),
        RoutingTraceRecord(
            role="sender",
            epoch=0,
            artifact_class="Issue",
            identifier=(2,),
            url="u2",
            timestamp=100,
        ),
    ]

    trace = build_interaction_trace(records=records)

    assert len(trace) == 2
    assert trace[0].timestamp == 100
    assert trace[1].timestamp == 200
