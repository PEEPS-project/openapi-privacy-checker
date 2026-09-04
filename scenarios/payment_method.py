"""Scenario 6 - Payment method with billing identity.

    POST /v1/payment_methods       type=card, tok_visa + billing_details
                                   (name, email, address city/country)
    GET  /v1/payment_methods/{id}  read back

`billing_details` is declared personal data: a good control that the detector
does NOT flag name / email where the spec declares them.

Run:  locust -f scenarios/payment_method.py --headless -u 1 -r 1 -t 20s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario


class PaymentMethod(StripeScenario):

    @task
    def create_card(self):
        print("\n=== Payment method: card with billing identity ===")

        method = self.post("/v1/payment_methods", {
            "type": "card",
            "card[token]": "tok_visa",
            "billing_details[name]": "Marie Leblanc",
            "billing_details[email]": "marie.leblanc@example-peeps.com",
            "billing_details[address][city]": "Paris",
            "billing_details[address][country]": "FR",
        }, step="1 create payment method")
        if not method:
            return

        self.get(f"/v1/payment_methods/{method['id']}",
                 step="2 read payment method", name="/v1/payment_methods/{id}")
        # an unattached payment method needs no clean-up: it simply expires
        self.done()
