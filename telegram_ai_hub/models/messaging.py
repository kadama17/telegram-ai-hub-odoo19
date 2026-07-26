import json
import logging
import re
import time
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class MessagingChannel(models.Model):
    _name = "rb.messaging.channel"
    _description = "Messaging Channel"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    _sql_constraints = [("code_unique", "unique(code)", "Channel code must be unique.")]

    def init(self):
        self.env.cr.execute("CREATE UNIQUE INDEX IF NOT EXISTS rb_messaging_channel_code_uniq ON rb_messaging_channel (code)")


class MessagingConnection(models.Model):
    _name = "rb.messaging.connection"
    _description = "Messaging Connection"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, track_visibility="onchange")
    uuid = fields.Char(default=lambda self: str(uuid.uuid4()), required=True, readonly=True, copy=False, index=True)
    channel_id = fields.Many2one("rb.messaging.channel", required=True, ondelete="restrict", track_visibility="onchange")
    channel_code = fields.Char(related="channel_id.code", store=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.user.company_id)
    technical_user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    active = fields.Boolean(default=False, track_visibility="onchange")
    language = fields.Selection(selection=lambda self: self.env["res.lang"].get_installed(), default=lambda self: self.env.lang)
    webhook_url = fields.Char(compute="_compute_webhook_url")
    _sql_constraints = [("uuid_unique", "unique(uuid)", "Connection UUID must be unique.")]

    def init(self):
        self.env.cr.execute("CREATE UNIQUE INDEX IF NOT EXISTS rb_messaging_connection_uuid_uniq ON rb_messaging_connection (uuid)")

    @api.depends("uuid", "channel_code")
    def _compute_webhook_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        for record in self:
            record.webhook_url = "%s/rb_messaging/%s/webhook/%s" % (base, record.channel_code or "channel", record.uuid)

    def _get_adapter(self):
        self.ensure_one()
        adapter = getattr(self, "_get_%s_adapter" % self.channel_code, None)
        if not adapter:
            raise UserError(_("No adapter is installed for channel %s.") % self.channel_code)
        return adapter()

    def send_message(self, conversation, body, **kwargs):
        self.ensure_one()
        if not self.active:
            raise UserError(_("The connection is inactive."))
        return self._get_adapter().send_message(conversation, body, **kwargs)


class MessagingIdentity(models.Model):
    _name = "rb.messaging.identity"
    _description = "Multichannel Identity"

    name = fields.Char(required=True)
    channel_id = fields.Many2one("rb.messaging.channel", required=True, ondelete="restrict")
    external_id = fields.Char(required=True, index=True)
    chat_id = fields.Char(index=True)
    username = fields.Char()
    partner_id = fields.Many2one("res.partner", ondelete="set null")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.user.company_id)
    language = fields.Char()
    verified = fields.Boolean(default=False)
    consent_operational = fields.Boolean(default=False)
    consent_marketing = fields.Boolean(default=False)
    _sql_constraints = [
        ("identity_unique", "unique(channel_id, external_id, company_id)", "Identity already exists.")
    ]

    def init(self):
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS rb_messaging_identity_channel_external_company_uniq "
            "ON rb_messaging_identity (channel_id, external_id, company_id)"
        )


class MessagingConversation(models.Model):
    _name = "rb.messaging.conversation"
    _description = "Messaging Conversation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "last_message_at desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("New conversation"))
    connection_id = fields.Many2one("rb.messaging.connection", required=True, ondelete="restrict", index=True)
    identity_id = fields.Many2one("rb.messaging.identity", required=True, ondelete="restrict", index=True)
    partner_id = fields.Many2one(related="identity_id.partner_id", store=True)
    company_id = fields.Many2one(related="connection_id.company_id", store=True, index=True)
    state = fields.Selection([
        ("new", "New"), ("automated", "Automated"), ("waiting_info", "Waiting for information"),
        ("waiting_customer", "Waiting for customer"), ("human", "Transferred to operator"),
        ("processing", "Processing"), ("resolved", "Resolved"), ("closed", "Closed"),
        ("blocked", "Blocked"), ("error", "Error"),
    ], default="new", required=True, track_visibility="onchange", index=True)
    bot_active = fields.Boolean(default=True, track_visibility="onchange")
    operator_id = fields.Many2one("res.users", track_visibility="onchange")
    last_message_at = fields.Datetime(index=True)
    unread_count = fields.Integer(default=0)
    message_ids = fields.One2many("rb.messaging.message", "conversation_id")
    session_id = fields.Many2one("rb.messaging.session")

    def action_transfer_human(self):
        self.write({"state": "human", "bot_active": False, "operator_id": self.env.user.id})

    def action_resume_bot(self):
        self.write({"state": "automated", "bot_active": True, "operator_id": False})

    def action_close(self):
        self.write({"state": "closed", "bot_active": False})


class MessagingMessage(models.Model):
    _name = "rb.messaging.message"
    _description = "Messaging Message"
    _order = "create_date desc, id desc"

    conversation_id = fields.Many2one("rb.messaging.conversation", required=True, ondelete="cascade", index=True)
    connection_id = fields.Many2one(related="conversation_id.connection_id", store=True)
    company_id = fields.Many2one(related="conversation_id.company_id", store=True)
    external_id = fields.Char(index=True)
    direction = fields.Selection([("in", "Incoming"), ("out", "Outgoing"), ("note", "Internal note")], required=True)
    message_type = fields.Selection([("text", "Text"), ("image", "Image"), ("document", "Document"), ("interactive", "Interactive")], default="text")
    body = fields.Text()
    status = fields.Selection([
        ("prepared", "Prepared"), ("queued", "Queued"), ("sent", "Sent"), ("delivered", "Delivered"),
        ("read", "Read"), ("failed", "Failed"), ("unavailable", "Unavailable"),
    ], default="prepared", index=True)
    error_message = fields.Text()
    payload_json = fields.Text(groups="telegram_ai_hub.group_messaging_technical")
    _sql_constraints = [
        ("external_message_unique", "unique(connection_id, external_id)", "Message already processed.")
    ]

    def init(self):
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS rb_messaging_message_connection_external_uniq "
            "ON rb_messaging_message (connection_id, external_id) WHERE external_id IS NOT NULL"
        )


class MessagingTemplate(models.Model):
    _name = "rb.messaging.template"
    _description = "Messaging Response Template"

    name = fields.Char(required=True, translate=True)
    body = fields.Text(required=True, translate=True)
    channel_id = fields.Many2one("rb.messaging.channel")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.user.company_id)

    @api.model
    def render_text(self, template, variables):
        text = template or ""
        for key in re.findall(r"{{\s*([\w.]+)\s*}}", text):
            value = variables
            for part in key.split("."):
                value = value.get(part, "") if isinstance(value, dict) else getattr(value, part, "")
            text = re.sub(r"{{\s*%s\s*}}" % re.escape(key), str(value or ""), text)
        return text


class MessagingWorkflow(models.Model):
    _name = "rb.messaging.workflow"
    _description = "Messaging Automation"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    trigger_type = fields.Selection([
        ("message", "New message"), ("keyword", "Keyword"), ("command", "Command"),
        ("button", "Button"), ("manual", "Manual"),
    ], default="message", required=True)
    trigger_value = fields.Char()
    channel_ids = fields.Many2many("rb.messaging.channel")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.user.company_id)
    step_ids = fields.One2many("rb.messaging.workflow.step", "workflow_id")

    def matches(self, message):
        self.ensure_one()
        body = (message.body or "").strip()
        if self.channel_ids and message.connection_id.channel_id not in self.channel_ids:
            return False
        if self.trigger_type == "keyword":
            return (self.trigger_value or "").lower() in body.lower()
        if self.trigger_type == "command":
            return body.split(" ", 1)[0].lower() == (self.trigger_value or "").lower()
        return self.trigger_type == "message"

    def execute(self, message):
        self.ensure_one()
        session = message.conversation_id.session_id
        if not session:
            session = self.env["rb.messaging.session"].create({
                "conversation_id": message.conversation_id.id,
                "workflow_id": self.id,
            })
            message.conversation_id.session_id = session
        variables = session.get_variables()
        variables.update({"message": {"body": message.body}, "partner": message.conversation_id.partner_id})
        for step in self.step_ids.sorted("sequence"):
            if step.condition_json and not step.evaluate_condition(variables):
                continue
            started = time.monotonic()
            try:
                result = step.execute(message, variables)
                variables["last_result"] = result
                self.env["rb.messaging.audit"].create_success(message, step, time.monotonic() - started)
            except Exception as exc:
                self.env["rb.messaging.audit"].create_failure(message, step, exc, time.monotonic() - started)
                if step.stop_on_error:
                    message.conversation_id.state = "error"
                    raise
        session.set_variables(variables)
        message.conversation_id.state = "automated"


class MessagingWorkflowStep(models.Model):
    _name = "rb.messaging.workflow.step"
    _description = "Messaging Automation Step"
    _order = "sequence, id"

    workflow_id = fields.Many2one("rb.messaging.workflow", required=True, ondelete="cascade")
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    action_type = fields.Selection([
        ("reply", "Send reply"), ("set_variable", "Set variable"), ("search", "Search record"),
        ("create", "Create record"), ("write", "Update record"), ("whitelisted_method", "Allowed business action"),
        ("transfer", "Transfer to human"),
    ], required=True)
    template_id = fields.Many2one("rb.messaging.template")
    model_id = fields.Many2one("ir.model", domain=[("transient", "=", False)])
    field_ids = fields.Many2many("ir.model.fields")
    domain_json = fields.Text(default="[]")
    values_json = fields.Text(default="{}")
    condition_json = fields.Text(default="{}")
    method_name = fields.Char()
    result_variable = fields.Char(default="result")
    stop_on_error = fields.Boolean(default=True)

    @api.constrains("domain_json", "values_json", "condition_json")
    def _check_json(self):
        for record in self:
            for value in (record.domain_json, record.values_json, record.condition_json):
                try:
                    json.loads(value or "{}")
                except (TypeError, ValueError) as exc:
                    raise ValidationError(_("Invalid JSON: %s") % exc)

    def evaluate_condition(self, variables):
        self.ensure_one()
        rule = json.loads(self.condition_json or "{}")
        if not rule:
            return True
        left = variables.get(rule.get("variable"))
        right = rule.get("value")
        operator = rule.get("operator", "eq")
        operations = {
            "eq": lambda: left == right, "ne": lambda: left != right,
            "contains": lambda: str(right).lower() in str(left).lower(),
            "starts": lambda: str(left).lower().startswith(str(right).lower()),
            "empty": lambda: not left, "in": lambda: left in right,
            "gt": lambda: left > right, "lt": lambda: left < right,
            "regex": lambda: bool(re.search(str(right), str(left))),
        }
        if operator not in operations:
            raise ValidationError(_("Unsupported condition operator."))
        return operations[operator]()

    def _safe_model(self):
        self.ensure_one()
        if not self.model_id or not self.model_id.model:
            raise ValidationError(_("A model is required."))
        allowed = self.env["rb.messaging.allowed.action"].search([
            ("model_name", "=", self.model_id.model), ("active", "=", True)
        ])
        if not allowed:
            raise AccessError(_("This model is not allowed for messaging automation."))
        return self.env[self.model_id.model], allowed

    def execute(self, message, variables):
        self.ensure_one()
        conversation = message.conversation_id
        if self.action_type == "reply":
            body = self.env["rb.messaging.template"].render_text(self.template_id.body, variables)
            return conversation.connection_id.send_message(conversation, body)
        if self.action_type == "transfer":
            conversation.action_transfer_human()
            return True
        if self.action_type == "set_variable":
            values = json.loads(self.values_json or "{}")
            variables.update(values)
            return values
        model, allowed = self._safe_model()
        model = model.with_user(conversation.connection_id.technical_user_id).with_company(conversation.company_id)
        domain = safe_eval(self.domain_json or "[]", {"variables": variables}, nocopy=True)
        if self.action_type == "search":
            records = model.search(domain, limit=20)
            safe_fields = self.field_ids.filtered(lambda f: f.name in allowed.mapped("read_field_ids.name")).mapped("name")
            result = records.read(safe_fields)
        elif self.action_type in ("create", "write"):
            values = json.loads(self.values_json or "{}")
            permitted = allowed.mapped("write_field_ids.name")
            if set(values) - set(permitted):
                raise AccessError(_("One or more fields are not allowed."))
            if self.action_type == "create":
                result = model.create(values).id
            else:
                records = model.search(domain, limit=1)
                result = records.write(values)
        else:
            action = allowed.filtered(lambda a: a.method_name == self.method_name)
            if not action:
                raise AccessError(_("This method is not whitelisted."))
            result = action.execute(model, message, json.loads(self.values_json or "{}"))
        variables[self.result_variable] = result
        return result


class MessagingAllowedAction(models.Model):
    _name = "rb.messaging.allowed.action"
    _description = "Messaging Allowed Action"

    name = fields.Char(required=True)
    model_name = fields.Char(required=True, index=True)
    method_name = fields.Char()
    handler = fields.Char(help="Name of a registered safe handler.")
    read_field_ids = fields.Many2many("ir.model.fields", "rb_msg_allowed_read_field_rel")
    write_field_ids = fields.Many2many("ir.model.fields", "rb_msg_allowed_write_field_rel")
    active = fields.Boolean(default=True)

    def execute(self, model, message, values):
        self.ensure_one()
        handler = getattr(model, self.handler or "", None)
        if not handler or not (self.handler or "").startswith("_rb_messaging_"):
            raise AccessError(_("Invalid safe handler."))
        return handler(message, values)


class MessagingSession(models.Model):
    _name = "rb.messaging.session"
    _description = "Messaging Session"

    conversation_id = fields.Many2one("rb.messaging.conversation", required=True, ondelete="cascade")
    workflow_id = fields.Many2one("rb.messaging.workflow", required=True, ondelete="cascade")
    current_step = fields.Integer(default=0)
    variables_json = fields.Text(default="{}")
    expires_at = fields.Datetime()
    processed_message_ids = fields.Many2many("rb.messaging.message")

    def get_variables(self):
        self.ensure_one()
        return json.loads(self.variables_json or "{}")

    def set_variables(self, variables):
        self.ensure_one()
        serializable = {k: v for k, v in variables.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
        self.variables_json = json.dumps(serializable)


class MessagingEvent(models.Model):
    _name = "rb.messaging.event"
    _description = "Incoming Messaging Event"
    _order = "create_date desc"

    connection_id = fields.Many2one("rb.messaging.connection", required=True, ondelete="cascade")
    external_id = fields.Char(required=True, index=True)
    payload_json = fields.Text(required=True, groups="telegram_ai_hub.group_messaging_technical")
    state = fields.Selection([("received", "Received"), ("done", "Done"), ("failed", "Failed")], default="received", index=True)
    attempts = fields.Integer(default=0)
    error_message = fields.Text()
    _sql_constraints = [("event_unique", "unique(connection_id, external_id)", "Event already received.")]

    def init(self):
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS rb_messaging_event_connection_external_uniq "
            "ON rb_messaging_event (connection_id, external_id)"
        )

    def process_normalized(self, normalized):
        self.ensure_one()
        self.attempts += 1
        identity = self.env["rb.messaging.identity"].search([
            ("channel_id", "=", self.connection_id.channel_id.id),
            ("external_id", "=", str(normalized["sender_id"])),
            ("company_id", "=", self.connection_id.company_id.id),
        ], limit=1)
        if not identity:
            identity = self.env["rb.messaging.identity"].create({
                "name": normalized.get("sender_name") or str(normalized["sender_id"]),
                "channel_id": self.connection_id.channel_id.id,
                "external_id": str(normalized["sender_id"]),
                "chat_id": str(normalized.get("chat_id") or normalized["sender_id"]),
                "username": normalized.get("username"),
                "language": normalized.get("language"),
                "company_id": self.connection_id.company_id.id,
            })
        conversation = self.env["rb.messaging.conversation"].search([
            ("connection_id", "=", self.connection_id.id), ("identity_id", "=", identity.id),
            ("state", "not in", ["closed"]),
        ], limit=1)
        if not conversation:
            conversation = self.env["rb.messaging.conversation"].create({
                "name": identity.name, "connection_id": self.connection_id.id, "identity_id": identity.id,
            })
        message = self.env["rb.messaging.message"].create({
            "conversation_id": conversation.id, "external_id": normalized["message_id"],
            "direction": "in", "body": normalized.get("body", ""), "status": "delivered",
            "payload_json": self.payload_json,
        })
        conversation.write({"last_message_at": fields.Datetime.now(), "unread_count": conversation.unread_count + 1})
        command = (message.body or "").strip().split(" ", 1)[0].lower()
        if command in ("/bot", "/resume"):
            conversation.action_resume_bot()
            conversation.connection_id.send_message(
                conversation,
                _("The automated assistant is active again. You can continue your requests."),
            )
            self.state = "done"
            return message
        workflows = self.env["rb.messaging.workflow"].search([
            ("active", "=", True), ("company_id", "=", conversation.company_id.id)
        ], order="sequence")
        if conversation.bot_active:
            for workflow in workflows:
                if workflow.matches(message):
                    workflow.execute(message)
                    break
        self.state = "done"
        return message


class MessagingAudit(models.Model):
    _name = "rb.messaging.audit"
    _description = "Messaging Audit Log"
    _order = "create_date desc"

    message_id = fields.Many2one("rb.messaging.message", ondelete="set null")
    conversation_id = fields.Many2one("rb.messaging.conversation", ondelete="set null")
    workflow_id = fields.Many2one("rb.messaging.workflow", ondelete="set null")
    step_id = fields.Many2one("rb.messaging.workflow.step", ondelete="set null")
    user_id = fields.Many2one("res.users")
    result = fields.Selection([("success", "Success"), ("failure", "Failure")], required=True)
    duration_ms = fields.Integer()
    error_message = fields.Text()
    company_id = fields.Many2one("res.company", required=True)

    @api.model
    def create_success(self, message, step, duration):
        return self.create(self._values(message, step, "success", duration))

    @api.model
    def create_failure(self, message, step, error, duration):
        values = self._values(message, step, "failure", duration)
        values["error_message"] = str(error)[:2000]
        return self.create(values)

    def _values(self, message, step, result, duration):
        return {
            "message_id": message.id, "conversation_id": message.conversation_id.id,
            "workflow_id": step.workflow_id.id, "step_id": step.id,
            "user_id": message.connection_id.technical_user_id.id, "result": result,
            "duration_ms": int(duration * 1000), "company_id": message.company_id.id,
        }
