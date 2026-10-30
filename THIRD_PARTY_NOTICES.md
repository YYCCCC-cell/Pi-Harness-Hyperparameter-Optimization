# Third-party sources and licensing

Upstream software and reference materials retain their licenses and attribution. No project-wide open-source license has been selected; packaging does not grant a new license or replace an upstream license.

The upload copy excludes complete upstream repositories, downloaded source excerpts, paper PDFs and supplied course documents. Restore exact commits with `scripts/restore_sources.py`; original license files remain in those repositories.

| Source | Version / identity | Upstream license inspected locally |
|---|---|---|
| Pi | Fixed commit; runtime 1.4.0 | MIT, Mario Zechner |
| SkillsBench | v1.1 / fixed commit | Apache-2.0 |
| BenchFlow | 0.6.3 / fixed commit | Apache-2.0 |
| pi-acp | 0.0.34 / fixed commit | MIT, Sergii Kozak |
| SMAC / ConfigSpace and other Python dependencies | Exact installed artifacts | Package licenses remain authoritative; see dependency provenance |

Canonical upstream URLs and exact commits are in `docs/sources/source_lock.json`. Resolved Python artifacts are recorded in `requirements-hpo.lock` and `docs/sources/hpo/source_lock.json`.

Research citations remain in the algorithm design and literature review. Citation does not transfer ownership or permit redistribution of supplied PDFs. Public evidence summaries identify local originals by hash and label redactions; real task prompts and model completions are excluded.
