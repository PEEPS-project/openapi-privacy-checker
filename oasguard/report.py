"""The finding model and its renderings: console, markdown, JSON, SARIF.

Two classes of finding:
  - inconsistencies : the API response disagrees with its schema (type, null,
                      enum, required, or an undeclared field)
  - exposures       : personal data inside a spec-declared open map (conformant,
                      but a privacy risk a spec-only review cannot see)
"""
import json
from dataclasses import dataclass, field, asdict

from . import reference as ref

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}

PRIVACY_KINDS = ("undocumented_pii", "pii_in_open_map", "pii_in_free_text",
                 "classification_missing", "secret_exposure", "financial_exposure",
                 "consent_audit_exposure", "sensitive_data_exposure")

# One-line explanation per inconsistency type.
EXPLAIN = {
    "undocumented_pii":       "personal data the schema does not declare at all",
    "pii_in_open_map":        "personal data inside a spec-declared open map (metadata)",
    "pii_in_free_text":       "personal data embedded in a declared free-text field",
    "classification_missing": "declared PII field carries no privacy/GDPR classification",
    "secret_exposure":        "a secret credential is returned in the response",
    "financial_exposure":     "a financial identifier is exposed",
    "consent_audit_exposure": "consent / audit evidence returned without governance info",
    "sensitive_data_exposure": "special-category / national identifier returned",
}

LIMITS = ("Structural checks (type, nullability, enum, required, undeclared) plus "
          "name/value/text PII rules and a sensitive-field registry; coverage "
          "equals the traffic exercised.")

# Human-readable category shown in the table.
CATEGORY_LABEL = {
    "secret_exposure": "Secret exposure",
    "pii_in_open_map": "PII in metadata",
    "pii_in_free_text": "PII in free text",
    "classification_missing": "Unclassified PII",
    "financial_exposure": "Financial data",
    "consent_audit_exposure": "Consent / audit",
    "undocumented_pii": "Undocumented PII",
    "sensitive_data_exposure": "Sensitive data",
}

DATA_NAME = {
    "national_id": "National/tax ID", "contact": "Contact detail",
    "identity": "Identity data", "financial": "Financial data",
    "location": "Address", "online_id": "Online ID", "secret": "Secret",
    "audit": "Audit data", "consent": "Consent data",
}


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str
    method: str
    endpoint: str
    field_path: str
    field: str
    category: str = ""
    gdpr: str = ""
    signal: str = ""
    schema_pointer: str = None
    expected: str = ""
    actual: str = ""
    value_type: str = "string"
    verify: bool = False
    label: str = ""
    spec_decl: str = ""


@dataclass
class Report:
    inconsistencies: list = field(default_factory=list)
    exposures: list = field(default_factory=list)
    responses_analysed: int = 0
    schema_matched: int = 0
    unmatched: int = 0

    @staticmethod
    def _resource(pointer):
        if not pointer:
            return "(response)"
        parts = pointer.lstrip("#/").split("/")
        if "schemas" in parts and parts.index("schemas") + 1 < len(parts):
            return parts[parts.index("schemas") + 1]
        return parts[-1] if parts else "(response)"

    def _loc(self, f):
        return f"{self._resource(f.schema_pointer)}.{f.field}".rstrip(".")

    def _rank(self, f):
        return (SEVERITY_ORDER.get(f.severity, 9), self._loc(f), f.kind)

    def _grouped(self, findings, key):
        """Dedupe findings by `key(f)`; keep endpoints and one representative."""
        groups = {}
        for f in findings:
            g = groups.setdefault(key(f), {"f": f, "endpoints": set()})
            g["endpoints"].add(f"{f.method} {f.endpoint}")
        rows = list(groups.values())
        rows.sort(key=lambda g: self._rank(g["f"]))
        return rows

    def inconsistency_rows(self):
        return self._grouped(self.inconsistencies,
                             lambda f: (self._loc(f), f.kind))

    def exposure_rows(self):
        return self._grouped(self.exposures, lambda f: (f.kind, self._loc(f)))

    # -- verdict ------------------------------------------------------------
    def verdict(self):
        ni, ne = len(self.inconsistencies), len(self.exposures)
        types = sorted({f.kind for f in self.exposures})
        if not ni and not ne:
            return (f"No inconsistencies and no privacy findings in the "
                    f"{self.responses_analysed} analysed responses.")
        a = (f"{ni} spec inconsistenc{'y' if ni == 1 else 'ies'}"
             if ni else "no spec inconsistency")
        b = (f"{ne} privacy finding(s) across {len(types)} type(s) "
             f"({', '.join(types)})" if ne else "no privacy finding")
        return (f"{a} and {b}, across {self.responses_analysed} responses "
                f"({self.schema_matched} matched a schema).")

    # -- JSON / SARIF -------------------------------------------------------
    def to_dict(self):
        return {
            "summary": {
                "responses_analysed": self.responses_analysed,
                "schema_matched": self.schema_matched,
                "unmatched": self.unmatched,
                "inconsistencies": len(self.inconsistencies),
                "exposures": len(self.exposures),
            },
            "verdict": self.verdict(),
            "inconsistencies": [asdict(f) for f in sorted(self.inconsistencies, key=self._rank)],
            "exposures": [asdict(f) for f in sorted(self.exposures, key=self._rank)],
        }

    def write_json(self, path):
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    def write_sarif(self, path):
        results = []
        for f in sorted(self.inconsistencies + self.exposures, key=self._rank):
            results.append({
                "ruleId": f.kind,
                "level": SARIF_LEVEL.get(f.severity, "warning"),
                "message": {"text": _one_line(f)},
                "properties": {"kind": f.kind, "severity": f.severity,
                               "gdpr": f.gdpr, "category": f.category,
                               "expected": f.expected, "actual": f.actual,
                               "schemaPointer": f.schema_pointer},
                "locations": [{"logicalLocations": [
                    {"fullyQualifiedName": f"{f.method} {f.endpoint} :: {f.field_path}"}]}],
            })
        with open(path, "w") as fh:
            json.dump({
                "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
                "version": "2.1.0",
                "runs": [{"tool": {"driver": {"name": "OASguard", "rules": []}},
                          "results": results}],
            }, fh, indent=2)

    # -- render -------------------------------------------------------------
    def render(self, fmt="console", verbose=False):
        if fmt == "markdown":
            return _render_markdown(self)
        return _render_verbose(self) if verbose else _render_console(self)


# ---------------------------------------------------------------------------
def _detail(f):
    """The right-hand explanation for an inconsistency finding."""
    if f.kind == "type_mismatch":
        return f"expected {f.expected}, got {f.actual}"
    if f.kind == "null_not_allowed":
        return "returned null but field is not nullable"
    if f.kind == "enum_mismatch":
        return f"value {f.actual} not in {f.expected}"
    if f.kind == "missing_required":
        return "required by the schema but absent"
    if f.kind == "undeclared_field":
        gd = f" [{f.category}, GDPR {f.gdpr}]" if f.category else ""
        return f"not declared by the schema (returned {f.actual}){gd}"
    return ""


def _gdpr_tag(f):
    return f"{f.gdpr} (verify)" if f.verify else f.gdpr


def _one_line(f):
    if f.kind in PRIVACY_KINDS:
        return (f"{f.kind}: '{f.field}' ({f.category}, {f.gdpr}) in "
                f"{f.method} {f.endpoint} at {f.field_path}.")
    return (f"{f.kind}: {f.method} {f.endpoint} at {f.field_path} — {_detail(f)}.")


def _kind_counts(rows):
    counts = {}
    for g in rows:
        counts[g["f"].kind] = counts.get(g["f"].kind, 0) + 1
    return ", ".join(f"{n} {k}" for k, n in sorted(counts.items(), key=lambda x: -x[1]))


def _sev_counts(rows):
    counts = {}
    for g in rows:
        counts[g["f"].severity] = counts.get(g["f"].severity, 0) + 1
    return ", ".join(f"{counts[s]} {s}"
                     for s in ("critical", "high", "medium", "low") if counts.get(s))


# --- compact console: ranked top-5 cards -----------------------------------
# Security first, then special-category, then the rest.
KIND_PRIORITY = {"secret_exposure": 0, "sensitive_data_exposure": 1,
                 "undocumented_pii": 2, "pii_in_open_map": 3, "financial_exposure": 4,
                 "pii_in_free_text": 5, "classification_missing": 6,
                 "consent_audit_exposure": 7}


def _top_privacy(r, n=5, per_kind=2):
    rows = r.exposure_rows()
    rows.sort(key=lambda g: (SEVERITY_ORDER.get(g["f"].severity, 9),
                             KIND_PRIORITY.get(g["f"].kind, 9), r._loc(g["f"])))
    picked, counts = [], {}
    for g in rows:                      # spread across types for variety
        k = g["f"].kind
        if counts.get(k, 0) < per_kind:
            picked.append(g)
            counts[k] = counts.get(k, 0) + 1
        if len(picked) >= n:
            return picked
    for g in rows:                      # top up if the cap left us short
        if g not in picked:
            picked.append(g)
        if len(picked) >= n:
            break
    return picked


def _path(r, f):
    """JSON path of the finding, prefixed with its object (without duplication)."""
    res = r._resource(f.schema_pointer)
    p = f.field_path or ""
    if res and res != "(response)" and not p.startswith(res + "."):
        return f"{res}.{p}".rstrip(".")
    return p or res


def _data_name(cat):
    return DATA_NAME.get(cat, cat)


def _summary(f):
    """One-line, sensitive-value-free summary of the inconsistency."""
    art = f.gdpr
    k = f.kind
    if k == "secret_exposure":
        return "Secret credential returned in the response body"
    if k == "pii_in_open_map":
        return f"{_data_name(f.category)} stored in open 'metadata' map ({art})"
    if k == "pii_in_free_text":
        return f"{_data_name(f.category)} embedded in a declared free-text field ({art})"
    if k == "classification_missing":
        return f"Declared {_data_name(f.category)} field, no GDPR classification ({art})"
    if k == "financial_exposure":
        return f"Financial identifier exposed in the response ({art})"
    if k == "consent_audit_exposure":
        return "Consent/audit field returned without governance metadata"
    if k == "undocumented_pii":
        return f"{_data_name(f.category)} returned but not declared in the schema ({art})"
    if k == "sensitive_data_exposure":
        return f"Special-category / national identifier returned ({art})"
    return EXPLAIN.get(k, "")


def _safe(f):
    """Redacted evidence for verbose / markdown views (never a raw secret/id)."""
    v = f.actual
    if not v or v == "present (null)":
        return v or ""
    s = str(v)
    if f.kind == "secret_exposure" or f.category in ("secret", "national_id", "financial"):
        return "«redacted»"
    if f.category == "contact" and "@" in s:
        user, _, dom = s.partition("@")
        return user[:2] + "…@" + dom
    return s[:40]


def _render_console(r):
    total = len(r.exposure_rows())
    struct = len(r.inconsistency_rows())
    types = len({f.kind for f in r.exposures})
    matched = ("all matched a schema" if not r.unmatched
               else f"{r.schema_matched} matched, {r.unmatched} not in the spec")
    L = [f"OASguard  ·  {r.responses_analysed} responses analysed, {matched}.", ""]

    if not total:
        L.append("No privacy or security findings.")
    else:
        top = _top_privacy(r, 6, per_kind=1)
        L.append(f"PRIVACY / SECURITY / GDPR  —  top {len(top)} of {total} "
                 f"findings ({types} types)")
        L.append("")
        rows = [[f"F{i}", g["f"].severity.upper(),
                 CATEGORY_LABEL.get(g["f"].kind, g["f"].kind),
                 _path(r, g["f"]), _summary(g["f"])]
                for i, g in enumerate(top, 1)]
        L += _grid(["ID", "SEVERITY", "CATEGORY", "JSON PATH", "INCONSISTENCY SUMMARY"],
                   rows, caps={4: 42})
        L.append("")

    L.append(f"Totals: {total} distinct privacy finding(s) across {types} type(s); "
             f"{struct} structural inconsistency(ies).")
    L.append("Full report (all findings):  --explain   or   --format markdown")
    return "\n".join(L)


# --- verbose console -------------------------------------------------------
def _render_verbose(r):
    L = ["", "VERDICT", "  " + _wrap(r.verdict(), "  "), ""]

    L.append("SPEC INCONSISTENCIES (the API response disagrees with the schema)")
    inc = r.inconsistency_rows()
    if not inc:
        L.append("  none\n")
    else:
        for g in inc:
            f = g["f"]
            L.append(f"  [{f.severity.upper():8}] {f.kind}  —  {r._loc(f)}")
            L.append("       " + _detail(f))
            L.append("       seen: " + ", ".join(sorted(g["endpoints"])))
        L.append("")

    L.append("PRIVACY FINDINGS (personal / sensitive data in the responses)")
    exp = r.exposure_rows()
    if not exp:
        L.append("  none\n")
    else:
        for g in exp:
            f = g["f"]
            L.append(f"  [{f.severity.upper():8}] {f.kind}  —  {r._loc(f)}  "
                     f"({f.category}, {_gdpr_tag(f)})")
            L.append("       " + EXPLAIN.get(f.kind, "") + f"; evidence: {_safe(f)}")
            L.append("       seen: " + ", ".join(sorted(g["endpoints"])))
        articles = []
        for g in exp:
            code = g["f"].gdpr
            if code.startswith("Art.") and code not in articles:
                articles.append(code)
        if articles:
            L.append("")
            L.append("  GDPR articles referenced")
            for code in articles:
                L.append(f"    {code:8} {ref.article_title(code)} — "
                         + _wrap(ref.article_note(code), "             "))
        L.append("")

    L.append("DETECTION LIMITS")
    L.append("  " + _wrap(LIMITS, "  "))
    return "\n".join(L)


# --- markdown --------------------------------------------------------------
def _render_markdown(r):
    L = ["# API / Spec Conformance Report", "", "## Verdict", "", r.verdict(), ""]

    L.append("## Spec inconsistencies")
    L.append("")
    inc = r.inconsistency_rows()
    if not inc:
        L.append("None.\n")
    else:
        L.append(f"_{len(r.inconsistencies)} finding(s)._")
        L.append("")
        L.append("| Severity | Kind | Location | Detail | Endpoints |")
        L.append("|----------|------|----------|--------|-----------|")
        for g in inc:
            f = g["f"]
            eps = "<br>".join(f"`{e}`" for e in sorted(g["endpoints"]))
            L.append(f"| **{f.severity.upper()}** | `{f.kind}` | `{r._loc(f)}` "
                     f"| {_detail(f)} | {eps} |")
        L.append("")

    L.append("## Privacy findings")
    L.append("")
    exp = r.exposure_rows()
    if not exp:
        L.append("None.\n")
    else:
        by_type = {}
        for g in exp:
            by_type.setdefault(g["f"].kind, 0)
            by_type[g["f"].kind] += 1
        L.append("_" + ", ".join(f"{n} {k}" for k, n in by_type.items()) + "._")
        L.append("")
        L.append("| Severity | Type | Object · path | Field | Category | "
                 "GDPR / security | Evidence | Endpoints |")
        L.append("|----------|------|---------------|-------|----------|"
                 "-----------------|----------|-----------|")
        for g in exp:
            f = g["f"]
            eps = "<br>".join(f"`{e}`" for e in sorted(g["endpoints"]))
            ev = _safe(f).replace("|", "\\|")
            L.append(f"| **{f.severity.upper()}** | `{f.kind}` | `{r._loc(f)}` "
                     f"| `{f.field}` | {f.category} | {_gdpr_tag(f)} | {ev} | {eps} |")
        L.append("")
        L.append("**Inconsistency types**")
        L.append("")
        for k in by_type:
            L.append(f"- `{k}` — {EXPLAIN.get(k, '')}")
        L.append("")

    L.append("## Detection limits\n")
    L.append(LIMITS + "\n")
    return "\n".join(L)


def _wrap(text, indent, width=78):
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    out.append(line)
    return ("\n" + indent).join(out)


def _wrap_to(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        while len(w) > width:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:width])
            w = w[width:]
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _grid(headers, rows, caps=None, indent="  "):
    """ASCII table; columns in `caps` wrap onto multiple lines."""
    caps = caps or {}
    ncol = len(headers)
    widths = [min(caps[c], max([len(headers[c])] + [len(r[c]) for r in rows], default=0))
              if c in caps else max([len(headers[c])] + [len(r[c]) for r in rows], default=0)
              for c in range(ncol)]

    def rule(fill="-"):
        return indent + "+" + "+".join(fill * (w + 2) for w in widths) + "+"

    def emit(cells):
        wrapped = [_wrap_to(cells[c], widths[c]) for c in range(ncol)]
        height = max(len(w) for w in wrapped)
        out = []
        for i in range(height):
            parts = [(wrapped[c][i] if i < len(wrapped[c]) else "").ljust(widths[c])
                     for c in range(ncol)]
            out.append(indent + "| " + " | ".join(parts) + " |")
        return out

    lines = [rule(), *emit(headers), rule("=")]
    for r in rows:
        lines += emit(r)
    lines.append(rule())
    return lines
