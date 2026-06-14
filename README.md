# Watcher - AI-Powered Marketplace Moderation

AI-assisted listing moderation for e-commerce platforms. Built for the AIXCL BYO app framework.

## Overview

Watcher provides a two-stage AI moderation pipeline for marketplace listings:

1. **Text moderation** via Ollama (Qwen2.5 7B)
2. **Image moderation** via vision model (Qwen2.5-VL 3B) + text classifier

Decisions are stored in PostgreSQL. Uncertain listings enter a human review queue.

## Architecture

```
User submits listing
        |
        v
+--------------------------------------+
|  Watcher Moderation Service          |
|  FastAPI + React (port 9104)        |
|                                      |
|  /api/submit    → Text + Image      |
|  /api/review    → Human queue       |
|  /              → React SPA         |
+--------------------------------------+
        |
   +----+----+
   |         |
   v         v
Text       Image
(Qwen2.5 7B) (Qwen2.5-VL 3B)
   |         |
   +----+----+
        |
   +----+----+
   |         |
   v         v
APPROVE   REVIEW/REJECT
(auto)    (human review)
```

## Platform Integration

Watcher is fully integrated with AIXCL platform services:

| Service | Integration |
|---------|-------------|
| **PostgreSQL** | Shared platform instance (`aixcl` DB, `watcher` schema) |
| **Vault** | Secrets via `/run/secrets` (database password, auth credentials) |
| **Redis** | Dedicated `watcher-redis` container for Medusa event bus |
| **Ollama** | `localhost:11434` via host networking |
| **Prometheus** | Metrics on `:9104/api/metrics` |
| **Grafana** | Dashboard at `grafana/dashboards/watcher-moderation.json` |

## File Structure

```
apps/watcher/
├── app.yaml                          # AIXCL manifest
├── docker-compose.yml                # Watcher + Redis services
├── README.md                         # This file
├── grafana/
│   └── dashboards/
│       └── watcher-moderation.json   # Grafana dashboard
├── ui/                               # React frontend (Vite)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── components/
│       │   ├── SubmitForm.jsx
│       │   ├── ReviewQueue.jsx
│       │   ├── StatsPanel.jsx
│       │   └── LoginModal.jsx
│       └── api/
│           └── client.js
└── watcher/                          # FastAPI backend
    ├── Dockerfile                    # Multi-stage (UI + Python build)
    ├── requirements.txt
    ├── config.py                     # Settings from env/Vault
    ├── auth.py                       # Password hashing + basic auth
    ├── db.py                         # PostgreSQL schema + CRUD
    ├── models.py                     # Pydantic models
    ├── moderation.py                 # LLM pipeline
    └── main.py                       # FastAPI app + routes
```

## Quick Start

### Prerequisites

- AIXCL platform running (`./aixcl stack start --profile sys`)
- Vault initialized and unsealed
- Models pulled in Ollama (names are case-sensitive, match `ollama list`):
  ```bash
  ollama pull qwen2.5:7b      # text moderation (TEXT_MODEL)
  ollama pull qwen2.5VL:3B    # image analysis (VISION_MODEL)
  ```

### 1. Build and Start

```bash
# From AIXCL repo root
./aixcl app build watcher
./aixcl app start watcher
```

No manual secret or database setup is required. The `provision:` section
of `app.yaml` declares what Watcher needs; on every start the platform
idempotently:

- generates the secrets in Vault KV (`kv/apps/watcher`)
- renders them into the per-app volume `aixcl-app-watcher-secrets`
  (`/run/secrets/watcher-<name>` inside the container)
- creates the `watcher` PostgreSQL role and database

To see the generated credentials (the seeded `user` and `admin` UI
accounts use `user-password` and `admin-password`):

```bash
./aixcl app secrets watcher
```

### 2. Access the UI

Open browser: http://localhost:9104

### 3. Submit a Listing

Fill the form with:
- User ID: any string (register first at `/api/register`)
- Title: "Brand new iPhone 15 Pro Max"
- Description: "512GB - $200 only! Contact on WhatsApp +1234567890"
- Price: 200.00
- Images: optional

### 4. Review Queue

Navigate to "Review Queue" to see AI-flagged listings. Approve or reject with one click.

### 5. Check Stats

Navigate to "Stats" for moderation metrics.

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health` | GET | No | Service health |
| `/api/metrics` | GET | No | Prometheus metrics |
| `/api/register` | POST | No | User registration |
| `/api/login` | POST | No | User login |
| `/api/submit` | POST | No | Submit listing for moderation |
| `/api/review-queue` | GET | No | List human review queue |
| `/api/review/{id}` | POST | No | Human moderator action |
| `/api/stats` | GET | No | Moderation statistics |
| `/api/images/{id}` | GET | No | Serve listing image |

## Database Schema

All tables in `watcher` schema within the platform `aixcl` database:

- `users` — Registered users
- `listings` — Product listings
- `listing_images` — Uploaded images (BYTEA)
- `listing_moderation` — AI moderation decisions
- `human_review_queue` — Pending human reviews
- `listing_publish_log` — Audit log

## Configuration

| Variable | Default | Source |
|----------|---------|--------|
| `OLLAMA_URL` | `http://localhost:11434` | env |
| `DB_HOST` | `localhost` | env |
| `DB_PORT` | `5432` | env |
| `DB_NAME` | `aixcl` | env |
| `DB_USER` | `watcher` | env |
| `DB_PASSWORD` | — | Vault `/run/secrets/watcher-db-password` |
| `AUTH_USERNAME` | `admin` | env |
| `AUTH_PASSWORD` | — | Vault `/run/secrets/watcher-auth-password` |
| `TEXT_MODEL` | `qwen3:4b` | env |
| `VISION_MODEL` | `qwen2.5-vl:3b` | env |
| `AUTO_APPROVE_THRESHOLD` | `0.95` | env |
| `REVIEW_THRESHOLD` | `0.70` | env |
| `PORT` | `9104` | env |

## Security

| Control | Implementation |
|---------|---------------|
| SQL Injection | Parameterized queries (psycopg2) |
| XSS | React auto-escaping + CSP headers |
| File Upload | Max 5MB, whitelist MIME types |
| Rate Limiting | 30 requests/minute per IP |
| Auth | Basic auth for review queue (optional) |
| Password Storage | PBKDF2-HMAC-SHA256 |
| Container | `cap_drop: [ALL]`, `no-new-privileges:true` |
| Network | `network_mode: host` (AIXCL invariant) |
| Secrets | Vault-managed, mounted at `/run/secrets` |

## Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `watcher_listings_submitted_total` | Counter | Total listings submitted |
| `watcher_users_registered_total` | Counter | Total users registered |
| `watcher_decisions_total` | Counter | Decisions by type |
| `watcher_review_queue_depth` | Gauge | Queue depth |
| `watcher_moderation_latency_seconds` | Histogram | Moderation latency |
| `watcher_model_errors_total` | Counter | Model errors by stage |

## Hardware Requirements

- **CPU**: 2+ cores
- **RAM**: 4GB for service + models
- **VRAM**: 8GB (Qwen2.5 7B ~5GB + Qwen2.5-VL 3B ~3GB)
- **Storage**: 500MB for images + logs

## License

MIT — Same as AIXCL platform.
