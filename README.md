# OpenAPI Privacy Checker

A command-line tool that detects privacy and GDPR inconsistencies between an OpenAPI specification and the real REST API it describes, then enriches the specification to close those gaps.

> Status: research prototype, currently under development as part of the PEEPS project.

## The problem

Many developers rely on an OpenAPI specification as the single source of truth for their REST API. It documents every endpoint, what it accepts, and what it returns. Teams generate client code, tests, and documentation from it, and consumers trust it to know how the API behaves.

But this contract is usually silent about privacy. It rarely says which fields are personal data, or which GDPR rules apply to them. And because the specification and the real implementation drift apart over time, the running API can return personal data that the specification never declared. A common example is sensitive data hidden inside a generic `metadata` object that the spec only types as a plain object.

The result is a privacy blind spot. Personal data flows through the API in ways nobody documented, GDPR obligations go unmet, and no one notices because the specification looks complete. Checking this by hand does not scale to APIs with hundreds of endpoints.

## The solution

This tool treats the OpenAPI specification as a contract and checks whether the real API keeps it for personal data. It reads the spec, generates and sends requests to the running API, compares the responses against what the spec promised, and flags any personal data that is undeclared, exposed in a URL, or returned without authentication, each mapped to a GDPR article. It then proposes the privacy annotations the spec was missing.

In short: make the OpenAPI specification tell the truth about privacy.

The tool works in three stages:

1. **Generate and send.** Read the spec, build requests for every method (GET, POST, PUT, DELETE), fill them with fake data, and send them to the real API. Resource ids are chained from one response into the next, so endpoints that need an existing resource can still be reached.

2. **Detect.** Compare each real response against what the spec declares, and flag:
   * Undeclared personal data returned in a response (GDPR Art. 5, 13 and 14; special category data such as an SSN maps to Art. 9)
   * Personal data in a URL path or query parameter (Art. 25)
   * Personal data returned without authentication (Art. 32)

3. **Enrich.** For every issue found, add the missing privacy annotation (`x-pii`, `x-pii-category`, `x-gdpr-article`, and so on) to a copy of the spec, leaving the original untouched.

It runs as a CLI and is designed to integrate into CI/CD pipelines, failing a build when privacy violations are found, so issues are caught before release.

## Use case: the Stripe API

The tool is validated on the Stripe API in its sandbox, a large, real world payments platform rich in personal data.

* Stripe provides a public OpenAPI specification (around 414 paths and 1400 schemas).
* Its sandbox offers safe test keys, with no real money and no real users.
* This makes it a realistic stress test for spec versus reality privacy checking on a production grade API.

One inconsistency found: a customer response hid personal data inside a generic `metadata` object.

```json
{
  "id": "cus_123",
  "metadata": {
    "ssn": "123-45-6789",
    "dob": "1990-01-15"
  }
}
```

The specification only types `metadata` as a generic object, so it never declares an SSN. That undeclared special category data is a GDPR Article 9 concern, exactly the kind of gap this tool surfaces and then annotates.

## How it works

The pipeline reads the spec, orders the endpoints so that the ones producing resource ids run before the ones needing them, then loops over every endpoint: build a request, send it, collect any ids from the response for later use, and compare the response to the spec. Findings drive the enrichment step, which outputs an annotated copy of the specification alongside a report.

