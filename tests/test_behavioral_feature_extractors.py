from features.behaviourial.session import SessionFeatureExtractor
from features.behaviourial.timing import TimingFeatureExtractor
from features.behaviourial.transition import TransitionFeatureExtractor
from features.pipeline import FeatureExtractionPipeline

from dataset.benign_dataset import BenignDataset
from dataset.interaction_trace import InteractionTrace
from dataset.interaction_event import InteractionEvent


def _make_simple_dataset() -> BenignDataset:
    """
    Build a minimal but valid dataset with timestamps
    sufficient to exercise behavioral extractors.
    """
    trace = InteractionTrace([
        InteractionEvent(
            timestamp=0.0,
            action_type="Issue",
            artifact_ids=(1,),
            metadata=(),
        ),
        InteractionEvent(
            timestamp=10.0,
            action_type="IssueComment",
            artifact_ids=(1,),
            metadata=(),
        ),
        InteractionEvent(
            timestamp=25.0,
            action_type="PullRequest",
            artifact_ids=(2,),
            metadata=(),
        ),
    ])

    return BenignDataset([trace])


def test_behavioral_feature_pipeline_runs():
    """
    Ensures behavioral feature extractors:
    - integrate with FeatureExtractionPipeline
    - accept BenignDataset
    - return FeatureSet entries with correct keys
    """
    dataset = _make_simple_dataset()

    pipeline = FeatureExtractionPipeline([
        SessionFeatureExtractor(),
        TimingFeatureExtractor(),
        TransitionFeatureExtractor(),
    ])

    feature_set = pipeline.run(dataset)

    # Assert feature keys exist
    assert "fsession_length" in feature_set
    assert "ft_intra_user_timing" in feature_set
    assert "faccess_transition_matrix" in feature_set

    # Assert returned values are tuples (pipeline contract)
    assert isinstance(feature_set["fsession_length"], tuple)
    assert isinstance(feature_set["ft_intra_user_timing"], tuple)
    assert isinstance(feature_set["faccess_transition_matrix"], tuple)
