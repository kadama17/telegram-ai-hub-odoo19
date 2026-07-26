from odoo.tests.common import TransactionCase


class TestMessagingCRM(TransactionCase):
    def test_create_lead_handler(self):
        channel = self.env.ref("rb_messaging_automation_core.channel_telegram")
        connection = self.env["rb.messaging.connection"].create({
            "name": "Telegram", "channel_id": channel.id, "technical_user_id": self.env.user.id,
        })
        identity = self.env["rb.messaging.identity"].create({
            "name": "Ada", "channel_id": channel.id, "external_id": "42",
            "company_id": self.env.company.id,
        })
        conversation = self.env["rb.messaging.conversation"].create({
            "name": "Ada", "connection_id": connection.id, "identity_id": identity.id,
        })
        message = self.env["rb.messaging.message"].create({
            "conversation_id": conversation.id, "direction": "in", "body": "Quote",
        })
        result = self.env["crm.lead"]._rb_messaging_create_lead(message, {"name": "ABC quote"})
        self.assertEqual(self.env["crm.lead"].browse(result["id"]).name, "ABC quote")
