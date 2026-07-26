{
    "name": "Odoo Telegram AI Hub",
    "summary": "Telegram-only AI assistant, guided setup and operations dashboard",
    "version": "19.0.2.0.0",
    "license": "OPL-1",
    "author": "ResilientByte Maroc",
    "depends": ["rb_messaging_automation_core", "web"],
    "data": ["security/ir.model.access.csv", "views/telegram_views.xml"],
    "assets": {
        "web.assets_backend": [
            "rb_messaging_telegram/static/src/dashboard/dashboard.js",
            "rb_messaging_telegram/static/src/dashboard/dashboard.xml",
            "rb_messaging_telegram/static/src/dashboard/dashboard.scss",
        ],
    },
    "application": False,
    "installable": False,
}
