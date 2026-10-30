# Submission report and presentation

- [Academic paper in PDF](EP6203_Paper.pdf): primary reading copy.
- [Academic paper in Word](EP6203_Paper.docx): editable copy of the same paper.
- [Presentation](EP6203_Presentation.pptx): 16-slide English deck with speaker notes and appendix, prepared for the ten-minute talk and five-minute Q&A.

The paper uses a single-column academic layout with an abstract, keywords, numbered sections, related work, numbered table and figure captions, references and a reproducibility appendix. The author line remains EP6203 Project Team; individual names and student IDs were not supplied.

Both the paper and deck use the preserved 30 October 2026 12:03 UTC+8 campaign cutoff. The full eight-task test and IGBS adaptive phase remain incomplete. The paper formatting revision does not add experimental evidence or change the selected configurations.

Public data and figures are in [the aggregate directory](../results/final-20261030-1203/README.md). Original raw task and request records remain outside this submission. Use the public audit, source provenance and aggregate tables for review; full raw-evidence auditing requires the retained local archive.

## Rebuild the paper

Install `python-docx` from [the report dependencies](../requirements-report.txt). Synthetic figure regeneration additionally needs `matplotlib` and `numpy`; a fresh reporting environment has not been tested for this export. Then run from the repository root:

```bash
python reports/source/build_paper.py
python reports/source/render_synthetic_figure.py
python reports/source/integrate_synthetic.py
```

These commands rebuild the base Word paper, render the synthetic figure, and integrate Appendix B. Run them in this order from a clean base build; the integration step edits the Word paper in place. Export the Word file to PDF using Word or LibreOffice and inspect pagination. This is a document rebuild, not a benchmark rerun. The shipped Word and PDF were rendered and visually checked together.


## Controlled synthetic validation added on 30 October

The updated paper includes a separate synthetic experiment in Appendix B and integrates its interpretation into the abstract, discussion and conclusion. Six runs completed 60 panels and 480 synthetic evaluations with zero model calls and USD 0 in paid API costs. Strong-signal pair weighting and conservative fallback passed the mechanism checks. Real-task adaptive efficacy remains unverified; the original real-campaign cutoff and primary outcome tables are unchanged. See [synthetic evidence](../results/igbs-synthetic-20261030/RESULTS.md). The presentation retains the original real-campaign cutoff.
