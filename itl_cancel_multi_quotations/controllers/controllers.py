# -*- coding: utf-8 -*-
from odoo import http

# class ItlCancelMultiQuotations(http.Controller):
#     @http.route('/itl_cancel_multi_quotations/itl_cancel_multi_quotations/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/itl_cancel_multi_quotations/itl_cancel_multi_quotations/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('itl_cancel_multi_quotations.listing', {
#             'root': '/itl_cancel_multi_quotations/itl_cancel_multi_quotations',
#             'objects': http.request.env['itl_cancel_multi_quotations.itl_cancel_multi_quotations'].search([]),
#         })

#     @http.route('/itl_cancel_multi_quotations/itl_cancel_multi_quotations/objects/<model("itl_cancel_multi_quotations.itl_cancel_multi_quotations"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('itl_cancel_multi_quotations.object', {
#             'object': obj
#         })