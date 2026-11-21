# ClearTrace — financial crime screening resolver

ClearTrace is a deterministic, evidence-first entity-resolution system for Track 2. It resolves messy customer records, evaluates the matching watchlist entity against the supplied SOP, and writes an auditable decision for every hit.

## What makes it robust

- Follows account, login, email, onboarding, and KYC links; typo-aware candidate retrieval is used only when direct links are absent.
- Groups duplicate customer records only with multiple identity signals. A shared phone or address alone never merges people; conflicting plausible records stay ambiguous.
- Uses approved identity checks above declared details. Rejected or expired checks cannot establish identity.
- Handles aliases, order changes, initials, joined/split names, accents, placeholders, entity-type conflicts, partial dates, age-at-event checks, incorporation timing, death dates, and country variants conservatively.
- Returns `REVIEW` when the evidence is incomplete or contradictory. Every result carries a policy reason code, a short explanation, the resolved customer record, and source IDs.
- Uses Python 3 standard libraries only. It makes no model or network calls and has no inference cost.

## Run the submission

```sh
system/run <data-folder> <output.jsonl>
python3 validate.py --data <data-folder> --output <output.jsonl> --score <data-folder>/practice_labels.jsonl
```

The included `output/dev.jsonl` has 819 lines, validates with zero structural problems, and scores 50/50 on the 50 supplied practice labels with zero unsafe clearances. That is practice-set performance, not a prediction of unseen-set accuracy. A full run took 5.49 seconds on the development machine.

## Stress tests and edge cases

Run the independent policy tests and meaning-preserving input transformations:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 system/stress.py <data-folder> --scenario combined --report reports/metamorphic-stress.md
```

The test suite includes rare and adversarial boundaries: deceased dates, same-day event ambiguity, post-report incorporation, rejected/expired KYC, note paraphrases, false duplicate links, shared-family contact details, ambiguous records, name token reuse, placeholder names, company biography dates, and partial-date uncertainty. The stress harness rewrites date formats, name order/surface, country names to codes, and approved KYC-note wording in temporary data copies, then checks decision, reason-code, customer-resolution, and evidence-reference stability. See `reports/` for measured results. These tests are invariance checks, not hidden-set score estimates.

## Audit viewer

The local viewer reads the supplied data and prediction file but binds to `127.0.0.1` only:

```sh
system/demo <data-folder> <output.jsonl> [port]
```

It has a searchable queue, decision filters, summary metrics, and a click-through trail covering the alert, customer resolution, account, KYC checks, notes, hit facts, decision, and cited evidence. The public Pages build contains only fictional examples from `system/demo.json`; it does not package the development dataset or the real development output.

## GitHub Pages

The Actions workflow deploys the fictional-only audit demo from `system/index.html` and `system/demo.json`. For the first deployment, set **Settings → Pages → Build and deployment → Source → GitHub Actions** for this repository. Later pushes to `main` redeploy automatically.
