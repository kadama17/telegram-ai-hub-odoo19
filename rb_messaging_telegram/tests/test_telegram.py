from odoo.tests.common import TransactionCase


class TestTelegram(TransactionCase):
    def test_normalization(self):
        channel = self.env.ref("rb_messaging_automation_core.channel_telegram")
        connection = self.env["rb.messaging.connection"].create({
            "name": "Telegram", "channel_id": channel.id, "technical_user_id": self.env.user.id,
        })
        payload = {"update_id": 99, "message": {
            "message_id": 7, "from": {"id": 42, "first_name": "Ada", "username": "ada"},
            "chat": {"id": 42, "type": "private"}, "text": "/start",
        }}
        normalized = connection._get_telegram_adapter().normalize_event(payload)
        self.assertEqual(normalized["message_id"], "tg:99")
        self.assertEqual(normalized["body"], "/start")

