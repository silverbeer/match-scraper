# Requirements Document

## Introduction

The MLS Match Scraper is an automated system that periodically scrapes match data from the MLS Next website, processes game schedules and scores, and posts this information to the missing-table.com API. The system will be deployed as a serverless Lambda function with comprehensive monitoring and local testing capabilities using LocalStack.

## Requirements

### Requirement 1

**User Story:** As a system administrator, I want an automated scraper that runs on a schedule, so that match data is consistently collected without manual intervention.

#### Acceptance Criteria

1. WHEN the scheduled time is reached THEN the system SHALL execute the scraping job automatically
2. WHEN the scraper runs THEN the system SHALL parse https://www.mlssoccer.com/mlsnext/schedule/all/ for match data
3. WHEN parsing is complete THEN the system SHALL extract game schedules and scores from the webpage
4. IF the scraper encounters network errors THEN the system SHALL retry up to 3 times with exponential backoff
5. WHEN the scraper completes THEN the system SHALL log execution metrics including games scheduled and games scored

### Requirement 2

**User Story:** As a data consumer, I want scraped match data to be automatically posted to missing-table.com, so that the latest game information is available through the API.

#### Acceptance Criteria

1. WHEN new game data is scraped THEN the system SHALL POST game information to the missing-table.com REST API
2. WHEN game scores are available THEN the system SHALL POST score updates to the missing-table.com REST API
3. IF API calls fail THEN the system SHALL retry with exponential backoff up to 3 times
4. WHEN API calls succeed THEN the system SHALL log successful data transmission
5. IF API authentication is required THEN the system SHALL handle authentication securely

### Requirement 3

**User Story:** As a system administrator, I want configurable scraping parameters, so that I can control which matches are scraped without code changes.

#### Acceptance Criteria

1. WHEN the Lambda starts THEN the system SHALL read environment variables for age_group, club, competition, and division
2. WHEN no environment variables are set THEN the system SHALL use defaults: age_group=U14, club=none, competition=none, division=Northeast
3. WHEN filtering matches THEN the system SHALL apply the configured parameters to limit results
4. IF invalid parameter values are provided THEN the system SHALL log warnings and use default values
5. WHEN parameters change THEN the system SHALL use new values without requiring code deployment

### Requirement 4

**User Story:** As a system administrator, I want configurable date range filtering, so that I can control how far back to look for match data.

#### Acceptance Criteria

1. WHEN the Lambda starts THEN the system SHALL read the look_back_days environment variable with default value of 1
2. WHEN calculating date range THEN the system SHALL use current date as end date and current date minus look_back_days as start date
3. WHEN interacting with the date picker THEN the system SHALL click the Match Date field to open the calendar
4. WHEN setting dates THEN the system SHALL select the calculated start and end dates in the calendar widget
5. WHEN dates are set THEN the system SHALL click Apply to filter results by the date range

### Requirement 5

**User Story:** As a developer, I want the scraper to use Playwright for web scraping, so that dynamic content and JavaScript-rendered pages are properly handled.

#### Acceptance Criteria

1. WHEN scraping begins THEN the system SHALL use Playwright to load the MLS Next schedule page
2. WHEN the page loads THEN the system SHALL wait for dynamic content to render completely
3. WHEN extracting data THEN the system SHALL handle JavaScript-generated DOM elements including calendar widgets
4. IF the page structure changes THEN the system SHALL gracefully handle parsing errors
5. WHEN scraping completes THEN the system SHALL properly close browser resources

### Requirement 6

**User Story:** As a DevOps engineer, I want the scraper deployed as a Lambda function, so that it runs cost-effectively and scales automatically.

#### Acceptance Criteria

1. WHEN deploying THEN the system SHALL package the Python scraper as an AWS Lambda function
2. WHEN the Lambda executes THEN the system SHALL complete within the configured timeout limit
3. WHEN packaging THEN the system SHALL include all required dependencies including Playwright
4. IF memory limits are exceeded THEN the system SHALL log appropriate error messages
5. WHEN Lambda completes THEN the system SHALL return appropriate success/failure status

### Requirement 7

**User Story:** As a DevOps engineer, I want infrastructure deployed using Terraform, so that infrastructure is version-controlled and reproducible.

#### Acceptance Criteria

1. WHEN deploying infrastructure THEN the system SHALL use Terraform configuration files
2. WHEN Terraform runs THEN the system SHALL create Lambda function, IAM roles, and CloudWatch resources
3. WHEN scheduling is configured THEN the system SHALL create EventBridge rules for periodic execution
4. IF infrastructure changes are needed THEN the system SHALL support incremental updates via Terraform
5. WHEN destroying infrastructure THEN the system SHALL cleanly remove all created resources

### Requirement 8

**User Story:** As a developer, I want CI/CD through GitHub Actions, so that code changes are automatically tested and deployed.

#### Acceptance Criteria

1. WHEN code is pushed to main branch THEN the system SHALL trigger automated deployment pipeline
2. WHEN tests run THEN the system SHALL execute unit tests and integration tests
3. WHEN tests pass THEN the system SHALL automatically deploy to AWS using Terraform
4. IF deployment fails THEN the system SHALL notify developers and halt the pipeline
5. WHEN deployment succeeds THEN the system SHALL update deployment status and notify stakeholders

### Requirement 9

**User Story:** As a developer, I want to test the system locally using LocalStack, so that I can develop and debug without incurring AWS costs.

#### Acceptance Criteria

1. WHEN running locally THEN the system SHALL use LocalStack to simulate AWS services
2. WHEN testing Lambda functions THEN the system SHALL execute against LocalStack Lambda service
3. WHEN testing EventBridge THEN the system SHALL use LocalStack EventBridge simulation
4. IF LocalStack services are unavailable THEN the system SHALL provide clear error messages
5. WHEN local testing completes THEN the system SHALL provide the same results as AWS deployment

### Requirement 10

**User Story:** As a system administrator, I want comprehensive metrics and monitoring, so that I can track system performance and identify issues.

#### Acceptance Criteria

1. WHEN the scraper runs THEN the system SHALL emit metrics for games scheduled and games scored
2. WHEN errors occur THEN the system SHALL log detailed error information with timestamps
3. WHEN API calls are made THEN the system SHALL track response times and success rates
4. IF performance degrades THEN the system SHALL alert administrators through CloudWatch alarms
5. WHEN metrics are collected THEN the system SHALL store them in CloudWatch for analysis and dashboards
