# OASGuard

**Automatic detection and enrichment of privacy inconsistencies in the OpenAPI specifications of REST APIs.**

OASGuard exercises a live REST API with realistic scenarios, compares what the API *actually returns* against what its OpenAPI specification *declares*, reports every piece of personal data (PII) that flows undocumented, and writes the missing privacy annotations back into the specification as GDPR-aware vendor extensions.

> Developed during an end-of-studies internship within the [DiverSE team](https://www.diverse-team.fr/) (IRISA / Inria, University of Rennes), as part of the PEEPS research project. Validated on the [Stripe API](https://stripe.com/docs/api) and its official OpenAPI specification.

---

## The problem

An OpenAPI specification is the *contract* between an API provider and its consumers: it describes, for every endpoint, the shape of the data exchanged. But this contract has a **privacy blind spot**:

1. **OpenAPI has no notion of personal data.** A specification can say a field is a `string`; it cannot say that the field carries an email, a national identifier, or a date of birth, nor which GDPR obligations attach to it.
2. **The implementation drifts from its documentation.** APIs evolve faster than their specs, so a running API may return data the specification never declared.
3. **Free-form fields are open doors.** Specifications routinely declare open maps (`additionalProperties`) and free-text fields. A developer can store an SSN in a `metadata` map, the API will echo it back, and no static reading of the specification will ever reveal it.

The result: personal data circulates through endpoints that no document faithfully records — invisible to the developers who integrate the API and to the officers responsible for GDPR compliance. The GDPR demands minimization, transparency, and security (Art. 5, 6, 9, 12–14, 25, 32), and the OWASP API Security Top 10 ranks excessive data exposure among the most critical API risks. Yet existing tooling addresses only fragments of the problem: spec validators never observe the real API, API fuzzers check robustness but are blind to PII, and static privacy-annotation vocabularies rely on a human already knowing which fields are personal.

## What OASGuard does

OASGuard treats the specification as a contract and **verifies it against real traffic**, then **fixes the documentation gap it finds**:

```
 Inputs                          Pipeline                       Outputs
 ──────                          ────────                       ───────
 OpenAPI spec (spec3.json) ──┐
 Privacy rules (yaml)      ──┤   1. CAPTURE  scenarios → trace.jsonl
 Live API (Stripe sandbox) ──┘   2. DETECT   trace vs. spec → findings
                                 3. ENRICH   findings → annotated spec ──→ spec.enriched.json
                                 4. REPORT   console / Markdown / JSON / SARIF
```

1. **Capture** — runs 17 realistic business scenarios (onboarding, checkout, subscription, refund, …) against the live API with [Locust](https://locust.io/), recording every request/response pair into a trace. Capture and analysis are strictly separated: the analysis reads only the trace, so it works on traffic from *any* source.
2. **Detect** — walks each response and its declared schema **in parallel** (resolving `$ref`, `anyOf`/`oneOf`/`allOf`), and classifies every value against an editable privacy knowledge base (`privacy_rules.yaml`). A field is reported only when it is both **structurally undocumented** *and* **personal data** — that twofold condition is what keeps the findings precise.
3. **Enrich** — writes the findings back into a corrected copy of the specification using OpenAPI vendor extensions (`x-observed-pii`, `x-gdpr-warning`, `x-gdpr`). The enriched spec remains valid and backward compatible: tools that don't know the extensions simply ignore them.
4. **Report** — renders the same findings for humans (console, Markdown) and machines (JSON, SARIF), each classified by PII category, GDPR article, and severity.

### Before / after enrichment

A free-form `metadata` map, before:

```yaml
metadata:
  type: object
  additionalProperties: { type: string }
```

After OASGuard observed a national identifier flowing through it at runtime:

```yaml
metadata:
  type: object
  additionalProperties: { type: string }
  x-gdpr-warning: "Free-form map observed to carry personal data at runtime."
  x-observed-pii:
    - { field: ssn,           category: national_id, article: "Art. 87", severity: critical }
    - { field: date_of_birth, category: identity,    article: "Art. 6",  severity: high }
```

What was invisible to any static review is now recorded in the contract itself — readable by developers, security teams, and DPOs alike.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                                  # installs the `oasguard` command
echo "STRIPE_API_KEY=sk_test_your_key_here" > .env   # Stripe TEST key (sandbox only)
```

One-shot run — capture, detect, enrich:

```bash
oasguard run spec3.json
```

Analyze an existing trace against any spec (no live API calls — portable mode):

```bash
oasguard run https://api.example.com/openapi.json --trace out/trace.jsonl
```

Or drive the stages individually:

```bash
oasguard capture onboarding refund        # scenarios → out/trace.jsonl
oasguard detect  --format markdown json sarif
oasguard enrich  --out out/spec.enriched.json
```

The exit code is CI-friendly (`--fail-on` controls when a run exits non-zero, so a new finding can break a build). See [COMMANDS.md](COMMANDS.md) for the full command reference, and the Python API:

```python
import oasguard
report = oasguard.analyze("spec3.json", "out/trace.jsonl")
print(report.verdict())
```

## Extending the privacy knowledge base

What counts as personal data lives in [oasguard/privacy_rules.yaml](oasguard/privacy_rules.yaml), not in code: `phrases` (whole field names like `social_security_number`), `tokens` (single words like `ssn`, `email`), `value_patterns` (regexes on values, catching PII behind uninformative names), `text_patterns` (PII inside free text), and `exclusions` (structural names that must never fire). The rules draw on Microsoft Presidio, Google Cloud DLP, and CNIL categories, in English and French. Adding a new kind of PII is one YAML entry — or point `--rules` at your own file.

## Project layout

```
oasguard/            the analysis engine
  cli.py             command-line interface (run / capture / detect / enrich / all)
  spec.py            reads the spec; resolves $ref and anyOf/oneOf/allOf; tracks pointers
  rules.py           loads privacy_rules.yaml; classifies fields as personal data
  detect.py          walks response and schema in parallel; produces the findings
  enrich.py          writes findings back into a corrected spec
  report.py          console / Markdown / JSON / SARIF rendering
  privacy_rules.yaml the editable PII knowledge base
scenarios/           17 Locust business scenarios + trace recorder (capture.py)
tests/               pytest suite
spec3.json           the official Stripe OpenAPI specification (reference contract)
```

## Results on the Stripe case study

Against Stripe's spec (414 paths, 587 operations) and 79 captured requests from 17 scenarios, OASGuard surfaced privacy documentation gaps of several distinct kinds — PII planted in open `metadata` maps, contact data embedded in free-text descriptions, declared personal fields (billing address, card fingerprint) with no privacy classification, and consent fields lacking governance metadata — every reported finding a true positive within the evaluated scenarios, and every already-documented field correctly left untouched.

**Scope & limitations.** All experiments run against the Stripe **test sandbox** with entirely synthetic data; the planted PII demonstrates the detection on a controlled case rather than revealing a leak in Stripe. Coverage equals scenario coverage, and recognition is bounded by the rules file. OASGuard is a privacy-*assistance* tool, not a legal compliance oracle: context-dependent findings are flagged for human verification.


## Author

**Abdelilah Ettarch**
