# Fast Development Workflow

## Quick Commits (1-2 seconds)
Pre-commit now only runs fast checks:
- Trailing whitespace cleanup
- File ending fixes
- YAML validation
- Large file detection
- Merge conflict detection
- Debug statement detection
- Ruff linting + formatting

## When You Need Full Validation

### Option 1: Temporary enable (uncomment in .pre-commit-config.yaml)
```bash
# Edit .pre-commit-config.yaml and uncomment the pytest/mypy sections
git add . && git commit -m "your message"
# Re-comment them after commit
```

### Option 2: Manual testing before commit
```bash
# Run tests manually
uv run pytest tests/unit/ -x --tb=short

# Run type checking
uv run mypy src/

# Then commit normally
git commit -m "your message"
```

### Option 3: Skip pre-commit entirely
```bash
git commit --no-verify -m "Quick fix - CI will catch issues"
```

## CI Still Runs Everything
Don't worry - GitHub Actions still runs:
- Full test suite (unit + integration + e2e)
- Complete mypy type checking
- Full ruff linting
- Coverage analysis

## Best Practice
- Use fast commits for most development
- Run full validation before important commits/PRs
- Let CI catch edge cases you miss locally
