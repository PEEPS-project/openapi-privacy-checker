"""Scenario: right to erasure (GDPR Art. 17 - "delete my data").

    customer  ->  pay with a test card  ->  DELETE the customer
              ->  read the payment back and see what personal data survives

Deleting a customer does not delete the payment records attached to them. This
reads the payment intent and charge afterwards, so the trace shows exactly which
personal data a deletion request leaves behind - the interesting question for
Art. 17, and one only real traffic can answer.

Run:  locust -f scenarios/erasure.py --headless -u 1 -r 1 -t 15s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario, PERSONAL_METADATA


class Erasure(StripeScenario):

    @task
    def erase(self):
        print("\n=== Erasure: delete a customer, inspect what remains ===")

        customer = self.create_customer(step="1 create customer")
        if not customer:
            return
        cid = customer["id"]

        payment = self.post("/v1/payment_intents", {
            "amount": "2000",
            "currency": "usd",
            "customer": cid,
            "payment_method": "pm_card_visa",
            "payment_method_types[0]": "card",
            "confirm": "true",
            "off_session": "true",
            "receipt_email": "marie.leblanc@example-peeps.com",
            **PERSONAL_METADATA,
        }, step="2 pay with test card")
        if not payment:
            return

        # the erasure request
        self.delete(f"/v1/customers/{cid}", step="3 delete customer",
                    name="/v1/customers/{id}")

        # what personal data survived the deletion?
        self.get(f"/v1/payment_intents/{payment['id']}",
                 step="4 read payment after erasure",
                 name="/v1/payment_intents/{id}")
        self.get("/v1/charges?limit=1", step="5 read charges after erasure",
                 name="/v1/charges")
        self.done()
