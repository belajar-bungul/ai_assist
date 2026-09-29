# -*- coding: utf-8 -*-
import json
import logging
import time
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AiCopilotProvider(models.Model):
    _name = 'ai.copilot.provider'
    _description = 'AI Copilot Provider Configuration'
    _order = 'is_default desc, id asc'

    name = fields.Char(string='Provider Name', required=True)
    provider_type = fields.Selection([
        ('gemini', 'Google Gemini'),
        ('openai', 'OpenAI'),
        ('claude', 'Anthropic Claude'),
        ('nvidia', 'NVIDIA NIM'),
        ('openrouter', 'OpenRouter'),
    ], string='Provider Type', required=True, default='gemini')

    api_key = fields.Char(string='API Key', help='Secret API Key from provider', copy=False)
    api_base = fields.Char(string='API Base URL', help='Leave blank to use standard official endpoint')
    model = fields.Char(string='Model Name', required=True, default='gemini-flash-latest',
                        help='E.g. gemini-flash-latest, gemini-flash-lite-latest, gpt-4o, claude-3-7-sonnet-20250219')
    temperature = fields.Float(string='Temperature', default=0.2, help='Lower values (0.1 - 0.3) provide more factual Odoo query results')
    max_tokens = fields.Integer(string='Max Tokens', default=4096)
    is_active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Default Provider', default=False)
    is_tested = fields.Boolean(string='Connection Tested', default=False, help='Indicates if connection test was successful')
    last_tested_date = fields.Datetime(string='Last Tested On')
    supports_multimodal = fields.Boolean(string='Supports Multimodal (Images/PDFs)', default=True)
    supports_tools = fields.Boolean(string='Supports Tool Calling', default=True)

    @api.constrains('name')
    def _check_name_unique(self):
        for rec in self:
            if self.search_count([('name', '=', rec.name), ('id', '!=', rec.id)]) > 0:
                raise ValidationError(_("Provider name must be unique!"))

    @api.onchange('provider_type')
    def _onchange_provider_type(self):
        defaults = {
            'gemini': {
                'model': 'gemini-flash-latest',
                'api_base': 'https://generativelanguage.googleapis.com/v1beta/openai',
            },
            'openai': {
                'model': 'gpt-4o',
                'api_base': 'https://api.openai.com/v1',
            },
            'claude': {
                'model': 'claude-3-7-sonnet-20250219',
                'api_base': 'https://api.anthropic.com/v1',
            },
            'nvidia': {
                'model': 'meta/llama-3.1-70b-instruct',
                'api_base': 'https://integrate.api.nvidia.com/v1',
            },
            'openrouter': {
                'model': 'deepseek/deepseek-r1',
                'api_base': 'https://openrouter.ai/api/v1',
            },
        }
        if self.provider_type in defaults:
            self.model = defaults[self.provider_type]['model']
            self.api_base = defaults[self.provider_type]['api_base']

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_default'):
                self.search([('is_default', '=', True)]).write({'is_default': False})
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('is_default'):
            self.search([('is_default', '=', True), ('id', 'not in', self.ids)]).write({'is_default': False})
        return super().write(vals)

    def action_set_as_default(self):
        self.ensure_one()
        self.search([]).write({'is_default': False})
        self.write({'is_default': True, 'is_active': True})
        return True

    @api.model
    def get_default_provider(self):
        provider = self.search([('is_default', '=', True), ('is_active', '=', True)], limit=1)
        if not provider:
            provider = self.search([('is_active', '=', True)], limit=1)
        if not provider:
            # Fallback create default Gemini provider
            provider = self.create({
                'name': 'Google Gemini',
                'provider_type': 'gemini',
                'model': 'gemini-2.5-flash',
                'api_base': 'https://generativelanguage.googleapis.com/v1beta/openai',
                'is_default': True,
                'is_active': True,
            })
        return provider

    def _get_effective_base_url(self):
        if self.api_base and self.api_base.strip():
            return self.api_base.strip().rstrip('/')
        if self.provider_type == 'gemini':
            return 'https://generativelanguage.googleapis.com/v1beta/openai'
        elif self.provider_type == 'openai':
            return 'https://api.openai.com/v1'
        elif self.provider_type == 'claude':
            return 'https://api.anthropic.com/v1'
        elif self.provider_type == 'nvidia':
            return 'https://integrate.api.nvidia.com/v1'
        elif self.provider_type == 'openrouter':
            return 'https://openrouter.ai/api/v1'
        return 'https://api.openai.com/v1'

    def action_test_connection(self):
        self.ensure_one()
        if not self.api_key:
            self.write({'is_tested': False})
            raise UserError(_("Please provide an API Key first before testing the connection."))

        try:
            test_message = [{"role": "user", "content": "Respond with 'OK' only."}]
            reply = self.generate_completion(test_message, max_tokens=10)
            if reply and ('content' in reply or 'text' in reply):
                self.write({
                    'is_tested': True,
                    'last_tested_date': fields.Datetime.now(),
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("Connection Successful!"),
                        'message': _("Successfully connected to %s (%s). Response: %s") % (
                            self.name, self.model, reply.get('content', 'OK')
                        ),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self.write({'is_tested': False})
                raise UserError(_("Received empty response from %s") % self.name)
        except Exception as e:
            self.write({'is_tested': False})
            _logger.exception("AI Provider Test Connection failed: %s", str(e))
            raise UserError(_("Connection test failed: %s") % str(e))

    @api.model
    def get_tested_providers(self):
        """Returns active providers that have passed connection test."""
        tested = self.search([
            ('is_active', '=', True),
            ('is_tested', '=', True),
            ('api_key', '!=', False),
        ], order='is_default desc, id asc')

        # Fallback: if no provider is marked tested yet, return active providers that have an API key or default provider
        if not tested:
            tested = self.search([
                ('is_active', '=', True),
                ('api_key', '!=', False),
            ], order='is_default desc, id asc')
        if not tested:
            tested = self.search([('is_active', '=', True)], limit=1)
        return tested

    def generate_completion(self, messages, tools=None, temperature=None, max_tokens=None):
        """
        Sends chat completion request to the active AI provider.
        Supports tool calling and multimodal contents.
        Returns a dict:
        {
            'content': 'Response text',
            'tool_calls': [
                {
                    'id': 'call_xxx',
                    'name': 'tool_name',
                    'arguments': {...}
                }
            ]
        }
        """
        self.ensure_one()
        if not self.api_key:
            raise UserError(_("API Key is missing for AI Provider '%s'. Please configure it in Copilot Settings.") % self.name)

        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens
        base_url = self._get_effective_base_url()

        if self.provider_type == 'claude':
            return self._call_anthropic(messages, tools, temp, tokens, base_url)
        else:
            return self._call_openai_compatible(messages, tools, temp, tokens, base_url)

    def _call_openai_compatible(self, messages, tools, temperature, max_tokens, base_url):
        candidate_models = [self.model]
        if self.provider_type == 'gemini':
            for fb in ['gemini-flash-latest', 'gemini-flash-lite-latest', 'gemini-pro-latest']:
                if fb not in candidate_models:
                    candidate_models.append(fb)
        elif self.provider_type == 'openai':
            for fb in ['gpt-4o-mini', 'gpt-4o']:
                if fb not in candidate_models:
                    candidate_models.append(fb)

        last_error = None
        for current_model in candidate_models:
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key.strip()}",
                "Content-Type": "application/json",
            }
            if self.provider_type == 'openrouter':
                headers["HTTP-Referer"] = "https://www.arasoft.id"
                headers["X-Title"] = "Ara Odoo AI Copilot"

            payload = {
                "model": current_model,
                "messages": messages,
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
            }

            if tools and self.supports_tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            for attempt in range(2):
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=60)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        choices = res_json.get("choices", [])
                        if not choices:
                            return {"content": "", "tool_calls": []}

                        choice = choices[0]
                        msg = choice.get("message", {})
                        content = msg.get("content") or ""
                        raw_tool_calls = msg.get("tool_calls", [])

                        tool_calls = []
                        for tc in raw_tool_calls:
                            func = tc.get("function", {})
                            args = func.get("arguments", "{}")
                            if isinstance(args, str):
                                try:
                                    parsed_args = json.loads(args)
                                except Exception:
                                    parsed_args = {}
                            else:
                                parsed_args = args

                            tool_calls.append({
                                "id": tc.get("id"),
                                "name": func.get("name"),
                                "arguments": parsed_args,
                            })

                        # If this fallback succeeded and differs from self.model, log success
                        if current_model != self.model:
                            _logger.info("Successfully used fallback model '%s' instead of busy '%s'", current_model, self.model)

                        return {
                            "content": content,
                            "tool_calls": tool_calls,
                            "raw_message": msg,
                            "usage": res_json.get("usage", {}),
                        }

                    # If 503 (High Demand) or 429 (Rate Limit), wait briefly and retry or try fallback
                    if resp.status_code in (503, 429):
                        _logger.warning("AI Provider '%s' with model '%s' returned HTTP %s (busy). Attempting fallback...",
                                        self.name, current_model, resp.status_code)
                        time.sleep(1.2)
                        continue

                    # Other client errors (400, 401, 403)
                    err_msg = resp.text
                    try:
                        err_json = resp.json()
                        if 'error' in err_json:
                            err_msg = err_json['error'].get('message', resp.text)
                    except Exception:
                        pass
                    last_error = _("AI Provider Error (%s): %s") % (resp.status_code, err_msg)
                    break

                except requests.exceptions.RequestException as e:
                    _logger.warning("Connection failure contacting %s (%s): %s", self.name, current_model, str(e))
                    last_error = _("Network request failed: %s") % str(e)
                    time.sleep(1)

        if last_error:
            raise UserError(last_error)
        raise UserError(_("AI Server (%s) is currently experiencing temporary high traffic (HTTP 503). Please retry in a few moments.") % self.name)

    def _call_anthropic(self, messages, tools, temperature, max_tokens, base_url):
        url = f"{base_url}/messages"
        headers = {
            "x-api-key": self.api_key.strip(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Separate system messages from user/assistant messages for Claude
        system_prompt = ""
        filtered_messages = []
        for m in messages:
            if m.get("role") == "system":
                system_prompt += (m.get("content") or "") + "\n\n"
            else:
                filtered_messages.append(m)

        payload = {
            "model": self.model,
            "messages": filtered_messages,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        }
        if system_prompt.strip():
            payload["system"] = system_prompt.strip()

        if tools and self.supports_tools:
            # Transform OpenAI format tools to Claude format
            claude_tools = []
            for t in tools:
                if t.get("type") == "function":
                    fn = t.get("function", {})
                    claude_tools.append({
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                    })
            if claude_tools:
                payload["tools"] = claude_tools

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code != 200:
                err_msg = resp.text
                try:
                    err_json = resp.json()
                    if 'error' in err_json:
                        err_msg = err_json['error'].get('message', resp.text)
                except Exception:
                    pass
                raise UserError(_("Anthropic API Error (%s): %s") % (resp.status_code, err_msg))

            res_json = resp.json()
            contents = res_json.get("content", [])
            text_parts = []
            tool_calls = []

            for block in contents:
                b_type = block.get("type")
                if b_type == "text":
                    text_parts.append(block.get("text", ""))
                elif b_type == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "arguments": block.get("input", {}),
                    })

            return {
                "content": "\n".join(text_parts),
                "tool_calls": tool_calls,
                "usage": res_json.get("usage", {}),
            }

        except requests.exceptions.RequestException as e:
            _logger.exception("Failed to connect to Anthropic: %s", str(e))
            raise UserError(_("Network error contacting Anthropic Claude: %s") % str(e))
