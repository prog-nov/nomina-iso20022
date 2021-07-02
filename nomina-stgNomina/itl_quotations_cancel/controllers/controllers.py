# -*- coding: utf-8 -*-
from odoo import http

# class ItlQuotationsCancel(http.Controller):
#     @http.route('/itl_quotations_cancel/itl_quotations_cancel/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/itl_quotations_cancel/itl_quotations_cancel/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('itl_quotations_cancel.listing', {
#             'root': '/itl_quotations_cancel/itl_quotations_cancel',
#             'objects': http.request.env['itl_quotations_cancel.itl_quotations_cancel'].search([]),
#         })

#     @http.route('/itl_quotations_cancel/itl_quotations_cancel/objects/<model("itl_quotations_cancel.itl_quotations_cancel"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('itl_quotations_cancel.object', {
#             'object': obj
#         })