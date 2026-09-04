"""Scenario: personal data placed in DECLARED free-text fields.

A developer often writes a customer's email or phone into a human-readable
field like an invoice description or footer. Those fields are declared as plain
strings, so a spec-only review sees nothing — but the value is personal data.

    customer -> invoice item -> invoice with PII in description + footer -> read

Demonstrates the `pii_in_free_text` category.
"""
from locust import task

from common import StripeScenario


class FreeTextPII(StripeScenario):

    @task
    def free_text(self):
        print("\n=== Free-text PII: email/phone inside declared strings ===")

        customer = self.create_customer(step="1 create customer")
        if not customer:
            return
        cid = customer["id"]

        self.post("/v1/products", {
            "name": "Consulting",
            "description": "Delivered by Marie Leblanc, reach her at "
                           "marie.leblanc@example-peeps.com",
        }, step="2 product with email in description")

        self.post("/v1/invoiceitems", {
            "customer": cid, "amount": "2000", "currency": "usd",
            "description": "Consulting for Marie, phone +33 6 12 34 56 78",
        }, step="3 invoice item with phone in description")

        invoice = self.post("/v1/invoices", {
            "customer": cid,
            "description": "Contact marie.leblanc@example-peeps.com for questions",
            "footer": "Billing contact: marie.leblanc@example-peeps.com",
        }, step="4 invoice with email in description + footer")
        if not invoice:
            return

        self.get(f"/v1/invoices/{invoice['id']}", step="5 read invoice",
                 name="/v1/invoices/{id}")
        self.delete(f"/v1/invoices/{invoice['id']}", step="6 delete draft invoice",
                    name="/v1/invoices/{id}")
        self.delete(f"/v1/customers/{cid}", step="7 delete customer",
                    name="/v1/customers/{id}")
        self.done()
