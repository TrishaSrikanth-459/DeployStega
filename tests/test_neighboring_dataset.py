from dataset.neighboring_dataset import NeighboringDataset
from dataset.benign_dataset import BenignDataset
from dataset.interaction_trace import InteractionTrace


def test_neighboring_dataset_replacement():
    base = BenignDataset([
        InteractionTrace(("a",)),
        InteractionTrace(("b",)),
        InteractionTrace(("c",)),
    ])

    replacement = InteractionTrace(("X",))

    nd = NeighboringDataset(base, {1: replacement})

    assert len(nd) == 3
    assert nd[0] == base[0]
    assert nd[1] == replacement
    assert nd[2] == base[2]
