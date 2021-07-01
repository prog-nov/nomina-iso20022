# -*- coding: utf-8 -*-

from odoo import api, fields, models
#from odoo.addons.l10n_mx_edi.hooks import _load_xsd_files


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_mx_edi_pac = fields.Selection(
        selection=[('finkok', 'Finkok'), ('solfact',
                                          'Solucion Factible'), ('prodigia', 'Prodigia')],
        string='PAC',
        help='The PAC that will sign/cancel the invoices',
    )

    l10n_mx_edi_pac_contract = fields.Char(
        string='Contrato Prodigia',
        help='La clave del contrato de Prodigia')
