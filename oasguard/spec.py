"""OpenAPI spec access: resolve $ref chains and compositions (anyOf/oneOf/allOf),
and -- crucially for enrichment -- track the canonical location of each schema
node so the enricher can write annotations back to the right place.
"""
import json
from dataclasses import dataclass

MAX_DEPTH = 14


def _parse(text):
    """Parse a spec document as JSON, falling back to YAML."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import yaml
        return yaml.safe_load(text)


@dataclass
class ObjectSchema:
    """One concrete object a value may conform to, at a locatable place."""
    node: dict            # the live schema dict inside Spec.doc
    pointer: tuple        # canonical path to `node` (e.g. components/schemas/customer), or () if inline/unknown
    open_map: bool        # does it accept arbitrary extra keys (additionalProperties)?


@dataclass
class SchemaInfo:
    """A schema flattened (through $ref and anyOf/oneOf/allOf) into everything
    needed to validate one value against it."""
    types: set            # allowed JSON types; empty means "unconstrained, skip"
    nullable: bool
    enum: list            # allowed values, or None
    properties: dict      # name -> (subschema, pointer)
    required: set         # required property names (allOf/direct only)
    open_map: bool
    open_map_pointer: tuple
    object_pointer: tuple  # a closed object's node, for undeclared-field annotation
    item_schema: dict
    item_pointer: tuple


class Spec:
    def __init__(self, doc):
        self.doc = doc

    @classmethod
    def load(cls, source):
        """Load a spec from a local path or an http(s) URL, JSON or YAML."""
        if source.startswith(("http://", "https://")):
            import urllib.request
            with urllib.request.urlopen(source) as r:
                text = r.read().decode("utf-8")
        else:
            with open(source) as f:
                text = f.read()
        return cls(_parse(text))

    # -- $ref resolution ----------------------------------------------------
    def _lookup(self, ref):
        """(node, canonical pointer) for a local $ref, or (None, ()) if invalid."""
        if not ref.startswith("#/"):
            return None, ()
        node, pointer = self.doc, []
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                return None, ()
            node = node[part]
            pointer.append(part)
        return (node, tuple(pointer)) if isinstance(node, dict) else (None, ())

    def _resolve(self, schema, pointer, seen):
        """Follow a single $ref, returning (node, canonical pointer)."""
        depth = 0
        while isinstance(schema, dict) and "$ref" in schema and depth < MAX_DEPTH:
            ref = schema["$ref"]
            if ref in seen:
                return None, ()
            seen = seen | {ref}
            schema, pointer = self._lookup(ref)
            depth += 1
        return schema, pointer

    # -- object shape (used by both detection and enrichment) ---------------
    def concrete_objects(self, schema, pointer=(), depth=0, seen=frozenset()):
        """Every concrete object schema a value here may match.

        Composition (anyOf/oneOf/allOf) yields several; a plain object yields
        one. Each carries the canonical pointer to its node so annotations land
        in the right place.
        """
        if depth > MAX_DEPTH or not isinstance(schema, dict):
            return []
        node, node_ptr = self._resolve(schema, pointer, seen)
        if node is None:
            return []
        if "$ref" in schema:
            seen = seen | {schema["$ref"]}

        results = []
        if node.get("properties") is not None or node.get("type") == "object" \
                or "additionalProperties" in node:
            extra = node.get("additionalProperties")
            open_map = isinstance(extra, dict) or extra is True
            results.append(ObjectSchema(node, node_ptr, open_map))

        for key in ("anyOf", "oneOf", "allOf"):
            for sub in node.get(key) or []:
                results.extend(self.concrete_objects(sub, (), depth + 1, seen))
        return results

    def schema_info(self, schema, pointer=()):
        """Flatten a schema (through $ref and composition) into a SchemaInfo.

        Conservative on purpose: if any branch is unconstrained, the type set is
        cleared (no type check) so we never invent a mismatch from something we
        could not fully understand. `required`/`enum` are only taken where they
        are unambiguous (direct node or allOf, single enum)."""
        info = SchemaInfo(set(), False, None, {}, set(), False, (), (), {}, ())
        state = {"unknown": False, "enum_count": 0}
        self._collect(schema, pointer, info, 0, frozenset(), state, in_union=False)
        if state["unknown"]:
            info.types = set()          # cannot constrain the type
        if state["enum_count"] > 1:
            info.enum = None            # ambiguous across branches
        return info

    def _collect(self, schema, pointer, info, depth, seen, state, in_union):
        if depth > MAX_DEPTH or not isinstance(schema, dict):
            state["unknown"] = True
            return
        node, ptr = self._resolve(schema, pointer, seen)
        if node is None:
            state["unknown"] = True
            return
        if "$ref" in schema:
            seen = seen | {schema["$ref"]}

        constrained = False
        if node.get("nullable") is True:
            info.nullable = True

        t = node.get("type")
        if isinstance(t, list):
            constrained = True
            for x in t:
                info.nullable = info.nullable or x == "null"
                if x != "null":
                    info.types.add(x)
        elif isinstance(t, str):
            constrained = True
            info.types.add(t)

        if isinstance(node.get("enum"), list):
            constrained = True
            state["enum_count"] += 1
            if info.enum is None:
                info.enum = list(node["enum"])

        props = node.get("properties")
        if isinstance(props, dict):
            constrained = True
            info.types.add("object")
            if not info.object_pointer:
                info.object_pointer = ptr
            for k, sub in props.items():
                info.properties.setdefault(
                    k, (sub, ptr + ("properties", k) if ptr else ()))

        extra = node.get("additionalProperties")
        if isinstance(extra, dict) or extra is True:
            constrained = True
            info.types.add("object")
            info.open_map = True
            if not info.open_map_pointer:
                info.open_map_pointer = ptr

        if isinstance(node.get("required"), list) and not in_union:
            info.required.update(node["required"])

        if isinstance(node.get("items"), dict):
            constrained = True
            info.types.add("array")
            if not info.item_schema:
                info.item_schema = node["items"]
                info.item_pointer = ptr + ("items",) if ptr else ()

        for sub in node.get("allOf") or []:          # allOf merges (required kept)
            constrained = True
            self._collect(sub, (), info, depth + 1, seen, state, in_union)
        for key in ("anyOf", "oneOf"):               # union (required dropped)
            branches = node.get(key) or []
            if branches:
                constrained = True
                for sub in branches:
                    self._collect(sub, (), info, depth + 1, seen, state, in_union=True)

        if not constrained:
            state["unknown"] = True

    def item_schema(self, schema, pointer=(), depth=0, seen=frozenset()):
        """(schema, pointer) for elements of an array, through $ref/composition."""
        if depth > MAX_DEPTH or not isinstance(schema, dict):
            return {}, ()
        node, node_ptr = self._resolve(schema, pointer, seen)
        if node is None:
            return {}, ()
        if "$ref" in schema:
            seen = seen | {schema["$ref"]}
        if isinstance(node.get("items"), dict):
            items = node["items"]
            return items, (node_ptr + ("items",) if node_ptr else ())
        for key in ("anyOf", "oneOf", "allOf"):
            for sub in node.get(key) or []:
                found, ptr = self.item_schema(sub, (), depth + 1, seen)
                if found:
                    return found, ptr
        return {}, ()

    def response_schemas(self):
        """{(METHOD, normalised path): (schema, pointer)} for 2xx JSON responses."""
        out = {}
        for path, item in (self.doc.get("paths") or {}).items():
            if not isinstance(item, dict):
                continue
            for method, op in item.items():
                if not isinstance(op, dict) or "responses" not in op:
                    continue
                responses = op["responses"]
                code = "200" if "200" in responses else next(
                    (c for c in responses if str(c).startswith("2")), None)
                if code is None or not isinstance(responses[code], dict):
                    continue
                schema = ((responses[code].get("content") or {})
                          .get("application/json", {})
                          .get("schema"))
                if isinstance(schema, dict):
                    ptr = ("paths", path, method, "responses", code,
                           "content", "application/json", "schema")
                    out[(method.upper(), normalise_path(path))] = (schema, ptr)
        return out

    def node_at(self, pointer):
        """Return the live dict at a canonical pointer (for enrichment)."""
        node = self.doc
        for part in pointer:
            node = node[part]
        return node


def normalise_path(path):
    """Make trace and spec paths comparable: {id} and {customer} both -> {}."""
    import re
    return re.sub(r"\{[^}]+\}", "{}", path)


def pointer_str(pointer):
    """Canonical pointer tuple -> JSON Pointer string for reports."""
    if not pointer:
        return None
    return "#/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in pointer)


def parse_pointer(text):
    """JSON Pointer string -> canonical pointer tuple (inverse of pointer_str)."""
    if not text or not text.startswith("#/"):
        return ()
    return tuple(p.replace("~1", "/").replace("~0", "~") for p in text[2:].split("/"))
