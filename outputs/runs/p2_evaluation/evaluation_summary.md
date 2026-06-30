# TRACE-LAB held-out perturbation evaluation

- anomaly rows: 210
- triage rows: 102; abstain rows: 108 (abstain rate 0.5143)
- evaluable perturbations: 39
- detected perturbations: 39
- misattribution rows: 0
- negative controls: 65; false-positive rows on controls: 0 (rate 0.0)
- ambiguous perturbations: 4 (correctly abstained 8)
- lineage-broken perturbations: 5 (correctly abstained 2)
- UNKNOWN perturbations: 18 (correctly abstained 40, mis-triaged 0)

Per-category precision / recall (TRACE-LAB main):
- UNIT_CHANGE: precision 1.0, recall 1.0
- INTERFACE_MAPPING_ERROR: precision 0.9688, recall 1.0
- FIELD_SEMANTIC_CHANGE: precision 1.0, recall 1.0
- EXTRACTION_FAILURE: precision 1.0, recall 1.0
- TRUE_BUSINESS_CHANGE: precision 1.0, recall 1.0
- UNKNOWN: precision None, recall None

Comparison across methods:

| method | abstain_rate | FP rate on controls | misattribution |
|---|---|---|---|
| TRACE_LAB_MAIN | 0.5143 | 0.0 | 0 |
| B0_SINGLE_FIELD_RULES | 0.0 | 1.0 | 46 |
| B1_NO_LINEAGE_DETECTION | 0.0095 | 0.0 | 103 |
| B2_CHANGE_POINT_ONLY | 0.8619 | 0.0 | 19 |
| B3_SITE_MAPPING_TABLE | 0.0 | 1.0 | 46 |

TRIAGE rows are advisory human-review recommendations, not confirmed causal attributions.

