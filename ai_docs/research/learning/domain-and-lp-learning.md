# Domain and LP Learning Plan: ERCOT/BESS Fluency + Linear Programming Intuition

Purpose: build genuine ERCOT/BESS market fluency and real LP intuition (not
"the solver said so"), using bess-optimizer's own code, specs, and README
numbers as the curriculum wherever possible. Compiled 2026-08-01.

## TLDR

- The single best domain document is free and non-obvious: Potomac
  Economics' 2024 State of the Market Report for ERCOT (the Independent
  Market Monitor's own filing) has a dedicated Energy Storage Resources
  section (pp. 20 to 26) with regulator-grade revenue and AS-participation
  data, no login, no paywall.
- ERCOT BESS revenue mix has swung hard: multiple sources agree ancillary
  services fell from roughly 84 to 85 percent of battery revenue in 2023 to
  roughly 40 to 48 percent by 2024 to 2025, as arbitrage share rose and AS
  prices compressed (ECRS average clearing price alone fell from $76.77/MWh
  in 2023 to $9.62/MWh in 2024, per Potomac Economics). Sources disagree on
  the exact split because of differing methodology; explaining why they
  disagree is more interview-credible than reciting one number.
- HiGHS (the solver this repo already uses via highspy) ships its own docs
  on shadow prices, KKT conditions, and sensitivity ranging, and the repo's
  code never reads them today: `optimizer/lp.py` and `optimizer/as_lp.py`
  only ever pull `col_value` and `getObjectiveValue()`, never
  `row_dual`/`col_dual`. Extracting a dual value yourself, by hand, against
  a golden test the repo already has, is the fastest path to real duality
  intuition.
- The project's own LP structure gives at least eight exercises for free:
  the M1 goldens (objective values 180.0, 175.0, 50.0), the M2 TB4 capture
  rate (0.547), and the M3 result that NONSPIN earns exactly $0.00 are all
  derivable by hand from the constraint algebra in specs/M1_python_core.md
  and specs/M3_ancillary_services.md before ever running the solver.
- Two Substack/podcast leads in the original brief do not check out: "Tim
  Ohlenburg" has no ERCOT/energy Substack (the real Tim Ohlenburg found in
  search is an unrelated UCL economist), and Modo Energy's podcast is called
  "Transmission," not "Battery Storage Bites." Drop both names from any
  interview answer.

---

## 1. Domain resource shortlist: ERCOT market mechanics and BESS revenue economics

### Reading order

**Week 1, all free:**

1. ERCOT, [Wholesale Markets 101](https://www.ercot.com/files/docs/2023/07/07/2023_07-wholesale-101.pdf) (PDF, Jul 2023). Seven modules: intro, real-time dispatch and pricing (SCED), forward markets (DAM), energy settlements, congestion, ancillary services, system capacity. This is the actual "ERCOT 101" document; it is buried under a training-course subpage rather than linked from the main nav, which is why it is easy to miss.
2. Modo Energy, ["How does a battery energy storage system make money?"](https://modoenergy.com/research/en/how-does-battery-energy-storage-make-money) (article, free, updated Jul 2026). Maps the vocabulary from step 1 onto the three BESS revenue streams: arbitrage, ancillary services, capacity.
3. Potomac Economics (ERCOT's Independent Market Monitor), [2024 State of the Market Report for the ERCOT Electricity Markets](https://www.potomaceconomics.com/wp-content/uploads/2025/06/2024-State-of-the-Market-Report.pdf) (PDF, free, no login, published May 2025, about 110 pages). Read at minimum: the Executive Summary, Section II.E (Energy Storage Resources, pp. 20 to 26, with a Total and Normalized ESR Revenue chart for 2020 to 2024 in $/kW-yr and an ESR-share-of-AS-by-product chart), and Section III.D (Ancillary Services Market, pp. 44 onward, with 2020 to 2024 clearing-price tables). This is the highest-value document in this whole list: free, current, regulator-grade, and plainly written.
4. Gridstatus.io, ["Batteries have Reshaped ERCOT's Ancillary Services Procurement"](https://blog.gridstatus.io/batteries-ercot-ancillary-services-2024/) (article, free, Jan 16 2025, by Connor Waldoch). Ties the AS-saturation narrative together in plain technical language.
5. Modo Energy, ["ERCOT battery storage in 2026: 7 things to watch"](https://modoenergy.com/research/en/ercot-battery-storage-2026-things-to-watch) (article, free, updated Jul 2026). Brings the picture current: RTC+B, data-center load growth, the 2-hour duration premium, financing environment.

**Weeks 2 to 3, more depth, mix of free and paywalled:**

6. Gridstatus, ["RTC+B, 60 Days Later in ERCOT"](https://blog.gridstatus.io/rtc-b-60-days-later-in-ercot/) (free, early 2026). ERCOT's Real-Time Co-optimization plus Batteries market redesign went live December 5, 2025; this is the post-mortem of its first two months. Given how structurally important and current this change is, treat it as a must-read.
7. Gridstatus, ["ERCOT's 4CP Summer Demand Roller Coaster Takes Off as Storage Flips Outcomes"](https://blog.gridstatus.io/ercot-4cp-2025-june/) (free, Jun 19 2025). Explains how battery charging, treated as Wholesale Storage Load (WSL), distorts the 4CP transmission-cost-allocation intervals. Niche and genuinely differentiated interview material.
8. Gridstatus, ["Exploring extreme prices in ERCOT with Grid Status"](https://blog.gridstatus.io/exploring-extreme-prices-in-ercot-with-grid-status/) (free, spring 2025). Scarcity-pricing case study built around the February 19, 2025 nodal spike to roughly $30,000/MWh, tied to a specific battery asset.
9. Gridstatus, ["Two Weeks of Firsts in Texas: ECRS and New Records"](https://blog.gridstatus.io/ecrs-first-two-weeks/) (free, Jun 30 2023). Explains the ECRS product from its own launch, useful given ECRS is the largest single AS revenue line in this repo's M3 fixture.
10. Luminary Strategies (Arushi Sharma Frank), Substack, ["Revenue Unlock for ERCOT Batteries"](https://luminarystrategies.substack.com/p/understanding-metering-unlocks-batteries) (free). Covers Wholesale Storage Load metering designation and how it can swing a 250 MW / 1 GWh battery's opex by more than $6M/yr. The author is a real ERCOT market-design practitioner; this is exactly the kind of granular mechanism knowledge that reads as fluency rather than surface reading.
11. Modo Energy podcast, "Transmission" (hosted by Ed Porter, weekly, free, [Spotify](https://open.spotify.com/show/72xGXuV2vYokrR0jQGEcfU), 178+ episodes). Two specific ERCOT episodes worth prioritizing: ["Battery storage optimization in ERCOT with Mike Kirschner (Habitat Energy)"](https://modoenergy.com/research/podcast-battery-energy-storage-optimizer-habitat-energy-mike-kirschner-transmission) (an optimizer's-eye view of ERCOT dispatch strategy, directly relevant to this repo's LP), and ["The state of storage in ERCOT with Brandt Vermillion (ERCOT Market Lead)"](https://modoenergy.com/research/podcast-battery-energy-storage-buildout-ercot-brandt-vermillion-) (from ERCOT staff directly).
12. Modo Energy paywalled deep dives (free signup unlocks at least a substantive preview): ["ERCOT & CAISO BESS: The evolving revenue stack (June 2025)"](https://modoenergy.com/research/en/ercot-caiso-june-2025-revenue-stack-batteries-bess-energy-arbitrage-nodal-price-locational-marginal-price-transmission-congestion-price-spreads), ["ERCOT: Annual battery energy storage revenue report 2024"](https://modoenergy.com/research/en/ercot-battery-energy-storage-revenues-energy-markets-ancillary-services-capacity-location-owners-operators-annual-report-2024), ["ERCOT: What did BESS revenues look like in 2023?"](https://modoenergy.com/research/ercot-battery-energy-storage-systems-annual-revenues-2023-bess-index-ancillary-services-arbitrage-ecrs), and ["ERCOT: How to maximize revenues across Ancillary Services and Energy"](https://modoenergy.com/research/en/ercot-battery-energy-storage-ancillary-service-offers-volumes-prices-saturation-revenues-strategy-2025) (bidding-strategy depth, the "why" rather than the "what").

**Ongoing, background reading, no rush:**

13. Lazard, [Levelized Cost of Energy+ / LCOS v18.0 / v10.0](https://www.lazard.com/media/eijnqja3/lazards-lcoeplus-june-2025.pdf) (PDF, free, Jun 2025). Not ERCOT-specific, but the industry-standard cost benchmark everyone in the space cites. US storage LCOS: $155/MWh (2023) down to $104/MWh (2024) down to $93/MWh (2025).
14. Steven Stoft, *Power System Economics: Designing Markets for Electricity* (Wiley-IEEE Press, May 2002, ISBN 0-471-15040-1, about 496 pages). Confirmed as the standard academic text: five parts running from economic and engineering fundamentals through reliability policy, DAM/RT market design, market power, and network effects. No legitimate free copy exists; the author's own site (stoft.com/books-and-papers) links other Stoft works free but sends this one to Amazon only, and PDF copies circulating on Scribd, PDFCoffee, and Silo.tips are unauthorized, not legitimate, do not use them. It is dense and 2002-vintage (it predates BESS as a market participant entirely), so treat it as a long-term deep-dive: read Parts 1 through 3, skim the rest, not near-term interview prep.
15. Davis W. Edwards, *Energy Trading and Investing*, 2nd ed. (McGraw-Hill, ISBN 9781259835384). Has an "Electricity Storage" chapter and a "Levelized Cost of Entry" section, but it is a broad multi-commodity trading and derivatives textbook (gas, oil, coal, weather derivatives, VaR, options pricing), not ERCOT- or BESS-specific. Lower priority than the free Potomac Economics report; useful only if Travis wants broader commodities-trading fluency beyond ERCOT/BESS.

**Reference only, not first-pass learning:**

16. ERCOT, [Nodal Protocols](https://www.ercot.com/mktrules/nprotocols) and [Market Guides](https://www.ercot.com/mktrules/guides) (free, always current). The actual rulebook (Verifiable Cost Manual, Nodal Operating Guide, and similar). Dense reference material, good for look-up, bad for a first pass; this confirms the brief's hypothesis that ERCOT.com is hard to navigate for newcomers.
17. ERCOT, [2024 Biennial Report on the Operating Reserve Demand Curve (ORDC)](https://www.ercot.com/files/docs/2024/10/31/2024-biennial-ercot-report-on-the-ordc-20241031.pdf) (PDF, free, Oct 31 2024). ERCOT's own ORDC primer, statutorily mandated so it is written to be explainable to non-specialists.
18. ERCOT [training course catalog](https://www.ercot.com/services/training/courses): most instructor-led courses run about $650, officially scoped to "Market Participants," with no confirmation of open access for outside job-seekers. Not worth the money or time; the free 101 PDF and the Potomac Economics report cover the same ground at zero cost.

### Verified ERCOT BESS revenue-mix numbers, 2023 to 2025

| Metric | Value | Source |
| --- | --- | --- |
| 2023 annual BESS revenue | about $196/kW | Modo Energy |
| 2024 annual BESS revenue | $55/kW (down 71% YoY) | Modo Energy |
| 2023 annual BESS revenue (alt.) | $149/kW | Enverus, via [pv magazine](https://pv-magazine-usa.com/2025/11/21/battery-energy-storage-revenues-for-ancillary-services-fall-nearly-90-in-ercot/) |
| 2025 annual BESS revenue (projected) | $17/kW | Enverus |
| AS share of BESS revenue, 2023 to 2025 | 84% down to 48% | Enverus |
| AS share, 2023 to 2024 | 85% down to about 40% (so about 60% arbitrage by 2024) | Modo Energy, via [energy-storage.news](https://www.ess-news.com/2025/09/23/arbitrage-remains-leading-use-case-for-us-grid-scale-batteries/) |
| Arbitrage share, trailing 12 months to June 2025 | 25% up to 76% | Modo Energy |
| AS revenue, Oct 2024 to Oct 2025 | $1.52/kW-mo down to $0.50/kW-mo | Modo Energy |
| June 2025 monthly revenue, ERCOT vs CAISO | $3.01/kW vs $2.73/kW | Modo Energy |
| H1 2025 fleet-wide revenue mix | AS 42%, RT energy 40%, DA energy about 18% | [Tyba Energy](https://www.tyba.ai/resources/ercot-storage-performance/ercot-storage-performance-h1-2025/) |
| H1 2025 revenue, median vs top-20 asset | $2.13/kW-mo vs $4.63/kW-mo | Tyba Energy |
| EIA 2024, national | 41% of assets primarily arbitrage, 24% primarily frequency regulation | [EIA](https://www.eia.gov/todayinenergy/detail.php?id=66164) |
| EIA 2024, ERCOT-specific | 50% of ERCOT's 8.1 GW primarily used for arbitrage | EIA |
| ESR share of ERCOT AS, 2024 | Reg-Up 84%, Reg-Down 77%, RRS 39% | Potomac Economics IMM report, p. 22 |
| ECRS average clearing price, 2023 to 2024 | $76.77/MWh down to $9.62/MWh | Potomac Economics IMM report |
| Total AS cost to load, 2023 to 2024 | $3.74/MWh down to $0.98/MWh | Potomac Economics IMM report |
| ESR installed capacity, end of 2024 | 9,505 MW, average duration 1.6 hours | Potomac Economics IMM report, pp. 21 to 22 |
| ERCOT installed battery capacity | about 11 GW (mid-2025) up to 14.96 GW (Q1 2026) | Modo Energy / Enverus |
| US storage LCOS | $155/MWh (2023) down to $104/MWh (2024) down to $93/MWh (2025) | Lazard |

Sources disagree on the exact AS-versus-arbitrage split (Enverus reports 48%
AS share by late 2025; Modo's trailing-12-month figure implies closer to
24%) because of differing methodology: fleet-wide average versus median
asset, monthly-settled versus trailing-12-month, actual versus projected,
and different underlying asset samples. Being able to explain why the
numbers diverge is a stronger interview answer than picking one number and
reciting it.

### Verified but not worth citing

- **"Battery Storage Bites" podcast**: does not exist. Modo Energy's actual podcast is "Transmission," hosted by Ed Porter.
- **Tim Ohlenburg**: no ERCOT/energy Substack exists under this name. The real Tim Ohlenburg found in search is a UCL PhD candidate/economist working on algorithmic social-protection targeting, an unrelated field. Drop this lead entirely.
- **RMI**: general storage/grid content exists, nothing ERCOT-specific and quantified enough to cite over the Potomac Economics report.
- **Wood Mackenzie**: public releases cover installation capacity (GW/GWh) trends well; no free, ERCOT-specific revenue-stack report was found (their granular data is subscription-only). Cite them for buildout/capacity stats only, not revenue mix.
- **Aurora Energy Research**: has an ERCOT topic page but no specific free ERCOT-BESS revenue-stack report could be verified.
- **S&P Global**, "Battery stampede spurs sunny storage economics in ERCOT": exists but paywalled, only usable via free write-ups that cite it.

---

## 2. LP intuition resource shortlist

### Reading order

1. **Geometric intuition first.** [lpviz.net](https://lpviz.net) (paper: [arxiv.org/abs/2604.27518](https://arxiv.org/abs/2604.27518)), free, open-source: draw a feasible region and objective vector directly, no coefficient entry, and compare Simplex versus Interior-Point versus Primal-Dual Hybrid Gradient versus the central path live, including a 3D mode showing the complementarity gap and KKT residual in real time. Follow with the [miniwebtool Linear Programming Solver](https://miniwebtool.com/linear-programming-solver/) (free) for a couple of 2-variable examples with stepwise simplex tableaux, a 5-minute refresher rather than deep study. Then [GILP](https://github.com/engri-1101/gilp) (`pip install gilp`, free, CC BY-NC-SA), a Cornell teaching tool that builds LPs from NumPy arrays, runs revised simplex with Phase I, and generates an interactive Plotly HTML with a slider to step through iterations; it runs inline in Jupyter, a natural fit since this repo is already Python.
2. **Economic and duality intuition.** MIT 15.053, ["Duality in Linear Programming" (AMP Chapter 4)](https://web.mit.edu/15.053/www/AMP-Chapter-04.pdf), free PDF. Derives shadow prices from a resource-allocation story before formalizing anything, and explains complementary slackness as "unused resources are worthless" rather than as a bare theorem; probably the best first duality reading. Follow with IIT Bombay CS435, [Lecture 15: Complementary Slackness](https://www.cse.iitb.ac.in/~sundar/linear_optimization/lecture15.pdf), free PDF, a concise worked-example treatment. Then the [MOSEK Modeling Cookbook](https://docs.mosek.com/modeling-cookbook/index.html) (free, no login, release 3.4.0, Nov 2025), specifically the [Linear](https://docs.mosek.com/modeling-cookbook/linear.html) and [Duality](https://docs.mosek.com/modeling-cookbook/duality.html) chapters (section 2.4 covers duality and shadow prices/sensitivity explicitly, section 2.3 covers Farkas' lemma as an infeasibility-diagnosis story), moderately beginner-friendly early on and more rigorous later.
3. **Practical solver mechanics, using the actual solver this repo runs.** HiGHS's own docs: the [Terminology page](https://ergo-code.github.io/HiGHS/stable/terminology/) explicitly defines "dual values associated with constraints are often referred to as shadow prices or fair prices" and defines reduced costs and Lagrange multipliers in HiGHS's own vocabulary, directly mapping to what `solver.getSolution()` returns in this repo's code. The [Feasibility and Optimality (KKT) guide](https://ergo-code.github.io/HiGHS/stable/guide/kkt/) states the five KKT conditions HiGHS actually checks, including complementarity `x^T s = 0`, and its tolerance handling; this is complementary slackness as literally implemented in this project's solver, and is the single highest-value "connect the math to my own code" document found. The [ranging/sensitivity options](https://ergo-code.github.io/HiGHS/dev/options/definitions/) (`--ranging`) describe cost ranging, bound ranging, and RHS ranging, the concrete sensitivity-analysis output HiGHS can compute, directly relevant to "why did the solver pick this vertex" and how far prices or dispatch can move before the basis changes. Read these while poking at your own `highspy` model's dual, reduced-cost, and ranging output, ideally right after step 2 so the vocabulary is already familiar.
4. **Degeneracy, "why did the solver pick this vertex."** Deliberately construct a degenerate toy LP in GILP or lpviz and watch multiple bases map to the same vertex or objective value; this is the practical version of the M3 spec's own documented degeneracy (at zero MCPC, the solver may return arbitrary award splits with identical revenue, specs/M3_ancillary_services.md, "Known gotchas" item 3). For the formal picture, Nimrod Megiddo's short note, ["A Note on Degeneracy in Linear Programming"](https://theory.stanford.edu/~megiddo/pdf/notedege.pdf) (free PDF), terse rather than intuitive, an optional deep-dive, not a first read.
5. **Formulation depth, ongoing reference, not a front-to-back read.** H.P. Williams, *Model Building in Mathematical Programming*, 5th ed. (Wiley, 2013, ISBN 9781118443330). Confirmed as the current edition; the publisher description explicitly states it "emphasizes the importance of building and interpreting models rather than the solution process," making it the canonical practitioner reference for formulating LPs with intuition rather than proving theorems about them. New copies run $67 to $82, used from about $42, and it can be borrowed free at [archive.org](https://archive.org/details/modelbuildinginm0000will) with a free preview on [Google Books](https://books.google.com/books/about/Model_Building_in_Mathematical_Programmi.html?id=YJRh0tOes7UC). Boyd and Vandenberghe, *Convex Optimization* (Cambridge University Press, 2004), full legal free PDF at [web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf) (Cambridge explicitly allows the authors to host it free): Chapter 2 covers polyhedra and halfspace geometry, Chapter 5 covers Lagrangian duality, weak/strong duality, and complementary slackness rigorously with worked examples; more proof-oriented than Williams, the go-to "go deeper" reference. Stanford's [EE364a course site](https://see.stanford.edu/Course/EE364A) has the full free video lectures and problem sets if a slower, structured pass is wanted, though LP appears there only as one instance of the broader convex-problem framework, not a standalone LP course.
6. **Energy-market bridge, do this last, once the above feels solid.** See Section below.

### Best resources connecting LP duals to electricity market pricing

This is the highest-value bridge for Travis, since his own M3 AS
co-optimizer LP produces exactly this kind of shadow price (a dual variable
on an availability, coupling, or adequacy constraint), and ERCOT's real DAM
and RTM clearing prices are themselves dual variables from ERCOT's own
SCED/DAM LP.

1. **Papavasiliou, *Optimization Models in Electricity Markets*, free companion slide decks**: [Appendix A, Introduction to Linear Programming](https://ap-rg.eu/wp-content/uploads/2024/09/App-Α-Introduction-to-linear-programming.pdf), [Chapter 4, Economic Dispatch](https://ap-rg.eu/wp-content/uploads/2024/05/Ch-4-Economic-dispatch.pdf), and [Chapter 5.2, Locational Marginal Pricing](https://ap-rg.eu/wp-content/uploads/2024/05/Ch-5.2-Locational-marginal-pricing.pdf) (landing page: [ap-rg.eu](https://ap-rg.eu/courses/optimization-models-in-electricity-markets-book/)). The book itself is paid (Cambridge University Press, about $389 list); skip it and use the free slides. Chapter 5.2 states explicitly that "locational marginal prices emerge as dual variables associated with power flow balance constraints," the most direct and currently free treatment found of the exact pattern this repo's AS co-optimizer generalizes: MCPC as the dual of the AS requirement/adequacy constraint, instead of LMP as the dual of the energy balance constraint. Somewhat proof-heavy, dense notation, but exactly the right subject.
2. **ERCOT's own live shadow-price data**: [Market Prices](https://www.ercot.com/mktinfo/prices), [DAM dashboards](https://www.ercot.com/mktinfo/dam), [DAM Clearing Prices for Capacity (MCPC) data product](https://www.ercot.com/mp/data-products/data-product-details?id=NP4-188-CD), and the [RTM Clearing Prices for Capacity dashboard](https://www.ercot.com/gridmktinfo/dashboards/rtmarketclearingpricescapacity), all free. These MCPC and LMP numbers are dual values from ERCOT's own SCED/DAM LP. Pulling real data here and comparing it to what your own M3 co-optimizer produces is the most concrete, zero-abstraction way to build this intuition, and it directly explains the zero-clearing-price degeneracy this repo already documents.
3. **MIT AMP Chapter 4 (Duality)**, listed above, as the connective tissue: not energy-specific, but the clearest plain-economics statement of why a dual variable equals "the marginal value of relaxing this constraint by one unit," the exact sentence that becomes "LMP is the cost of serving one more MW at this node" once substituted into the economic-dispatch context.

### Searched but not worth including

- **numberanalytics.com** guides on shadow prices and complementary slackness: confirmed AI-generated SEO content (byline literally reads "Sarah Lee, AI generated o4-mini"), thin sourcing, skip.
- **RPI (Mitchell) notes on multiple optima**: repeatedly failed to load across multiple attempts; unverified, don't rely on it without checking directly first.
- **lmpmarketdesign.com** (Scott Harvey / William Hogan archive): confirmed live and legitimate, but a static archive of FERC-level market-design policy papers, not an intuition-building resource; save for much later, if ever.
- **YouTube shadow-price explainers** ("Introduction to Shadow Prices," "Economic Interpretation of the Dual LP"): existence confirmed via search, content not frame-verified in this session; fine as a 15-minute primer, no more.

---

## 3. Repo-grounded exercises

Grounded in `specs/M1_python_core.md`, `specs/M1b_optimizer.md`,
`specs/M2_rolling_and_benchmarks.md`, `specs/M3_ancillary_services.md`, and
`src/bess/optimizer/lp.py` / `src/bess/optimizer/as_lp.py`. The base LP
(M1): variables `c_t` (charge, MW), `d_t` (discharge, MW), `s_t` (SoC, MWh,
end of interval); maximize `sum p_t * (d_t - c_t) * dt`; SoC recursion
`s_t = s_{t-1} + eta_c * c_t * dt - d_t * dt / eta_d`; bounds
`0 <= c_t, d_t <= power_mw`, `0 <= s_t <= energy_mwh`; no terminal SoC
constraint. Default battery: 100 MW / 200 MWh, efficiency 0.927 each way
(sqrt(0.86), 86% round trip). The M3 co-optimizer adds award variables
`a_pt >= 0` per product per interval, coupled into the same power budget as
energy dispatch and gated by SoC-based adequacy constraints (exact
formulation in `specs/M3_ancillary_services.md`).

**Notable gap worth exploiting**: neither `optimizer/lp.py` nor
`optimizer/as_lp.py` ever reads `solver.getSolution().row_dual` or
`col_dual`, only `col_value` and `getObjectiveValue()`. The project has
never looked at its own shadow prices. Exercise 5 fixes that.

1. **Hand-verify a golden by hand, before running the solver.** Take the
   M1b lossy-charge golden (`specs/M1b_optimizer.md`): T=24, hours 0 to 11
   at $10/MWh, hours 12 to 23 at $100/MWh, 1 MW / 2 MWh battery,
   `charge_eff=0.8`, `discharge_eff=1.0`, initial SoC 0. Work out by hand
   when to charge, how much, when to discharge, and derive the $175.0
   objective yourself (grid draw cost separately from discharge revenue: a
   2.5 MWh grid draw costs $25 at $10/MWh, a 2 MWh discharge earns $200 at
   $100/MWh). Then check against the golden test. This forces working the
   SoC recursion and efficiency losses by hand instead of trusting the
   solver.

2. **Predict TB4 capture before computing it.** Given TB4 = $572.55/day
   (the 4 highest hourly prices minus the 4 lowest, no efficiency
   adjustment, per `specs/M2_rolling_and_benchmarks.md`) and a 2-hour
   battery (100 MW / 200 MWh, round-trip efficiency 0.86), predict what
   fraction of TB4 the battery should capture on a typical day, before
   looking at the README's real 0.547 capture-rate figure. Reason from the
   fact that a 2-hour battery can only span 2 of the 4 highest and 2 of the
   4 lowest hours per single cycle (unless the price shape lets it cycle
   twice), and efficiency losses eat further into the spread. Write down a
   predicted range, then compare it to 0.547 and explain the gap.

3. **Explain the July 2023 100.0% foresight capture rate from LP
   structure, not luck.** The README states rolling equals perfect for
   HB_NORTH, July 2023, because "the LP naturally returns state of charge
   to 0 at every local day boundary" that month. Using the fact that there
   is no terminal SoC constraint (`specs/M1_python_core.md`) and that, with
   lossy efficiency, idling is strictly optimal on flat or near-flat price
   stretches (the M2 "zero-profit ties" gotcha), explain why a myopic
   one-day-lookahead operator loses nothing that specific month. Then
   predict where the gap should open up. The duration sweep already shows
   it starting to: $193,184.32/MW-yr perfect versus $193,176.05/MW-yr
   rolling at 4-hour duration. Explain mechanically why longer duration is
   where persistence-forecast error starts to cost money.

4. **Derive the NONSPIN $0.00 result algebraically, not from running the
   code.** Using the up-adequacy constraint
   `sum_{p in UP} sustain_p * a_pt <= s_t * discharge_eff`, and NONSPIN's
   `sustain_hours=4.0` against a 200 MWh / 100 MW battery (max `s_t=200`,
   `discharge_eff=0.927`), compute the absolute ceiling on a NONSPIN award
   assuming the battery devotes its entire adequacy budget to NONSPIN
   alone. Show how tight that ceiling already is, then explain why, once
   REG_UP, RRS, and ECRS are all competing for the same `s_t * discharge_eff`
   budget in the same row, NONSPIN gets crowded out to exactly zero at the
   optimum: it has by far the largest `sustain_hours` coefficient per MW of
   any UP product, so it consumes the most adequacy budget per dollar of
   coupling relief, and every other UP product has a better MCPC-to-adequacy
   ratio in the July 2023 fixture. This is a real LP crowding-out result,
   not a bug (the README says exactly this).

5. **Extract and hand-verify a shadow price the codebase doesn't currently
   expose.** In a scratch script (not the frozen module), call
   `solver.getSolution()` after solving the M1b flat-price golden (T=24, all
   prices $50, efficiency 0.9/0.9) and read `row_dual` for the SoC dynamics
   row at some interior `t` (`0 < s_t < energy_mwh`, no bound binding).
   Confirm it is roughly 0: flat prices give no reason to value stored
   energy on the margin, consistent with the golden's own point that
   revenue is exactly 0.0. Then rerun on the negative-hour golden (T=24, one
   hour at -$50, battery 1 MW / 2 MWh, efficiency 0.9/0.9, objective 50.0)
   and read the dual for the SoC row immediately after the negative-price
   hour. It should be strongly positive: one more MWh sitting in the
   battery right after the cheap hour is worth real money, since it could
   have been bought at -$50 and held. Compare that dual's magnitude to a
   hand-computed marginal value and explain any gap caused by binding power
   or SoC bounds elsewhere in the horizon.

6. **Explain simultaneous charge/discharge at negative prices from LP first
   principles, using the actual constraint set.** The LP has no constraint
   forcing `c_t=0` or `d_t=0` (mutual exclusivity is explicitly deferred to
   a future MILP fix, `specs/M1b_optimizer.md`, "Out of scope"). At a deeply
   negative price `p_t`, the objective term `p_t * (d_t - c_t) * dt` makes
   increasing `c_t` (charging, i.e. buying) itself profitable, since you are
   paid to take energy; increasing `d_t` at the same time lets you resell
   part of what you just bought, net-losing only the round-trip efficiency
   gap while collecting the negative-price payment twice. Derive
   algebraically the price threshold below which simultaneous `c_t > 0` and
   `d_t > 0` is strictly profitable, given `eta_c = eta_d = 0.9`, and
   compare it to the deeply negative price used in `specs/M1b_optimizer.md`
   acceptance criterion 10.

7. **Reconcile the AS uplift's energy-leg cannibalization using the
   coupling constraints.** The README reports energy-only revenue of
   $970,937.15 falling to a co-optimized energy leg of only $567,376.46,
   even as total revenue (energy plus AS) rises 2.77x to $2,689,961.68. The
   co-opt LP shares one power/inverter budget between `(d_t - c_t)` and
   every UP award, and a separate one between `(c_t - d_t)` and REG_DOWN,
   so every MW committed to an AS award in an interval is a MW not
   available for arbitrage that hour. Using the revenue-mix table (ECRS
   60.1% of AS revenue at 14,623.9 MWh awarded, REG_UP 21.1% at 38,163.4
   MWh, REG_DOWN 12.7% at 52,581.9 MWh), estimate the implied $/MWh ECRS
   effectively earns per unit of coupling capacity it occupies, and compare
   that to the fixture month's realized energy arbitrage $/MWh. Show that
   ECRS clearly outbids the marginal arbitrage opportunity most hours,
   which is why total revenue rises even though the energy leg falls.

8. **Predict the direction of the AS uplift under a longer-duration
   battery, before checking any code.** Given that NONSPIN earns exactly
   $0 at 2-hour duration purely from adequacy crowd-out (exercise 4),
   predict qualitatively what happens to the revenue mix at 4-hour duration
   (`energy_mwh=400`, same 100 MW power, using the sweep config already in
   `config.toml`, `[sweep] durations_h = [1, 2, 4]`). Does NONSPIN's share
   of AS revenue rise? Does total AS uplift rise or fall relative to
   2.77x? Reason from the fact that the up-adequacy budget
   (`s_t * discharge_eff`) scales with `energy_mwh` while the up-coupling
   budget (`power_mw`) does not. Then, optionally, run `bess sweep` and
   `bess backtest --ancillary` at the 4-hour point to check the prediction.

---

## 4. Interview question bank

Ten questions a battery-storage company would plausibly ask, with a
pointer to where each is covered, in this repo and in the resource list
above.

1. **"Walk me through ERCOT's ancillary service products, what each is for
   operationally, and how their durations/response times differ."**
   Repo: `specs/M3_ancillary_services.md` `sustain_hours` table and
   `DEFAULT_AS_PRODUCTS` in `src/bess/models.py`. Domain: ERCOT's
   [Wholesale Markets 101](https://www.ercot.com/files/docs/2023/07/07/2023_07-wholesale-101.pdf)
   (module 6, Ancillary Services) and Gridstatus's
   [ECRS launch post](https://blog.gridstatus.io/ecrs-first-two-weeks/).

2. **"Has ERCOT battery revenue in 2023 to 2025 come mostly from energy
   arbitrage or ancillary services? What's driven the mix shift?"** Repo:
   README AS uplift section (2.77x uplift, AS revenue $2,122,585.22 versus
   energy revenue $567,376.46 in the co-opt fixture) as an illustrative LP
   output. Domain: the revenue-mix table in Section 1 above (AS share fell
   from roughly 84 to 85% in 2023 to roughly 40 to 48% by 2024 to 2025 per
   Modo Energy and Enverus); a strong candidate states unprompted that this
   repo's numbers are a single-hub, single-month, perfect-foresight,
   price-taker illustration, not a fleet-level statistic.

3. **"What is a shadow price, or dual value, and how does it map to a real
   electricity market concept like LMP or an AS clearing price?"** Repo:
   exercise 5 above (extract `row_dual` from HiGHS by hand). LP resources:
   MIT AMP Chapter 4, HiGHS's
   [Terminology](https://ergo-code.github.io/HiGHS/stable/terminology/) and
   [KKT guide](https://ergo-code.github.io/HiGHS/stable/guide/kkt/),
   Papavasiliou's free [Chapter 5.2 slides](https://ap-rg.eu/wp-content/uploads/2024/05/Ch-5.2-Locational-marginal-pricing.pdf)
   on LMP as a dual variable.

4. **"Why would a battery simultaneously charge and discharge in the same
   interval? Is that ever rational?"** Repo: exercise 6, `specs/M1b_optimizer.md`
   acceptance criterion 10, and the `optimizer/lp.py` docstring ("burning
   energy through efficiency losses is profitable at negative prices").

5. **"Explain LP degeneracy. Why might a solver return different award
   splits for the same total revenue?"** Repo:
   `specs/M3_ancillary_services.md` "Known gotchas" item 3, and the M3b
   acceptance criteria (the zero-price equivalence golden asserts objective
   only, never raw awards; memory note `lp-optimizer-degeneracy-in-tests`).
   LP resources: GILP or lpviz for a constructed degenerate toy LP, and
   Megiddo's note for the formal picture.

6. **"What's the difference between energy-only arbitrage value and AS
   capacity value for a battery, and why can't you just add them up
   naively?"** Repo: the README scope note ("energy-only understates...
   AS co-optimized overstates... the honest number lies between") and
   exercise 7 (the coupling-constraint cannibalization, energy leg falling
   from $970,937.15 to $567,376.46 under co-optimization).

7. **"How does battery duration, 2-hour versus 4-hour, affect which AS
   products it can economically participate in?"** Repo: exercises 4 and 8
   (NONSPIN's 4-hour sustain requirement is structurally unaffordable at
   2-hour duration; the up-adequacy constraint scales with `energy_mwh`,
   not `power_mw`).

8. **"What is TB2/TB4 and why do people use it as an industry benchmark
   instead of just quoting revenue?"** Repo: `specs/M2_rolling_and_benchmarks.md`
   benchmark definitions, README TB2 ($332.95) and TB4 ($572.55) mean-daily
   numbers, TB4 capture (0.547).

9. **"What's the difference between perfect foresight and a realistic
   (rolling, day-ahead) dispatch, and how big is the gap in practice?"**
   Repo: README M2 section (rolling versus perfect capture rate 100.0% for
   the July fixture, but the duration sweep shows the gap opening at 4
   hours) and exercise 3.

10. **"If ERCOT prices go negative, what should a battery do, and why do
    negative prices happen at all?"** Repo: exercise 6 and the M1b
    negative-hour golden (T=24, one hour at -$50, objective 50.0). Domain:
    Gridstatus's [extreme prices post](https://blog.gridstatus.io/exploring-extreme-prices-in-ercot-with-grid-status/)
    and ERCOT's [ORDC biennial report](https://www.ercot.com/files/docs/2024/10/31/2024-biennial-ercot-report-on-the-ordc-20241031.pdf)
    for the scarcity-pricing and oversupply context behind negative and
    extreme prices.
