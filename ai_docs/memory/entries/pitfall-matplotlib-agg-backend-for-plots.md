---
name: matplotlib-agg-backend-for-plots
description: src/bess/viz/plots.py must force the Agg backend; default backend can't render headless in CI
type: pitfall
source_adw_ids: [27b2b22d, cea65174, 325296bb, 6f498150]
date: 2026-07-29
---

matplotlib's default backend on a dev Mac is the interactive `macosx` backend, which cannot render in CI's headless environment. src/bess/viz/plots.py must call `matplotlib.use('Agg')` before importing pyplot so PNG rendering works identically on a dev machine and in CI. Relevant to any future plotting code (M2 dashboard, additional chart types).
