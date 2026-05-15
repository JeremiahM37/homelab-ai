"""ToolSpec schema generation."""
from homelab_ai.services.base import ToolSpec


async def _noop(**kwargs):
    return kwargs


def test_empty_params_schema():
    spec = ToolSpec(name="t", description="d", handler=_noop)
    schema = spec.json_schema()
    assert schema["type"] == "object"
    assert schema["properties"] == {}
    assert "required" not in schema


def test_typed_params():
    spec = ToolSpec(
        name="t", description="d", handler=_noop,
        params={
            "query": {"type": "string", "description": "q", "required": True},
            "limit": {"type": "integer", "default": 10},
        },
    )
    schema = spec.json_schema()
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["limit"]["default"] == 10
    assert schema["required"] == ["query"]


def test_no_default_becomes_required():
    spec = ToolSpec(name="t", description="d", handler=_noop,
                    params={"x": {"type": "string"}})
    schema = spec.json_schema()
    assert schema["required"] == ["x"]


def test_explicit_required_false():
    spec = ToolSpec(name="t", description="d", handler=_noop,
                    params={"x": {"type": "string", "required": False}})
    schema = spec.json_schema()
    assert "required" not in schema
