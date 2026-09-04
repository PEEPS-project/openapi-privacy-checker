"""Shared building blocks for the Stripe privacy scenarios.

Every scenario:
  * authenticates with the Stripe TEST key from .env,
  * records its traffic to the trace file (via capture), and
  * tucks personal data into `metadata`, which Stripe's spec types only as open
    string pairs. The spec never declares that an `ssn` or `date_of_birth` lives
    there, so when the API returns it, the detector reports the gap.

Scenarios subclass `StripeScenario` and use its small post/get/delete helpers.
"""
import os
import sys

from dotenv import load_dotenv
from locust import HttpUser, between

# capture.py lives next to this file; importing it registers the trace hooks.
sys.path.insert(0, os.path.dirname(__file__))
import capture  # noqa: E402,F401

load_dotenv()
API_KEY = os.getenv("STRIPE_API_KEY")

# Personal data we deliberately hide in metadata (undeclared by the spec).
PERSONAL_METADATA = {
    "metadata[ssn]": "123-45-6789",
    "metadata[date_of_birth]": "1990-01-15",
}


class StripeScenario(HttpUser):
    """Base user: Stripe auth + request helpers.

    `abstract = True` tells Locust this is a base class, so it is never run on
    its own — only the concrete scenario in the file passed with `-f` runs.
    """
    abstract = True
    wait_time = between(0.2, 0.4)

    def on_start(self):
        if not API_KEY:
            print("\nERROR: put STRIPE_API_KEY=sk_test_... in a .env file first.\n")
            self.environment.runner.quit()
            return
        # Stripe auth: secret key as the basic-auth username, empty password.
        self.client.auth = (API_KEY, "")

    # -- helpers ------------------------------------------------------------
    def post(self, path, data, step, name=None):
        """POST a form; return the JSON body, or None on failure (and stop).

        On failure, print Stripe's own error message so the cause is visible.
        """
        with self.client.post(path, data=data, name=name or path,
                              context={"step": step}, catch_response=True) as r:
            if r.status_code not in (200, 201):
                try:
                    err = r.json().get("error", {})
                    detail = f"{err.get('type')}: {err.get('message')}"
                except Exception:
                    detail = r.text[:200]
                print(f"\n  !! [{step}] {path} -> HTTP {r.status_code}\n     {detail}\n")
                r.failure(f"{step} failed: {r.status_code}")
                self.environment.runner.quit()
                return None
            return r.json()

    def get(self, path, step, name=None):
        """GET a resource (the privacy-relevant read-back call)."""
        self.client.get(path, name=name or path, context={"step": step})

    def delete(self, path, step, name=None):
        """DELETE a resource (test clean-up)."""
        self.client.delete(path, name=name or path, context={"step": step})

    def create_customer(self, step="create customer"):
        """Create a customer with personal data hidden in metadata."""
        return self.post("/v1/customers", {
            "email": "marie.leblanc@example-peeps.com",
            "name": "Marie Leblanc",
            **PERSONAL_METADATA,
        }, step=step, name="/v1/customers")

    def done(self):
        self.environment.runner.quit()  # one clean pass
