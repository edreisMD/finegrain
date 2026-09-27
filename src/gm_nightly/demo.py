from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .models import Memory
from .pipeline import write_jsonl

DEMO_NOTES = [
    (
        "Atlas releases",
        "Release owner: Platform Engineering\nDeployment window: Tuesday 15:00 UTC\nRollback command: atlas rollback --last-good",
    ),
    (
        "Beacon support",
        "Priority-one channel: #beacon-incidents\nEscalation owner: Customer Engineering\nResponse target: 15 minutes",
    ),
    (
        "Cedar onboarding",
        "Starter repository: cedar-starter\nBuddy team: Developer Experience\nFirst milestone: Ship a documentation change",
    ),
    (
        "Delta analytics",
        "Warehouse: Snowflake\nMetric owner: Data Platform\nReporting timezone: UTC",
    ),
    (
        "Ember design",
        "Primary font: Inter\nDesign review day: Thursday\nComponent library: ember-ui",
    ),
    (
        "Fjord security",
        "Review channel: #security-review\nCredential store: Company Vault\nAccess review cadence: Every 30 days",
    ),
    (
        "Grove engineering",
        "Branch convention: feature/ticket-id\nMerge strategy: Squash merge\nTest command: make test",
    ),
    (
        "Harbor operations",
        "Incident commander: On-call engineer\nStatus page: status.harbor.example\nPostmortem deadline: Three business days",
    ),
]


def create_demo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    config = root / "gm-nightly.toml"
    memories = root / "memories.jsonl"
    if config.exists() or memories.exists():
        raise ValueError(
            "Demo output already exists; choose a new directory or use compile on its config"
        )
    write_jsonl(
        memories,
        [
            asdict(
                Memory(
                    id=f"note-{i}",
                    tenant="demo-company",
                    employee=f"employee-{i % 3}",
                    source="synthetic",
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
    config.write_text("""[gm]
tenant = "demo-company"
state_dir = "state"

[generation]
teacher = "demo"

[schedule]
cadence = "weekly"
auto_train = false
timezone = "America/Los_Angeles"
hour = 2

[[sources]]
name = "company"
kind = "jsonl"
path = "memories.jsonl"
""")
    return config
