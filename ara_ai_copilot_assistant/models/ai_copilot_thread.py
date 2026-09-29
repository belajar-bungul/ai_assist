# -*- coding: utf-8 -*-
import base64
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiCopilotThread(models.Model):
    _name = 'ai.copilot.thread'
    _description = 'AI Copilot Conversation Thread'
    _order = 'is_favorite desc, write_date desc, id desc'

    name = fields.Char(string='Thread Title', default=lambda self: _('New Conversation'), required=True)
    user_id = fields.Many2one('res.users', string='Owner', default=lambda self: self.env.user, required=True, index=True)
    provider_id = fields.Many2one('ai.copilot.provider', string='AI Provider', help='AI Provider used for this conversation')
    message_ids = fields.One2many('ai.copilot.message', 'thread_id', string='Messages')
    active = fields.Boolean(string='Active', default=True)
    is_favorite = fields.Boolean(string='Favorite', default=False, index=True)

    last_context_model = fields.Char(string='Last Context Model')
    last_context_res_id = fields.Integer(string='Last Context Record ID')

    @api.model
    def get_or_create_active_thread(self, thread_id=None):
        """Returns existing thread or creates a new one for current user."""
        if thread_id:
            thread = self.search([('id', '=', int(thread_id)), ('user_id', '=', self.env.user.id)], limit=1)
            if thread:
                return thread

        # Find latest thread with messages < 50
        thread = self.search([('user_id', '=', self.env.user.id), ('active', '=', True)], limit=1)
        if not thread:
            thread = self.create({
                'name': _('Chat %s') % fields.Date.today(),
                'user_id': self.env.user.id,
            })
        return thread

    def _get_provider(self):
        if self.provider_id and self.provider_id.is_active:
            return self.provider_id
        return self.env['ai.copilot.provider'].get_default_provider()

    def _build_system_prompt(self, context_info=None):
        company = self.env.company
        user = self.env.user
        lang = user.lang or 'en_US'
        is_admin = user._is_admin() or user.has_group('base.group_system')
        has_hr_manager = user.has_group('hr.group_hr_manager')
        has_accounting = user.has_group('account.group_account_user') or user.has_group('account.group_account_manager') or is_admin

        roles = []
        if is_admin:
            roles.append("System Administrator (Full access to all models, records, and confidential HR/Financial data)")
        if has_hr_manager:
            roles.append("HR Manager (Authorized access to employee salaries, wages, and HR records)")
        if has_accounting:
            roles.append("Accounting / Financial Officer (Authorized access to General Ledger, P&L, and balance sheets)")
        if not roles:
            roles.append("Standard User (Standard restricted permissions)")
        user_roles_str = ", ".join(roles)

        system_prompt = f"""You are Ara Copilot, an enterprise-grade AI Assistant embedded directly inside Odoo 19 ERP.
You are communicating with {user.name} at company '{company.name}' (Currency: {company.currency_id.name}).
Current User Roles & Privileges: {user_roles_str} (Is Administrator: {is_admin}).

DYNAMIC LANGUAGE MIRRORING (CRITICAL & STRICT RULE):
- You MUST detect and strictly mirror the language used by the user in each prompt:
  * If the user writes in Indonesian (Bahasa Indonesia), you MUST reply entirely in natural, professional Indonesian.
  * If the user writes in English, you MUST reply entirely in natural, professional English.
  * If the user writes in any other language (e.g. Spanish, French, German, Arabic, Japanese, Chinese), you MUST reply in that same language.
- DO NOT mix languages unless specifically requested by the user.

Your capabilities:
1. Search & Read: Query any Odoo model (sale.order, account.move, res.partner, product.template, product.product, stock.picking, crm.lead, hr.employee, mrp.production, etc.) using technical tools.
2. Financial Reporting: Instantly generate Profit & Loss, Balance Sheet, Aged Receivables, and Aged Payables using 'odoo_financial_report'.
3. Safe Actions & Mutations: Whenever the user wants to CREATE or UPDATE records, SEND an email, or EXECUTE a workflow button, use the respective proposal tools ('odoo_propose_record_create', 'odoo_propose_record_update', 'odoo_propose_execute_action', 'odoo_propose_send_email'). This guarantees a safe user confirmation step before changes take effect.
4. Smart Navigation: If the user asks to open or view a record or list, call 'odoo_navigate'.
5. Document Search: Search uploaded attachments and documents with 'odoo_semantic_search_docs'.

CRITICAL FORMATTING & LINKING RULES (STRICT):
- ABSOLUTELY NEVER output raw HTML tags (e.g. <p>, </p>, <table>, <tr>, <td>, <br>, <div>). Any raw HTML tags will break the interface.
- ALWAYS use pure standard Markdown:
  * Bold: **text**
  * Italic: *text*
  * Lists: - item
  * Headings: ### Heading
  * Clean markdown tables:
    | Column 1 | Column 2 | Record Reference |
    | --- | --- | --- |
- RECORD REFERENCE / PROOF LINKS (MANDATORY):
  Whenever you search, create, update, or reference ANY Odoo record, you MUST provide a clickable proof link in this exact format:
  [Record Name (#ID) ↗](/#id={{ID}}&model={{MODEL}}&view_type=form)
  Examples:
  * [PT ABC (#14) ↗](/#id=14&model=res.partner&view_type=form)
  * [SO0045 (#8) ↗](/#id=8&model=sale.order&view_type=form)
  * [Apple Pie (#102) ↗](/#id=102&model=product.product&view_type=form)

PROACTIVE CRUD & DOCUMENT CREATION INSTRUCTIONS:
- When the user asks to CREATE or UPDATE a document or record (e.g. Sales Order/Quotation 'sale.order', Invoice 'account.move', Purchase Order 'purchase.order', Contact 'res.partner', Task 'project.task', Product, etc.):
  1. DO NOT STOP at just searching records! Always proceed to call 'odoo_propose_record_create' or 'odoo_propose_record_update'!
  2. For Sales Order ('sale.order'):
     * Set 'partner_id': String name of the contact (e.g. 'PT ABC') or contact ID. If contact doesn't exist, our system automatically creates it!
     * Set 'order_line': List of order lines, e.g. [{{'product_id': 'Apple Pie', 'product_uom_qty': 5, 'price_unit': 30.0}}].
  3. When searching for records, ALWAYS specify domain or query (e.g. query='Apple Pie' or domain=[['name', 'ilike', 'Apple Pie']]).
  4. Always explain what proposal you generated in the user's detected language, and invite them to review and approve via the proposal card.
SECURITY & ROLE-BASED ACCESS CONTROL (STRICT ENFORCEMENT):
- Ara Copilot strictly adheres to Odoo's native ORM security, Access Control Lists (ir.model.access), and Record Rules.
- You operate under the exact permissions of the current logged-in user: {user.name} ({user_roles_str}).
- Odoo 19 Data Structure & Permission Rules:
  * In Odoo 19, employee information and salaries/wages are stored in model 'hr.employee' (fields: 'name', 'wage', 'contract_wage', 'hourly_cost', 'job_title').
  * The 'wage' and 'contract_wage' fields are restricted by Odoo ORM to HR Managers and Administrators.
  * If the user is an Administrator ({is_admin}) or has the authorized role (such as HR Manager for salaries, or Accounting for financial reports):
    They HAVE FULL PERMISSION. You MUST execute the tool (e.g. 'odoo_search_read' on 'hr.employee' with fields ['name', 'wage', 'job_title']) and provide the requested information directly!
  * ONLY refuse and state "Access Denied" if an executed tool actually returns an "Access Denied" error from Odoo (which happens for unauthorized users like standard sales staff).
  * If a model is not installed (e.g. returns "Model does not exist"), state that the module is not installed in this database; do NOT confuse it with an access rights restriction.
  * NEVER invent, guess, estimate, or hallucinate data that was denied by Odoo's security system.

- When summarizing financial numbers, always include the company currency ({company.currency_id.name}).
- Be concise, factual, polite, and helpful.
"""
        if context_info:
            active_model = context_info.get('resModel')
            active_id = context_info.get('resId')
            active_name = context_info.get('displayName')
            if active_model:
                system_prompt += f"\nCURRENT USER CONTEXT:\nThe user is currently looking at model '{active_model}'"
                if active_id:
                    system_prompt += f", Record ID #{active_id} ('{active_name or ''}'). You can directly reference this record if relevant to user's question."

        return system_prompt

    def send_user_message(self, content, attachment_ids=None, context_info=None):
        """
        Sends a user message to this thread, processes AI completion and tool calls,
        and returns the resulting assistant messages and actions.
        """
        self.ensure_one()
        provider = self._get_provider()
        tool_engine = self.env['ai.copilot.tool']

        # 1. Update title if this is the first message
        if len(self.message_ids) == 0 and content:
            clean_title = (content.strip()[:40] + '...') if len(content.strip()) > 40 else content.strip()
            self.name = clean_title or _('Conversation')

        # 2. Save user message
        user_msg_vals = {
            'thread_id': self.id,
            'role': 'user',
            'content': content or '',
        }
        if attachment_ids:
            user_msg_vals['attachment_ids'] = [(6, 0, attachment_ids)]
            # Also index documents for RAG
            for att_id in attachment_ids:
                self.env['ai.copilot.knowledge'].index_attachment(att_id)

        user_message = self.env['ai.copilot.message'].create(user_msg_vals)

        # 3. Assemble LLM conversation history
        messages_payload = [
            {"role": "system", "content": self._build_system_prompt(context_info)}
        ]

        # Fetch recent messages (up to 12)
        history_msgs = self.env['ai.copilot.message'].search(
            [('thread_id', '=', self.id)], order='id asc', limit=20
        )

        for m in history_msgs:
            if m.role == 'user':
                # Handle multimodal if attachments exist
                if m.attachment_ids and provider.supports_multimodal:
                    content_parts = [{"type": "text", "text": m.content or "Please analyze the attached document/image."}]
                    for att in m.attachment_ids:
                        if att.mimetype and att.mimetype.startswith('image/'):
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{att.mimetype};base64,{att.datas.decode('utf-8') if isinstance(att.datas, bytes) else att.datas}"
                                }
                            })
                        elif att.datas:
                            # Include text representation
                            try:
                                raw_txt = base64.b64decode(att.datas).decode('utf-8', errors='ignore')[:3000]
                                content_parts.append({
                                    "type": "text",
                                    "text": f"--- Attached Document: {att.name} ---\n{raw_txt}"
                                })
                            except Exception:
                                pass
                    messages_payload.append({"role": "user", "content": content_parts})
                else:
                    messages_payload.append({"role": "user", "content": m.content or ""})

            elif m.role == 'assistant':
                messages_payload.append({"role": "assistant", "content": m.content or ""})

        # 4. Fetch available tools
        tools = tool_engine.get_tools_definitions() if provider.supports_tools else None

        # 5. Agentic Multi-Step Execution Loop (up to 5 turns)
        max_turns = 5
        turn_count = 0
        assistant_content = ""
        action_proposal = None
        client_action = None
        approval_state = 'none'
        all_executed_tool_calls = []

        while turn_count < max_turns:
            turn_count += 1
            response = provider.generate_completion(messages_payload, tools=tools)
            current_content = response.get('content') or ""
            tool_calls = response.get('tool_calls') or []

            if not tool_calls:
                # LLM finished thinking and provided natural language output
                if not assistant_content:
                    assistant_content = current_content
                elif current_content:
                    assistant_content = f"{assistant_content}\n\n{current_content}"
                break

            all_executed_tool_calls.extend(tool_calls)
            has_proposal_or_nav = False

            # 1. Preserve the full assistant response from provider (with thought_signature & extra_content)
            raw_ast_msg = response.get('raw_message')
            if not raw_ast_msg:
                raw_ast_msg = {
                    "role": "assistant",
                    "content": current_content or None,
                    "tool_calls": tool_calls,
                }
            messages_payload.append(raw_ast_msg)

            # 2. Execute each tool and append tool result message
            for tc in tool_calls:
                t_name = tc.get('name')
                t_args = tc.get('arguments') or {}
                t_id = tc.get('id') or f"call_{turn_count}_{len(all_executed_tool_calls)}"

                tool_result = tool_engine.execute_tool(t_name, t_args, user_context=context_info)

                messages_payload.append({
                    "role": "tool",
                    "tool_call_id": t_id,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })

                if isinstance(tool_result, dict) and tool_result.get('is_proposal'):
                    action_proposal = tool_result
                    approval_state = 'pending'
                    has_proposal_or_nav = True
                    prop_summary = tool_result.get('summary', 'Data change proposal')
                    if current_content:
                        assistant_content = current_content
                    else:
                        assistant_content = f"I have prepared the proposal for **{prop_summary}**. Please review the details in the approval card below and click **Approve & Execute** to proceed."

                elif isinstance(tool_result, dict) and tool_result.get('client_action') == 'navigate':
                    client_action = tool_result
                    has_proposal_or_nav = True
                    if not assistant_content:
                        assistant_content = f"Navigating to {tool_result.get('title', 'page')}..."

                else:
                    # Informational tools like search_read, read_record, financial_report
                    fallback_md = self._format_tool_result_as_markdown(t_name, tool_result)
                    if not assistant_content:
                        assistant_content = fallback_md

            if has_proposal_or_nav:
                # We reached a proposed mutation or navigation, break loop to await user confirmation
                break

        if not assistant_content:
            assistant_content = "Your request has been processed."

        # 7. Save assistant message
        ast_msg_vals = {
            'thread_id': self.id,
            'role': 'assistant',
            'content': assistant_content,
            'tool_calls_json': json.dumps(all_executed_tool_calls) if all_executed_tool_calls else False,
            'action_proposal_json': json.dumps(action_proposal) if action_proposal else False,
            'approval_state': approval_state,
            'client_action_json': json.dumps(client_action) if client_action else False,
        }
        assistant_message = self.env['ai.copilot.message'].create(ast_msg_vals)

        return {
            'user_message': user_message.to_dict(),
            'assistant_message': assistant_message.to_dict(),
            'thread_id': self.id,
            'thread_name': self.name,
        }

    def action_approve_proposal(self, message_id):
        """Executes an action proposal after user explicitly approves it."""
        self.ensure_one()
        msg = self.env['ai.copilot.message'].browse(int(message_id))
        if not msg.exists() or msg.thread_id.id != self.id:
            raise UserError(_("Message not found."))

        if msg.approval_state != 'pending' or not msg.action_proposal_json:
            raise UserError(_("This action is not awaiting approval."))

        proposal = json.loads(msg.action_proposal_json)
        result = self.env['ai.copilot.tool'].execute_approved_proposal(proposal)

        msg.write({'approval_state': 'approved'})

        reply_content = f"✅ **Executed Successfully!**\n\n{result.get('message', 'Action executed safely.')}"
        if result.get('status') == 'error':
            reply_content = f"⚠️ **Execution Failed:**\n\n{result.get('message', 'An error occurred while processing data.')}"
        elif result.get('res_id') and result.get('model'):
            rec_id = result['res_id']
            m_name = result['model']
            d_name = result.get('display_name') or f"Record #{rec_id}"
            reply_content += f"\n\n🔗 **Record Reference:** [{d_name} (#{rec_id}) ↗](/#id={rec_id}&model={m_name}&view_type=form)"

        reply_msg = self.env['ai.copilot.message'].create({
            'thread_id': self.id,
            'role': 'assistant',
            'content': reply_content,
            'approval_state': 'none',
        })

        return {
            'updated_message': msg.to_dict(),
            'response_message': reply_msg.to_dict(),
            'execution_result': result,
        }

    def action_reject_proposal(self, message_id):
        """Rejects a proposed action."""
        self.ensure_one()
        msg = self.env['ai.copilot.message'].browse(int(message_id))
        if not msg.exists() or msg.thread_id.id != self.id:
            raise UserError(_("Message not found."))

        msg.write({'approval_state': 'rejected'})

        # Log rejection in audit
        proposal = {}
        if msg.action_proposal_json:
            try:
                proposal = json.loads(msg.action_proposal_json)
            except Exception:
                pass

        self.env['ai.copilot.audit'].sudo().create({
            'user_id': self.env.user.id,
            'action_type': proposal.get('action_type', 'update'),
            'model_name': proposal.get('model', ''),
            'res_id': proposal.get('res_id', 0),
            'summary': proposal.get('summary', 'Action Proposal'),
            'status': 'rejected',
            'payload': msg.action_proposal_json,
            'error_message': 'User clicked Reject button in chat.',
        })

        reply_msg = self.env['ai.copilot.message'].create({
            'thread_id': self.id,
            'role': 'assistant',
            'content': "❌ **Action canceled.** No changes were saved to the database.",
            'approval_state': 'none',
        })

        return {
            'updated_message': msg.to_dict(),
            'response_message': reply_msg.to_dict(),
        }

    def get_thread_data(self):
        """Returns messages and metadata for frontend initialization."""
        self.ensure_one()
        prov = self._get_provider()
        return {
            'id': self.id,
            'name': self.name,
            'is_favorite': self.is_favorite,
            'provider': {
                'id': prov.id if prov else False,
                'name': prov.name if prov else '',
                'model': prov.model if prov else '',
                'type': prov.provider_type if prov else '',
                'has_api_key': bool(prov and prov.api_key),
            },
            'messages': [m.to_dict() for m in self.message_ids],
        }

    def _format_tool_result_as_markdown(self, tool_name, tool_result):
        """Formats raw tool outputs into clean, high-readability markdown."""
        if not isinstance(tool_result, dict):
            return str(tool_result)

        if tool_name == 'odoo_search_read':
            records = tool_result.get('records', [])
            model = tool_result.get('model', 'record')
            total = tool_result.get('total_count', len(records))
            if not records:
                return f"🔍 No records found on model `{model}` matching the specified criteria."

            lines = [f"Found **{len(records)}** records on `{model}` (total {total}):\n"]
            # Extract printable columns
            cols = [k for k in records[0].keys() if k not in ('id', 'create_date', 'record_url', 'model')][:5]
            if not cols:
                cols = [k for k in records[0].keys() if k not in ('record_url', 'model')][:5]

            # Header row with 'Record Link'
            header_titles = [c.replace('_', ' ').title() for c in cols] + ["Record Link"]
            lines.append("| " + " | ".join(header_titles) + " |")
            lines.append("| " + " | ".join("---" for _ in header_titles) + " |")

            for r in records:
                row_vals = []
                for c in cols:
                    val = r.get(c, '')
                    if isinstance(val, dict) and 'display_name' in val:
                        val = val['display_name']
                    elif val is False or val is None:
                        val = "-"
                    row_vals.append(str(val).replace('|', '/'))

                # Link record proof
                rec_id = r.get('id')
                if rec_id:
                    row_vals.append(f"[Open #{rec_id} ↗](/#id={rec_id}&model={model}&view_type=form)")
                else:
                    row_vals.append("-")

                lines.append("| " + " | ".join(row_vals) + " |")

            return "\n".join(lines)

        elif tool_name == 'odoo_financial_report':
            rep_name = tool_result.get('report_name', 'Financial Report')
            summary = tool_result.get('summary')
            lines = [f"### 📊 {rep_name}"]
            if 'period' in tool_result:
                lines.append(f"*Period: {tool_result['period']}*")
            if 'as_of_date' in tool_result:
                lines.append(f"*As of: {tool_result['as_of_date']}*")
            lines.append("")

            if summary and isinstance(summary, dict):
                lines.append("| Financial Indicator | Amount |")
                lines.append("| --- | --- |")
                for k, v in summary.items():
                    lines.append(f"| **{k}** | `{v}` |")

            if 'invoices' in tool_result:
                invs = tool_result['invoices']
                lines.append("\n**Related Invoices:**")
                lines.append("| Invoice | Customer | Due Date | Residual Amount | Record Link |")
                lines.append("| --- | --- | --- | --- | --- |")
                for inv in invs:
                    partner = inv.get('partner_id', {})
                    p_name = partner.get('display_name', '-') if isinstance(partner, dict) else str(partner or '-')
                    inv_id = inv.get('id')
                    inv_link = f"[Open #{inv_id} ↗](/#id={inv_id}&model=account.move&view_type=form)" if inv_id else "-"
                    lines.append(f"| {inv.get('name', '-')} | {p_name} | {inv.get('invoice_date_due', '-')} | `{inv.get('amount_residual', 0):,.2f}` | {inv_link} |")

            return "\n".join(lines)

        return f"```json\n{json.dumps(tool_result, indent=2, ensure_ascii=False)}\n```"
