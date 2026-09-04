"""Scenario: set up a payment method for future use (SetupIntent).

    POST /v1/setup_intents   (financial identifiers in metadata)
    GET  /v1/setup_intents/{id}
    POST /v1/setup_intents/{id}/cancel   (clean up)

Exercises the setup_intent schema.
"""
from locust import task

from common import StripeScenario


class SetupIntent(StripeScenario):

    @task
    def setup(self):
        print("\n=== SetupIntent: save a card for later ===")
        intent = self.post("/v1/setup_intents", {
            "payment_method_types[0]": "card",
            "metadata[customer_iban]": "FR7630006000011234567890189",
            "metadata[ssn]": "123-45-6789",
        }, step="1 create setup intent")
        if not intent:
            return

        self.get(f"/v1/setup_intents/{intent['id']}", step="2 read setup intent",
                 name="/v1/setup_intents/{id}")
        self.post(f"/v1/setup_intents/{intent['id']}/cancel", {},
                  step="3 cancel", name="/v1/setup_intents/{id}/cancel")
        self.done()
