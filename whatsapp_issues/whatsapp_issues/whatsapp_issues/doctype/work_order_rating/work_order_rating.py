import frappe
from frappe.model.document import Document


class WorkOrderRating(Document):
    def validate(self):
        if self.rating is None or not (1 <= int(self.rating) <= 5):
            frappe.throw("Rating must be between 1 and 5.")
        if not self.rated_on:
            self.rated_on = frappe.utils.now_datetime()
