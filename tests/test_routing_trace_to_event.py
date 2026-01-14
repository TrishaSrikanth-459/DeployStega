from dataset.routing_trace_record import RoutingTraceRecord
from dataset.routing_trace_to_interaction import routing_record_to_event

def test_routing_record_to_interaction_event():
    record = RoutingTraceRecord(
        experiment_id="test",
        epoch=0,
        role="sender",
        artifact_class="Issue",
        identifier=(123, 42),
        url="https://github.com/acme/repo/issues/42",
        timestamp=1000,
    )

    event = routing_record_to_event(record)

    assert event.timestamp == 1000
    assert event.action_type == "sender:Issue"
    assert event.artifact_ids == (123, 42)
    assert event.metadata == ()
