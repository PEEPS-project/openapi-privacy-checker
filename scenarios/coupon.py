"""Scenario 5 - Coupon (marketing contact data in metadata).

    POST   /v1/coupons        25% off, once + campaign_contact_email in metadata
    GET    /v1/coupons/{id}
    GET    /v1/coupons        list
    DELETE /v1/coupons/{id}   clean up

Run:  locust -f scenarios/coupon.py --headless -u 1 -r 1 -t 20s \
              --host https://api.stripe.com
"""
from locust import task

from common import StripeScenario


class Coupon(StripeScenario):

    @task
    def create_coupon(self):
        print("\n=== Coupon: create a marketing discount ===")

        coupon = self.post("/v1/coupons", {
            "percent_off": "25",
            "duration": "once",
            "metadata[campaign_contact_email]": "campaign@example-peeps.com",
        }, step="1 create coupon")
        if not coupon:
            return

        self.get(f"/v1/coupons/{coupon['id']}", step="2 read coupon",
                 name="/v1/coupons/{id}")
        self.get("/v1/coupons?limit=1", step="3 list coupons",
                 name="/v1/coupons")
        self.delete(f"/v1/coupons/{coupon['id']}", step="4 delete coupon",
                    name="/v1/coupons/{id}")
        self.done()
