# Code Coverage for New Code

## 🎯 Quick Start

### Automatic on Commit (Pre-commit Hook)
```bash
git commit -m "your message"
# Will automatically check coverage of changed files
# Requires 80% coverage of new/changed lines
```

### Manual Check
```bash
# Check coverage of your changes vs main branch
./scripts/check_coverage.sh

# Check vs different branch
./scripts/check_coverage.sh develop
```

## 📊 What Gets Measured

### diff-cover measures:
- **Lines added/modified** since the comparison branch
- **Coverage percentage** of only those new lines
- **Missing test coverage** for new code

### Example Output:
```
Diff Coverage: 85.7%
Lines not covered: src/scraper/new_feature.py (lines 23, 45-48)
```

## 🛠️ Available Commands

### 1. Pre-commit Hook (Automatic)
- Runs on `git commit` for `.py` files in `src/`
- Compares against `main` branch
- Requires 80% coverage of new code
- Fast: only runs unit tests

### 2. Manual Script
```bash
./scripts/check_coverage.sh [branch]
```
- Generates HTML report (`diff-cover.html`)
- Shows exact lines needing coverage
- Includes quality checks

### 3. CI Integration
```bash
# In GitHub Actions - compares against main
uv run pytest --cov=src --cov-report=xml
uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
```

## 🎨 Visual Reports

### HTML Diff Coverage Report
```bash
./scripts/check_coverage.sh
open diff-cover.html  # Shows highlighted uncovered lines
```

### Terminal Output
```bash
uv run diff-cover coverage.xml --compare-branch=main
```

## ⚙️ Configuration

### Change Coverage Threshold
Edit `.pre-commit-config.yaml`:
```yaml
--fail-under=80  # Change to desired percentage
```

### Change Comparison Branch
```bash
# Compare against develop instead of main
./scripts/check_coverage.sh develop
```

## 🏆 Best Practices

1. **Focus on new code**: Don't worry about legacy code coverage
2. **80% is reasonable**: Allows for error handling and edge cases
3. **Use HTML reports**: Visual feedback shows exactly what to test
4. **Test before commit**: Run `./scripts/check_coverage.sh` first

## 🚫 Bypass (Use Sparingly)
```bash
git commit --no-verify -m "WIP: will add tests later"
```

## 🔧 Troubleshooting

### "No coverage to compare"
- Make sure you have commits on the comparison branch
- Check branch names: `git branch -r`

### "Command not found: diff-cover"
```bash
uv sync --dev  # Install dev dependencies
```

### Hook too slow
- Comment out the diff-cover hook in `.pre-commit-config.yaml`
- Run manually: `./scripts/check_coverage.sh`
