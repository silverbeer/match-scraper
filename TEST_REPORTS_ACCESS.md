# How to Access Test Reports

## 🎯 Quick Answer
**Yes, failing tests will now prevent publishing!** The workflow will fail if tests fail.

## 📊 Accessing Test Reports

### Option 1: GitHub Actions Artifacts (All Branches)
1. Go to your GitHub Actions run: https://github.com/silverbeer/match-scraper/actions
2. Click on the failed/completed run
3. Scroll down to "Artifacts" section
4. Download `test-reports-[run-number]`
5. Extract and open `index.html` for full test report

### Option 2: GitHub Pages (Main Branch Only)
- **Live site:** https://silverbeer.github.io/match-scraper/
- Only updates when code is merged to `main` branch
- Feature branches won't update the live site (for security)

## 🚨 What Changed

### Before (Broken):
- Tests could fail but workflow would still "succeed"
- GitHub Pages only worked on main branch
- No way to see test reports from feature branches

### After (Fixed):
- ✅ **Test failures = workflow failure**
- ✅ **Test reports available as artifacts** (all branches)
- ✅ **GitHub Pages still works** (main branch only)
- ✅ **30-day retention** for test artifacts

## 🔍 What Reports Include
- **HTML Test Report:** Full test results with details
- **Coverage Report:** Code coverage analysis
- **JUnit XML:** For CI integration
- **JSON Report:** Machine-readable results

## 🛠️ For Your Current Branch
Since you're on `feature/code-quality-gates`:
1. Push your changes
2. Check the GitHub Actions run
3. Download the artifacts to see test reports
4. Fix any failing tests
5. Merge to main when ready (this will update the live site)
