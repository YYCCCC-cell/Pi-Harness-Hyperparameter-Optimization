# Recorded experiment aggregates

- `audit.json`: provenance, timing, measurement, accounting and completeness checks.
- `aggregate-tables/method-coverage.csv` and `.json`: validation and held-out ended observations, valid observations, policy penalties, passes and missing coverage.
- `aggregate-tables/frozen-winners.csv` and `.json`: the four configurations frozen before held-out testing.
- `aggregate-tables/common-budget-curves.csv` and `.json`: incumbent values restricted to common supported search-budget domains.
- `experiment-config.json`: model, seeds, settings policy, task split, original caps, stopping rules and source pins.
- `source-provenance.json`: source record and frozen-code hashes. Raw records stay local.
- `aggregate-tables/attempt-integrity.json` and `aggregate-tables/runtime-evidence.json`: sanitized audit details and observed settings/compaction evidence.
- `trajectory-report-paragraphs.json`: source-backed failure analysis summaries, with relative references to retained local evidence.
- `figures/`: report figures in PNG and PDF form.
- `figure-input.json` and `reproduce_figures.py`: public data and code for regenerating the two report figures.

The 151 ended observations comprise 139 validation and 12 held-out observations. Of those, 136 are measurement-valid and 15 retain measurement exceptions. Held-out coverage is three ended observations per method out of eight planned. One further Default dispatch remains unresolved. None of the methods has complete final eight-task pass@1.

The audited ledger records USD 20.4248448 in usage-based estimates plus USD 17 in reserves for 17 unknown requests, for USD 37.4248448 committed. Invoice reconciliation remains unavailable. The unresolved attempt has no provider setup marker or request journal and records `not_dispatched` usage, so no additional inventoried request exposure was found. It is not converted to a task failure or a success.

The search methods' common supported estimate-plus-reserve interval is USD 7.15150685 to 7.53589035. All three incumbent operational validation scores equal 0.25 in that interval. The known-estimate-only interval is USD 2.15150685 to 4.03755405 and omits unknown-cost exposure, so it is a sensitivity view. Default is a fixed baseline and is excluded from defining the three-search-method common interval.

IGBS only exercised initialization screening. BO and IGBS froze identical parameters with different scores from independent executions. Neither this score difference nor the partial held-out fractions establishes algorithm superiority.

To regenerate figures, use the versions listed in `requirements-report.txt` in a separate reporting environment and run `python reproduce_figures.py` from this directory. This reads only aggregate files and makes no model calls. Figures are regenerated locally; their PDF timestamps may change file hashes.
