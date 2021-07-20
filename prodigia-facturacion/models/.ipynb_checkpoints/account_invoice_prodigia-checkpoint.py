import base64
from itertools import groupby
import re
import logging
from datetime import datetime
from io import BytesIO

from lxml import etree
from lxml.objectify import fromstring
from suds.client import Client

from odoo import _, api, fields, models, tools
from odoo.tools.xml_utils import _check_with_xsd
from odoo.tools import DEFAULT_SERVER_TIME_FORMAT
from odoo.tools import float_round
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_repr

import logging
_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    @api.model
    def _l10n_mx_edi_prodigia_info(self, company_id, service_type):
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

    @api.multi
    def _l10n_mx_edi_prodigia_sign(self, pac_info):
        '''SIGN for Prodigia.
        '''
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        contract = pac_info['contract']
        test = pac_info['test']
        for inv in self:
            cfdi = inv.l10n_mx_edi_cfdi.decode('UTF-8')
            try:
                client = Client(url, timeout=20)
                if(test):
                    response = client.service.timbradoOdooPrueba(
                        contract, username, password, cfdi)
                else:
                    response = client.service.timbradoOdoo(
                        contract, username, password, cfdi)
            except Exception as e:
                inv.l10n_mx_edi_log_error(str(e))
                continue
            msg = getattr(response, 'mensaje', None)
            code = getattr(response, 'codigo', None)
            xml_signed = getattr(response, 'xml', None)
            inv._l10n_mx_edi_post_sign_process(xml_signed, code, msg)

    @api.multi
    def _l10n_mx_edi_prodigia_cancel(self, pac_info):
        '''CANCEL Prodigia.
        '''

        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        contract = pac_info['contract']
        test = pac_info['test']
        rfc_receptor = self.partner_id.vat
        if self:
            certificate_id = self[0].company_id.l10n_mx_edi_certificate_ids[0].sudo(
            )
        for inv in self:

            # uuids = [inv.l10n_mx_edi_cfdi_uuid]
            rfc_receptor = inv.partner_id
            rfc_rec = ""
            if rfc_receptor.vat is False:
                rfc_rec = "XAXX010101000"
            else:
                rfc_rec = rfc_receptor.vat

            uuids = [inv.l10n_mx_edi_cfdi_uuid+"|"+rfc_rec +
                     "|"+rfc_emisor.vat+"|" + str(inv.amount_total)]

            if not certificate_id:
                certificate_id = inv.l10n_mx_edi_cfdi_certificate_id.sudo()
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
                inv._l10n_mx_edi_post_cancel_process(cancelled, code, msg)
                continue
            try:
                client = Client(url, timeout=20)
                response = client.service.cancelar(
                    contract, username, password, rfc_emisor.vat, uuids, cer_pem, key_pem, key_password)
            except Exception as e:
                inv.l10n_mx_edi_log_error(str(e))
                continue
            code = getattr(response, 'codigo', None)
            cancelled = code in ('201', '202')
            msg = '' if cancelled else getattr(response, 'mensaje', None)
            code = '' if cancelled else code
            inv._l10n_mx_edi_post_cancel_process(cancelled, code, msg)

    @api.multi
    def _l10n_mx_edi_retry(self):
        '''Try to generate the cfdi attachment and then, sign it.
        '''
        _logger.info("############### _l10n_mx_edi_retry ####")
        #if self.env.context.get('not_sign'):
        if True:
            _logger.info("############### ENTRO PARA NO FIRMAR ####")
            return
        version = self.l10n_mx_edi_get_pac_version()
        for inv in self:
            cfdi_values = inv._l10n_mx_edi_create_cfdi()
            error = cfdi_values.pop('error', None)
            cfdi = cfdi_values.pop('cfdi', None)
            if error:
                # cfdi failed to be generated
                inv.l10n_mx_edi_pac_status = 'retry'
                inv.message_post(body=error, subtype='account.mt_invoice_validated')
                continue
            # cfdi has been successfully generated
            inv.l10n_mx_edi_pac_status = 'to_sign'
            filename = ('%s-%s-MX-Invoice-%s.xml' % (
                inv.journal_id.code, inv.number, version.replace('.', '-'))).replace('/', '')
            ctx = self.env.context.copy()
            ctx.pop('default_type', False)
            inv.l10n_mx_edi_cfdi_name = filename
            attachment_id = self.env['ir.attachment'].with_context(ctx).create({
                'name': filename,
                'res_id': inv.id,
                'res_model': inv._name,
                'datas': base64.encodestring(cfdi),
                'datas_fname': filename,
                'description': 'Mexican invoice',
                })
            inv.message_post(
                body=_('CFDI document generated (may be not signed)'),
                attachment_ids=[attachment_id.id],
                subtype='account.mt_invoice_validated')
            inv._l10n_mx_edi_sign()