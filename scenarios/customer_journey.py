"""Scenario: a realistic Stripe customer flow (Stripe test mode).

    create customer  ->  read it back  ->  list customers  ->  delete (clean up)

The create step stores an SSN and a date of birth inside `metadata`. Stripe's
spec types `metadata` only as open string key-value pairs, so it never declares
those fields. That is the gap the detector later reports.

Run it:  locust -f scenarios/customer_journey.py --headless -u 1 -r 1 -t 6s \
                 --host https://api.stripe.com
"""
import os
import sys

from dotenv import load_dotenv
from locust import HttpUser, task, between

# capture.py lives next to this file; import it so its trace hooks register.
sys.path.insert(0, os.path.dirname(__file__))
import capture  # noqa: E402,F401

load_dotenv()
API_KEY = os.getenv("STRIPE_API_KEY")


class CustomerJourney(HttpUser):
    wait_time = between(0.2, 0.4)

    def on_start(self):
        if not API_KEY:
            print("\nERROR: put STRIPE_API_KEY=sk_test_... in a .env file first.\n")
            self.environment.runner.quit()
            return
        # Stripe auth: secret key as the basic-auth username, empty password.
        self.client.auth = (API_KEY, "")

    @task
    def journey(self):
        print("\n=== Stripe customer journey (test mode) ===")

        # 1. CREATE a customer, hiding personal data in metadata.
        with self.client.post(
            "/v1/customers",
            data={
                "email": "marie.leblanc@example-peeps.com",
                "name": "Marie Leblanc",
                "metadata[ssn]": "123-45-6789",
                "metadata[date_of_birth]": "1990-01-15",
            },
            name="/v1/customers",
            context={"step": "1 create customer"},
            catch_response=True,
        ) as r:
            if r.status_code not in (200, 201):
                r.failure(f"create failed: {r.status_code} {r.text[:120]}")
                self.environment.runner.quit()
                return
            customer_id = r.json()["id"]

        # 2. READ the customer back (the privacy-relevant call).
        self.client.get(
            f"/v1/customers/{customer_id}",
            name="/v1/customers/{id}",
            context={"step": "2 read customer"},
        )

        # 3. LIST customers.
        self.client.get(
            "/v1/customers?limit=1",
            name="/v1/customers",
            context={"step": "3 list customers"},
        )

        # 4. CLEAN UP: delete the test customer we created.
        self.client.delete(
            f"/v1/customers/{customer_id}",
            name="/v1/customers/{id}",
            context={"step": "4 delete customer"},
        )

        self.environment.runner.quit()  # one clean pass
