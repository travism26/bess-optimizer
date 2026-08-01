# Rust Learning Plan for M4 (PyO3 Dispatch Port)

Prepared 2026-08-01 for Travis, ahead of Milestone M4 (late August 2026 target start).

## TLDR

- Skip beginner exercise mills. Travis already knows types, ownership-adjacent concepts (Go, Rust's borrow checker is genuinely new, budget real time for it), and distributed-systems-grade error handling. Spend the first two weeks on The Rust Book chapters 4, 8-13, 15-19 plus rustlings' `move_semantics`, `borrow`, `lifetimes`, and `traits` exercises only, not the full 100-exercise set.
- Use the `highs` crate (crates.io, v2.4.0, wraps `highs-sys` ^1.14.3), not `good_lp`. `good_lp` adds a macro-based modeling DSL (`variables!`, `constraint!`) that hides the sparse-matrix structure Travis needs to understand and needs to reproduce; `highs`'s `ColProblem`/`RowProblem` builders map almost one-to-one onto the CSC arrays already hand-built in `_build_lp` in `src/bess/optimizer/lp.py`.
- Hand-write the LP construction and PyO3 boundary yourself, with agent tutoring (explain-then-implement, not implement-then-explain); delegate test scaffolding, benchmark harnesses, CI/maturin config, and property-test generation to the agent. This is the single highest-leverage split: the LP construction is exactly the part that forces you to understand ownership, borrowing, and the numpy/ndarray zero-copy boundary, which is the actual interview-demonstrable skill.
- The real risk isn't the Rust syntax, it's the temptation to let the agent write `_build_lp`'s Rust equivalent end to end since it's "just a port." Anthropic's own RCT on AI-assisted coding found the hand-coding group scored 67% vs. 50% for the AI-assisted group on a comprehension/debugging quiz afterward (nearly two letter grades); the gap concentrated in debugging questions specifically, so plan to debug your own compiler errors and panics for at least the first 2 weeks before leaning on the agent for that too.
- 4-week plan, 5-8 hrs/week (24-32 hrs total): Week 1 fundamentals + toy PyO3 hello-world; Week 2 hand-write the LP builder and solver call in Rust against the `highs` crate with golden-test parity against `lp.py`; Week 3 numpy interop, GIL release, error handling, benchmark against the 30-second/T=17,520 budget from `specs/M1_python_core.md`; Week 4 property tests, docs, review-gate self-quiz, PR.

## 1. Resource shortlist

Given his background (10+ years Java/Kotlin/Go/Python, distributed systems), the two things genuinely new to Travis are the borrow checker/lifetimes and Rust's trait-based generics/error-handling idioms. Everything else (types, pattern matching, module systems, build tooling, testing) maps closely enough to what he already knows that a full "beginner path" wastes time.

**Core, in order:**

1. **The Rust Book** (doc.rust-lang.org/book, free, current edition tracks stable Rust). Read chapters 4 (ownership), 8 (collections), 9 (error handling), 10 (generics/traits/lifetimes), 13 (closures/iterators), 15-17 (smart pointers, concurrency, OOP-ish patterns), 18-19 (patterns, advanced traits/lifetimes/unsafe). Skim the rest; he doesn't need chapters 1-3 (basic syntax) beyond a skim, or chapter 20 (the toy web server project) at all.
   - Note: multiple 2026 sources (see the official Rust blog vision doc below) confirm the Book is still the anchor resource, but flag that experienced OOP-language developers specifically get stuck "thinking object-oriented" and need to consciously unlearn the instinct to model everything as mutable structs with methods; that's the trap to watch for, not syntax recall.
2. **Rustlings** (github.com/rust-lang/rustlings, `rustlings watch` interactive CLI). Do only the `move_semantics`, `borrow`, `lifetimes`, `traits`, `error_handling`, `generics`, and `threads` sections (roughly 25-30 of the ~100 exercises). Skip `variables`, `functions`, `if`, `primitive_types`, `vecs`, `strings` sections entirely; those are one-liners for him.
3. **rust-numpy examples + PyO3 user guide** (pyo3.rs/main, github.com/PyO3/rust-numpy). Not a "learn Rust" resource, this is the M4-specific surface; read it in Week 3, not before, so the concepts land against real code.
4. **Jon Gjengset, "Crust of Rust" YouTube playlist** (youtube.com/@jonhoo). Watch the lifetimes episode in Week 1 and the "smart pointers" and "dispatch and fat pointers" episodes in Week 2-3 if the trait-object questions PyO3 raises (e.g., `Bound<'py, T>`, `PyResult<T>`) feel murky. These are 1.5-2 hour deep-dive streams, not tutorials; treat them as optional depth, not a checklist.
5. **Jon Gjengset, *Rust for Rustaceans*** (No Starch Press, 2021, still current per Bitfield Consulting's 2026 book roundup). Optional, second-pass material for after M4 ships if Travis wants to go from "competent" to "idiomatic"; covers unsafe, type layout, trait coherence, API design. Don't front-load it, it targets people who already have working Rust experience, which he won't have until after Week 2.

**Skip entirely for this goal:**

- **Rust by Example** (doc.rust-lang.org/rust-by-example). Redundant with the Book for someone who reads code faster than prose; use it only as a quick-reference lookup if a Book chapter's prose is too slow, don't work through it as a track.
- **Exercism's Rust track** (exercism.org/tracks/rust, ~99 exercises). Good but redundant with rustlings for fundamentals; skip unless Travis wants extra reps after Week 2. If he does, jump straight to the "advanced" tier exercises that implement a stdlib trait, write a macro, or write a parallel/threaded solution, not the warm-up tier.
- **Advent of Code Rust drills.** Great for raw language reps but has zero overlap with M4's actual surface (FFI, numpy, PyO3 macros, error boundaries). Skip for this 4-week window; revisit in December if he wants more practice unrelated to the project.
- **A full "Rust from scratch" video bootcamp course.** He doesn't need beginner pacing; every hour spent here is an hour not spent in the actual M4 code.

**Rough hour budget:** 6-8 hrs Book + rustlings fundamentals, 2-3 hrs PyO3/numpy-specific reading, 2-4 hrs optional Gjengset video depth. That's roughly the whole Week 1 budget (5-8 hrs) plus some Week 2 overflow, which is intentional: fundamentals compress fast for someone who already knows what a borrow checker is trying to prevent, he just hasn't had the compiler enforce it before.

Sources: [The Rust Programming Language book](https://doc.rust-lang.org/book/), [rustlings](https://github.com/rust-lang/rustlings), [The many journeys of learning Rust (Rust Blog, June 2026)](https://blog.rust-lang.org/2026/06/25/vision-doc-journeys-to-learning-rust/), [Rust on Exercism](https://exercism.org/tracks/rust), [The best Rust books for 2026, reviewed (Bitfield Consulting)](https://bitfieldconsulting.com/posts/best-rust-books), [Jon Gjengset's YouTube channel](https://www.youtube.com/c/JonGjengset).

## 2. M4 technical surface: crate and solver recommendation

### PyO3 + maturin + numpy workflow

- **Toolchain:** PyO3 0.28.x + maturin 1.8.x. As of PyO3 0.28, extension modules default to declaring themselves GIL-free-threading-safe (matters if Travis later targets free-threaded Python 3.13t/3.14t, not required for M4 but good to know it exists). `rust-numpy` tracks PyO3's version closely (it bumped to PyO3 0.24 in its own recent releases; pin both together in `Cargo.toml` and let maturin resolve the ABI).
- **Workflow:** `maturin new` to scaffold, `maturin develop` for the local edit-test loop (installs straight into the active venv, faster than a full wheel build), `maturin build --release` for the artifact you'd actually benchmark or ship, `maturin generate-ci github` if CI needs a matrix later. This matches the "hot loop out of Python, 95% of the project stays Python" shape M4 already wants: `optimize_dispatch` is the one function that moves, the CLI/backtest/data layers stay Python and call the new extension through the frozen `bess.optimizer.lp` interface.
- **numpy interop:** use `numpy` (rust-numpy) crate's `PyReadonlyArray1<'py, f64>` for the incoming `prices` array (zero-copy read-only view over the numpy buffer) and build the three output arrays (`charge_mw`, `discharge_mw`, `soc_mwh`) as `ndarray::Array1<f64>` internally, then hand them back with `.into_pyarray(py)`. This mirrors the existing Python function signature almost exactly: `PyReadonlyArrayDyn`/`PyReadonlyArray1` in, `Bound<'py, PyArray1<f64>>` out.
- **Releasing the GIL:** wrap the actual HiGHS solve (and ideally the CSC-matrix construction, since at T=17,520 that's real work too, per the comment in `_build_lp` about why it's done with raw numpy arrays rather than the high-level `Highs()` API) in `py.allow_threads(|| { ... })`. That's the mechanical equivalent of what the Python code is implicitly relying on `highspy`'s C++ internals to do; in the Rust port, Travis has to do it explicitly, which is a good forcing function for understanding what the GIL actually blocks.
- **Error handling:** don't propagate raw HiGHS status strings by hand. Define a small `enum DispatchError` (via `thiserror::Error`), implement `impl From<DispatchError> for PyErr` (or use `thiserror` plus a manual `From` impl mapping to `PyRuntimeError::new_err(...)`), and return `PyResult<DispatchResult>` from the `#[pyfunction]`. This directly parallels the existing `RuntimeError` raised in `lp.py` when `HighsModelStatus != kOptimal`, so it's a clean 1:1 translation target and a good place to actually learn Rust's `?`-operator error propagation instead of copy-pasting a pattern.

Sources: [PyO3 user guide](https://pyo3.rs/), [PyO3/rust-numpy](https://github.com/PyO3/rust-numpy), [PyO3 free-threading guide](https://pyo3.rs/v0.28.3/free-threading), [Maturin tutorial](https://www.maturin.rs/tutorial.html), [PyO3 error handling discussion on thiserror + From<T> for PyErr](https://github.com/PyO3/pyo3/discussions/3641).

### LP solver: recommend the `highs` crate over `good_lp`, `highs-sys` raw, or hand-rolled FFI

Three real options surfaced, plus a fourth (raw FFI) that's not worth it:

| Option | What it is | Verdict |
|---|---|---|
| `good_lp` (crates.io, MIT) | High-level LP/MILP modeling DSL (`variables!`, `constraint!` macros) with pluggable backends (HiGHS, CBC default, Clarabel, SCIP, others) | **Skip for M4.** The macro DSL hides exactly the sparse-matrix structure that `_build_lp` in `lp.py` builds by hand for performance, and that's the part with real learning value. It's also an extra abstraction layer between Travis's code and HiGHS, which works against "explain the diff" review gates: harder to reason about what's actually happening at the FFI boundary. |
| `highs` crate (crates.io, v2.4.0, wraps `highs-sys` ^1.14.3, MIT) | Safe Rust wrapper over HiGHS with two builder APIs: `RowProblem` (declare variables via `add_column`, then constraints via `add_row`) and `ColProblem` (constraints first via `add_row`, then columns via `add_column` with sparse `&[(row, coeff)]` pairs) | **Recommended.** Maps closely onto the column-wise CSC layout already used in `_build_lp` (columns `[c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}]`, each with 1-2 nonzeros). `ColProblem` in particular lets Travis build the same "each SoC column has its own row plus a link to the next interval's row" structure the Python code builds directly, just via safe Rust calls instead of raw numpy CSC arrays. Safe (no `unsafe` blocks needed), well-typed, and it's the same underlying HiGHS binary the Python `highspy` binding calls (`pyproject.toml` currently pins `highspy>=1.7`), so numerical results should match to solver tolerance, which matters for a golden-test port. |
| `highs-sys` raw (crates.io, MIT) | Low-level unsafe FFI bindings, direct `Highs_call`-style C interface, exactly mirrors the sparse-array style of `_build_lp` (`astart`, `aindex`, `avalue`) | Optional stretch goal, not the Week 2 target. If the `highs` crate's per-column `add_column` loop turns out to be a real bottleneck at T=17,520 (52,560 total decision-variable columns) after profiling, dropping to `highs-sys` to build the full CSC arrays in one shot (this is genuinely closer to the exact shape of the existing Python code) is a good Week 3/4 stretch exercise, and a legitimately interesting one: it's the first real `unsafe` Rust Travis would write. Don't start there; start safe. |
| Hand-rolled simplex / `clarabel` | `clarabel` (Apache 2.0, pure Rust, Oxford Control group) is a fast native interior-point solver but LP-only, no MILP path if cycle-cap constraints ever need integer/binary variables later (out of scope for M1/M4 per spec, but M3 already touches cycle caps) | Skip. No version-parity guarantee with the `highspy` oracle results M1 already established as ground truth; switching solver families risks introducing small numerical divergences that would fail the golden tests in `M1_python_core.md` (objective values checked to 1e-6). Sticking with HiGHS keeps the "identical LP, different language" framing intact. |

Performance note: the Python `_build_lp` docstring explicitly calls out that building the CSC arrays directly with numpy, rather than the row-by-row high-level `Highs()` API, is what keeps a T=17,520 solve inside the 30-second budget (acceptance criterion 7 in `specs/M1_python_core.md`). That concern is Python-interpreter-loop-overhead-specific; a compiled Rust loop calling `add_column` 52,560 times is a different cost profile (no per-call interpreter overhead), so it's plausible the `highs` crate's builder API is fast enough outright. Budget 30-60 minutes in Week 3 to actually benchmark it against the 30-second target with real fixture data before deciding whether the `highs-sys` raw-array stretch goal is necessary.

Sources: [good_lp GitHub](https://github.com/rust-or/good_lp), [good_lp highs solver backend docs](https://docs.rs/good_lp/latest/good_lp/solvers/highs/index.html), [highs crate docs](https://docs.rs/highs/latest/highs/), [highs-sys GitHub](https://github.com/rust-or/highs-sys), [HiGHS project](https://highs.dev).

## 3. Learning-integrated agentic development: what practitioners are doing in 2025-2026

The pattern search turned up real, current material, not just theory:

- **Simon Willison, on porting a Python codebase to Rust with agents (2026):** "This was human-directed, not autonomous code generation. I decided what to port, in what order, and what the Rust code should look like." He used many small, specific prompts to steer agents rather than one big "port this to Rust" instruction. This is directly applicable to M4: Travis, not the agent, should decide the module boundaries, the order (LP builder before PyO3 wrapper before benchmark harness), and what the Rust shape should look like, even where he's leaning on the agent for the actual keystrokes.
- **Simon Willison's "Agentic Engineering Patterns" (ongoing newsletter series, 2026):** concrete, reusable practices: red/green TDD so the agent has a falsifiable target instead of vibes; "first run the tests" (never trust code that's never executed); ask for a "linear walkthrough" of a generated solution as a forced-explanation step; and "hoard things you know how to do", his term for the idea that an engineer's own retained skills are what let them direct an agent well, and those skills erode if never exercised.
- **Armin Ronacher, "The Tower Keeps Rising" (2026), quoted by Willison:** "Before agents, some of this shared understanding was maintained by friction... This friction synchronizes people." His argument: code review, PR back-and-forth, and the general slowness of collaborative coding weren't just overhead, they were the mechanism by which people built shared mental models of a system. Removing that friction (agents write, human rubber-stamps) removes the synchronization, not just the slowness. Practical implication for a solo project like bess-optimizer: Travis has to manufacture that friction deliberately since there's no reviewing teammate to force it. That's what a self-imposed review gate is for.
- **Anthropic's own RCT on AI coding assistance and skill formation (2026):** hand-coding group averaged 67% on a post-task comprehension/debugging quiz vs. 50% for the AI-assisted group, roughly two letter grades, with the gap concentrated specifically in debugging questions. The same research identifies which usage patterns correlated with better outcomes for the AI-assisted group: asking follow-up/conceptual questions instead of accepting output passively, asking the agent to explain what it produced after the fact rather than before, and resolving encountered errors yourself instead of immediately handing the traceback back to the agent. That last one maps directly onto a "no doom-loop" habit: when `cargo build` fails, spend the first 5-10 minutes reading the compiler error and trying a fix before pasting it back to the agent.
- **Generic 2026 "AI code review gate" writing** (vendor content from Codacy, CodeRabbit, and similar, less rigorous than the above but converges on the same shape): the recurring concrete mechanism across these pieces is "run `git diff` after every session and read it before moving on", "verify tests pass before merging, not after", and "a credible review gate has to be able to disagree with the generator" (i.e., don't let the same agent that wrote the code also be the only thing that approves it).

**Concrete review-gate design for M4** (synthesizing the above into something Travis can actually run solo): after each week's agent-assisted session, before committing, he answers three questions out loud or in a commit-message footer, without looking at the diff: (1) what does this function do and why does it do it that way, not just what, (2) what would break if I changed the horizon length or the SoC bounds, (3) what's the one line I'd have gotten wrong if I'd written this alone. If he can't answer confidently, that's the signal to slow down and re-derive that section by hand rather than merge it, matching Ronacher's "friction synchronizes" point and Anthropic's finding that follow-up questioning is the practice that correlates with retained comprehension.

Sources: [Simon Willison, quoted on porting Python to Rust with agents](https://simonwillison.net/2026/Feb/27/ai-agent-coding-in-excessive-detail/), [Agentic Engineering Patterns, Simon Willison's Newsletter](https://simonw.substack.com/p/agentic-engineering-patterns), [Armin Ronacher quote via Simon Willison, July 2026](https://simonwillison.net/2026/Jul/14/armin-ronacher/), [Armin Ronacher, "The Tower Keeps Rising"](https://lucumr.pocoo.org/2026/2/9/a-language-for-agents/), [Anthropic: How AI assistance impacts the formation of coding skills](https://www.anthropic.com/research/AI-assistance-coding-skills), [The Skill Atrophy Trap (Tianpan.co, April 2026)](https://tianpan.co/blog/2026-04-19-skill-atrophy-ai-augmented-engineering), [Quality gates for AI-generated code (CodeRabbit)](https://www.coderabbit.ai/guides/ai-generated-code-quality-gate).

One caveat on the Tianpan.co piece: its headline comprehension-gap number (17 points) roughly matches Anthropic's RCT, which is corroborating, but its specific "2.3 year recovery half-life" claim isn't sourced to a study in the visible article text and reads more like a rhetorical flourish than a measured figure. Treat it as directional, not load-bearing.

## 4. Hand-write vs. delegate split for M4

The organizing principle: **hand-write anything that forces you to reason about ownership, the numpy/Rust memory boundary, or numerical correctness; delegate anything that's mechanical, boilerplate, or would be identical regardless of who understands the domain.**

### Hand-write yourself (agent as tutor: ask it to explain concepts and review your draft, not to produce the draft)

1. **The LP construction module** (`build_lp` equivalent to `_build_lp` in `lp.py`): the column layout, the sparse constraint construction via the `highs` crate's `ColProblem`, the bounds arrays. This is the part with an existing, fully-specified reference implementation to port against, which makes it ideal for hand-writing: you always have a correctness oracle a few lines away in the Python file.
2. **The PyO3 function boundary**: the `#[pyfunction]` signature, `PyReadonlyArray1` extraction, the `allow_threads` wrapping, and the `into_pyarray` return. This is the crux of "PyO3 competence" as an interview-demonstrable skill; if an agent writes this end-to-end, Travis hasn't actually learned PyO3, he's learned to read PyO3.
3. **The `DispatchError` type and its `From<DispatchError> for PyErr` impl.** Small, contained, and exactly the kind of Rust idiom (trait impls, `?`-propagation) that's worth typing out by hand once so it's not cargo-culted.
4. **Reading and fixing your own compiler errors and panics for at least the first two weeks**, per the Anthropic RCT finding above. Paste the *concept* to the agent ("why does the borrow checker reject this pattern") before pasting the *error* ("fix this").

### Delegate fully (agent writes, you review via the gate in section 3, don't re-derive)

1. **Cargo/maturin project scaffolding**: `Cargo.toml`, `pyproject.toml` `[tool.maturin]` config, `.github/workflows` CI matrix if M4's spec calls for one, abi3 feature flags. Pure boilerplate, zero learning value, high error-proneness if hand-typed from memory.
2. **Test scaffolding and golden-test translation**: porting the 9 acceptance-criteria fixtures from `M1_python_core.md` (flat prices, step prices lossless/lossy, negative price, property tests on the frozen month of HB_NORTH data) into Rust `#[test]` functions that call the new extension via a Python subprocess or PyO3's `pytest` integration. Mechanical translation from an existing spec; delegate it, but read the generated tests closely since they define what "correct" means for the port.
3. **Benchmark harness** for the 30-second/T=17,520 runtime budget (criterion.rs or a simple timed loop). Useful, not a learning target.
4. **Property-based test generation** (if using `proptest` or similar to fuzz SoC bounds/dynamics residuals per acceptance criterion 5). Delegate the harness; hand-write the actual invariants being checked if they're not 1:1 copies of the Python property tests.
5. **Documentation and the M4 spec's "definition of done" writeup** (README section, results table). Low learning value, high agent leverage.

### The one gray area

The **numpy-to-ndarray zero-copy read path** (`PyReadonlyArray1::as_array()`) is small enough to feel delegable but is the exact place a subtle bug (accidentally copying when you meant to borrow, or vice versa, getting lifetimes wrong on the returned view) would teach the most. Recommendation: have the agent explain the borrow/lifetime mechanics first (tutoring mode), then Travis types the 5-10 lines himself, then the agent reviews.

## 5. Four-week schedule (5-8 hrs/week, ~24-32 hrs total)

Assumes M4 hasn't formally started yet (spec not yet written as of this research) but Travis wants to be ready to hand-write the core the week the spec lands, roughly matching the "late August 2026" milestone target.

### Week 1: Fundamentals + environment (5-8 hrs)

- (2-3 hrs) Rust Book ch. 4 (ownership/borrowing), ch. 9 (error handling: `Result`, `?`, `panic!` vs recoverable errors), ch. 10 (traits, generics, lifetimes intro).
- (1.5-2 hrs) Rustlings: `move_semantics`, `borrow`, `lifetimes` sections only, run via `rustlings watch`.
- (1 hr) Install toolchain: `rustup`, `cargo`, `maturin` (`pip install maturin` or `uv tool install maturin`), confirm a C++ compiler is present (needed for `highs-sys` to build HiGHS from source).
- (1-2 hrs) `maturin new` a throwaway hello-world extension, wire it into a scratch Python venv, call it from a Python REPL. Goal: touch the whole PyO3 -> maturin -> Python round trip once before it matters for real, on a trivial function (e.g., add two floats), not the actual LP.
- Tutoring prompt to use with the agent this week: "explain what the borrow checker is rejecting here and why, don't fix it for me" whenever rustlings gives an error.

### Week 2: The LP core, hand-written (6-8 hrs)

- (1 hr) Re-read `_build_lp` and `optimize_dispatch` in `src/bess/optimizer/lp.py` closely; write out the column layout and constraint structure from memory, then check it against the file.
- (1 hr) Read `highs` crate docs for `ColProblem`: `add_row`, `add_column`, `Sense::Maximise`, `.solve()`, `get_solution()`.
- (3-4 hrs) Hand-write the Rust LP builder: columns `[c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}]`, SoC recursion constraints, bounds, objective. Use the agent in tutoring mode: describe what you're trying to build, ask clarifying questions about `highs` crate API shape, but type the code yourself.
- (1-2 hrs) Get one golden case working end-to-end (start with acceptance criterion 1, flat prices, objective == 0.0) as a plain `cargo test`, no PyO3 yet. Keep it solver-only first; adding the Python boundary in the same week compounds the debugging surface.

### Week 3: PyO3 boundary, numpy, GIL, error handling (6-8 hrs)

- (1-2 hrs) Read PyO3 error-handling guide and rust-numpy's `PyReadonlyArray1` examples. Write the `DispatchError` enum with `thiserror` and its `From<DispatchError> for PyErr` impl by hand.
- (2-3 hrs) Wrap Week 2's LP solver in a `#[pyfunction]`: `PyReadonlyArray1<f64>` for prices in, `allow_threads` around the build+solve, `into_pyarray` for the three output arrays out. Get it callable from Python via `maturin develop`.
- (1-2 hrs) Run all 4 golden cases plus the negative-price and simultaneous-charge/discharge cases (acceptance criteria 1-4, 6 from `M1_python_core.md`) against the Rust extension, compare to `lp.py` output directly in a Python script.
- (1 hr) Benchmark the T=17,520 case against the 30-second budget (acceptance criterion 7). If it's not comfortably under, this is the point to evaluate the `highs-sys` raw-array stretch goal rather than guessing.
- Delegate to the agent this week: the test-fixture loading code, any pytest glue needed to call the compiled extension from the existing test suite.

### Week 4: Property tests, review gate, polish, ship (5-7 hrs)

- (1-2 hrs) Port acceptance criterion 5 (SoC bounds, dynamics residual, revenue reconciliation) as property tests; delegate the harness, hand-verify the invariants match the spec.
- (1 hr) Run the review-gate self-quiz from section 3 against the full week's diff before merging: explain what each function does and why, what would break under a horizon-length change, what you'd have gotten wrong solo.
- (1-2 hrs) Delegate CI wiring (if in scope for M4), README/results-table writeup, and final `ruff`/`mypy`/`clippy` cleanup pass.
- (1-2 hrs) Buffer for whatever broke. There's always something; don't schedule this week at 100% utilization.
- Stretch, only if ahead of schedule: the `highs-sys` raw-CSC-array version as a second implementation to diff against the `highs`-crate version, purely for the unsafe-Rust rep.

Total: 22-31 hrs of the 24-32 hr budget, leaving slack for the inevitable rustc fights in week 2-3.
