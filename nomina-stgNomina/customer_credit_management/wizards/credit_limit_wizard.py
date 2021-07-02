from odoo import models


class SaleCustomerCreditLimitWizard(models.TransientModel):
    _name = 'sale.customer.credit.limit.wizard'

    def action_exceed_limit(self):
        order_rec = self.env['sale.order'].browse(self._context['current_id'])
        order_rec.write({'state': "account_review"})
