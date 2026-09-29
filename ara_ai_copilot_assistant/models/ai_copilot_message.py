# -*- coding: utf-8 -*-
import json
from odoo import models, fields, api


class AiCopilotMessage(models.Model):
    _name = 'ai.copilot.message'
    _description = 'AI Copilot Message'
    _order = 'create_date asc, id asc'

    thread_id = fields.Many2one('ai.copilot.thread', string='Thread', required=True, ondelete='cascade', index=True)
    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
        ('tool', 'Tool'),
    ], string='Role', required=True, default='user')

    content = fields.Text(string='Message Content', default='')
    tool_calls_json = fields.Text(string='Tool Calls JSON')
    action_proposal_json = fields.Text(string='Action Proposal JSON')
    approval_state = fields.Selection([
        ('none', 'No Approval Required'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved & Executed'),
        ('rejected', 'Rejected'),
    ], string='Approval State', default='none', index=True)

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'ai_copilot_message_attachment_rel',
        'message_id',
        'attachment_id',
        string='Multimodal Attachments'
    )

    client_action_json = fields.Text(string='Client Action Payload (e.g. Navigation)')

    def to_dict(self):
        """Converts message to frontend-friendly dictionary."""
        self.ensure_one()
        attachments_data = []
        for att in self.attachment_ids:
            attachments_data.append({
                'id': att.id,
                'name': att.name,
                'mimetype': att.mimetype,
                'url': f"/web/content/{att.id}?download=true",
            })

        proposal = None
        if self.action_proposal_json:
            try:
                proposal = json.loads(self.action_proposal_json)
            except Exception:
                proposal = None

        client_action = None
        if self.client_action_json:
            try:
                client_action = json.loads(self.client_action_json)
            except Exception:
                client_action = None

        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'approval_state': self.approval_state,
            'proposal': proposal,
            'client_action': client_action,
            'attachments': attachments_data,
            'create_date': fields.Datetime.to_string(self.create_date),
        }
