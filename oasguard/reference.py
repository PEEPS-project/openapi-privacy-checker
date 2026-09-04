"""Human-readable text for the classifications the reports emit. Explanatory
labels, not legal advice."""

ARTICLES = {
    "Art. 6": ("Lawfulness of processing",
               "Ordinary personal data. Processing requires a lawful basis "
               "(consent, contract, legal obligation, etc.)."),
    "Art. 9": ("Special categories of personal data",
               "Highest-sensitivity data (health, beliefs, biometrics, genetics, "
               "sexual orientation, racial/ethnic origin, political opinion, "
               "trade-union membership). Processing is prohibited without a "
               "narrow exception."),
    "Art. 87": ("National identification numbers",
                "National and tax identifiers, whose processing is governed by "
                "specific Member-State law."),
}

CATEGORIES = {
    "national_id":        "National or tax identifier (SSN, passport, tax ID).",
    "financial":          "Financial identifier (IBAN, card, bank account).",
    "contact":            "Contact detail (email, phone).",
    "identity":           "Identity attribute (name, date of birth).",
    "location":           "Location or postal address.",
    "online_id":          "Online identifier (IP, MAC, device ID).",
    "health":             "Health data.",
    "belief":             "Religious or philosophical belief.",
    "trade_union":        "Trade-union membership.",
    "sexual_orientation": "Sexual orientation.",
    "political":          "Political opinion.",
    "ethnicity":          "Racial or ethnic origin.",
    "genetic":            "Genetic data.",
    "biometric":          "Biometric data.",
}

SEVERITIES = {
    "critical": "Special-category or strong identifier; exposure is a serious breach.",
    "high":     "Directly identifies or contacts a person; significant risk.",
    "medium":   "Contributes to identifying a person; lower but non-trivial risk.",
}

# The two finding classes. (label, description, remediation).
KINDS = {
    "violation": (
        "Spec violation",
        "Personal data returned by the API but not declared anywhere in the "
        "endpoint's response schema -- a genuine gap between the API and its "
        "specification.",
        "Add the field to the response schema (documenting its privacy "
        "classification), or stop returning it if it should not be exposed."),
    "exposure": (
        "Undocumented PII exposure",
        "Personal data inside a free-form map the schema declares with "
        "`additionalProperties` (e.g. `metadata`). The spec permits arbitrary "
        "keys, so it is technically conformant -- yet the data is real and no "
        "spec-only review could predict it. This is the exposure the tool exists "
        "to surface.",
        "Do not store personal data in free-form maps. Where unavoidable, "
        "minimise it, document it, and govern access; prefer a typed field with "
        "an explicit privacy annotation."),
}


def article_title(code):
    return ARTICLES.get(code, (code, ""))[0]


def article_note(code):
    return ARTICLES.get(code, (code, ""))[1]


def category_note(name):
    return CATEGORIES.get(name, "")


def severity_note(name):
    return SEVERITIES.get(name, "")
