# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)


class itl_quotations_cancel(models.Model):
    _inherit = 'sale.order'
    def metodo_prueba(self):
        _logger.info("--> FONG Test")
        self.write({'state': 'cancel'})

class itl_payslip_cancel(models.Model):
    _inherit = 'hr.payslip'
    def payslip_cancel(self):
        _logger.info("--> FONG Test")
 #       self.write({'state': 'cancel'})
        
#domain=[('state','=', 'done')]
        

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         self.value2 = float(self.value) / 100