from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    credit_limit = fields.Integer('Credit Limit')
