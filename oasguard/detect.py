"""Compare captured responses against the spec and produce a Report.

Structural inconsistencies (response disagrees with the schema):
  type_mismatch, null_not_allowed, enum_mismatch, missing_required, undeclared_field

Privacy inconsistencies (personal / sensitive data findings):
  undocumented_pii       PII in a field the schema does not declare
  pii_in_open_map        PII inside a spec-declared open map (metadata)
  pii_in_free_text       PII embedded in a declared free-text field (description...)
  classification_missing declared PII field carries no privacy classification
  secret_exposure        a secret (client_secret, ...) is returned
  financial_exposure     a financial identifier (iban, routing_number, last4, ...)
  consent_audit_exposure consent / audit evidence (user_agent, tos_acceptance, ...)
  sensitive_data_exposure special-category / national identifier (id_number, dob, ...)
"""
import json
from dataclasses import dataclass, field as dc_field

from .report import Finding, Report, PRIVACY_KINDS
from .rules import _snake
from .spec import MAX_DEPTH, normalise_path, pointer_str

STRONG = ("critical", "high")

# Only these declared string fields are scanned for PII embedded in prose;
# scanning every declared string produces false positives on ids/dates.
FREE_TEXT = {"description", "footer", "comment", "memo", "note", "message",
             "statement_descriptor", "descriptor", "instructions", "custom_message"}


@dataclass
class Issue:
    kind: str
    path: str
    field: str = ""
    expected: str = ""
    actual: str = ""
    pointer: tuple = ()
    category: str = ""
    gdpr: str = ""
    severity: str = ""
    verify: bool = False


def _json_type(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def _type_ok(actual, allowed):
    return actual in allowed or (actual == "integer" and "number" in allowed)


def _leaf(path):
    return path.rstrip("]").rsplit(".", 1)[-1].rstrip("[") or "."


def _snippet(value):
    s = value if isinstance(value, str) else json.dumps(value)
    return s[:60]


def _compact(schema, keys=("type", "format", "enum", "nullable")):
    if not isinstance(schema, dict):
        return "{}"
    d = {k: schema[k] for k in keys if k in schema}
    if not d and "$ref" in schema:
        d["$ref"] = schema["$ref"].split("/")[-1]
    return json.dumps(d, separators=(",", ":"))[:80] or "{}"


def _spec_decl(spec, issue):
    """A short string describing what the spec declares at the finding site."""
    if issue.kind in ("undocumented_pii", "undeclared_field"):
        return "field is not declared in the response schema"
    try:
        node = spec.node_at(issue.pointer) if issue.pointer else None
    except (KeyError, TypeError, IndexError):
        node = None
    if not isinstance(node, dict):
        return "declared (schema not locatable)"
    if issue.kind == "pii_in_open_map":
        ap = node.get("additionalProperties")
        return f'open map: additionalProperties {_compact(ap, ("type", "maxLength"))}'
    sub = (node.get("properties") or {}).get(issue.field)
    if sub is None:
        return "declared field"
    resolved, _ = spec._resolve(sub, (), frozenset())
    base = resolved if isinstance(resolved, dict) else sub
    return _compact(base) + " (no x-gdpr classification)"


def _has_annotation(spec, sub, sub_ptr):
    node, _ = spec._resolve(sub, sub_ptr, frozenset())
    node = node if isinstance(node, dict) else (sub if isinstance(sub, dict) else {})
    return any(k.startswith("x-gdpr") or k.startswith("x-privacy") or k == "x-observed-pii"
               for k in node)


def _privacy_declared(spec, rules, path, field, value, sub, sub_ptr, container):
    """Privacy finding for a DECLARED field, or None."""
    hit = rules.sensitive_hit(field, path)                      # secrets / financial / consent
    if hit:
        # A null secret / financial identifier is not actually exposed; consent
        # and special-category fields are flagged for governance even when null.
        if not (value is None and hit.kind in ("secret_exposure", "financial_exposure")):
            return Issue(hit.kind, path, field=field, pointer=container,
                         category=hit.category, gdpr=hit.classification,
                         severity=hit.severity, verify=hit.verify,
                         actual=_snippet(value) if value is not None else "present (null)")

    named = rules.classify(field)                               # PII by field name
    if named and named.severity in STRONG and value is not None:
        if not _has_annotation(spec, sub, sub_ptr):
            return Issue("classification_missing", path, field=field, pointer=container,
                         category=named.category, gdpr=named.gdpr,
                         severity=named.severity, verify=named.verify,
                         actual=_snippet(value))

    if not named and isinstance(value, str):                    # PII inside free text
        if FREE_TEXT & set(_snake(field).split("_")):
            text_hit, snippet = rules.scan_text(value)
            if text_hit:
                return Issue("pii_in_free_text", path, field=field, pointer=container,
                             category=text_hit.category, gdpr=text_hit.gdpr,
                             severity=text_hit.severity, verify=text_hit.verify,
                             actual=snippet)
    return None


def check(spec, rules, value, schema, pointer=(), path="", out=None, depth=0):
    if out is None:
        out = []
    if depth > MAX_DEPTH:
        return out
    info = spec.schema_info(schema, pointer)

    if value is None:
        if info.types and not info.nullable:
            out.append(Issue("null_not_allowed", path or ".", field=_leaf(path),
                             expected="not nullable", actual="null",
                             pointer=info.object_pointer, severity="medium"))
        return out

    actual = _json_type(value)
    if info.types and not _type_ok(actual, info.types):
        out.append(Issue("type_mismatch", path or ".", field=_leaf(path),
                         expected="/".join(sorted(info.types)), actual=actual,
                         pointer=info.object_pointer, severity="medium"))
        return out

    if info.enum is not None and value not in info.enum:
        shown = ", ".join(map(str, info.enum[:6])) + ("..." if len(info.enum) > 6 else "")
        out.append(Issue("enum_mismatch", path or ".", field=_leaf(path),
                         expected=f"one of [{shown}]", actual=repr(value),
                         pointer=info.object_pointer, severity="medium"))

    if isinstance(value, dict):
        for req in sorted(info.required):
            if req not in value:
                out.append(Issue("missing_required", f"{path}.{req}".lstrip("."),
                                 field=req, expected="present (required)",
                                 actual="absent", pointer=info.object_pointer,
                                 severity="medium"))
        for key, sub_value in value.items():
            here = f"{path}.{key}".lstrip(".")
            if key in info.properties:
                sub, sub_ptr = info.properties[key]
                pe = _privacy_declared(spec, rules, here, key, sub_value,
                                       sub, sub_ptr, info.object_pointer)
                if pe:
                    out.append(pe)
                check(spec, rules, sub_value, sub, sub_ptr, here, out, depth + 1)
            elif info.open_map or not info.properties:
                hit = rules.classify(key, sub_value)
                if hit:
                    out.append(Issue("pii_in_open_map", here, field=key,
                                     pointer=info.open_map_pointer or info.object_pointer,
                                     category=hit.category, gdpr=hit.gdpr,
                                     severity=hit.severity, verify=hit.verify,
                                     actual=_snippet(sub_value)))
            else:
                out.append(Issue("undeclared_field", here, field=key,
                                 expected="not declared", actual=_json_type(sub_value),
                                 pointer=info.object_pointer, severity="low"))
                hit = rules.classify(key, sub_value)
                if hit:
                    out.append(Issue("undocumented_pii", here, field=key,
                                     pointer=info.object_pointer, category=hit.category,
                                     gdpr=hit.gdpr, severity=hit.severity,
                                     verify=hit.verify, actual=_snippet(sub_value)))
    elif isinstance(value, list):
        for element in value:
            check(spec, rules, element, info.item_schema, info.item_pointer,
                  path + "[]", out, depth + 1)
    return out


def read_trace(trace_path):
    with open(trace_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            status = record.get("status")
            if status is None or not (200 <= status < 300):
                continue
            if isinstance(record.get("response"), (dict, list)):
                yield record


def analyze(spec, rules, records):
    schemas = spec.response_schemas()
    report = Report()
    seen = set()
    for record in records:
        report.responses_analysed += 1
        method = record["method"].upper()
        endpoint = record["endpoint"]
        key = (method, normalise_path(endpoint))
        if key not in schemas:
            report.unmatched += 1
            continue
        report.schema_matched += 1
        schema, ptr = schemas[key]

        for issue in check(spec, rules, record["response"], schema, ptr):
            dedupe = (issue.kind, method, normalise_path(endpoint), issue.path)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            finding = Finding(
                kind=issue.kind, severity=issue.severity or "medium",
                method=method, endpoint=endpoint, field_path=issue.path,
                field=issue.field or _leaf(issue.path),
                category=issue.category, gdpr=issue.gdpr, signal="",
                schema_pointer=pointer_str(issue.pointer),
                expected=issue.expected, actual=issue.actual,
                value_type=issue.actual if issue.kind == "undeclared_field" else "string",
                verify=issue.verify, spec_decl=_spec_decl(spec, issue))
            if issue.kind in PRIVACY_KINDS:
                report.exposures.append(finding)
            else:
                report.inconsistencies.append(finding)
    return report
