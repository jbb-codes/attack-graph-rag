from pathlib import Path

import pytest

from attack_graph.cli import main


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestTechniqueLookup:
    def test_prints_name_tactics_and_related_items(self, capsys):
        code, out, _ = run(capsys, "technique", "T1003.001")

        assert code == 0
        assert "T1003.001" in out
        assert "LSASS Memory" in out
        assert "credential-access" in out
        assert "G0016 APT29" in out
        assert "G0007 APT28" in out
        assert "S0002 Mimikatz" in out
        assert "M1026 Privileged Account Management" in out

    def test_id_is_case_and_whitespace_insensitive(self, capsys):
        code, out, _ = run(capsys, "technique", " t1566.001 ")

        assert code == 0
        assert "Spearphishing Attachment" in out

    def test_technique_with_no_groups_says_so(self, capsys):
        code, out, _ = run(capsys, "technique", "T1543")

        assert code == 0
        assert "Groups: none" in out

    def test_unknown_id_gives_clear_message(self, capsys):
        code, out, err = run(capsys, "technique", "T9999")

        assert code == 1
        assert out == ""
        assert "No technique found with ID 'T9999'" in err


class TestGroupLookup:
    def test_prints_name_aliases_techniques_and_software(self, capsys):
        code, out, _ = run(capsys, "group", "APT29")

        assert code == 0
        assert "G0016" in out
        assert "Cozy Bear" in out
        assert "T1566.001 Spearphishing Attachment" in out
        assert "S0154 Cobalt Strike" in out

    def test_alias_lookup_is_case_insensitive(self, capsys):
        code, out, _ = run(capsys, "group", "cozy bear")

        assert code == 0
        assert "G0016" in out

    def test_unknown_name_gives_clear_message(self, capsys):
        code, out, err = run(capsys, "group", "Not A Group")

        assert code == 1
        assert out == ""
        assert "No group found named 'Not A Group'" in err


class TestDataFile:
    def test_missing_data_file_gives_clear_message(self, capsys, tmp_path: Path):
        missing = tmp_path / "nope.json"

        code, _, err = run(capsys, "--data", str(missing), "technique", "T1566")

        assert code == 2
        assert "nope.json" in err

    def test_invalid_json_gives_clear_message(self, capsys, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")

        code, _, err = run(capsys, "--data", str(bad), "technique", "T1566")

        assert code == 2
        assert "bad.json" in err

    def test_custom_data_file_is_used(self, capsys, tmp_path: Path):
        custom = tmp_path / "tiny.json"
        custom.write_text(
            '{"type":"bundle","objects":[{"type":"attack-pattern","id":"attack-pattern--1",'
            '"name":"Tiny Technique","description":"d",'
            '"external_references":[{"source_name":"mitre-attack","external_id":"T0001"}]}]}'
        )

        code, out, _ = run(capsys, "--data", str(custom), "technique", "T0001")

        assert code == 0
        assert "Tiny Technique" in out


def test_no_subcommand_exits_with_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])

    assert exc.value.code == 2
