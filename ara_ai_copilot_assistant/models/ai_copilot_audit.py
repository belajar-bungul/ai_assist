# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AiCopilotAudit(models.Model):
    _name = 'ai.copilot.audit'
    _description = 'AI Copilot Action Audit Log'
    _order = 'create_date desc, id desc'

    user_id = fields.Many2one('res.users', string='Executed By', default=lambda self: self.env.user, required=True, index=True)
    action_type = fields.Selection([
        ('create', 'Record Creation'),
        ('update', 'Record Update'),
        ('execute_action', 'Workflow Action'),
        ('send_email', 'Send Email'),
        ('delete', 'Record Deletion'),
    ], string='Action Type', required=True)

    model_name = fields.Char(string='Target Model', index=True)
    res_id = fields.Integer(string='Target Record ID')
    summary = fields.Char(string='Action Summary', required=True)
    payload = fields.Text(string='Raw Proposal Data')
    status = fields.Selection([
        ('success', 'Executed Successfully'),
        ('failed', 'Execution Failed'),
        ('rejected', 'Rejected by User'),
    ], string='Status', default='success', required=True)

    result = fields.Text(string='Execution Output')
    error_message = fields.Text(string='Error Details')
