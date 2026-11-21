# ClearTrace — Track 2 screening resolver

ClearTrace resolves both sides of a screening hit, applies the supplied identity SOP, and emits a deterministic, evidence-cited decision. It uses Python 3 standard libraries only; there is no model call, API key, network request, or per-hit inference cost.

## Run

```sh
system/run <data-folder> <output.jsonl>
```

From this repository, the development run is `system/run dev output/dev.jsonl`. The implementation reads only the supplied folder and writes one JSON object per hit. It is designed for Python 3.9+.

## How a decision is made

```text
alert links ──> candidate customer records ──> person-level identity facts
                         │                            │
                         └── KYC / account / notes ───┘
                                                      │
watchlist profile ──> names / DOBs / countries / dates┴──> SOP gates
                                                              │
                                 DIFFERENT_ENTITY / SAME_ENTITY / REVIEW
                                                              │
                                             reason + source IDs in JSONL
```

1. **Resolve the customer.** Direct account, login, email, onboarding, and KYC links are followed first. When a link is missing, candidate retrieval is typo-aware. Records are grouped only when multiple identity signals support the same person; shared phone or address alone never merges people. Conflicting plausible records remain ambiguous.
2. **Build an evidence-backed identity.** Approved identity checks outrank declarations. Rejected and expired checks are retained for the audit view but cannot establish identity. Notes are parsed only for supported verification facts. Search results are candidate discovery leads, not customer identity evidence.
3. **Resolve the listed person.** The engine considers the hit's structured names, aliases, DOBs and countries, plus safely parseable profile facts. Search-result DOBs require a strong name link. Company incorporation dates are kept separate from biography dates.
4. **Apply conservative SOP gates.** Contradictions are evaluated before confirmation. Partial dates remain intervals; an ordering is used only when it is certain. Confirmations require the policy's name plus DOB (people) or name plus country (companies). Missing or conflicting evidence leads to `REVIEW`.
5. **Cite the decision.** Reasons state the decisive facts and evidence IDs point to the specific customer, KYC, note, or hit fields used. Output ordering and evidence lists are deterministic.

## Robustness and auditability

Run the synthetic and policy-boundary unit suite:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Run hidden-set-style metamorphic stress checks against a local data folder:

```sh
python3 system/stress.py dev --scenario date_formats
python3 system/stress.py dev --scenario combined
```

The stress harness writes transformed data only into temporary directories, removes them after each run, and prints aggregate stability counts without record contents. Its transformations cover date formats, reordered and reformatted names, country codes, and paraphrased KYC notes. The checks measure invariance under those specific transformations; they are not an estimate of hidden-set accuracy.

The local evidence viewer is read-only and binds only to `127.0.0.1`:

```sh
system/demo
```

It presents a searchable decision queue and an audit trail from alert through customer resolution, account, identity checks, notes, hit facts, and cited evidence. The public static demo uses fictional examples in `system/demo.json`; it contains no development records.

## Example cases

The three fictional cases in `system/demo.json` illustrate the policy boundaries:

- **Clear mismatch:** the names agree, but an approved customer DOB conflicts with every DOB in the hit (`DOB_MISMATCH` / `DIFFERENT_ENTITY`).
- **Supported match:** reordered customer and hit names, DOB, and country agree without a contradiction (`NAME_DOB_LOCATION_MATCH` / `SAME_ENTITY`).
- **Human review:** names and country align, but neither side supplies a DOB, so identity is not confirmed (`INSUFFICIENT_DATA` / `REVIEW`).

## Runtime and cost

The engine is local, deterministic, and dependency-free. It has no model/API cost and does not send data over the network. The measured full development run took 5.49 seconds on the development machine, well inside the brief's 30-minute limit. See [`../reports/validation.md`](../reports/validation.md) for the practice-label and robustness results.
