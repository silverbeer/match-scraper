# Claude Code Agents Configuration

This directory contains specialized AI agents for the MLS Match Scraper project.

## Available Agents

### 🧪 Test Guardian (`test-guardian`)
**Purpose**: Specialized agent for code review, test creation, and test debugging.

**Usage**:
```bash
# In Claude Code:
/agents test-guardian

# Then ask questions like:
# "Review recent changes and identify missing tests"
# "Fix the failing integration tests"
# "Create comprehensive tests for the new scraping module"
```

**Capabilities**:
- ✅ Analyze git diffs for test coverage gaps
- ✅ Write comprehensive unit tests following project patterns
- ✅ Debug and fix async mock issues (Playwright, AsyncMock patterns)
- ✅ Update tests when models/APIs change
- ✅ Optimize slow or flaky tests

**Integration**:
- Use with `uv run python scripts/test-review.py` for quick analysis
- Understands project structure: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- Knows recent fixes: Pydantic field changes, async mock patterns
- Follows CI pipeline: Only unit tests run on commits

## Helper Scripts

### Test Review Script
```bash
# Quick test status and recent changes
uv run python scripts/test-review.py review

# Focus on fixing failures
uv run python scripts/test-review.py fix

# Coverage analysis
uv run python scripts/test-review.py coverage
```

## Adding New Agents

1. Create a new `.md` file in `.claude/agents/`
2. Follow the pattern from `test-guardian.md`
3. Include purpose, methodology, and project-specific context
4. Commit to repo for team access

## Access Across Devices

These agent configurations are stored in the git repo, so they're available on any machine where you clone the project and use Claude Code.

Simply run `/agents` to see available agents or `/agents [agent-name]` to activate a specific one.