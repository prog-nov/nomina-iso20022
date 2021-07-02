# -*- coding: utf-8 -*-
{
    'name': "Prodigia Facturación",

    'summary': """
       Módulo de facturación para enviar facturas al servicio de Prodigia.""",
    'description': """
        Éste módulo agrega a Prodigia como opción para emitir facturas desde el módulo de facturación de odoo-enterprise. para versión 12
    """,
    'author': "Prodigia",
    'website': "https://www.prodigia.mx",
    'support': 'soporte@prodigia.com.mx',
    'category': 'Invoicing',
    'version': '1.0.12',
    'maintainer': "Prodigia Team",
    'license': 'OPL-1',
    # dependencias
    'depends': [
        'account',
        'account_cancel',
        'base_vat',
        'base_address_extended',
        'document',
        'base_address_city',
        'l10n_mx_edi',
        'l10n_mx'],
    # always loaded
    'data': [
        'views/res_config_settings_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [

    ],
    'installable': True,
    'auto_install': False,
}
