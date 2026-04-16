# MAST Enforce MCP Server

External enforcement tools for the 3 MAST failure modes that prompt engineering alone cannot solve:

| Failure Mode | Problem | Tool | Solution |
|---|---|---|---|
| FM-1.5 | Premature termination | `check_completion()` | Requires explicit evidence for each requirement before declaring done |
| FM-3.2 | No verification | `verify_code()` | Actually executes code and returns pass/fail — can't fake verification |
| FM-3.3 | Weak verification | `generate_edge_cases()` + `verify_code()` | Generates boundary conditions the agent wouldn't think of |

These are the 3 modes that remained problematic across configs in our ChatDev validation (baseline 8/14, MAST-Full 11/14, MAST-Lite 7/14). In v4 dynamic testing, FM-1.5 and FM-3.2 are now addressed by prompt engineering, but FM-3.3 (superficial verification) and FM-1.4 (context loss) still benefit from architectural enforcement. No amount of prompt text guarantees a model will actually run tests before delivering code, or will track all requirements across a long conversation.

## How It Works

The model calls these tools before critical actions:

```
1. Agent receives task
2. Agent implements solution
3. Agent calls verify_code() → MUST pass before delivery
4. Agent calls check_completion() → MUST return can_proceed: true before declaring done
5. Only after both pass can the agent deliver
```

RULES.md enforces this:

```markdown
## Mandatory Enforcement (MCP)

Before delivering any code artifact:
1. Call verify_code() with your implementation
2. If verify_code() returns failures, fix them and re-verify

Before declaring any task complete:
1. Call check_completion() with original requirements and deliverables
2. Only proceed if can_proceed: true

Delivering code without verification or declaring completion
without checking is a critical failure.
```

## Tools

### verify_code(code, language, test_cases, function_name, auto_edge_cases)

Executes code against test cases and returns pass/fail results.

- If `auto_edge_cases=True`, generates additional boundary conditions beyond those provided
- Returns `can_deliver: true` only if ALL tests pass
- Supports Python and JavaScript

```python
# Example: Agent verifies a palindrome function
result = verify_code(
    code='def is_palindrome(s): return s == s[::-1]',
    language='python',
    function_name='is_palindrome',
    test_cases='[{"input": {"s": "racecar"}, "expected": true}]',
    auto_edge_cases=True
)
# Returns edge cases the agent didn't think of:
# {"s": ""} → False (empty string)
# {"s": "Racecar"} → False (case sensitivity)
# {"s": "a"} → True (single char)
```

### check_completion(requirements, deliverables, strict)

Evaluates whether each requirement has concrete evidence before allowing task completion.

- Returns `can_proceed: true` only if ALL requirements have evidence (or 80% in non-strict mode)
- Detects "TODO", "not yet", "in progress" as unmet evidence
- Prevents the "I'm done, let me just add one more feature" loop

```python
result = check_completion(
    requirements='["Read CSV files", "Handle headers", "Validate data types"]',
    deliverables='{"0": "csv_reader function implemented", "1": "header parsing in lines 15-20", "2": "NOT YET DONE"}'
)
# Returns: can_proceed=False, unmet_count=1, unmet=[{"requirement": "Validate data types"}]
```

### generate_edge_cases(function_signature, description, language)

Generates boundary test cases for a function based on its parameter types.

- Handles string, numeric, list, and boolean edge cases
- Adds domain-specific cases based on description keywords (palindrome, sort, search, validate)
- Returns test case dicts with `input`, `expected`, and `category` fields

```python
cases = generate_edge_cases(
    function_signature='def is_palindrome(s: str) -> bool',
    description='Checks if a string reads the same forwards and backwards',
    language='python'
)
# Returns: [{"input": {"s": ""}, "category": "empty_string"}, ...]
```

## Installation

### As an MCP Server for Hermes Agent

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  mast-enforce:
    command: "uvx"
    args: ["--from", "/path/to/mast-skills/mcp/mast-enforce", "mast-enforce"]
```

Or run directly:

```bash
cd /path/to/mast-skills/mcp/mast-enforce
fastmcp run server.py
```

### As a Python Package

```bash
pip install -e /path/to/mast-skills/mcp/mast-enforce
```

## Testing

```bash
cd /path/to/mast-skills/mcp/mast-enforce
python -m pytest test_server.py -v
```

## Architecture

```
mast-enforce/
  server.py          # FastMCP server with 3 tools
  pyproject.toml     # Package config
  README.md          # This file
  test_server.py     # Unit tests
```

The server runs each code verification in an isolated subprocess with a 10-second timeout. It cannot access the filesystem, network, or agent process memory. This isolation is by design — the model can't tamper with the verification environment.

## Results

On our 14-mode dynamic test suite:

| Config | FM-1.5 | FM-3.2 | FM-3.3 | Total |
|---|---|---|---|---|
| Baseline (no defense) | FAIL | FAIL | FAIL | 8/14 |
| MAST-Full (prompts only) | FAIL | FAIL | FAIL | 11/14 |
| MAST + mast-enforce MCP | PASS | PASS | PASS | **14/14** |

The 3 modes that prompts can't solve are exactly the ones that need code execution and requirement tracing. This server provides that enforcement layer.

## License

MIT