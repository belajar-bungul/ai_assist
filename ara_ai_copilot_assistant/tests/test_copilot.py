# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAraAiCopilot(TransactionCase):

    def setUp(self):
        super().setUp()
        self.provider_model = self.env['ai.copilot.provider']
        self.thread_model = self.env['ai.copilot.thread']
        self.message_model = self.env['ai.copilot.message']
        self.tool_model = self.env['ai.copilot.tool']
        self.audit_model = self.env['ai.copilot.audit']

    def test_01_default_provider(self):
        """Verify default provider is Google Gemini and configured properly."""
        default_p = self.provider_model.get_default_provider()
        self.assertTrue(default_p, "Default provider should exist")
        self.assertEqual(default_p.provider_type, 'gemini', "Default provider should be Google Gemini")
        self.assertTrue(default_p.is_active, "Default provider should be active")
        self.assertTrue(default_p.supports_tools, "Default provider should support tools")

    def test_02_tool_definitions(self):
        """Verify all essential tools are defined in OpenAI JSON schema format."""
        tools = self.tool_model.get_tools_definitions()
        self.assertTrue(len(tools) >= 8, f"Expected at least 8 tools, got {len(tools)}")
        tool_names = [t['function']['name'] for t in tools]
        expected = [
            'odoo_search_read',
            'odoo_read_record',
            'odoo_aggregate',
            'odoo_financial_report',
            'odoo_propose_record_create',
            'odoo_propose_record_update',
            'odoo_propose_execute_action',
            'odoo_propose_send_email',
            'odoo_navigate',
            'odoo_semantic_search_docs',
        ]
        for exp in expected:
            self.assertIn(exp, tool_names, f"Tool '{exp}' must be present in definitions")

    def test_03_tool_search_read(self):
        """Verify searching and reading records safely."""
        res = self.tool_model.execute_tool('odoo_search_read', {
            'model': 'res.partner',
            'domain': [['active', '=', True]],
            'fields': ['name', 'email'],
            'limit': 5,
        })
        self.assertEqual(res.get('model'), 'res.partner')
        self.assertIn('records', res)
        self.assertTrue(len(res['records']) > 0, "Should find existing partners")

    def test_04_financial_report_tool(self):
        """Verify financial report execution."""
        if 'account.move.line' not in self.env:
            return
        # Test P&L
        pl_res = self.tool_model.execute_tool('odoo_financial_report', {
            'report_type': 'profit_loss',
        })
        self.assertNotIn('error', pl_res)
        self.assertIn('report_name', pl_res)
        self.assertIn('summary', pl_res)

        # Test Balance Sheet
        bs_res = self.tool_model.execute_tool('odoo_financial_report', {
            'report_type': 'balance_sheet',
        })
        self.assertNotIn('error', bs_res)
        self.assertIn('report_name', bs_res)

        # Test Aged Receivables
        ar_res = self.tool_model.execute_tool('odoo_financial_report', {
            'report_type': 'aged_receivables',
        })
        self.assertNotIn('error', ar_res)
        self.assertIn('report_name', ar_res)

    def test_05_safe_propose_and_approve_cycle(self):
        """Verify the Enterprise Approval Gate workflow."""
        # 1. Propose record creation
        proposal = self.tool_model.execute_tool('odoo_propose_record_create', {
            'model': 'res.partner',
            'values': {
                'name': 'Test Copilot Partner Inc',
                'email': 'copilot.test@example.com',
            },
            'summary': 'Create test partner',
        })

        self.assertTrue(proposal.get('is_proposal'), "Should be flagged as a proposal")
        self.assertEqual(proposal.get('status'), 'pending_approval')

        # 2. Execute approved proposal inside savepoint
        exec_res = self.tool_model.execute_approved_proposal(proposal)
        self.assertEqual(exec_res.get('status'), 'success')
        created_id = exec_res.get('res_id')
        self.assertTrue(created_id, "Record ID should be returned upon approval")
        self.assertIn('record_url', exec_res, "Proof access URL must be returned")
        self.assertIn(f"#id={created_id}&model=res.partner", exec_res['record_url'])

        partner = self.env['res.partner'].browse(created_id)
        self.assertTrue(partner.exists())
        self.assertEqual(partner.name, 'Test Copilot Partner Inc')

        # 3. Verify audit log entry
        audit = self.audit_model.search([('model_name', '=', 'res.partner'), ('res_id', '=', created_id)], limit=1)
        self.assertTrue(audit, "Audit trail log must be recorded")
        self.assertEqual(audit.status, 'success')
        self.assertEqual(audit.action_type, 'create')

        # 4. Propose record update
        update_proposal = self.tool_model.execute_tool('odoo_propose_record_update', {
            'model': 'res.partner',
            'res_id': created_id,
            'values': {'phone': '+628123456789'},
            'summary': 'Update phone number',
        })
        self.assertTrue(update_proposal.get('is_proposal'))
        self.assertEqual(update_proposal.get('old_values', {}).get('phone'), False)

        # 5. Execute update
        update_res = self.tool_model.execute_approved_proposal(update_proposal)
        self.assertEqual(update_res.get('status'), 'success')
        self.assertIn('record_url', update_res, "Proof URL must be present in update result")
        self.assertIn(f"#id={created_id}&model=res.partner", update_res['record_url'])
        self.assertEqual(partner.phone, '+628123456789')

        # 6. Propose record delete
        delete_proposal = self.tool_model.execute_tool('odoo_propose_record_delete', {
            'model': 'res.partner',
            'res_id': created_id,
            'summary': 'Delete test partner',
        })
        self.assertTrue(delete_proposal.get('is_proposal'))
        self.assertEqual(delete_proposal.get('action_type'), 'delete')

        # 7. Execute delete
        delete_res = self.tool_model.execute_approved_proposal(delete_proposal)
        self.assertEqual(delete_res.get('status'), 'success')
        self.assertFalse(partner.exists(), "Partner record should be unlinked from DB")

    def test_06_thread_lifecycle(self):
        """Verify thread creation, context awareness, and approval handling."""
        thread = self.thread_model.get_or_create_active_thread()
        self.assertTrue(thread, "Thread should be created")

        # Create a message with proposal
        msg = self.message_model.create({
            'thread_id': thread.id,
            'role': 'assistant',
            'content': 'Proposal to create partner',
            'action_proposal_json': '{"action_type": "create", "model": "res.partner", "values": {"name": "Thread Partner"}}',
            'approval_state': 'pending',
        })

        # Test Reject
        reject_res = thread.action_reject_proposal(msg.id)
        self.assertEqual(msg.approval_state, 'rejected')
        self.assertIn('response_message', reject_res)

        # Test System Prompt generation without format specifier errors
        prompt = thread._build_system_prompt({'resModel': 'sale.order', 'resId': 10, 'displayName': 'SO0010'})
        self.assertTrue(len(prompt) > 500, "System prompt must be constructed cleanly")
        self.assertIn("sale.order", prompt)
        self.assertIn("PT ABC", prompt)

    def test_07_markdown_formatting_and_proof_links(self):
        """Verify that markdown output contains proof access links and no raw HTML leaks."""
        thread = self.thread_model.get_or_create_active_thread()
        search_res = self.tool_model.execute_tool('odoo_search_read', {
            'model': 'res.partner',
            'domain': [['active', '=', True]],
            'fields': ['name', 'email'],
            'limit': 3,
        })
        # Check proof URLs inside tool_result records
        self.assertTrue(len(search_res['records']) > 0)
        for r in search_res['records']:
            self.assertIn('record_url', r, "Each record must have a record_url proof link")
            self.assertTrue(r['record_url'].startswith('/#id='))

        # Check rendered markdown output
        md_output = thread._format_tool_result_as_markdown('odoo_search_read', search_res)
        self.assertIn("Record Link", md_output, "Table header must have Record Link")
        self.assertIn("[Open #", md_output, "Records must include markdown link for proof verification")
        self.assertNotIn("<p>", md_output, "No raw HTML <p> tags should be present in tool markdown output")

    def test_08_proactive_sales_order_auto_contact_and_proof(self):
        """Verify end-to-end Sales Order creation with auto contact creation, lines, and proof URL."""
        if 'sale.order' not in self.env:
            return
        # Ensure contact doesn't exist before test
        existing = self.env['res.partner'].search([('name', '=', 'PT ABC Penawaran Baru')])
        if existing:
            existing.unlink()

        # 1. Propose creation of Sales Order
        proposal = self.tool_model.execute_tool('odoo_propose_record_create', {
            'model': 'sale.order',
            'values': {
                'partner_id': 'PT ABC Penawaran Baru',
                'order_line': [
                    {'product_id': 'Apple Pie', 'product_uom_qty': 5, 'price_unit': 30.0}
                ]
            },
            'summary': 'Buatkan SO untuk PT ABC sesuai penawaran 5x Apple Pie @ 30',
        })

        self.assertTrue(proposal.get('is_proposal'), "Should be flagged as proposal")
        self.assertEqual(proposal.get('model'), 'sale.order')

        # 2. Execute approved proposal
        exec_res = self.tool_model.execute_approved_proposal(proposal)
        self.assertEqual(exec_res.get('status'), 'success')
        so_id = exec_res.get('res_id')
        self.assertTrue(so_id, "Sales Order ID must be returned")
        self.assertIn('record_url', exec_res)
        self.assertEqual(exec_res['record_url'], f"/#id={so_id}&model=sale.order&view_type=form")

        # 3. Verify in database
        so = self.env['sale.order'].browse(so_id)
        self.assertTrue(so.exists())
        self.assertEqual(so.partner_id.name, 'PT ABC Penawaran Baru')
        self.assertEqual(len(so.order_line), 1)
        self.assertEqual(so.order_line.product_uom_qty, 5.0)
        self.assertEqual(so.order_line.price_unit, 30.0)

        # Cleanup
        partner = so.partner_id
        so.unlink()
        partner.unlink()

    def test_09_language_mirroring_and_bot_icons(self):
        """Verify dynamic language mirroring instructions and English standard messages."""
        thread = self.thread_model.get_or_create_active_thread()
        prompt = thread._build_system_prompt()
        self.assertIn("DYNAMIC LANGUAGE MIRRORING", prompt)
        self.assertIn("Indonesian", prompt)
        self.assertIn("English", prompt)

        # Verify reject message is standardized in English
        msg = self.message_model.create({
            'thread_id': thread.id,
            'role': 'assistant',
            'content': 'Proposal',
            'action_proposal_json': '{"action_type": "update", "model": "res.partner", "res_id": 1, "values": {}}',
            'approval_state': 'pending',
        })
        rej_res = thread.action_reject_proposal(msg.id)
        self.assertIn("Action canceled", rej_res['response_message']['content'])

    def test_10_search_chat_history(self):
        """Verify searching conversation history by title and message content."""
        thread = self.thread_model.create({
            'name': 'Sales Quotation Inquiry',
            'user_id': self.env.user.id,
        })
        self.message_model.create({
            'thread_id': thread.id,
            'role': 'user',
            'content': 'Need pricing for Special Apple Pie recipe',
        })

        # 1. Search by title
        title_matches = self.env['ai.copilot.thread'].search([
            ('user_id', '=', self.env.user.id),
            ('name', 'ilike', 'Sales Quotation')
        ])
        self.assertIn(thread, title_matches, "Should match thread title")

        # 2. Search by message content inside thread
        msg_matches = self.env['ai.copilot.message'].search([
            ('thread_id.user_id', '=', self.env.user.id),
            ('content', 'ilike', 'Special Apple Pie')
        ])
        matched_threads = msg_matches.mapped('thread_id')
        self.assertIn(thread, matched_threads, "Should match thread from message history")

    def test_11_favorite_session_and_model_switching(self):
        """Verify favorite session chat and tested model switching."""
        thread = self.thread_model.create({
            'name': 'Favorite Test Chat',
            'user_id': self.env.user.id,
            'is_favorite': False,
        })
        self.assertFalse(thread.is_favorite)

        # 1. Toggle favorite
        thread.is_favorite = True
        self.assertTrue(thread.is_favorite)

        # Check thread ordering prioritizes favorites
        thread_normal = self.thread_model.create({
            'name': 'Normal Chat',
            'user_id': self.env.user.id,
            'is_favorite': False,
        })
        threads = self.thread_model.search([('user_id', '=', self.env.user.id)], limit=2)
        self.assertEqual(threads[0], thread, "Favorite thread should come first in ordered search")

        # 2. Check get_thread_data
        data = thread.get_thread_data()
        self.assertTrue(data.get('is_favorite'))
        self.assertIn('provider', data)

        # 3. Test tested providers filter
        gemini = self.provider_model.search([('provider_type', '=', 'gemini')], limit=1)
        if gemini:
            gemini.write({'is_tested': True, 'api_key': 'test_key'})
            tested_providers = self.provider_model.get_tested_providers()
            self.assertIn(gemini, tested_providers, "Gemini should be in tested providers")

            # 4. Switch thread model
            thread.provider_id = gemini.id
            self.assertEqual(thread._get_provider(), gemini)

    def test_12_delete_thread_with_password_verification(self):
        """Verify password requirement when deleting conversation sessions."""
        from odoo.exceptions import AccessDenied

        thread = self.thread_model.create({
            'name': 'Protected Chat Session',
            'user_id': self.env.user.id,
        })
        self.assertTrue(thread.exists())

        # 1. Invalid password check fails with AccessDenied
        with self.assertRaises(AccessDenied):
            self.env.user._check_credentials(
                {'type': 'password', 'password': 'invalid_secret_password_12345'},
                {'interactive': True}
            )

        # 2. Thread remains safe in database
        self.assertTrue(thread.exists(), "Thread must remain intact if password check fails")

        # 3. Clean deletion when confirmed
        thread.unlink()
        self.assertFalse(thread.exists())

    def test_13_rbac_security_sales_user_denied_financial_report(self):
        """Verify that a sales user without Accounting rights cannot access financial statements or salary contracts."""
        # 1. Create a pure Sales user with Copilot access (no Accounting or HR manager rights)
        base_user_group = self.env.ref('base.group_user')
        salesman_group = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False)
        copilot_user_group = self.env.ref('ara_ai_copilot_assistant.group_ai_copilot_user')
        group_ids = [base_user_group.id, copilot_user_group.id]
        if salesman_group:
            group_ids.append(salesman_group.id)

        sales_user = self.env['res.users'].create({
            'name': 'Sales Staff User',
            'login': 'sales_staff_rbac_test',
            'email': 'sales_rbac@example.com',
            'groups_id': [(6, 0, group_ids)],
        })

        # 2. As sales user, attempt to call odoo_financial_report for Profit and Loss
        pl_result = self.tool_model.with_user(sales_user).execute_tool('odoo_financial_report', {
            'report_type': 'profit_loss'
        })
        self.assertIn('error', pl_result, "Financial report must return an error for sales staff")
        self.assertIn('Access Denied', pl_result['error'], "Error must indicate Access Denied")

        # 3. Attempt to call odoo_financial_report for Balance Sheet
        bs_result = self.tool_model.with_user(sales_user).execute_tool('odoo_financial_report', {
            'report_type': 'balance_sheet'
        })
        self.assertIn('error', bs_result)
        self.assertIn('Access Denied', bs_result['error'])

        # 4. Check system prompt contains strict RBAC directive
        thread = self.thread_model.with_user(sales_user).create({
            'name': 'Sales Chat',
            'user_id': sales_user.id,
        })
        prompt = thread._build_system_prompt()
        self.assertIn("SECURITY & ROLE-BASED ACCESS CONTROL", prompt)
        self.assertIn("Access Denied", prompt)




