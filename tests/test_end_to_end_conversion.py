from scripts.convert_routing_trace import convert_routing_trace_to_dataset

def test_end_to_end_conversion(tmp_path):
    routing_file = tmp_path / "trace.jsonl"
    routing_file.write_text("""
{"experiment_id":"x","epoch":0,"role":"sender","artifact_class":"Issue","identifier":[1,2],"url":"u","timestamp":1}
""")

    dataset = convert_routing_trace_to_dataset(routing_file)

    assert len(dataset) == 1
    trace = dataset[0]
    assert len(trace) == 1
