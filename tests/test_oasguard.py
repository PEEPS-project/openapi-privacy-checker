"""Tests for the conformance checker, PII rules, and the enricher.

Run:  .venv/bin/pytest -q
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from oasguard.detect import analyze                  # noqa: E402
from oasguard.enrich import enrich                    # noqa: E402
from oasguard.rules import PrivacyRules               # noqa: E402
from oasguard.spec import Spec                         # noqa: E402

RULES = PrivacyRules.load()


# --- a tiny spec: /widgets/{id} -> a CLOSED object with an OPEN metadata map,
#     a typed field, a nullable field, an enum, and a required field.
def make_spec():
    return Spec({
        "paths": {"/widgets/{id}": {"get": {"responses": {"200": {"content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/widget"}}}}}}}},
        "components": {"schemas": {
            "widget": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "email": {"type": "string"},
                    "count": {"type": "integer"},
                    "note": {"type": "string", "nullable": True},
                    "status": {"type": "string", "enum": ["on", "off"]},
                    "description": {"type": "string"},
                    "client_secret": {"type": "string"},
                    "metadata": {"type": "object",
                                 "additionalProperties": {"type": "string"}},
                },
            }
        }},
    })


def record(response):
    return [{"method": "GET", "endpoint": "/widgets/{id}",
             "status": 200, "response": response}]


def analyze_one(response):
    return analyze(make_spec(), RULES, record(response))


# --- classify() -------------------------------------------------------------
def test_classify_token_and_phrase():
    assert RULES.classify("ssn").category == "national_id"
    assert RULES.classify("date_of_birth").category == "identity"
    assert RULES.classify("customerEmail").category == "contact"


def test_classify_value_pattern_beats_bland_name():
    hit = RULES.classify("internal_ref", "123-45-6789")
    assert hit and hit.category == "national_id" and hit.signal == "value format"


def test_classify_non_pii_is_silent():
    for name in ["created", "livemode", "tax_rates", "automatic_tax", "shard_id"]:
        assert RULES.classify(name) is None, name


def test_article_mapping():
    assert RULES.classify("ssn").gdpr == "Art. 87"
    assert RULES.classify("iban").gdpr == "Art. 6"
    assert RULES.classify("health").gdpr == "Art. 9"


# --- conformance: a valid, non-PII response has no findings -----------------
def test_valid_response_is_clean():
    rep = analyze_one({"id": "w1", "count": 3, "note": None, "status": "on"})
    assert rep.inconsistencies == [] and rep.exposures == []


# --- conformance: type / null / enum / required -----------------------------
def test_type_mismatch():
    rep = analyze_one({"id": "w1", "count": "three"})   # string where integer
    kinds = {f.kind for f in rep.inconsistencies}
    assert "type_mismatch" in kinds
    f = next(f for f in rep.inconsistencies if f.kind == "type_mismatch")
    assert f.expected == "integer" and f.actual == "string"


def test_integer_satisfies_number():
    spec = Spec({"paths": {"/n/{id}": {"get": {"responses": {"200": {"content": {
        "application/json": {"schema": {"type": "object",
            "properties": {"amt": {"type": "number"}}}}}}}}}}})
    rep = analyze(spec, RULES, [{"method": "GET", "endpoint": "/n/{id}",
                                 "status": 200, "response": {"amt": 5}}])
    assert rep.inconsistencies == []


def test_null_not_allowed():
    rep = analyze_one({"id": "w1", "email": None})      # email is not nullable
    assert any(f.kind == "null_not_allowed" for f in rep.inconsistencies)


def test_nullable_field_accepts_null():
    rep = analyze_one({"id": "w1", "note": None})       # note IS nullable
    assert rep.inconsistencies == []


def test_enum_mismatch():
    rep = analyze_one({"id": "w1", "status": "paused"})
    assert any(f.kind == "enum_mismatch" for f in rep.inconsistencies)


def test_missing_required():
    rep = analyze_one({"email": "a@b.com"})             # 'id' is required
    assert any(f.kind == "missing_required" and f.field_path == "id"
               for f in rep.inconsistencies)


# --- undeclared vs open map -------------------------------------------------
def test_undeclared_field_is_inconsistency():
    rep = analyze_one({"id": "w1", "surprise": "x"})
    f = next(f for f in rep.inconsistencies if f.kind == "undeclared_field")
    assert f.field == "surprise"
    assert f.schema_pointer == "#/components/schemas/widget"


def test_pii_in_open_map_is_exposure():
    rep = analyze_one({"id": "w1", "metadata": {"ssn": "123-45-6789"}})
    assert len(rep.exposures) == 1 and rep.exposures[0].kind == "pii_in_open_map"


def test_exclusion_suppresses_structural_name():
    rep = analyze_one({"id": "w1", "metadata": {"file_name": "x.pdf"}})
    assert rep.exposures == []


# --- new privacy categories -------------------------------------------------
def test_classification_missing_on_declared_pii():
    rep = analyze_one({"id": "w1", "email": "marie@x.com"})
    kinds = {f.kind for f in rep.exposures}
    assert "classification_missing" in kinds


def test_pii_in_free_text():
    rep = analyze_one({"id": "w1", "description": "call Marie at marie@x.com please"})
    f = next(f for f in rep.exposures if f.kind == "pii_in_free_text")
    assert f.category == "contact" and "marie@x.com" in f.actual


def test_secret_exposure():
    rep = analyze_one({"id": "w1", "client_secret": "seti_123_secret_abc"})
    assert any(f.kind == "secret_exposure" for f in rep.exposures)


# --- enrichment -------------------------------------------------------------
def test_enrich_adds_undeclared_field():
    spec = make_spec()
    rep = analyze(spec, RULES, record({"id": "w1", "patient_ssn": "123-45-6789"}))
    enriched, stats = enrich(spec, rep)
    props = enriched.doc["components"]["schemas"]["widget"]["properties"]
    assert "patient_ssn" in props and stats["fields_added"] == 1
    assert "patient_ssn" not in spec.doc["components"]["schemas"]["widget"]["properties"]


def test_enrich_annotates_open_map():
    spec = make_spec()
    rep = analyze(spec, RULES, record({"id": "w1", "metadata": {"ssn": "123-45-6789"}}))
    enriched, stats = enrich(spec, rep)
    meta = enriched.doc["components"]["schemas"]["widget"]["properties"]["metadata"]
    assert "x-observed-pii" in meta and stats["maps_annotated"] == 1


# --- anyOf resolution (the original false-positive bug) ---------------------
def test_anyof_resolution():
    spec = Spec({
        "paths": {"/c/{id}": {"get": {"responses": {"200": {"content": {
            "application/json": {"schema": {"anyOf": [
                {"$ref": "#/components/schemas/customer"},
                {"$ref": "#/components/schemas/deleted"}]}}}}}}}},
        "components": {"schemas": {
            "customer": {"type": "object", "properties": {"email": {"type": "string"}}},
            "deleted": {"type": "object", "properties": {"deleted": {"type": "boolean"}}},
        }},
    })
    rep = analyze(spec, RULES, [{"method": "GET", "endpoint": "/c/{id}",
                                 "status": 200, "response": {"email": "a@b.com"}}])
    assert rep.inconsistencies == []
