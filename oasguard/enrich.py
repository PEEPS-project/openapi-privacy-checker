"""Enrichment: turn findings into a corrected OpenAPI spec.

  Case A (violation): add the undeclared field to the schema's `properties`.
  Case B (exposure) : annotate the open map with the personal data seen in it.

The original spec is never mutated; a deep copy is returned.
"""
import copy

from .spec import Spec, parse_pointer

WARNING = ("Free-form map observed to carry personal data at runtime. The spec "
           "allows arbitrary keys here, so this is not a schema defect, but the "
           "data flowing through it is a GDPR concern and should be governed.")


def enrich(spec, report, annotate_open_maps=True):
    """Return (enriched Spec, stats dict)."""
    enriched = Spec(copy.deepcopy(spec.doc))
    fields_added = maps_annotated = 0

    # Case A: add undeclared fields (structural and PII) to their schema.
    added_from = [f for f in report.inconsistencies if f.kind == "undeclared_field"]
    added_from += [f for f in report.exposures if f.kind == "undocumented_pii"]
    for f in added_from:
        node = _node(enriched, f.schema_pointer)
        if node is None or f.field in node.setdefault("properties", {}):
            continue
        prop = {"type": f.value_type or "string",
                "description": ("Documented by OASguard: observed in real API "
                                "responses but previously undeclared.")}
        if f.category:
            prop["x-gdpr"] = {"category": f.category, "article": f.gdpr,
                              "severity": f.severity}
        node["properties"][f.field] = prop
        fields_added += 1

    # Case B: annotate open maps with the PII observed inside them.
    if annotate_open_maps:
        by_map = {}
        for f in report.exposures:
            if f.kind == "pii_in_open_map" and f.schema_pointer:
                by_map.setdefault(f.schema_pointer, []).append(f)
        for pointer, items in by_map.items():
            node = _node(enriched, pointer)
            if node is None:
                continue
            observed = sorted({(i.field, i.category, i.gdpr, i.severity) for i in items})
            node["x-gdpr-warning"] = WARNING
            node["x-observed-pii"] = [
                {"field": fld, "category": cat, "article": art, "severity": sev}
                for fld, cat, art, sev in observed]
            maps_annotated += 1

    return enriched, {"fields_added": fields_added, "maps_annotated": maps_annotated}


def _node(spec, pointer_string):
    if not pointer_string:
        return None
    try:
        return spec.node_at(parse_pointer(pointer_string))
    except (KeyError, TypeError, IndexError):
        return None
