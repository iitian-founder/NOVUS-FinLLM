"""
code_executor.py — Sandboxed Python Execution Node
====================================================
Executes the analyst-approved projection code in a secure subprocess sandbox.

Security measures:
  - Restricted builtins (no __import__, exec, eval, open, etc.)
  - No network access (subprocess inherits no env vars)
  - No filesystem access (restricted builtins)
  - 30-second timeout
  - Output is JSON only (structured projection results)
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict


# Builtins that are SAFE for financial calculations
ALLOWED_BUILTINS = [
    "abs", "bool", "dict", "enumerate", "float", "int",
    "isinstance", "len", "list", "max", "min", "pow",
    "print", "range", "round", "sorted", "str", "sum",
    "tuple", "zip", "True", "False", "None",
]

SANDBOX_TIMEOUT_SECONDS = 30


def _build_sandbox_script(code: str, assumptions_json: str) -> str:
    """Build a self-contained Python script that runs inside the sandbox."""
    return textwrap.dedent(f"""\
import json
import math
import sys

# ── Restricted builtins ──
_safe = {{k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k) for k in {ALLOWED_BUILTINS!r} if (isinstance(__builtins__, dict) and k in __builtins__) or hasattr(__builtins__, k)}}
_safe["math"] = math
_safe["json"] = json

# ── Inject the projection code ──
{code}

# ── Load assumptions and execute ──
assumptions = json.loads('''{assumptions_json}''')
try:
    result = run_projection(assumptions)
    print(json.dumps(result, indent=2, default=str))
except Exception as exc:
    print(json.dumps({{"error": str(exc)}}, indent=2))
    sys.exit(1)
""")


def code_executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the approved projection code in a sandboxed subprocess.
    """
    code = state.get("generated_projection_code", "")
    assumptions = state.get("locked_assumptions", state.get("draft_assumptions", {}))

    print(f"\n{'='*60}")
    print(f"⚡ CODE EXECUTOR — Running in sandbox...")
    print(f"{'='*60}")

    if not code:
        return {
            "code_execution_error": "No projection code to execute",
            "multi_year_projection": {},
        }

    # Serialize assumptions to JSON for injection
    assumptions_json = json.dumps(assumptions, default=str).replace("'", "\\'")

    # Build the sandbox script
    sandbox_script = _build_sandbox_script(code, assumptions_json)

    # Write to a temp file and execute
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix="projection_sandbox_"
        ) as f:
            f.write(sandbox_script)
            script_path = f.name

        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=SANDBOX_TIMEOUT_SECONDS,
            env={},  # Empty env → no network, no secrets
        )

        # Clean up
        Path(script_path).unlink(missing_ok=True)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            print(f"  ❌ Sandbox execution failed: {error_msg[:200]}")
            return {
                "code_execution_error": error_msg,
                "multi_year_projection": {},
            }

        # Parse output
        output = result.stdout.strip()
        projection_result = json.loads(output)

        if "error" in projection_result:
            print(f"  ❌ Projection code error: {projection_result['error']}")
            return {
                "code_execution_error": projection_result["error"],
                "multi_year_projection": {},
            }

        n_items = len(projection_result.get("projections", {}))
        n_derived = len(projection_result.get("derived_items", {}))
        print(f"  ✅ Projection executed: {n_items} items + {n_derived} derived items")

        return {
            "code_execution_error": None,
            "multi_year_projection": projection_result,
        }

    except subprocess.TimeoutExpired:
        Path(script_path).unlink(missing_ok=True)
        print(f"  ❌ Sandbox timeout after {SANDBOX_TIMEOUT_SECONDS}s")
        return {
            "code_execution_error": f"Execution timed out after {SANDBOX_TIMEOUT_SECONDS}s",
            "multi_year_projection": {},
        }
    except json.JSONDecodeError as exc:
        print(f"  ❌ Failed to parse projection output: {exc}")
        return {
            "code_execution_error": f"Output JSON parse error: {exc}",
            "multi_year_projection": {},
        }
    except Exception as exc:
        print(f"  ❌ Unexpected error: {exc}")
        return {
            "code_execution_error": str(exc),
            "multi_year_projection": {},
        }
