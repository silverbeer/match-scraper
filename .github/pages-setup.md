# GitHub Pages Setup Instructions

To enable GitHub Pages for test reports, follow these steps:

## 1. Enable GitHub Pages

1. Go to your repository on GitHub
2. Click on **Settings** tab
3. Scroll down to **Pages** section
4. Under **Source**, select **GitHub Actions**
5. Save the configuration

## 2. Update Repository URLs

Replace `USERNAME` in the following files with your actual GitHub username:

### README.md
- Line 3: `https://github.com/USERNAME/match-scraper/actions/workflows/test-and-publish.yml/badge.svg`
- Line 4: `https://USERNAME.github.io/match-scraper/`
- Line 9: `https://USERNAME.github.io/match-scraper/`

### .github/workflows/test-and-publish.yml
- The workflow automatically detects the repository name using `$GITHUB_REPOSITORY`

## 3. Required Permissions

The workflow needs the following permissions (already configured):
- `contents: read` - to checkout code
- `pages: write` - to deploy to GitHub Pages
- `id-token: write` - for OIDC authentication

## 4. First Run

1. Push the changes to the `main` branch
2. The workflow will run automatically
3. GitHub Pages will be available at: `https://USERNAME.github.io/match-scraper/`

## 5. Features Included

### Test Reports
- **HTML Test Reports**: Pretty test results with pytest-html
- **Coverage Reports**: Interactive HTML coverage reports
- **JUnit XML**: For CI/CD integration
- **JSON Reports**: Machine-readable test results

### Badge Endpoints
- **Dynamic Badges**: Automatically updated coverage and test status badges
- **GitHub Pages Integration**: Test results hosted on GitHub Pages
- **Branch-specific Reports**: Separate reports for each branch

### Report Management
- **Automatic Cleanup**: Keeps last 5 reports per branch
- **Organized Structure**: Reports organized by branch and run number
- **Easy Navigation**: Index page with links to all reports

## 6. Accessing Reports

After the first successful run:
- **Main Report Page**: `https://USERNAME.github.io/match-scraper/`
- **Latest Test Results**: Available from the main page
- **Coverage Reports**: Click "Coverage Report" links for detailed coverage
- **Historical Reports**: Browse previous runs by branch

## 7. Troubleshooting

### If Pages don't deploy:
1. Check the **Actions** tab for workflow errors
2. Ensure GitHub Pages is enabled in repository settings
3. Verify the workflow has required permissions

### If badges don't update:
1. Wait a few minutes after the workflow completes
2. Check that the main branch workflow ran successfully
3. Clear browser cache for badge images
