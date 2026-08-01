---
name: metrics-json-unqualified-filename-collision
description: bess backtest wrote perfect and rolling metrics to the same unqualified filename, overwriting each other
type: pitfall
source_adw_ids: [325296bb, 6f498150, 3034ec63]
date: 2026-07-30
---

`bess backtest` originally wrote metrics to a single unqualified path `{location}_metrics.json` (src/bess/cli.py) regardless of mode, so running perfect then rolling (or vice versa) for the same location silently overwrote the first mode's output. M2b needed both modes' metrics simultaneously for capture-rate calculations, so it added a second, mode-qualified file `{location}_metrics_{mode}.json` written alongside the existing unqualified one, leaving old filenames/tests untouched. Any future command needing outputs from multiple modes/variants of the same location (e.g. more sweep dimensions, M4 engine parity) should write mode/variant-qualified filenames from the start rather than relying on a single shared path that the next run can clobber.
