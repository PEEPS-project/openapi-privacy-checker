"""Scenario 4 - Invoice flow (plants PII in invoice metadata).

    POST   /v1/customers       create a customer first, keep the id
    POST   /v1/invoices        customer=<id> + billing_contact_email / tax_id
                               in metadata
    GET    /v1/invoices/{id}   read back - the privacy-relevant call
    DELETE /v1/invoices/{id}   the invoice is a draft, so it can be deleted
    DELETE /v1/customers/{id}  clean up

Run:  locust -f scenarios/invoicing.py --headless -u 1 -r 1 -t 20s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario


class Invoicing(StripeScenario):

    @task
    def invoice(self):
        print("\n=== Invoicing: draft an invoice ===")

        customer = self.create_customer(step="1 create customer")
        if not customer:
            return
        cid = customer["id"]

        invoice = self.post("/v1/invoices", {
            "customer": cid,
            "metadata[billing_contact_email]": "billing@example-peeps.com",
            "metadata[tax_id]": "FR12345678901",
        }, step="2 create invoice")
        if not invoice:
            return

        self.get(f"/v1/invoices/{invoice['id']}", step="3 read invoice",
                 name="/v1/invoices/{id}")

        self.delete(f"/v1/invoices/{invoice['id']}", step="4 delete draft invoice",
                    name="/v1/invoices/{id}")
        self.delete(f"/v1/customers/{cid}", step="5 delete customer",
                    name="/v1/customers/{id}")
        self.done()
