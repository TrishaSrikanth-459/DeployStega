from features.behaviourial.session import SessionFeatureExtractor
from features.behaviourial.timing import TimingFeatureExtractor
from features.behaviourial.transition import TransitionFeatureExtractor
from features.pipeline import FeatureExtractionPipeline

from dataset.benign_dataset import BenignDataset
from dataset.interaction_trace import InteractionTrace
from dataset.interaction_event import InteractionEvent


def _make_simple_dataset() -> BenignDataset:
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
    dataset = _make_simple_dataset()

    pipeline = FeatureExtractionPipeline([
        SessionFeatureExtractor(),
        TimingFeatureExtractor(),
        TransitionFeatureExtractor(),
    ])

    feature_set = pipeline.run(dataset)

    # ---- OUTPUT ----
    print("\n[INFO] Feature extraction completed")
    print("[INFO] Extracted feature keys:")
    for k in feature_set:
        print(f"  - {k}: {feature_set[k]}")

    # ---- ASSERTIONS ----
    assert "fsession_length" in feature_set
    assert "ft_intra_user_timing" in feature_set
    assert "faccess_transition_matrix" in feature_set

    assert isinstance(feature_set["fsession_length"], tuple)
    assert isinstance(feature_set["ft_intra_user_timing"], tuple)
    assert isinstance(feature_set["faccess_transition_matrix"], tuple)

    print("\n[PASS] Behavioral feature pipeline test passed")


# ✅ ENTRYPOINT FOR DIRECT EXECUTION
if __name__ == "__main__":
    test_behavioral_feature_pipeline_runs()
