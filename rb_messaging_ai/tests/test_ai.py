from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestMessagingAI(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        channel = cls.env.ref("rb_messaging_automation_core.channel_telegram")
        cls.connection = cls.env["rb.messaging.connection"].create({
            "name": "AI test", "channel_id": channel.id,
            "technical_user_id": cls.env.user.id, "active": True,
        })
        identity = cls.env["rb.messaging.identity"].create({
            "name": "Test user", "channel_id": channel.id, "external_id": "ai-42",
            "company_id": cls.env.company.id,
        })
        cls.conversation = cls.env["rb.messaging.conversation"].create({
            "name": "AI", "connection_id": cls.connection.id, "identity_id": identity.id,
        })
        cls.message = cls.env["rb.messaging.message"].create({
            "conversation_id": cls.conversation.id, "direction": "in", "body": "Mes factures",
        })
        cls.provider = cls.env["rb.messaging.ai.provider"].create({
            "name": "Mock", "active": True, "api_key": "test-key",
            "technical_user_id": cls.env.user.id,
        })

    def test_unverified_identity_is_rejected_by_business_tools(self):
        result = self.env["rb.messaging.ai.agent"]._execute_tool(
            "find_customer", {}, self.message, self.provider
        )
        self.assertEqual(result["error"], "identity_required")

    def test_provider_response_text_extraction(self):
        text = self.provider._extract_text({
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Bonjour"}]}]
        })
        self.assertEqual(text, "Bonjour")

    def test_mocked_response_does_not_need_live_key(self):
        with patch.object(type(self.provider), "_request", return_value={
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Réponse sûre"}]}]
        }):
            with patch.object(type(self.connection), "send_message", return_value=99):
                result = self.env["rb.messaging.ai.agent"].run(self.provider, self.message)
        self.assertEqual(result, 99)
