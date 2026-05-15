"""NUT plugin — protocol parsing + tool wiring (no live TCP)."""
import pytest

from homelab_ai.services.nut import NUT, _to_float


def test_parse_list_ups_extracts_name_and_description():
    lines = [
        'UPS apc900 "APC Back-UPS 900"',
        'UPS apc-rack "Rack UPS"',
        'OK',
    ]
    parsed = NUT._parse_list_ups(lines)
    assert {p["name"] for p in parsed} == {"apc900", "apc-rack"}
    assert parsed[0]["description"] == "APC Back-UPS 900"


def test_parse_list_ups_skips_unrelated_lines():
    lines = ["BEGIN LIST UPS", 'UPS x ""', "END LIST UPS", "junk"]
    assert len(NUT._parse_list_ups(lines)) == 1


def test_parse_vars_round_trip():
    lines = [
        'VAR myups battery.charge "100"',
        'VAR myups battery.runtime "3600"',
        'VAR myups ups.status "OL"',
    ]
    parsed = NUT._parse_vars(lines)
    assert parsed["battery.charge"] == "100"
    assert parsed["ups.status"] == "OL"


def test_parse_vars_skips_unrelated_lines():
    lines = ["VAR ups foo bar", "RANDOM JUNK", 'VAR ups x "y"']
    out = NUT._parse_vars(lines)
    # The first line has 3 tokens after VAR; 'foo' is treated as the name
    # and 'bar' as the value (unquoted). Either we accept this or we
    # require quotes. Documenting current behaviour:
    assert "foo" in out
    assert out["foo"] == "bar"
    assert out["x"] == "y"


def test_to_float_handles_garbage():
    assert _to_float("3.14") == 3.14
    assert _to_float(None) is None
    assert _to_float("not-a-number") is None
    assert _to_float("") is None


def test_tools_use_default_ups_when_set():
    svc = NUT({"host": "x", "ups": "myups"}, None)
    names = [t.name for t in svc.tools()]
    assert "nut_list_upses" in names
    assert "nut_battery" in names
    assert "nut_status" in names
