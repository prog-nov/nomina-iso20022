from odoo import fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"
    state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('account_review', 'Approve For Sale Order'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
    ], string='Status',
        readonly=True, copy=False, index=True, tracking=3, default='draft')
    in_approve = fields.Boolean('In Approve')

    def action_confirm(self):
        partner = self.partner_id

        if partner.credit_limit > 0:
            if partner.credit > partner.credit_limit:
                view_id = self.env.ref(
                    'customer_credit_management.credit_management_limit_wizard').id
                return {
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'sale.customer.credit.limit.wizard',
                    'target': 'new',
                    'type': 'ir.actions.act_window',
                    'name': 'Customer Credit Limit',
                    'views': [[view_id, 'form']],
                    'context': {'current_id': self.id}
                }
            else:
                credit = 0
                total_sales = 0
                sale_amt = 0
                inv_total_amt = 0
                inv_rec = self.env['account.invoice'].search([
                    ('partner_id', '=', partner.id),
                    ('state', 'not in', ['draft', 'cancel'])])
                sale_amount = self.search(
                    [('partner_id', '=', partner.id),
                     ]).mapped('amount_total')
                sale_amt = sum([sale for sale in sale_amount])
                for inv in inv_rec:
                    inv_total_amt += inv.amount_total - inv.residual
                if partner.parent_id and partner.parent_id.credit < 0:
                    credit = partner.parent_id.credit
                elif partner.credit < 0:
                    credit = partner.credit
                total_sales = sale_amt + credit - inv_total_amt
                if total_sales > partner.credit_limit:
                    view_id = self.env.ref(
                        'customer_credit_management.credit_management_limit_wizard').id
                    return {
                        'view_type': 'form',
                        'view_mode': 'form',
                        'res_model': 'sale.customer.credit.limit.wizard',
                        'target': 'new',
                        'type': 'ir.actions.act_window',
                        'name': 'Customer Credit Limit',
                        'views': [[view_id, 'form']],
                        'context': {'current_id': self.id}
                    }
                else:
                    super(SaleOrder, self).action_confirm()
        else:
            super(SaleOrder, self).action_confirm()

    def action_account_approve(self):
        if self.env.user.has_group('sales_team.group_sale_manager'):
            super(SaleOrder, self).action_confirm()
        else:
            raise UserError((
                " Please contact your Administrator For SALE ORDER approval"))
