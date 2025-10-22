# Async Message Queue Architecture

**A beginner-friendly guide to understanding the match-scraper → RabbitMQ → Celery pipeline**

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [Components Explained](#components-explained)
4. [Message Flow Walkthrough](#message-flow-walkthrough)
5. [Code Path Deep Dive](#code-path-deep-dive)
6. [Data Models & Contracts](#data-models--contracts)
7. [Configuration](#configuration)
8. [Testing & Monitoring](#testing--monitoring)
9. [Troubleshooting](#troubleshooting)

---

## Overview

### What Problem Does This Solve?

**Before (Synchronous):**
```
Scraper → HTTP API → Database
   ↓         ↓          ↓
 Wait... Wait... Done!
```
- Scraper waits for API to finish
- If API is down, scraping fails
- No retry mechanism
- Hard to scale

**After (Asynchronous with Message Queue):**
```
Scraper → Queue → Workers → Database
   ↓        ↓        ↓         ↓
 Done!   Stores   Process   Save!
```
- Scraper finishes immediately
- Messages persist even if workers are down
- Automatic retries
- Easy to scale (add more workers)

### Key Benefits

✅ **Decoupling**: Scraper and workers don't need to know about each other
✅ **Resilience**: Messages persist if workers fail or restart
✅ **Scalability**: Add more workers to process faster
✅ **Reliability**: Automatic retries and error handling
✅ **Observability**: Monitor queue depth and worker status

---

## Architecture Diagrams

### High-Level System Architecture

```mermaid
graph TB
    subgraph "K3s Cluster (Mac Mini)"
        MS[Match Scraper<br/>CronJob]
        RMQ[RabbitMQ<br/>Message Broker]
        W1[Celery Worker 1]
        W2[Celery Worker 2]

        MS -->|Publish Messages| RMQ
        RMQ -->|Consume| W1
        RMQ -->|Consume| W2
    end

    subgraph "Cloud"
        SB[(Supabase<br/>PostgreSQL)]
    end

    W1 -->|Write Data| SB
    W2 -->|Write Data| SB

    style MS fill:#e1f5ff
    style RMQ fill:#fff4e1
    style W1 fill:#e8f5e9
    style W2 fill:#e8f5e9
    style SB fill:#f3e5f5
```

### Detailed Component Interaction

```mermaid
sequenceDiagram
    participant Scraper as Match Scraper
    participant RMQ as RabbitMQ
    participant Worker as Celery Worker
    participant DB as Supabase

    Note over Scraper: Daily 6 AM UTC
    Scraper->>Scraper: Scrape MLS website
    Scraper->>Scraper: Parse match data
    Scraper->>Scraper: Validate with Pydantic

    Scraper->>RMQ: Publish message to "matches" queue
    Note over RMQ: Message persists<br/>until acknowledged

    RMQ->>Worker: Deliver message
    Worker->>Worker: Deserialize JSON
    Worker->>Worker: Validate data

    Worker->>DB: Look up teams
    DB-->>Worker: Return team IDs

    Worker->>DB: Check for duplicate match
    DB-->>Worker: Return existing match (if any)

    alt Match exists
        Worker->>DB: Update scores
    else New match
        Worker->>DB: Insert new match
    end

    Worker->>RMQ: ACK (acknowledge message)
    Note over RMQ: Message removed<br/>from queue
```

### Message Flow Through the System

```mermaid
flowchart LR
    subgraph Producer["Producer (match-scraper)"]
        A1[Scrape Matches] --> A2[Validate Data]
        A2 --> A3[Serialize to JSON]
        A3 --> A4[Send to Queue]
    end

    subgraph Broker["Message Broker (RabbitMQ)"]
        B1[Receive Message]
        B2[Store in Queue]
        B3[Route to Consumer]

        B1 --> B2 --> B3
    end

    subgraph Consumer["Consumer (Celery Worker)"]
        C1[Receive Message]
        C2[Deserialize JSON]
        C3[Process Task]
        C4[Write to Database]
        C5[Send ACK]

        C1 --> C2 --> C3 --> C4 --> C5
    end

    A4 -->|AMQP Protocol| B1
    B3 -->|Task Delivery| C1
    C5 -->|Acknowledge| B2

    style A4 fill:#bbdefb
    style B2 fill:#fff9c4
    style C3 fill:#c8e6c9
```

### Queue and Task States

```mermaid
stateDiagram-v2
    [*] --> Scraped: Match data scraped
    Scraped --> Validated: Pydantic validation
    Validated --> Queued: Published to RabbitMQ

    state "RabbitMQ Queue" as Queue {
        Queued --> Pending: Message stored
        Pending --> Delivered: Worker available
    }

    state "Worker Processing" as Worker {
        Delivered --> Processing: Task started
        Processing --> Success: Completed successfully
        Processing --> Retry: Temporary failure
        Retry --> Processing: Retry attempt
        Processing --> Failed: Max retries exceeded
    }

    Success --> Acknowledged: Send ACK
    Acknowledged --> [*]: Message removed

    Failed --> DeadLetter: Move to DLQ
    DeadLetter --> [*]: Requires manual intervention
```

---

## Components Explained

### 1. Match Scraper (Producer)

**Role:** Scrapes match data from MLS website and publishes to queue

**Location:** `match-scraper` repo
**Deployment:** Kubernetes CronJob (runs daily at 6 AM UTC)
**Key Files:**
- `src/cli/main.py` - Entry point for scraping
- `src/celery/queue_client.py` - Queue publishing logic
- `src/models/match_data.py` - Data validation schema

**What It Does:**
1. Scrapes match data from MLS Next website
2. Validates data using Pydantic models
3. Converts to JSON format
4. Publishes messages to RabbitMQ queue
5. Exits (doesn't wait for processing)

**Key Code:**
```python
# Initialize queue client
queue_client = MatchQueueClient()

# Publish match to queue
task_id = queue_client.submit_match({
    "home_team": "IFA",
    "away_team": "NEFC",
    "match_date": "2025-10-18",
    "season": "2024-25",
    "age_group": "U14",
    "division": "Northeast",
    "match_type": "League"
})
```

---

### 2. RabbitMQ (Message Broker)

**Role:** Stores and routes messages between producer and consumers

**Location:** K3s cluster (`match-scraper` namespace)
**Management UI:** http://localhost:30672
**Credentials:** admin / admin123

**What It Does:**
1. Receives messages from scraper via AMQP protocol
2. Stores messages persistently in queues
3. Routes messages to available workers
4. Tracks message acknowledgments
5. Provides monitoring and management UI

**Key Concepts:**

**Queues:**
- `matches` - Main queue for match data messages
- Messages persist until acknowledged by worker

**Exchanges:**
- Routes messages to appropriate queues
- Uses routing keys (e.g., `matches.*`)

**Acknowledgments:**
- Worker sends ACK when task completes successfully
- If worker crashes, message stays in queue for retry

---

### 3. Celery Workers (Consumers)

**Role:** Processes messages and writes data to Supabase

**Location:** `missing-table` repo
**Deployment:** Kubernetes Deployment (2 replicas)
**Key Files:**
- `backend/celery_app.py` - Celery app configuration
- `backend/celery_tasks/match_tasks.py` - Task definitions
- `backend/dao/` - Database access layer

**What It Does:**
1. Connects to RabbitMQ and listens to `matches` queue
2. Receives messages from queue
3. Deserializes JSON to Python dict
4. Validates data against schema
5. Looks up teams in Supabase
6. Checks for duplicate matches
7. Inserts or updates match in database
8. Sends ACK to RabbitMQ

**Key Code:**
```python
@app.task(name="celery_tasks.match_tasks.process_match_data", bind=True)
def process_match_data(self: Task, match_data: dict) -> dict:
    """Process a match data message from queue"""

    # Validate data
    validated = MatchData(**match_data)

    # Look up teams
    home_team = find_or_create_team(validated.home_team)
    away_team = find_or_create_team(validated.away_team)

    # Check for duplicate
    existing = find_match_by_external_id(validated.external_match_id)

    if existing:
        # Update scores if needed
        update_match(existing.id, validated)
    else:
        # Create new match
        create_match(validated)

    return {"status": "success"}
```

---

### 4. Supabase (Database)

**Role:** Stores match, team, and related data

**Location:** Cloud (Supabase hosted PostgreSQL)
**Environment:** Dev or Prod (configurable)

**Tables:**
- `matches` - Match records
- `teams` - Team information
- `seasons` - Season data
- `age_groups` - Age group categories
- `divisions` - Division information

---

## Message Flow Walkthrough

Let's trace a single match through the entire system:

### Step 1: Scraping (0-30 seconds)

```
match-scraper CronJob starts
    ↓
Playwright navigates to MLS Next website
    ↓
Parse match: "IFA vs NEFC, 2025-10-18"
    ↓
Create match dict
```

**Code Location:** `src/scraper/mls_scraper.py`

---

### Step 2: Validation (< 1 second)

```
Match dict passed to MatchQueueClient
    ↓
Pydantic validation:
    ✓ home_team: "IFA" (string, non-empty)
    ✓ away_team: "NEFC" (string, non-empty)
    ✓ match_date: 2025-10-18 (valid date)
    ✓ match_status: "completed" (valid enum)
    ↓
Validation passes → Continue
```

**Code Location:** `src/models/match_data.py`

**What Happens on Validation Failure:**
- `ValidationError` raised
- Match skipped (not queued)
- Error logged
- Scraper continues with next match

---

### Step 3: Publishing to Queue (< 1 second)

```
Create Celery message:
{
    "task": "celery_tasks.match_tasks.process_match_data",
    "id": "887795e2-12a9-4e72-ba8e-04ff29f44205",
    "args": [{
        "home_team": "IFA",
        "away_team": "NEFC",
        "match_date": "2025-10-18",
        ...
    }],
    "kwargs": {},
    "routing_key": "matches.process"
}
    ↓
Serialize to JSON
    ↓
Send to RabbitMQ via AMQP
    ↓
RabbitMQ stores in "matches" queue
    ↓
Scraper receives task_id and exits
```

**Code Location:** `src/celery/queue_client.py:84-131`

**AMQP Connection:**
```
Protocol: AMQP 0.9.1
URL: amqp://admin:admin123@rabbitmq.match-scraper:5672//
Queue: matches
Routing Key: matches.process
Persistence: Yes (message survives broker restart)
```

---

### Step 4: Queue Storage (persistent)

```
RabbitMQ receives message
    ↓
Stores in "matches" queue
    ↓
Message state: "Ready" (waiting for consumer)
    ↓
[Message waits here until worker is available]
    ↓
Worker connects and asks for work
    ↓
RabbitMQ delivers message to worker
    ↓
Message state: "Unacked" (delivered but not acknowledged)
```

**Queue Status:**
```bash
$ kubectl exec rabbitmq-0 -- rabbitmqctl list_queues
matches    1    2  # 1 message, 2 consumers ready
```

---

### Step 5: Worker Receives Task (< 1 second)

```
Worker polling queue
    ↓
RabbitMQ delivers message
    ↓
Worker deserializes JSON → Python dict
    ↓
Celery calls: process_match_data(match_data)
    ↓
Task starts processing
```

**Worker Log:**
```
[INFO] Task celery_tasks.match_tasks.process_match_data[887795e2...] received
[INFO] Processing match data: IFA vs NEFC
```

**Code Location:** `backend/celery_tasks/match_tasks.py:166-283`

---

### Step 6: Database Operations (1-2 seconds)

```
Connect to Supabase
    ↓
Look up home team: "IFA"
    → SQL: SELECT * FROM teams WHERE name ILIKE 'IFA'
    → Result: team_id = 123
    ↓
Look up away team: "NEFC"
    → SQL: SELECT * FROM teams WHERE name ILIKE 'NEFC'
    → Result: team_id = 456
    ↓
Check for existing match:
    → SQL: SELECT * FROM matches WHERE match_id = '100436'
    → Result: match_id = 789 (already exists)
    ↓
Compare scores:
    → Existing: NULL (no score)
    → New: 5-1 (completed)
    → Action: UPDATE needed
    ↓
Update match:
    → SQL: UPDATE matches SET home_score=5, away_score=1,
           match_status='completed' WHERE id=789
    → Result: 1 row updated
    ↓
Success!
```

**Worker Log:**
```
[INFO] HTTP Request: GET .../teams?name=ilike.IFA "HTTP/2 200 OK"
[INFO] HTTP Request: GET .../matches?match_id=eq.100436 "HTTP/2 200 OK"
[INFO] Updating existing match 789: IFA vs NEFC
[INFO] HTTP Request: PATCH .../matches?id=eq.789 "HTTP/2 200 OK"
[INFO] Successfully updated match 789: {'home_score': 5, 'away_score': 1}
```

---

### Step 7: Task Completion (< 1 second)

```
Database operation successful
    ↓
Worker sends ACK to RabbitMQ
    ↓
RabbitMQ removes message from queue
    ↓
Task result stored in RPC backend (optional)
    ↓
Worker ready for next task
```

**Worker Log:**
```
[INFO] Successfully processed match: {'match_id': 789, 'status': 'updated'}
[INFO] Task succeeded in 1.86s: {'match_id': 789, ...}
```

**Queue Status After:**
```bash
$ kubectl exec rabbitmq-0 -- rabbitmqctl list_queues
matches    0    2  # 0 messages (processed!), 2 consumers ready
```

---

### Total Time: ~3 seconds end-to-end

```
Scraping:     30s  (network dependent)
Validation:   <1s
Publishing:   <1s
Queue:        <1s  (immediate delivery)
Processing:   1-2s (database operations)
ACK:          <1s
────────────────────
Total:        ~33s per match
```

With 2 workers processing concurrently, can handle ~120 matches/minute!

---

## Code Path Deep Dive

### Producer Code Path (match-scraper)

#### 1. CLI Entry Point

**File:** `src/cli/main.py:920-971`

```python
# User runs: python -m src.cli.main scrape --use-queue

# Initialize queue client
from src.celery.queue_client import MatchQueueClient

queue_client = MatchQueueClient()  # Reads RABBITMQ_URL env var

# Check connection
if not queue_client.check_connection():
    print("Cannot connect to RabbitMQ")
    return

# Convert matches to dicts
match_dicts = []
for match in matches:
    match_dict = {
        "home_team": match.home_team,
        "away_team": match.away_team,
        "match_date": match.match_datetime.date(),
        ...
    }
    match_dicts.append(match_dict)

# Submit batch
task_ids = queue_client.submit_matches_batch(match_dicts)
```

---

#### 2. Queue Client Initialization

**File:** `src/celery/queue_client.py:32-76`

```python
class MatchQueueClient:
    def __init__(self, broker_url: Optional[str] = None):
        # Get RabbitMQ URL
        self.broker_url = broker_url or os.getenv("RABBITMQ_URL")
        # Example: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"

        # Create Celery app (producer-only)
        self.app = Celery("match_scraper", broker=self.broker_url)

        # Configure
        self.app.conf.update(
            task_ignore_result=True,      # Don't wait for results
            task_serializer="json",       # Use JSON (not pickle)
            accept_content=["json"],      # Only accept JSON
            broker_connection_retry=True, # Retry on connection failure
        )
```

**Why these settings?**

| Setting | Value | Reason |
|---------|-------|--------|
| `task_ignore_result` | `True` | We don't need to wait for worker response (fire-and-forget) |
| `task_serializer` | `"json"` | JSON is safe, portable, and human-readable |
| `accept_content` | `["json"]` | Security: only accept JSON (not Python pickle which can execute code) |
| `broker_connection_retry` | `True` | Auto-reconnect if RabbitMQ temporarily unavailable |

---

#### 3. Message Publishing

**File:** `src/celery/queue_client.py:84-131`

```python
def submit_match(self, match_data: dict) -> str:
    # Step 1: Validate
    try:
        validated = MatchData(**match_data)
    except ValidationError as e:
        print(f"Validation failed: {e}")
        raise  # Don't queue invalid data!

    # Step 2: Send to queue
    result = self.app.send_task(
        # CRITICAL: Task name must match worker's @app.task(name=...)
        "celery_tasks.match_tasks.process_match_data",

        # Arguments (serialized to JSON)
        args=[validated.model_dump(mode="json")],

        # Queue name (where message goes in RabbitMQ)
        queue="matches",

        # Routing key (for exchange routing)
        routing_key="matches.process",
    )

    print(f"Match submitted to queue: {result.id}")
    return result.id  # UUID for tracking
```

**Message Structure Sent to RabbitMQ:**
```json
{
  "task": "celery_tasks.match_tasks.process_match_data",
  "id": "887795e2-12a9-4e72-ba8e-04ff29f44205",
  "args": [
    {
      "home_team": "IFA",
      "away_team": "NEFC",
      "match_date": "2025-10-18",
      "season": "2024-25",
      "age_group": "U14",
      "match_type": "League",
      "division": "Northeast",
      "home_score": 5,
      "away_score": 1,
      "match_status": "completed",
      "external_match_id": "100436"
    }
  ],
  "kwargs": {},
  "callbacks": null,
  "errbacks": null,
  "chain": null,
  "chord": null,
  "retries": 0,
  "eta": null,
  "expires": null
}
```

---

### Consumer Code Path (Celery Worker)

#### 1. Worker Startup

**File:** `backend/celery_app.py`

```python
from celery import Celery

# Create Celery app
app = Celery("missing_table_worker")

# Configure
app.conf.update(
    # Broker (RabbitMQ)
    broker_url="amqp://admin:admin123@rabbitmq.match-scraper:5672//",

    # Results backend (RPC = stores in RabbitMQ)
    result_backend="rpc://",

    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Queue routing
    task_routes={
        'celery_tasks.match_tasks.*': {'queue': 'matches'},
    },
)
```

**Starting the Worker:**
```bash
celery -A backend.celery_app worker \
    --loglevel=info \
    --queues=matches \
    --concurrency=4
```

This creates 4 worker processes that can handle 4 tasks simultaneously.

---

#### 2. Task Definition

**File:** `backend/celery_tasks/match_tasks.py:166-283`

```python
from celery import Task
from backend.celery_app import app

@app.task(
    name="celery_tasks.match_tasks.process_match_data",  # MUST match producer!
    bind=True  # Gives access to self (the task instance)
)
def process_match_data(self: Task, match_data: dict) -> dict:
    """
    Process a match data message from the queue.

    This function is automatically called when a message arrives
    in the 'matches' queue with task name matching this decorator.
    """

    logger.info(f"Processing match data: {match_data['home_team']} vs {match_data['away_team']}")

    try:
        # Validate data
        validated = MatchData(**match_data)

        # Database operations
        result = process_match_to_database(validated)

        return result

    except Exception as e:
        logger.error(f"Error processing match: {e}")

        # Retry with exponential backoff
        raise self.retry(
            exc=e,
            countdown=60,  # Wait 60 seconds before retry
            max_retries=3   # Try up to 3 times
        )
```

**Key Concepts:**

**`bind=True`:**
- Gives access to `self` (the task instance)
- Needed for `self.retry()` to retry failed tasks

**Retry Logic:**
```python
# First attempt fails → Wait 60s → Retry (attempt 2)
# Second attempt fails → Wait 60s → Retry (attempt 3)
# Third attempt fails → Wait 60s → Retry (attempt 4)
# Fourth attempt fails → Give up, move to dead-letter queue
```

---

#### 3. Database Processing

**File:** `backend/celery_tasks/match_tasks.py:166-283`

```python
def process_match_to_database(match_data: MatchData) -> dict:
    # Connect to Supabase
    supabase = get_supabase_client()

    # Look up teams
    home_team = supabase.table("teams") \
        .select("id, name") \
        .ilike("name", match_data.home_team) \
        .limit(1) \
        .execute()

    away_team = supabase.table("teams") \
        .select("id, name") \
        .ilike("name", match_data.away_team) \
        .limit(1) \
        .execute()

    # Check for existing match
    existing = supabase.table("matches") \
        .select("*") \
        .eq("match_id", match_data.external_match_id) \
        .limit(1) \
        .execute()

    if existing.data:
        # Update existing match
        match_id = existing.data[0]["id"]

        result = supabase.table("matches") \
            .update({
                "home_score": match_data.home_score,
                "away_score": match_data.away_score,
                "match_status": match_data.match_status,
            }) \
            .eq("id", match_id) \
            .execute()

        return {"match_id": match_id, "status": "updated"}
    else:
        # Create new match
        result = supabase.table("matches") \
            .insert({
                "match_id": match_data.external_match_id,
                "home_team_id": home_team.data[0]["id"],
                "away_team_id": away_team.data[0]["id"],
                "match_date": match_data.match_date,
                "home_score": match_data.home_score,
                "away_score": match_data.away_score,
                "match_status": match_data.match_status,
                ...
            }) \
            .execute()

        return {"match_id": result.data[0]["id"], "status": "created"}
```

---

#### 4. Acknowledgment

When the task completes successfully:

```python
# Celery automatically sends ACK to RabbitMQ
# Message is removed from queue
# Worker is ready for next task
```

If task raises an exception:

```python
# If retries exhausted:
#   - Celery sends NACK (negative acknowledgment)
#   - Message moved to dead-letter queue
#   - Requires manual intervention

# If retries available:
#   - Task retried after countdown
#   - Message stays in queue as "unacked"
```

---

## Data Models & Contracts

### Message Contract (JSON Schema)

The producer and consumer agree on this data structure:

```python
# File: src/models/match_data.py (match-scraper)
# File: backend/models/match_data.py (missing-table)

from pydantic import BaseModel, Field
from datetime import date

class MatchData(BaseModel):
    """
    Match data contract between producer and consumer.

    IMPORTANT: Both repos maintain their own copy of this model.
    Changes must be synchronized or versioned!
    """

    # Required fields
    home_team: str = Field(..., min_length=1)
    away_team: str = Field(..., min_length=1)
    match_date: date
    season: str = Field(..., min_length=1)
    age_group: str = Field(..., min_length=1)
    match_type: str = Field(..., min_length=1)

    # Optional fields
    division: str | None = None
    home_score: int | None = Field(None, ge=0)
    away_score: int | None = Field(None, ge=0)
    match_status: Literal["scheduled", "completed", "postponed", "cancelled"] | None = None
    external_match_id: str | None = None
    location: str | None = None
    notes: str | None = None
```

**Why Duplicate the Model?**

Each service maintains its own copy to avoid coupling:
- Services can be deployed independently
- No shared library dependencies
- Contract enforced through JSON schema validation
- Breaking changes detected at validation time

**Version Management:**
```python
# Future: Add version field for schema evolution
class MatchData(BaseModel):
    schema_version: str = "1.0"  # Bump on breaking changes
    ...
```

---

### Example Valid Message

```json
{
  "home_team": "IFA",
  "away_team": "NEFC",
  "match_date": "2025-10-18",
  "season": "2024-25",
  "age_group": "U14",
  "match_type": "League",
  "division": "Northeast",
  "home_score": 5,
  "away_score": 1,
  "match_status": "completed",
  "external_match_id": "100436",
  "location": "Boston, MA",
  "notes": null
}
```

---

### Example Invalid Messages

**Missing Required Field:**
```json
{
  "home_team": "IFA",
  // Missing away_team!
  "match_date": "2025-10-18"
}
```
**Error:** `ValidationError: field required (type=value_error.missing)`

---

**Invalid Type:**
```json
{
  "home_team": "IFA",
  "away_team": "NEFC",
  "match_date": "not-a-date",  // Invalid date format!
  ...
}
```
**Error:** `ValidationError: invalid date format (type=value_error.date)`

---

**Invalid Enum Value:**
```json
{
  ...
  "match_status": "TBD"  // Not in allowed values!
}
```
**Error:** `ValidationError: value is not a valid enumeration member; permitted: 'scheduled', 'completed', 'postponed', 'cancelled'`

---

## Configuration

### Environment Variables

#### Match-Scraper (Producer)

**File:** `k3s/match-scraper/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: match-scraper-config
  namespace: match-scraper
data:
  # Scraping config
  AGE_GROUP: "U14"
  DIVISION: "Northeast"

  # RabbitMQ connection
  RABBITMQ_URL: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"

  # Logging
  LOG_LEVEL: "INFO"
  NO_COLOR: "1"  # Disable colors in K8s logs
```

---

#### Celery Worker (Consumer)

**File:** `k3s/worker/configmap.yaml` (in missing-table repo)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: missing-table-worker-config
  namespace: match-scraper
data:
  # RabbitMQ connection (SAME as producer!)
  RABBITMQ_URL: "amqp://admin:admin123@rabbitmq.match-scraper:5672//"

  # Results backend
  CELERY_RESULT_BACKEND: "rpc://"

  # Supabase connection
  SUPABASE_URL: "https://ppgxasqgqbnauvxozmjw.supabase.co"

  # Worker config
  CELERY_WORKER_CONCURRENCY: "4"
  LOG_LEVEL: "INFO"
```

**File:** `k3s/worker/secret.yaml`

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: missing-table-worker-secrets
  namespace: match-scraper
type: Opaque
stringData:
  SUPABASE_KEY: "your-supabase-service-key-here"
```

---

### RabbitMQ Configuration

**File:** `k3s/rabbitmq/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: rabbitmq-config
  namespace: match-scraper
data:
  rabbitmq.conf: |
    # Networking
    listeners.tcp.default = 5672
    management.tcp.port = 15672

    # Clustering (single node for local)
    cluster_formation.peer_discovery_backend = classic_config

    # Persistence
    queue_master_locator = min-masters

    # Monitoring
    management.load_definitions = /etc/rabbitmq/definitions.json

  enabled_plugins: |
    [rabbitmq_management,rabbitmq_prometheus,rabbitmq_federation].
```

---

### Kubernetes Deployments

#### Match-Scraper CronJob

**File:** `k3s/match-scraper/cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: match-scraper-cronjob
  namespace: match-scraper
spec:
  # Run daily at 6 AM UTC
  schedule: "0 6 * * *"
  timeZone: "UTC"

  # Don't allow concurrent runs
  concurrencyPolicy: Forbid

  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: match-scraper
            image: match-scraper:latest
            imagePullPolicy: Never  # Use local image

            command: ["python", "-m", "src.cli.main", "scrape"]
            # Note: --use-queue is enabled by default

            envFrom:
            - configMapRef:
                name: match-scraper-config
            - secretRef:
                name: match-scraper-secrets
                optional: true

            resources:
              requests:
                memory: "1Gi"
                cpu: "500m"
              limits:
                memory: "2Gi"
                cpu: "1000m"
```

---

#### Celery Worker Deployment

**File:** `k3s/worker/deployment.yaml` (in missing-table repo)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: missing-table-celery-worker
  namespace: match-scraper
spec:
  replicas: 2  # 2 worker pods for concurrency

  selector:
    matchLabels:
      app: missing-table-worker

  template:
    metadata:
      labels:
        app: missing-table-worker

    spec:
      containers:
      - name: celery-worker
        image: missing-table-worker:latest
        imagePullPolicy: Never

        command:
          - celery
          - -A
          - backend.celery_app
          - worker
          - --loglevel=info
          - --queues=matches
          - --concurrency=4  # 4 processes per pod

        envFrom:
        - configMapRef:
            name: missing-table-worker-config
        - secretRef:
            name: missing-table-worker-secrets

        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
```

**Total Concurrency:** 2 pods × 4 workers = 8 concurrent tasks!

---

## Testing & Monitoring

### Manual Testing

#### 1. Trigger a Test Job

```bash
# Manually trigger scraper (doesn't wait for scheduled time)
./scripts/test-k3s.sh trigger

# Output:
# Job created: test-run-1760880253
# Monitor with: ./scripts/test-k3s.sh logs
```

---

#### 2. Monitor Scraper Logs

```bash
./scripts/test-k3s.sh logs

# Or directly:
kubectl logs -n match-scraper -l app=match-scraper --tail=100 -f
```

**Expected Output:**
```
✓ Celery client initialized
✓ RabbitMQ connection successful
✓ Match submitted to queue: 887795e2-12a9-4e72-ba8e-04ff29f44205
✓ Match submitted to queue: b361ea4a-af92-4562-b9c0-335b586f570a
✓ Batch complete: 5 submitted, 3 failed
✅ 5 matches queued for processing
```

---

#### 3. Check Queue Status

```bash
./scripts/test-k3s.sh rabbitmq

# Or directly:
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_queues name messages consumers
```

**Expected Output:**
```
matches    5    2    # 5 messages, 2 consumers connected
```

**Interpretation:**
- `5 messages` - Tasks waiting to be processed
- `2 consumers` - 2 worker pods connected and ready
- If messages > 0 for extended time, workers may be slow or stuck

---

#### 4. Monitor Worker Logs

```bash
kubectl logs -n match-scraper -l app=missing-table-worker --tail=50 -f
```

**Expected Output:**
```
[INFO] Task celery_tasks.match_tasks.process_match_data[887795e2...] received
[INFO] Processing match data: IFA vs NEFC
[INFO] HTTP Request: GET .../teams?name=ilike.IFA "HTTP/2 200 OK"
[INFO] Updating existing match 450: IFA vs NEFC
[INFO] Successfully updated match 450
[INFO] Task succeeded in 1.86s
```

---

#### 5. Verify in Supabase

```bash
# Check matches table in Supabase dashboard
# OR query via API:

curl -X GET 'https://your-project.supabase.co/rest/v1/matches' \
  -H "apikey: your-anon-key" \
  -H "Authorization: Bearer your-anon-key"
```

---

### RabbitMQ Management UI

**Access:** http://localhost:30672
**Credentials:** admin / admin123

#### Useful Sections:

**Queues Tab:**
- View all queues
- See message counts
- Monitor consumer connections
- Manually purge messages (for testing)

**Connections Tab:**
- See active connections (scraper, workers)
- Check connection state
- View channels

**Admin Tab:**
- User management
- Virtual host configuration
- Policy settings

---

### Health Checks

#### Check All Components

```bash
# RabbitMQ
kubectl get pods -n match-scraper -l app=rabbitmq
# Expected: 1/1 Running

# Workers
kubectl get pods -n match-scraper -l app=missing-table-worker
# Expected: 2/2 Running (both pods ready)

# CronJob
kubectl get cronjob -n match-scraper
# Expected: ACTIVE=0 (not currently running)

# Recent jobs
kubectl get jobs -n match-scraper --sort-by=.metadata.creationTimestamp
# Shows recent scraper runs
```

---

#### Check Queue Metrics

```bash
# Queue depth over time
watch -n 2 'kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_queues name messages consumers'

# Expected during processing:
# matches    10    2    # Queue filling up
# matches    5     2    # Workers consuming
# matches    0     2    # Queue empty (all processed!)
```

---

### Logging

#### Structured JSON Logs

Workers output structured JSON logs for easy parsing:

```json
{
  "timestamp": "2025-10-19T13:25:11.467436Z",
  "level": "info",
  "logger": "celery_tasks.match_tasks",
  "event": "Processing match data: IFA vs NEFC",
  "filename": "match_tasks.py",
  "lineno": 169
}
```

**Parse with jq:**
```bash
kubectl logs -n match-scraper -l app=missing-table-worker | \
  grep '{' | \
  jq -r 'select(.level=="error") | .event'
```

---

### Metrics & Alerting

#### RabbitMQ Prometheus Metrics

RabbitMQ exposes Prometheus metrics on port 15692:

```yaml
# Access metrics
curl http://rabbitmq.match-scraper:15692/metrics
```

**Key Metrics:**
- `rabbitmq_queue_messages` - Messages in queue
- `rabbitmq_queue_consumers` - Active consumers
- `rabbitmq_queue_messages_published_total` - Total published
- `rabbitmq_queue_messages_delivered_total` - Total delivered

**Alert Examples:**
```yaml
# Alert if queue backlog > 100
- alert: RabbitMQHighQueueDepth
  expr: rabbitmq_queue_messages{queue="matches"} > 100
  for: 5m

# Alert if no consumers connected
- alert: RabbitMQNoConsumers
  expr: rabbitmq_queue_consumers{queue="matches"} == 0
  for: 5m
```

---

## Troubleshooting

### Common Issues & Solutions

#### Issue 1: Messages Not Being Consumed

**Symptoms:**
```bash
$ kubectl exec rabbitmq-0 -- rabbitmqctl list_queues
matches    50    0    # Messages stuck, no consumers!
```

**Diagnosis:**
```bash
# Check if workers are running
kubectl get pods -n match-scraper -l app=missing-table-worker

# If pods not running:
kubectl describe pod -n match-scraper -l app=missing-table-worker
```

**Solutions:**

**A) Workers Not Deployed:**
```bash
# Deploy workers from missing-table repo
kubectl apply -f k3s/worker/
```

**B) Workers Crashed:**
```bash
# Check logs for errors
kubectl logs -n match-scraper -l app=missing-table-worker --tail=100

# Common issues:
# - Database connection failed
# - Invalid configuration
# - Resource limits exceeded

# Restart workers
kubectl rollout restart deployment missing-table-celery-worker -n match-scraper
```

**C) Wrong Queue Name:**
```bash
# Verify worker is listening to correct queue
kubectl logs -n match-scraper -l app=missing-table-worker | grep "queues"
# Should show: .> matches exchange=matches(direct)
```

---

#### Issue 2: Tasks Failing with Validation Errors

**Symptoms:**
```
[ERROR] ValidationError: 1 validation error for MatchData
match_status
  Input should be 'scheduled', 'completed', 'postponed' or 'cancelled'
```

**Diagnosis:**
This means the producer is sending data that doesn't match the consumer's schema.

**Solutions:**

**A) Check Schema Versions:**
```bash
# Compare producer model
cat match-scraper/src/models/match_data.py

# With consumer model
cat missing-table/backend/models/match_data.py
```

**B) Update Producer to Send Valid Data:**
```python
# In match-scraper code, ensure match_status is valid:
valid_statuses = ["scheduled", "completed", "postponed", "cancelled"]

if match.status not in valid_statuses:
    match.status = "scheduled"  # Default fallback
```

**C) Add Field to Consumer Schema:**
```python
# If producer added new field, update consumer:
class MatchData(BaseModel):
    ...
    new_field: str | None = None  # Make optional for backward compatibility
```

---

#### Issue 3: Database Connection Errors

**Symptoms:**
```
[ERROR] ConnectionError: Error connecting to Supabase
```

**Diagnosis:**
```bash
# Check worker logs for full error
kubectl logs -n match-scraper -l app=missing-table-worker --tail=100 | grep -A 10 "ConnectionError"
```

**Solutions:**

**A) Check Supabase URL:**
```bash
# Verify ConfigMap has correct URL
kubectl get configmap missing-table-worker-config -n match-scraper -o yaml

# Expected:
# SUPABASE_URL: "https://ppgxasqgqbnauvxozmjw.supabase.co"
```

**B) Check Supabase Key:**
```bash
# Verify Secret exists and is correct
kubectl get secret missing-table-worker-secrets -n match-scraper -o yaml

# Test key manually:
curl -X GET 'https://your-project.supabase.co/rest/v1/teams' \
  -H "apikey: your-key" \
  -H "Authorization: Bearer your-key"
```

**C) Network Connectivity:**
```bash
# Test from worker pod
kubectl exec -n match-scraper -it \
  deployment/missing-table-celery-worker -- \
  curl -I https://ppgxasqgqbnauvxozmjw.supabase.co

# Should return: HTTP/2 200
```

---

#### Issue 4: RabbitMQ Connection Refused

**Symptoms:**
```
[ERROR] Connection refused: amqp://admin:***@rabbitmq.match-scraper:5672//
```

**Diagnosis:**
```bash
# Check if RabbitMQ pod is running
kubectl get pods -n match-scraper -l app=rabbitmq

# Check RabbitMQ logs
kubectl logs -n match-scraper rabbitmq-0 --tail=100
```

**Solutions:**

**A) RabbitMQ Not Running:**
```bash
# Check pod status
kubectl describe pod rabbitmq-0 -n match-scraper

# Common issues:
# - PVC not bound (check storage)
# - Resource limits (check node resources)
# - ConfigMap errors (check configuration)

# Restart if stuck
kubectl delete pod rabbitmq-0 -n match-scraper
# StatefulSet will recreate it
```

**B) Wrong Hostname:**
```bash
# Verify service exists
kubectl get svc -n match-scraper rabbitmq

# Should show:
# rabbitmq   ClusterIP   10.x.x.x   5672/TCP,15672/TCP

# Test DNS resolution from scraper pod
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  nslookup rabbitmq.match-scraper
```

**C) Wrong Credentials:**
```bash
# Check RabbitMQ secret
kubectl get secret rabbitmq-secret -n match-scraper -o yaml

# Decode and verify:
echo "YWRtaW4=" | base64 -d  # Should be: admin
```

---

#### Issue 5: Memory/CPU Limits

**Symptoms:**
```
Pod OOMKilled / CPU Throttling
Workers slow or unresponsive
```

**Diagnosis:**
```bash
# Check resource usage
kubectl top pods -n match-scraper

# Check limits
kubectl describe pod -n match-scraper -l app=missing-table-worker | \
  grep -A 5 "Limits"
```

**Solutions:**

**A) Increase Resource Limits:**
```yaml
# Edit worker deployment
kubectl edit deployment missing-table-celery-worker -n match-scraper

# Increase limits:
resources:
  requests:
    memory: "1Gi"    # Was 512Mi
    cpu: "500m"      # Was 250m
  limits:
    memory: "2Gi"    # Was 1Gi
    cpu: "1000m"     # Was 500m
```

**B) Reduce Concurrency:**
```bash
# Edit ConfigMap
kubectl edit configmap missing-table-worker-config -n match-scraper

# Change from 4 to 2:
CELERY_WORKER_CONCURRENCY: "2"

# Restart workers
kubectl rollout restart deployment missing-table-celery-worker -n match-scraper
```

**C) Scale Horizontally:**
```bash
# Add more worker pods instead of increasing resources
kubectl scale deployment missing-table-celery-worker -n match-scraper --replicas=4
```

---

#### Issue 6: Messages Going to Dead Letter Queue

**Symptoms:**
Messages disappear from main queue but don't get processed successfully.

**Diagnosis:**
```bash
# Check for dead letter queue
kubectl exec -n match-scraper rabbitmq-0 -- \
  rabbitmqctl list_queues name messages | grep dead

# Check worker logs for repeated failures
kubectl logs -n match-scraper -l app=missing-table-worker | \
  grep -i "retry\|failed"
```

**Solutions:**

**A) View Failed Messages:**
```bash
# Access RabbitMQ UI: http://localhost:30672
# Navigate to Queues → matches.dead_letter
# Click "Get Messages" to see failed tasks
```

**B) Analyze Failure Pattern:**
```python
# Common causes:
# - Invalid data (fix validation)
# - Database constraints (fix data or schema)
# - Transient errors exceeded retries (increase max_retries)
```

**C) Requeue Messages:**
```bash
# In RabbitMQ UI:
# Queues → matches.dead_letter → Move messages
# Select destination: matches
# Click "Move messages"
```

---

### Debugging Tools

#### Interactive Shell in Worker Pod

```bash
# Open shell in worker pod
kubectl exec -n match-scraper -it \
  deployment/missing-table-celery-worker -- /bin/bash

# Inside pod, you can:
# - Test database connections
# - Run Python REPL
# - Inspect environment variables
# - Test task execution
```

---

#### Test Task Execution Manually

```python
# Inside worker pod Python REPL:
from backend.celery_tasks.match_tasks import process_match_data
from backend.models.match_data import MatchData

# Create test data
test_match = {
    "home_team": "IFA",
    "away_team": "NEFC",
    "match_date": "2025-10-18",
    "season": "2024-25",
    "age_group": "U14",
    "match_type": "League",
    "division": "Northeast"
}

# Execute task directly (bypasses queue)
result = process_match_data(test_match)
print(result)
```

---

#### Monitor Network Traffic

```bash
# Install tcpdump in RabbitMQ pod
kubectl exec -n match-scraper rabbitmq-0 -- apk add tcpdump

# Capture AMQP traffic
kubectl exec -n match-scraper rabbitmq-0 -- \
  tcpdump -i any -n port 5672 -w /tmp/rabbitmq.pcap

# Download and analyze with Wireshark
kubectl cp match-scraper/rabbitmq-0:/tmp/rabbitmq.pcap ./rabbitmq.pcap
```

---

## Best Practices

### 1. Message Design

**✅ DO:**
- Keep messages small (< 1MB)
- Use JSON for portability
- Version your message schema
- Include correlation IDs for tracing
- Add timestamps for debugging

**❌ DON'T:**
- Send binary data (images, PDFs) in messages
- Include sensitive data unencrypted
- Use Python pickle (security risk)
- Create circular task chains
- Make messages dependent on external state

---

### 2. Error Handling

**✅ DO:**
- Implement retry logic with exponential backoff
- Use dead-letter queues for failed messages
- Log errors with context (task ID, data)
- Alert on high failure rates
- Gracefully handle transient failures

**❌ DON'T:**
- Retry indefinitely (set max_retries)
- Ignore errors silently
- Retry immediately (use countdown)
- Log sensitive data in errors
- Assume network is always available

---

### 3. Monitoring

**✅ DO:**
- Monitor queue depth
- Track task duration
- Alert on consumer count = 0
- Log structured data (JSON)
- Set up health checks

**❌ DON'T:**
- Only check when something breaks
- Ignore slow tasks
- Let queues grow unbounded
- Skip dead-letter queue monitoring
- Forget to rotate logs

---

### 4. Scaling

**✅ DO:**
- Scale workers horizontally
- Monitor resource usage
- Use separate queues for different priorities
- Batch similar operations
- Cache frequently accessed data

**❌ DON'T:**
- Scale beyond database capacity
- Ignore worker resource limits
- Mix slow and fast tasks in same queue
- Create too many workers (connection overhead)
- Forget about RabbitMQ resource limits

---

### 5. Security

**✅ DO:**
- Use TLS for production RabbitMQ
- Store credentials in Kubernetes Secrets
- Rotate credentials regularly
- Limit network access (NetworkPolicies)
- Validate all input data

**❌ DON'T:**
- Hardcode credentials
- Use default passwords
- Expose RabbitMQ management UI publicly
- Trust message data without validation
- Skip authentication

---

## Additional Resources

### Documentation
- [Celery Documentation](https://docs.celeryproject.org/)
- [RabbitMQ Tutorials](https://www.rabbitmq.com/tutorials)
- [Pydantic Validation](https://docs.pydantic.dev/)
- [AMQP Protocol](https://www.amqp.org/)

### Tools
- [RabbitMQ Management UI](http://localhost:30672)
- [Flower (Celery monitoring)](https://flower.readthedocs.io/)
- [Prometheus + Grafana](https://prometheus.io/)

### Related Documentation
- [K3s Deployment Guide](../deployment/k3s-deployment.md)
- [Local Development Setup](../guides/local-development.md)
- [CLI Usage Guide](../guides/cli-usage.md)

---

## Appendix: Quick Reference

### Common Commands

```bash
# Trigger scraper
./scripts/test-k3s.sh trigger

# View logs
./scripts/test-k3s.sh logs

# Check queue
./scripts/test-k3s.sh rabbitmq

# Check status
kubectl get all -n match-scraper

# Scale workers
kubectl scale deployment missing-table-celery-worker --replicas=4

# Restart workers
kubectl rollout restart deployment missing-table-celery-worker

# Purge queue (testing only!)
kubectl exec rabbitmq-0 -n match-scraper -- \
  rabbitmqctl purge_queue matches
```

---

### Architecture Summary

```
┌────────────────────────────────────────────────────────┐
│                    COMPLETE FLOW                       │
├────────────────────────────────────────────────────────┤
│                                                        │
│  1. CronJob scrapes MLS website (daily 6 AM UTC)      │
│  2. Validates match data with Pydantic                │
│  3. Publishes JSON message to RabbitMQ                │
│  4. RabbitMQ stores message in "matches" queue        │
│  5. Worker receives message via AMQP                  │
│  6. Worker validates and processes data               │
│  7. Worker writes to Supabase database                │
│  8. Worker sends ACK to RabbitMQ                      │
│  9. Message removed from queue                        │
│                                                        │
│  ✅ End-to-end latency: ~3 seconds                     │
│  ✅ Throughput: ~120 matches/minute with 2 workers    │
│  ✅ Reliability: Messages persist, auto-retry         │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

**Last Updated:** 2025-10-19
**Version:** 1.0
**Maintainers:** match-scraper team

---

*This guide is designed to be educational and approachable for developers new to message queue architectures. For questions or improvements, please submit an issue or PR!*
