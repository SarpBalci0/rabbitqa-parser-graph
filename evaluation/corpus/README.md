# Evaluation Corpus

**This corpus is SYNTHETIC and ILLUSTRATIVE — it is NOT real NIS2/CRA/DORA text.**

`rabbitqa_spec_v1.0.0.md` §10 Q3 ("Confirm the exact NIS2/CRA/DORA article subset
to pin for v1 corpus") remains genuinely open — `spec.md`'s resolved clarification
settled the *scope* ("a bounded subset," not the full instrument) but the specific
enumerated article list was explicitly left to a Regulatory SME owner (see
`research.md` §8's "Open point carried to Engineering"). Fabricating text and
presenting it as authoritative regulatory content would be worse than not having a
corpus at all — a reader could mistake invented obligations for real legal
requirements.

Until that owner supplies the real article list, this directory contains
hand-authored, clearly-labeled synthetic fixture documents that exercise every
structural characteristic §9.3 requires a corpus to cover, so the parsing
pipeline and the `evaluation/metrics/harness.py` measurement code can be built,
run, and validated now, without waiting on that decision. **Metrics computed
against this corpus measure the pipeline's behavior on synthetic text — they are
NOT a claim about real-world NIS2/CRA/DORA extraction accuracy** (§9.2's targets
apply once a real corpus replaces this one).

## Contents

- `synthetic_instrument_v1.txt` — one synthetic "instrument" (labeled `SYN`, not a
  real NIS2/CRA/DORA `instrument` enum value — see note below) covering, per §9.3:
  - **Hard negatives**: paragraphs with no modal verb, or modal-verb-shaped text
    that isn't actually a normative requirement.
  - **Nested conditions**: an obligation whose applicability depends on a
    conditional clause.
  - **An annex table**: a structured table of requirements outside the main
    article body.
  - **A long cross-reference**: an obligation referencing a definition/provision
    defined many paragraphs away.
  - **One amendment scenario**: a later article that amends an earlier one.
- `labels.json` — hand-authored ground truth for the synthetic corpus (which
  spans are true normative passages, expected core/complex field values per
  clause) used by `evaluation/metrics/harness.py`.
- `train_eval_split.json` — the locked train/eval split (§9.3: "no eval clause
  ever used in prompt few-shot examples") over this synthetic corpus's clause
  IDs.

## Note on `instrument`

`CanonicalDocument.instrument`/`ObligationObject.identity.instrument` (§2.1/§2.2)
only allow `"NIS2" | "CRA" | "DORA"` — there is no `"SYN"` value in that enum, and
this corpus does not attempt to add one (that would be an uncoordinated schema
change). The synthetic fixture is registered under `instrument: "NIS2"` purely as
a placeholder pipeline target; `labels.json` and this README are what actually
mark it as synthetic, not the `instrument` field itself. Replace this whole
directory's content once real, SME-confirmed article text is available — the
harness code in `evaluation/metrics/harness.py` does not need to change.
