import json

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestMessagingCore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env.ref("rb_messaging_automation_core.channel_telegram")
        cls.connection = cls.env["rb.messaging.connection"].create({
            "name": "Test", "channel_id": cls.channel.id, "active": True,
            "technical_user_id": cls.env.user.id,
        })
        cls.identity = cls.env["rb.messaging.identity"].create({
            "name": "Ada", "channel_id": cls.channel.id, "external_id": "42",
            "chat_id": "42", "company_id": cls.env.company.id,
        })
        cls.conversation = cls.env["rb.messaging.conversation"].create({
            "name": "Ada", "connection_id": cls.connection.id, "identity_id": cls.identity.id,
        })

    def test_template_substitution(self):
        rendered = self.env["rb.messaging.template"].render_text(
            "Hello {{ partner.name }}, {{order.name}}",
            {"partner": {"name": "Ada"}, "order": {"name": "S0001"}},
        )
        self.assertEqual(rendered, "Hello Ada, S0001")

    def test_condition_operators(self):
        workflow = self.env["rb.messaging.workflow"].create({"name": "Test"})
        step = self.env["rb.messaging.workflow.step"].create({
            "name": "Condition", "workflow_id": workflow.id, "action_type": "set_variable",
            "condition_json": json.dumps({"variable": "body", "operator": "contains", "value": "order"}),
        })
        self.assertTrue(step.evaluate_condition({"body": "My ORDER please"}))
        self.assertFalse(step.evaluate_condition({"body": "invoice"}))

    def test_transfer_human(self):
        self.conversation.action_transfer_human()
        self.assertEqual(self.conversation.state, "human")
        self.assertFalse(self.conversation.bot_active)
        self.conversation.action_resume_bot()
        self.assertTrue(self.conversation.bot_active)

    def test_model_requires_allowlist(self):
        workflow = self.env["rb.messaging.workflow"].create({"name": "Unsafe"})
        model = self.env["ir.model"]._get("res.users")
        step = self.env["rb.messaging.workflow.step"].create({
            "name": "Unsafe search", "workflow_id": workflow.id, "action_type": "search",
            "model_id": model.id,
        })
        with self.assertRaises(AccessError):
            step._safe_model()

    def test_event_idempotency_constraint(self):
        values = {"connection_id": self.connection.id, "external_id": "evt-1", "payload_json": "{}"}
        self.env["rb.messaging.event"].create(values)
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env["rb.messaging.event"].create(values)

