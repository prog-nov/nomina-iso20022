# -*- coding: utf-8 -*-

{
    'name': 'Nomina Electrónica para México CFDI v3.3 EE',
    'summary': 'Agrega funcionalidades para timbrar la nómina electrónica en México para la versión EE.',
    'description': '''
    Nomina CFDI Module
    ''',
    'author': 'IT Admin',
    'version': '13.0.1.0.0',
    'category': 'Employees',
    'depends': [
        'base_import_module', 'hr', 'hr_payroll', 'l10n_mx_edi'
    ],
    'data': [
        'views/hr_employee_view.xml',
        'data/nomina12.xml',
        'data/sequence_data.xml',
        'data/cron.xml',
        'views/hr_contract_view.xml',
        'views/hr_salary_view.xml',
        'views/hr_payroll_payslip_view.xml',
        'views/tablas_cfdi_view.xml',
        'views/res_company_view.xml',
        'report/report_payslip.xml',
        'views/res_bank_view.xml',
        'data/mail_template_data.xml',
        'security/ir.model.access.csv',
        'data/res.bank.csv',
        'views/menu.xml',
        #'views/horas_extras_view.xml',
        #'wizard/wizard_liquidacion_view.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
