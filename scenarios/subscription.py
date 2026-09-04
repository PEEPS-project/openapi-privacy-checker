"""Scenario 7 - Subscription lifecycle (chains customer -> product -> price).

    POST   /v1/customers          keep the id
    POST   /v1/products           keep the id
    POST   /v1/prices             product=<id>, keep the price id
    POST   /v1/subscriptions      customer + price + subscriber_ssn in metadata
    GET    /v1/subscriptions/{id} read back - the privacy-relevant call
    DELETE /v1/subscriptions/{id} cancel
    DELETE /v1/customers/{id}     clean up

Dependencies are solved by order: each returned id feeds the next step.

Run:  locust -f scenarios/subscription.py --headless -u 1 -r 1 -t 20s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario


class Subscription(StripeScenario):

    @task
    def subscribe(self):
        print("\n=== Subscription: full lifecycle ===")

        customer = self.create_customer(step="1 create customer")
        if not customer:
            return

        product = self.post("/v1/products", {"name": "PEEPS Pro"},
                            step="2 create product")
        if not product:
            return

        price = self.post("/v1/prices", {
            "product": product["id"],
            "unit_amount": "1500",
            "currency": "eur",
            "recurring[interval]": "month",
        }, step="3 create price")
        if not price:
            return

        subscription = self.post("/v1/subscriptions", {
            "customer": customer["id"],
            "items[0][price]": price["id"],
            "payment_behavior": "default_incomplete",
            "metadata[subscriber_ssn]": "123-45-6789",
        }, step="4 create subscription")
        if not subscription:
            return

        self.get(f"/v1/subscriptions/{subscription['id']}",
                 step="5 read subscription", name="/v1/subscriptions/{id}")

        self.delete(f"/v1/subscriptions/{subscription['id']}",
                    step="6 cancel subscription", name="/v1/subscriptions/{id}")
        self.delete(f"/v1/customers/{customer['id']}",
                    step="7 delete customer", name="/v1/customers/{id}")
        self.done()
