import requests
import json
import sys

# Minimal mock payload based on output
payload = {
    "ticker": "HINDUNILVR",
    "query": "Test execute",
    "approved_plan": [
        {"agent_id": "fsa_quant", "description": "Test FSA"}
    ],
    "assumptions": [
        {"id": "wacc", "human_override": "15.0"},
        {"id": "terminal_growth", "human_override": "8.0"},
        {"id": "projection_years", "human_override": "5"}
    ]
}

print("Testing /execute...")
try:
    with requests.post(
        "http://localhost:5001/api/v1/research/execute", 
        json=payload, 
        stream=True
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                print(decoded_line)
except Exception as e:
    print(f"Error: {e}")
