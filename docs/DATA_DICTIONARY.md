# DATA DICTIONARY — trace-lab-research

All tables are CSV with UTF-8, LF, header row, `keep_default_na=False`
semantics (empty string means "no value", never NaN). Timestamps are UTC
ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`). Empty `valid_to` means "still valid".
All data is synthetic; the generator seed is 20250110.

## lineage_nodes.csv (32 rows)

| Column | Type | Notes |
| --- | --- | --- |
| node_id | string `^N[0-9]{3}$` | primary key, unique |
| system | enum | ANALYZER / ETL / LIS / INTERFACE / REPORT |
| field_name | string | observable field label |
| semantic_definition | string | plain-language definition |
| unit | string | profile unit (`n/a` for non-numeric) |
| datatype | enum | numeric / string / enum / datetime |
| schema_version | enum | SCHEMA_V1 / SCHEMA_V2 |
| valid_from | timestamp | node becomes valid (V1 nodes from 2025-01-10; V2 nodes from 2025-06-01) |
| valid_to | timestamp or empty | node stops being valid; 24 of 32 V1 nodes close at the 2025-06-01 boundary, while eight long-lived V1 fields stay open-ended |

## lineage_edges.csv (40 rows)

| Column | Type | Notes |
| --- | --- | --- |
| from_node | string | source node id |
| to_node | string | target node id |
| transform_id | string `^T[0-9]{3}$` | transform label |
| rule_version | string | `rX.Y` rule version of the transform |
| valid_from / valid_to | timestamp | same version semantics as nodes |
| confirmed_by | string | fictional review role |
| source_file | string | fictional config source path |

One edge (`N030 → N029`) deliberately expires at 2025-12-31, creating the
lineage break exercised by the counter-example tests.

## schema_changes.csv (117 rows)

| Column | Type | Notes |
| --- | --- | --- |
| change_id | string `^C[0-9]{4}$` | primary key |
| affected_nodes | string | `;`- or `,`-separated node ids |
| change_category | enum | UNIT_REDEFINITION / INTERFACE_REMAP / SEMANTIC_REDEFINITION / EXTRACTION_PIPELINE_CHANGE / BUSINESS_CHANGE / NORMAL_CHANGE |
| submitted_at / approved_at / effective_at | timestamp | submitted <= approved <= effective |
| version | string | register row version |
| ticket_index | integer or empty | dropped by triage before scoring (anti-leak) |

`NORMAL_CHANGE` rows (65) are negative controls with no injected effect.

## field_profiles.csv (19 rows)

| Column | Type | Notes |
| --- | --- | --- |
| field_name | string | unique key, joins to nodes/observations |
| unit | string | expected unit |
| value_range | string | `lo..hi` inclusive |
| missing_rate | float 0..1 | expected missing fraction |
| time_window | string | era label of the profile |

## field_observations.csv (2020 rows)

| Column | Type | Notes |
| --- | --- | --- |
| observation_id | string `^OBS[0-9]{6}$` | unique |
| node_id | string | joins to lineage_nodes |
| observed_at_utc | timestamp | stream cadence ~3.5 days per node |
| raw_value | string | as-extracted value (may fail format under garble) |
| parsed_value | string | parsed numeric (may be out of range) |
| reported_unit | string | unit attached to the record |
| source_system | string | system that emitted the row |
| record_version | string | stream row version |

## Ground truth (evaluation only — never read by triage)

### defect_tickets.csv (180 rows)

| Column | Type | Notes |
| --- | --- | --- |
| defect_id | string | unique |
| detected_at | timestamp | detection date |
| field_version | string | schema version at detection |
| symptom | string | free-text symptom |
| detection_method | string | how the ticket was opened |
| confirmed_category | enum | one of the six frozen categories |
| confirmed_at | timestamp | confirmation date |
| basis | string | confirmation basis |
| adjudicated_by | string | fictional review role |

Category distribution: INTERFACE_MAPPING_ERROR 48, UNIT_CHANGE 40,
EXTRACTION_FAILURE 30, FIELD_SEMANTIC_CHANGE 26, TRUE_BUSINESS_CHANGE 18,
UNKNOWN 18.

### perturbation_library.json (66 perturbations)

| Field | Notes |
| --- | --- |
| perturbation_id | `Pxxxx` unique |
| kind | mechanism label |
| node_id / window_start / window_end | where the effect was injected |
| change_id / defect_id | link into the register/tickets |
| true_category | the frozen category the perturbation simulates |
| ambiguous_pair | non-empty for the 4 near-coincident pairs |
| lineage_break | true for the 5 broken-chain injections |
| shift_magnitude | >0 for mean-shift injections |
| wrong_unit | unit string for unit injections |
| missing_fraction | >0 for dropped-row injections |
| garble_fraction | >0 for format-violating garble |
| out_of_range_fraction | >0 for out-of-range value injections |

Exactly one injection mechanism is active per perturbation.
Category counts: UNIT_CHANGE 10, INTERFACE_MAPPING_ERROR 15,
EXTRACTION_FAILURE 12, FIELD_SEMANTIC_CHANGE 7, TRUE_BUSINESS_CHANGE 4,
UNKNOWN 18.

### normal_control_index.csv (65 rows)

| Column | Notes |
| --- | --- |
| control_id | unique |
| change_id | the NORMAL_CHANGE register row |
| node_id | affected node |
| window_start / window_end | the (effect-free) control window |
| category | always NORMAL_CHANGE |

## Run artifacts (outputs/runs/<command>/)

| File | Notes |
| --- | --- |
| manifest.json | command, status (INTERNAL_RESEARCH), hashes, utc, result_hash |
| run_receipt.json | command-specific counts |
| run.log | logical-timestamped log lines |
| excluded_rows.csv | rejected rows with reasons (validate: schema violations; triage: orphan nodes) |
| data_quality_report.json | validate only |
| triage_results.csv / anomalies.csv | triage only |
| evaluation_report.json / baselines_report.csv / evaluation_summary.md | evaluate only |
| data/_ground_truth/ | evaluation-only copies of ground truth (triage never reads them) |
