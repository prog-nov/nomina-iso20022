# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_mx_edi_pac_contract = fields.Char(
        related='company_id.l10n_mx_edi_pac_contract',
        string='MX PAC contract*', readonly=False)
