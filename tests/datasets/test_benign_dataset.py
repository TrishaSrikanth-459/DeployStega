from dataset.benign_dataset import BenignDataset
from dataset.interaction_trace import InteractionTrace
from dataset.interaction_event import InteractionEvent

def make_trace(i: int) -> InteractionTrace:
    return InteractionTrace([
        InteractionEvent(i, "action", (f"a{i}",))
    ])

def test_benign_dataset_basic_access():
    traces = [make_trace(0), make_trace(1)]
    dataset = BenignDataset(traces)

    assert len(dataset) == 2
    assert dataset.get_trace(0) == traces[0]
    assert dataset.get_trace(1) == traces[1]

def test_benign_dataset_is_ordered():
    traces = [make_trace(0), make_trace(1)]
    dataset = BenignDataset(traces)
    assert dataset.traces() == tuple(traces)
