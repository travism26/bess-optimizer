---
name: metrics-json-unqualified-filename-collision
description: bess backtest wrote perfect and rolling metrics to the same unqualified filename, overwriting each other
type: pitfall
source_adw_ids: [325296bb, 6f498150, 3034ec63, d39c4d18, 8694b681]
date: 2026-08-01
---

`bess backtest` originally wrote metrics to a single unqualified path `{location}_metrics.json` (src/bess/cli.py) regardless of mode, so running perfect then rolling (or vice versa) for the same location silently overwrote the first mode's output. M2b needed both modes' metrics simultaneously for capture-rate calculations, so it added a second, mode-qualified file `{location}_metrics_{mode}.json` written alongside the existing unqualified one, leaving old filenames/tests untouched. M3c's `--ancillary` flag followed the convention correctly from the start, adding a further-qualified `{location}_metrics_{mode}_ancillary.json`. Any future command needing outputs from multiple modes/variants of the same location (e.g. more sweep dimensions, M4 engine parity) should write mode/variant-qualified filenames from the start rather than relying on a single shared path that the next run can clobber.
