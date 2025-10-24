# Claude Code Configuration and Preferences

This file contains project-specific preferences and conventions for Claude Code to follow when working on this codebase.

## Code Style Preferences

### Data Models
- **Always use Pydantic models instead of dataclasses** for data structures
- Pydantic provides better validation, serialization, and developer experience
- Use Field() for field definitions with descriptions and constraints
- Implement field_validator and model_validator for custom validation logic
- Include JSON schema examples in Config class for documentation

### Example Pydantic Model Structure:
```python
from pydantic import BaseModel, Field, field_validator

class MyModel(BaseModel):
    name: str = Field(..., description="Name field")
    age: int = Field(ge=0, le=150, description="Age in years")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "age": 30
            }
        }
```

## Project-Specific Notes

### Date Range Logic
- CLI uses offset-based date arguments (--start, --end)
- Negative values = past dates, positive = future dates, 0 = today
- Calendar supports cross-month date ranges by detecting adjacent months and using both left/right calendar panels

### Environment Variables
- Use MISSING_TABLE_API_BASE_URL (not MISSING_TABLE_API_URL)
- Use MISSING_TABLE_API_TOKEN (not MISSING_TABLE_API_KEY)
- Both old and new naming conventions are supported for backwards compatibility

### Error Handling
- Implement fail-fast behavior for API operations
- Cache preload failures should stop execution
- Team creation/lookup failures should raise exceptions instead of continuing

### Team Name Mapping
- "Intercontinental Football Academy of New England" should display as "IFA"
- Apply normalization consistently across CLI output and API integration

## Documentation Maintenance

### Documentation Structure
All project documentation is organized in the `docs/` folder:

```
docs/
├── README.md              # Documentation hub and navigation
├── guides/                # How-to guides and tutorials
├── development/           # Development, testing, coverage guides
├── deployment/            # GKE deployment and CI/CD guides
├── observability/         # Monitoring, logging, metrics guides
└── architecture/          # Architecture decisions and summaries
```

### Documentation Guidelines

**IMPORTANT: Always keep documentation synchronized with code changes.**

#### When Making Changes
1. **New Features**: Update relevant guides in `docs/guides/`
   - Add CLI examples to `docs/guides/cli-usage.md`
   - Update main README.md if it's a major feature

2. **Code Changes**: Update technical documentation
   - API changes → Update integration guides
   - Model changes → Update data model documentation in README.md
   - Config changes → Update deployment guides in `docs/deployment/`

3. **Testing Changes**: Keep test documentation current
   - New test patterns → Update `docs/development/testing.md`
   - E2E test changes → Update `docs/development/e2e-testing.md`
   - Coverage changes → Update `docs/development/coverage.md`

4. **Deployment Changes**: Update infrastructure docs
   - K8s manifest changes → Update `docs/deployment/gke-deployment.md`
   - CI/CD changes → Update `docs/deployment/gke-github-actions.md`
   - Observability changes → Update `docs/observability/grafana-cloud-setup.md`

5. **Architecture Decisions**: Document in `docs/architecture/`
   - Major refactoring → Add or update architecture docs
   - Performance improvements → Document in fix summaries

#### Documentation Best Practices
- **Update docs in the same commit** as code changes
- **Use concrete examples** with actual commands and expected output
- **Keep links up to date** when moving or renaming files
- **Maintain the docs/README.md index** when adding new documentation
- **Include screenshots** for UI/visual features (in docs/images/)
- **Version-specific notes** should indicate which version they apply to

#### Documentation Quality Checklist
Before committing changes that include documentation:
- [ ] All code examples are tested and working
- [ ] Links to other docs are valid (no broken links)
- [ ] New features are documented with examples
- [ ] Deprecated features are marked as such
- [ ] docs/README.md is updated if adding new docs
- [ ] Main README.md reflects major changes
- [ ] Command examples include expected output
- [ ] Configuration examples are complete and accurate

#### Finding Documentation to Update
Use these commands to find related documentation:
```bash
# Find all references to a feature
grep -r "feature_name" docs/

# Find all markdown files
find docs/ -name "*.md"

# Check for broken links (if using markdown-link-check)
find docs/ -name "*.md" -exec markdown-link-check {} \;
```

### Documentation Anti-Patterns to Avoid
- ❌ **Don't** let documentation drift from code
- ❌ **Don't** create multiple docs for the same topic
- ❌ **Don't** leave TODO or incomplete sections uncommitted
- ❌ **Don't** document obsolete features without marking them deprecated
- ❌ **Don't** create root-level docs when `docs/` structure exists

### Special Documentation Files
- **CLAUDE.md** (this file) - Guidelines for AI assistants, project conventions
- **README.md** - Main project overview, stays in root
- **docs/README.md** - Documentation hub and navigation
- **terraform/README.md** - Terraform-specific documentation (stays with code)
- **scripts/README.md** - Scripts documentation (stays with code)
- **grafana/dashboards/README.md** - Dashboard documentation (stays with dashboards)

These files should remain with their respective code directories for context.
