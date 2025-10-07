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
- Calendar interaction has limitations with cross-month date ranges

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
