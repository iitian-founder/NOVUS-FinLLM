import pytest
from agents.agent_base import AgentBase

def test_extract_json():
    # Test stripping <think> tags (R1 reasoning) and markdown fences
    raw = '''<think> Let me think </think>
```json
{"key": "value"}
```
'''
    result = AgentBase._extract_json(raw)
    assert result == '{"key": "value"}'

    # Test raw json extraction fallback
    raw_text = 'Here is the json: {"a": 1, "b": {"c": 2}} hope it helps.'
    result = AgentBase._extract_json(raw_text)
    assert result == '{"a": 1, "b": {"c": 2}}'

def test_nullify_numerical_fields():
    # Test setting int/float to None for the kill switch functionality
    data = {
        "revenue": 100.5,
        "count": 5,
        "name": "Reliance",
        "nested": {"debt": 50, "string_val": "high"}
    }
    result = AgentBase._nullify_numerical_fields(data)
    
    assert result["revenue"] is None
    assert result["count"] is None
    assert result["name"] == "Reliance"
    assert result["nested"]["debt"] is None
    assert result["nested"]["string_val"] == "high"
