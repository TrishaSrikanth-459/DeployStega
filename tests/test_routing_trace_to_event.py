from dataset.routing_trace_record import RoutingTraceRecord
from dataset.routing_trace_to_interaction import routing_record_to_event


def test_routing_record_to_interaction_event():
    record = RoutingTraceRecord(
        role="sender",
        epoch=0,
        artifact_class="Issue",
        identifier=(123, 42),
        url="https://github.com/acme/repo/issues/42",
        timestamp=1000,
    )

    event = routing_record_to_event(record)

    assert event.timestamp == 1000
    assert event.action_type == "route_access"
    assert event.artifact_ids == ("Issue", 123, 42)

    # Metadata is structured, not empty
    assert ("role", "sender") in event.metadata
    assert ("epoch", 0) in event.metadata
