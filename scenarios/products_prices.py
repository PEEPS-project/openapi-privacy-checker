"""Scenario 2 - Product and price setup (plants PII in product metadata).

    POST /v1/products      name + owner_email / owner_phone in metadata
    POST /v1/prices        product=<id>, 1500 eur, monthly
    GET  /v1/products/{id}
    GET  /v1/prices/{id}
    cleanup: archive the price (active=false), then delete the product

Run:  locust -f scenarios/products_prices.py --headless -u 1 -r 1 -t 20s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario


class ProductsPrices(StripeScenario):

    @task
    def setup_catalogue(self):
        print("\n=== Products and prices: catalogue setup ===")

        product = self.post("/v1/products", {
            "name": "PEEPS Pro",
            "metadata[owner_email]": "owner@example-peeps.com",
            "metadata[owner_phone]": "+33712345678",
        }, step="1 create product")
        if not product:
            return

        price = self.post("/v1/prices", {
            "product": product["id"],
            "unit_amount": "1500",
            "currency": "eur",
            "recurring[interval]": "month",
        }, step="2 create price")
        if not price:
            return

        self.get(f"/v1/products/{product['id']}", step="3 read product",
                 name="/v1/products/{id}")
        self.get(f"/v1/prices/{price['id']}", step="4 read price",
                 name="/v1/prices/{id}")

        # Clean up by archiving. Neither object can be deleted here: a price is
        # never deletable, and Stripe refuses to delete a product that has any
        # user-created price attached to it.
        self.post(f"/v1/prices/{price['id']}", {"active": "false"},
                  step="5 archive price", name="/v1/prices/{id}")
        self.post(f"/v1/products/{product['id']}", {"active": "false"},
                  step="6 archive product", name="/v1/products/{id}")
        self.done()
