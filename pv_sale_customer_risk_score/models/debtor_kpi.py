# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class PvDebtorKpi(models.Model):
    _name = "pv.debtor.kpi"
    _description = "Debtor KPI Snapshot"
    _order = "company_id, overdue_ratio desc, outstanding desc"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    commercial_partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, index=True
    )

    # Denominator for the ratio (open invoices only)
    outstanding = fields.Float(string="Outstanding (Invoices)", digits=(16, 2))
    # Open credit notes residual (for transparency in list/pivot)
    credit_open = fields.Float(string="Credit Open", digits=(16, 2))
    # Overdue invoices residual
    overdue = fields.Float(string="Overdue (Invoices)", digits=(16, 2))

    # Other KPIs
    credit_limit = fields.Float(string="Credit Limit", digits=(16, 2))
    credit_util_pct = fields.Float(string="Credit Util %", digits=(16, 2))
    overdue_ratio = fields.Float(string="Overdue Ratio", digits=(16, 4))
    orders_in_window = fields.Integer(string="Orders in Window")

    risk_score = fields.Integer(string="Risk Score")
    risk_level = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High")],
        string="Risk Level",
    )

    last_updated = fields.Datetime(string="Last Updated", default=fields.Datetime.now)

    _sql_constraints = [
        (
            "uniq_company_partner",
            "unique(company_id, commercial_partner_id)",
            "One KPI row per customer per company.",
        )
    ]

    # -------- Helpers reused from partner --------
    def _get_window_days_for_company(self, partner, company):
        return partner._get_activity_window_days_for_company(company)

    def _get_thresholds_for_company(self, partner, company):
        return partner._get_thresholds_for_company(company)

    def _get_credit_limit_for_partner(self, partner, company):
        return partner._get_partner_credit_limit(company)

    # -------- Public APIs --------
    @api.model
    def action_refresh_from_partners(self, partners=None):
        """
        Refresh KPI rows for given partners; if None, refresh all commercial customers.
        Calculates:
          - outstanding = sum open residuals of invoices
          - credit_open = sum open residuals of credit notes
          - overdue = sum open residuals of invoices past due
          - overdue_ratio = max(0, (overdue - credit_open)) / outstanding   (if outstanding > 0)
        """
        if partners is None:
            partners = self.env["res.partner"].search([("customer_rank", ">", 0)])

        Move = self.env["account.move"].sudo()
        Sale = self.env["sale.order"].sudo()
        now_dt = fields.Datetime.now()

        for partner in partners:
            company = partner.company_id or self.env.company
            cp = partner.commercial_partner_id
            today = fields.Date.context_today(partner)

            # Window for orders_in_window
            window_days = self._get_window_days_for_company(partner, company)
            date_from_dt = now_dt - timedelta(days=window_days)

            # ---- Open posted invoices (denominator & overdue) ----
            inv_domain = [
                ("company_id", "=", company.id),
                ("partner_id.commercial_partner_id", "=", cp.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("amount_residual", ">", 0),
            ]
            invoices = Move.with_company(company).search(inv_domain)
            inv_outstanding = sum(m.amount_residual for m in invoices) or 0.0
            inv_overdue = sum(
                m.amount_residual
                for m in invoices
                if m.invoice_date_due and m.invoice_date_due < today
            ) or 0.0

            # ---- Open posted credit notes (to offset overdue) ----
            cr_domain = [
                ("company_id", "=", company.id),
                ("partner_id.commercial_partner_id", "=", cp.id),
                ("move_type", "=", "out_refund"),
                ("state", "=", "posted"),
                ("amount_residual", ">", 0),
            ]
            credits = Move.with_company(company).search(cr_domain)
            credit_open = sum(m.amount_residual for m in credits) or 0.0

            # ---- Orders in window ----
            orders_in_window = Sale.with_company(company).search_count(
                [
                    ("company_id", "=", company.id),
                    ("partner_id.commercial_partner_id", "=", cp.id),
                    ("state", "in", ("sale", "done")),
                    ("date_order", ">=", date_from_dt),
                ]
            )

            # ---- Credit limit & utilization ----
            credit_limit = self._get_credit_limit_for_partner(partner, company)
            # Utilization uses net exposure (invoices minus open credits) bounded at >= 0
            net_exposure = max(inv_outstanding - credit_open, 0.0)
            credit_util_pct = (net_exposure / credit_limit * 100.0) if credit_limit else 0.0

            # ---- Overdue ratio ----
            overdue_effective = max(inv_overdue - credit_open, 0.0)
            overdue_ratio = (overdue_effective / inv_outstanding) if inv_outstanding > 0 else 0.0

            # ---- Risk score/level (reuse partner’s live compute output if available) ----
            threshold_low, threshold_high = self._get_thresholds_for_company(partner, company)
            score = partner.risk_score or 0
            level = partner.risk_level or ("high" if score >= threshold_high else "medium" if score >= threshold_low else "low")

            # upsert
            rec = self.search(
                [("company_id", "=", company.id), ("commercial_partner_id", "=", cp.id)],
                limit=1,
            )
            vals = {
                "company_id": company.id,
                "commercial_partner_id": cp.id,
                "outstanding": inv_outstanding,
                "credit_open": credit_open,
                "overdue": inv_overdue,
                "credit_limit": credit_limit,
                "credit_util_pct": credit_util_pct,
                "overdue_ratio": overdue_ratio,
                "orders_in_window": orders_in_window,
                "risk_score": score,
                "risk_level": level,
                "last_updated": now_dt,
            }
            if rec:
                rec.write(vals)
            else:
                self.create(vals)

        return True

    @api.model
    def cron_refresh_all(self):
        """Cron entry point – refresh all commercial customers."""
        self.action_refresh_from_partners(None)
        return True
