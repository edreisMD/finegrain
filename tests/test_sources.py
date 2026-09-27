import io
import json
import tarfile

import pytest

from finegrain.sources import collect, conversation, read_archive


def test_codex_messages_exclude_tools_and_reasoning():
    rows = [
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Who owns Atlas?"}],
            },
        },
        {"type": "response_item", "payload": {"type": "reasoning", "content": "private chain"}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Platform Engineering."}],
            },
        },
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "text": "secret-tool-output"},
        },
    ]
    content = conversation(rows, "codex")
    assert "Who owns Atlas?" in content and "Platform Engineering." in content
    assert "private chain" not in content and "secret-tool-output" not in content


def test_codex_exec_and_prompt_envelope():
    rows = [
        {"type": "finegrain.user_prompt", "text": "Question"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Answer"}},
    ]
    assert conversation(rows, "codex") == "user: Question\n\nassistant: Answer"


def test_claude_only_plain_conversation():
    rows = [
        {"type": "user", "message": {"role": "user", "content": "What is the deploy process?"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "private reasoning"},
                    {"type": "tool_use", "input": "secret input"},
                    {"type": "text", "text": "Get approval, then deploy."},
                ],
            },
        },
        {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "tool_result", "content": "private"}]},
        },
    ]
    assert (
        conversation(rows, "claude")
        == "user: What is the deploy process?\n\nassistant: Get approval, then deploy."
    )


def test_markdown_only_and_no_symlink_escape(tmp_path):
    root = tmp_path / "export"
    root.mkdir()
    (root / "policy.md").write_text("Company policies: Approved reference material")
    (root / "image.png").write_text("binary")
    outside = tmp_path / "secret.md"
    outside.write_text("Do not read")
    (root / "outside.md").symlink_to(outside)
    source = {"name": "gbrain", "kind": "gbrain", "path": str(root)}
    memories = collect(source, "acme")
    assert len(memories) == 1 and memories[0].title == "policy"
    assert memories[0].scope == "private" and not memories[0].training_allowed


def test_partial_jsonl_fails_whole_snapshot(tmp_path):
    source = tmp_path / "sessions.jsonl"
    source.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "approved"}})
        + '\n{"type":'
    )
    with pytest.raises(ValueError, match="line 2"):
        collect({"name": "claude", "kind": "claude", "path": str(source)}, "acme")


def test_gm_corrections_become_company_training_memories(tmp_path):
    source = tmp_path / "corrections.jsonl"
    source.write_text(
        json.dumps(
            {
                "ts": "2026-09-27T15:50:00Z",
                "prompt": "How do we ship a hotfix?",
                "gm_answer": "Push directly to main.",
                "correct_answer": "Open a reviewed pull request and get the on-call approval.",
            }
        )
        + "\n"
    )
    memories = collect(
        {"name": "gm-corrections", "kind": "gm_corrections", "path": str(source)},
        "acme",
    )
    assert len(memories) == 1
    assert memories[0].scope == "company" and memories[0].training_allowed
    assert "Correct company procedure" in memories[0].content
    assert "Push directly to main" in memories[0].content


@pytest.mark.parametrize(
    "row",
    [
        {"ts": "now", "prompt": "", "gm_answer": "wrong", "correct_answer": "right"},
        {"ts": "now", "prompt": "question", "gm_answer": "wrong"},
    ],
)
def test_gm_corrections_fail_closed(row, tmp_path):
    source = tmp_path / "corrections.jsonl"
    source.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="correction"):
        collect({"name": "gm", "kind": "gm_corrections", "path": str(source)}, "acme")


@pytest.mark.parametrize(
    "name,link", [("../escape.md", False), ("/absolute.md", False), ("brain/link.md", True)]
)
def test_unsafe_archives_rejected(name, link):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        entry = tarfile.TarInfo(name)
        if link:
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/secret"
        tar.addfile(entry)
    stream.seek(0)
    with pytest.raises(ValueError, match="Unsafe"):
        read_archive(stream, {"name": "gbrain"}, "acme")


def test_read_documented_gbrain_tar():
    stream = io.BytesIO()
    content = b"Owner: Platform Engineering"
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        entry = tarfile.TarInfo("brain/atlas.md")
        entry.size = len(content)
        tar.addfile(entry, io.BytesIO(content))
    stream.seek(0)
    assert read_archive(stream, {"name": "gbrain"}, "acme")[0].content == content.decode()


def test_ssh_arguments_not_shell_executable():
    with pytest.raises(ValueError, match="user@hostname"):
        collect({"name": "gbrain", "kind": "gbrain_ssh", "host": "-oProxyCommand=evil"}, "acme")
