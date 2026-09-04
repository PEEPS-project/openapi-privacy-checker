"""Scenario: create a tax rate.

    POST /v1/tax_rates   (owner contact in metadata)
    GET  /v1/tax_rates/{id}
    GET  /v1/tax_rates   list
    POST /v1/tax_rates/{id}  active=false   (archive; tax rates cannot be deleted)

Exercises the tax_rate schema.
"""
from locust import task

from common import StripeScenario


class TaxRate(StripeScenario):

    @task
    def create_tax_rate(self):
        print("\n=== Tax rate: create a VAT rate ===")
        rate = self.post("/v1/tax_rates", {
            "display_name": "VAT",
            "inclusive": "false",
            "percentage": "20",
            "metadata[owner_email]": "owner@example-peeps.com",
        }, step="1 create tax rate")
        if not rate:
            return

        self.get(f"/v1/tax_rates/{rate['id']}", step="2 read tax rate",
                 name="/v1/tax_rates/{id}")
        self.get("/v1/tax_rates?limit=1", step="3 list tax rates",
                 name="/v1/tax_rates")
        self.post(f"/v1/tax_rates/{rate['id']}", {"active": "false"},
                  step="4 archive tax rate", name="/v1/tax_rates/{id}")
        self.done()
