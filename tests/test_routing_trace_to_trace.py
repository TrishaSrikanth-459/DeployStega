from dataset.routing_trace_to_interaction import build_interaction_trace
from dataset.routing_trace_record import RoutingTraceRecord

def test_build_interaction_trace_sorted():
    records = [
        RoutingTraceRecord(..., timestamp=200),
        RoutingTraceRecord(..., timestamp=100),
    ]

    trace = build_interaction_trace(records)

    assert len(trace) == 2
    assert trace[0].timestamp == 100
    assert trace[1].timestamp == 200
