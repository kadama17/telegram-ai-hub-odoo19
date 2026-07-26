import json

from psycopg2 import IntegrityError

from odoo import http
from odoo.http import request


class TelegramWebhook(http.Controller):
    @http.route("/rb_messaging/telegram/webhook/<string:connection_uuid>", type="http", auth="public", methods=["POST"], csrf=False)
    def receive(self, connection_uuid, **kwargs):
        connection = request.env["rb.messaging.connection"].sudo().search([
            ("uuid", "=", connection_uuid), ("channel_code", "=", "telegram"), ("active", "=", True)
        ], limit=1)
        if not connection or request.httprequest.headers.get("X-Telegram-Bot-Api-Secret-Token") != connection.telegram_webhook_secret:
            return request.make_response(
                json.dumps({"ok": False}),
                headers=[("Content-Type", "application/json")],
                status=403,
            )
        payload = request.httprequest.get_json(silent=True)
        if not isinstance(payload, dict) or "update_id" not in payload:
            return request.make_response(
                json.dumps({"ok": False}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )
        try:
            connection.process_telegram_payload(payload)
        except IntegrityError:
            request.env.cr.rollback()
        return request.make_response(
            json.dumps({"ok": True}),
            headers=[("Content-Type", "application/json")],
        )
