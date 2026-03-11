# Testing

**Status:** Stable

**Context:** Test infrastructure, conventions, and how to run the test suite. Intended for engineers writing or debugging tests.

**Outcome:** After reading, you can run all tests, add new test cases, and understand the test organization.

## Running Tests

```bash
pytest tests/ -q
```

Full quality check:

```bash
pytest tests/ -q && ruff check src/ tests/ && mypy src/
```

## Test Structure

```
tests/
├── __init__.py
├── test_config.py       # Config loading and validation
├── test_router.py       # Notification filtering, classification, formatting
├── test_poller.py       # URL parsing, context fetching
├── test_executor.py     # Prompt building, output parsing
├── test_workspace.py    # Workspace path computation
└── test_audit.py        # Audit entry serialization and reading
```

Each test file maps to a source module. Test classes group related assertions. Every test method has a docstring following the project convention.

## Test Configuration

Configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
pythonpath = ["src"]
```

- `asyncio_mode = "auto"` — Async test functions run automatically without `@pytest.mark.asyncio`
- `asyncio_default_fixture_loop_scope = "function"` — Keeps async fixture loop behavior stable across pytest-asyncio versions
- `pythonpath = ["src"]` — Tests import directly from `agent0.*`

## Writing Tests

### Conventions

- Test classes named `TestXxx` grouping related tests
- Test methods named `test_xxx` describing what is being verified
- Every test gets a docstring: `Compute that [behavior].`
- No comments unless critical
- No print statements
- No fallbacks — tests fail hard
- One assertion per test where practical

### Helper Pattern

Tests use factory functions to create test fixtures:

```python
def _make_config() -> Config:
    return Config(github_token='test', anthropic_api_key='test')
```

### Testing Sync Functions

Most router and executor functions are synchronous and can be tested directly:

```python
class TestShouldProcess:

    def test_mention(self) -> None:
        assert should_process({'reason': 'mention'}, _make_config())

    def test_subscribed_not_actionable(self) -> None:
        assert not should_process({'reason': 'subscribed'}, _make_config())
```

### Testing Async Functions

Async functions work automatically due to `asyncio_mode = "auto"`:

```python
async def test_read_history_empty(tmp_path: Path) -> None:
    config = Config(github_token='test', anthropic_api_key='test', data_dir=tmp_path)
    entries = await read_history(config)
    assert entries == []
```

### What to Test

When adding a new feature:

1. **Pure functions first** — Notification filtering, prompt building, output parsing
2. **Dataclass construction** — Verify fields are populated correctly from raw data
3. **Edge cases** — Empty inputs, missing keys, truncation boundaries
4. **Integration boundaries** — Mock the GitHub API client for poller tests

### What Not to Mock

Avoid mocking internal functions. Test them directly with controlled inputs. Mock only at the boundaries:

- `GitHubClient` methods (for testing Poller without hitting the API)
- File system operations (use `tmp_path` fixture)
- Subprocess execution (for testing executor without spawning Claude Code)

## Code Quality

### Ruff

```bash
ruff check src/ tests/
```

Configuration in `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py312"
line-length = 99

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
```

Checks: PEP 8 style (E), Pyflakes errors (F), import sorting (I), warnings (W).

### Mypy

```bash
mypy src/
```

Configuration:

```toml
[tool.mypy]
strict = true
python_version = "3.12"
explicit_package_bases = true
mypy_path = ["src"]
```

Strict mode enables all optional checks. All functions require type hints. No `Any` without explicit annotation.
