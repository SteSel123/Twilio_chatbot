# AppAssist — SMB WhatsApp Assistant Platform

Multi-tenant WhatsApp automation for small businesses. Pairs with the [AppAssist landing page](https://whatsapp-saas-landing-beryl.vercel.app) (`whatsapp-saas-landing` repo): signup → live setup preview → Twilio WhatsApp bot with docs, booking, payments, and admin tools.

**Stack:** Flask · Twilio · OpenAI / Ollama · Tavily · ChromaDB · Redis · SQLite / PostgreSQL · Stripe · Google Calendar · MCP

---

## Table of contents

1. [Features](#features)
2. [Project structure](#project-structure)
3. [Multi-tenancy](#multi-tenancy)
4. [Data & storage](#data--storage)
5. [HTTP API](#http-api)
6. [Setup page & onboarding](#setup-page--onboarding)
7. [Agent & LLM tools](#agent--llm-tools)
8. [Document pipeline & RAG](#document-pipeline--rag)
9. [Sample tenants](#sample-tenants)
10. [MCP server](#mcp-server)
11. [Pricing tiers](#pricing-tiers)
12. [Production (Docker)](#production-docker)
13. [Landing page integration](#landing-page-integration)
14. [WhatsApp commands](#whatsapp-commands)
15. [Testing](#testing)
16. [Environment variables](#environment-variables)
17. [Disclaimer](#disclaimer)

---

## Features

| Category | Capabilities |
|----------|-------------|
| **Reactive** | 24/7 WhatsApp replies, doc-trained Q&A (keyword + ChromaDB vector RAG), Tavily web search, Google Maps opening hours, lead scoring, human handoff (Slack / webhook / email) |
| **Proactive** | Appointment reminders, payment links, review requests, reschedule nudges, scheduled follow-ups (`platform/outbound.py`) |
| **Integrations** | External MCP servers (CRM / booking / inventory), Google Calendar OAuth + free/busy slots, Stripe checkout |
| **Media** | Voice transcription and image analysis on Growth tier (`platform/media_ai.py`) |
| **Onboarding** | Public signup from landing, tokenized setup URL, live WhatsApp-style preview with Google lookup + optional PDF/image upload |
| **Admin** | Analytics dashboard, profile CRUD, doc upload with sidecar indexing, outbound scheduler |
| **Compliance** | GDPR export/delete, consent gate, privacy/terms pages, PII redaction, prompt-injection guard |
| **Owner notifications** | Conversation summary e-mail via SMTP (or `.user_data/email_outbox/` fallback) |
| **MCP** | Same tool surface for WhatsApp agent, Cursor, OpenAI Remote MCP, web copilot |

---

## Project structure

```
Twilio_chatbot/
├── app.py                    # Flask app — routes, CORS, tenant resolution
├── agent.py                  # BusinessAgent — inbound message handler
├── config.py                 # Environment configuration
├── worker.py                 # RQ worker (whatsapp + outbound queues)
├── llm_client.py             # OpenAI / unified LLM calls
├── ollama_client.py          # Local Ollama fallback
├── doc_loader.py             # Load & keyword-search markdown docs
├── document_storage.py       # User-uploaded media on disk
├── memory.py                 # Conversation history (Redis or JSON files)
├── user_data.py              # SQLite UserDataStore (GDPR, case state)
├── twilio_client.py          # Per-tenant WhatsApp FROM numbers
├── prompts.py                # System prompt builder
├── patterns.py               # Intent / topic regex helpers
├── search.py                 # Tavily web search wrapper
│
├── platform/                 # Feature modules
│   ├── analytics.py          # Messages, leads, monthly usage
│   ├── auth.py               # Admin API key + browser session
│   ├── billing.py            # Stripe checkout + webhooks
│   ├── business_profile.py   # Tenant JSON profiles
│   ├── calendar.py           # Appointments + Google Calendar sync
│   ├── commercial_tone.py    # Setup preview tone (opening hours phrasing)
│   ├── consent.py            # Privacy consent gate
│   ├── cors.py               # Landing page CORS
│   ├── document_pipeline.py  # PDF extract + GPT-4o / Ollama vision
│   ├── feedback.py           # 1/2 rating after replies
│   ├── gdpr.py               # Export / erase user data
│   ├── google_maps.py        # Places API opening hours
│   ├── google_oauth.py       # Per-tenant Calendar OAuth
│   ├── handoff.py            # Human escalation
│   ├── industry_faqs.py      # Sector FAQ seeds for preview
│   ├── kaggle_faqs.py        # Kaggle-derived FAQ merge layer
│   ├── leads.py              # Lead qualification scoring
│   ├── llm_tools.py          # OpenAI function-calling loop
│   ├── mcp.py                # Tool registry + audit log
│   ├── mcp_external.py       # External MCP server proxy
│   ├── mcp_tools.py          # Shared tool implementations
│   ├── media_ai.py           # Whisper + vision for inbound media
│   ├── onboarding.py         # Signup, setup tokens, demo requests
│   ├── outbound.py           # Proactive message scheduler
│   ├── owner_email.py        # Owner summary e-mails
│   ├── payments.py           # Stripe payment links
│   ├── preview_conversation.py # Animated demo conversations
│   ├── prompt_guard.py       # Injection stripping
│   ├── queue.py              # Redis RQ enqueue
│   ├── rate_limit.py         # Ingress + public API limits
│   ├── redis_client.py       # Redis connection helper
│   ├── retention.py          # Tier-based data expiry
│   ├── setup_preview.py      # Setup page preview engine
│   ├── tenant.py             # Tenant resolution from Twilio `To`
│   ├── tiers.py              # Starter / Growth / Enterprise limits
│   └── …                     # events, health, i18n, observability, security
│
├── webhook/
│   ├── handler.py            # Async inbound processing + Twilio reply
│   ├── validator.py          # Twilio HMAC validation
│   └── idempotency.py        # Duplicate MessageSid guard
│
├── rag/
│   └── vector_store.py       # ChromaDB per-tenant collections
│
├── storage/
│   ├── __init__.py           # get_data_store() — SQLite or Postgres
│   └── postgres_store.py     # PostgreSQL UserDataStore
│
├── mcp_server/
│   └── __main__.py           # MCP stdio + Streamable HTTP server
│
├── businesses/               # One JSON profile per tenant
├── docs/                     # Knowledge base per tenant (docs_subdir)
├── templates/                # setup.html, admin.html, privacy, terms
├── static/                   # setup-i18n.js, demo SVG assets
└── tests/                    # 87 pytest tests (see [Testing](#testing))
```

---

## Multi-tenancy

Each business is a **tenant** identified by `tenant_id` (slug from signup or manual JSON filename).

| Mechanism | Location | Behavior |
|-----------|----------|----------|
| Profile | `businesses/{tenant_id}.json` | Name, industry, tier, tools, `docs_subdir`, optional `twilio_whatsapp_from` |
| Docs | `docs/{docs_subdir}/` | Markdown / text knowledge; indexed into ChromaDB on load |
| Twilio routing | `platform/tenant.py` | Maps inbound `To` WhatsApp number → tenant via `twilio_whatsapp_from` |
| Header override | `X-Tenant-Id` | Admin / MCP calls can target a specific tenant |
| Default | `DEFAULT_TENANT_ID` env | Fallback when no mapping matches |

**Per-tenant WhatsApp number:** set `"twilio_whatsapp_from": "whatsapp:+32..."` in the tenant JSON. Outbound replies use the matching FROM via `twilio_client.py`.

---

## Data & storage

### Runtime directories

| Path | Purpose |
|------|---------|
| `.user_data/` | All local SQLite databases, uploads, vector index, e-mail outbox |
| `.user_data/cases.db` | Primary user store (dev); Postgres when `DATABASE_URL` is set |
| `.user_data/analytics.db` | Message metrics, leads, monthly conversation counts |
| `.user_data/onboarding.db` | Setup tokens (7-day TTL), demo contact requests |
| `.user_data/appointments.db` | Booked appointments + calendar event IDs |
| `.user_data/outbound.db` | Scheduled proactive WhatsApp jobs |
| `.user_data/google_oauth.db` | OAuth refresh tokens + CSRF states |
| `.user_data/audit.db` | MCP / tool invocation audit log |
| `.user_data/vector_db/` | ChromaDB persistent collections (`business_docs_{tenant}`) |
| `.user_data/uploads/` | Customer-uploaded files |
| `.user_data/email_outbox/` | Owner e-mails when SMTP is not configured |
| `.conversation_memory/{tenant}/` | JSON chat history fallback (when Redis unavailable) |

### Redis (optional, recommended in production)

- Conversation memory keys: `mem:{tenant_id}:{user_id}` (7-day TTL)
- RQ job queues: `whatsapp`, `outbound`
- Rate limiting counters

### PostgreSQL (production)

When `DATABASE_URL` is set, `storage/postgres_store.py` replaces SQLite for the **user data store** with equivalent tables:

| Table | Columns (summary) |
|-------|-------------------|
| `users` | `user_id`, `created_at`, `expires_at` |
| `personal_data` | `user_id`, `field_name`, `field_value`, `updated_at` |
| `case_state` | `user_id`, `country`, `visa_type`, `process_name`, document lists, `next_steps` |
| `uploaded_files` | `user_id`, `filename`, `file_path`, `media_type`, `uploaded_at` |
| `user_consent` | `user_id`, `consented_at`, `privacy_version` |
| `reply_feedback` | `user_id`, `correlation_id`, `rating`, `created_at` |
| `subscriptions` | Stripe customer/subscription IDs, `tier`, `status` |

Other SQLite databases (analytics, onboarding, appointments, outbound, OAuth, audit) remain file-based unless extended separately.

### Data retention

Controlled by subscription tier (`platform/retention.py`, `platform/tiers.py`):

| Tier key | Default retention |
|----------|-------------------|
| `free` | 12 hours |
| `starter` / `standard` | 168 hours (7 days) |
| `growth` / `premium` | 720 hours (30 days) |

Override globally with `DATA_RETENTION_HOURS` or per-tier env vars (`RETENTION_HOURS_*`).

---

## HTTP API

### Health

| Route | Method | Description |
|-------|--------|-------------|
| `/health` | GET | Liveness + current tenant |
| `/health/ready` | GET | Readiness (Redis, DB, config checks) |

### Twilio webhooks

| Route | Method | Description |
|-------|--------|-------------|
| `/webhook` | POST | Inbound WhatsApp (HMAC validated, rate-limited, async via RQ or inline) |
| `/webhook/status` | POST | Delivery status callbacks |

### Public (landing page, CORS)

| Route | Method | Description |
|-------|--------|-------------|
| `/public/signup` | POST | Create tenant + setup URL + token |
| `/public/checkout` | POST | Signup + Stripe checkout session |
| `/public/demo` | POST | Book-a-demo / contact sales |

### Setup & onboarding

| Route | Method | Description |
|-------|--------|-------------|
| `/setup` | GET | Post-signup page (`?tenant=&token=`) — live preview + optional upload |
| `/setup/knowledge-preview` | POST | Google business lookup, PDF/image demo, or demo sample |
| `/onboard/google/start` | GET | Start Google Calendar OAuth |
| `/onboard/google/callback` | GET | OAuth callback |
| `/demo-site/<industry>` | GET | Minimal HTML demo sites for preview |

### Admin

Browser session via `/admin/login` or header `X-Admin-Key: <ADMIN_API_KEY>`.

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/login` | GET, POST | Admin key login |
| `/admin/logout` | GET, POST | Clear session |
| `/admin/dashboard` | GET | Analytics dashboard (HTML) |
| `/admin/analytics` | GET | JSON metrics |
| `/admin/business` | GET, POST | List / create tenants |
| `/admin/business/{id}` | GET, PUT, DELETE | Profile CRUD |
| `/admin/docs/upload` | POST | Upload knowledge files (+ pipeline reindex) |
| `/admin/outbound` | GET, POST | Schedule proactive messages |
| `/admin/gdpr/export/{user_id}` | GET | Admin GDPR export |
| `/admin/gdpr/erase/{user_id}` | DELETE | Admin GDPR erase |

### Billing & legal

| Route | Method | Description |
|-------|--------|-------------|
| `/billing/checkout` | POST | Stripe subscription checkout |
| `/billing/webhook` | POST | Stripe webhook handler |
| `/privacy` | GET | Privacy policy page |
| `/terms` | GET | Terms page |

### Other

| Route | Method | Description |
|-------|--------|-------------|
| `/iot/webhook` | POST | IoT device payload handler |
| `/` | GET | Index / info page |

---

## Setup page & onboarding

Flow after landing signup:

1. `POST /public/signup` creates `businesses/{slug}.json`, seeds docs, stores setup token in `onboarding.db`.
2. User opens `/setup?tenant={slug}&token=…`.
3. Page auto-runs Google Places lookup (if `GOOGLE_MAPS_API_KEY` set) and plays an animated WhatsApp conversation (`platform/setup_preview.py`, `platform/preview_conversation.py`).
4. Optional upload: JPG, PNG, WebP, or PDF (max 8 MB) — extracted via `document_pipeline.py` (pypdf + GPT-4o vision).
5. UI matches landing page: shared navbar, i18n (NL, EN, FR, ES, IT, DE via `static/setup-i18n.js` + `localStorage`), mobile-first chat demo layout.

Commercial tone for opening hours in preview uses `platform/commercial_tone.py` (e.g. *"Ja, wij bij {bedrijfsnaam} zijn vandaag open van …"*).

---

## Agent & LLM tools

`agent.py` (`BusinessAgent.handle_message`) pipeline:

1. Consent gate → GDPR commands → handoff → feedback (1/2) → reset
2. Tier check (monthly conversation limit, media allowed)
3. Doc search (vector RAG + keyword fallback) + optional Google Maps hours + web search
4. LLM reply via `llm_client.py`; when `LLM_PROVIDER=openai` and API key present, **function calling** via `platform/llm_tools.py`

| Tool | Purpose |
|------|---------|
| `listAvailableSlots` | Free slots on a date (Google Calendar free/busy) |
| `bookAppointment` | Book + sync calendar |
| `qualifyLead` | Interest / budget / urgency score |
| `createPaymentLink` | Stripe payment link (euro cents) |
| `searchBusinessDocs` | Internal knowledge search |
| `getCustomerContext` | Stored customer fields |
| `webSearch` | Tavily search with business context |
| `listExternalIntegrations` | Configured external MCP servers |
| `callExternalTool` | Proxy to tenant MCP plugin |
| `scheduleReminder` | Queue proactive outbound job |

Special commands: `RESCHEDULE` triggers outbound reschedule flow; owner summary e-mail sent on qualifying conversations (`platform/owner_email.py`).

---

## Document pipeline & RAG

**Ingestion** (`platform/document_pipeline.py`):

- Text: `.txt`, `.md`, `.json` — read directly
- PDF: pypdf text extract; if sparse, rasterize pages (PyMuPDF) → GPT-4o / Ollama vision
- Images: GPT-4o / Ollama vision with business-document prompt

**Indexing** (`rag/vector_store.py`):

- ChromaDB persistent store under `.user_data/vector_db/`
- Per-tenant collection; chunks ~800 chars; reindexed on admin upload and agent reload
- Fallback: keyword search in `doc_loader.py` when vector RAG disabled or empty

**Admin upload** writes source file + optional `.md` sidecar under `docs/{tenant}/`.

---

## Sample tenants

### Built-in demos (recommended for local dev)

| Tenant | Industry | Tier | Profile | Docs |
|--------|----------|------|---------|------|
| `default` | General | Starter | `businesses/default.json` | `docs/default/` |
| `salon` | Beauty salon | Growth | `businesses/salon.json` | `docs/salon/` |
| `restaurant` | Restaurant | Starter | `businesses/restaurant.json` | `docs/restaurant/` |

```powershell
# Demo the salon profile
$env:DEFAULT_TENANT_ID = "salon"
python app.py
```

### Signup-created tenants

Created via `/public/signup` (landing page). Examples in repo from testing: `dreamland`, `leonidas`, `test-cafe-oauth*`, `test-with-email*`. Each has matching `docs/{tenant_id}/`.

### Add a tenant manually

1. Copy `businesses/default.json` → `businesses/my-shop.json` (set `tenant_id` fields).
2. Add markdown under `docs/my-shop/` and set `"docs_subdir": "my-shop"`.
3. Optionally set `"twilio_whatsapp_from"` for dedicated WhatsApp number.
4. Set `"subscription_tier"`: `starter`, `growth`, or `enterprise`.

---

## MCP server

```powershell
# Cursor (stdio)
python -m mcp_server --transport stdio

# OpenAI Remote MCP / web copilot (HTTP)
$env:MCP_API_KEY = "your-secret"
python -m mcp_server --transport streamable-http --port 8000
```

Registered tools (see `mcp_server/__main__.py`): `search_business_docs`, `get_customer_context`, `web_search`, `list_external_integrations`, `call_external_tool`, `qualify_lead`, `book_appointment`, `list_available_slots`, `create_payment_link`, `schedule_reminder`.

Legacy aliases still work: `searchImmigrationDocs`, `getUserCaseStatus`.

Docker Compose runs MCP on port **8000** alongside the web app.

---

## Pricing tiers

Enforced in `platform/tiers.py` via `subscription_tier` in the business profile:

| Tier | Conversations/mo | Numbers | Voice & images | Web search |
|------|------------------|---------|----------------|------------|
| Free (trial) | 50 | 1 | No | Yes |
| Starter | 400 | 1 | No | Yes |
| Growth | Unlimited | 3 | Yes | Yes |
| Enterprise | Unlimited | 10 | Yes | Yes |

Legacy aliases: `standard` → Starter limits, `premium` → Growth limits.

---

## Production (Docker)

```powershell
docker compose up -d
```

| Service | Role |
|---------|------|
| `web` | Flask app on port 5000 |
| `worker` | RQ worker — inbound messages + outbound scheduler |
| `mcp` | MCP Streamable HTTP on port 8000 |
| `redis` | Queues + memory + rate limits |
| `postgres` | PostgreSQL 16 (`chatbot` database) |

Compose sets `ENV=production`, `USE_REDIS_QUEUE=1`, and `DATABASE_URL=postgresql://postgres:postgres@postgres:5432/chatbot`.

---

## Landing page integration

Landing repo: `whatsapp-saas-landing` (Vite/React, deployed to Vercel).

1. Deploy landing — set `VITE_API_URL=https://your-backend-domain.com`.
2. Backend `.env`:
   ```
   LANDING_ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:5173
   LANDING_URL=https://your-app.vercel.app
   GOOGLE_OAUTH_REDIRECT_URI=https://your-backend-domain.com/onboard/google/callback
   ```
3. Restart backend so CORS accepts signup from the live landing page.

Setup page navbar links back to `LANDING_URL` (defaults to Vercel deploy if not set).

---

## WhatsApp commands

| Input | Action |
|-------|--------|
| `YES` | Accept privacy notice |
| `reset` / `clear` | Clear conversation memory |
| `export my data` | GDPR export |
| `delete my data` | GDPR erase |
| `speak to human` | Staff handoff (Slack / e-mail / webhook) |
| `1` / `2` | Rate last bot reply |
| `RESCHEDULE` | Trigger reschedule outbound flow |

---

## Testing

**87 tests** across 16 files. Run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest tests/ -v
```

| File | Tests | Coverage |
|------|-------|----------|
| `test_agent_google_maps.py` | 2 | Agent injects Google Maps context for hours questions |
| `test_ai_safety.py` | 6 | Prompt injection stripping, consent, i18n, handoff triggers |
| `test_business_profile.py` | 3 | Load/save tenant JSON profiles |
| `test_commercial_tone.py` | 6 | Opening-hours phrasing and soft CTAs in preview |
| `test_google_maps.py` | 6 | Places API formatting, weekday hours, agent context |
| `test_industry_faqs.py` | 6 | Sector FAQ picker (restaurant, retail, salon, energy) |
| `test_kaggle_faqs.py` | 4 | Kaggle FAQ merge for B2B verticals |
| `test_landing_features.py` | 10 | Leads, tiers, analytics, calendar, outbound, MCP registry |
| `test_mcp_tools.py` | 3 | Doc search, customer context, external integrations |
| `test_onboarding.py` | 5 | Signup, tokens, demo requests, setup URL format |
| `test_owner_email.py` | 2 | Owner summary e-mail formatting + outbox fallback |
| `test_platform.py` | 5 | Intent detection, prompt guard, PII redaction, rate limits |
| `test_preview_conversation.py` | 3 | Multi-turn preview conversations |
| `test_setup_preview.py` | 21 | Upload, Google lookup, demo samples, hallucination guards |
| `test_tenant_twilio.py` | 1 | Resolve tenant from Twilio `To` number |
| `test_webhook_e2e.py` | 7 | Webhook TwiML, idempotency, agent consent + small talk |

Shared fixtures: `tests/conftest.py`.

### Kaggle sector FAQs (B2B verticals)

For **industrial**, **construction**, **logistics**, **financial** and **property**, extra FAQ seeds come from `data/kaggle_faqs.json` (merged at runtime via `platform/kaggle_faqs.py`). The repo ships a curated snapshot so preview and signup seed docs work without Kaggle credentials.

To refresh from Kaggle:

```powershell
pip install kaggle
# Set KAGGLE_USERNAME + KAGGLE_KEY, or place ~/.kaggle/kaggle.json
python scripts/kaggle_import.py
python scripts/kaggle_import.py --vertical logistics
python scripts/kaggle_import.py --dry-run
```

Dataset mapping lives in `data/kaggle_sources.json` (maintenance orders, fleet maintenance, customer-support tickets). Imported entries are deduped and capped per vertical; hand-curated entries in `data/kaggle_faqs.json` are kept when using `--merge` (default).

---

## Environment variables

Copy `.env.example` to `.env`. Key groups:

| Group | Variables |
|-------|-----------|
| **Twilio** | `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY`, `TWILIO_API_SECRET`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `WEBHOOK_BASE_URL` |
| **Security** | `ENV`, `ENFORCE_HTTPS`, `ENFORCE_TWILIO_HMAC`, `ADMIN_API_KEY`, `FLASK_SECRET_KEY` |
| **Multi-tenant** | `DEFAULT_TENANT_ID`, `DEFAULT_REGION` |
| **Redis / queue** | `REDIS_URL`, `USE_REDIS_QUEUE` |
| **Database** | `DATABASE_URL` (empty = SQLite dev) |
| **LLM** | `LLM_PROVIDER` (`ollama` / `openai`), `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_VISION_MODEL`, Ollama vars |
| **Search & maps** | `TAVILY_API_KEY`, `GOOGLE_MAPS_API_KEY` |
| **RAG** | `USE_VECTOR_RAG` |
| **Stripe** | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*` |
| **Google Calendar** | `GOOGLE_OAUTH_*`, `GOOGLE_CALENDAR_CREDENTIALS_JSON` |
| **Landing** | `LANDING_ALLOWED_ORIGINS`, `LANDING_URL` |
| **E-mail** | `SMTP_*`, `NOTIFY_FROM_EMAIL`, `HANDOFF_EMAIL` |
| **MCP** | `MCP_HOST`, `MCP_PORT`, `MCP_API_KEY`, `MCP_TRANSPORT` |
| **Observability** | `SENTRY_DSN`, `APP_VERSION` |

Optional: `AZURE_KEY_VAULT_URL` for secret resolution via `platform/secrets.py`.  
Optional Kaggle import: `KAGGLE_USERNAME`, `KAGGLE_KEY` (or `~/.kaggle/kaggle.json`).

---

## Quick start (local)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env — at minimum set DEFAULT_TENANT_ID=salon for demo
python app.py
```

Open `http://localhost:5000/admin/dashboard` (after setting `ADMIN_API_KEY` and logging in).

For Ollama locally: install Ollama, pull `llama3`, set `LLM_PROVIDER=ollama`. For production-like behavior: set `OPENAI_API_KEY` and `LLM_PROVIDER=openai`.

---

## Disclaimer

AI-generated customer service — businesses should verify prices, availability, and policies before relying on automated replies.
