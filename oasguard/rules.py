"""Personal-data classification, driven by privacy_rules.yaml."""
import os
import re
from dataclasses import dataclass

import yaml

DEFAULT_RULES = os.path.join(os.path.dirname(__file__), "privacy_rules.yaml")


@dataclass(frozen=True)
class Classification:
    category: str
    gdpr: str
    severity: str
    signal: str        # "field name", "value format", or "text scan"
    verify: bool = False
    label: str = ""


@dataclass(frozen=True)
class SensitiveHit:
    category: str
    classification: str    # GDPR/security text
    severity: str
    kind: str              # inconsistency type (secret_exposure, ...)
    verify: bool = False


def _snake(field):
    """customerEmail -> customer_email;  date-of-birth -> date_of_birth."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", field)
    return re.sub(r"[^a-zA-Z0-9]+", "_", spaced).strip("_").lower()


class PrivacyRules:
    """Classify a field/value as personal data, scan free text, and match the
    registry of sensitive (secret / financial / consent) fields."""

    def __init__(self, phrases, tokens, value_patterns, text_patterns,
                 sensitive, excl_names, excl_tokens):
        self.phrases = phrases
        self.tokens = tokens
        self.value_patterns = value_patterns   # [(regex, rule)]
        self.text_patterns = text_patterns     # [(regex, rule)]
        self.sensitive = sensitive             # [rule dict with compiled path]
        self.excl_names = excl_names
        self.excl_tokens = excl_tokens

    @classmethod
    def load(cls, path=None):
        with open(path or DEFAULT_RULES) as f:
            data = yaml.safe_load(f) or {}
        excl = data.get("exclusions") or {}
        compile_rules = lambda key: [(re.compile(r["pattern"]), r)
                                     for r in data.get(key) or []]
        return cls(
            data.get("phrases") or {},
            data.get("tokens") or {},
            compile_rules("value_patterns"),
            compile_rules("text_patterns"),
            data.get("sensitive") or [],
            set(excl.get("field_names") or []),
            set(excl.get("tokens") or []),
        )

    # -- name / whole-value classification ---------------------------------
    def classify(self, field, value=None):
        """Return a Classification if `field` is personal data, else None."""
        snake = _snake(field)
        tokens = {t for t in snake.split("_") if t}
        if snake in self.excl_names or (tokens & self.excl_tokens):
            return None

        padded = f"_{snake}_"
        for phrase, rule in self.phrases.items():
            if f"_{phrase}_" in padded:
                return self._make(rule, "field name")
        for token, rule in self.tokens.items():
            if token in tokens:
                return self._make(rule, "field name")
        if isinstance(value, str):
            stripped = value.strip()
            for regex, rule in self.value_patterns:
                if regex.match(stripped):
                    return self._make(rule, "value format")
        return None

    # -- free-text scanning (PII embedded in prose) ------------------------
    def scan_text(self, text):
        """Return a Classification for the first PII found inside `text`, plus
        the matched snippet, or (None, None)."""
        if not isinstance(text, str) or len(text) < 5:
            return None, None
        for regex, rule in self.text_patterns:
            m = regex.search(text)
            if m:
                return self._make(rule, "text scan"), m.group(0)
        return None, None

    # -- sensitive registry (secrets / financial / consent) ----------------
    def sensitive_hit(self, field, path):
        """Return a SensitiveHit if `field`/`path` matches the registry."""
        tokens = {t for t in _snake(field).split("_") if t}
        snake_path = path.lower()
        for rule in self.sensitive:
            if rule["match"] not in tokens and rule["match"] not in _snake(field):
                continue
            if rule.get("path") and rule["path"] not in snake_path:
                continue
            return SensitiveHit(rule["category"], rule["classification"],
                                rule["severity"], rule["kind"],
                                bool(rule.get("verify", False)))
        return None

    @staticmethod
    def _make(rule, signal):
        return Classification(rule["category"], rule["gdpr"], rule["severity"],
                              signal, bool(rule.get("verify", False)),
                              rule.get("label", ""))
