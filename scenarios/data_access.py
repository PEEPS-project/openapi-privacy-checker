"""Scenario: subject access request (GDPR Art. 15 - right of access).

Simulates answering "send me everything you hold about me": build a customer
with data spread across several objects, then read every endpoint that returns
something about them.

    customer + payment method + invoice item
        ->  read profile, payment methods, invoices, invoice items

This is the widest sweep of personal data in one trace, so it exercises the
most response schemas.

Run:  locust -f scenarios/data_access.py --headless -u 1 -r 1 -t 15s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario, PERSONAL_METADATA


class DataAccess(StripeScenario):

    @task
    def subject_access_request(self):
        print("\n=== Data access: gather everything about one person ===")

        customer = self.create_customer(step="1 create customer")
        if not customer:
            return
        cid = customer["id"]

        method = self.post("/v1/payment_methods", {
            "type": "card",
            "card[token]": "tok_visa",
            "billing_details[name]": "Marie Leblanc",
            "billing_details[email]": "marie.leblanc@example-peeps.com",
            "billing_details[phone]": "+33612345678",
        }, step="2 create payment method")
        if not method:
            return
        self.post(f"/v1/payment_methods/{method['id']}/attach", {"customer": cid},
                  step="3 attach card", name="/v1/payment_methods/{id}/attach")

        self.post("/v1/invoiceitems", {
            "customer": cid, "amount": "2000", "currency": "usd",
            "description": "Consulting",
            **PERSONAL_METADATA,
        }, step="4 add invoice item")

        # --- the access request itself: read everything back ---------------
        self.get(f"/v1/customers/{cid}", step="5 read profile",
                 name="/v1/customers/{id}")
        self.get(f"/v1/payment_methods?customer={cid}&type=card",
                 step="6 read payment methods", name="/v1/payment_methods")
        self.get(f"/v1/invoiceitems?customer={cid}", step="7 read invoice items",
                 name="/v1/invoiceitems")
        self.get(f"/v1/invoices?customer={cid}", step="8 read invoices",
                 name="/v1/invoices")
        self.get(f"/v1/subscriptions?customer={cid}", step="9 read subscriptions",
                 name="/v1/subscriptions")

        # clean up
        self.delete(f"/v1/customers/{cid}", step="10 delete customer",
                    name="/v1/customers/{id}")
        self.done()
