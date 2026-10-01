import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "train"))
from train_gm import split  # noqa: E402


def test_split_holds_out_a_fixed_fraction_without_overlap():
    rows = [{"id": i} for i in range(100)]
    train, val = split(rows, 0.1, seed=0)
    assert len(val) == 10 and len(train) == 90
    assert {r["id"] for r in train}.isdisjoint(r["id"] for r in val)


def test_split_is_reproducible():
    rows = [{"id": i} for i in range(50)]
    assert split(rows, 0.1, seed=0) == split(rows, 0.1, seed=0)
