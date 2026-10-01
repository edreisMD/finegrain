import json
from copy import deepcopy

import pytest

from gm_nightly.brain import candidates, compile_session, scrub
from gm_nightly.capture import TraceJournal, active_messages, project_row
from gm_nightly.config import Config
from gm_nightly.employee import relay, validate_server_url
from gm_nightly.gbrain import correction_markdown, shared_memory
from gm_nightly.models import canonical
from gm_nightly.onboarding import write_config
from gm_nightly.storage import Store


def append(path, row):
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def page(**overrides):
    return {
        "slug": "gm-nightly/compiled/example",
        "source_id": "default",
        "title": "Release policy",
        "type": "note",
        "compiled_truth": "We always require two reviewers before production deployment.",
        "frontmatter": {"visibility": "brain-wide", "gm_training": True},
        "revision": "r1",
        "raw_data": "RAW_SENTINEL",
        "timeline": "RAW_SENTINEL",
        "source_path": "/private/RAW_SENTINEL",
        **overrides,
    }


class FakeBrain:
    def __init__(self, pages=None):
        self.records = pages or []
        self.writes = []
        self.deletes = []
        self.fail = False

    def pages(self, tag, limit):
        return deepcopy(self.records)

    def put(self, slug, markdown, revision=None, request_id=None):
        self.writes.append((slug, markdown, revision, request_id))
        if self.fail:
            raise RuntimeError("network timeout")
        return {"revision": "r" + str(len(self.writes)), "state": "committed"}

    def delete(self, slug, revision, request_id):
        self.deletes.append((slug, revision, request_id))
        return {"state": "committed"}


def test_partial_append_and_restart_and_rotation(tmp_path):
    path = tmp_path / "session.jsonl"
    row = {
        "type": "user",
        "cwd": str(tmp_path),
        "message": {"role": "user", "content": "We always require review before deployment."},
    }
    path.write_bytes(json.dumps(row).encode()[:20])
    journal = TraceJournal(tmp_path / "journal.db")
    assert journal.read(path, "claude")["events"] == 0
    with path.open("ab") as f:
        f.write(json.dumps(row).encode()[20:] + b"\n")
    assert journal.read(path, "claude")["events"] == 1
    assert journal.read(path, "claude")["events"] == 0
    journal.close()
    journal = TraceJournal(tmp_path / "journal.db")
    assert len(journal.sessions()[0]["messages"]) == 1
    path.write_text("{}\n")
    journal.read(path, "claude")
    assert journal.sessions()[0]["messages"] == []
    journal.close()


@pytest.mark.parametrize(
    "kind,row",
    [
        (
            "codex",
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "channel": "analysis",
                    "content": "SECRET_REASONING",
                },
            },
        ),
        (
            "claude",
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "SECRET_REASONING"},
                        {"type": "tool_use", "input": "SECRET_REASONING"},
                    ],
                },
            },
        ),
        (
            "pi",
            {"type": "message", "message": {"role": "toolResult", "content": "SECRET_REASONING"}},
        ),
    ],
)
def test_hidden_trace_fields_never_projected(kind, row):
    assert "SECRET_REASONING" not in canonical(project_row(row, kind, 0))


def test_pi_branch_and_context_edit():
    rows = [
        project_row(r, "pi", i)
        for i, r in enumerate(
            [
                {
                    "type": "message",
                    "id": "a",
                    "parentId": None,
                    "message": {"role": "user", "content": "Root"},
                },
                {
                    "type": "message",
                    "id": "b",
                    "parentId": "a",
                    "message": {"role": "user", "content": "Abandoned"},
                },
                {
                    "type": "message",
                    "id": "c",
                    "parentId": "a",
                    "message": {"role": "user", "content": "Current"},
                },
                {
                    "type": "context_edit",
                    "id": "d",
                    "parentId": "c",
                    "targetId": "a",
                    "replacement": None,
                },
            ]
        )
    ]
    assert [r["text"] for r in active_messages(rows, "pi")] == ["Current"]


def test_mixed_project_session_cannot_share(tmp_path):
    journal = TraceJournal(tmp_path / "journal.db")
    path = tmp_path / "session.jsonl"
    append(path, {"type": "session_meta", "payload": {"cwd": str(tmp_path)}})
    append(path, {"type": "turn_context", "payload": {"cwd": "/private/elsewhere"}})
    append(
        path,
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": "We always require two reviewers for production changes.",
            },
        },
    )
    journal.read(path, "codex")
    p = compile_session(journal.sessions()[0], Config(shared_projects=[str(tmp_path)]))
    assert p and not p["shared"]
    journal.close()


def test_conservative_compiler_grounds_user_rules_and_scrubs():
    messages = [
        {
            "role": "user",
            "text": "We always require two reviewers before deployment.\nMy password=abcdef123456789\nNever contact alice@example.com for approval.\nCan you use Docker?",
        },
        {"role": "assistant", "text": "Our fictional CEO is Ada Invented."},
    ]
    assert candidates(messages) == ["We always require two reviewers before deployment."]
    assert "rv_" not in scrub("rv_" + "x" * 40)


@pytest.mark.parametrize(
    "change",
    [
        {"type": "conversation"},
        {"deleted_at": "2026-01-01"},
        {"frontmatter": {"visibility": "private", "gm_training": True}},
        {"frontmatter": {"visibility": "brain-wide", "gm_training": "true"}},
        {"compiled_truth": "We use token rv_" + "a" * 30},
        {"compiled_truth": "<!--- gbrain:facts:begin --> private facts"},
    ],
)
def test_only_explicit_compiled_pages_are_trainable(change):
    assert shared_memory(page(**change), "acme") is None


def test_existing_finegrain_approval_is_trainable():
    approved = page(frontmatter={"visibility": "brain-wide", "finegrain_training": True})
    assert shared_memory(approved, "acme") is not None


def test_correction_becomes_approved_gbrain_page_without_bad_answer():
    markdown = correction_markdown(
        "How do we ship a hotfix?",
        "Open a reviewed pull request and get on-call approval.",
    )
    assert 'tags: ["finegrain-share"]' in markdown
    assert "finegrain_training: true" in markdown
    assert "Approved company behavior" in markdown
    assert "Push directly to main" not in markdown


def test_correction_rejects_secrets():
    with pytest.raises(ValueError, match="secret"):
        correction_markdown(
            "Deploy this service",
            "Use api_key=super-secret-value-123456789 during deployment.",
        )


def test_relay_whitelist_idempotency_and_withdrawal(tmp_path):
    config = Config(tenant="acme", employee_id="alice", company_home=str(tmp_path))
    local, company = FakeBrain([page()]), FakeBrain()
    store = Store(tmp_path)
    assert relay(config, local, company, store)["sent"] == 1
    wire = canonical(company.writes)
    assert "RAW_SENTINEL" not in wire
    assert company.writes[0][0].startswith("employees/alice/")
    assert relay(config, local, company, store)["sent"] == 0
    local.records = []
    assert relay(config, local, company, store)["withdrawn"] == 1
    store.close()


def test_retry_uses_exact_upstream_request_id(tmp_path):
    config = Config(tenant="acme", employee_id="alice", company_home=str(tmp_path))
    local, company = FakeBrain([page()]), FakeBrain()
    store = Store(tmp_path)
    company.fail = True
    with pytest.raises(RuntimeError):
        relay(config, local, company, store)
    company.fail = False
    relay(config, local, company, store)
    assert company.writes[0] == company.writes[1]
    store.close()


def test_employee_cycle_uses_native_ingest_and_real_brain_interface(tmp_path):
    from gm_nightly.runtime import employee_cycle

    class Local(FakeBrain):
        ingested = []

        def ingest(self, path, kind):
            self.ingested.append((path, kind))

    trace = tmp_path / "session.jsonl"
    append(
        trace,
        {
            "type": "user",
            "cwd": str(tmp_path),
            "message": {
                "role": "user",
                "content": "We always require two reviewers before production deployment.",
            },
        },
    )
    config = Config(
        tenant="acme",
        state_dir=tmp_path,
        capture_sources=[{"kind": "claude", "path": str(trace)}],
        shared_projects=[str(tmp_path)],
        quiet_seconds=0,
    )
    local = Local()
    store = Store(config.workspace)
    result = employee_cycle(config, store, force=True, brain=local)
    assert result["compiled_sessions"] == 1
    assert len(local.ingested) == 1
    assert "finegrain_training: true" in local.writes[0][1]
    employee_cycle(config, store, force=True, brain=local)
    assert len(local.writes) == 1
    store.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.example",
        "https://user:pass@example.com",
        "https://example.com/private",
        "ftp://example.com",
    ],
)
def test_company_endpoint_validation(url):
    with pytest.raises(ValueError):
        validate_server_url(url)


def test_generated_server_config_round_trip(tmp_path):
    from gm_nightly.config import load_config

    path = tmp_path / "server.toml"
    write_config(
        path,
        {
            "gm": {"tenant": "acme", "role": "server"},
            "generation": {"teacher": "river"},
            "schedule": {"auto_train": True},
            "sources": [{"name": "company", "kind": "gbrain_cli", "source_id": "shared"}],
        },
    )
    config = load_config(path)
    assert config.role == "server" and config.auto_train
    assert path.stat().st_mode & 0o077 == 0
