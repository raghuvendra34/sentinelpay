> **Blog post:** _Designing Idempotent Payment Microservices & Guardrailed LangGraph Dispute Agents_ — [add your Medium / Dev.to link here]

<h1 align="center">SentinelPay</h1>

<p align="center">
  Fault-tolerant payment microservices with a stateful <b>LangGraph</b> agent that resolves customer disputes,<br>
  where the AI scores risk and plain code decides who gets their money back.
</p>

<p align="center">
  <img alt="tests" src="https://img.shields.io/badge/tests-11%20passing-2D7048">
  <img alt="python" src="https://img.shields.io/badge/python-3.11-1D5C5A">
  <img alt="fastapi" src="https://img.shields.io/badge/FastAPI-microservices-1D5C5A">
  <img alt="postgres" src="https://img.shields.io/badge/PostgreSQL-16-1D5C5A">
  <img alt="redis" src="https://img.shields.io/badge/Redis-Streams-A63A2E">
  <img alt="langgraph" src="https://img.shields.io/badge/LangGraph-agent-16252B">
  <img alt="nextjs" src="https://img.shields.io/badge/Next.js-14%20%2B%20TypeScript-16252B">
</p>

<p align="center">
  <img src="docs/console.png" alt="SentinelPay console: T-account balances and the live ledger journal" width="900">
</p>

---

## Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Design decisions](#design-decisions)
- [Quick start](#quick-start)
- [Try it](#try-it)
- [The dispute agent](#the-dispute-agent)
- [API reference](#api-reference)
- [Data model](#data-model)
- [Testing and verification](#testing-and-verification)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Run without Docker](#run-without-docker-zero-cost-cloud-services)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)

## What it does

SentinelPay moves money between accounts and handles the disputes that follow. Three guarantees drive every design choice:

| Guarantee | How it is enforced |
|---|---|
| **Money is never created, lost or double-charged** | Double-entry ledger inside one PostgreSQL transaction; row locks; `Idempotency-Key` on every transfer |
| **A retry or a burst cannot hurt the system** | Sliding-window rate limiter on Redis; event queue with retries and a dead-letter stream |
| **An AI model never decides a refund** | The LLM returns a risk score only; a deterministic rule engine makes the decision and the full reasoning trace is stored |

<table>
<tr>
<td width="50%"><img src="docs/inspector.png" alt="Agent reasoning inspector showing an escalated dispute, risk bar and guardrail checks"></td>
<td width="50%"><b>Agent reasoning inspector.</b> Every resolved dispute shows its risk score against the 0.35 auto-credit limit, the three guardrail checks, and an expandable input/output trace for each LangGraph node.</td>
</tr>
</table>

## Architecture

```mermaid
flowchart LR
  C["Console<br/>Next.js :3000"] -->|"REST + JWT + Idempotency-Key"| G["API Gateway<br/>FastAPI :8001"]
  G -->|"sync REST"| L["Ledger Service<br/>FastAPI :8002"]
  G -->|"rate limit + XADD"| R[("Redis<br/>sorted sets + Streams<br/>tx_events, tx_dlq")]
  R -->|"XREADGROUP"| W["Agent Worker<br/>LangGraph"]
  G -.->|"idempotency lookup"| P[("PostgreSQL 16")]
  L --> P
  W --> P
```

| Service | Port | Responsibility |
|---|---|---|
| **API Gateway** | 8001 | Verifies the JWT, applies the per-account rate limit, checks the `Idempotency-Key`, forwards transfers, publishes events |
| **Ledger Service** | 8002 | The only service that moves money. Atomic double-entry bookkeeping with row-level locks |
| **Agent Worker** | none | Consumes `tx_events`, runs the 3-node LangGraph workflow, writes the resolution and reasoning trace |
| **Console** | 3000 | Transfer simulator, live ledger journal, agent reasoning inspector |
| **PostgreSQL / Redis** | 5433 / 6379 | System of record / rate limits and event streams |

### A transfer, step by step

```mermaid
sequenceDiagram
  participant C as Console
  participant G as Gateway
  participant R as Redis
  participant L as Ledger
  participant P as PostgreSQL
  C->>G: POST /api/v1/transfers (JWT, Idempotency-Key)
  G->>R: sliding-window check
  opt over the limit
    G-->>C: 429
  end
  G->>P: has this key been used?
  opt seen before
    G-->>C: 200 stored transaction (replayed)
  end
  G->>L: POST /internal/transfers
  L->>P: BEGIN, lock both accounts in ID order
  L->>P: move balances, insert transaction, DEBIT + CREDIT, COMMIT
  L-->>G: 201 transaction
  G->>R: XADD tx_events TX_CREATED (and DISPUTE_OPENED if $500+)
  G-->>C: 201
```

## Design decisions

<details open>
<summary><b>Double-entry ledger with deterministic row locking</b></summary>

Every transfer runs in one SQL transaction. The ledger sorts the two account IDs and runs `SELECT ... WHERE account_id = ANY(...) ORDER BY account_id FOR UPDATE`, so two opposite transfers (A to B and B to A) always lock in the same order and cannot deadlock. Balances are `BIGINT` cents, never floats, and the schema enforces `balance_cents >= 0`. Each transfer writes one `DEBIT` and one `CREDIT` entry. Raising `HTTPException` inside the transaction rolls everything back.
</details>

<details>
<summary><b>Idempotency in two layers</b></summary>

The gateway returns the stored transaction for a key it has already seen. The ledger checks the key again after taking the account locks, and a `UNIQUE` constraint on `idempotency_key` is the final backstop, so two identical requests arriving at the same instant still produce exactly one charge.
</details>

<details>
<summary><b>Sliding-window log rate limiter (and a bug that was fixed)</b></summary>

Each account has a Redis sorted set of request timestamps: trim entries older than 60 seconds, add the new one, count, allow up to 10. The first version used the millisecond timestamp as the set member, so two requests in the same millisecond overwrote each other and the count came out too low. Each member is now `timestamp:random-suffix`. A regression test with an in-memory fake Redis proves 12 same-millisecond requests now give 10 allowed and 2 blocked, where the original allowed all 12.
</details>

<details>
<summary><b>Events, retries and a dead-letter queue</b></summary>

Slow work never blocks a payment. The gateway publishes to the Redis Stream `tx_events`; the worker reads through a consumer group, retries a failed dispute 3 times with exponential backoff (2 s, 4 s), then writes the payload to `tx_dlq` so no dispute is silently dropped. Unacknowledged messages from a crashed worker are replayed on restart.
</details>

<details>
<summary><b>The AI never decides</b></summary>

The model classifies a dispute and returns `{risk_score, category, explanation}` in a strict Pydantic schema. The refund decision is a pure function in `services/agent_worker/guardrails.py` with its own unit tests. The customer's dispute text is passed to the model as untrusted input. Resolution is idempotent: a re-delivered event cannot issue a second credit.
</details>

## Quick start

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) running, and a free [Groq API key](https://console.groq.com/keys). No local Python or Node install is needed.

```bash
git clone https://github.com/YOUR_USERNAME/sentinelpay.git
cd sentinelpay

# 1. Config
cp .env.example .env
sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=$(openssl rand -hex 32)|" .env
# open .env and set LLM_API_KEY=<your Groq key>

# 2. Mint a login token for the console (signed with your JWT_SECRET)
echo "DEMO_JWT=$(docker run --rm --env-file .env -v "$PWD":/app -w /app python:3.11-slim \
  sh -c 'pip install -q python-jose && python infra/mint_token.py' | tail -n 1)" >> .env

# 3. Build and start everything
docker compose up --build
```

Open **http://localhost:3000**. The first build takes a few minutes.

| URL | What |
|---|---|
| http://localhost:3000 | Console |
| http://localhost:8001/docs | Gateway API (Swagger) |
| http://localhost:8002/docs | Ledger API (Swagger) |
| `localhost:5433` | PostgreSQL (user, password and database are all `sentinel`/`sentinelpay`). Published on 5433 so it never clashes with a local Postgres on 5432 |

Stop with `docker compose down`; add `-v` to also wipe the database.

> Change `JWT_SECRET` later and you must remint `DEMO_JWT` and rebuild the console (`docker compose up --build`), because the token is baked into the frontend at build time.

## Try it

Two accounts are seeded with $1,000.00 each: **Alice Nguyen** and **Ben Carter**.

1. **Send a transfer.** Pick a sender and an amount and click **Send transfer**. A new row inks into the journal: the sender's debit on the left, the receiver's credit on the right.
2. **Prove idempotency.** Click **Test duplicate retry**. The same `Idempotency-Key` is sent twice: the first call returns `201 created`, the second `200 replayed`, and the balance changes once.
3. **Raise a dispute.** Click **Raise dispute** on a completed row, choose a reason and submit. The row shows *Agent reviewing*, then *Credited back* or *With ops* within a few seconds.
4. **Read the reasoning.** Click the row. The inspector shows the risk score against the 0.35 limit, the three guardrail checks, and each node's input and output.
5. **Trigger auto-flagging.** Send **$500 or more**. The transfer is marked `FLAGGED` and goes to the agent without anyone raising a dispute.
6. **Trip the rate limiter.** Send more than 10 requests within a minute from one account and the gateway answers `429`.

## The dispute agent

```mermaid
flowchart LR
  E["DISPUTE_OPENED event"] --> N1["1. retrieve_context<br/>transaction, last 10 transfers,<br/>30-day mean, prior disputes"]
  N1 --> N2["2. evaluate_policy<br/>deviation computed in code,<br/>LLM returns risk score + category"]
  N2 --> N3{"3. guardrails, in code<br/>amount ≤ $100<br/>risk ≤ 0.35<br/>no prior disputes"}
  N3 -->|"all three true"| A["AUTO_CREDIT_APPROVED<br/>provisional credit entry"]
  N3 -->|"otherwise"| O["ESCALATED_TO_OPS<br/>human review"]
```

| Check | Rule |
|---|---|
| Amount | `amount_cents <= 10000` ($100) |
| Risk | `risk_score <= 0.35` |
| History | `prior_disputes == 0` |

All three must pass for `AUTO_CREDIT_APPROVED`; anything else is `ESCALATED_TO_OPS`. Both limits are inclusive and covered by a parametrised test matrix.

**Conventions worth knowing**

- **Provisional credit** is a single `CREDIT` ledger entry and balance increase for the disputing sender. It is bank-funded, so the receiver is not debited, and the transaction becomes `DISPUTE_CREDITED`. An escalation sets `DISPUTE_ESCALATED`.
- **Confidence** is `1 - risk` for an approval and `risk` for an escalation. An escalation forced by a hard rule on a low-risk transfer therefore scores low, which tells the reviewer the call is theirs.
- **One resolution per transaction.** A second event for an already-resolved transaction is acknowledged and ignored.

### Real run

A $25 transfer sent seconds after two others, disputed with *"I did not authorise this payment"*:

| Step | Result |
|---|---|
| Context | amount $25.00, 0 prior disputes, 30-day average $262.00 |
| Model | risk **0.45**, category *velocity anomaly* |
| Guardrails | amount ok, **risk 0.45 > 0.35 (fail)**, no prior disputes ok |
| Decision | `ESCALATED_TO_OPS`, confidence 0.45, transaction `DISPUTE_ESCALATED` |

The model's written explanation described the burst as three transfers of $25. One of them was actually $499. The decision was still correct, because the rule engine reads numbers, not prose. This is the reason the model is not allowed to decide.

## API reference

All `/api/v1` routes need `Authorization: Bearer <JWT>` (HS256, signed with `JWT_SECRET`).

| Method | Path | Success | Notes |
|---|---|---|---|
| `POST` | `/api/v1/transfers` | `201` created, `200` replayed | Requires an `Idempotency-Key` header |
| `POST` | `/api/v1/disputes` | `202` accepted | Body `{tx_id, reason}`; queues `DISPUTE_OPENED` |
| `GET` | `/api/v1/accounts/{id}/history` | `200` | Balance plus the 15 most recent transactions with any dispute resolution |
| `GET` | `/health` | `200` | Each service |

Internal (ledger only, not exposed to clients): `POST /internal/transfers`, `GET /internal/accounts/{id}/history`.

```bash
TOKEN=$(grep '^DEMO_JWT=' .env | cut -d= -f2-)
KEY=$(uuidgen)

# Run this twice: the first call returns 201, the second returns 200 with the same tx_id
curl -s -X POST http://localhost:8001/api/v1/transfers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "sender_id":   "11111111-1111-4111-8111-111111111111",
        "receiver_id": "22222222-2222-4222-8222-222222222222",
        "amount_cents": 2500,
        "merchant_cat": "GROCERIES"
      }'
```

| Status | `detail` | Meaning |
|---|---|---|
| `400` | `INSUFFICIENT_FUNDS` | Sender balance is lower than the amount |
| `400` | `SAME_ACCOUNT` / `ACCOUNT_NOT_ACTIVE` | Invalid transfer |
| `401` | `MISSING_TOKEN` / `INVALID_TOKEN` | Bad or absent JWT |
| `404` | `ACCOUNT_NOT_FOUND` / `TRANSACTION_NOT_FOUND` | Unknown ID |
| `429` | `RATE_LIMIT_EXCEEDED` | More than 10 requests in 60 s for this account (`Retry-After: 60`) |
| `503` | `LEDGER_UNAVAILABLE` | Gateway cannot reach the ledger |

## Data model

```
accounts            account_id · owner_name · email · balance_cents (>= 0) · status
transactions        tx_id · idempotency_key (unique) · sender_id · receiver_id · amount_cents (> 0)
                    merchant_cat · status · risk_score · created_at
ledger_entries      entry_id · tx_id · account_id · entry_type (DEBIT | CREDIT) · amount_cents
dispute_resolutions dispute_id · tx_id · reason · decision · confidence · reasoning_trace (JSONB)
```

Transaction `status` moves through `COMPLETED` or `FLAGGED` and then `DISPUTE_CREDITED` or `DISPUTE_ESCALATED`.

`infra/schema.sql` ends with idempotent `CREATE INDEX IF NOT EXISTS` statements for the hot paths: transaction history by sender and receiver with `created_at DESC`, ledger entries by `tx_id` and account, and the latest dispute per transaction. On an existing database you can run just that block.

## Testing and verification

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pytest httpx "sqlalchemy[asyncio]" asyncpg python-jose python-dotenv

# Point the tests at the Docker database (note the 5433 host port)
# .env:  DATABASE_URL=postgresql+asyncpg://sentinel:sentinel@localhost:5433/sentinelpay

pytest -v        # with `docker compose up` running
```

Each integration test creates its own fresh accounts, so results do not depend on earlier runs.

| Check | Test | Result |
|---|---|---|
| Double-spend: 5 simultaneous $400 transfers from $1,000 → 2 succeed, 3 `INSUFFICIENT_FUNDS`, final balance $200 | `tests/test_concurrency.py` | ✅ 2 succeeded, 3 `INSUFFICIENT_FUNDS`, balance $200.00 |
| Idempotency: same key twice → one transaction, one DEBIT + one CREDIT | `tests/test_idempotency.py` | ✅ replayed on retry, 1 transaction, 1 DEBIT + 1 CREDIT |
| Rate limit: requests 11 and 12 → 429 | `tests/test_rate_limit.py` | ✅ requests 1–10 returned 201, 11–12 returned 429 |
| Guardrail matrix, inclusive limits and confidence bounds (no services needed) | `tests/test_guardrails.py` | ✅ 7 cases |
| Limiter counts same-millisecond requests (in-memory fake Redis, no services needed) | `tests/test_rate_limiter_unit.py` | ✅ 12 requests, 10 allowed, 2 blocked |

Full output: [`tests/verification_output.txt`](tests/verification_output.txt) (`11 passed`).

## Configuration

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Purpose | Default |
|---|---|---|
| `JWT_SECRET` | Signs and verifies HS256 tokens | none (set it) |
| `DEMO_JWT` | Token baked into the console at build time | none (mint it) |
| `LLM_API_KEY` | Groq (or Gemini) API key | none |
| `LLM_PROVIDER` | `groq` or `gemini` | `groq` |
| `LLM_MODEL` | Model ID. Check your provider's deprecation page before pinning | `openai/gpt-oss-120b` |
| `DATABASE_URL` | Any `postgres://` or `postgresql://` string works; it is converted to `postgresql+asyncpg://` and Neon's `sslmode=require` is translated | local Postgres |
| `REDIS_URL` | `redis://` or Upstash `rediss://` | `redis://localhost:6379/0` |
| `LEDGER_URL` | Where the gateway reaches the ledger | `http://localhost:8002` |
| `ALLOWED_ORIGINS` | Comma-separated browser origins allowed by CORS | `http://localhost:3000` |
| `NEXT_PUBLIC_API_URL` | Gateway URL used by the console | `http://localhost:8001` |
| `PORT` | If set, the worker opens a health endpoint (for hosts that only run web services) | unset |

Docker Compose sets the container-internal database and Redis addresses itself, so the `DATABASE_URL` and `REDIS_URL` in `.env` only matter for the tests and for running outside Docker.

## Project layout

```
sentinelpay/
├── services/
│   ├── gateway/         main.py · rate_limiter.py · config.py        Auth, rate limit, idempotency, events
│   ├── ledger/          main.py · config.py                          ACID double-entry transfers
│   └── agent_worker/    graph.py · consumer.py · guardrails.py       LangGraph agent, stream consumer, rules
├── frontend/            app/ · components/ · lib/ · Dockerfile       Next.js 14 + TypeScript + Tailwind console
├── infra/               schema.sql · mint_token.py                   DDL, seed data, indexes, token helper
├── tests/               conftest.py · test_*.py · verification_output.txt
├── docs/                console.png · inspector.png
├── Dockerfile           multi-stage image shared by the three Python services
├── docker-compose.yml   Postgres, Redis, ledger, gateway, agent worker, console
└── requirements.txt
```

## Run without Docker (zero-cost cloud services)

1. Create a free **Neon** Postgres and an **Upstash** Redis. Put their URLs, your `LLM_API_KEY` and `JWT_SECRET` in `.env`.
2. Run `infra/schema.sql` in the Neon SQL editor. It creates the tables and indexes and seeds both accounts.
3. From the repo root, in a Python 3.11 virtualenv with `pip install -r requirements.txt`, start each service in its own terminal:

```bash
uvicorn services.ledger.main:app  --port 8002
uvicorn services.gateway.main:app --port 8001
python -m services.agent_worker.consumer
```

4. Console:

```bash
cd frontend && cp .env.example .env.local     # paste the output of: python ../infra/mint_token.py
npm install && npm run dev
```

## Deployment

- **Backend:** deploy the gateway, ledger and worker to [Render](https://render.com) as three services from this repo, using the start commands above. Set `LEDGER_URL` on the gateway to the ledger's public URL, and `ALLOWED_ORIGINS` to your console's URL. The worker honours `PORT` with a small health endpoint.
- **Frontend:** deploy `frontend/` to [Vercel](https://vercel.com) with `NEXT_PUBLIC_API_URL` set to the gateway URL and `NEXT_PUBLIC_DEMO_JWT` set to a fresh token.
- **Before going public:** generate a new `JWT_SECRET` and remint the token, and rotate any key that has ever appeared in a chat, log or screenshot.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Console says *Missing token* or *Invalid token* | `DEMO_JWT` is empty or was signed with a different `JWT_SECRET`. Remint it and run `docker compose up --build` |
| A dispute stays on *Agent reviewing* | The worker failed. Run `docker compose logs --tail 25 agent_worker` and look for `attempt … failed`. A failed event lands in `tx_dlq`; refresh the page and raise the dispute again after fixing the cause |
| Worker log says `model_not_found` | Your provider retired the model. Set `LLM_MODEL` in `.env` to a current one, then `docker compose up -d --force-recreate agent_worker` |
| Worker log says the API key must be set | `LLM_API_KEY` is empty. Set it and use `--force-recreate`; a plain restart does not reload `.env` |
| `docker compose` says *no configuration file provided* | Run it from the repo root, where `docker-compose.yml` lives |
| Image build times out downloading packages | Slow network. Run `COMPOSE_PARALLEL_LIMIT=1 docker compose build`; cached layers make each retry go further |
| `pytest`: `role "sentinel" does not exist` | You reached a different Postgres on 5432. Use the Docker one on **5433** in `DATABASE_URL` |
| `pytest`: `greenlet library is required` | Install `sqlalchemy[asyncio]`, not plain `sqlalchemy` |
| Port already in use | Another process holds 3000, 5433, 6379, 8001 or 8002. Check with `lsof -i :<port>` |

## Known limitations

This is a portfolio-scale system, deliberately simple in places:

- **Authentication is a demo token.** There is no login or user model; a token is minted by a script and rate limits are keyed on the sending account.
- **Provisional credit is not counter-entered.** The schema has no bank or suspense account, so an auto-credit raises the customer's balance without a matching debit.
- **LLM explanations can be wrong.** Decisions never depend on them, but the text shown in the inspector is the model's prose and may misstate details (see the real run above).
- **No velocity signal in code yet.** The model infers bursts from raw timestamps. A deterministic "transfers in the last N minutes" count would make this more reliable.
- **The console cannot see a failed dispute.** A dispute in `tx_dlq` keeps showing *Agent reviewing* until the page is refreshed.
- **Single currency (USD), two seeded accounts, no account-creation flow.**

## Tech stack

Python 3.11 · FastAPI · Uvicorn · SQLAlchemy 2 (async) + asyncpg · PostgreSQL 16 · Redis 7 (sorted sets and Streams) · LangGraph · LangChain (Groq or Gemini) · Pydantic · python-jose · TypeScript · Next.js 14 · Tailwind CSS · Docker Compose · pytest