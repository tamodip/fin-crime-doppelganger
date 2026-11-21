# Track 2 metamorphic stress results

Each scenario transformed the development corpus into a temporary copy, re-ran all 819 hits, compared the outputs, and deleted the copy. Results cover only the listed meaning-preserving transformations; they do not predict hidden-set accuracy. The report contains aggregate counts only.

| Transformation | Changed input values | Decision stable | Reason code stable | Customer resolution stable | Exact evidence IDs stable |
|---|---:|---:|---:|---:|---:|
| Date format changes | 217,831 | 819/819 | 819/819 | 819/819 | 819/819 |
| Name order changes | 128,364 | 819/819 | 819/819 | 819/819 | 702/819 |
| Name surface changes (case, accents, punctuation) | 145,305 | 819/819 | 819/819 | 819/819 | 819/819 |
| Country names to codes | 201,577 | 819/819 | 819/819 | 819/819 | 819/819 |
| Approved KYC-note paraphrases | 8,643 | 819/819 | 819/819 | 819/819 | 819/819 |
| All transformations combined | 701,451 | 819/819 | 819/819 | 819/819 | 702/819 |

## Interpretation

- **Policy-output drift was zero** in every scenario: no verdict, reason code, or resolved customer changed.
- In the name-order and combined scenarios, exact evidence-field IDs changed for 117 hits because equivalent name facts were represented through different source fields. Those were citation-path changes only; the cited facts still supported the same decision.
- The canonical development output was separately validated at **50/50 practice decisions with zero unsafe clearances**.
- The date scenario rewrote 217,831 recognized date strings, exercising partial dates and temporal comparisons in both structured data and narrative text.
- The combined scenario changed more than 701,000 field values, including 8,388 approved verification notes.

The transformations are a targeted robustness check, not a hidden-set simulation in the statistical sense. The unseen corpus may contain policy or data patterns not present here.
