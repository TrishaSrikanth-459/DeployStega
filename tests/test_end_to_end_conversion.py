from scripts.convert_routing_trace import convert_routing_trace_to_dataset


def test_end_to_end_conversion(tmp_path):
    routing_file = tmp_path / "trace.jsonl"
    routing_file.write_text(
        """
{"role":"sender","epoch":0,"artifact_class":"Issue","identifier":[1,2],"url":"u","timestamp":1}
"""
    )

    dataset = convert_routing_trace_to_dataset(routing_file)

    assert len(dataset) == 1

    trace = dataset[0]
    assert len(trace) == 1

    event = trace[0]
    assert event.timestamp == 1
    assert event.artifact_ids == ("Issue", 1, 2)
