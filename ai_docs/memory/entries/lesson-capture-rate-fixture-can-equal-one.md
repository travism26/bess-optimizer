---
name: capture-rate-fixture-can-equal-one
description: Foresight capture rate can legitimately equal exactly 1.0 on fixtures with a day-separable optimum
type: lesson
source_adw_ids: [325296bb, 6f498150, 3034ec63]
date: 2026-07-30
---

On the July 2023 fixture, M1's perfect-foresight optimal dispatch is day-separable (SoC returns to 0 at every Central day boundary), so M2a's rolling backtest with lookahead_days=1 reproduces perfect revenue bit for bit, giving a foresight capture rate of exactly 1.0, not just close to it. This is valid per the M2 master spec's corridor ((0,1] / sanity range [0.4, 1.0]) but is easy to mistake for a units/windowing bug, and a test asserting `capture < 1.0` would wrongly fail on this fixture. When writing capture-rate tests or README language against the July fixture, treat exactly 1.0 as expected and note the day-separability reason rather than assuming rolling always strictly underperforms perfect.
