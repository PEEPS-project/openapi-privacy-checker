"""Scenario 1 - Customer onboarding (plants PII in metadata).

    POST   /v1/customers        email, name, phone + ssn / date_of_birth /
                                national_id in metadata
    GET    /v1/customers/{id}   read back - the privacy-relevant call
    GET    /v1/customers        list
    DELETE /v1/customers/{id}   clean up

Run:  locust -f scenarios/onboarding.py --headless -u 1 -r 1 -t 20s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario


class Onboarding(StripeScenario):

    @task
    def onboard(self):
        print("\n=== Onboarding: sign up a customer ===")

        customer = self.post("/v1/customers", {
            "email": "marie.leblanc@example-peeps.com",
            "name": "Marie Leblanc",
            "phone": "+33612345678",
            "metadata[ssn]": "123-45-6789",
            "metadata[date_of_birth]": "1990-01-15",
            "metadata[national_id]": "FR9012345678",
        }, step="1 create customer")
        if not customer:
            return
        cid = customer["id"]

        self.get(f"/v1/customers/{cid}", step="2 read customer",
                 name="/v1/customers/{id}")
        self.get("/v1/customers?limit=1", step="3 list customers",
                 name="/v1/customers")
        self.delete(f"/v1/customers/{cid}", step="4 delete customer",
                    name="/v1/customers/{id}")
        self.done()
