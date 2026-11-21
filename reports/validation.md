# Validation record

Run date: 2026-11-21 (local development environment)

- Full development run: **819 output lines**, measured at **5.49 seconds** wall time.
- Organizer validator: **0 problems**.
- Practice labels: **50/50 decisions**, **0 unsafe clearances**, 100.0 decision score; reason-code and customer-record agreement were 100% on correct decisions.
- Unit/policy suite: **24 tests passed**.
- Local audit UI: page, summary, review queue, and evidence detail endpoints returned successfully; the viewer binds to `127.0.0.1` only.
- Metamorphic stress: **819/819** decisions, reason codes, and customer resolutions were stable under six scenarios: date formats, name order, name surface, country codes, KYC-note paraphrases, and all combined. Exact citation paths shifted in 117 records under name-order/combined rewrites; policy outputs were unchanged. Full aggregate results are in [`metamorphic-stress.md`](metamorphic-stress.md).

The source and synthetic demo use no external model and make no network request. The development corpus is excluded from the public repository.
