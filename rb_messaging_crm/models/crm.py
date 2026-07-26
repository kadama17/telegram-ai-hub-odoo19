from odoo import _, models
from odoo.exceptions import ValidationError


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def _rb_messaging_create_lead(self, message, values):
        allowed = {"name", "contact_name", "partner_name", "email_from", "phone", "description", "team_id", "user_id"}
        if set(values) - allowed:
            raise ValidationError(_("Unsupported CRM field."))
        values.setdefault("name", _("Lead from %s") % message.conversation_id.identity_id.name)
        values.setdefault("phone", message.conversation_id.identity_id.external_id)
        lead = self.create(values)
        message.conversation_id.message_post(body=_("CRM lead %s created.") % lead.display_name)
        return {"id": lead.id, "name": lead.display_name}

