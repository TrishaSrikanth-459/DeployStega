from features.behaviourial.session import SessionFeatureExtractor
from features.behaviourial.timing import TimingFeatureExtractor
from features.behaviourial.transition import TransitionFeatureExtractor
from features.behaviourial.revisit import RevisitFeatureExtractor
from features.behaviourial.frequency import FrequencyFeatureExtractor

# Routing / access-topology features
from features.routing.shared_access import SharedAccessOverlapFeatureExtractor
from features.routing.role_asymmetry import RoleAsymmetryFeatureExtractor
from features.routing.shared_access_topology import SharedAccessTopologyFeatureExtractor
from features.routing.identifier_concentration import IdentifierConcentrationFeatureExtractor

from features.pipeline import FeatureExtractionPipeline

from dataset.benign_dataset import BenignDataset
from dataset.interaction_trace import InteractionTrace
from dataset.interaction_event import InteractionEvent


def _make_behaviorally_rich_dataset() -> BenignDataset:
    """
    Construct a dataset that satisfies ALL extractor invariants.

    Includes:
    - repeated artifact access (revisit)
    - multiple artifact classes (frequency)
    - transitions between classes
    - sufficient timing gaps
    - sender/receiver role metadata for routing features
    """

    trace = InteractionTrace([
        InteractionEvent(
            0.0,
            "route_access",
            (1,),
            (("artifact_class", "issue"), ("role", "sender")),
        ),
        InteractionEvent(
            5.0,
            "route_access",
            (1,),
            (("artifact_class", "issue"), ("role", "sender")),
        ),
        InteractionEvent(
            10.0,
            "route_access",
            (1,),
            (("artifact_class", "issue"), ("role", "receiver")),
        ),
        InteractionEvent(
            15.0,
            "route_access",
            (2,),
            (("artifact_class", "pr"), ("role", "sender")),
        ),
        InteractionEvent(
            20.0,
            "route_access",
            (2,),
            (("artifact_class", "pr"), ("role", "receiver")),
        ),
        InteractionEvent(
            25.0,
            "route_access",
            (2,),
            (("artifact_class", "pr"), ("role", "receiver")),
        ),
    ])

    return BenignDataset([trace])


def test_behavioral_and_routing_feature_pipeline_runs_and_emits_features():
    dataset = _make_behaviorally_rich_dataset()

    pipeline = FeatureExtractionPipeline([
        # ---------------- Behavioral ----------------
        SessionFeatureExtractor(),
        TimingFeatureExtractor(),
        TransitionFeatureExtractor(),
        FrequencyFeatureExtractor(),
        RevisitFeatureExtractor(),

        # ---------------- Routing / topology ----------------
        SharedAccessOverlapFeatureExtractor(),
        RoleAsymmetryFeatureExtractor(),
        SharedAccessTopologyFeatureExtractor(),
        IdentifierConcentrationFeatureExtractor(),
    ])

    feature_set = pipeline.run(dataset)

    # -------------------- OUTPUT --------------------
    print("\n[INFO] Feature extraction completed")
    for name, values in feature_set.items():
        print(f"  - {name}: {values}")

    # -------------------- STRUCTURAL ASSERTIONS --------------------
    assert "fsession_length" in feature_set
    assert "ft_intra_user_timing" in feature_set
    assert "faccess_transition_matrix" in feature_set
    assert "f_event_type_frequency" in feature_set
    assert "f_artifact_revisit" in feature_set

    assert "fr_shared_access_overlap" in feature_set
    assert "fr_role_asymmetry" in feature_set
    assert "fr_shared_access_topology" in feature_set
    assert "fr_identifier_concentration" in feature_set

    # -------------------- BEHAVIORAL SEMANTICS --------------------
    fsession_lengths = feature_set.get("fsession_length")
    assert isinstance(fsession_lengths, tuple)
    assert len(fsession_lengths) >= 1
    assert all(x > 0 for x in fsession_lengths)

    ft_deltas = feature_set.get("ft_intra_user_timing")
    assert len(ft_deltas) >= 5
    assert all(x > 0 for x in ft_deltas)

    faccess = feature_set.get("faccess_transition_matrix")[0]
    assert "issue" in faccess
    assert "pr" in faccess["issue"]

    ffreq = feature_set.get("f_event_type_frequency")[0]
    assert abs(sum(ffreq.values()) - 1.0) < 1e-6

    frevisit = feature_set.get("f_artifact_revisit")
    revisit_rates, unique_counts, max_revisits = frevisit
    assert revisit_rates[0] > 0
    assert unique_counts[0] == 2
    assert max_revisits[0] >= 1

    # -------------------- ROUTING SEMANTICS --------------------
    shared = feature_set.get("fr_shared_access_overlap")[0]
    assert shared["shared"] >= 1
    assert shared["jaccard"] > 0

    asym = feature_set.get("fr_role_asymmetry")[0]
    assert asym["sender_total"] > 0
    assert asym["receiver_total"] > 0

    topo = feature_set.get("fr_shared_access_topology")[0]
    assert topo["shared_fraction"] > 0

    conc = feature_set.get("fr_identifier_concentration")[0]
    assert conc["num_unique_artifacts"] == 2
    assert conc["hhi"] > 0

    print("\n[PASS] Behavioral + routing feature pipeline exercised successfully")


if __name__ == "__main__":
    test_behavioral_and_routing_feature_pipeline_runs_and_emits_features()
