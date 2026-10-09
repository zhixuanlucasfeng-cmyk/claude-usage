import json
import os
from pathlib import Path

import pytest

from claude_usage.scanner import scan_file, scan_projects_dir


def _usage_line(**overrides) -> dict:
    """A minimal well-formed usage line; overrides patch top-level keys,
    and the special keys model/usage patch inside `message`."""
    line = {
        "timestamp": "2026-08-12T10:00:00.000Z",
        "cwd": "/tmp/proj",
        "sessionId": "abc123",
        "message": {
            "model": "claude-opus-5",
            "usage": {
                "input_tokens": 1,
                "output_tokens": 1,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    }
    for key, value in overrides.items():
        if key == "model":
            line["message"]["model"] = value
        elif key == "usage":
            line["message"]["usage"].update(value)
        elif key == "message_id":
            line["message"]["id"] = value
        else:
            line[key] = value
    return line


def _write_jsonl(path: Path, lines: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            if isinstance(line, str):
                f.write(line + "\n")
            else:
                f.write(json.dumps(line) + "\n")


def test_scan_file_extracts_valid_usage_records(tmp_path):
    jsonl_path = tmp_path / "session.jsonl"
    _write_jsonl(jsonl_path, [
        {
            "timestamp": "2026-08-12T10:00:00.000Z",
            "cwd": "/Users/alice/terse",
            "sessionId": "abc123",
            "message": {
                "model": "claude-sonnet-5",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 5,
                },
            },
        },
    ])

    records = scan_file(jsonl_path)

    assert len(records) == 1
    r = records[0]
    assert r.cwd == "/Users/alice/terse"
    assert r.session_id == "abc123"
    assert r.model == "claude-sonnet-5"
    assert r.input_tokens == 100
    assert r.output_tokens == 50
    assert r.cache_creation_input_tokens == 10
    assert r.cache_read_input_tokens == 5
    assert r.timestamp.year == 2026


def test_scan_file_skips_lines_without_usage(tmp_path):
    jsonl_path = tmp_path / "session.jsonl"
    _write_jsonl(jsonl_path, [
        {"type": "agent-name", "agentName": "foo", "sessionId": "abc123"},
        {
            "timestamp": "2026-08-12T10:00:00.000Z",
            "cwd": "/tmp/proj",
            "sessionId": "abc123",
            "message": {
                "model": "claude-opus-5",
                "usage": {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        },
    ])

    records = scan_file(jsonl_path)

    assert len(records) == 1


def test_scan_file_skips_malformed_json_lines(tmp_path):
    jsonl_path = tmp_path / "session.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write("{not valid json\n")
        f.write(json.dumps({
            "timestamp": "2026-08-12T10:00:00.000Z",
            "cwd": "/tmp/proj",
            "sessionId": "abc123",
            "message": {
                "model": "claude-opus-5",
                "usage": {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        }) + "\n")

    records = scan_file(jsonl_path)

    assert len(records) == 1


def test_scan_file_skips_blank_lines(tmp_path):
    jsonl_path = tmp_path / "session.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write("\n")
        f.write(json.dumps({
            "timestamp": "2026-08-12T10:00:00.000Z",
            "cwd": "/tmp/proj",
            "sessionId": "abc123",
            "message": {
                "model": "claude-opus-5",
                "usage": {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        }) + "\n")
        f.write("   \n")

    records = scan_file(jsonl_path)

    assert len(records) == 1


def test_scan_projects_dir_scans_all_jsonl_files_recursively(tmp_path):
    project_a = tmp_path / "-Users-alice-terse"
    project_a.mkdir()
    _write_jsonl(project_a / "s1.jsonl", [
        {
            "timestamp": "2026-08-12T10:00:00.000Z",
            "cwd": "/Users/alice/terse",
            "sessionId": "s1",
            "message": {
                "model": "claude-opus-5",
                "usage": {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        },
    ])
    project_b = tmp_path / "-Users-alice-other"
    project_b.mkdir()
    _write_jsonl(project_b / "s2.jsonl", [
        {
            "timestamp": "2026-08-12T11:00:00.000Z",
            "cwd": "/Users/alice/other",
            "sessionId": "s2",
            "message": {
                "model": "claude-sonnet-5",
                "usage": {"input_tokens": 2, "output_tokens": 2, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        },
    ])

    records = scan_projects_dir(tmp_path)

    assert len(records) == 2
    session_ids = {r.session_id for r in records}
    assert session_ids == {"s1", "s2"}


def test_scan_file_handles_naive_timestamp_without_z_suffix(tmp_path):
    jsonl_path = tmp_path / "session.jsonl"
    _write_jsonl(jsonl_path, [
        {
            "timestamp": "2026-08-12T10:00:00",
            "cwd": "/Users/alice/terse",
            "sessionId": "abc123",
            "message": {
                "model": "claude-sonnet-5",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
    ])

    records = scan_file(jsonl_path)

    assert len(records) == 1
    r = records[0]
    assert r.cwd == "/Users/alice/terse"
    assert r.session_id == "abc123"
    assert r.timestamp.tzinfo is not None


# --- Cross-file dedup of resumed/forked sessions -------------------------


def test_scan_projects_dir_dedupes_same_call_across_files(tmp_path):
    """Claude Code copies prior turns into a new file when a session is
    resumed or forked, so the same API call appears in several files."""
    shared = _usage_line(
        cwd="/Users/alice/terse",
        sessionId="resumed",
        message_id="msg_shared",
        requestId="req_shared",
        uuid="uuid-in-file-a",
    )
    duplicate = _usage_line(
        cwd="/Users/alice/terse",
        sessionId="resumed",
        message_id="msg_shared",
        requestId="req_shared",
        # A different per-line uuid: the message id + request id still
        # identify this as the same underlying API call.
        uuid="uuid-in-file-b",
    )

    project_a = tmp_path / "-Users-alice-terse"
    project_a.mkdir()
    project_b = tmp_path / "-Users-alice-other"
    project_b.mkdir()
    _write_jsonl(project_a / "s1.jsonl", [shared])
    _write_jsonl(project_b / "s2.jsonl", [duplicate])

    records = scan_projects_dir(tmp_path)

    assert len(records) == 1

    # scan_file has no cross-file awareness: each file still yields its line.
    assert len(scan_file(project_a / "s1.jsonl")) == 1
    assert len(scan_file(project_b / "s2.jsonl")) == 1


def test_scan_projects_dir_dedupes_on_uuid_when_ids_absent(tmp_path):
    line = _usage_line(uuid="shared-uuid", sessionId="resumed")

    project_a = tmp_path / "proj-a"
    project_a.mkdir()
    project_b = tmp_path / "proj-b"
    project_b.mkdir()
    _write_jsonl(project_a / "s1.jsonl", [line])
    _write_jsonl(project_b / "s2.jsonl", [line])

    records = scan_projects_dir(tmp_path)

    assert len(records) == 1


def test_scan_projects_dir_keeps_distinct_calls(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_jsonl(project / "s1.jsonl", [
        _usage_line(message_id="msg_a", requestId="req_a"),
        _usage_line(message_id="msg_b", requestId="req_b"),
    ])

    assert len(scan_projects_dir(tmp_path)) == 2


def test_scan_projects_dir_never_dedupes_records_without_identity(tmp_path):
    """No message id, no request id, no uuid: identity is unknowable, so the
    records are counted rather than silently collapsed."""
    line = _usage_line()
    project = tmp_path / "proj"
    project.mkdir()
    _write_jsonl(project / "s1.jsonl", [line])
    _write_jsonl(project / "s2.jsonl", [line])

    assert len(scan_projects_dir(tmp_path)) == 2


def test_scan_projects_dir_dedupes_on_max_usage_not_first_seen(tmp_path):
    """A single API call is written as multiple JSONL lines (one per content block)
    sharing the same dedup key. Earlier lines carry stub values (output_tokens: 1)
    while the final line carries real usage. Keep the one with max total usage."""
    project = tmp_path / "proj"
    project.mkdir()

    # Three lines sharing the same message.id + requestId (same dedup key),
    # simulating three content blocks of one assistant turn.
    # First two are stubs (output_tokens: 1), third has real value (output_tokens: 241).
    _write_jsonl(project / "session.jsonl", [
        _usage_line(
            message_id="msg_123",
            requestId="req_456",
            usage={"input_tokens": 50, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        ),
        _usage_line(
            message_id="msg_123",
            requestId="req_456",
            usage={"input_tokens": 50, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        ),
        _usage_line(
            message_id="msg_123",
            requestId="req_456",
            usage={"input_tokens": 50, "output_tokens": 241, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        ),
    ])

    records = scan_projects_dir(tmp_path)

    # Should dedupe to a single record with the real usage.
    assert len(records) == 1
    assert records[0].output_tokens == 241
    assert records[0].input_tokens == 50


# --- Malformed JSON shapes must never crash the scan ---------------------


@pytest.mark.parametrize("bad_line", [
    pytest.param("[1,2,3]", id="top-level-array"),
    pytest.param('"hello"', id="top-level-string"),
    pytest.param("null", id="top-level-null"),
    pytest.param("42", id="top-level-number"),
    pytest.param(json.dumps(_usage_line(timestamp=1234567890)), id="int-timestamp"),
    pytest.param(json.dumps(_usage_line(cwd=["/a"])), id="list-cwd"),
    pytest.param(json.dumps(_usage_line(sessionId={"a": 1})), id="dict-session-id"),
    pytest.param(json.dumps(_usage_line(model={"foo": "bar"})), id="dict-model"),
])
def test_scan_file_skips_malformed_shapes_without_crashing(tmp_path, bad_line):
    jsonl_path = tmp_path / "session.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(bad_line + "\n")
        f.write(json.dumps(_usage_line(sessionId="good")) + "\n")

    records = scan_file(jsonl_path)

    assert len(records) == 1
    assert records[0].session_id == "good"


@pytest.mark.parametrize("bad_value", [
    pytest.param(None, id="null"),
    pytest.param("100", id="string"),
    pytest.param(-5, id="negative"),
    pytest.param(1.5, id="float"),
    pytest.param(True, id="bool"),
])
def test_bad_token_field_degrades_to_zero_without_dropping_record(tmp_path, bad_value):
    jsonl_path = tmp_path / "session.jsonl"
    _write_jsonl(jsonl_path, [
        _usage_line(usage={"input_tokens": bad_value, "output_tokens": 7}),
    ])

    records = scan_file(jsonl_path)

    assert len(records) == 1
    assert records[0].input_tokens == 0
    # The rest of the record survives intact.
    assert records[0].output_tokens == 7
    assert records[0].model == "claude-opus-5"


def test_all_token_fields_are_coerced_independently(tmp_path):
    jsonl_path = tmp_path / "session.jsonl"
    _write_jsonl(jsonl_path, [
        _usage_line(usage={
            "input_tokens": None,
            "output_tokens": "5",
            "cache_creation_input_tokens": -1,
            "cache_read_input_tokens": 900,
        }),
    ])

    records = scan_file(jsonl_path)

    assert len(records) == 1
    r = records[0]
    assert (r.input_tokens, r.output_tokens, r.cache_creation_input_tokens) == (0, 0, 0)
    assert r.cache_read_input_tokens == 900


# --- One bad file must not abort a multi-file scan -----------------------


def test_scan_projects_dir_skips_invalid_utf8_file(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_jsonl(project / "good.jsonl", [_usage_line(sessionId="good", uuid="u1")])
    (project / "bad.jsonl").write_bytes(b"\xff\xfe\x00\x01")

    records = scan_projects_dir(tmp_path)

    assert len(records) == 1
    assert records[0].session_id == "good"


def test_scan_projects_dir_skips_unreadable_file(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_jsonl(project / "good.jsonl", [_usage_line(sessionId="good", uuid="u1")])
    unreadable = project / "locked.jsonl"
    _write_jsonl(unreadable, [_usage_line(sessionId="locked", uuid="u2")])
    unreadable.chmod(0o000)
    if os.access(unreadable, os.R_OK):  # running as root: chmod does not restrict
        pytest.skip("cannot make a file unreadable as this user")

    try:
        records = scan_projects_dir(tmp_path)
    finally:
        unreadable.chmod(0o644)

    assert [r.session_id for r in records] == ["good"]


def test_scan_file_still_raises_on_unreadable_file(tmp_path):
    """The single-file API is explicit about one named file, so a caller who
    points it at a broken file should see the error rather than an empty list."""
    bad = tmp_path / "bad.jsonl"
    bad.write_bytes(b"\xff\xfe\x00\x01")

    with pytest.raises(UnicodeDecodeError):
        scan_file(bad)
