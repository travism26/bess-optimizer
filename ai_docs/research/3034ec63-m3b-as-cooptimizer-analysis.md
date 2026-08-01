# Research: M3b Energy + AS Co-optimization LP

## Metadata

adw_id: `3034ec63`
prompt: `specs/M3b_as_cooptimizer.md`
date: `2026-08-01`

## Executive Summary

M3b is a purely additive slice: one new module (`src/bess/optimizer/as_lp.py`),
three new frozen dataclasses/constants in `src/bess/models.py`, and two new test
files. Nothing existing is edited except `models.py` (append-only) and possibly
the package `__all__`; `optimizer/lp.py` stays byte-for-byte untouched. I
prototyped the master spec's LP formulation end to end during this research
(numpy-CSC `HighsLp`, same technique as `lp.py`) and **all five goldens
reproduce exactly**: masked equivalence is bit-identical to `optimize_dispatch`,
zero-price equivalence is bit-identical, pure REG_UP = 240.0, additive = 250.0,
REG_DOWN room = 150.0, and the 2-year/5-product runtime is **1.05 s against a
60 s budget**.

Two findings need action before the build. First, **this worktree branch is
stale**: `adw/3034ec63` was cut from main before PR #8 (M3a) merged, so
`tests/fixtures/as_mcpc_2023_07.parquet` and `src/bess/data/as_prices.py` are
absent here even though they are on `origin/main`. The property tests (AC 6-9)
cannot run until `origin/main` is merged into this branch. Second, **per-product
revenue attribution is degenerate under a product-order shuffle** (measured:
REG_UP and ECRS swap $2,555 on the July fixture at an identical objective), so
the gotcha-4 shuffle test must assert the aggregate AS revenue and the objective,
never the per-product split.

## Existing Architecture

### Relevant Documentation Found

| Doc | What it contains |
| --- | --- |
| `specs/M3_ancillary_services.md` | Master. Frozen `AsProduct` / `AsDispatchResult` / `optimize_dispatch_as` shapes, the exact LP formulation, the three pinned conventions, the modeling-assumptions text, `[ancillary]` config block. Wins on any conflict. |
| `specs/M3b_as_cooptimizer.md` | This slice: 10 acceptance criteria, 4 gotchas, definition of done. |
| `specs/M3a_as_data_layer.md` | Sibling slice, already merged (PR #8). Defines the AS fixtures this slice's property tests consume. |
| `specs/M3c_as_backtest_cli.md` | Downstream consumer: `run_backtest_as` builds the (P, T) matrices from the long AS frame and calls `optimize_dispatch_as`. Constrains nothing here beyond keeping the frozen signature. |
| `specs/M1_python_core.md`, `specs/M1b_optimizer.md` | The M1 LP formulation and purity rules that `as_lp.py` mirrors. |
| `app_docs/feature-3b9cf1a9-lp-optimizer.md` | How the M1b optimizer slice was built and documented; the closest structural template for this slice. |
| `ai_docs/research/3b9cf1a9-m1b-lp-optimizer-analysis.md` | Prior research doc for the analogous optimizer slice. |
| `ai_docs/memory/entries/` | 13 entries; four are directly load-bearing here (degeneracy, highspy typing, AST import guard, `.ports.env`). |
| `CLAUDE.md` | Frozen interfaces, purity rule, no em-dashes, no AI-attribution trailers, gates. |

### Component Map

```
        prices (T,)  as_prices (P,T)  as_available (P,T)  BatterySpec  products
                              |
                              v
   NEW  src/bess/optimizer/as_lp.py :: optimize_dispatch_as  ---> AsDispatchResult
                              |                                    (wraps DispatchResult)
                              |  pure numpy + highspy + bess.models
                              |
   unchanged  src/bess/optimizer/lp.py :: optimize_dispatch  (M4 Rust target, frozen)
                              ^
                              |  used by M3b tests only, as the equivalence/dominance oracle

   M3c (out of scope here): backtest/as_runner.py -> builds (P,T) matrices from the
   long canonical AS frame -> optimize_dispatch_as -> metrics_from_dispatch -> CLI JSON
```

### Key Files and Modules

- `src/bess/models.py` (67 lines): `BatterySpec`, `DispatchResult`,
  `BacktestResult`. Frozen dataclasses, module docstring says do not rename or
  reorder. M3b appends `AsProduct`, `DEFAULT_AS_PRODUCTS`, `AsDispatchResult`.
- `src/bess/optimizer/lp.py` (179 lines): `optimize_dispatch` plus the private
  `_build_lp`. The reference implementation for the CSC build, status handling,
  simultaneity warning, and docstring style. Must not be touched.
- `src/bess/optimizer/__init__.py`: one-line docstring only, no re-exports.
- `src/bess/__init__.py`: re-exports `BacktestResult`, `BatterySpec`,
  `DispatchResult` with an explicit `__all__`.
- `tests/test_optimizer_golden.py` / `tests/test_optimizer_properties.py`: the
  structural templates for the two new test files, including the AST-based
  import-purity guard (`_top_level_import_modules`) and the wall-time-printing
  runtime test.
- `tests/conftest.py`: autouse socket guard; `manual`-marked tests exempt.
- `tests/fixtures/hb_north_2023_07.parquet`: 744 rows, canonical energy schema,
  `2023-07-01T05:00Z` through `2023-08-01T04:00Z`.
- `tests/fixtures/as_mcpc_2023_07.parquet` (**on origin/main, not in this
  worktree**): 3,720 rows = 744 intervals x 5 products, long canonical AS
  schema, all five products live for the whole month, timestamps an exact set
  match with the energy fixture. Verified by reading it out of
  `origin/main` during this research.

## Affected Areas

### Files That Will Need Changes

| File | Change |
| --- | --- |
| `src/bess/models.py` | Append `AsProduct` (frozen: `name`, `direction`, `sustain_hours`), `DEFAULT_AS_PRODUCTS` (REG_UP 1.0 up, REG_DOWN 1.0 down, RRS 1.0 up, ECRS 2.0 up, NONSPIN 4.0 up, per the master's `[ancillary.sustain_hours]`), `AsDispatchResult` (`dispatch`, `products`, `awards_mw`, `energy_revenue_usd`, `as_revenue_usd`). Additive only; existing three classes untouched. |
| `src/bess/optimizer/as_lp.py` | **New.** `optimize_dispatch_as` + a private `_build_as_lp`. Purity allowlist identical to `lp.py`. |
| `tests/test_as_optimizer_golden.py` | **New.** AC 1-5. |
| `tests/test_as_optimizer_properties.py` | **New.** AC 6-10, plus the AST purity guard for `as_lp.py` and the gotcha-4 shuffle test. |
| `src/bess/__init__.py` | Optional but consistent: add the three new names to the imports and `__all__`. Additive, no risk. |

Explicitly not changed: `optimizer/lp.py`, `backtest/*`, `data/*`, `analytics/*`,
`viz/*`, `cli.py`, `config.toml`, `README.md` (M3c owns the README M3 section and
the `[ancillary]` config block).

### Dependencies

- `as_lp.py` depends on: `numpy`, `highspy`, `bess.models`, `logging`,
  `__future__`. Nothing else, mirroring the M1b purity rule.
- Depends on M3a only through a **data artifact**, never code: the property tests
  read `tests/fixtures/as_mcpc_2023_07.parquet` with `pd.read_parquet` and pivot
  it inline. Do not import `bess.data.as_prices` (the spec says so explicitly,
  and the M1b test files set the precedent of fixture-free/code-free isolation).
- Depended on by: M3c's `run_backtest_as` (signature + `AsDispatchResult` shape),
  and potentially a later Rust port (the master calls it a candidate, not part
  of M4's initial scope).

### Integration Points

1. `AsDispatchResult.dispatch` is a plain `DispatchResult`, so M3c can feed it
   straight into the existing `metrics_from_dispatch` code path
   (memory: `backtest-shared-solve-for-metrics-and-plots`). Populate every
   `DispatchResult` field exactly as `optimize_dispatch` does, including
   `simultaneous_hours` and the WARNING log, and set `objective_value` to the
   **full co-optimized** objective per the master's comment.
2. `products` on the result is the row-order key for `awards_mw`; M3c's
   `revenue_by_product` and `award_mw_hours` series depend on it being the same
   tuple that was passed in (echo it back, do not re-sort).
3. Test-only integration with `optimize_dispatch` as the equivalence oracle
   (AC 1, 2, 9) and with `bess.models.BatterySpec`.

## Impact Analysis

### Scope of Change

Small and contained: roughly 200 lines of new optimizer code plus two test
modules. Zero edits to existing behavior, so regression risk on M1/M2 is close
to nil. The risk concentrates in LP formulation correctness, which I de-risked by
building and running the formulation during research (see below).

### Prototype Results (run during this research, throwaway script in /tmp)

Formulation: columns `[c(T), d(T), s(T), a_0(T) .. a_{P-1}(T)]`, rows
`[dynamics(T), up coupling(T), down coupling(T), up adequacy(T), down room(T)]`,
availability as a zero upper bound on the award column.

| Check | Result |
| --- | --- |
| AC-1 masked equivalence (seed 0, T=168, default battery) | objective identical to `optimize_dispatch` to the last bit; `awards_mw.max() == 0.0` |
| AC-2 zero-price equivalence | identical to the last bit |
| AC-3 pure REG_UP, 1 MW / 1 MWh | **240.0**; awards 1 MW every hour, SoC pinned at 1.0 |
| AC-3 note, same case with 2 MWh | **250.0**, exactly as the spec predicts (the note is correct, capacity is load-bearing) |
| AC-4 additive | **250.0**; c=[1,0], d=[0,1], a=[1,0] |
| AC-5 REG_DOWN room | **150.0**; d=[1,1], a=[1,2], SoC [1,0] (the 2 MW award exceeds `power_mw`, confirming pinned convention 2) |
| AC-10 runtime, T=17,520, P=5 (122,640 cols, 87,600 rows) | **1.05 s** (budget 60 s) |
| AC 6-8 on the July fixtures, default battery | status optimal; max constraint residual 2.8e-14 across all four AS rows; SoC dynamics residual 5.2e-13; decomposition exact |
| AC-9 dominance | co-opt 2,689,961.68 vs energy-only 970,937.15 |

Useful numbers for M3c later: July 2023 HB_NORTH uplift **2.77x** (inside M3c's
[1.0, 8.0] corridor), AS share 78.9 percent, mix ECRS $1.275M / REG_UP $448k /
REG_DOWN $269k / RRS $131k / NONSPIN $0. NONSPIN winning nothing is not a bug:
its 4.0 h sustain makes it the most expensive product per MW of adequacy.
Awards exceed `power_mw` in 145 of 744 intervals on the fixture, so convention 2
is genuinely exercised there, not just in golden 4/5.

### Risks and Considerations

1. **Stale branch, missing fixture (blocker).** `adw/3034ec63` branched from main
   at `7d11baa` (PR #7); M3a merged afterwards as `f13d5f4` (PR #8). This
   worktree has no `tests/fixtures/as_*.parquet`. Merge `origin/main` into the
   branch before writing the property tests, otherwise AC 6-9 have no input and
   the failure will look like a test bug rather than a branch-state problem.
2. **Per-product attribution is degenerate.** Shuffling product order on the July
   fixture leaves the objective identical (6.5e-9) but moves $2,555 between
   REG_UP and ECRS, because at some hours the coupling constraint binds while
   adequacy is slack and two products tie on price. Gotcha 4's shuffle test must
   assert `objective_value` and total `as_revenue_usd`, plus (safely) that the
   returned `products` tuple matches the input order. Asserting per-product
   revenue equality would be flaky. This is the same family as
   memory: `lp-optimizer-degeneracy-in-tests`, one level up.
3. **highspy is untyped** (memory: `highspy-untyped-mypy`). `warn_return_any` is
   on. Cast everything read back from the solver: `float(solver.getObjectiveValue())`,
   `np.asarray(solver.getSolution().col_value, dtype=np.float64)`,
   and annotate the `HighsLp` builder's return type. `highspy.kHighsInf` is the
   correct one-sided-bound sentinel and exists in the pinned version (verified).
4. **Reshape order.** `awards_mw` is (P, T) and the solution vector is flat;
   `sol[3*T:].reshape(P, T)` is correct only with C order and the column layout
   above. Pair it with `(as_prices * dt).reshape(-1)` for the cost vector so the
   two orders cannot drift apart.
5. **Negative zero and tolerances.** The solver returns `-0.0` awards and SoC
   values like `-1e-16`; use the M1 convention of `>= -1e-6` / `<= bound + 1e-6`
   rather than strict comparisons. `awards >= 0` with `-0.0` is fine as written.
6. **Do not add rows conditionally.** Keeping all four AS row blocks present even
   when a direction has no products is safe (each degenerates to a constraint
   already implied by the M1 bounds) and is what makes masked equivalence come
   out bit-identical. Special-casing the row set risks losing that.
7. **Empty/edge inputs.** Decide and document behavior for `products=()` (P=0,
   `as_prices` shape (0, T)); the natural answer is that it reduces to
   `optimize_dispatch`. Validation must catch: `as_prices.shape != (len(products), T)`,
   `as_available.shape` mismatch, non-bool availability, and any
   `direction` not in {"up", "down"} (the master's UP/DOWN sets are exhaustive).
8. **`.ports.env` housekeeping** (memory: `adw-worktree-port-file-cleanup`).
   It is already modified in this worktree and has been flagged in three prior
   runs. Restore or untrack it before finalizing this PR.
9. Style gates: ruff line-length 100, `select = [E,W,F,I,B,UP,SIM,RUF]`, mypy
   `disallow_untyped_defs`, no em-dashes anywhere, no AI-attribution trailer in
   commits.

### Existing Patterns to Follow

- **CSC build with numpy, not the high-level API.** `_build_lp` builds
  `start`/`index`/`value` arrays directly; that is what keeps T=17,520 fast. The
  prototype extends the same technique to (3+P)*T columns and hits 1.05 s.
- **Docstring cites the spec section and explains the "why".** `optimize_dispatch`'s
  docstring is the model: formulation, deliberate omissions, negative-price
  philosophy. AC/DoD requires the same for `optimize_dispatch_as` plus the three
  pinned conventions and the capacity-only caveat.
- **Status handling:** anything but `kOptimal` raises `RuntimeError` including
  `solver.modelStatusToString(status)`.
- **AST-based import-confinement guard** (memory: `ast-based-import-confinement-guard`):
  copy `_top_level_import_modules` and assert `as_lp.py`'s imports against
  `{"numpy", "highspy", "bess.models", "logging", "__future__"}`.
- **Test file conventions:** module docstring naming the acceptance criteria
  covered, `FIXTURES_DIR = Path(__file__).parent / "fixtures"`, `pytest.approx(..., abs=...)`,
  `@pytest.mark.parametrize("seed", (0, 1, 2))` with `np.random.default_rng`,
  and printing the wall time in the runtime test (`print(f"... {elapsed:.3f}s")`).
- **Golden docstrings derive the expected number by hand** before asserting it.

## Recommendations

1. **First action in the build phase: `git merge origin/main`** (or rebase) so the
   M3a fixtures and `as_prices.py` are present. Confirm
   `tests/fixtures/as_mcpc_2023_07.parquet` exists and that `uv run pytest -q` is
   green on the merged base before adding anything.
2. **Models first, additively.** Append the three names to `models.py` in the
   master's field order, `@dataclass(frozen=True)`, docstrings stating that
   `dispatch.objective_value` is the full co-optimized dollar figure and that
   `products` is the row-order key for `awards_mw`. Mirror them into
   `src/bess/__init__.py`'s `__all__`.
3. **Implement `as_lp.py` with this layout** (validated by the prototype):
   - columns `[c(T), d(T), s(T), a_0(T) .. a_{P-1}(T)]`, `num_col = (3+P)*T`;
   - rows `dynamics [0,T)`, `up coupling [T,2T)`, `down coupling [2T,3T)`,
     `up adequacy [3T,4T)`, `down room [4T,5T)`, `num_row = 5*T`;
   - nnz per column: c 3, d 3, s 4 (3 for the last one), each award 2;
   - row bounds: dynamics `[0,0]` with row 0 pinned to `initial_soc_mwh`;
     coupling rows `(-inf, power_mw]`; up adequacy `(-inf, 0]` with the
     `-discharge_eff * s_t` term carried on the SoC column; down room
     `(-inf, energy_mwh]` with `+1` on the SoC column;
   - award upper bound `np.where(as_available.reshape(-1), kHighsInf, 0.0)`;
   - cost `[-prices*dt, prices*dt, zeros(T), (as_prices*dt).reshape(-1)]`,
     `sense_ = kMaximize`.
4. **Validate before building the LP:** shapes, dtype of `as_available`, and
   directions; raise `ValueError` with the offending value in the message.
   Compute `energy_revenue_usd` and `as_revenue_usd` from the returned arrays
   (not from solver internals) so AC-8's "recomputes from the raw arrays" is true
   by construction; assert their sum against `objective_value` only in tests.
5. **Reuse the simultaneity logic verbatim** (threshold 1e-3, WARNING log) so the
   co-opt dispatch reports the same field M1/M2 metrics already consume. Consider
   a shared module-level constant in `as_lp.py` rather than importing from
   `lp.py`, which would violate that module's frozen-and-untouched status only if
   edited; importing a constant is fine but duplicating it keeps `lp.py`'s import
   graph out of the picture entirely.
6. **Test mapping:** goldens 1-5 into `tests/test_as_optimizer_golden.py`
   (goldens 3-5 with hand-derived docstrings, goldens 1-2 comparing against
   `optimize_dispatch` on seeded random series); AC 6-10 plus the shuffle test
   and the AST purity guard into `tests/test_as_optimizer_properties.py`. Assert
   revenue and residuals everywhere else, never raw award values (gotcha 1).
   Property tests read the July fixtures with `pd.read_parquet` and pivot to
   (P, T) inline, ordering rows by the `products` tuple.
7. **Runtime test:** the measured 1.05 s leaves 57x headroom, so assert `< 60.0`
   as specified and print the elapsed time; no need to shrink the case.
