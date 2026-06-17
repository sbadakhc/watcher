# Watcher - AI-Powered Marketplace Moderation

AI-assisted listing moderation for e-commerce platforms. Built for the AIXCL BYO app framework.

## Overview

Watcher provides a three-outcome AI moderation pipeline for marketplace listings:

1. **Text moderation** via Ollama (configurable, default `qwen3:4b`)
2. **Image analysis** via vision model (configurable, default `qwen2.5vl:3b`)
3. **Threshold routing** -- auto-approve, auto-reject, or human review queue

Confident approvals publish immediately. Confident violations are auto-rejected and
the seller's violation count is incremented. Only genuinely ambiguous listings reach
the human review queue.

## Architecture

```
User submits listing
        |
        v
POST /api/submit  (returns immediately)
        |
        v (background task)
+--------------------------------------+
|  Moderation Pipeline                 |
|                                      |
|  1. Image analysis (vision model)    |
|  2. Text + image combined classify   |
|  3. Threshold routing                |
+--------------------------------------+
        |
   +----+----+
   |    |    |
   v    v    v
AUTO  HUMAN  AUTO
APPROVE REVIEW REJECT
(published)  (queue) (rejected)
```

## Platform Integration

| Service | Integration |
|---------|-------------|
| **PostgreSQL** | Dedicated `watcher` database, `watcher` schema |
| **Vault** | Secrets via `/run/secrets` (db password, auth credentials) |
| **Ollama** | `localhost:11434` via host networking |
| **Open WebUI** | Shared access to `qwen3:4b` and `qwen2.5vl:3b` -- use for interactive model testing and decision debugging (`http://localhost:8080`) |
| **Prometheus** | Metrics on `:9104/api/metrics` |
| **Grafana** | Dashboard at `grafana/dashboards/watcher-moderation.json` |

## File Structure

```
watcher/
+-- app.yaml                          # AIXCL manifest
+-- docker-compose.yml                # Watcher service
+-- README.md                         # This file
+-- grafana/
|   +-- dashboards/
|       +-- watcher-moderation.json   # Grafana dashboard
+-- scripts/
|   +-- seed.py                       # Demo data seeder
+-- watcher/                          # FastAPI backend + frontend
    +-- Dockerfile
    +-- requirements.txt
    +-- config.py                     # Settings from env/Vault
    +-- auth.py                       # Password hashing + basic auth
    +-- db.py                         # PostgreSQL schema + CRUD
    +-- models.py                     # Pydantic models
    +-- moderation.py                 # LLM pipeline + threshold logic
    +-- main.py                       # FastAPI app + routes
    +-- static/
        +-- index.html                # Vanilla JS SPA (storefront, submit, review, dashboard)
```

## Quick Start

### Prerequisites

- AIXCL platform running (`./aixcl stack start --profile sys`)
- Vault initialized and unsealed
- Models pulled in Ollama (names are case-sensitive; must match `./aixcl models list` output exactly):
  ```bash
  ./aixcl models add qwen3:4b
  ./aixcl models add qwen2.5vl:3b
  ```

### 1. Build and Start

```bash
# From AIXCL repo root
./aixcl app build watcher
./aixcl app start watcher
```

No manual secret or database setup is required. The `provision:` section of `app.yaml`
declares what Watcher needs; on every start the platform idempotently:

- generates secrets in Vault KV (`kv/apps/watcher`)
- renders them into the per-app volume `aixcl-app-watcher-secrets`
  (`/run/secrets/watcher-<name>` inside the container)
- creates the `watcher` PostgreSQL role and database

To see the generated credentials:

```bash
./aixcl app secrets watcher
```

Note the `watcher-user-password` and `watcher-admin-password` values -- you will need
these to log in to the UI. The usernames are `user` and `admin` respectively.

If the service does not become healthy, check the logs directly via podman
(`./aixcl stack logs` only covers platform services, not app containers):

```bash
podman logs --tail 50 watcher-moderation
```

### 2. Access the UI

```
http://localhost:9104
```

### 3. Seed Demo Data

The seed script creates 4 seller accounts with realistic account histories and
submits 13 listings that exercise all three pipeline outcomes.

```bash
DB_PASS=$(podman exec watcher-moderation cat /run/secrets/watcher-db-password)
USER_PASS=$(podman exec watcher-moderation cat /run/secrets/watcher-user-password)
podman cp scripts/seed.py watcher-moderation:/tmp/seed.py
podman exec watcher-moderation python3 /tmp/seed.py \
  --db-password "$DB_PASS" \
  --user-password "$USER_PASS"
```

Expected outcome: ~7 auto-approved, ~3 auto-rejected, ~3 to human review queue.

### 4. Review Queue

Navigate to the "Review Queue" tab. Listings the LLM could not confidently classify
appear here for human decision.

### 5. Check Stats

The "Stats" tab shows pipeline throughput, average latency, and queue depth.

### 6. Grafana Dashboard

The watcher ships a dedicated Grafana dashboard provisioned automatically when the app starts.

**Credentials:**

```bash
./aixcl vault passwords
# Use the "Grafana admin" username and password
```

**URL:** `http://localhost:3000`

Navigate to Dashboards -> Watcher -> **Watcher Moderation Dashboard**.

| Panel | What it shows |
|-------|---------------|
| Total Moderated | Cumulative listings processed |
| Auto-Resolve Rate | Percentage handled without human intervention |
| Published / Auto-Rejected / In Review | Current counts by outcome |
| Review Queue Depth | Listings awaiting human decision (key operational signal) |
| Model Error Rate | LLM failures by pipeline stage |
| Avg Latency | Mean end-to-end moderation time |
| Decisions Breakdown | Pie chart of approve/reject/review ratio |
| Moderation Latency (p95/p99) | Time-series latency percentiles |

**Note on logs:** Watcher container logs are not shipped to Loki -- no log driver is configured. The platform Grafana/Loki stack will not show watcher logs. Use `podman logs` for log access (see Step 1 above).

### 7. Inspect the Database (pgAdmin)

pgAdmin is available for direct database inspection.

**Credentials:**

```bash
./aixcl vault passwords
# Use the "pgAdmin admin" username and password
```

**URL:** `http://localhost:5050`

The watcher database is pre-created by the platform on app start. To browse it:

1. Log in to pgAdmin
2. In the left panel: Servers -> AIXCL -> Databases -> **watcher**
3. Navigate to Schemas -> **watcher** -> Tables

| Table | Contents |
|-------|----------|
| `users` | Seller and admin accounts |
| `listings` | All listings with current moderation status |
| `listing_images` | Uploaded images (stored as BYTEA) |
| `listing_moderation` | AI decisions -- confidence scores, risk scores, latency |
| `human_review_queue` | Listings pending human decision |
| `listing_publish_log` | Full audit trail of publish and reject actions |

### 8. Interact with the Models (Open WebUI)

Open WebUI provides a chat interface to the same models the watcher pipeline uses.
It is useful for understanding and tuning pipeline behaviour without going through
the full submission flow.

**Credentials:**

```bash
./aixcl vault passwords
# Use the "Open WebUI admin" username and password
```

**URL:** `http://localhost:8080`

| Use case | How |
|----------|-----|
| Test how the text model classifies a listing | Paste the listing title and description into a chat with `qwen3:4b` and ask it to assess whether the content violates marketplace policy |
| Debug an unexpected decision | Reproduce the listing text or image in Open WebUI to see the model's raw reasoning -- helps distinguish a threshold tuning issue from a model behaviour issue |
| Test the vision model against a specific image | Start a chat with `qwen2.5vl:3b`, attach the image, and ask for a content assessment before submitting it through the pipeline |
| Verify models are loaded and responding | Confirm both `qwen3:4b` and `qwen2.5vl:3b` appear in the model selector and respond before starting the watcher |

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health` | GET | No | Service health |
| `/api/metrics` | GET | No | Prometheus metrics |
| `/api/login` | POST | No | User login (returns user info) |
| `/api/submit` | POST | No | Submit listing (async, returns immediately) |
| `/api/listings` | GET | No | Published listings (storefront) |
| `/api/listings/{id}` | PUT | No | Edit and resubmit a rejected listing |
| `/api/listings/{id}` | DELETE | No | Delete a listing (owner or admin) |
| `/api/my-listings` | GET | No | Seller's own listings with status |
| `/api/review-queue` | GET | No | Human review queue |
| `/api/review/{id}` | POST | No | Moderator action (publish/ban/approve/reject) |
| `/api/ban-user/{username}` | POST | No | Ban a user (admin only) |
| `/api/images/{id}` | GET | No | Serve listing image (supports ?width=N) |
| `/api/stats` | GET | No | Moderation statistics |

## Database Schema

All tables in `watcher` schema within the dedicated `watcher` database:

| Table | Purpose |
|-------|---------|
| `users` | User accounts (sellers and admins) |
| `listings` | Product listings with moderation status |
| `listing_images` | Uploaded images stored as BYTEA |
| `listing_moderation` | AI decisions with confidence, risk score, latency |
| `human_review_queue` | Listings awaiting human judgement |
| `listing_publish_log` | Audit trail for all publish/reject actions |

## Configuration

All thresholds are tunable via environment variables without code changes.

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `TEXT_MODEL` | `qwen3:4b` | Text moderation model |
| `VISION_MODEL` | `qwen2.5vl:3b` | Image analysis model |
| `VISION_TIMEOUT` | `360` | Ollama request timeout in seconds |
| `AUTO_APPROVE_CONFIDENCE` | `0.85` | Min confidence to auto-approve |
| `AUTO_APPROVE_RISK_MAX` | `30` | Max risk score to auto-approve |
| `AUTO_REJECT_CONFIDENCE` | `0.80` | Min confidence to auto-reject |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `watcher` | Database name |
| `DB_USER` | `watcher` | Database user |
| `DB_PASSWORD_FILE` | -- | Path to password file (Vault secret) |
| `AUTH_USERNAME` | `admin` | Basic auth username for review queue |
| `AUTH_PASSWORD_FILE` | -- | Path to auth password file (Vault secret) |
| `PORT` | `9104` | Service port |
| `LOG_LEVEL` | `INFO` | Logging level |

## Security

| Control | Implementation |
|---------|---------------|
| SQL injection | Parameterized queries (psycopg2) |
| XSS | Content-Security-Policy headers |
| File upload | Max 5MB, JPEG/PNG whitelist |
| Password storage | PBKDF2-HMAC-SHA256 (100k iterations) |
| Container | `cap_drop: [ALL]`, `no-new-privileges:true` |
| Network | `network_mode: host` (AIXCL invariant) |
| Secrets | Vault-managed, mounted at `/run/secrets` |

## Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `watcher_listings_submitted_total` | Counter | Total listings submitted |
| `watcher_decisions_total{decision}` | Counter | Decisions by type (auto_approve/auto_reject/human_review) |
| `watcher_review_queue_depth` | Gauge | Listings pending human review |
| `watcher_moderation_latency_seconds` | Histogram | End-to-end moderation latency |
| `watcher_model_errors_total{stage}` | Counter | Model errors by stage |

## Hardware Requirements

| Resource | Minimum |
|----------|---------|
| CPU | 2 cores |
| RAM | 4 GB (service) + model memory |
| VRAM | 8 GB (qwen3:4b ~5 GB + qwen2.5vl:3b ~3 GB) |
| Storage | 500 MB for images |

## License

MIT -- Same as AIXCL platform.
