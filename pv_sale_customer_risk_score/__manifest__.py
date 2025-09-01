# -*- coding: utf-8 -*-
{
    "name": "PV: Customer Risk Score for Sales",
    "version": "18.0.2.0",
    "category": "Sales/Accounting",
    "images": ["static/description/banner.png"],
    "summary": "Customer risk KPIs + Debtors dashboard snapshot for pivot/grouping",
    "author": "PV-Odoo",
    "license": "LGPL-3",
    "depends": [
        "base",
        "account",
        "sale",
    ],
    "data": [
        "security/ir.model.access.csv",          
        "views/res_config_settings_views.xml",   
        "views/res_partner_views.xml",           
        "views/sale_order_views.xml",            
        "data/ir_cron.xml",                      

        
        "views/debtor_kpi_views.xml",
        "data/ir_cron_debtor_kpi.xml",
    ],
    "assets": {},
    "installable": True,
    "application": False,
    "auto_install": False,
}
