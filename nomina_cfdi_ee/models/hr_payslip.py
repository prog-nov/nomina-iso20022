# -*- coding: utf-8 -*-

import base64
import json
import requests
from lxml import etree
from io import BytesIO
from itertools import groupby
#import time
import re
from datetime import datetime
from datetime import timedelta
from datetime import time as datetime_time
from dateutil import relativedelta
from pytz import timezone
from lxml.objectify import fromstring
from odoo.tools.xml_utils import _check_with_xsd
from odoo.tools.float_utils import float_repr

from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError, ValidationError
from reportlab.graphics.barcode import createBarcodeDrawing #, getCodes
from reportlab.lib.units import mm
import logging
_logger = logging.getLogger(__name__)
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF, DEFAULT_SERVER_DATETIME_FORMAT as DTF, DEFAULT_SERVER_TIME_FORMAT

from odoo.addons.l10n_mx_edi.tools.run_after_commit import run_after_commit

from suds.client import Client

CFDI_TEMPLATE_NOMINA12 = 'nomina_cfdi_ee.nomina12'
CFDI_XSLT_CADENA_TFD = 'l10n_mx_edi/data/xslt/3.3/cadenaoriginal_TFD_1_1.xslt'
CFDI_XSLT_CADENA = 'l10n_mx_edi/data/%s/cadenaoriginal.xslt'
CFDI_SAT_QR_STATE = {
    'No Encontrado': 'not_found',
    'Cancelado': 'cancelled',
    'Vigente': 'valid',
}

def create_list_html(array):
    '''Convert an array of string to a html list.
    :param array: A list of strings
    :return: an empty string if not array, an html list otherwise.
    '''
    if not array:
        return ''
    msg = ''
    for item in array:
        msg += '<li>' + item + '</li>'
    return '<ul>' + msg + '</ul>'

class HrPayslipWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'
    work_entry_type_id = fields.Text(string='work_entry_type_id')
    
    @api.onchange('number_of_days')
    def _onchange_number_of_days(self):
        if self.work_entry_type_id and self.work_entry_type_id.code =='WORK100' and self.payslip_id.contract_id:
            self.number_of_hours = self.number_of_days * 8
            self.amount = self.number_of_days * self.payslip_id.contract_id.sueldo_diario
            
    

class HrSalaryRule(models.Model):
    #_inherit = ['hr.salary.rule','mail.thread']
    _inherit = 'hr.salary.rule'
    tipo_percepcion = fields.Selection(
        selection=[('001', 'Sueldos, Salarios  Rayas y Jornales'), 
                   ('002', 'Gratificación Anual (Aguinaldo)'), 
                   ('003', 'Participación de los Trabajadores en las Utilidades PTU'),
                   ('004', 'Reembolso de Gastos Médicos Dentales y Hospitalarios'), 
                   ('005', 'Fondo de ahorro'),
                   ('006', 'Caja de ahorro'),
                   ('009', 'Contribuciones a Cargo del Trabajador Pagadas por el Patrón'), 
                   ('010', 'Premios por puntualidad'),
                   ('011', 'Prima de Seguro de vida'), 
                   ('012', 'Seguro de Gastos Médicos Mayores'), 
                   ('013', 'Cuotas Sindicales Pagadas por el Patrón'), 
                   ('014', 'Subsidios por incapacidad'),
                   ('015', 'Becas para trabajadores y/o hijos'), 
                   ('019', 'Horas extra'),
                   ('020', 'Prima dominical'), 
                   ('021', 'Prima vacacional'),
                   ('022', 'Prima por antigüedad'),
                   ('023', 'Pagos por separación'),
                   ('024', 'Seguro de retiro'),
                   ('025', 'Indemnizaciones'), 
                   ('026', 'Reembolso por funeral'), 
                   ('027', 'Cuotas de seguridad social pagadas por el patrón'), 
                   ('028', 'Comisiones'),
                   ('029', 'Vales de despensa'),
                   ('030', 'Vales de restaurante'), 
                   ('031', 'Vales de gasolina'),
                   ('032', 'Vales de ropa'), 
                   ('033', 'Ayuda para renta'), 
                   ('034', 'Ayuda para artículos escolares'), 
                   ('035', 'Ayuda para anteojos'),
                   ('036', 'Ayuda para transporte'), 
                   ('037', 'Ayuda para gastos de funeral'),
                   ('038', 'Otros ingresos por salarios'), 
                   ('039', 'Jubilaciones, pensiones o haberes de retiro'),
                   ('044', 'Jubilaciones, pensiones o haberes de retiro en parcialidades'),
                   ('045', 'Ingresos en acciones o títulos valor que representan bienes'),
                   ('046', 'Ingresos asimilados a salarios'),
                   ('047', 'Alimentación'), 
                   ('048', 'Habitación'), 
                   ('049', 'Premios por asistencia'), 
                   ('050', 'Viáticos'),
                   ('051', 'Pagos por gratificaciones, primas, compensaciones, recompensas u otros a extrabajadores derivados de jubilación en parcialidades'),
                   ('052', 'Pagos que se realicen a extrabajadores que obtengan una jubilación en parcialidades derivados de la ejecución de resoluciones judicial o de un laudo'),
                   ('053', 'Pagos que se realicen a extrabajadores que obtengan una jubilación en una sola exhibición derivados de la ejecución de resoluciones judicial o de un laudo'),],
        string=_('Tipo de percepción'),
    )
    tipo_deduccion = fields.Selection(
        selection=[('001', 'Seguridad social'), 
                   ('002', 'ISR'), 
                   ('003', 'Aportaciones a retiro, cesantía en edad avanzada y vejez.'),
                   ('004', 'Otros'), 
                   ('005', 'Aportaciones a Fondo de vivienda'),
                   ('006', 'Descuento por incapacidad'),
                   ('007', 'Pensión alimenticia'),
                   ('008', 'Renta'),
                   ('009', 'Préstamos provenientes del Fondo Nacional de la Vivienda para los Trabajadores'), 
                   ('010', 'Pago por crédito de vivienda'),
                   ('011', 'Pago de abonos INFONACOT'), 
                   ('012', 'Anticipo de salarios'), 
                   ('013', 'Pagos hechos con exceso al trabajador'), 
                   ('014', 'Errores'),
                   ('015', 'Pérdidas'), 
                   ('016', 'Averías'), 
                   ('017', 'Adquisición de artículos producidos por la empresa o establecimiento'),
                   ('018', 'Cuotas para la constitución y fomento de sociedades cooperativas y de cajas de ahorro'), 				   
                   ('019', 'Cuotas sindicales'),
                   ('020', 'Ausencia (Ausentismo)'), 
                   ('021', 'Cuotas obrero patronales'),
                   ('022', 'Impuestos Locales'),
                   ('023', 'Aportaciones voluntarias'),
                   ('080', 'Ajuste en Viáticos gravados'),
                   ('081', 'Ajuste en Viáticos (entregados al trabajador)'),
                   ('101', 'ISR Retenido de ejercicio anterior'),
                   ('102', 'Ajuste a pagos por gratificaciones, primas, compensaciones, recompensas u otros a extrabajadores derivados de jubilación en parcialidades, gravados'),
                   ('103', 'Ajuste a pagos que se realicen a extrabajadores que obtengan una jubilación en parcialidades derivados de la ejecución de una resolución judicial o de un laudo gravados'),
                   ('104', 'Ajuste a pagos que se realicen a extrabajadores que obtengan una jubilación en parcialidades derivados de la ejecución de una resolución judicial o de un laudo exentos'),
                   ('105', 'Ajuste a pagos que se realicen a extrabajadores que obtengan una jubilación en una sola exhibición derivados de la ejecución de una resolución judicial o de un laudo gravados'),
                   ('106', 'Ajuste a pagos que se realicen a extrabajadores que obtengan una jubilación en una sola exhibición derivados de la ejecución de una resolución judicial o de un laudo exentos'),],
        string=_('Tipo de deducción'),
    )

    tipo_otro_pago = fields.Selection(
        selection=[('001', 'Reintegro de ISR pagado en exceso'), 
                   ('002', 'Subsidio para el empleo'), 
                   ('003', 'Viáticos'),
                   ('004', 'Aplicación de saldo a favor por compensación anual'), 
                   ('005', 'Reintegro de ISR retenido en exceso de ejercicio anterior'),
                   ('999', 'Pagos distintos a los listados y que no deben considerarse como ingreso por sueldos, salarios o ingresos asimilados'),],
        string=_('Otros Pagos'),)
    category_code = fields.Char("Category Code",related="category_id.code",store=True)

    forma_pago = fields.Selection(
        selection=[('001', 'Efectivo'), 
                   ('002', 'Especie'),],
        string=_('Forma de pago'),default='001')
    
    #fong agregado inicio--
    #itl_tipo_tabla_isr = fields.Selection(
     #   selection=[('001', 'Quincenal'), 
      #             ('002', 'Mensual'),],
       # string=_('Tipo de tabla ISR'),default='001')
    #fong agregado fin --
    
    
class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'
    #fong agregado inicio--
    itl_tipo_tabla_isr = fields.Selection(
       selection=[('001', 'Quincenal'), 
                   ('002', 'Mensual'),],
        string=_('Tipo de tabla ISR'),default='001')
    #fong agregado fin --    

class HrPayslip(models.Model):
    _name = "hr.payslip"
    _inherit = ['hr.payslip','mail.thread']

    currency_id = fields.Many2one(related='contract_id.currency_id')

    tipo_nomina = fields.Selection(
        selection=[('O', 'Nómina ordinaria'), 
                   ('E', 'Nómina extraordinaria'),],
        string=_('Tipo de nómina'), required=True, default='O'
    )

    estado_factura = fields.Selection(
        selection=[('factura_no_generada', 'Factura no generada'), ('factura_correcta', 'Factura correcta'), 
                   ('problemas_factura', 'Problemas con la factura'), ('factura_cancelada', 'Factura cancelada')],
        string=_('Estado de factura'),
        default='factura_no_generada',
        readonly=True,
        copy=False
    )	
    #imss_dias = fields.Float('Cotizar en el IMSS',default='16') #, readonly=True) 
    #imss_mes = fields.Float('Dias a cotizar en el mes',default='30.4') #, readonly=True)
    #xml_nomina_link = fields.Char(string=_('XML link'), readonly=True)
    nomina_cfdi = fields.Boolean('Nomina CFDI')
    #qrcode_image = fields.Binary("QRCode")
    #qr_value = fields.Char(string=_('QR Code Value'))
    #numero_cetificado = fields.Char(string=_('Numero de cetificado'))
    #cetificaso_sat = fields.Char(string=_('Cetificao SAT'))
    #folio_fiscal = fields.Char(string=_('Folio Fiscal'), readonly=True)
    #fecha_certificacion = fields.Char(string=_('Fecha y Hora Certificación'))
    #cadena_origenal = fields.Char(string=_('Cadena Origenal del Complemento digital de SAT'))
    #selo_digital_cdfi = fields.Char(string=_('Selo Digital del CDFI'))
    #selo_sat = fields.Char(string=_('Selo del SAT'))
    #moneda = fields.Char(string=_('Moneda'))
    #tipocambio = fields.Char(string=_('TipoCambio'))
    #folio = fields.Char(string=_('Folio'))
    version = fields.Char(string=_('Version'))
    #serie_emisor = fields.Char(string=_('Serie'))
    invoice_datetime = fields.Char(string=_('Fecha factura'))
    rfc_emisor = fields.Char(string=_('RFC'))
    #total_nomina = fields.Float('Total a pagar')
    #subtotal = fields.Float('Subtotal')
    #descuento = fields.Float('Descuento')
    #deducciones_lines = []
    #number_folio = fields.Char(string=_('Folio'), compute='_get_number_folio')
    #fecha_factura = fields.Datetime(string=_('Fecha Factura'), readonly=True)
    #subsidio_periodo = fields.Float('subsidio_periodo')
    #isr_periodo = fields.Float('isr_periodo')
    #retencion_subsidio_pagado = fields.Float('retencion_subsidio_pagado')
    #importe_imss = fields.Float('importe_imss')
    #importe_isr = fields.Float('importe_isr')
    #periodicidad = fields.Float('periodicidad')
    #concepto_periodico = fields.Boolean('Conceptos periodicos', default = True)
    #septimo_dia = fields.Boolean(string='Proporcional septimo día')
    #incapa_sept_dia = fields.Boolean(string='Incluir incapacidades 7mo día')

    #desglose imss
    prestaciones  = fields.Float('prestaciones')
    invalli_y_vida  = fields.Float('invalli_y_vida')
    cesantia_y_vejez = fields.Float('cesantia_y_vejez')
    pensio_y_benefi  = fields.Float('pensio_y_benefi')

    #forma_pago = fields.Selection(
    #    selection=[('99', '99 - Por definir'),],
    #    string=_('Forma de pago'),default='99',
    #)	
    tipo_comprobante = fields.Selection(
        selection=[('N', 'Nómina'),],
        string=_('Tipo de comprobante'),default='N',
    )	
    #tipo_relacion = fields.Selection(
    #    selection=[('04', 'Sustitución de los CFDI previos'),],
    #    string=_('Tipo relación'),
    #)
    uuid_relacionado = fields.Char(string=_('CFDI Relacionado'))
    #methodo_pago = fields.Selection(
    #    selection=[('PUE', _('Pago en una sola exhibición')),],
    #    string=_('Método de pago'), default='PUE',
    #)	
    #uso_cfdi = fields.Selection(
    #    selection=[('P01', _('Por definir')),],
    #    string=_('Uso CFDI (cliente)'),default='P01',
    #)
    fecha_pago = fields.Date(string=_('Fecha de pago'))
    #dias_pagar = fields.Float('Días promedio al mes', default='30.4')
    #no_nomina = fields.Selection(
    #    selection=[('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), ('6', '6')], string=_('Nómina del mes'))
    #acum_per_totales = fields.Float('Percepciones totales', compute='_get_percepciones_totales')
    #acum_per_grav  = fields.Float('Percepciones gravadas', compute='_get_percepciones_gravadas')
    #acum_isr  = fields.Float('ISR', compute='_get_isr')
    #acum_isr_antes_subem  = fields.Float('ISR antes de SUBEM', compute='_get_isr_antes_subem')
    #acum_subsidio_aplicado  = fields.Float('Subsidio aplicado', compute='_get_subsidio_aplicado')
    #acum_fondo_ahorro = fields.Float('Fondo ahorro', compute='_get_fondo_ahorro')
    dias_periodo = fields.Float(string=_('Dias en el periodo'), compute='_get_dias_periodo')
    #num_faltas = fields.Integer(string="Número de faltas")
    #isr_devolver = fields.Boolean(string='Devolver ISR')
    #isr_ajustar = fields.Boolean(string='Ajustar ISR en cada nómina')
    #acum_sueldo = fields.Float('Sueldo', compute='_get_sueldo')

    mes = fields.Selection(
        selection=[('01', 'Enero'), 
                   ('02', 'Febrero'), 
                   ('03', 'Marzo'),
                   ('04', 'Abril'), 
                   ('05', 'Mayo'),
                   ('06', 'Junio'),
                   ('07', 'Julio'),
                   ('08', 'Agosto'),
                   ('09', 'Septiembre'),
                   ('10', 'Octubre'),
                   ('11', 'Noviembre'),
                   ('12', 'Diciembre'),
                   ],
        string=_('Mes de la nómina'))

    allowance_total_amount = fields.Float(compute="_get_total_amounts", string="Suma de percepciones", readonly=True)
    deduction_total_amount = fields.Float(compute="_get_total_amounts", string="Suma de deducciones", readonly=True)
    neto_total_amount = fields.Float(compute="_get_total_amounts", string="Neto a pagar", readonly=True)
    home_currency_amount_total = fields.Float(string='Total Amount in company currency', compute="_compute", store=True)
    #############################################################
    ############ Fields for sign payroll ########################
    #############################################################
    l10n_mx_edi_pac_status = fields.Selection(
        selection=[
            ('retry', 'Retry'),
            ('to_sign', 'To sign'),
            ('signed', 'Signed'),
            ('to_cancel', 'To cancel'),
            ('cancelled', 'Cancelled')
        ],
        string='PAC status',
        help='Refers to the status of the invoice inside the PAC.',
        readonly=True,
        copy=False)
    l10n_mx_edi_sat_status = fields.Selection(
        selection=[
            ('none', 'State not defined'),
            ('undefined', 'Not Synced Yet'),
            ('not_found', 'Not Found'),
            ('cancelled', 'Cancelled'),
            ('valid', 'Valid'),
        ],
        string='SAT status',
        help='Refers to the status of the invoice inside the SAT system.',
        readonly=True,
        copy=False,
        required=True,
        tracking=True,
        default='undefined')
    l10n_mx_edi_cfdi_name = fields.Char(string='CFDI name', copy=False, readonly=True,
        help='The attachment name of the CFDI.')
    l10n_mx_edi_partner_bank_id = fields.Many2one('res.partner.bank',
        string='Partner bank',
        readonly=True,
        states={'draft': [('readonly', False)]},
        domain="[('partner_id', '=', partner_id)]",
        help='The bank account the client will pay from. Leave empty if '
        'unkown and the XML will show "Unidentified".')
    l10n_mx_edi_payment_method_id = fields.Many2one('l10n_mx_edi.payment.method',
        string='Payment Way',
        readonly=True,
        states={'draft': [('readonly', False)]},
        help='Indicates the way the invoice was/will be paid, where the '
        'options could be: Cash, Nominal Check, Credit Card, etc. Leave empty '
        'if unkown and the XML will show "Unidentified".',
        default=lambda self: self.env.ref('l10n_mx_edi.payment_method_otros',
                                          raise_if_not_found=False))
    l10n_mx_edi_cfdi_uuid = fields.Char(string='Fiscal Folio', copy=False, readonly=True,
        help='Folio in electronic invoice, is returned by SAT when send to stamp.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_cfdi = fields.Binary(string='Cfdi content', copy=False, readonly=True,
        help='The cfdi xml content encoded in base64.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_cfdi_supplier_rfc = fields.Char(string='Supplier RFC', copy=False, readonly=True,
        help='The supplier tax identification number.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_cfdi_customer_rfc = fields.Char(string='Customer RFC', copy=False, readonly=True,
        help='The customer tax identification number.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_cfdi_amount = fields.Float(string='Total Amount', copy=False, readonly=True,
        help='The total amount reported on the cfdi.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_time_invoice = fields.Char(
        string='Time invoice', readonly=True, copy=False,
        states={'draft': [('readonly', False)]},
        help="Keep empty to use the current México central time")
    l10n_mx_edi_usage = fields.Selection([
        ('G01', 'Acquisition of merchandise'),
        ('G02', 'Returns, discounts or bonuses'),
        ('G03', 'General expenses'),
        ('I01', 'Constructions'),
        ('I02', 'Office furniture and equipment investment'),
        ('I03', 'Transportation equipment'),
        ('I04', 'Computer equipment and accessories'),
        ('I05', 'Dices, dies, molds, matrices and tooling'),
        ('I06', 'Telephone communications'),
        ('I07', 'Satellite communications'),
        ('I08', 'Other machinery and equipment'),
        ('D01', 'Medical, dental and hospital expenses.'),
        ('D02', 'Medical expenses for disability'),
        ('D03', 'Funeral expenses'),
        ('D04', 'Donations'),
        ('D05', 'Real interest effectively paid for mortgage loans (room house)'),
        ('D06', 'Voluntary contributions to SAR'),
        ('D07', 'Medical insurance premiums'),
        ('D08', 'Mandatory School Transportation Expenses'),
        ('D09', 'Deposits in savings accounts, premiums based on pension plans.'),
        ('D10', 'Payments for educational services (Colegiatura)'),
        ('P01', 'To define'),
    ], 'Usage', default='P01',
        help='Used in CFDI 3.3 to express the key to the usage that will '
        'gives the receiver to this invoice. This value is defined by the '
        'customer. \nNote: It is not cause for cancellation if the key set is '
        'not the usage that will give the receiver of the document.')
    l10n_mx_edi_origin = fields.Char(
        string='CFDI Origin', copy=False,
        help='In some cases like payments, credit notes, debit notes, '
        'invoices re-signed or invoices that are redone due to payment in '
        'advance will need this field filled, the format is: \nOrigin Type|'
        'UUID1, UUID2, ...., UUIDn.\nWhere the origin type could be:\n'
        u'- 01: Nota de crédito\n'
        u'- 02: Nota de débito de los documentos relacionados\n'
        u'- 03: Devolución de mercancía sobre facturas o traslados previos\n'
        u'- 04: Sustitución de los CFDI previos\n'
        '- 05: Traslados de mercancias facturados previamente\n'
        '- 06: Factura generada por los traslados previos\n'
        u'- 07: CFDI por aplicación de anticipo')
    l10n_mx_edi_cer_source = fields.Char(
        'Certificate Source',
        help='Used in CFDI like attribute derived from the exception of '
        'certificates of Origin of the Free Trade Agreements that Mexico '
        'has celebrated with several countries. If it has a value, it will '
        'indicate that it serves as certificate of origin and this value will '
        'be set in the CFDI node "NumCertificadoOrigen".')
    
    # Inherit
    def _get_worked_day_lines(self):
        _logger.info("---> _get_worked_day_lines")
        result = super(HrPayslip, self)._get_worked_day_lines()
        
        res = []
        self.ensure_one()
        contract = self.contract_id
        _logger.info("---> contract.periodicidad_pago antes  del  IF(): " + str(contract.periodicidad_pago))
        if contract.periodicidad_pago == '04':
            _logger.info("entro IF")
            work_entry_type = self.env['hr.work.entry.type'].browse(1)
            sueldo_diario = self.contract_id.sueldo_diario
            amount = sueldo_diario * 15
            attendance_line = {
                    'sequence': work_entry_type.sequence,
                    'work_entry_type_id': 1,
                    'number_of_days': 15,
                    'number_of_hours': 180,
                    'amount': amount,
                }
            res.append(attendance_line)
            
            return res
        _logger.info("result (DESPUES DE IF): " + str(result))
        return result
            
    '''
    def _get_total_amounts(self):
        self.allowance_total_amount = sum([item.total for item in self.line_ids if 'ALW' in item.category_id.code])
        self.deduction_total_amount = sum([item.total for item in self.line_ids if 'DED' in item.category_id.code])
        self.neto_total_amount = self.allowance_total_amount - self.deduction_total_amount
        '''

    def _get_total_amounts(self):
        self.allowance_total_amount = sum([item.total for item in self.line_ids if 'ALW' in item.category_id.code])
        self.deduction_total_amount = sum([item.total for item in self.line_ids if 'DED' in item.category_id.code])
        self.neto_total_amount = self.allowance_total_amount - self.deduction_total_amount
    

    @api.depends('l10n_mx_edi_cfdi_name', 'l10n_mx_edi_pac_status')
    def _compute_cfdi_values(self):
        '''Fill the invoice fields from the cfdi values.
        '''
        for nom in self:
            attachment_id = nom.l10n_mx_edi_retrieve_last_attachment()
            # At this moment, the attachment contains the file size in its 'datas' field because
            # to save some memory, the attachment will store its data on the physical disk.
            # To avoid this problem, we read the 'datas' directly on the disk.
            datas = attachment_id._file_read(attachment_id.store_fname) if attachment_id else None
            nom.l10n_mx_edi_cfdi_uuid = None
            if not datas:
                if attachment_id:
                    _logger.error('The CFDI attachment cannot be found')
                nom.l10n_mx_edi_cfdi = None
                nom.l10n_mx_edi_cfdi_supplier_rfc = None
                nom.l10n_mx_edi_cfdi_customer_rfc = None
                nom.l10n_mx_edi_cfdi_amount = None
                continue
            nom.l10n_mx_edi_cfdi = datas
            cfdi = base64.decodestring(datas).replace(
                b'xmlns:schemaLocation', b'xsi:schemaLocation')
            tree = nom.l10n_mx_edi_get_xml_etree(cfdi)
            # if already signed, extract uuid
            tfd_node = nom.l10n_mx_edi_get_tfd_etree(tree)
            if tfd_node is not None:
                nom.l10n_mx_edi_cfdi_uuid = tfd_node.get('UUID')
            nom.l10n_mx_edi_cfdi_amount = tree.get('Total', tree.get('total'))
            nom.l10n_mx_edi_cfdi_supplier_rfc = tree.Emisor.get(
                'Rfc', tree.Emisor.get('rfc'))
            nom.l10n_mx_edi_cfdi_customer_rfc = tree.Receptor.get(
                'Rfc', tree.Receptor.get('rfc'))
            certificate = tree.get('noCertificado', tree.get('NoCertificado'))
    
    @api.model
    def l10n_mx_edi_get_tfd_etree(self, cfdi):
        '''Get the TimbreFiscalDigital node from the cfdi.

        :param cfdi: The cfdi as etree
        :return: the TimbreFiscalDigital node
        '''
        if not hasattr(cfdi, 'Complemento'):
            return None
        attribute = 'tfd:TimbreFiscalDigital[1]'
        namespace = {'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
        node = cfdi.Complemento.xpath(attribute, namespaces=namespace)
        return node[0] if node else None
    
    @api.model
    def l10n_mx_edi_retrieve_last_attachment(self):
        attachment_ids = self.l10n_mx_edi_retrieve_attachments()
        return attachment_ids and attachment_ids[0] or None
    
    @api.model
    def l10n_mx_edi_retrieve_attachments(self):
        '''Retrieve all the cfdi attachments generated for this invoice.

        :return: An ir.attachment recordset
        '''
        self.ensure_one()
        if not self.l10n_mx_edi_cfdi_name:
            return []
        domain = [
            ('res_id', '=', self.id),
            ('res_model', '=', self._name),
            ('name', '=', self.l10n_mx_edi_cfdi_name)]
        return self.env['ir.attachment'].search(domain)
    
    
    def set_fecha_pago(self, payroll_name):
            values = {
                'payslip_run_id': payroll_name
                }
            self.update(values)
	
    @api.onchange('date_to')
    def _get_fecha_pago(self):
        if self.date_to:
            values = {
                'fecha_pago': self.date_to
                }
            self.update(values)

    @api.onchange('date_to')
    def _get_dias_periodo(self):
        self.dias_periodo = 0
        if self.date_to and self.date_from and self.contract_id.periodicidad_pago == '04':
            line = self.contract_id.env['tablas.periodo.mensual'].search([('form_id','=',self.contract_id.tablas_cfdi_id.id),('dia_fin','>=',self.date_to),
                                                                    ('dia_inicio','<=',self.date_to)],limit=1)
            if line:
                self.dias_periodo = line.no_dias/2
            else:
                raise UserError(_('No están configurados correctamente los periodos mensuales en las tablas CFDI'))

    @api.model
    def create(self, vals):
        if not vals.get('fecha_pago') and vals.get('date_to'):
            vals.update({'fecha_pago': vals.get('date_to')})
            
        res = super(HrPayslip, self).create(vals)
        return res
    
    #@api.depends('number')
    #def _get_number_folio(self):
    #    if self.number:
    #        self.number_folio = self.number.replace('SLIP','').replace('/','')

    #@api.returns('self', lambda value: value.id)
    #def copy(self, default=None):
    #    default = dict(default or {})
    #    if self.estado_factura == 'factura_correcta':
    #        default['estado_factura'] = 'factura_no_generada'
    #        default['folio_fiscal'] = ''
    #        default['fecha_factura'] = None
    #        default['nomina_cfdi'] = False
    #    return super(HrPayslip, self).copy(default=default)

    @api.onchange('mes')
    def _get_percepciones_gravadas(self):
        total = 0
        if self.employee_id and self.mes and self.contract_id.tablas_cfdi_id:
            mes_actual = self.env['tablas.periodo.mensual'].search([('mes', '=', self.mes)])[0]
            date_start = mes_actual.dia_inicio # self.date_from
            date_end = mes_actual.dia_fin #self.date_to
            domain=[('state','=', 'done')]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            rules = self.env['hr.salary.rule'].search([('code', '=', 'TPERG')])
            payslips = self.env['hr.payslip'].search(domain)
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        self.acum_per_grav = total

    @api.onchange('mes')
    def _get_isr(self):
        total = 0
        if self.employee_id and self.mes and self.contract_id.tablas_cfdi_id:
            mes_actual = self.env['tablas.periodo.mensual'].search([('mes', '=', self.mes)])[0]
            date_start = mes_actual.dia_inicio # self.date_from
            date_end = mes_actual.dia_fin #self.date_to
            domain=[('state','=', 'done')]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            rules = self.env['hr.salary.rule'].search([('code', '=', 'ISR2'),('category_id.code','=','DED')])
            #_logger.info("rules: " + str(rules))
            payslips = self.env['hr.payslip'].search(domain)
            #_logger.info("payslips: " + str(domain))
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        self.acum_isr = total

    @api.onchange('mes')
    def _get_isr_antes_subem(self):
        total = 0
        if self.employee_id and self.mes and self.contract_id.tablas_cfdi_id:
            mes_actual = self.env['tablas.periodo.mensual'].search([('mes', '=', self.mes)])[0]
            date_start = mes_actual.dia_inicio # self.date_from
            date_end = mes_actual.dia_fin #self.date_to
            domain=[('state','=', 'done')]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            rules = self.env['hr.salary.rule'].search([('code', '=', 'ISR')])
            payslips = self.env['hr.payslip'].search(domain)
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        self.acum_isr_antes_subem = total

    @api.onchange('mes')
    def _get_subsidio_aplicado(self):
        total = 0
        if self.employee_id and self.mes and self.contract_id.tablas_cfdi_id:
            mes_actual = self.env['tablas.periodo.mensual'].search([('mes', '=', self.mes)])[0]
            date_start = mes_actual.dia_inicio # self.date_from
            date_end = mes_actual.dia_fin #self.date_to
            domain=[('state','=', 'done')]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            rules = self.env['hr.salary.rule'].search([('code', '=', 'SUB')])
            payslips = self.env['hr.payslip'].search(domain)
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        self.acum_subsidio_aplicado = total

    @api.onchange('mes')
    def _get_fondo_ahorro(self):
        total = 0
        if self.employee_id and self.mes and self.contract_id.tablas_cfdi_id:
            mes_actual = self.env['tablas.periodo.mensual'].search([('mes', '=', self.mes)])[0]
            date_start = mes_actual.dia_inicio # self.date_from
            date_end = mes_actual.dia_fin #self.date_to
            domain=[('state','=', 'done')]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            rules = self.env['hr.salary.rule'].search([('code', '=', 'D067'),('category_id.code','=','DED')])
            payslips = self.env['hr.payslip'].search(domain)
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        self.acum_fondo_ahorro = total

    @api.onchange('mes')
    def _get_percepciones_totales(self):
        total = 0
        if self.employee_id and self.mes and self.contract_id.tablas_cfdi_id:
            mes_actual = self.env['tablas.periodo.mensual'].search([('mes', '=', self.mes)])[0]
            date_start = mes_actual.dia_inicio
            date_end = mes_actual.dia_fin
            domain=[('state','=', 'done')]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            rules = self.env['hr.salary.rule'].search([('code', '=', 'TPER')])
            payslips = self.env['hr.payslip'].search(domain)
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        self.acum_per_totales = total

    @api.onchange('mes')
    def _get_sueldo(self):
        total = 0
        if self.employee_id and self.mes and self.contract_id.tablas_cfdi_id:
            mes_actual = self.env['tablas.periodo.mensual'].search([('mes', '=', self.mes)])[0]
            date_start = mes_actual.dia_inicio # self.date_from
            date_end = mes_actual.dia_fin #self.date_to
            domain=[('state','=', 'done')]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            rules = self.env['hr.salary.rule'].search([('code', '=', 'P001')])
            payslips = self.env['hr.payslip'].search(domain)
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        self.acum_sueldo = total

    @api.model
    def fondo_ahorro(self):	
        deducciones_ahorro = self.env['hr.payslip.line'].search([('category_id.code','=','DED'),('slip_id','=',self.id)])
        if deducciones_ahorro:
            _logger.info('fondo ahorro deudccion...')
            for line in deducciones_ahorro:
                if line.salary_rule_id.tipo_deduccion == '017':
                    self.employee_id.fondo_ahorro += line.total

        percepciones_ahorro = self.env['hr.payslip.line'].search([('category_id.code','=','ALW2'),('slip_id','=',self.id)])
        if percepciones_ahorro:
            _logger.info('fondo ahorro percepcion...')
            for line in percepciones_ahorro:
                if line.salary_rule_id.tipo_percepcion == '005':
                    self.employee_id.fondo_ahorro -= line.total

    @api.model
    def devolucion_fondo_ahorro(self):	
        deducciones_ahorro = self.env['hr.payslip.line'].search([('category_id.code','=','DED'),('slip_id','=',self.id)])
        if deducciones_ahorro:
            _logger.info('Devolucion fondo ahorro deduccion...')
            for line in deducciones_ahorro:
                if line.salary_rule_id.tipo_deduccion == '017':
                    self.employee_id.fondo_ahorro -= line.total

        percepciones_ahorro = self.env['hr.payslip.line'].search([('category_id.code','=','ALW2'),('slip_id','=',self.id)])
        if percepciones_ahorro:
            _logger.info('Devolucion fondo ahorro percepcion...')
            for line in percepciones_ahorro:
                if line.salary_rule_id.tipo_percepcion == '005':
                    self.employee_id.fondo_ahorro += line.total

    def action_payslip_done(self):
        res = super(HrPayslip, self).action_payslip_done()
        for rec in self:
            rec.fondo_ahorro()
        return res

    def refund_sheet(self):
        res = super(HrPayslip, self).refund_sheet()
        for rec in self:
            rec.devolucion_fondo_ahorro()
        return res
    
    
    
    def _l10n_mx_edi_post_cancel_process(self, cancelled, code=None, msg=None):
        '''Post process the results of the cancel service.

        :param cancelled: is the cancel has been done with success
        :param code: an eventual error code
        :param msg: an eventual error msg
        '''

        self.ensure_one()
        if cancelled:
            body_msg = _('The cancel service has been called with success')
            self.l10n_mx_edi_pac_status = 'cancelled'
        else:
            body_msg = _('The cancel service requested failed')
        post_msg = []
        if code:
            post_msg.extend([_('Code: %s') % code])
        if msg:
            post_msg.extend([_('Message: %s') % msg])
        self.message_post(
            body=body_msg + create_list_html(post_msg),
            subtype='account.mt_invoice_validated')

    @api.model
    def calculo_imss(self):
        #cuota del IMSS parte del Empleado
        salario_cotizado = self.contract_id.sueldo_diario_integrado * self.imss_dias
        uma3 =  self.contract_id.tablas_cfdi_id.uma * 3
        # falta especie excedente

        self.prestaciones = salario_cotizado * self.contract_id.tablas_cfdi_id.enf_mat_prestaciones_e/100
        self.invalli_y_vida = salario_cotizado * self.contract_id.tablas_cfdi_id.inv_vida_e/100
        self.cesantia_y_vejez = salario_cotizado * self.contract_id.tablas_cfdi_id.cesantia_vejez_e/100
        self.pensio_y_benefi = salario_cotizado * self.contract_id.tablas_cfdi_id.enf_mat_gastos_med_e/100

        #seguro_enfermedad_maternidad
        excedente = self.contract_id.sueldo_diario_integrado - uma3
        base_cotizacion = excedente * self.imss_mes
        seg_enf_mat = base_cotizacion * self.contract_id.tablas_cfdi_id.enf_mat_excedente_e/100

        if self.contract_id.sueldo_diario_integrado < uma3:
            self.prestaciones = self.prestaciones + self.pensio_y_benefi
        else:
            self.prestaciones = self.prestaciones + self.pensio_y_benefi + abs(seg_enf_mat)
    """
    @api.model
    def calculo3_imss(self, contract, worked_days, payslip, categories):
        #cuota del IMSS parte del Empleado
        #salario_cotizado = contract.sueldo_diario_integrado * payslip.imss_dias
        uma3 =  contract.tablas_cfdi_id.uma * 3
        uma25 = contract.tablas_cfdi_id.uma * 25
        
        #seguro_enfermedad_maternidad - falta considerar días de incapacidad cuando aplique
        seg_enf_mat = 0
        if contract.sueldo_diario_integrado > uma3:
            excedente = contract.sueldo_diario_integrado - uma3
            base_cotizacion = excedente * payslip.imss_dias
            seg_enf_mat = base_cotizacion * (contract.tablas_cfdi_id.enf_mat_excedente_e/100)
        _logger.info("seg_enf_mat: " + str(seg_enf_mat))

        # falta especie excedente
        # falta considerar días de incapacidad cuando aplique
        prestaciones = contract.sueldo_diario_integrado * payslip.imss_dias * (contract.tablas_cfdi_id.enf_mat_prestaciones_e/100)
        _logger.info("prestaciones: " + str(prestaciones))
        # falta considerar días de incapacidad cuando aplique
        pensio_y_benefi = contract.sueldo_diario_integrado * payslip.imss_dias * contract.tablas_cfdi_id.enf_mat_gastos_med_e/100
        _logger.info("pensio_y_benefi: " + str(pensio_y_benefi))
        
        if contract.sueldo_diario_integrado < uma25:
            invalli_y_vida = contract.sueldo_diario_integrado * (payslip.imss_dias - payslip.num_faltas) * contract.tablas_cfdi_id.inv_vida_e/100
            cesantia_y_vejez = contract.sueldo_diario_integrado * (payslip.imss_dias - payslip.num_faltas) * contract.tablas_cfdi_id.cesantia_vejez_e/100
        else:
            invalli_y_vida = uma25 * (payslip.imss_dias - payslip.num_faltas) * contract.tablas_cfdi_id.inv_vida_e/100
            cesantia_y_vejez = uma25 * (payslip.imss_dias - payslip.num_faltas) * contract.tablas_cfdi_id.cesantia_vejez_e/100
        _logger.info("invalli_y_vida: " + str(invalli_y_vida))
        _logger.info("cesantia_y_vejez: " + str(cesantia_y_vejez))

        #if contract.sueldo_diario_integrado < uma3:
        #    prestaciones = prestaciones + pensio_y_benefi
        #else:
        #    prestaciones = prestaciones + pensio_y_benefi + abs(seg_enf_mat)
        
        total_imss = seg_enf_mat + prestaciones + pensio_y_benefi + invalli_y_vida + cesantia_y_vejez
        
        return total_imss
    """

    @api.model
    def calculo2_imss(self, contract, worked_days, payslip, categories):
        #cuota del IMSS parte del Empleado
        #salario_cotizado = contract.sueldo_base_cotizacion * 15
        _logger.info("#################### Calculo de IMSS ##################")
        uma3 =  round(contract.tablas_cfdi_id.uma * 3, 2)
        _logger.info("uma3: " + str(uma3))
        sbc_menos_3uma = round(contract.sueldo_base_cotizacion - uma3, 2)
        _logger.info("sbc_menos_3uma: " + str(sbc_menos_3uma))
        imss_dias = contract.tablas_cfdi_id.imss_mes / 2
        _logger.info("imss_dias: " + str(imss_dias))
        # Enfermedad y maternidad
        enf_mat_especie = round((contract.tablas_cfdi_id.enf_mat_excedente_e/100) * imss_dias * sbc_menos_3uma, 2)
        _logger.info("Exedente: " + str(enf_mat_especie))
        enf_mat_pensio_y_benefi = round((contract.tablas_cfdi_id.enf_mat_gastos_med_e/100) * imss_dias * contract.sueldo_base_cotizacion, 2)
        _logger.info("Pensionados: " + str(enf_mat_pensio_y_benefi))
        enf_mat_en_dinero = round((contract.tablas_cfdi_id.enf_mat_prestaciones_e/100) * imss_dias * contract.sueldo_base_cotizacion, 2)
        _logger.info("Unica: " + str(enf_mat_en_dinero))
        # Invalidez y vida; Ausentismo/ F. injustificadas - Incapacidades
        inv_vida_esp_y_dinero = round((contract.tablas_cfdi_id.inv_vida_e/100) * imss_dias * contract.sueldo_base_cotizacion, 2)
        _logger.info("Invalidez: " + str(inv_vida_esp_y_dinero))
        # Cesantia y vejez
        ceav = round((contract.tablas_cfdi_id.cesantia_vejez_e/100) * imss_dias * contract.sueldo_base_cotizacion, 2)

        total_imss = enf_mat_especie + enf_mat_pensio_y_benefi + enf_mat_en_dinero + inv_vida_esp_y_dinero + ceav

        
        _logger.info("contract.sueldo_base_cotizacion * 15: "+str(contract.sueldo_base_cotizacion * 15))
        _logger.info("total_imss: "+str(total_imss))
        return total_imss
    
    
    
    #
    @api.model
    def calculo_imss3(self, contract, worked_days, payslip, categories):
        #cuota del IMSS parte del Empleado
        #salario_cotizado = contract.sueldo_base_cotizacion * 15
        _logger.info("#################### Calculo de IMSS ##################")
        uma1 = round(contract.tablas_cfdi_id.uma, 2)
        uma3 =  round(contract.tablas_cfdi_id.uma * 3, 2)
        _logger.info("uma3: " + str(uma3))
        
        sueldo = categories.ALW * 2
        _logger.info("Sueldo mensual: " + str(sueldo))
        
        diasBase = 30.4
        
        sueldoDiario = sueldo / diasBase
        _logger.info("Sueldo diario: " + str(sueldoDiario))
        
        operacionExtra = ((15+1.5)/365)+1 
        _logger.info("operacionExtra: " + str(operacionExtra))
        
        salarioBaseCotizacion = operacionExtra * sueldoDiario
        _logger.info("salarioBaseCotizacion: " + str(salarioBaseCotizacion))
        
        salarioBaseCotizacion2 = salarioBaseCotizacion * diasBase
        _logger.info("salarioBaseCotizacion2: " + str(salarioBaseCotizacion2))
        
        totalRetencion = 2.375
        _logger.info("totalRetencion %: " + str(totalRetencion))
        
        retInicIMSS = (salarioBaseCotizacion2/100)*totalRetencion
        _logger.info("retInicIMSS: " + str(retInicIMSS))
        
        total_imss = retInicIMSS / 2
        _logger.info("total_imss: " + str(total_imss))
        return total_imss
    #
    
    
    
    
    @api.model
    def calculo_isr(self, contract, worked_days, payslip, categories):
        _logger.info("calculando isr..." + str(contract.periodicidad_pago))
        
        #sueldo = contract.sueldo_diario * worked_days.WORK100.number_of_days
        dias_base = 1
        #tabla_isr = self.env['tablas.cfdi'].browse(contract.tablas_cfdi_id.id)
        if contract.periodicidad_pago == '04':
            dias_base = 15
            tabla_isr = contract.tablas_cfdi_id.tabla_isr_quincenal
        if contract.periodicidad_pago == '05':
            dias_base = 15
            tabla_isr = contract.tablas_cfdi_id.tabla_LISR

            
        _logger.info("*****> contract.periodicidad_pago: " + str(contract.periodicidad_pago))
        #base_mensual_gravada = categories.ALW / dias_base
        #base_mensual_gravada = base_mensual_gravada * payslip.dias_pagar
        _logger.info("*****> categories.ALW: " + str(categories.ALW))
        sueldo = categories.ALW
        _logger.info("#################### Calculo de ISR ##################")
        _logger.info("-> Percepciones: " + str(sueldo))
        #if contract.periodicidad_pago == '05':
        #if contract.periodicidad_pago == '04':
            #tabla_isr_mensual = self.env['tablas.cfdi'].browse(contract.tablas_cfdi_id.id).tabla_isr_quincenal
        #_logger.info("tabla_isr_mensual: " + str(tabla_isr))
        limite_inferior = 0
        cuota_fija = 0
        excedente = 0

        lim_int_ant = 0
        cuota_fija_ant = 0
        excedente_ant = 0
        index = 0
        for record in tabla_isr:
            if record.lim_inf > sueldo:
                limite_inferior = lim_int_ant
                cuota_fija = cuota_fija_ant
                excedente = excedente_ant
                break
            index += 1
            lim_int_ant = record.lim_inf
            cuota_fija_ant = record.c_fija
            excedente_ant = record.s_excedente
        
        _logger.info("-> Limite inferior: " + str(limite_inferior))

        resta = round(sueldo - limite_inferior, 6)
        _logger.info("-> Excedente limite inferior: " + str(resta))
        _logger.info("-> % Sobre excedente: " + str(excedente))
        multiplica = round(resta * (excedente/100), 6)
        _logger.info("-> ISR Marginal: " + str(multiplica))
        suma = round(multiplica + cuota_fija, 6)
        _logger.info("-> Cuota fija: " + str(cuota_fija))
        #_logger.info("suma: " + str(suma))
        #resultado = (suma / payslip.dias_pagar) * dias_base
        resultado = suma

        _logger.info("-> ISR: " + str(resultado))
        _logger.info("--------------------------------------------------------------")

        return resultado

    
    
    
    #Fong 
    @api.model
    def calculo_isrVadsa(self, contract, worked_days, payslip, categories):
        _logger.info("calculando isrVadsa asimilado..." + str(contract.periodicidad_pago))
        
        self.env.cr.execute("Select itl_tipo_tabla_isr from hr_payroll_structure where name = 'Asimilados'")
        tipoTabla = str(self.env.cr.fetchall())
        _logger.info("query_test: (" + str(tipoTabla)+")")
        first_char = tipoTabla[5]
        _logger.info("char1:: (" + str(first_char)+")")
        
        divisor = -1
        if first_char == "1":
            divisor = 2
            
        if first_char == "2":
            divisor = 1   
        _logger.info("divisor: " + str(divisor))
        
        #sueldo = contract.sueldo_diario * worked_days.WORK100.number_of_days
        dias_base = 1
        #tabla_isr = self.env['tablas.cfdi'].browse(contract.tablas_cfdi_id.id)
        if contract.periodicidad_pago == '04':
            dias_base = 15
            tabla_isr = contract.tablas_cfdi_id.tabla_isr_quincenal
        if contract.periodicidad_pago == '05':
            dias_base = 30
            tabla_isr = contract.tablas_cfdi_id.tabla_LISR

        dias_base = 30/divisor
        _logger.info("dias_base: " + str(dias_base))
        
        
        tabla_isr = contract.tablas_cfdi_id.tabla_isr_quincenal
        if divisor == 1:
            tabla_isr = contract.tablas_cfdi_id.tabla_LISR
        _logger.info("tabla_isr: " + str(tabla_isr))
 
            
        _logger.info("*****> tabla_isr: " + str(tabla_isr))
        _logger.info("*****> contract.periodicidad_pago: " + str(contract.periodicidad_pago))
        #base_mensual_gravada = categories.ALW / dias_base
        #base_mensual_gravada = base_mensual_gravada * payslip.dias_pagar
        _logger.info("*****> categories.ALW: " + str(categories.ALW))
        sueldo = categories.ALW
        
        if divisor == 1:
            sueldo = sueldo * 2
        
        _logger.info("sueldo: " + str(sueldo))
        
        
        _logger.info("#################### Calculo de ISR ##################")
        _logger.info("-> Percepciones: " + str(sueldo))
        #if contract.periodicidad_pago == '05':
        #if contract.periodicidad_pago == '04':
            #tabla_isr_mensual = self.env['tablas.cfdi'].browse(contract.tablas_cfdi_id.id).tabla_isr_quincenal
        #_logger.info("tabla_isr_mensual: " + str(tabla_isr))
        limite_inferior = 0
        cuota_fija = 0
        excedente = 0

        lim_int_ant = 0
        cuota_fija_ant = 0
        excedente_ant = 0
        index = 0
        for record in tabla_isr:
            if record.lim_inf > sueldo:
                limite_inferior = lim_int_ant
                cuota_fija = cuota_fija_ant
                excedente = excedente_ant
                break
            index += 1
            lim_int_ant = record.lim_inf
            cuota_fija_ant = record.c_fija
            excedente_ant = record.s_excedente
        
        _logger.info("-> Limite inferior: " + str((limite_inferior))) #_logger.info("-> Limite inferior: " + str((limite_inferior/2)))
        #sueldo = sueldo/2
        #limite_inferior = limite_inferior/2
        #resta = round(sueldo - limite_inferior, 6) #base
        #_logger.info("-> Excedente limite inferior: " + str(resta))
        _logger.info("-> % Sobre excedente: " + str(excedente))
        multiplica = round(sueldo * (excedente/100), 6)
        _logger.info("-> ISR Marginal: " + str(multiplica))
        #suma = round(multiplica + (cuota_fija/2), 6)
        #_logger.info("-> Cuota fija: " + str((cuota_fija/2)))
        #_logger.info("suma: " + str(suma))
        #resultado = (suma / payslip.dias_pagar) * dias_base
        resta = multiplica #sueldo - multiplica
        resultado =  resta 
        if divisor == 1:
            resultado = resultado / 2
            _logger.info("resultado / 2")

        _logger.info("-> ISR: " + str(resultado))
        _logger.info("--------------------------------------------------------------")

        return resultado
     
    @api.model
    def calculo_isrVadsaSub(self, contract, worked_days, payslip, categories):
        _logger.info("calculando isrVadsa Subsidio..." + str(contract.periodicidad_pago))
        
        self.env.cr.execute("Select itl_tipo_tabla_isr from hr_payroll_structure where name = 'Subsidio'")
        tipoTabla = str(self.env.cr.fetchall())
        _logger.info("query_test: (" + str(tipoTabla)+")")
        first_char = tipoTabla[5]
        _logger.info("char1:: (" + str(first_char)+")")
        
        divisor = -1
        if first_char == "1":
            divisor = 2
            
        if first_char == "2":
            divisor = 1   
        _logger.info("divisor: " + str(divisor))
        
        #sueldo = contract.sueldo_diario * worked_days.WORK100.number_of_days
        dias_base = 1
        #tabla_isr = self.env['tablas.cfdi'].browse(contract.tablas_cfdi_id.id)
        if contract.periodicidad_pago == '04':
            dias_base = 15
            tabla_isr = contract.tablas_cfdi_id.tabla_isr_quincenal
        if contract.periodicidad_pago == '05':
            dias_base = 30
            tabla_isr = contract.tablas_cfdi_id.tabla_LISR

        dias_base = 30/divisor
        _logger.info("dias_base: " + str(dias_base))
        
        
        tabla_isr = contract.tablas_cfdi_id.tabla_isr_quincenal
        if divisor == 1:
            tabla_isr = contract.tablas_cfdi_id.tabla_LISR
        _logger.info("tabla_isr: " + str(tabla_isr))

            
        _logger.info("*****> tabla_isr: " + str(tabla_isr))
        _logger.info("*****> contract.periodicidad_pago: " + str(contract.periodicidad_pago))
        #base_mensual_gravada = categories.ALW / dias_base
        #base_mensual_gravada = base_mensual_gravada * payslip.dias_pagar
        _logger.info("*****> categories.ALW: " + str(categories.ALW))
        sueldo = categories.ALW
        
        if divisor == 1:
            sueldo = sueldo * 2
        
        _logger.info("sueldo: " + str(sueldo))
        
        _logger.info("#################### Calculo de ISR ##################")
        _logger.info("-> Percepciones: " + str(sueldo))
        #if contract.periodicidad_pago == '05':
        #if contract.periodicidad_pago == '04':
            #tabla_isr_mensual = self.env['tablas.cfdi'].browse(contract.tablas_cfdi_id.id).tabla_isr_quincenal
        #_logger.info("tabla_isr_mensual: " + str(tabla_isr))
        limite_inferior = 0
        cuota_fija = 0
        excedente = 0

        lim_int_ant = 0
        cuota_fija_ant = 0
        excedente_ant = 0
        index = 0
        for record in tabla_isr:
            if record.lim_inf > sueldo:
                limite_inferior = lim_int_ant
                cuota_fija = cuota_fija_ant
                excedente = excedente_ant
                break
            index += 1
            lim_int_ant = record.lim_inf
            cuota_fija_ant = record.c_fija
            excedente_ant = record.s_excedente
        
        _logger.info("-> Limite inferior: " + str(limite_inferior))

        resta = round(sueldo - limite_inferior, 6)
        _logger.info("-> Excedente limite inferior: " + str(resta))
        _logger.info("-> % Sobre excedente: " + str(excedente))
        multiplica = round(resta * (excedente/100), 6)
        _logger.info("-> ISR Marginal: " + str(multiplica))
        suma = round(multiplica + cuota_fija, 6)
        _logger.info("-> Cuota fija: " + str(cuota_fija))
        _logger.info("suma: " + str(suma))
        #resultado = (suma / payslip.dias_pagar) * dias_base
        resultado = suma

        
        
        tabla_subem = contract.tablas_cfdi_id.tabla_subem
        if divisor == 2:
            tabla_subem = contract.tablas_cfdi_id.tabla_subeq
            
        _logger.info("--> tabla_isr: " + str(tabla_isr))
        sub_limite_inferior = 0
        subsidio = 0 
        
        sub_lim_int_ant = 0
        subsidio_ant = 0
        sub_index = 0
        _logger.info("--> antes de for")
        for record in tabla_subem:
            _logger.info("-- > for record: " + str(sub_index))
            if record.lim_inf > sueldo:
                _logger.info("record.lim_inf: ("+str(record.lim_inf)+") sueldo: (" + str(sueldo)+")")
                sub_limite_inferior = sub_lim_int_ant
                _logger.info("-- > sub_limite_inferior: " + str(sub_limite_inferior))
                subsidio = subsidio_ant
                _logger.info("-- > subsidio: " + str(subsidio))
                break
            sub_index += 1
            sub_lim_int_ant = record.lim_inf
            _logger.info("-- > sub_lim_int_ant: " + str(sub_lim_int_ant))
            
            if divisor == 1:
                subsidio_ant = record.s_mensual
            if divisor == 2:
                subsidio_ant = record.s_quincenal
                
            _logger.info("-- > subsidio_ant: " + str(subsidio_ant))
            
        _logger.info("-- > salio de for ")
         
           
        _logger.info("-> subsidio: " + str(subsidio))
        _logger.info("-> resultado: " + str(resultado))
        restaResSub = resultado - subsidio
        
        _logger.info("-> ISR: " + str(restaResSub))
        _logger.info("--------------------------------------------------------------")

        if divisor == 1:
            restaResSub = restaResSub / 2
            _logger.info("restaResSub / 2")
        return restaResSub
    
    
     
    
    
    @api.model
    def calculo_descuentos(self, contract, worked_days, payslip, categories):
        #cuota del IMSS parte del Empleado
        #salario_cotizado = contract.sueldo_base_cotizacion * 15
        _logger.info("#################### Calculo de DESCUENTOS ##################")
        
        total_imss = payslip.env['hr.payslip'].calculo2_imss(contract, worked_days, payslip, categories)
        _logger.info("[total_imss: "+str(total_imss) + "] ")
        total_isr = payslip.env['hr.payslip'].calculo_isrVadsaSub(contract, worked_days, payslip, categories)
        _logger.info("[total_isr: "+str(total_isr)+"]")
       
        sueldo = categories.ALW
        _logger.info("sueldo: " + str(sueldo))
        total_DESC = (total_isr + total_imss)
        _logger.info("total_DESC 1: " + str(total_DESC))
        total_DESC = sueldo - total_DESC
        _logger.info("total_DESC: "+str(total_DESC))
        return total_DESC 
    #Fong final---------
    
    
    
    
    
    def compute_sheet(self):
        record = super(HrPayslip, self).compute_sheet()
        
        if self.employee_id.regimen == '02':
            subsidio_empleo = self.line_ids.filtered(lambda line: line.category_id.code == 'DED_OTRO' and line.salary_rule_id.tipo_otro_pago == '002')
            if len(subsidio_empleo) == 0:
                raise ValidationError('El tipo de régimen configurado en el empleado es "' + str(dict(self.employee_id._fields['regimen'].selection).get(self.employee_id.regimen)) + '" por lo que debe de agregar una regla que indique el Subsidio para el empleo con clave 002.')
        
        """
        _logger.info("---> compute_sheet")
        subtotal = 0
        descuento = 0
        for rec in self.line_ids:
            if 'ALW' in rec.category_id.code:
                subtotal = subtotal  + rec.total
            if 'DED' in rec.category_id.code:
                _logger.info("***> rec.name: " + str(rec.name))
                _logger.info("***> rec.category: " + str(rec.category_id.code))
                descuento = descuento + rec.total
        
        self.subtotal = subtotal
        self.descuento = descuento
        _logger.info("---> self.subtotal: " + str(self.subtotal))
        _logger.info("---> self.descuento: " + str(self.descuento))
        self.total_nomina = self.subtotal - (self.descuento * -1)
        self.neto_total_amount = self.subtotal - (self.descuento * -1)
        _logger.info("---> self.total_nomina: " + str(self.total_nomina))
        """
        
        return record
    

    ##############################################################
    ############### For sign payroll #############################
    ##############################################################
    invoice_payment_term_id = fields.Many2one('account.payment.term', string='Payment Terms',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        readonly=True, states={'draft': [('readonly', False)], 'verify': [('readonly', False)]})
    
    def create_cfdi(self):
        '''Creates and returns a dictionnary containing 'cfdi' if the cfdi is well created, 'error' otherwise.
        '''
        self.ensure_one()
        qweb = self.env['ir.qweb']
        error_log = []
        company_id = self.company_id
        pac_name = company_id.l10n_mx_edi_pac
        values = {}
        #if self.l10n_mx_edi_external_trade:
            # Call the onchange to obtain the values of l10n_mx_edi_qty_umt
            # and l10n_mx_edi_price_unit_umt, this is necessary when the
            # invoice is created from the sales order or from the picking
            #self.invoice_line_ids.onchange_quantity()
            #self.invoice_line_ids._set_price_unit_umt()
        # ----------
        # Producto nómina
        #-----------
        net_salary = self.line_ids.filtered(lambda line: line.code == 'NET')
        
        allowances = self.line_ids.filtered(lambda line: line.category_id.code == 'ALW')
        allowance_amount = 0.0
        if allowances:
            allowance_amount = sum(allowances.mapped('total'))
        
        deductions = self.line_ids.filtered(lambda line: line.category_id.code == 'DED')
        deduction_amount = 0.0
        if deductions:
            deduction_amount = sum(deductions.mapped('total'))
        
        other_inputs = self.line_ids.filtered(lambda line: line.category_id.code == 'DED2')
        #_logger.info("other_inputs:----> " + str(other_inputs))
        other_inputs_amount = 0.0
        if other_inputs:
            other_inputs_amount = sum(other_inputs.mapped('total'))
        
        values['otros_amount'] = other_inputs_amount
        allowance_amount = allowance_amount + other_inputs_amount
        #_logger.info("allowances: " + str(sum(allowances.mapped('total'))))
        values['concepts'] = [{
            'quantity': 1,
            'product_code': '84111505',
            'unit_code': 'ACT',
            'name': 'Pago de nómina',
            'discount': deduction_amount,
            'total_amount': allowance_amount,
            'unit_amount': allowance_amount
        }]
        
        values = self.create_cfdi_values(values)
        
        # -----------------------
        # Check the configuration
        # -----------------------
        # -Check certificate
        certificate_ids = company_id.l10n_mx_edi_certificate_ids
        certificate_id = certificate_ids.sudo().get_valid_certificate()
        if not certificate_id:
            error_log.append(_('No valid certificate found'))
        
        # -Check PAC
        if pac_name:
            pac_test_env = company_id.l10n_mx_edi_pac_test_env
            pac_password = company_id.l10n_mx_edi_pac_password
            if not pac_test_env and not pac_password:
                error_log.append(_('No PAC credentials specified.'))
        else:
            error_log.append(_('No PAC specified.'))

        if error_log:
            return {'error': _('Please check your configuration: ') + create_list_html(error_log)}

        # -Compute date and time of the invoice
        date_mx = self.env['l10n_mx_edi.certificate'].sudo().get_mx_current_datetime()
        date_mx_time = self._update_hour_timezone()
        #_logger.info("date_mx: ----- > " + str(date_mx.date()))
        time_invoice = datetime.strptime(date_mx_time, DEFAULT_SERVER_TIME_FORMAT).time()
        
        # -----------------------
        # Create the EDI document
        # -----------------------
        version = self.get_pac_version()

        # -Compute certificate data
        values['date'] = datetime.combine(
            fields.Datetime.from_string(date_mx.date()), time_invoice).strftime('%Y-%m-%dT%H:%M:%S')
        values['certificate_number'] = certificate_id.serial_number
        values['certificate'] = certificate_id.sudo().get_data()[0]
        
        _logger.info("values: " + str(values))
        
        # -Compute cfdi
        cfdi = qweb.render(CFDI_TEMPLATE_NOMINA12, values=values)
        cfdi = cfdi.replace(b'xmlns__', b'xmlns:')
        
        node_sello = 'Sello'
        attachment = self.env.ref('l10n_mx_edi.xsd_cached_nomina12_xsd', False)
        xsd_datas = base64.b64decode(attachment.datas) if attachment else b''
        
        #_logger.info("xsd_datas: " + str(xsd_datas))
        
        # -Compute cadena
        tree = self.l10n_mx_edi_get_xml_etree(cfdi)
        #_logger.info("tree: ---> " + str(tree))
        cadena = self.l10n_mx_edi_generate_cadena(CFDI_XSLT_CADENA % version, tree)
        
        tree.attrib[node_sello] = certificate_id.sudo().get_encrypted_cadena(cadena)
        #_logger.info("cfdi: " + str(cfdi))
        #raise UserError("tree:----->" + str(etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding='UTF-8')))
        return {'cfdi': etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding='UTF-8')}
        # Check with xsd
        #if xsd_datas:
        #    try:
        #        with BytesIO(xsd_datas) as xsd:
        #            #_logger.info("tree: " + str(tree))
        #            #_logger.info("xsd: " + str(xsd))
        #            _check_with_xsd(tree, xsd)
        #    except (IOError, ValueError):
        #        raise UserError(_('The xsd file to validate the XML structure was not found'))
        #        _logger.info(
        #            _('The xsd file to validate the XML structure was not found'))
        #    except Exception as e:
        #        raise UserError(_('The cfdi generated is not valid') +
        #                            create_list_html(str(e).split('\\n')))
        #        return {'error': (_('The cfdi generated is not valid') +
        #                            create_list_html(str(e).split('\\n')))}
        #raise UserError("OK")
        #return {'cfdi': etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding='UTF-8')}
    
    def edi_retry(self):
        '''Try to generate the cfdi attachment and then, sign it.
        '''
        _logger.info("FONG ---> P1")
        version = self.get_pac_version()
        _logger.info("FONG ---> P2")
        for nom in self:
            cfdi_values = nom.create_cfdi()
            _logger.info("FONG ---> P3 cfdi_values: "+str(cfdi_values))
            error = cfdi_values.pop('error', None)
            _logger.info("FONG ---> P3 error: "+str(error))
            cfdi = cfdi_values.pop('cfdi', None)
            _logger.info("FONG ---> P3_2s cfdi: "+str(cfdi))
             
            if error:
                _logger.info("FONG ---> P4 cfdi: cfdi failed to be generated")
                # cfdi failed to be generated
                nom.l10n_mx_edi_pac_status = 'retry'
                #nom.message_post(body=error, subtype='account.mt_invoice_validated')
                nom.message_post(body=error)
                continue
            # cfdi has been successfully generated
            _logger.info("FONG ---> P4 cfdi: cfdi has been successfully generated")
            nom.l10n_mx_edi_pac_status = 'to_sign'
            _logger.info("FONG ---> P5 nom.l10n_mx_edi_pac_status: "+str(nom.l10n_mx_edi_pac_status))
            filename = ('%s-MX-Payroll-%s.xml' % (
                nom.number, version.replace('.', '-'))).replace('/', '')
            _logger.info("FONG ---> P6 filename: "+str(filename))
            ctx = self.env.context.copy()
            _logger.info("FONG ---> P7 ctx: "+str(ctx))
            ctx.pop('default_type', False)
            nom.l10n_mx_edi_cfdi_name = filename
            _logger.info("FONG ---> P8 nom.l10n_mx_edi_cfdi_name: "+str(nom.l10n_mx_edi_cfdi_name))
            attachment_id = self.env['ir.attachment'].with_context(ctx).create({
                'name': filename,
                'res_id': nom.id,
                'res_model': nom._name,
                'datas': base64.encodestring(cfdi),
                'description': 'Mexican payroll',
                })
            #nom.message_post(
            #    body=_('CFDI document generated (may be not signed)'),
            #    attachment_ids=[attachment_id.id],
            #    subtype='account.mt_invoice_validated')
            nom.message_post(
                body=_('CFDI document generated (may be not signed)'),
                attachment_ids=[attachment_id.id])
            nom._sign()
    
    def _sign(self):
        _logger.info("FONG ---> P9 Entro a def _sign(self):")
        '''Call the sign service with records that can be signed.
        '''
        records = self.search([
            ('l10n_mx_edi_pac_status', 'not in', ['signed', 'to_cancel', 'cancelled', 'retry']),
            ('id', 'in', self.ids)])
        _logger.info("FONG ---> P11 records: "+str(records))
        records._l10n_mx_edi_call_service('sign')
    
    @run_after_commit
    def _l10n_mx_edi_call_service(self, service_type):
        '''Call the right method according to the pac_name, it's info returned by the '_l10n_mx_edi_%s_info' % pac_name'
        method and the service_type passed as parameter.
        :param service_type: sign or cancel
        '''
        # Regroup the invoices by company (= by pac)
        _logger.info("FONG ---> P12")
        comp_x_records = groupby(self, lambda r: r.company_id)
        for company_id, records in comp_x_records:
            pac_name = company_id.l10n_mx_edi_pac
            if not pac_name:
                continue
            # Get the informations about the pac
            pac_info_func = '_%s_info' % pac_name
            service_func = '_%s_%s' % (pac_name, service_type)
            pac_info = getattr(self, pac_info_func)(company_id, service_type)
            
            for record in records:
                getattr(record, service_func)(pac_info)

    def _prodigia_sign(self, pac_info):
        '''SIGN for Prodigia.
        '''
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        contract = pac_info['contract']
        test = pac_info['test']
        for nom in self:
            #raise UserError(nom.folio_fiscal)
            cfdi = nom.l10n_mx_edi_cfdi.decode('UTF-8')
            # cfdi = base64.decodestring(inv.l10n_mx_edi_cfdi)
            try:
                client = Client(url, timeout=50)
                if(test):
                    response = client.service.timbradoOdooPrueba(
                        contract, username, password, cfdi)
                else:
                    response = client.service.timbradoOdoo(
                        contract, username, password, cfdi)
            except Exception as e:
                nom.l10n_mx_edi_log_error(str(e))
                continue
            msg = getattr(response, 'mensaje', None)
            code = getattr(response, 'codigo', None)
            xml_signed = getattr(response, 'xml', None)
            nom._l10n_mx_edi_post_sign_process(xml_signed, code, msg)
    
    def _prodigia_cancel(self, pac_info):
        '''CANCEL Prodigia.
        '''

        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        contract = pac_info['contract']
        test = pac_info['test']
        #rfc_receptor = self.partner_id.vat
        rfc_receptor = self.employee_id.rfc
        rfc_emisor = self.company_id
        if self:
            certificate_id = self[0].company_id.l10n_mx_edi_certificate_ids[0].sudo(
            )
        for payr in self:

            # uuids = [inv.l10n_mx_edi_cfdi_uuid]
            rfc_receptor = payr.employee_id
            rfc_rec = ""
            if rfc_receptor.rfc is False:
                rfc_rec = "XAXX010101000"
            else:
                rfc_rec = rfc_receptor.rfc

            uuids = [payr.l10n_mx_edi_cfdi_uuid+"|"+rfc_rec +
                     "|"+rfc_emisor.vat+"|" + str(payr.amount_total)]

            if not certificate_id:
                certificate_id = payr.l10n_mx_edi_cfdi_certificate_id.sudo()
            cer_pem = base64.encodestring(certificate_id.get_pem_cer(
                certificate_id.content)).decode('UTF-8')
            key_pem = base64.encodestring(certificate_id.get_pem_key(
                certificate_id.key, certificate_id.password)).decode('UTF-8')
            key_password = certificate_id.password
            rfc_emisor = self.company_id
            cancelled = False
            if(test):
                cancelled = True
                msg = 'Este comprobante se cancelo en modo pruebas'
                code = '201'
                payr._l10n_mx_edi_post_cancel_process(cancelled, code, msg)
                continue
            try:
                client = Client(url, timeout=50)
                response = client.service.cancelar(
                    contract, username, password, rfc_emisor.vat, uuids, cer_pem, key_pem, key_password)
            except Exception as e:
                payr.l10n_mx_edi_log_error(str(e))
                continue
            code = getattr(response, 'codigo', None)
            cancelled = code in ('201', '202')
            msg = '' if cancelled else getattr(response, 'mensaje', None)
            code = '' if cancelled else code
            payr._l10n_mx_edi_post_cancel_process(cancelled, code, msg)

            
    def _l10n_mx_edi_post_sign_process(self, xml_signed, code=None, msg=None):
        _logger.info("FONG ---> P19")
        '''Post process the results of the sign service.

        :param xml_signed: the xml signed datas codified in base64
        :param code: an eventual error code
        :param msg: an eventual error msg
        '''
        self.ensure_one()
        _logger.info("FONG ---> P20 xml_signed" + str(xml_signed)) 
        if xml_signed:
            # Post append addenda
            body_msg = _('The sign service has been called with success')
            # Update the pac status
            self.l10n_mx_edi_pac_status = 'signed'
            self.l10n_mx_edi_cfdi = xml_signed
            # Update the content of the attachment
            attachment_id = self.l10n_mx_edi_retrieve_last_attachment()
            attachment_id.write({
                'datas': xml_signed,
                'mimetype': 'application/xml'
            })
            #xml_signed = self.l10n_mx_edi_append_addenda(xml_signed)
            post_msg = [_('The content of the attachment has been updated')]
            self.estado_factura = 'factura_correcta'
        else:
            body_msg = _('The sign service requested failed')
            post_msg = []
            self.estado_factura = 'problemas_factura'
        if code:
            post_msg.extend([_('Code: %s') % code])
        if msg:
            post_msg.extend([_('Message: %s') % msg])
        self.message_post(
            body=body_msg + create_list_html(post_msg))
    
    def _prodigia_info(self, company_id, service_type):
        test = company_id.l10n_mx_edi_pac_test_env
        contract = company_id.l10n_mx_edi_pac_contract
        password = company_id.l10n_mx_edi_pac_password
        user = company_id.l10n_mx_edi_pac_username
        url = 'https://timbrado.pade.mx/odoo/PadeOdooTimbradoService?wsdl'
        return {
            'url': url,
            'username': user,
            'password': password,
            'contract': contract,
            'test': test,
        }
    
    
    def _solfact_info(self, company_id, service_type):
        test = company_id.l10n_mx_edi_pac_test_env
        username = company_id.l10n_mx_edi_pac_username
        password = company_id.l10n_mx_edi_pac_password
        url = 'https://testing.solucionfactible.com/ws/services/Timbrado?wsdl'\
            if test else 'https://solucionfactible.com/ws/services/Timbrado?wsdl'
        return {
            'url': url,
            'multi': False,  # TODO: implement multi
            'username': 'testing@solucionfactible.com' if test else username,
            'password': 'timbrado.SF.16672' if test else password,
        }

    def _solfact_sign(self, pac_info):
        '''SIGN for Solucion Factible.
        '''
        _logger.info("FONG ---> P13")
        url = pac_info['url']
        username = pac_info['username']
        _logger.info("FONG ---> username: " + str(username))
        password = pac_info['password']
        _logger.info("FONG ---> password: " + str(password))
        for inv in self:
            cfdi = inv.l10n_mx_edi_cfdi.decode('UTF-8')
            _logger.info("FONG ---> P14 cfdi: " + str(cfdi))
            try:
                client = Client(url, timeout=20)
                response = client.service.timbrar(username, password, cfdi, False)
            except Exception as e:
                inv.l10n_mx_edi_log_error(str(e))
                continue
            res = response.resultados
            _logger.info("FONG ---> P15 res: " + str(res))
            msg = getattr(res[0] if res else response, 'mensaje', None)
            _logger.info("FONG ---> P16 msg: " + str(msg))
            code = getattr(res[0] if res else response, 'status', None)
            _logger.info("FONG ---> P17 code: " + str(code))
            xml_signed = getattr(res[0] if res else response, 'cfdiTimbrado', None)
            _logger.info("FONG ---> P18 xml_signed: " + str(xml_signed))
            inv._l10n_mx_edi_post_sign_process(
                xml_signed.encode('utf-8') if xml_signed else None, code, msg) 

    def _solfact_cancel(self, pac_info):
        '''CANCEL for Solucion Factible.
        '''
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        for inv in self:
            uuids = [inv.l10n_mx_edi_cfdi_uuid]
            certificate_ids = inv.company_id.l10n_mx_edi_certificate_ids
            certificate_id = certificate_ids.sudo().get_valid_certificate()
            cer_pem = base64.encodestring(certificate_id.get_pem_cer(
                certificate_id.content)).decode('UTF-8')
            key_pem = base64.encodestring(certificate_id.get_pem_key(
                certificate_id.key, certificate_id.password)).decode('UTF-8')
            key_password = certificate_id.password
            try:
                client = Client(url, timeout=20)
                response = client.service.cancelar(username, password, uuids, cer_pem.replace(
                    '\n', ''), key_pem, key_password)
            except Exception as e:
                inv.l10n_mx_edi_log_error(str(e))
                continue
            res = response.resultados
            code = getattr(res[0], 'statusUUID', None) if res else getattr(response, 'status', None)
            cancelled = code in ('201', '202')  # cancelled or previously cancelled
            # no show code and response message if cancel was success
            msg = '' if cancelled else getattr(res[0] if res else response, 'mensaje', None)
            code = '' if cancelled else code
            inv._l10n_mx_edi_post_cancel_process(cancelled, code, msg)
    
    
    def _finkok_info(self, company_id, service_type):
        test = company_id.l10n_mx_edi_pac_test_env
        username = company_id.l10n_mx_edi_pac_username
        _logger.info("FONG ---> P21 username: " + str(username))
        password = company_id.l10n_mx_edi_pac_password 
        if service_type == 'sign':
            url = 'http://demo-facturacion.finkok.com/servicios/soap/stamp.wsdl'\
                if test else 'http://facturacion.finkok.com/servicios/soap/stamp.wsdl'
        else:
            url = 'http://demo-facturacion.finkok.com/servicios/soap/cancel.wsdl'\
                if test else 'http://facturacion.finkok.com/servicios/soap/cancel.wsdl'
        return {
            'url': url,
            'multi': False,  # TODO: implement multi
            'username': 'cfdi@vauxoo.com' if test else username,
            'password': 'vAux00__' if test else password,
        }

    
    def _finkok_sign(self, pac_info):
        '''SIGN for Finkok.
        '''
        url = pac_info['url']
        password = pac_info['password']
        for inv in self:
            cfdi = [inv.l10n_mx_edi_cfdi.decode('UTF-8')]
            try:
                client = Client(url, timeout=20)
                response = client.service.stamp(cfdi, username, password)
            except Exception as e:
                inv.l10n_mx_edi_log_error(str(e))
                continue
            code = 0
            msg = None
            if response.Incidencias:
                code = getattr(response.Incidencias[0][0], 'CodigoError', None)
                msg = getattr(response.Incidencias[0][0], 'MensajeIncidencia', None)
            xml_signed = getattr(response, 'xml', None)
            if xml_signed:
                xml_signed = base64.b64encode(xml_signed.encode('utf-8'))
            inv._l10n_mx_edi_post_sign_process(xml_signed, code, msg)

            
    def _l10n_mx_edi_finkok_cancel(self, pac_info):
        '''CANCEL for Finkok.
        '''
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        for inv in self:
            uuid = inv.l10n_mx_edi_cfdi_uuid
            certificate_ids = inv.company_id.l10n_mx_edi_certificate_ids
            certificate_id = certificate_ids.sudo().get_valid_certificate()
            company_id = self.company_id
            cer_pem = base64.encodestring(certificate_id.get_pem_cer(
                certificate_id.content)).decode('UTF-8')
            key_pem = base64.encodestring(certificate_id.get_pem_key(
                certificate_id.key, certificate_id.password)).decode('UTF-8')
            cancelled = False
            code = False
            try:
                client = Client(url, timeout=20)
                invoices_list = client.factory.create("UUIDS")
                invoices_list.uuids.string = [uuid]
                response = client.service.cancel(invoices_list, username, password, company_id.vat, cer_pem.replace(
                    '\n', ''), key_pem)
            except Exception as e:
                inv.l10n_mx_edi_log_error(str(e))
                continue
            if not getattr(response, 'Folios', None):
                code = getattr(response, 'CodEstatus', None)
                msg = _("Cancelling got an error") if code else _('A delay of 2 hours has to be respected before to cancel')
            else:
                code = getattr(response.Folios[0][0], 'EstatusUUID', None)
                cancelled = code in ('201', '202')  # cancelled or previously cancelled
                # no show code and response message if cancel was success
                code = '' if cancelled else code
                msg = '' if cancelled else _("Cancelling got an error")
            inv._l10n_mx_edi_post_cancel_process(cancelled, code, msg)
            
    def l10n_mx_edi_log_error(self, message):
        self.ensure_one()
        self.message_post(body=_('Error during the process: %s') % message)
    
    @api.model
    def l10n_mx_edi_generate_cadena(self, xslt_path, cfdi_as_tree):
        '''Generate the cadena of the cfdi based on an xslt file.
        The cadena is the sequence of data formed with the information contained within the cfdi.
        This can be encoded with the certificate to create the digital seal.
        Since the cadena is generated with the invoice data, any change in it will be noticed resulting in a different
        cadena and so, ensure the invoice has not been modified.

        :param xslt_path: The path to the xslt file.
        :param cfdi_as_tree: The cfdi converted as a tree
        :return: A string computed with the invoice data called the cadena
        '''
        xslt_root = etree.parse(tools.file_open(xslt_path))
        return str(etree.XSLT(xslt_root)(cfdi_as_tree))
    
    @api.model
    def l10n_mx_edi_get_xml_etree(self, cfdi=None):
        '''Get an objectified tree representing the cfdi.
        If the cfdi is not specified, retrieve it from the attachment.

        :param cfdi: The cfdi as string
        :return: An objectified tree
        '''
        #_logger.info("cfdi: ---< " + str(cfdi))
        #TODO helper which is not of too much help and should be removed 
        self.ensure_one()
        if cfdi is None and self.l10n_mx_edi_cfdi:
            cfdi = base64.decodestring(self.l10n_mx_edi_cfdi)
        return fromstring(cfdi) if cfdi else None

    def _update_hour_timezone(self):
        for payr in self:
            partner = payr.company_id.partner_id.commercial_partner_id
            tz = self._get_timezone(partner.state_id.code)

            datetime_mx_tz = datetime.now(tz)
            return datetime_mx_tz.strftime("%H:%M:%S")
            
    @api.model
    def _get_timezone(self, state):
        # northwest area
        if state == 'BCN':
            return timezone('America/Tijuana')
        # Southeast area
        elif state == 'ROO':
            return timezone('America/Cancun')
        # Pacific area
        elif state in ('BCS', 'CHH', 'SIN', 'NAY'):
            return timezone('America/Chihuahua')
        # Sonora
        elif state == 'SON':
            return timezone('America/Hermosillo')
        # By default, takes the central area timezone
        return timezone('America/Mexico_City')

    @api.model
    def get_pac_version(self):
        '''Returns the cfdi version to generate the CFDI.
        In December, 1, 2017 the CFDI 3.2 is deprecated, after of July 1, 2018
        the CFDI 3.3 could be used.
        '''
        version = self.env['ir.config_parameter'].sudo().get_param(
            'l10n_mx_edi_cfdi_version', '3.3')
        return version
    
    @staticmethod
    def _get_serie_and_folio(number):
        values = {'serie': None, 'folio': None}
        number = (number or '').strip()
        number_matchs = [rn for rn in re.finditer('\d+', number)]
        if number_matchs:
            last_number_match = number_matchs[-1]
            values['serie'] = number[:last_number_match.start()] or None
            values['folio'] = last_number_match.group().lstrip('0') or None
        return values
    
    def get_cfdi_related(self):
        """To node CfdiRelacionados get documents related with each invoice
        from l10n_mx_edi_origin, hope the next structure:
            relation type|UUIDs separated by ,"""
        self.ensure_one()
        if not self.uuid_relacionado:
            return {}
        origin = self.uuid_relacionado.split('|')
        uuids = origin[1].split(',') if len(origin) > 1 else []
        return {
            'type': origin[0],
            'related': [u.strip() for u in uuids],
            }
    
    @api.model
    def get_pac_version(self):
        '''Returns the cfdi version to generate the CFDI.
        In December, 1, 2017 the CFDI 3.2 is deprecated, after of July 1, 2018
        the CFDI 3.3 could be used.
        '''
        version = self.env['ir.config_parameter'].sudo().get_param(
            'l10n_mx_edi_cfdi_version', '3.3')
        return version
    
    @staticmethod
    def _get_string_cfdi(text, size=100):
        """Replace from text received the characters that are not found in the
        regex. This regex is taken from SAT documentation
        https://goo.gl/C9sKH6
        text: Text to remove extra characters
        size: Cut the string in size len
        Ex. 'Product ABC (small size)' - 'Product ABC small size'"""
        if not text:
            return None
        text = text.replace('|', ' ')
        return text.strip()[:size]
    
    def _l10n_mx_edi_get_payment_policy(self):
        self.ensure_one()
        version = self.get_pac_version()
        term_ids = self.invoice_payment_term_id.line_ids
        if version == '3.2':
            if len(term_ids.ids) > 1:
                return 'Pago en parcialidades'
            else:
                return 'Pago en una sola exhibición'
        elif version == '3.3' and self.fecha_pago:
            #if self.type == 'out_refund':
            return 'PUE'
            # In CFDI 3.3 - SAT 2018 rule 2.7.1.44, the payment policy is PUE
            # if the invoice will be paid before 17th of the following month,
            # PPD otherwise
            date_pue = (fields.Date.from_string(self.invoice_date) +
                        relativedelta(day=17, months=1))
            invoice_date_due = fields.Date.from_string(self.fecha_pago)
            if (invoice_date_due > date_pue or len(term_ids) > 1):
                return 'PPD'
            return 'PUE'
        return ''
    
    def create_cfdi_values(self, values):
        '''Create the values to fill the CFDI template.
        '''
        self.ensure_one()
        precision_digits = self.currency_id.l10n_mx_edi_decimal_places
        if precision_digits is False:
            raise UserError(_(
                "The SAT does not provide information for the currency %s.\n"
                "You must get manually a key from the PAC to confirm the "
                "currency rate is accurate enough."), self.currency_id)
        partner_id = self.employee_id.user_partner_id
        if self.employee_id.user_partner_id.type != 'invoice':
            partner_id = self.employee_id.user_partner_id.commercial_partner_id
        values.update({
            'record': self,
            'currency_name': self.currency_id.name,
            'supplier': self.company_id.partner_id.commercial_partner_id,
            #'issued': self.journal_id.l10n_mx_address_issued_id,
            'customer': partner_id,
            'fiscal_regime': self.company_id.l10n_mx_edi_fiscal_regime,
            'payment_method': self.l10n_mx_edi_payment_method_id.code,
            'use_cfdi': self.l10n_mx_edi_usage,
            'conditions': False,
        })

        _logger.info("---> FONG: P22 self.company_id.l10n_mx_edi_fiscal_regime: " + str(self.company_id.l10n_mx_edi_fiscal_regime))
        
        values.update(self._get_serie_and_folio(self.number))
        ctx = dict(company_id=self.company_id.id, date=self.fecha_pago)
        mxn = self.env.ref('base.MXN').with_context(ctx)
        payroll_currency = self.currency_id.with_context(ctx)
        values['rate'] = ('%.6f' % (
            payroll_currency._convert(1, mxn, self.company_id, self.fecha_pago or fields.Date.today(), round=False))) if self.currency_id.name != 'MXN' else False

        values['document_type'] = 'nomina'
        values['payment_policy'] = self._l10n_mx_edi_get_payment_policy()
        #domicile = self.journal_id.l10n_mx_address_issued_id or self.company_id
        #values['domicile'] = '%s %s, %s' % (
        #        domicile.city,
        #        domicile.state_id.name,
        #        domicile.country_id.name,
        #)
        antiguedad = 1
        _logger.info("---> FONG: self.contract_id.date_end: " + str(self.contract_id.date_end))
        _logger.info("---> FONG: self.contract_id.date_start: " + str(self.contract_id.date_start))
        _logger.info("---> FONG: self.date_to: " + str(self.date_to))
        _logger.info("---> FONG: self.contract_id.date_start: " + str(self.contract_id.date_start))
        if self.contract_id.date_end and self.contract_id.date_start:
            _logger.info("---> if")
            antiguedad = int((self.contract_id.date_end - self.contract_id.date_start + timedelta(days=1)).days/7)
        elif self.date_to and self.contract_id.date_start:
            _logger.info("---> else")
            antiguedad = int((self.date_to - self.contract_id.date_start + timedelta(days=1)).days/7)
        _logger.info("---> antiguedad: " + str(antiguedad))
        values['antiguedad'] = 'P' + str(antiguedad) + 'W'
        values['total_exento'] = round(0.0, 2)
        values['total_gravado'] = sum(self.line_ids.filtered(lambda line: line.category_id.code == 'ALW').mapped('total'))
        
        values['amount_untaxed'] = round(values['concepts'][0]['total_amount'], 2)
        values['amount_discount'] = round(values['concepts'][0]['discount'], 2)
        values['amount_total'] = round(round(values['concepts'][0]['total_amount'], 2) - round(values['concepts'][0]['discount'], 2), 2)
        """
        values['decimal_precision'] = precision_digits
        subtotal_wo_discount = lambda l: float_round(
            l.price_subtotal / (1 - l.discount/100) if l.discount != 100 else
            l.price_unit * l.quantity, int(precision_digits))
        values['subtotal_wo_discount'] = subtotal_wo_discount
        get_discount = lambda l, d: ('%.*f' % (
            int(d), subtotal_wo_discount(l) - l.price_subtotal)) if l.discount else False
        values['total_discount'] = get_discount
        total_discount = sum([float(get_discount(p, precision_digits)) for p in self.invoice_line_ids])
        values['amount_untaxed'] = '%.*f' % (
            precision_digits, sum([subtotal_wo_discount(p) for p in self.invoice_line_ids]))
        values['amount_discount'] = '%.*f' % (precision_digits, total_discount) if total_discount else None

        values['taxes'] = self._l10n_mx_edi_create_taxes_cfdi_values()
        values['amount_total'] = '%0.*f' % (precision_digits,
            float(values['amount_untaxed']) - float(values['amount_discount'] or 0) + (
                values['taxes']['total_transferred'] or 0) - (values['taxes']['total_withhold'] or 0))

        values['tax_name'] = lambda t: {'ISR': '001', 'IVA': '002', 'IEPS': '003'}.get(t, False)

        if self.l10n_mx_edi_partner_bank_id:
            digits = [s for s in self.l10n_mx_edi_partner_bank_id.acc_number if s.isdigit()]
            acc_4number = ''.join(digits)[-4:]
            values['account_4num'] = acc_4number if len(acc_4number) == 4 else None
        else:
            values['account_4num'] = None
        """
        #values.update(self._get_external_trade_values(values))
        return values
    
    @api.model
    def _get_l10n_mx_edi_cadena(self):
        self.ensure_one()
        #get the xslt path
        xslt_path = CFDI_XSLT_CADENA_TFD
        #get the cfdi as eTree
        cfdi = base64.decodestring(self.l10n_mx_edi_cfdi)
        cfdi = self.l10n_mx_edi_get_xml_etree(cfdi)
        cfdi = self.l10n_mx_edi_get_tfd_etree(cfdi)
        #return the cadena
        return self.l10n_mx_edi_generate_cadena(xslt_path, cfdi)
    
    @api.model
    def l10n_mx_edi_get_et_etree(self, cfdi):
        """Get the ComercioExterior node from the cfdi.
        :param cfdi: The cfdi as etree
        :return: the ComercioExterior node
        """
        if not hasattr(cfdi, 'Complemento'):
            return None
        attribute = 'cce11:ComercioExterior[1]'
        namespace = {'cce11': 'http://www.sat.gob.mx/ComercioExterior11'}
        node = cfdi.Complemento.xpath(attribute, namespaces=namespace)
        return node[0] if node else None
    
    def l10n_mx_edi_update_sat_status(self):
        '''Synchronize both systems: Odoo & SAT to make sure the invoice is valid.
        '''
        url = 'https://consultaqr.facturaelectronica.sat.gob.mx/ConsultaCFDIService.svc?wsdl'
        headers = {'SOAPAction': 'http://tempuri.org/IConsultaCFDIService/Consulta', 'Content-Type': 'text/xml; charset=utf-8'}
        template = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:ns0="http://tempuri.org/" xmlns:ns1="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
   <SOAP-ENV:Header/>
   <ns1:Body>
      <ns0:Consulta>
         <ns0:expresionImpresa>${data}</ns0:expresionImpresa>
      </ns0:Consulta>
   </ns1:Body>
</SOAP-ENV:Envelope>"""
        namespace = {'a': 'http://schemas.datacontract.org/2004/07/Sat.Cfdi.Negocio.ConsultaCfdi.Servicio'}
        for inv in self.filtered('l10n_mx_edi_cfdi'):
            supplier_rfc = inv.l10n_mx_edi_cfdi_supplier_rfc
            customer_rfc = inv.l10n_mx_edi_cfdi_customer_rfc
            total = float_repr(inv.l10n_mx_edi_cfdi_amount,
                               precision_digits=inv.currency_id.decimal_places)
            uuid = inv.l10n_mx_edi_cfdi_uuid
            params = '?re=%s&amp;rr=%s&amp;tt=%s&amp;id=%s' % (
                tools.html_escape(tools.html_escape(supplier_rfc or '')),
                tools.html_escape(tools.html_escape(customer_rfc or '')),
                total or 0.0, uuid or '')
            soap_env = template.format(data=params)
            try:
                soap_xml = requests.post(url, data=soap_env,
                                         headers=headers, timeout=20)
                response = fromstring(soap_xml.text)
                status = response.xpath(
                    '//a:Estado', namespaces=namespace)
            except Exception as e:
                inv.l10n_mx_edi_log_error(str(e))
                continue
            inv.l10n_mx_edi_sat_status = CFDI_SAT_QR_STATE.get(
                status[0] if status else '', 'none')
    
    def l10n_mx_edi_request_cancellation(self):
        if self.filtered(lambda payr: payr.state not in ['draft', 'done']):
            raise UserError(_(
                'Payroll must be in draft or open state in order to be '
                'cancelled.'))
        #if self.filtered(lambda inv: inv.journal_id.restrict_mode_hash_table):
        #    raise UserError(_(
        #        'You cannot modify a posted entry of this journal.\nFirst you '
        #        'should set the journal to allow cancelling entries.'))
        self.l10n_mx_edi_update_sat_status()
        payrolls = self.filtered(lambda payr:
                                 payr.l10n_mx_edi_sat_status != 'cancelled')
        payrolls._l10n_mx_edi_cancel()
    
    def _l10n_mx_edi_cancel(self):
        '''Call the cancel service with records that can be signed.
        '''
        records = self.search([
            ('l10n_mx_edi_pac_status', 'in', ['to_sign', 'signed', 'to_cancel', 'retry']),
            ('id', 'in', self.ids)])
        for record in records:
            if record.l10n_mx_edi_pac_status in ['to_sign', 'retry']:
                record.l10n_mx_edi_pac_status = False
                record.message_post(body=_('The cancel service has been called with success'))
            else:
                record.l10n_mx_edi_pac_status = 'to_cancel'
        records = self.search([
            ('l10n_mx_edi_pac_status', '=', 'to_cancel'),
            ('id', 'in', self.ids)])
        records._l10n_mx_edi_call_service('cancel')
    
    def l10n_mx_edi_update_pac_status(self):
        '''Synchronize both systems: Odoo & PAC if the invoices need to be signed or cancelled.
        '''
        for record in self:
            if record.l10n_mx_edi_pac_status in ('to_sign', 'retry'):
                record.edi_retry()
            elif record.l10n_mx_edi_pac_status == 'to_cancel':
                record._l10n_mx_edi_cancel()
                
    def send_nomina(self):
        self.ensure_one()
        template = self.env.ref('nomina_cfdi_ee.email_template_payroll', False)
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
            
        ctx = dict()
        ctx.update({
            'default_model': 'hr.payslip',
            'default_res_id': self.id,
            'default_use_template': bool(template),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
        })
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }
        
    @api.multi
    def action_payslip_cancel(self):
        _logger.info("---> FONG: Entro al metodo de Cancelar Nomina")
        if self.filtered(lambda slip: slip.state == 'done'):
            self.l10n_mx_edi_request_cancellation()
        self.filtered(lambda inv: inv.state != 'cancel').action_cancel()
        
        return self.write({'state': 'cancel'})
    
    
    
    @api.multi
    def action_cancel(self):
        moves = self.env['account.move']
        for inv in self:
            if inv.move_id:
                moves += inv.move_id
            #unreconcile all journal items of the invoice, since the cancellation will unlink them anyway
            inv.move_id.line_ids.filtered(lambda x: x.account_id.reconcile).remove_move_reconcile()

        # First, set the invoices as cancelled and detach the move ids
        self.write({'state': 'cancel', 'move_id': False})
        if moves:
            # second, invalidate the move(s)
            moves.button_cancel()
            # delete the move this invoice was pointing to
            # Note that the corresponding move_lines and move_reconciles
            # will be automatically deleted too
            moves.unlink()
        return True
    
class HrPayslipMail(models.Model):
    _name = "hr.payslip.mail"
    _inherit = ['mail.thread']
    _description = "Nomina Mail"
   
    payslip_id = fields.Many2one('hr.payslip', string='Nomina')
    name = fields.Char(related='payslip_id.name')
    #xml_nomina_link = fields.Char(related='payslip_id.xml_nomina_link')
    employee_id = fields.Many2one(related='payslip_id.employee_id')
    company_id = fields.Many2one(related='payslip_id.company_id')
    
"""
class MailTemplate(models.Model):
    "Templates for sending email"
    _inherit = 'mail.template'
    
    @api.model
    def _get_file(self, url):
        url = url.encode('utf8')
        filename, headers = urllib.urlretrieve(url)
        fn, file_extension = os.path.splitext(filename)
        return  filename, file_extension.replace('.', '')

    def generate_email(self, res_ids, fields=None):
        results = super(MailTemplate, self).generate_email(res_ids, fields=fields)
        
        if isinstance(res_ids, (int)):
            res_ids = [res_ids]
        res_ids_to_templates = super(MailTemplate, self).get_email_template(res_ids)

        # templates: res_id -> template; template -> res_ids
        templates_to_res_ids = {}
        for res_id, template in res_ids_to_templates.items():
            templates_to_res_ids.setdefault(template, []).append(res_id)
        
        template_id = self.env.ref('nomina_cfdi_ee.email_template_payroll')
        for template, template_res_ids in templates_to_res_ids.items():
            if template.id  == template_id.id:
                for res_id in template_res_ids:
                    payment = self.env[template.model].browse(res_id)
                    if payment.xml_nomina_link:
                        attachments =  results[res_id]['attachments'] or []
                        names = payment.xml_nomina_link.split('/')
                        fn = names[len(names) - 1]
                        data = open(payment.xml_nomina_link, 'rb').read()
                        attachments.append((fn, base64.b64encode(data)))
                        results[res_id]['attachments'] = attachments
        return results
"""

"""
    @api.model
    def to_json(self):
        payslip_total_TOP = 0
        payslip_total_TDED = 0
        payslip_total_PERG = 0
        payslip_total_PERE = 0
        payslip_total_SEIN = 0
        payslip_total_JPRE = 0
        antiguedad = 1y
        if self.contract_id.date_end and self.contract_id.date_start:
            antiguedad = int((self.contract_id.date_end - self.contract_id.date_start + timedelta(days=1)).days/7)
        elif self.date_to and self.contract_id.date_start:
            antiguedad = int((self.date_to - self.contract_id.date_start + timedelta(days=1)).days/7)

#**********  Percepciones ************
        total_percepciones_lines = self.env['hr.payslip.line'].search(['|',('category_id.code','=','ALW'),('code','=','P001'),('category_id.code','=','ALW3'),('slip_id','=',self.id)])
        percepciones_grabadas_lines = self.env['hr.payslip.line'].search(['|',('category_id.code','=','ALW'),('code','=','P001'),('slip_id','=',self.id)])
        lineas_de_percepcion = []
        tipo_percepcion_dict = dict(self.env['hr.salary.rule']._fields.get('tipo_percepcion').selection)
        if percepciones_grabadas_lines:
            for line in percepciones_grabadas_lines:
                if line.salary_rule_id.tipo_percepcion != '022' and line.salary_rule_id.tipo_percepcion != '023' and line.salary_rule_id.tipo_percepcion != '025' and line.salary_rule_id.tipo_percepcion !='039' and line.salary_rule_id.tipo_percepcion !='044':
                    payslip_total_PERG += round(line.total,2)
                lineas_de_percepcion.append({'TipoPercepcion': line.salary_rule_id.tipo_percepcion,
                'Clave': line.code,
                'Concepto': tipo_percepcion_dict.get(line.salary_rule_id.tipo_percepcion),
                'ImporteGravado': line.total,
                'ImporteExento': '0'})
                if line.salary_rule_id.tipo_percepcion == '022' or line.salary_rule_id.tipo_percepcion == '023' or line.salary_rule_id.tipo_percepcion == '025':
                    payslip_total_SEIN += round(line.total,2)
                if line.salary_rule_id.tipo_percepcion =='039' or line.salary_rule_id.tipo_percepcion =='044':
                    payslip_total_JPRE += round(line.total,2)

        percepciones_excentas_lines = self.env['hr.payslip.line'].search([('category_id.code','=','ALW2'),('slip_id','=',self.id)])
        lineas_de_percepcion_exentas = []
        if percepciones_excentas_lines:
            for line in percepciones_excentas_lines:
                parte_exenta = 0
                parte_gravada = 0

                #fondo ahorro
                if line.salary_rule_id.tipo_percepcion == '005':
                    if line.total > self.contract_id.tablas_cfdi_id.ex_fondo_ahorro:
                        parte_gravada = line.total - self.contract_id.tablas_cfdi_id.ex_fondo_ahorro
                        parte_exenta = self.contract_id.tablas_cfdi_id.ex_fondo_ahorro
                    else:
                        parte_exenta = line.total
                        parte_gravada = 0

                #prima dominical
                if line.salary_rule_id.tipo_percepcion == '020':
                    if line.total > self.contract_id.tablas_cfdi_id.ex_prima_dominical:
                        parte_gravada = line.total - self.contract_id.tablas_cfdi_id.ex_prima_dominical
                        parte_exenta = self.contract_id.tablas_cfdi_id.ex_prima_dominical
                    else:
                        parte_exenta = line.total
                        parte_gravada = 0

                #vale de despensa
                if  line.salary_rule_id.tipo_percepcion == '029':
                    if line.total > self.contract_id.tablas_cfdi_id.ex_vale_despensa:
                        parte_gravada = line.total - self.contract_id.tablas_cfdi_id.ex_vale_despensa
                        parte_exenta = self.contract_id.tablas_cfdi_id.ex_vale_despensa
                    else:
                        parte_exenta = line.total
                        parte_gravada = 0

                #aguinaldo
                if line.salary_rule_id.tipo_percepcion == '002':
                    if line.total > self.contract_id.tablas_cfdi_id.ex_aguinaldo:
                        parte_gravada = line.total - self.contract_id.tablas_cfdi_id.ex_aguinaldo
                        parte_exenta = self.contract_id.tablas_cfdi_id.ex_aguinaldo
                    else:
                        parte_exenta = line.total
                        parte_gravada = 0

                #reparto de utlidades
                if line.salary_rule_id.tipo_percepcion == '003':
                    if line.total > self.contract_id.tablas_cfdi_id.ex_ptu:
                        parte_gravada = line.total - self.contract_id.tablas_cfdi_id.ex_ptu
                        parte_exenta = self.contract_id.tablas_cfdi_id.ex_ptu
                    else:
                        parte_exenta = line.total
                        parte_gravada = 0

                #prima vacacional diario
                if line.salary_rule_id.tipo_percepcion == '021': #and line.salary_rule_id.sequence == 120:
                    antiguedad_anos = self.contract_id.antiguedad_anos
                    dias_vacaciones = 0
                    if self.contract_id.tablas_cfdi_id:
                        line2 = self.contract_id.env['tablas.antiguedades.line'].search([('form_id','=',self.contract_id.tablas_cfdi_id.id),('antiguedad','<=',antiguedad_anos)],order='antiguedad desc',limit=1)
                        if line2:
                            dias_vacaciones = line2.vacaciones

                    dias_prima_vac = self.env['hr.payslip.worked_days'].search(['|',('payslip_id','=',self.id),('code','=','VAC')]) #l,imit=1
                    dias_vac = 0
                    if dias_prima_vac:
                        _logger.info('si hay dias vacaciones..')
                        for dias_vac_line in dias_prima_vac:
                            dias_vac = dias_vac_line.number_of_days

                    monto_max = self.contract_id.tablas_cfdi_id.ex_prima_vacacional / dias_vacaciones * dias_vac
                    if line.total > monto_max:
                        parte_gravada = line.total - monto_max
                        parte_exenta = monto_max
                    else:
                        parte_exenta = line.total
                        parte_gravada = 0

                #prima vaccional completo
                #if line.salary_rule_id.tipo_percepcion == '021' and line.salary_rule_id.sequence == 122:
                #    _logger.info('entro a prima vacacional')
                #    if line.total > self.contract_id.tablas_cfdi_id.ex_prima_vacacional:
                #        parte_gravada = line.total - self.contract_id.tablas_cfdi_id.ex_prima_vacacional
                #        parte_exenta = self.contract_id.tablas_cfdi_id.ex_prima_vacacional
                #    else:
                #        parte_exenta = line.total
                #        parte_gravada = 0

                #viaticos
                if line.salary_rule_id.tipo_percepcion == '050':
                    #if line.total > self.contract_id.tablas_cfdi_id.ex_ptu:
                    #    parte_gravada = line.total - self.contract_id.tablas_cfdi_id.ex_ptu
                    #    parte_exenta = self.contract_id.tablas_cfdi_id.ex_ptu
                    #else:
                        parte_exenta = line.total
                        parte_gravada = 0

                #nomina de liquidacion / finiquito
                if line.salary_rule_id.tipo_percepcion == '022' or line.salary_rule_id.tipo_percepcion == '023' or line.salary_rule_id.tipo_percepcion == '025':
                #calculo total indemnizacion
                    total_indemnizacion = 0
                    percepciones_liquidacion = self.env['hr.payslip.line'].search([('category_id.code','=','ALW2'),('slip_id','=',self.id)])
                    if percepciones_liquidacion:
                        for line3 in percepciones_liquidacion:
                            if line3.salary_rule_id.tipo_percepcion == '022' or line3.salary_rule_id.tipo_percepcion == '023' or line3.salary_rule_id.tipo_percepcion == '025':
                                total_indemnizacion += line3.total
                    #indemnizacion
                    if line.salary_rule_id.tipo_percepcion == '025':
                        if total_indemnizacion > self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos:
                            parte_gravada = round(line.total - (self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos) * (line.total/total_indemnizacion),2)
                            parte_exenta = round(self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos * (line.total/total_indemnizacion),2)
                        else:
                            parte_exenta = line.total
                            parte_gravada = 0

                    #prima de antiguedad
                    if line.salary_rule_id.tipo_percepcion == '022':
                        if total_indemnizacion > self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos:
                            parte_gravada = round(line.total - (self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos) * (line.total/total_indemnizacion),2)
                            parte_exenta = round(self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos * (line.total/total_indemnizacion),2)
                        else:
                            parte_exenta = line.total
                            parte_gravada = 0

                    #pagos por separacion
                    if line.salary_rule_id.tipo_percepcion == '023':
                        if total_indemnizacion > self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos:
                            parte_gravada = round(line.total - (self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos) * (line.total/total_indemnizacion),2)
                            parte_exenta = round(self.contract_id.tablas_cfdi_id.ex_liquidacion * self.contract_id.antiguedad_anos * (line.total/total_indemnizacion),2)
                        else:
                            parte_exenta = line.total
                            parte_gravada = 0

                # obtener totales
                #if line.salary_rule_id.tipo_percepcion != '022' and line.salary_rule_id.tipo_percepcion != '023' and line.salary_rule_id.tipo_percepcion != '025' and line.salary_rule_id.tipo_percepcion !='039' and line.salary_rule_id.tipo_percepcion !='044':
                if line.salary_rule_id.tipo_percepcion !='039' and line.salary_rule_id.tipo_percepcion !='044':
                    payslip_total_PERE += round(parte_exenta,2)
                    payslip_total_PERG += round(parte_gravada,2)
                if line.salary_rule_id.tipo_percepcion == '022' or line.salary_rule_id.tipo_percepcion == '023' or line.salary_rule_id.tipo_percepcion == '025':
                    payslip_total_SEIN += round(line.total,2)
                if line.salary_rule_id.tipo_percepcion =='039' or line.salary_rule_id.tipo_percepcion =='044':
                    payslip_total_JPRE += round(line.total,2)

                # horas extras
                if line.salary_rule_id.tipo_percepcion == '019':
                    percepciones_horas_extras = self.env['hr.payslip.worked_days'].search([('payslip_id','=',self.id)])
                    if percepciones_horas_extras:
                        _logger.info('si hay ..')
                        for ext_line in percepciones_horas_extras:
                            #_logger.info('codigo %s.....%s ', line.code, ext_line.code)
                            if line.code == ext_line.code:
                                if line.code == 'HEX1':
                                    tipo_hr = '03'
                                elif line.code == 'HEX2':
                                    tipo_hr = '01'
                                elif line.code == 'HEX3':
                                    tipo_hr = '02'
                                lineas_de_percepcion_exentas.append({'TipoPercepcion': line.salary_rule_id.tipo_percepcion,
                             'Clave': line.code,
                             'Concepto': tipo_percepcion_dict.get(line.salary_rule_id.tipo_percepcion),
                             'ImporteGravado': parte_gravada,
                             'ImporteExento': parte_exenta,
                             'Dias': ext_line.number_of_days,
                             'TipoHoras': tipo_hr,
                             'HorasExtra': ext_line.number_of_hours,
                             'ImportePagado': line.total})
                # Jubilaciones, pensiones o haberes de retiro en una exhibición
                #elif line.salary_rule_id.tipo_percepcion == '039':

                # Jubilaciones, pensiones o haberes de retiro en parcialidades
                #elif line.salary_rule_id.tipo_percepcion == '044':

                # Ingresos en acciones o títulos valor que representan bienes
                elif line.salary_rule_id.tipo_percepcion == '045':
                    lineas_de_percepcion_exentas.append({'TipoPercepcion': line.salary_rule_id.tipo_percepcion,
                   'Clave': line.code,
                   'Concepto': tipo_percepcion_dict.get(line.salary_rule_id.tipo_percepcion),
                   'ValorMercado': 56,
                   'PrecioAlOtorgarse': 48,
                   'ImporteGravado': parte_gravada,
                   'ImporteExento': parte_exenta})
                else:
                    lineas_de_percepcion_exentas.append({'TipoPercepcion': line.salary_rule_id.tipo_percepcion,
                   'Clave': line.code,
                   'Concepto': tipo_percepcion_dict.get(line.salary_rule_id.tipo_percepcion),
                   'ImporteGravado': parte_gravada,
                   'ImporteExento': parte_exenta})

        percepcion = {
               'Totalpercepcion': {
                        'TotalSeparacionIndemnizacion': payslip_total_SEIN,
                        'TotalJubilacionPensionRetiro': payslip_total_JPRE,
                        'TotalGravado': payslip_total_PERG,
                        'TotalExento': payslip_total_PERE,
                        'TotalSueldos': payslip_total_PERG + payslip_total_PERE - payslip_total_SEIN - payslip_total_JPRE,
               },
        }

        #************ SEPARACION / INDEMNIZACION   ************#
        if payslip_total_SEIN > 0:
            if payslip_total_PERG > self.contract_id.wage:
                ingreso_acumulable = self.contract_id.wage
            else:
                ingreso_acumulable = payslip_total_PERG
            if payslip_total_PERG - self.contract_id.wage < 0:
                ingreso_no_acumulable = 0
            else:
                ingreso_no_acumulable = payslip_total_PERG - self.contract_id.wage

            percepcion.update({
               'separacion': [{
                        'TotalPagado': payslip_total_SEIN,
                        'NumAñosServicio': self.contract_id.antiguedad_anos,
                        'UltimoSueldoMensOrd': self.contract_id.wage,
                        'IngresoAcumulable': ingreso_acumulable,
                        'IngresoNoAcumulable': ingreso_no_acumulable,
                }]
            })
            #percepcion.update({'SeparacionIndemnizacion': separacion})


        percepcion.update({'lineas_de_percepcion_grabadas': lineas_de_percepcion, 'no_per_grabadas': len(percepciones_grabadas_lines)})
        percepcion.update({'lineas_de_percepcion_excentas': lineas_de_percepcion_exentas, 'no_per_excentas': len(percepciones_excentas_lines)})
        request_params = {'percepciones': percepcion}

#****** OTROS PAGOS ******
        otrospagos_lines = self.env['hr.payslip.line'].search([('category_id.code','=','ALW3'),('slip_id','=',self.id)])
        tipo_otro_pago_dict = dict(self.env['hr.salary.rule']._fields.get('tipo_otro_pago').selection)
        auxiliar_lines = self.env['hr.payslip.line'].search([('category_id.code','=','AUX'),('slip_id','=',self.id)])
        #tipo_otro_pago_dict = dict(self.env['hr.salary.rule']._fields.get('tipo_otro_pago').selection)
        lineas_de_otros = []
        if otrospagos_lines:
            for line in otrospagos_lines:
                #_#logger.info('line total ...%s', line.total)
                if line.salary_rule_id.tipo_otro_pago == '002' and line.total > 0:
                    line2 = self.contract_id.env['tablas.subsidio.line'].search([('form_id','=',self.contract_id.tablas_cfdi_id.id),('lim_inf','<=',self.contract_id.wage)],order='lim_inf desc',limit=1)
                    self.subsidio_periodo = 0
                    #_logger.info('entro a este ..')
                    payslip_total_TOP += line.total
                    #if line2:
                    #    self.subsidio_periodo = (line2.s_mensual/self.imss_mes)*self.imss_dias
                    for aux in auxiliar_lines:
                        if aux.code == 'SUB':
                            self.subsidio_periodo = aux.total
                    _logger.info('subsidio aplicado %s importe excento %s', self.subsidio_periodo, line.total)
                    lineas_de_otros.append({'TipoOtrosPagos': line.salary_rule_id.tipo_otro_pago,
                    'Clave': line.code,
                    'Concepto': tipo_otro_pago_dict.get(line.salary_rule_id.tipo_otro_pago),
                    'ImporteGravado': '0',
                    'ImporteExento': line.total,
                    'SubsidioCausado': self.subsidio_periodo})
                else:
                    payslip_total_TOP += line.total
                    #_logger.info('entro al otro ..')
                    lineas_de_otros.append({'TipoOtrosPagos': line.salary_rule_id.tipo_otro_pago,
                        'Clave': line.code,
                        'Concepto': tipo_otro_pago_dict.get(line.salary_rule_id.tipo_otro_pago),
                        'ImporteGravado': '0',
                        'ImporteExento': line.total})
        otrospagos = {
            'otrospagos': {
                    'Totalotrospagos': payslip_total_TOP,
            },
        }
        otrospagos.update({'otros_pagos': lineas_de_otros, 'no_otros_pagos': len(otrospagos_lines)})
        request_params.update({'otros_pagos': otrospagos})

#********** DEDUCCIONES *********
        total_imp_ret = 0
        suma_deducciones = 0
        self.importe_isr = 0
        self.isr_periodo = 0
        no_deuducciones = 0 #len(self.deducciones_lines)
        self.deducciones_lines = self.env['hr.payslip.line'].search([('category_id.code','=','DED'),('slip_id','=',self.id)])
        #ded_impuestos_lines = self.env['hr.payslip.line'].search([('category_id.name','=','Deducciones'),('code','=','301'),('slip_id','=',self.id)],limit=1)
        tipo_deduccion_dict = dict(self.env['hr.salary.rule']._fields.get('tipo_deduccion').selection)
        #if ded_impuestos_lines:
        #   total_imp_ret = round(ded_impuestos_lines.total,2)
        lineas_deduccion = []
        if self.deducciones_lines:
            _logger.info('entro deduciones ...')
            #todas las deducciones excepto imss e isr
            for line in self.deducciones_lines:
                if line.salary_rule_id.tipo_deduccion != '001' and line.salary_rule_id.tipo_deduccion != '002':
                    #_logger.info('linea  ...')
                    no_deuducciones += 1
                    lineas_deduccion.append({'TipoDeduccion': line.salary_rule_id.tipo_deduccion,
                   'Clave': line.code,
                   'Concepto': tipo_deduccion_dict.get(line.salary_rule_id.tipo_deduccion),
                   'Importe': round(line.total,2)})
                    payslip_total_TDED += round(line.total,2)

            #todas las deducciones imss
            self.importe_imss = 0
            for line in self.deducciones_lines:
                if line.salary_rule_id.tipo_deduccion == '001':
                    #_logger.info('linea imss ...')
                    self.importe_imss += round(line.total,2)

            if self.importe_imss > 0:
                no_deuducciones += 1
                self.calculo_imss()
                lineas_deduccion.append({'TipoDeduccion': '001',
                  'Clave': '302',
                  'Concepto': 'Seguridad social',
                  'Importe': round(self.importe_imss,2)})
                payslip_total_TDED += round(self.importe_imss,2)

            #todas las deducciones isr
            for line in self.deducciones_lines:
                if line.salary_rule_id.tipo_deduccion == '002' and line.salary_rule_id.code == 'ISR':
                    self.isr_periodo = line.total 
                if line.salary_rule_id.tipo_deduccion == '002':
                    _logger.info('linea ISR ...')
                    self.importe_isr += round(line.total,2)

            if self.importe_isr > 0:
                no_deuducciones += 1
                lineas_deduccion.append({'TipoDeduccion': '002',
                  'Clave': '301',
                  'Concepto': 'ISR',
                  'Importe': round(self.importe_isr,2)})
                payslip_total_TDED += round(self.importe_isr,2)
            total_imp_ret = round(self.importe_isr,2)

        deduccion = {
            'TotalDeduccion': {
                    'TotalOtrasDeducciones': round(payslip_total_TDED - total_imp_ret,2),
                    'TotalImpuestosRetenidos': total_imp_ret,
            },
        }
        deduccion.update({'lineas_de_deduccion': lineas_deduccion, 'no_deuducciones': no_deuducciones})
        request_params.update({'deducciones': deduccion})

        #************ INCAPACIDADES  ************#
        incapacidades = self.env['hr.payslip.worked_days'].search([('payslip_id','=',self.id)])
        if incapacidades:
            for ext_line in incapacidades:
                if ext_line.code == 'INC_RT' or ext_line.code == 'INC_EG' or ext_line.code == 'INC_MAT':
                    _logger.info('codigo %s.... ', ext_line.code)
                    tipo_inc = ''
                    if ext_line.code == 'INC_RT':
                        tipo_inc = '01'
                    elif ext_line.code == 'INC_EG':
                        tipo_inc = '02'
                    elif ext_line.code == 'INC_MAT':
                        tipo_inc = '03'
                    incapacidad = {
                  'Incapacidad': {
                        'DiasIncapacidad': ext_line.number_of_days,
                        'TipoIncapacidad': tipo_inc,
                        'ImporteMonetario': 0,
                        },
                        }
                    request_params.update({'incapacidades': incapacidad})

        self.retencion_subsidio_pagado = self.isr_periodo - self.subsidio_periodo
        self.total_nomina = payslip_total_PERG + payslip_total_PERE + payslip_total_TOP - payslip_total_TDED
        self.subtotal =  payslip_total_PERG + payslip_total_PERE + payslip_total_TOP
        self.descuento = payslip_total_TDED

        if self.tipo_nomina == 'O':
            self.periodicdad = self.contract_id.periodicidad_pago
        else:
            self.periodicdad = '99'
        diaspagados = 0
        if self.struct_id.name == 'Reparto de utilidades':
            diaspagados = 365
        else:
            if self.date_to and self.date_from:
               diaspagados = (self.date_to - self.date_from + timedelta(days=1)).days
        regimen = 0
        contrato = 0
        if self.struct_id.name == 'Liquidación - indemnizacion/finiquito':
            regimen = '13'
            contrato = '99'
        else:
            regimen = self.employee_id.regimen
            contrato = self.employee_id.contrato

        request_params.update({
                'factura': {
                      'serie': self.company_id.serie_nomina,
                      'folio': self.number_folio,
                      'metodo_pago': self.methodo_pago,
                      'forma_pago': self.forma_pago,
                      'tipocomprobante': self.tipo_comprobante,
                      'moneda': 'MXN',
                      'tipodecambio': '1.0000',
                      'fecha_factura': self.fecha_factura and self.fecha_factura.strftime(DTF),
                      'LugarExpedicion': self.company_id.zip,
                      'RegimenFiscal': self.company_id.regimen_fiscal,
                      'subtotal': self.subtotal,
                      'descuento': self.descuento,
                      'total': self.total_nomina,
                },
                'emisor': {
                      'rfc': self.company_id.rfc,
                      'api_key': self.company_id.proveedor_timbrado,
                      'modo_prueba': self.company_id.modo_prueba,
                      'nombre_fiscal': self.company_id.nombre_fiscal,
                      'telefono_sms': self.company_id.telefono_sms,
                },
                'receptor': {
                      'rfc': self.employee_id.rfc,
                      'nombre': self.employee_id.name,
                      'uso_cfdi': self.uso_cfdi,
                },
                'conceptos': {
                      'cantidad': '1.0',
                      'ClaveUnidad': 'ACT',
                      'ClaveProdServ': '84111505',
                      'descripcion': 'Pago de nómina',
                      'valorunitario': self.subtotal,
                      'importe':  self.subtotal,
                      'descuento': self.descuento,
                },
                'nomina12': {
                      'TipoNomina': self.tipo_nomina,
                      'FechaPago': self.fecha_pago and self.fecha_pago.strftime(DF),
                      'FechaInicialPago': self.date_from and self.date_from.strftime(DF),
                      'FechaFinalPago': self.date_to and self.date_to.strftime(DF),
                      'NumDiasPagados': diaspagados,
                      'TotalPercepciones': payslip_total_PERG + payslip_total_PERE,
                      'TotalDeducciones': self.descuento,
                      'TotalOtrosPagos': payslip_total_TOP,
                },
                'nomina12Emisor': {
                      'RegistroPatronal': self.employee_id.registro_patronal,
                      'RfcPatronOrigen': self.company_id.rfc,
                },
                'nomina12Receptor': {
                      'ClaveEntFed': self.employee_id.estado.code,
                      'Curp': self.employee_id.curp,
                      'NumEmpleado': self.employee_id.no_empleado,
                      'PeriodicidadPago': self.periodicdad, #self.contract_id.periodicidad_pago,
                      'TipoContrato': contrato,
                      'TipoRegimen': regimen,
                      'TipoJornada': self.employee_id.jornada,
                      'Antiguedad': 'P' + str(antiguedad) + 'W',
                      'Banco': self.employee_id.banco.c_banco,
                      'CuentaBancaria': self.employee_id.no_cuenta,
                      'FechaInicioRelLaboral': self.contract_id.date_start and self.contract_id.date_start.strftime(DF),
                      'NumSeguridadSocial': self.employee_id.segurosocial,
                      'Puesto': self.employee_id.job_id.name,
                      'Departamento': self.employee_id.department_id.name,
                      'RiesgoPuesto': self.contract_id.riesgo_puesto,
                      'SalarioBaseCotApor': self.contract_id.sueldo_diario_integrado,
                      'SalarioDiarioIntegrado': self.contract_id.sueldo_diario_integrado,
                },
		})

#****** CERTIFICADOS *******
        if not self.company_id.archivo_cer:
            raise UserError(_('Archivo .cer path is missing.'))
        if not self.company_id.archivo_key:
            raise UserError(_('Archivo .key path is missing.'))
        archivo_cer = self.company_id.archivo_cer
        archivo_key = self.company_id.archivo_key
        request_params.update({
                'certificados': {
                      'archivo_cer': archivo_cer.decode("utf-8"),
                      'archivo_key': archivo_key.decode("utf-8"),
                      'contrasena': self.company_id.contrasena,
                }})
        return request_params
        
    def action_cfdi_nomina_generate(self):
        for payslip in self:
            if payslip.fecha_factura == False:
                payslip.fecha_factura= datetime.datetime.now()
                payslip.write({'fecha_factura': payslip.fecha_factura})
            if payslip.estado_factura == 'factura_correcta':
                raise UserError(_('Error para timbrar factura, Factura ya generada.'))
            if payslip.estado_factura == 'factura_cancelada':
                raise UserError(_('Error para timbrar factura, Factura ya generada y cancelada.'))

            values = payslip.to_json()
            #  print json.dumps(values, indent=4, sort_keys=True)
            if payslip.company_id.proveedor_timbrado == 'multifactura':
                url = '%s' % ('http://facturacion.itadmin.com.mx/api/nomina')
            elif invoice.company_id.proveedor_timbrado == 'multifactura2':
                url = '%s' % ('http://facturacion2.itadmin.com.mx/api/nomina')
            elif invoice.company_id.proveedor_timbrado == 'multifactura3':
                url = '%s' % ('http://facturacion3.itadmin.com.mx/api/nomina')
            elif payslip.company_id.proveedor_timbrado == 'gecoerp':
                if self.company_id.modo_prueba:
                    url = '%s' % ('https://ws.gecoerp.com/itadmin/pruebas/nomina/?handler=OdooHandler33')
                else:
                    url = '%s' % ('https://itadmin.gecoerp.com/nomina/?handler=OdooHandler33')

            response = requests.post(url,auth=None,verify=False, data=json.dumps(values),headers={"Content-type": "application/json"})

            _logger.info('something ... %s', response.text)
            json_response = response.json()
            xml_file_link = False
            estado_factura = json_response['estado_factura']
            if estado_factura == 'problemas_factura':
                raise UserError(_(json_response['problemas_message']))
            # Receive and stroe XML 
            if json_response.get('factura_xml'):
                xml_file_link = payslip.company_id.factura_dir + '/' + payslip.name.replace('/', '_') + '.xml'
                xml_file = open(xml_file_link, 'w')
                xml_payment = base64.b64decode(json_response['factura_xml'])
                xml_file.write(xml_payment.decode("utf-8"))
                xml_file.close()
                payslip._set_data_from_xml(xml_payment)
                    
                xml_file_name = payslip.name.replace('/', '_') + '.xml'
                self.env['ir.attachment'].sudo().create(
                                            {
                                                'name': xml_file_name,
                                                'datas': json_response['factura_xml'],
                                                'datas_fname': xml_file_name,
                                                'res_model': self._name,
                                                'res_id': payslip.id,
                                                'type': 'binary'
                                            })	
                report = self.env['ir.actions.report']._get_report_from_name('nomina_cfdi_ee.report_payslip')
                report_data = report.render_qweb_pdf([payslip.id])[0]
                pdf_file_name = payslip.name.replace('/', '_') + '.pdf'
                self.env['ir.attachment'].sudo().create(
                                            {
                                                'name': pdf_file_name,
                                                'datas': base64.b64encode(report_data),
                                                'datas_fname': pdf_file_name,
                                                'res_model': self._name,
                                                'res_id': payslip.id,
                                                'type': 'binary'
                                            })

            payslip.write({'estado_factura': estado_factura,
                    'xml_nomina_link': xml_file_link,
                    'nomina_cfdi': True})

    def _set_data_from_xml(self, xml_invoice):
        if not xml_invoice:
            return None
        NSMAP = {
                 'xsi':'http://www.w3.org/2001/XMLSchema-instance',
                 'cfdi':'http://www.sat.gob.mx/cfd/3', 
                 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
                 }

        xml_data = etree.fromstring(xml_invoice)
        Emisor = xml_data.find('cfdi:Emisor', NSMAP)
        RegimenFiscal = Emisor.find('cfdi:RegimenFiscal', NSMAP)
        Complemento = xml_data.find('cfdi:Complemento', NSMAP)
        TimbreFiscalDigital = Complemento.find('tfd:TimbreFiscalDigital', NSMAP)
        
        self.rfc_emisor = Emisor.attrib['Rfc']
        self.name_emisor = Emisor.attrib['Nombre']
        self.tipocambio = xml_data.attrib['TipoCambio']
        #  self.tipo_comprobante = xml_data.attrib['TipoDeComprobante']
        self.moneda = xml_data.attrib['Moneda']
        self.numero_cetificado = xml_data.attrib['NoCertificado']
        self.cetificaso_sat = TimbreFiscalDigital.attrib['NoCertificadoSAT']
        self.fecha_certificacion = TimbreFiscalDigital.attrib['FechaTimbrado']
        self.selo_digital_cdfi = TimbreFiscalDigital.attrib['SelloCFD']
        self.selo_sat = TimbreFiscalDigital.attrib['SelloSAT']
        self.folio_fiscal = TimbreFiscalDigital.attrib['UUID']
        self.folio = xml_data.attrib['Folio']
        self.serie_emisor = xml_data.attrib['Serie']
        self.invoice_datetime = xml_data.attrib['Fecha']
        self.version = TimbreFiscalDigital.attrib['Version']
        self.cadena_origenal = '||%s|%s|%s|%s|%s||' % (self.version, self.folio_fiscal, self.fecha_certificacion, 
                                                         self.selo_digital_cdfi, self.cetificaso_sat)
        
        options = {'width': 275 * mm, 'height': 275 * mm}
        amount_str = str(self.total_nomina).split('.')
        #print 'amount_str, ', amount_str
        qr_value = '?re=%s&rr=%s&tt=%s.%s&id=%s' % (self.company_id.rfc, 
                                                 self.employee_id.rfc,
                                                 amount_str[0].zfill(10),
                                                 amount_str[1].ljust(6, '0'),
                                                 self.folio_fiscal
                                                 )
        self.qr_value = qr_value
        ret_val = createBarcodeDrawing('QR', value=qr_value, **options)
        self.qrcode_image = base64.encodestring(ret_val.asString('jpg'))

    def action_cfdi_cancel(self):
        for payslip in self:
            if payslip.nomina_cfdi:
                if payslip.estado_factura == 'factura_cancelada':
                    pass
                    # raise UserError(_('La factura ya fue cancelada, no puede volver a cancelarse.'))
                if not payslip.company_id.archivo_cer:
                    raise UserError(_('Falta la ruta del archivo .cer'))
                if not payslip.company_id.archivo_key:
                    raise UserError(_('Falta la ruta del archivo .key'))
                archivo_cer = payslip.company_id.archivo_cer
                archivo_key = payslip.company_id.archivo_key
                archivo_xml_link = payslip.company_id.factura_dir + '/' + payslip.folio_fiscal + '.xml'
                with open(archivo_xml_link, 'rb') as cf:
                     archivo_xml = base64.b64encode(cf.read())
                values = {
                          'rfc': payslip.company_id.rfc,
                          'api_key': payslip.company_id.proveedor_timbrado,
                          'uuid': self.folio_fiscal,
                          'folio': self.folio,
                          'serie_factura': payslip.company_id.serie_nomina,
                          'modo_prueba': payslip.company_id.modo_prueba,
                            'certificados': {
                                  'archivo_cer': archivo_cer.decode("utf-8"),
                                  'archivo_key': archivo_key.decode("utf-8"),
                                  'contrasena': payslip.company_id.contrasena,
                            },
                          'xml': archivo_xml.decode("utf-8"),
                          }
                if self.company_id.proveedor_timbrado == 'multifactura':
                    url = '%s' % ('http://facturacion.itadmin.com.mx/api/refund')
                elif self.company_id.proveedor_timbrado == 'multifactura2':
                    url = '%s' % ('http://facturacion2.itadmin.com.mx/api/refund')
                elif self.company_id.proveedor_timbrado == 'multifactura3':
                    url = '%s' % ('http://facturacion3.itadmin.com.mx/api/refund')
                elif self.company_id.proveedor_timbrado == 'gecoerp':
                    if self.company_id.modo_prueba:
                        url = '%s' % ('https://ws.gecoerp.com/itadmin/pruebas/refund/?handler=OdooHandler33')
                        #url = '%s' % ('https://itadmin.gecoerp.com/refund/?handler=OdooHandler33')
                    else:
                        url = '%s' % ('https://itadmin.gecoerp.com/refund/?handler=OdooHandler33')
                response = requests.post(url , 
                                         auth=None,verify=False, data=json.dumps(values), 
                                         headers={"Content-type": "application/json"})
    
                #print 'Response: ', response.status_code
                json_response = response.json()
                #_logger.info('log de la exception ... %s', response.text)

                if json_response['estado_factura'] == 'problemas_factura':
                    raise UserError(_(json_response['problemas_message']))
                elif json_response.get('factura_xml', False):
                    if payslip.number:
                        xml_file_link = payslip.company_id.factura_dir + '/CANCEL_' + payslip.number.replace('/', '_') + '.xml'
                    else:
                        xml_file_link = payslip.company_id.factura_dir + '/CANCEL_' + self.folio_fiscal + '.xml'
                    xml_file = open(xml_file_link, 'w')
                    xml_invoice = base64.b64decode(json_response['factura_xml'])
                    xml_file.write(xml_invoice.decode("utf-8"))
                    xml_file.close()
                    if payslip.number:
                        file_name = payslip.number.replace('/', '_') + '.xml'
                    else:
                        file_name = self.folio_fiscal + '.xml'
                    self.env['ir.attachment'].sudo().create(
                                                {
                                                    'name': file_name,
                                                    'datas': json_response['factura_xml'],
                                                    'datas_fname': file_name,
                                                    'res_model': self._name,
                                                    'res_id': payslip.id,
                                                    'type': 'binary'
                                                })
                payslip.write({'estado_factura': json_response['estado_factura']})

    

"""