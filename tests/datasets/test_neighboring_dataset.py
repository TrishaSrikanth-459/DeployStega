from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset
from dataset.interaction_trace import InteractionTrace
from dataset.interaction_event import InteractionEvent

def make_trace(i: int) -> InteractionTrace:
    return InteractionTrace([
        InteractionEvent(i, "action", (f"a{i}",))
    ])

def test_neighboring_dataset_single_replacement():
    base = BenignDataset([make_trace(0), make_trace(1)])
    replacement = make_trace(99)

    D_prime = NeighboringDataset(base, {1: replacement})

    assert len(D_prime) == 2
    assert D_prime.get_trace(0) == base.get_trace(0)
    assert D_prime.get_trace(1) == replacement

def test_neighboring_dataset_invalid_index_raises():
    base = BenignDataset([make_trace(0)])

    try:
        NeighboringDataset(base, {2: make_trace(1)})
        assert False
    except IndexError:
        pass
