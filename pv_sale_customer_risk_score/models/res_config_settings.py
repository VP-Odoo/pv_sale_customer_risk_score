# pv_sale_customer_risk_score/models/res_config_settings.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pv_risk_activity_window_days = fields.Integer(
        string="Activity Window (Days)",
        default=90,
        config_parameter="pv_sale_customer_risk.activity_window_days",
        company_dependent=True,
        help="How many days to look back when counting confirmed/done sales orders used by the risk indicator.",
    )

    # Thresholds
    risk_low_threshold = fields.Integer(
        string="Low threshold (score ≥)",
        default=20,
        config_parameter="pv_sale_customer_risk.low_threshold",
        company_dependent=True,
    )
    risk_high_threshold = fields.Integer(
        string="High threshold (score ≥)",
        default=60,
        config_parameter="pv_sale_customer_risk.high_threshold",
        company_dependent=True,
    )

    # Toggles
    risk_show_warning_on_quote = fields.Boolean(
        string="Warn on Quotation if Risk",
        default=True,
        config_parameter="pv_sale_customer_risk.warn_on_quote",
        company_dependent=True,
    )
    risk_block_sale_on_high = fields.Boolean(
        string="Block confirmation if High",
        default=False,
        config_parameter="pv_sale_customer_risk.block_sale_on_high",
        company_dependent=True,
    )

    # Optional weights/targets (kept as integers)
    risk_weight_credit = fields.Integer(
        string="Weight: Credit Utilization",
        default=40,
        config_parameter="pv_sale_customer_risk.weight_credit",
        company_dependent=True,
    )
    risk_weight_overdue = fields.Integer(
        string="Weight: Overdue Ratio",
        default=50,
        config_parameter="pv_sale_customer_risk.weight_overdue",
        company_dependent=True,
    )
    risk_weight_activity = fields.Integer(
        string="Weight: Inactivity",
        default=10,
        config_parameter="pv_sale_customer_risk.weight_activity",
        company_dependent=True,
    )
    risk_target_orders_in_window = fields.Integer(
        string="Target orders in window",
        default=1,
        config_parameter="pv_sale_customer_risk.target_orders_in_window",
        company_dependent=True,
    )

    @api.constrains(
        'pv_risk_activity_window_days',
        'risk_low_threshold',
        'risk_high_threshold',
        'risk_target_orders_in_window',
    )
    def _check_positive_ints(self):
        for rec in self:
            if rec.pv_risk_activity_window_days and rec.pv_risk_activity_window_days < 1:
                raise ValidationError(_("Activity window must be at least 1 day."))
            if rec.risk_low_threshold is not False and rec.risk_low_threshold < 0:
                raise ValidationError(_("Thresholds must be ≥ 0."))
            if (
                rec.risk_high_threshold is not False
                and rec.risk_low_threshold is not False
                and rec.risk_high_threshold < rec.risk_low_threshold
            ):
                raise ValidationError(_("High threshold must be ≥ Low threshold."))
            if (
                rec.risk_target_orders_in_window is not False
                and rec.risk_target_orders_in_window < 0
            ):
                raise ValidationError(_("Target orders must be ≥ 0."))
