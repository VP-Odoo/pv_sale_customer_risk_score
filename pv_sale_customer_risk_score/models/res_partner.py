# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Snapshot fields shown on the Risk tab
    risk_credit_util_pct = fields.Float(
        string="Credit Utilization %",
        compute="_compute_risk_snapshot",
        store=False,
        digits=(16, 2),
    )
    risk_overdue_ratio = fields.Float(
        string="Overdue Ratio",
        compute="_compute_risk_snapshot",
        store=False,
        digits=(16, 4),
    )
    risk_orders_90d = fields.Integer(
        string="Orders in Window",
        compute="_compute_risk_snapshot",
        store=False,
    )
    risk_activity_window_days = fields.Integer(
        string="Activity Window (Days)",
        compute="_compute_risk_snapshot",
        store=False,
    )
    risk_score = fields.Integer(
        string="Risk Score",
        compute="_compute_risk_snapshot",
        store=False,
    )
    risk_level = fields.Selection(
        [
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
        ],
        string="Risk Level",
        compute="_compute_risk_snapshot",
        store=False,
    )
    risk_last_recomputed = fields.Datetime(
        string="Risk Last Recomputed",
        compute="_compute_risk_snapshot",
        store=False,
        readonly=True,
    )

    # ------------------------------
    # Company configuration helpers
    # ------------------------------
    def _get_activity_window_days_for_company(self, company):
        ICP = self.env['ir.config_parameter'].sudo().with_company(company)
        val = ICP.get_param('pv_sale_customer_risk.window_days', default='120')
        try:
            return int(val)
        except Exception:
            return 120

    def _get_thresholds_for_company(self, company):
        ICP = self.env['ir.config_parameter'].sudo().with_company(company)
        low = ICP.get_param('pv_sale_customer_risk.threshold_low', default='30')
        high = ICP.get_param('pv_sale_customer_risk.threshold_high', default='70')
        try:
            return float(low), float(high)
        except Exception:
            return 30.0, 70.0

    def _get_partner_credit_limit(self, company):
        partner = self.commercial_partner_id.with_company(company)
        ICP = self.env['ir.config_parameter'].sudo().with_company(company)

        # Try common fields first; fall back to parameter
        if 'credit_limit' in partner._fields:
            return float(partner.credit_limit or 0.0)
        if 'property_credit_limit' in partner._fields:
            return float(partner.property_credit_limit or 0.0)

        default_limit = ICP.get_param('pv_sale_customer_risk.default_credit_limit', default='0')
        try:
            return float(default_limit)
        except Exception:
            return 0.0

    # ------------------------------
    # Compute everything in one pass
    # ------------------------------
    @api.depends(
        'company_id',
        'child_ids',
        'invoice_ids.amount_residual',
        'invoice_ids.invoice_date_due',
        'invoice_ids.state',
        'invoice_ids.move_type',
        'sale_order_ids.state',
        'sale_order_ids.date_order',
    )
    def _compute_risk_snapshot(self):
        Move = self.env['account.move'].sudo()
        Sale = self.env['sale.order'].sudo()

        for partner in self:
            company = partner.company_id or self.env.company
            cp = partner.commercial_partner_id
            today = fields.Date.context_today(partner)

            # Config
            window_days = partner._get_activity_window_days_for_company(company)
            threshold_low, threshold_high = partner._get_thresholds_for_company(company)
            date_from_dt = fields.Datetime.now() - timedelta(days=window_days)

            # -------- Open Invoices (denominator) --------
            inv_domain = [
                ('company_id', '=', company.id),
                ('partner_id.commercial_partner_id', '=', cp.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('amount_residual', '>', 0),
            ]
            inv_moves = Move.with_company(company).search(inv_domain)
            total_open_invoices = sum(m.amount_residual for m in inv_moves) or 0.0

            # Overdue part of invoices (numerator base)
            overdue_invoices_amount = sum(
                m.amount_residual
                for m in inv_moves
                if m.invoice_date_due and m.invoice_date_due < today
            ) or 0.0

            # -------- Open Credit Notes (to subtract from numerator) --------
            # We take open (not fully reconciled) customer credit notes and sum their residuals
            cn_domain = [
                ('company_id', '=', company.id),
                ('partner_id.commercial_partner_id', '=', cp.id),
                ('move_type', '=', 'out_refund'),
                ('state', '=', 'posted'),
                ('amount_residual', '!=', 0),
            ]
            cn_moves = Move.with_company(company).search(cn_domain)
            # Use absolute to be robust to sign conventions
            open_credit_notes_total = sum(abs(m.amount_residual) for m in cn_moves) or 0.0

            # -------- Orders in window --------
            orders_in_window = Sale.with_company(company).search_count([
                ('company_id', '=', company.id),
                ('partner_id.commercial_partner_id', '=', cp.id),
                ('state', 'in', ('sale', 'done')),
                ('date_order', '>=', date_from_dt),
            ])

            # -------- Credit utilization & overdue ratio --------
            # Net exposure for utilization (open invoices minus open credit notes, not below zero)
            net_outstanding = max(0.0, total_open_invoices - open_credit_notes_total)

            credit_limit = partner._get_partner_credit_limit(company)
            credit_util_pct = (net_outstanding / credit_limit) * 100.0 if credit_limit else 0.0

            # Overdue Ratio
            # (overdue invoices - open credit notes) / total open invoices
            numerator = max(0.0, overdue_invoices_amount - open_credit_notes_total)
            overdue_ratio = (numerator / total_open_invoices) if total_open_invoices > 0 else 0.0

            # -------- Score --------
            score = 0
            # Credit utilization weight
            if credit_util_pct > 100:
                score += 60
            elif credit_util_pct > 80:
                score += 40
            elif credit_util_pct > 50:
                score += 20
            # Overdue weight
            if overdue_ratio > 0.20:
                score += 50
            elif overdue_ratio > 0.05:
                score += 20
            # Activity weight
            if orders_in_window >= 10:
                score += 20
            elif orders_in_window >= 5:
                score += 10

            level = 'low'
            if score >= threshold_high:
                level = 'high'
            elif score >= threshold_low:
                level = 'medium'

            # Assign (non-stored) values
            partner.risk_activity_window_days = window_days
            partner.risk_credit_util_pct = credit_util_pct
            partner.risk_overdue_ratio = overdue_ratio
            partner.risk_orders_90d = orders_in_window
            partner.risk_score = score
            partner.risk_level = level
            partner.risk_last_recomputed = fields.Datetime.now()

    # Button: Recompute now
    def action_recompute_risk(self):
        self.sudo()._compute_risk_snapshot()
        return True
