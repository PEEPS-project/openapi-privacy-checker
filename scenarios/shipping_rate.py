"""Scenario: create a shipping rate.

    POST /v1/shipping_rates   (owner contact in metadata)
    GET  /v1/shipping_rates/{id}
    POST /v1/shipping_rates/{id}  active=false   (archive; cannot be deleted)

Exercises the shipping_rate schema.
"""
from locust import task

from common import StripeScenario


class ShippingRate(StripeScenario):

    @task
    def create_shipping_rate(self):
        print("\n=== Shipping rate: create a flat rate ===")
        rate = self.post("/v1/shipping_rates", {
            "display_name": "Standard",
            "type": "fixed_amount",
            "fixed_amount[amount]": "500",
            "fixed_amount[currency]": "usd",
            "metadata[owner_phone]": "+33712345678",
        }, step="1 create shipping rate")
        if not rate:
            return

        self.get(f"/v1/shipping_rates/{rate['id']}", step="2 read shipping rate",
                 name="/v1/shipping_rates/{id}")
        self.post(f"/v1/shipping_rates/{rate['id']}", {"active": "false"},
                  step="3 archive shipping rate", name="/v1/shipping_rates/{id}")
        self.done()
