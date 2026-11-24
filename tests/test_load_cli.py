import hashlib
import json
from pathlib import Path

import pytest

from attack_graph.cli import main
from attack_graph.release import Release

# A tiny stand-in for the real ATT&CK download. It has a group the bundled
# fixture does not know, so a hit proves the lookup used the loaded data.
BUNDLE = json.dumps({
    "type": "bundle",
    "objects": [
        {"type": "attack-pattern", "id": "attack-pattern--1", "name": "Loaded Technique",
         "description": "d", "external_references": [
             {"source_name": "mitre-attack", "external_id": "T7777"}]},
        {"type": "intrusion-set", "id": "intrusion-set--1", "name": "Loaded Group",
         "aliases": ["Loaded Group", "LG"], "description": "d", "external_references": [
             {"source_name": "mitre-attack", "external_id": "G7777"}]},
        {"type": "relationship", "id": "relationship--1", "relationship_type": "uses",
         "source_ref": "intrusion-set--1", "target_ref": "attack-pattern--1"},
    ],
}).encode()

RELEASE = Release(
    version="0.0-test",
    url="https://example.invalid/bundle.json",
    sha256=hashlib.sha256(BUNDLE).hexdigest(),
)


class FakeFetch:
    def __init__(self, body: bytes = BUNDLE, error: Exception | None = None) -> None:
        self.body, self.error, self.calls = body, error, 0

    def __call__(self, url: str) -> bytes:
        self.calls += 1
        if self.error:
            raise self.error
        return self.body


def run(capsys, *argv: str, fetch=None) -> tuple[int, str, str]:
    code = main(list(argv), fetch=fetch or FakeFetch(), release=RELEASE)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_lookups_use_the_bundled_fixture_before_any_load(capsys):
    code, _, err = run(capsys, "group", "Loaded Group")

    assert code == 1
    assert "No group found" in err


def test_load_then_group_lookup_returns_techniques_from_loaded_data(capsys):
    code, out, _ = run(capsys, "load")
    assert code == 0
    assert "0.0-test" in out

    code, out, _ = run(capsys, "group", "LG")

    assert code == 0
    assert "T7777 Loaded Technique" in out


def test_loaded_data_replaces_the_fixture_for_technique_lookup(capsys):
    run(capsys, "load")

    code, _, err = run(capsys, "technique", "T1566.001")

    assert code == 1
    assert "No technique found" in err


def test_rerunning_load_gives_the_same_graph(capsys):
    run(capsys, "load")
    _, first, _ = run(capsys, "group", "Loaded Group")
    store = next(Path("data").glob("*.nt"))
    first_store = store.read_text()

    code, _, _ = run(capsys, "load")
    _, second, _ = run(capsys, "group", "Loaded Group")

    assert code == 0
    assert second == first
    assert store.read_text() == first_store


def test_rerunning_load_does_not_download_again(capsys):
    fetch = FakeFetch()

    run(capsys, "load", fetch=fetch)
    run(capsys, "load", fetch=fetch)

    assert fetch.calls == 1


def test_explicit_data_file_beats_loaded_data(capsys, tmp_path: Path):
    run(capsys, "load")
    other = tmp_path / "other.json"
    other.write_text(BUNDLE.decode().replace("Loaded Group", "Other Group"))

    code, out, _ = run(capsys, "--data", str(other), "group", "Other Group")

    assert code == 0
    assert "G7777" in out


def test_download_failure_gives_clear_message_and_loads_nothing(capsys):
    code, _, err = run(capsys, "load", fetch=FakeFetch(error=OSError("offline")))

    assert code == 2
    assert "offline" in err
    assert not list(Path("data").glob("*.nt"))


def test_download_with_wrong_checksum_is_rejected(capsys):
    code, _, err = run(capsys, "load", fetch=FakeFetch(body=b'{"objects": []}'))

    assert code == 2
    assert "checksum" in err.lower()
    assert not list(Path("data").glob("*.nt"))
    assert not list(Path("data").glob("*.json"))


def test_failed_reload_keeps_previous_loaded_data(capsys):
    run(capsys, "load")
    for cached in Path("data").glob("*.json"):
        cached.unlink()

    code, _, _ = run(capsys, "load", fetch=FakeFetch(error=OSError("offline")))
    lookup_code, out, _ = run(capsys, "group", "LG")

    assert code == 2
    assert lookup_code == 0
    assert "T7777" in out


def test_corrupt_loaded_store_gives_clear_message(capsys):
    run(capsys, "load")
    next(Path("data").glob("*.nt")).write_text("garbage garbage\n")

    code, _, err = run(capsys, "group", "LG")

    assert code == 2
    assert "load" in err


def test_load_needs_no_other_arguments_and_rejects_extras():
    with pytest.raises(SystemExit):
        main(["load", "extra"])
