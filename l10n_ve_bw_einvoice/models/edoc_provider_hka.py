# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
"""Adaptador de The Factory HKA Venezuela.

Escrito contra la documentación pública del proveedor
(https://wiki.thefactoryhka.com.ve/doku.php?id=manual_de_integracion_venezuela):

- POST /api/Autenticacion  {usuario, clave} → {token, expiracion}; el token
  dura 12 h y viaja como "Authorization: Bearer <token>" en el resto.
- POST /api/Emision        {documentoElectronico: {...}} → resultado con el
  Nº de control SÍNCRONO (por eso _edoc_fetch no existe para HKA).
- POST /api/Anular         {serie, tipoDocumento, numeroDocumento,
  motivoAnulacion, fechaAnulacion, horaAnulacion}.

El wiki solo publica la URL del ambiente demo; la de producción la entrega el
proveedor con el contrato y se configura en la compañía. Todos los montos
viajan como STRINGS (así los tipa el JSON de ejemplo del wiki).
"""
import json
import re
from datetime import timedelta

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

DEMO_BASE_URL = "https://demoemisionv2.thefactoryhka.com.ve"
TIMEOUT = 60
# Se renueva el token un rato antes de su expiración real para no mandar una
# emisión con un token al borde de vencer.
TOKEN_MARGIN = timedelta(minutes=10)

# Tipos de documento según la respuesta de /api/Emision del wiki (la factura
# de ejemplo responde tipoDocumento "01"). ⚠️ Confirmar "02"/"03" contra el
# catálogo de campos que HKA entrega junto con las credenciales.
DOC_TYPES = {"factura": "01", "nota_debito": "02", "nota_credito": "03"}

# codigoImpuesto por alícuota: G general 16 %, R reducida 8 %, A adicional
# 31 %, E exento. ⚠️ Mismo caso: confirmar contra el catálogo de HKA.
TAX_CODES = {16.0: "G", 8.0: "R", 31.0: "A"}


class L10nVeEdocProviderHka(models.AbstractModel):
    _name = "l10n.ve.edoc.provider.hka"
    _inherit = "l10n.ve.edoc.provider"
    _description = "The Factory HKA (Venezuela)"

    # ------------------------------------------------------------------
    # Contrato l10n.ve.edoc.provider
    # ------------------------------------------------------------------
    def _edoc_send(self, move, vals):
        company = move.company_id
        payload = self._hka_payload(move, vals)
        data = self._hka_post(company, "/api/Emision", payload)
        resultado = data.get("resultado") or {}
        return {
            "external_id": resultado.get("numeroDocumento") or vals["numero"],
            "control_number": resultado.get("numeroControl") or None,
            "control_date": self._hka_parse_date(
                resultado.get("fechaAsignacionNumeroControl")
                or resultado.get("fechaAsignacion")),
        }

    def _edoc_fetch(self, move):
        raise UserError(_(
            "The Factory HKA asigna el Nº de control en la propia emisión y "
            "no expone un método de consulta. Si un envío quedó a medias, "
            "verifique el documento en el portal del proveedor antes de "
            "reintentar, para no emitirlo dos veces."))

    def _edoc_cancel(self, move, reason):
        company = move.company_id
        now = fields.Datetime.context_timestamp(move, fields.Datetime.now())
        payload = {
            "serie": company.l10n_ve_edoc_serie or "",
            "tipoDocumento": DOC_TYPES[move._l10n_ve_edoc_doc_type()],
            "numeroDocumento": move.name,
            "motivoAnulacion": reason,
            "fechaAnulacion": now.strftime("%d/%m/%Y"),
            "horaAnulacion": now.strftime("%H:%M:%S"),
        }
        self._hka_post(company, "/api/Anular", payload)
        return True

    def _edoc_test_connection(self):
        company = self.env.company
        data = self._hka_auth(company)
        return _(
            "Conexión correcta con The Factory HKA (%(ambiente)s). "
            "Token válido hasta %(vence)s (UTC).",
            ambiente=_("demo") if company.l10n_ve_edoc_test else _("producción"),
            vence=self._hka_parse_expiry(data.get("expiracion")),
        )

    # ------------------------------------------------------------------
    # HTTP y token
    # ------------------------------------------------------------------
    def _hka_base_url(self, company):
        """Demo mientras 'Ambiente de pruebas' esté marcado; así es imposible
        apuntar una prueba a producción por una URL mal copiada."""
        if company.l10n_ve_edoc_test:
            return DEMO_BASE_URL
        url = (company.l10n_ve_edoc_url or "").strip().rstrip("/")
        if not url:
            raise UserError(_(
                "Configura la URL de producción de The Factory HKA en los "
                "Ajustes de Contabilidad de %s (la entrega el proveedor con "
                "el contrato).", company.display_name))
        return url

    def _hka_auth(self, company):
        if not company.l10n_ve_edoc_user or not company.l10n_ve_edoc_password:
            raise UserError(_(
                "Configura usuario y clave de The Factory HKA en los Ajustes "
                "de Contabilidad de %s.", company.display_name))
        response = requests.post(
            self._hka_base_url(company) + "/api/Autenticacion",
            json={"usuario": company.l10n_ve_edoc_user,
                  "clave": company.l10n_ve_edoc_password},
            timeout=TIMEOUT)
        data = self._hka_parse(response)
        if not data.get("token"):
            raise UserError(_(
                "The Factory HKA no devolvió token: %s",
                data.get("mensaje") or _("sin mensaje")))
        return data

    def _hka_token(self, company, force=False):
        """Token cacheado por compañía en ir.config_parameter: dura 12 h y
        autenticarse en cada llamada sería una petición de más por factura."""
        icp = self.env["ir.config_parameter"].sudo()
        key = "l10n_ve_bw_einvoice.hka_token_%d" % company.id
        if not force:
            cached = icp.get_param(key)
            if cached:
                try:
                    value = json.loads(cached)
                    expiry = fields.Datetime.from_string(value["vence"])
                    if fields.Datetime.now() < expiry - TOKEN_MARGIN:
                        return value["token"]
                except (ValueError, KeyError, TypeError):
                    pass
        data = self._hka_auth(company)
        icp.set_param(key, json.dumps({
            "token": data["token"],
            "vence": fields.Datetime.to_string(
                self._hka_parse_expiry(data.get("expiracion"))),
        }))
        return data["token"]

    def _hka_post(self, company, path, payload):
        for attempt in (1, 2):
            token = self._hka_token(company, force=attempt == 2)
            response = requests.post(
                self._hka_base_url(company) + path, json=payload,
                headers={"Authorization": "Bearer %s" % token},
                timeout=TIMEOUT)
            # 401 con token cacheado = revocado antes de su expiración
            # (rotación de clave, reinicio del proveedor): se renueva UNA vez.
            if response.status_code == 401 and attempt == 1:
                continue
            return self._hka_parse(response)

    def _hka_parse(self, response):
        try:
            data = response.json()
        except ValueError:
            raise UserError(_(
                "The Factory HKA respondió HTTP %(status)s sin JSON: "
                "%(body)s",
                status=response.status_code, body=response.text[:500]))
        # El wiki tipa "codigo" como número en Autenticación y como string en
        # Emisión: se compara siempre como string.
        codigo = str(data.get("codigo", response.status_code))
        if codigo != "200":
            detalles = data.get("validaciones") or []
            raise UserError("The Factory HKA [%s]: %s%s" % (
                codigo,
                data.get("mensaje") or _("Error del proveedor"),
                ("\n- " + "\n- ".join(detalles)) if detalles else ""))
        return data

    # ------------------------------------------------------------------
    # Traducción dict neutro → dialecto HKA
    # ------------------------------------------------------------------
    def _hka_payload(self, move, vals):
        company = move.company_id
        fecha = self._hka_date(vals["fecha"])
        identificacion = {
            "tipoDocumento": DOC_TYPES[vals["tipo_documento"]],
            "numeroDocumento": vals["numero"],
            "fechaEmision": fecha,
            "horaEmision": vals.get("hora") or "",
            "moneda": vals["moneda"],
            "serie": company.l10n_ve_edoc_serie or "",
            "sucursal": company.l10n_ve_edoc_sucursal or "",
            # ⚠️ Valor legible a falta del catálogo público de tipoDeVenta;
            # ajustar cuando HKA entregue la tabla de valores admitidos.
            "tipoDeVenta": ("Contado" if vals.get("tipo_venta") == "contado"
                            else "Crédito"),
            # Idempotencia: identifica este intento de emisión ante HKA.
            "transaccionId": "ODOO-%d-%d" % (company.id, move.id),
        }
        afectado = vals.get("documento_afectado")
        if afectado:
            identificacion.update({
                "serieFacturaAfectada": company.l10n_ve_edoc_serie or "",
                "numeroFacturaAfectada": afectado["numero"],
                "fechaFacturaAfectada": self._hka_date(afectado["fecha"]),
                "montoFacturaAfectada": self._hka_amount(afectado["monto"]),
                "comentarioFacturaAfectada": afectado.get("comentario") or "",
            })
        buyer = vals["comprador"]
        comprador = {
            "tipoIdentificacion": buyer.get("tipo_identificacion") or "",
            "numeroIdentificacion": (buyer.get("numero_identificacion")
                                     or buyer["rif"]),
            "razonSocial": buyer["razon_social"],
            "direccion": buyer["domicilio"],
            "pais": "VE",
            "notificar": "Si" if buyer.get("correo") else "No",
            "telefono": [buyer["telefono"]] if buyer.get("telefono") else [],
            "correo": [buyer["correo"]] if buyer.get("correo") else [],
        }
        detalles = [{
            "numeroLinea": str(index),
            "codigoPLU": linea.get("codigo") or "",
            "descripcion": linea["descripcion"],
            "cantidad": self._hka_amount(linea["cantidad"]),
            "unidadMedida": linea.get("unidad") or "",
            "precioUnitario": self._hka_amount(linea["precio_unitario"]),
            "descuentoMonto": self._hka_amount(
                linea.get("descuento_monto", 0.0)),
            "precioItem": self._hka_amount(linea["base"]),
            "codigoImpuesto": self._hka_tax_code(linea),
            "tasaIVA": self._hka_amount(linea["alicuota"]),
            "valorIVA": self._hka_amount(linea.get("iva", 0.0)),
            "valorTotalItem": self._hka_amount(
                linea.get("total", linea["base"])),
        } for index, linea in enumerate(vals["lineas"], start=1)]
        totales = {
            "nroItems": str(vals.get("nro_items", len(vals["lineas"]))),
            "montoGravadoTotal": self._hka_amount(vals["total_base"]),
            "montoExentoTotal": self._hka_amount(vals["total_exento"]),
            "subtotal": self._hka_amount(
                vals.get("subtotal", vals["total_base"] + vals["total_exento"])),
            "totalIVA": self._hka_amount(vals["total_iva"]),
            "montoTotalConIVA": self._hka_amount(vals["total"]),
            "totalAPagar": self._hka_amount(vals["total"]),
            "impuestosSubtotal": self._hka_tax_subtotals(vals),
            "formasPago": self._hka_payments(vals, fecha),
        }
        encabezado = {
            "identificacionDocumento": identificacion,
            "comprador": comprador,
            "totales": totales,
        }
        bs = vals.get("totales_bs")
        if bs:
            encabezado["totalesOtraMoneda"] = {
                "moneda": bs["moneda"],
                "tipoCambio": self._hka_amount(bs["tipo_cambio"], digits=4),
                "montoGravadoTotal": self._hka_amount(bs["total_base"]),
                "montoExentoTotal": self._hka_amount(bs["total_exento"]),
                "subtotal": self._hka_amount(
                    bs["total_base"] + bs["total_exento"]),
                "totalIVA": self._hka_amount(bs["total_iva"]),
                "montoTotalConIVA": self._hka_amount(bs["total"]),
                "totalAPagar": self._hka_amount(bs["total"]),
            }
        return {"documentoElectronico": {
            "encabezado": self._hka_clean(encabezado),
            "detallesItems": [self._hka_clean(d) for d in detalles],
        }}

    def _hka_tax_code(self, linea):
        if linea["exento"]:
            return "E"
        return TAX_CODES.get(linea["alicuota"], "G")

    def _hka_tax_subtotals(self, vals):
        """impuestosSubtotal: una fila por código/alícuota, sumando bases e
        IVA de las líneas. El dict neutro trae alícuota por línea justo para
        poder reconstruir este desglose sin tocar lo fiscal."""
        groups = {}
        for linea in vals["lineas"]:
            code = self._hka_tax_code(linea)
            group = groups.setdefault(code, {
                "alicuota": 0.0 if linea["exento"] else linea["alicuota"],
                "base": 0.0, "iva": 0.0})
            group["base"] += linea["base"]
            group["iva"] += linea.get("iva", 0.0)
        return [{
            "codigoTotalImp": code,
            "alicuotaImp": self._hka_amount(group["alicuota"]),
            "baseImponibleImp": self._hka_amount(group["base"]),
            "valorTotalImp": self._hka_amount(group["iva"]),
        } for code, group in groups.items()]

    def _hka_payments(self, vals, fecha):
        formas = [{
            "descripcion": pago["descripcion"],
            "fecha": self._hka_date(pago["fecha"]),
            "monto": self._hka_amount(pago["monto"]),
            "moneda": pago.get("moneda") or vals["moneda"],
        } for pago in vals.get("formas_pago") or []]
        if not formas:
            # Sin cobros conciliados al emitir (lo normal): una sola forma de
            # pago por el total, rotulada con la condición de venta.
            formas = [{
                "descripcion": ("Contado"
                                if vals.get("tipo_venta") == "contado"
                                else "Crédito"),
                "fecha": fecha,
                "monto": self._hka_amount(vals["total"]),
                "moneda": vals["moneda"],
            }]
        return formas

    # ------------------------------------------------------------------
    # Formatos: montos string, fechas dd/mm/yyyy (como los ejemplos del wiki)
    # ------------------------------------------------------------------
    @staticmethod
    def _hka_amount(value, digits=2):
        return "%.*f" % (digits, value or 0.0)

    @staticmethod
    def _hka_date(value):
        return value.strftime("%d/%m/%Y") if value else ""

    @staticmethod
    def _hka_parse_date(value):
        match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", (value or "").strip())
        if not match:
            return None
        day, month, year = match.groups()
        return fields.Date.to_date("%s-%s-%s" % (year, month, day))

    @staticmethod
    def _hka_parse_expiry(value):
        """La expiración llega como "2022-09-24T02:53:54.6190734Z": ISO en UTC
        con SIETE decimales (formato .NET), que fromisoformat no traga; se
        recorta a segundos. Ilegible → se asume la vigencia documentada de
        12 h, menos margen no hace daño."""
        match = re.match(
            r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", value or "")
        if match:
            return fields.Datetime.from_string("%s %s" % match.groups())
        return fields.Datetime.now() + timedelta(hours=12)

    @classmethod
    def _hka_clean(cls, value):
        """Poda recursiva de campos vacíos: mejor no mandar la clave que
        mandar "" a un validador ajeno (y el JSON queda auditable en la
        bitácora sin ruido)."""
        if isinstance(value, dict):
            cleaned = {k: cls._hka_clean(v) for k, v in value.items()}
            return {k: v for k, v in cleaned.items()
                    if v not in ("", None, [], {})}
        if isinstance(value, list):
            return [cls._hka_clean(v) for v in value]
        return value
