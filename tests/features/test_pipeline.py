from features.pipeline import FeatureExtractionPipeline
from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.interaction_trace import InteractionTrace
from dataset.interaction_event import InteractionEvent


class DummyExtractor(FeatureExtractor):
    name = "dummy"

    def extract(self, dataset):
        return [len(dataset)]


def make_dataset():
    trace = InteractionTrace([
        InteractionEvent(0.0, "action", ("a",))
    ])
    return BenignDataset([trace])


def test_pipeline_runs_extractors():
    pipeline = FeatureExtractionPipeline([DummyExtractor()])
    dataset = make_dataset()

    features = pipeline.run(dataset)

    assert features.get("dummy") == (1,)
