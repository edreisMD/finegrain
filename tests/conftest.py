from dataclasses import asdict

import pytest

from finegrain.config import Config
from finegrain.demo import DEMO_NOTES
from finegrain.models import Memory
from finegrain.pipeline import write_jsonl
from finegrain.storage import Store


@pytest.fixture
def memory():
    return Memory(
        id="m1",
        tenant="acme",
        employee="alice",
        source="gbrain",
        title="Atlas",
        content="Release owner: Platform Engineering\nDeployment window: Tuesday 15:00 UTC",
        group="atlas",
        scope="company",
        training_allowed=True,
    )


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "memories.jsonl"
    write_jsonl(
        path,
        [
            asdict(
                Memory(
                    id=f"m{i}",
                    tenant="acme",
                    employee="alice",
                    source="gbrain",
                    title=title,
                    content=content,
                    group=f"project-{i}",
                    scope="company",
                    training_allowed=True,
                )
            )
            for i, (title, content) in enumerate(DEMO_NOTES)
        ],
    )
    return Config(
        tenant="acme",
        state_dir=tmp_path / "state",
        sources=[{"name": "approved", "kind": "jsonl", "path": str(path)}],
    ).validate()


@pytest.fixture
def store(config):
    result = Store(config.workspace)
    yield result
    result.close()
