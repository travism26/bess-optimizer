# Project Context: BESS Dispatch & Revenue Optimizer

> Planning handoff that seeded this repo. The authoritative build spec is
> `specs/M1_python_core.md`; this file records the why and the shape of the
> project. No em-dashes anywhere in this repo's docs.

---

## Why this project exists

1. **Learning vehicle.** A bounded, real problem for closing two stack gaps:
   Rust (via a PyO3 optimization engine) and Snowflake (via warehouse-backed
   price analytics). Python-first sequencing keeps the domain learning and the
   language learning from colliding.
2. **Portfolio piece.** Utility-scale battery storage is a real, growing
   domain (ERCOT is the largest US storage market); a working optimizer with
   honest metrics is a stronger signal than a resume line.
3. **Dogfooding + content.** The repo is built with ADW, my own multi-agent
   SDLC harness for Claude Code, which proves the harness generalizes to a new
   language and domain. Each milestone becomes a dev.to post.

## The build tool: ADW (Agentic Developer Workflow)

ADW is a production-grade multi-agent SDLC harness (~18K LOC Python) for
Claude Code. It runs a pipeline (research, plan, build, validate, test,
review, document), each phase a separate agent, with eval-driven development
(pass@k / pass^k), best-of-N, capability-based safety controls, and a memory
layer. The engine lives in a private repo; the project-tailored slash
commands it uses are tracked here under `.claude/commands/`.

---

## The project

**One-liner:** given historical ISO electricity-market prices, compute the
optimal battery charge/discharge schedule that maximizes revenue under real
battery constraints, backtest it over historical data, and visualize it.

**Domain focus:** ERCOT first (largest US storage market, richest price
volatility). CAISO second.

**The optimization core:** battery energy arbitrage as a linear program.
Maximize `sum over t of (price_t * discharge_t - price_t * charge_t)` subject to:

- state-of-charge dynamics (SoC_t+1 = SoC_t + eff * charge_t - discharge_t)
- power limits (MW) on charge and discharge
- energy capacity limits (MWh), SoC bounds
- round-trip efficiency
- optional: daily cycle cap, cycle-cost/degradation penalty

Extensions once the base works: co-optimize ancillary services, day-ahead vs
real-time, multi-node.

**Backtesting is eval discipline applied to a new domain.** Scoring a
dispatch strategy against historical prices is the same rigor as an agent
eval harness, pointed at revenue.

### Stack

- **Rust**: the dispatch/optimization engine (performance-critical), exposed
  to Python via PyO3 / maturin. A Python-callable Rust core mirrors how a
  Python+Rust shop actually works.
- **Python**: data ingestion, backtesting harness, orchestration, calls the
  Rust core.
- **Snowflake**: warehouse for historical price/load timeseries; SQL analytics
  (arbitrage spreads, TB4 value = top-4 minus bottom-4 hours, capture rate by
  node/season). dbt optional.
- **AWS**: Lambda + EventBridge cron pulls data daily to S3, loads to
  Snowflake.
- **TypeScript / React**: dashboard: price curve, optimal dispatch, SoC over
  time, cumulative revenue, node comparison.
- **Claude Code / ADW**: build the whole thing with the harness; blog each
  milestone.

### Data sources (all public/free)

- **GridStatus.io** (Python lib) for ISO market data (ERCOT, CAISO, PJM,
  MISO, etc.).
- **EIA Open Data API** for generation/storage/prices.
- ERCOT / CAISO direct where needed.

### Pragmatic build order (do NOT fight Rust and the domain at once)

1. Build the optimizer in **Python first** (HiGHS) to nail the domain logic
   and get a working backtest.
2. **Then** port the hot loop to **Rust** (PyO3) as the performance and
   learning exercise, and benchmark Rust vs Python.
3. Layer in Snowflake storage/analytics, then the AWS ingestion pipeline,
   then the dashboard.

### Constraints

- Public repo. Never commit API keys, secrets, or bulk market data; only
  small frozen fixtures under `tests/fixtures/` are tracked.
- Rust-beginner sequencing: fundamentals first, small surface area, the
  Python implementation stays as the correctness oracle.
