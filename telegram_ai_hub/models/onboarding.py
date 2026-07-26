from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TelegramHubDashboard(models.TransientModel):
    _name = "rb.telegram.hub.dashboard"
    _description = "Telegram AI Hub Dashboard"

    connection_count = fields.Integer(readonly=True)
    active_bot_count = fields.Integer(readonly=True)
    authorized_user_count = fields.Integer(readonly=True)
    conversation_count = fields.Integer(readonly=True)
    automated_count = fields.Integer(readonly=True)
    human_count = fields.Integer(readonly=True)
    incoming_today = fields.Integer(readonly=True)
    outgoing_today = fields.Integer(readonly=True)
    messages_7d = fields.Integer(readonly=True)
    messages_30d = fields.Integer(readonly=True)
    processed_event_count = fields.Integer(readonly=True)
    failed_event_count = fields.Integer(readonly=True)
    success_rate = fields.Float(string="Success rate (%)", readonly=True, digits=(5, 1))

    @api.model
    def _dashboard_values(self):
        self = self.sudo()
        company = self.env.user.company_id
        connections = self.env["rb.messaging.connection"].search([
            ("company_id", "=", company.id),
            ("channel_code", "=", "telegram"),
        ])
        active = connections.filtered("active")
        conversations = self.env["rb.messaging.conversation"].search([
            ("company_id", "=", company.id),
            ("connection_id", "in", connections.ids),
        ])
        today = fields.Date.context_today(self)
        message_domain = [
            ("company_id", "=", company.id),
            ("connection_id", "in", connections.ids),
        ]
        event_domain = [("connection_id", "in", connections.ids)]
        processed_events = self.env["rb.messaging.event"].search_count(
            event_domain + [("state", "=", "done")]
        )
        failed_events = self.env["rb.messaging.event"].search_count(
            event_domain + [("state", "=", "failed")]
        )
        completed_events = processed_events + failed_events
        now = datetime.now()
        return {
            "connection_count": len(connections),
            "active_bot_count": len(active),
            "authorized_user_count": self.env["rb.messaging.telegram.user"].search_count([
                ("company_id", "=", company.id), ("active", "=", True)
            ]),
            "conversation_count": len(conversations),
            "automated_count": len(conversations.filtered(lambda c: c.bot_active)),
            "human_count": len(conversations.filtered(lambda c: not c.bot_active)),
            "incoming_today": self.env["rb.messaging.message"].search_count(message_domain + [
                ("direction", "=", "in"),
                ("create_date", ">=", fields.Datetime.to_string(today)),
            ]),
            "outgoing_today": self.env["rb.messaging.message"].search_count(message_domain + [
                ("direction", "=", "out"),
                ("create_date", ">=", fields.Datetime.to_string(today)),
            ]),
            "messages_7d": self.env["rb.messaging.message"].search_count(
                message_domain + [("create_date", ">=", now - timedelta(days=7))]
            ),
            "messages_30d": self.env["rb.messaging.message"].search_count(
                message_domain + [("create_date", ">=", now - timedelta(days=30))]
            ),
            "processed_event_count": processed_events,
            "failed_event_count": failed_events,
            "success_rate": (
                round(100.0 * processed_events / completed_events, 1)
                if completed_events else 0.0
            ),
        }

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create(self._dashboard_values())
        return {
            "type": "ir.actions.act_window",
            "name": _("Telegram AI Hub"),
            "res_model": self._name,
            "res_id": dashboard.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_refresh(self):
        self.write(self._dashboard_values())
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def dashboard_data(self):
        self = self.sudo()
        values = self._dashboard_values()
        connections = self.env["rb.messaging.connection"].search([
            ("company_id", "=", self.env.user.company_id.id),
            ("channel_code", "=", "telegram"),
        ])
        today = fields.Date.context_today(self)
        labels, incoming, outgoing = [], [], []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            next_day = day + timedelta(days=1)
            domain = [
                ("company_id", "=", self.env.user.company_id.id),
                ("connection_id", "in", connections.ids),
                ("create_date", ">=", fields.Datetime.to_string(day)),
                ("create_date", "<", fields.Datetime.to_string(next_day)),
            ]
            labels.append(day.strftime("%a"))
            incoming.append(self.env["rb.messaging.message"].search_count(
                domain + [("direction", "=", "in")]
            ))
            outgoing.append(self.env["rb.messaging.message"].search_count(
                domain + [("direction", "=", "out")]
            ))
        errors = self.env["rb.messaging.event"].search(
            [("connection_id", "in", connections.ids), ("state", "=", "failed")],
            order="create_date desc",
            limit=5,
        )
        values.update({
            "activity_labels": labels,
            "activity_incoming": incoming,
            "activity_outgoing": outgoing,
            "recent_errors": [{
                "id": event.id,
                "message": event.error_message or _("Unknown processing error"),
                "date": fields.Datetime.to_string(event.create_date),
            } for event in errors],
        })
        return values

class TelegramOnboardingWizard(models.TransientModel):
    _name = "rb.telegram.onboarding.wizard"
    _description = "Telegram Bot Guided Setup"

    step = fields.Selection([
        ("welcome", "Welcome"),
        ("botfather", "Create the bot"),
        ("token", "Connect Telegram"),
        ("ai", "Configure AI"),
        ("admin", "Authorize an administrator"),
        ("done", "Finish"),
    ], default="welcome", required=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.user.company_id
    )
    connection_name = fields.Char(default="Telegram AI Bot", required=True)
    bot_token = fields.Char(string="BotFather Token")
    bot_username = fields.Char(readonly=True)
    ai_api_key = fields.Char(string="OpenAI API Key")
    ai_model = fields.Char(default="gpt-5.6")
    telegram_user_id = fields.Char(
        string="Administrator Telegram ID",
        help="Permanent numeric Telegram user ID, not the @username.",
    )
    telegram_display_name = fields.Char(default="Telegram Administrator")
    odoo_user_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        domain=[("share", "=", False)],
    )
    permission_contacts = fields.Boolean(default=True)
    permission_crm = fields.Boolean(default=True)
    permission_sales_read = fields.Boolean(default=True)
    permission_invoices_read = fields.Boolean(default=True)
    permission_invoices_create = fields.Boolean(default=False)
    connection_id = fields.Many2one("rb.messaging.connection", readonly=True)
    webhook_url = fields.Char(readonly=True)
    result_message = fields.Text(readonly=True)

    @api.model
    def action_open_wizard(self):
        wizard = self.create({})
        return {
            "type": "ir.actions.act_window",
            "name": _("Configure a Telegram Bot"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_next(self):
        order = ["welcome", "botfather", "token", "ai", "admin", "done"]
        self.step = order[min(order.index(self.step) + 1, len(order) - 1)]
        return self._reopen()

    def action_back(self):
        order = ["welcome", "botfather", "token", "ai", "admin", "done"]
        self.step = order[max(order.index(self.step) - 1, 0)]
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Configure a Telegram Bot"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_open_botfather(self):
        return {
            "type": "ir.actions.act_url",
            "url": "https://t.me/BotFather",
            "target": "new",
        }

    def action_open_manual(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Telegram Bots"),
            "res_model": "rb.messaging.connection",
            "view_mode": "list,form",
            "domain": [("channel_code", "=", "telegram")],
            "target": "current",
        }

    def action_open_bot(self):
        username = (self.bot_username or "").lstrip("@")
        if not username:
            raise UserError(_("The bot username is not available yet."))
        return {
            "type": "ir.actions.act_url",
            "url": "https://t.me/%s" % username,
            "target": "new",
        }

    def action_test_token(self):
        self.ensure_one()
        if not self.bot_token:
            raise UserError(_("Paste the token supplied by BotFather."))
        channel = self.env["rb.messaging.channel"].search([
            ("code", "=", "telegram")
        ], limit=1)
        connection = self.env["rb.messaging.connection"].new({
            "name": self.connection_name,
            "channel_id": channel.id,
            "company_id": self.company_id.id,
            "technical_user_id": self.odoo_user_id.id,
            "bot_token": self.bot_token,
        })
        info = connection._get_telegram_adapter()._call("getMe", {})
        self.bot_username = "@%s" % info.get("username")
        self.step = "ai"
        return self._reopen()

    def _ensure_workflow(self, name, sequence, trigger_type, trigger_value, body=None):
        workflow = self.env["rb.messaging.workflow"].search([
            ("name", "=", name),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not workflow:
            channel = self.env["rb.messaging.channel"].search([
                ("code", "=", "telegram")
            ], limit=1)
            workflow = self.env["rb.messaging.workflow"].create({
                "name": name,
                "sequence": sequence,
                "trigger_type": trigger_type,
                "trigger_value": trigger_value,
                "company_id": self.company_id.id,
                "channel_ids": [(6, 0, channel.ids)],
                "active": True,
            })
        if body and not workflow.step_ids:
            template = self.env["rb.messaging.template"].create({
                "name": name,
                "body": body,
                "company_id": self.company_id.id,
            })
            self.env["rb.messaging.workflow.step"].create({
                "workflow_id": workflow.id,
                "name": _("Reply"),
                "sequence": 10,
                "action_type": "reply",
                "template_id": template.id,
            })
        return workflow

    def action_finish(self):
        self.ensure_one()
        channel = self.env["rb.messaging.channel"].search([
            ("code", "=", "telegram")
        ], limit=1)
        connection = self.env["rb.messaging.connection"].search([
            ("channel_id", "=", channel.id),
            ("company_id", "=", self.company_id.id),
            ("bot_token", "=", self.bot_token),
        ], limit=1)
        values = {
            "name": self.connection_name,
            "channel_id": channel.id,
            "company_id": self.company_id.id,
            "technical_user_id": self.odoo_user_id.id,
            "bot_token": self.bot_token,
            "language": self.env.user.lang or "fr_FR",
            "active": True,
        }
        if connection:
            connection.write(values)
        else:
            connection = self.env["rb.messaging.connection"].create(values)
        connection.action_test_telegram()
        connection.action_install_telegram_webhook()

        provider = False
        if "rb.messaging.ai.provider" in self.env:
            provider = self.env["rb.messaging.ai.provider"].search([
                ("company_id", "=", self.company_id.id),
                ("active", "=", True),
            ], limit=1)
        if self.ai_api_key:
            provider_values = {
                "name": "OpenAI",
                "company_id": self.company_id.id,
                "technical_user_id": self.odoo_user_id.id,
                "api_key": self.ai_api_key,
                "model": self.ai_model,
                "active": True,
            }
            if provider:
                provider.write(provider_values)
            else:
                provider = self.env["rb.messaging.ai.provider"].create(provider_values)

        if self.telegram_user_id:
            access = self.env["rb.messaging.telegram.user"].search([
                ("company_id", "=", self.company_id.id),
                ("telegram_id", "=", self.telegram_user_id),
            ], limit=1)
            access_values = {
                "name": self.telegram_display_name,
                "telegram_id": self.telegram_user_id,
                "odoo_user_id": self.odoo_user_id.id,
                "company_id": self.company_id.id,
                "active": True,
                "permission_contacts": self.permission_contacts,
                "permission_crm": self.permission_crm,
                "permission_sales_read": self.permission_sales_read,
                "permission_invoices_read": self.permission_invoices_read,
                "permission_invoices_create": self.permission_invoices_create,
            }
            access.write(access_values) if access else self.env[
                "rb.messaging.telegram.user"
            ].create(access_values)

        self._ensure_workflow(
            "Telegram - Accueil",
            10,
            "command",
            "/start",
            "Bonjour ! Votre assistant Odoo Telegram est opérationnel. Envoyez /help pour découvrir ses fonctions.",
        )
        self._ensure_workflow(
            "Telegram - Aide",
            5,
            "command",
            "/help",
            "Vous pouvez interroger vos contacts, CRM, ventes, factures, produits, paiements et rendez-vous en langage naturel.",
        )
        if provider:
            workflow = self._ensure_workflow(
                "Telegram - Assistant IA", 50, "message", False
            )
            workflow.active = True
            if not workflow.step_ids:
                self.env["rb.messaging.workflow.step"].create({
                    "workflow_id": workflow.id,
                    "name": _("AI Assistant"),
                    "sequence": 10,
                    "action_type": "ai_assistant",
                    "ai_provider_id": provider.id,
                })
            else:
                ai_steps = workflow.step_ids.filtered(
                    lambda step: step.action_type == "ai_assistant"
                )
                if ai_steps:
                    ai_steps.write({"ai_provider_id": provider.id})

        self.connection_id = connection
        self.bot_username = "@%s" % connection.bot_username
        self.webhook_url = "%s?db=%s" % (connection.webhook_url, self.env.cr.dbname)
        self.result_message = _(
            "The bot is connected, the webhook is installed and the default automations are active."
        )
        self.step = "done"
        return self._reopen()

    def action_open_dashboard(self):
        return self.env["rb.telegram.hub.dashboard"].action_open_dashboard()
