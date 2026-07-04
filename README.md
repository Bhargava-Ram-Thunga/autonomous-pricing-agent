# Autonomous Pricing Agent

**Kaggle x Google — 5-Day Gen AI Intensive: Agents Capstone Submission**

An autonomous AI agent that monitors live seat/ticket bookings and adjusts prices in real time to maximise revenue — running 24/7 with no human in the loop, while still respecting human overrides when they happen.

This project started as a production system managing real ticket pricing for a transportation operator. This repo is a genericized, de-branded version of that system, built to demonstrate the agent architecture, tool-use design, and decision loop for the capstone submission. Company-specific endpoints, credentials, and branding have been removed/replaced with placeholders.

---

## Why this is an "agent," not a script

A cron job that raises price by X% when bookings cross a threshold is automation. This is an agent because it:

- **Reasons** about demand signal (count *and* velocity) before acting, using an LLM (Groq `llama-3.3-70b`, with fallback)
- **Chooses and calls tools** rather than following a fixed code path — it decides *which* pricing lever to pull (tier bump, static fare, surge override, revert) based on context
- **Remembers** — every decision and its outcome is persisted, and past outcomes inform future decisions
- **Detects and respects human intervention** — if a person manually overrides a price, the agent notices, waits, and only reverts if the data still supports its original call
- **Explains itself** — every action is logged with reasoning and posted as a plain-English summary

---

## How Pricing Works

The agent follows a demand-based pricing matrix, with an LLM deciding when the matrix rule should be overridden:

| Seats Sold | Pricing Action |
|---|---|
| 0 – 3 | Fixed floor fares |
| 4 – 9 | Super Low classification |
| 10 – 17 | Low classification + small fare increase |
| 18 – 25 | Medium classification + moderate increase |
| 26 – 32 | High classification + larger increase |
| 33 – 40 | Super High classification + bigger increase |
| 40+ | Ultra High classification + max increase |

**Surge override:** if bookings arrive faster than a velocity threshold (e.g. 30/hour), the agent adds an extra bump on top of the matrix rule to capture peak demand — this is where reasoning beats a static rule table.

All fare changes are clamped to hard floor/ceiling guardrails (`pricing_rules.py`) so the agent can never price a seat outside safe business bounds, no matter what the LLM decides.

---

## Architecture

```
Every N minutes / Chat message (Slack or API)
         │
         ├─ Read queries (status, forecast, list trips)
         │        └─► Direct API/DB read — instant response, no LLM needed
         │
         └─ Pricing decisions (increase, set tier, apply surge)
                  └─► LangGraph ReAct Agent
                        ├─ LLM reasons about demand + history
                        ├─ Calls tools to read live data
                        ├─ Calls tools to write price/tier changes
                        ├─ Applies guardrail clamps before any write
                        ├─ Records outcome to Postgres for learning
                        └─ Posts plain-English summary to Slack
```

**Agentic loop (`autoloop.py`):** runs on a timer, pulls every active trip, classifies demand, and only calls the LLM for decisions that aren't simple matrix lookups — keeping cost and latency low while still being agentic where it matters.

**Tool layer (`api_tools.py`, `tools.py`):** every action the agent can take — read bookings, read fares, apply a tier, set a static fare, revert, query historical outcomes — is exposed as a discrete tool with guardrails baked in at the tool boundary, not just in the prompt.

**Memory (`state_store.py`, `db.py`, Postgres):** decisions, outcomes, and override events persist across restarts, so the agent's context isn't just the current conversation window.

---

## Key Agent Behaviors

- **Autonomous loop** — checks all active trips on a timer, applies rules, posts a summary, no human input required
- **Booking velocity tracking** — reasons about *rate* of demand, not just current count, to catch surges before they peak
- **Outcome learning** — after every price change, records how bookings responded afterward and folds that history into future prompts
- **Human-override awareness** — detects when a person manually changed a price outside the agent, waits a cooldown window, and only reverts if fresh data still supports the agent's original call
- **Anomaly alerts** — a sudden spike or drop triggers an out-of-cycle alert instead of waiting for the next loop
- **Full audit trail** — every write is logged to `changes.jsonl` with timestamp, tool, arguments, and result — nothing is a silent side effect

---

## Chat Interface

The same agent is reachable via Slack commands or the HTTP chat API:

| What you type | What happens |
|---|---|
| `status` | Live booking count for all active trips |
| `show status <trip_id>` | Booking details for a specific trip |
| `bookings tomorrow` | Seat fill for tomorrow's trips |
| `forecast 7 days` | Week-ahead booking outlook |
| `show fares` | Current fare breakdown by seat |
| `increase fares on <trip_id>` | Agent reasons and applies a fare increase |
| `set classification High on <trip_id>` | Agent updates the pricing tier |
| `reset static fares <trip_id>` | Clears fixed fares, model takes back over |
| `what pricing for <trip_id>?` | Agent analyses, recommends, and (if asked) applies |

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent framework | LangGraph ReAct agent |
| LLM | Groq `llama-3.3-70b` (HuggingFace fallback) |
| API server | FastAPI + SSE streaming |
| Data source | Generic REST admin API + read-only Postgres |
| Memory / history | PostgreSQL |
| Chat interface | Slack (Socket Mode) + HTTP chat endpoint |
| Dashboard | Next.js (`ui/`) |
| Audit log | `changes.jsonl` — every write recorded |

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and fill in:
```
GROQ_API_KEY=your_groq_key
API_BASE_URL=https://your-pricing-portal.example.com/admin
PORTAL_USER=your_username
PORTAL_PASSWORD=your_password
POSTGRES_URL=postgresql://user:pass@localhost:5432/pricing_agent
SLACK_BOT_TOKEN=xoxb-...        # optional — Slack interface
SLACK_CHANNEL_ID=your_channel   # optional
AUTOLOOP_SEC=300
```

### 3. Run
```bash
python main.py
```
Server starts on `http://localhost:8000`.

### 4. (Optional) Run the dashboard
```bash
cd ui
npm install
npm run dev
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Server status |
| `/chat` | POST | Send message to the agent |
| `/chat/stream` | POST | Streaming SSE response |

---

## Notes on This Version

This is a **de-branded, generalized copy** of a production pricing agent, prepared for the Kaggle x Google 5-Day Gen AI Intensive agents capstone. The original company name, real API endpoints, and credentials have been stripped and replaced with placeholders (`your-pricing-portal.example.com`, generic env vars). The agent logic, tool design, guardrails, and memory architecture are unchanged — this is the real system, pointed at a domain you configure.
