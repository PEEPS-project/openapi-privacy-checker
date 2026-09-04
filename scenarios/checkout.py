"""Scenario: hosted checkout (GDPR - personal data collected by a payment page).

    create checkout session (customer_email + PII in metadata)
        ->  read the session back  ->  expire it (clean up)

A Checkout Session returns a `customer_details` block that Stripe fills in
itself, so it is a good place to look for data the spec may not declare.

Run:  locust -f scenarios/checkout.py --headless -u 1 -r 1 -t 10s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario, PERSONAL_METADATA


class Checkout(StripeScenario):

    @task
    def hosted_checkout(self):
        print("\n=== Checkout: create a hosted payment session ===")

        session = self.post("/v1/checkout/sessions", {
            "mode": "payment",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
            "customer_email": "marie.leblanc@example-peeps.com",
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][unit_amount]": "2000",
            "line_items[0][price_data][product_data][name]": "Consulting",
            **PERSONAL_METADATA,
        }, step="1 create checkout session")
        if not session:
            return

        # read the session back - the privacy-relevant call
        self.get(f"/v1/checkout/sessions/{session['id']}",
                 step="2 read session", name="/v1/checkout/sessions/{id}")

        # clean up (sessions cannot be deleted, only expired)
        self.post(f"/v1/checkout/sessions/{session['id']}/expire", {},
                  step="3 expire session",
                  name="/v1/checkout/sessions/{id}/expire")
        self.done()
