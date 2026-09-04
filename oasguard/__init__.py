"""OASguard: detect undeclared and undocumented personal data in Web API
responses by comparing captured traffic against the OpenAPI specification.

Python API
----------
    import oasguard

    report = oasguard.analyze("https://api.example.com/openapi.json",
                              "out/trace.jsonl")
    print(report.verdict())
    for f in report.exposures:
        print(f.severity, f.endpoint, f.field, f.gdpr)

    enriched = oasguard.enrich_spec("spec3.json", "out/trace.jsonl")
    # -> a Spec whose .doc is the corrected specification
"""
from .detect import analyze as _analyze, read_trace
from .enrich import enrich as _enrich
from .report import Finding, Report
from .rules import PrivacyRules
from .spec import Spec

__all__ = ["analyze", "enrich_spec", "Report", "Finding", "Spec", "PrivacyRules",
           "load_spec", "load_rules", "read_trace"]


def load_spec(source):
    """Load an OpenAPI spec from a path or http(s) URL (JSON or YAML)."""
    return Spec.load(source)


def load_rules(path=None):
    """Load the PII dictionary (defaults to the bundled privacy_rules.yaml)."""
    return PrivacyRules.load(path)


def analyze(spec, trace, rules=None):
    """Compare a trace against a spec. `spec` is a path or URL; `trace` is a
    path to a JSONL trace; `rules` is an optional privacy_rules.yaml path.
    Returns a Report."""
    return _analyze(load_spec(spec), load_rules(rules), read_trace(trace))


def enrich_spec(spec, trace, rules=None, annotate_open_maps=True):
    """Analyze, then return an enriched Spec (the original is not mutated)."""
    s = load_spec(spec)
    report = _analyze(s, load_rules(rules), read_trace(trace))
    enriched, _ = _enrich(s, report, annotate_open_maps=annotate_open_maps)
    return enriched
