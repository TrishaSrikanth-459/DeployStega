from dataset.benign_dataset import BenignDataset
from dataset.interaction_trace import InteractionTrace

def test_benign_dataset_basic():
    t1 = InteractionTrace([])
    t2 = InteractionTrace([])

    dataset = BenignDataset([t1, t2])

    assert len(dataset) == 2
    assert dataset[0] is t1
    assert dataset[1] is t2
