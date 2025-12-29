from features.feature_set import FeatureSet

def test_feature_set_basic_access():
    fs = FeatureSet({
        "f1": [1, 2, 3],
        "f2": ["a", "b"],
    })

    assert len(fs) == 2
    assert fs.get("f1") == (1, 2, 3)
    assert "f2" in fs

def test_feature_set_is_immutable():
    fs = FeatureSet({"f": [1]})

    try:
        fs._features["f"] = (2,)
        assert False
    except Exception:
        pass

def test_feature_set_equality_and_hash():
    f1 = FeatureSet({"f": [1, 2]})
    f2 = FeatureSet({"f": [1, 2]})
    f3 = FeatureSet({"f": [3]})

    assert f1 == f2
    assert f1 != f3
    assert hash(f1) == hash(f2)
