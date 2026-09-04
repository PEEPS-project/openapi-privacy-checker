"""Scenario: read-only account data (broad schema coverage, no writes).

    GET /v1/balance
    GET /v1/events
    GET /v1/payment_methods

Exercises the balance, event, and list schemas without creating anything.
"""
from locust import task

from common import StripeScenario


class AccountData(StripeScenario):

    @task
    def read_account(self):
        print("\n=== Account data: read-only sweep ===")
        self.get("/v1/balance", step="1 read balance", name="/v1/balance")
        self.get("/v1/events?limit=3", step="2 read events", name="/v1/events")
        self.get("/v1/payment_methods?type=card&limit=3",
                 step="3 list payment methods", name="/v1/payment_methods")
        self.done()
