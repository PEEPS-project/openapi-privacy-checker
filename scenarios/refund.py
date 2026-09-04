"""Scenario: refund a payment (GDPR — personal data on a refund record).

    customer  ->  charge a test card  ->  refund (PII in metadata)
              ->  read refund back  ->  delete customer

Uses Stripe's test payment method `pm_card_visa`, which succeeds immediately,
so a real charge exists to refund. The refund's metadata carries personal data
the spec never declared.

Run:  locust -f scenarios/refund.py --headless -u 1 -r 1 -t 6s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario, PERSONAL_METADATA


class Refund(StripeScenario):

    @task
    def refund(self):
        print("\n=== Refund: charge then refund ===")

        customer = self.create_customer(step="1 create customer")
        if not customer:
            return

        payment = self.post("/v1/payment_intents", {
            "amount": "2000",
            "currency": "usd",
            "customer": customer["id"],
            "payment_method": "pm_card_visa",
            "payment_method_types[0]": "card",
            "confirm": "true",
            "off_session": "true",
        }, step="2 charge card")
        if not payment:
            return

        refund = self.post("/v1/refunds", {
            "payment_intent": payment["id"],
            "reason": "requested_by_customer",
            **PERSONAL_METADATA,
        }, step="3 refund")
        if not refund:
            return

        # read the refund back — the privacy-relevant call
        self.get(f"/v1/refunds/{refund['id']}", step="4 read refund",
                 name="/v1/refunds/{id}")

        # clean up
        self.delete(f"/v1/customers/{customer['id']}", step="5 delete customer",
                    name="/v1/customers/{id}")
        self.done()
