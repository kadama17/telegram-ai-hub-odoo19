import json
import html
import re
import secrets
from urllib.parse import quote_plus

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TelegramAdapter:
    def __init__(self, connection):
        self.connection = connection

    def normalize_event(self, payload):
        raw = payload.get("message") or payload.get("channel_post") or payload.get("callback_query", {}).get("message")
        sender = payload.get("callback_query", {}).get("from") or raw.get("from", {})
        text = payload.get("callback_query", {}).get("data") or raw.get("text") or raw.get("caption", "")
        audio = raw.get("voice") or raw.get("audio") or {}
        return {
            "message_id": "tg:%s" % payload["update_id"], "sender_id": sender["id"],
            "chat_id": raw["chat"]["id"], "sender_name": " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])),
            "username": sender.get("username"), "body": text,
            "language": sender.get("language_code"),
            "audio_file_id": audio.get("file_id"),
            "audio_mime_type": audio.get("mime_type") or "audio/ogg",
            "audio_file_name": raw.get("audio", {}).get("file_name") or "telegram_voice.ogg",
        }

    def _call(self, method, payload):
        if not (self.connection.bot_token or "").strip():
            raise UserError(_("The Telegram bot token is missing."))
        response = requests.post("https://api.telegram.org/bot%s/%s" % (self.connection.bot_token, method), json=payload, timeout=15)
        data = response.json()
        if not response.ok or not data.get("ok"):
            raise UserError(_("Telegram API error: %s") % data.get("description", response.text))
        return data["result"]

    def _render_html(self, text):
        rendered = html.escape(text or "")
        rendered = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", rendered, flags=re.DOTALL)
        rendered = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", rendered)
        rendered = re.sub(r"(?m)^#{1,6}\s+", "", rendered)
        return rendered

    def _split_text(self, text, limit=3500):
        chunks = []
        current = ""
        for line in (text or "").splitlines(keepends=True):
            if len(current) + len(line) <= limit:
                current += line
                continue
            if current:
                chunks.append(current.rstrip())
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
        if current or not chunks:
            chunks.append(current.rstrip())
        return chunks

    def send_message(self, conversation, body, buttons=None, **kwargs):
        last_message = False
        chunks = self._split_text(body)
        for index, chunk in enumerate(chunks):
            payload = {
                "chat_id": conversation.identity_id.chat_id,
                "text": self._render_html(chunk),
                "parse_mode": "HTML",
            }
            if buttons and index == len(chunks) - 1:
                payload["reply_markup"] = {"inline_keyboard": buttons}
            result = self._call("sendMessage", payload)
            last_message = self.connection.env["rb.messaging.message"].create({
                "conversation_id": conversation.id,
                "external_id": "tg:%s" % result["message_id"],
                "direction": "out",
                "body": chunk,
                "status": "sent",
                "payload_json": json.dumps(result),
            })
        return last_message.id

    def download_file(self, file_id):
        file_info = self._call("getFile", {"file_id": file_id})
        response = requests.get(
            "https://api.telegram.org/file/bot%s/%s"
            % (self.connection.bot_token, file_info["file_path"]),
            timeout=30,
        )
        response.raise_for_status()
        return response.content


class MessagingConnection(models.Model):
    _inherit = "rb.messaging.connection"

    bot_token = fields.Char(groups="rb_messaging_automation_core.group_messaging_technical")
    bot_username = fields.Char(readonly=True)
    telegram_webhook_secret = fields.Char(default=lambda self: secrets.token_urlsafe(24), groups="rb_messaging_automation_core.group_messaging_technical")
    allow_private = fields.Boolean(default=True)
    allow_groups = fields.Boolean(default=False)
    allow_channels = fields.Boolean(default=False)

    def _get_telegram_adapter(self):
        self.ensure_one()
        return TelegramAdapter(self)

    def action_test_telegram(self):
        usernames = []
        for record in self:
            info = record._get_telegram_adapter()._call("getMe", {})
            record.bot_username = info.get("username")
            usernames.append("@%s" % record.bot_username if record.bot_username else record.name)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Telegram connection successful"),
                "message": _("Bot verified: %s") % ", ".join(usernames),
                "type": "success",
                "sticky": False,
            },
        }

    def action_install_telegram_webhook(self):
        installed = []
        for record in self:
            webhook_url = "%s?db=%s" % (
                record.webhook_url,
                quote_plus(record.env.cr.dbname),
            )
            record._get_telegram_adapter()._call("setWebhook", {
                "url": webhook_url, "secret_token": record.telegram_webhook_secret,
                "allowed_updates": ["message", "callback_query", "channel_post"],
            })
            webhook_info = record._get_telegram_adapter()._call("getWebhookInfo", {})
            if webhook_info.get("url") != webhook_url:
                raise UserError(_("Telegram did not confirm the expected webhook URL."))
            installed.append(record.bot_username or record.name)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Telegram webhook installed"),
                "message": _(
                    "Webhook confirmed for %s. Telegram has no installation error."
                ) % ", ".join(installed),
                "type": "success",
                "sticky": False,
            },
        }

    def process_telegram_payload(self, payload):
        self.ensure_one()
        normalized = self._get_telegram_adapter().normalize_event(payload)
        normalized = self._prepare_telegram_normalized(normalized, payload)
        event = self.env["rb.messaging.event"].create({
            "connection_id": self.id, "external_id": normalized["message_id"],
            "payload_json": json.dumps(payload),
        })
        return event.process_normalized(normalized)

    def _prepare_telegram_normalized(self, normalized, payload):
        return normalized


class MessagingCommand(models.Model):
    _name = "rb.messaging.command"
    _description = "Telegram Command"

    name = fields.Char(required=True)
    command = fields.Char(required=True)
    description = fields.Char(required=True, translate=True)
    connection_id = fields.Many2one("rb.messaging.connection", required=True, ondelete="cascade")
    workflow_id = fields.Many2one("rb.messaging.workflow", required=True, ondelete="cascade")
    active = fields.Boolean(default=True)

    @api.constrains("command")
    def _check_command(self):
        for record in self:
            if not record.command.startswith("/"):
                raise UserError(_("A Telegram command must start with /."))


class MessagingTelegramUser(models.Model):
    _name = "rb.messaging.telegram.user"
    _description = "Authorized Telegram User"
    _order = "name"

    name = fields.Char(required=True)
    telegram_id = fields.Char(
        required=True,
        index=True,
        help="Permanent numeric Telegram user ID. The display name is not used for authentication.",
    )
    telegram_username = fields.Char()
    odoo_user_id = fields.Many2one(
        "res.users",
        required=True,
        domain=[("share", "=", False)],
        help="Odoo access rights of this user are applied in addition to the permissions below.",
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)
    permission_contacts = fields.Boolean(string="Manage contacts")
    permission_crm = fields.Boolean(string="Manage CRM")
    permission_sales_read = fields.Boolean(string="Read all sales")
    permission_invoices_read = fields.Boolean(string="Read all invoices")
    permission_invoices_create = fields.Boolean(string="Create invoices")

    def init(self):
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS rb_messaging_telegram_user_company_id_uniq "
            "ON rb_messaging_telegram_user (company_id, telegram_id)"
        )
