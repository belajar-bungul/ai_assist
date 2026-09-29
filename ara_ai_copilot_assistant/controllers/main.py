# -*- coding: utf-8 -*-
import base64
import json
import logging
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class AraCopilotController(http.Controller):

    @http.route('/ara_copilot/init', type='jsonrpc', auth='user')
    def copilot_init(self, context_info=None):
        """Initializes Copilot state for the current session."""
        env = request.env
        threads = env['ai.copilot.thread'].search(
            [('user_id', '=', env.user.id), ('active', '=', True)],
            order='is_favorite desc, write_date desc, id desc',
            limit=30
        )
        threads_data = [{
            'id': t.id,
            'name': t.name,
            'is_favorite': t.is_favorite,
            'write_date': str(t.write_date)
        } for t in threads]

        active_thread = None
        if threads:
            active_thread = threads[0]
        else:
            active_thread = env['ai.copilot.thread'].create({
                'name': _('New Chat'),
                'user_id': env.user.id,
            })
            threads_data.append({
                'id': active_thread.id,
                'name': active_thread.name,
                'is_favorite': active_thread.is_favorite,
                'write_date': str(active_thread.write_date)
            })

        # Fetch tested providers for model switcher dropdown
        tested_providers = env['ai.copilot.provider'].get_tested_providers()
        available_providers = [{
            'id': p.id,
            'name': p.name,
            'model': p.model,
            'type': p.provider_type,
            'is_default': p.is_default,
        } for p in tested_providers]

        # Active provider: thread-specific or default
        provider = active_thread._get_provider() if active_thread else env['ai.copilot.provider'].get_default_provider()
        has_api_key = bool(provider and provider.api_key)

        return {
            'threads': threads_data,
            'active_thread_id': active_thread.id,
            'active_thread_data': active_thread.get_thread_data(),
            'provider': {
                'id': provider.id if provider else False,
                'name': provider.name if provider else 'None',
                'model': provider.model if provider else 'None',
                'type': provider.provider_type if provider else 'none',
                'has_api_key': has_api_key,
            },
            'available_providers': available_providers,
            'user_name': env.user.name,
            'company_name': env.company.name,
            'currency_symbol': env.company.currency_id.symbol,
        }

    @http.route('/ara_copilot/send_message', type='jsonrpc', auth='user')
    def copilot_send_message(self, thread_id, content, attachment_ids=None, context_info=None):
        """Processes a chat message from the user."""
        env = request.env
        thread = env['ai.copilot.thread'].browse(int(thread_id))
        if not thread.exists() or thread.user_id.id != env.user.id:
            return {'error': _("Thread not found or permission denied.")}

        try:
            res = thread.send_user_message(content, attachment_ids=attachment_ids, context_info=context_info)
            return res
        except Exception as e:
            _logger.exception("AI Copilot Message processing error: %s", str(e))
            return {'error': str(e)}

    @http.route('/ara_copilot/create_thread', type='jsonrpc', auth='user')
    def copilot_create_thread(self, name=None):
        """Creates a new conversation thread."""
        env = request.env
        thread = env['ai.copilot.thread'].create({
            'name': name or _('New Conversation'),
            'user_id': env.user.id,
        })
        return {
            'thread_id': thread.id,
            'thread_data': thread.get_thread_data(),
        }

    @http.route('/ara_copilot/get_thread', type='jsonrpc', auth='user')
    def copilot_get_thread(self, thread_id):
        """Loads messages of a specific thread."""
        env = request.env
        thread = env['ai.copilot.thread'].browse(int(thread_id))
        if not thread.exists() or thread.user_id.id != env.user.id:
            return {'error': _("Thread not found.")}
        return thread.get_thread_data()

    @http.route('/ara_copilot/delete_thread', type='jsonrpc', auth='user')
    def copilot_delete_thread(self, thread_id, password=""):
        """Deletes a conversation thread after verifying current user password."""
        env = request.env
        if not password:
            return {'error': _("Password is required to delete the conversation session.")}

        # Verify current user's password
        try:
            env.user._check_credentials({'type': 'password', 'password': password}, {'interactive': True})
        except Exception:
            return {'error': _("Incorrect password. Conversation deletion rejected.")}

        thread = env['ai.copilot.thread'].browse(int(thread_id))
        if thread.exists() and thread.user_id.id == env.user.id:
            thread.unlink()
            return {'success': True}
        return {'error': _("Thread not found or permission denied.")}

    @http.route('/ara_copilot/toggle_favorite_thread', type='jsonrpc', auth='user')
    def copilot_toggle_favorite_thread(self, thread_id):
        """Toggles favorite status of a conversation thread."""
        env = request.env
        thread = env['ai.copilot.thread'].browse(int(thread_id))
        if thread.exists() and thread.user_id.id == env.user.id:
            thread.is_favorite = not thread.is_favorite
            return {'success': True, 'is_favorite': thread.is_favorite}
        return {'error': _("Thread not found.")}

    @http.route('/ara_copilot/set_thread_provider', type='jsonrpc', auth='user')
    def copilot_set_thread_provider(self, thread_id, provider_id):
        """Switches AI model provider for the conversation thread."""
        env = request.env
        thread = env['ai.copilot.thread'].browse(int(thread_id))
        if not thread.exists() or thread.user_id.id != env.user.id:
            return {'error': _("Thread not found.")}
        provider = env['ai.copilot.provider'].browse(int(provider_id))
        if not provider.exists() or not provider.is_active:
            return {'error': _("Provider not found or inactive.")}
        thread.provider_id = provider.id
        return {
            'success': True,
            'provider': {
                'id': provider.id,
                'name': provider.name,
                'model': provider.model,
                'type': provider.provider_type,
                'has_api_key': bool(provider.api_key),
            }
        }

    @http.route('/ara_copilot/get_available_providers', type='jsonrpc', auth='user')
    def copilot_get_available_providers(self):
        """Returns verified AI providers that passed connection test."""
        providers = request.env['ai.copilot.provider'].get_tested_providers()
        return [{
            'id': p.id,
            'name': p.name,
            'model': p.model,
            'type': p.provider_type,
            'is_default': p.is_default,
        } for p in providers]

    @http.route('/ara_copilot/search_threads', type='jsonrpc', auth='user')
    def copilot_search_threads(self, query=""):
        """Searches conversation threads by title and message contents."""
        env = request.env
        q = (query or '').strip()
        if not q:
            threads = env['ai.copilot.thread'].search(
                [('user_id', '=', env.user.id), ('active', '=', True)],
                order='is_favorite desc, write_date desc, id desc',
                limit=30
            )
        else:
            # 1. Threads matching title
            name_threads = env['ai.copilot.thread'].search([
                ('user_id', '=', env.user.id),
                ('active', '=', True),
                ('name', 'ilike', q)
            ], limit=30)

            # 2. Threads containing matching message contents
            matching_msgs = env['ai.copilot.message'].search([
                ('thread_id.user_id', '=', env.user.id),
                ('thread_id.active', '=', True),
                ('content', 'ilike', q)
            ], limit=50)
            msg_threads = matching_msgs.mapped('thread_id')

            all_threads = (name_threads | msg_threads).sorted(
                key=lambda t: (not t.is_favorite, -(t.write_date or t.create_date).timestamp())
            )
            threads = all_threads[:30]

        return [{
            'id': t.id,
            'name': t.name,
            'is_favorite': t.is_favorite,
            'write_date': str(t.write_date)
        } for t in threads]

    @http.route('/ara_copilot/approve_proposal', type='jsonrpc', auth='user')
    def copilot_approve_proposal(self, thread_id, message_id):
        """Executes an approved proposal."""
        env = request.env
        thread = env['ai.copilot.thread'].browse(int(thread_id))
        if not thread.exists() or thread.user_id.id != env.user.id:
            return {'error': _("Thread not found.")}
        try:
            return thread.action_approve_proposal(message_id)
        except Exception as e:
            _logger.exception("Error executing proposal approval: %s", str(e))
            return {'error': str(e)}

    @http.route('/ara_copilot/reject_proposal', type='jsonrpc', auth='user')
    def copilot_reject_proposal(self, thread_id, message_id):
        """Rejects a proposed action."""
        env = request.env
        thread = env['ai.copilot.thread'].browse(int(thread_id))
        if not thread.exists() or thread.user_id.id != env.user.id:
            return {'error': _("Thread not found.")}
        try:
            return thread.action_reject_proposal(message_id)
        except Exception as e:
            _logger.exception("Error rejecting proposal: %s", str(e))
            return {'error': str(e)}

    @http.route('/ara_copilot/upload_attachment', type='jsonrpc', auth='user')
    def copilot_upload_attachment(self, name, data_base64, mimetype=None):
        """Uploads an attachment file for multimodal interaction."""
        env = request.env
        try:
            # Strip data url prefix if present
            if ',' in data_base64:
                data_base64 = data_base64.split(',', 1)[1]

            attachment = env['ir.attachment'].create({
                'name': name,
                'datas': data_base64,
                'mimetype': mimetype or 'application/octet-stream',
                'res_model': 'ai.copilot.thread',
                'res_id': 0,
            })
            return {
                'id': attachment.id,
                'name': attachment.name,
                'mimetype': attachment.mimetype,
                'url': f"/web/content/{attachment.id}",
            }
        except Exception as e:
            _logger.exception("Failed to upload attachment: %s", str(e))
            return {'error': str(e)}
