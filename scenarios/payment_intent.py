"""Scenario 3 - Payment intent (financial identifiers in metadata).

    POST /v1/payment_intents   2000 eur + customer_iban / customer_full_name
                               in metadata
    GET  /v1/payment_intents/{id}
    GET  /v1/payment_intents   list
    cleanup: cancel the intent (it is never confirmed, so nothing is charged)

Run:  locust -f scenarios/payment_intent.py --headless -u 1 -r 1 -t 20s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario


class PaymentIntent(StripeScenario):

    @task
    def create_intent(self):
        print("\n=== Payment intent: authorise a payment ===")

        intent = self.post("/v1/payment_intents", {
            "amount": "2000",
            "currency": "eur",
            "metadata[customer_iban]": "FR7630006000011234567890189",
            "metadata[customer_full_name]": "Marie Leblanc",
        }, step="1 create payment intent")
        if not intent:
            return

        self.get(f"/v1/payment_intents/{intent['id']}",
                 step="2 read payment intent", name="/v1/payment_intents/{id}")
        self.get("/v1/payment_intents?limit=1", step="3 list payment intents",
                 name="/v1/payment_intents")

        # clean up: cancel the unconfirmed intent
        self.post(f"/v1/payment_intents/{intent['id']}/cancel", {},
                  step="4 cancel intent", name="/v1/payment_intents/{id}/cancel")
        self.done()
