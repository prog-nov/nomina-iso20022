# -*- coding: utf-8 -*-
{
    'name': "Customer Credit Management",
    'summary': """
         Credit limits for each customer""",
    'description': """
        - Define a credit limit on the partner
        - On the SaleOrder, if the sale order amount + overdue invoices
        exceeds the limit, the Order will need approval from the Sales Manager
    """,
    'author': "Aktiv Software",
    'website': "www.aktivsoftware.com",
    'category': 'Sales',
    'version': '12.0.1.0.0',
    'depends': ['sale_management'],
    'data': [
        'wizards/credit_limit_wizard.xml',
        'views/sale_views.xml',
        'views/partner_view.xml',
    ],
    'images': [
        'static/description/banner.jpg',
    ],
    'installable': True,
    'auto_install': False,
}
