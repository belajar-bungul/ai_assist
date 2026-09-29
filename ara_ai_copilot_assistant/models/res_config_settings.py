# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    copilot_provider_id = fields.Many2one(
        'ai.copilot.provider',
        string='Default AI Provider',
        config_parameter='ara_ai_copilot.default_provider_id'
    )
    copilot_gemini_api_key = fields.Char(
        string='Google Gemini API Key',
        config_parameter='ara_ai_copilot.gemini_api_key'
    )
    copilot_openai_api_key = fields.Char(
        string='OpenAI API Key',
        config_parameter='ara_ai_copilot.openai_api_key'
    )
    copilot_claude_api_key = fields.Char(
        string='Claude API Key',
        config_parameter='ara_ai_copilot.claude_api_key'
    )
    copilot_openrouter_api_key = fields.Char(
        string='OpenRouter API Key',
        config_parameter='ara_ai_copilot.openrouter_api_key'
    )
    copilot_require_approval = fields.Boolean(
        string='Require Approval for Write/Action Operations',
        default=True,
        config_parameter='ara_ai_copilot.require_approval'
    )

    def set_values(self):
        super().set_values()
        # Sync API keys to corresponding providers if set
        if self.copilot_gemini_api_key:
            gemini = self.env['ai.copilot.provider'].search([('provider_type', '=', 'gemini')], limit=1)
            if gemini:
                gemini.write({'api_key': self.copilot_gemini_api_key})
        if self.copilot_openai_api_key:
            openai_p = self.env['ai.copilot.provider'].search([('provider_type', '=', 'openai')], limit=1)
            if openai_p:
                openai_p.write({'api_key': self.copilot_openai_api_key})
        if self.copilot_claude_api_key:
            claude_p = self.env['ai.copilot.provider'].search([('provider_type', '=', 'claude')], limit=1)
            if claude_p:
                claude_p.write({'api_key': self.copilot_claude_api_key})
        if self.copilot_openrouter_api_key:
            or_p = self.env['ai.copilot.provider'].search([('provider_type', '=', 'openrouter')], limit=1)
            if or_p:
                or_p.write({'api_key': self.copilot_openrouter_api_key})
