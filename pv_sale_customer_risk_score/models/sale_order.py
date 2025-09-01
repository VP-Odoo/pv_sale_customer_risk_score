# pv_sale_customer_risk_score/models/sale_order.py
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import str2bool


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_risk_score = fields.Integer(
        string="Customer Risk Score",
        related="partner_id.commercial_partner_id.risk_score",
        readonly=True,
    )
    partner_risk_level = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string="Customer Risk Level",
        related="partner_id.commercial_partner_id.risk_level",
        readonly=True,
    )
    partner_risk_credit_util_pct = fields.Float(
        string="Credit Utilization %",
        related="partner_id.commercial_partner_id.risk_credit_util_pct",
        readonly=True,
    )
    partner_risk_overdue_ratio = fields.Float(
        string="Overdue Ratio",
        related="partner_id.commercial_partner_id.risk_overdue_ratio",
        readonly=True,
    )
    partner_risk_orders_90d = fields.Integer(
        string="Orders in Activity Window",
        related="partner_id.commercial_partner_id.risk_orders_90d",
        readonly=True,
    )

    def _pv_get_param_bool(self, key, default=False):
        company = self.company_id or self.env.company
        icp = self.env['ir.config_parameter'].sudo().with_company(company)
        val = icp.get_param(key, '1' if default else '0') or ('1' if default else '0')
        try:
            return bool(str2bool(val))
        except Exception:
            return bool(default)

    @api.onchange('partner_id')
    def _pv_onchange_partner_risk_warning(self):
        if not self.partner_id:
            return
        if not self._pv_get_param_bool('pv_sale_customer_risk.warn_on_quote', True):
            return
        level = self.partner_id.commercial_partner_id.risk_level
        if level in ('medium', 'high'):
            score = self.partner_id.commercial_partner_id.risk_score
            return {
                'warning': {
                    'title': _("Customer Risk"),
                    'message': _("This customer is %(level)s risk (score: %(score)s).",
                                level=level.title(), score=score)
                }
            }

    def action_confirm(self):
        if self._pv_get_param_bool('pv_sale_customer_risk.block_sale_on_high', False):
            if not self.env.user.has_group('sales_team.group_sale_manager'):
                blocked = self.filtered(lambda s: s.partner_id.commercial_partner_id.risk_level == 'high')
                if blocked:
                    partners = ", ".join(blocked.mapped('partner_id.commercial_partner_id.display_name')[:3])
                    more = "" if len(blocked) <= 3 else _(" (+%s more)", len(blocked) - 3)
                    raise UserError(
                        _("Confirmation blocked: customer risk is High for %s%s. "
                          "Ask a Sales Manager to confirm or adjust the risk in Contacts.",
                          partners, more)
                    )
        return super().action_confirm()
