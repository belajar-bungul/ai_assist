# -*- coding: utf-8 -*-
{
    'name': 'Ara AI Copilot Assistant - Multi-Provider Enterprise AI',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Artificial Intelligence',
    'summary': 'Next-Gen Enterprise AI Copilot for Odoo 19: Search & Read Anything, Safe Approval Workflows, Financial Reporting, Multimodal Vision, RAG Document Search, Smart Context Awareness & 5+ AI Providers',
    'description': """
Ara AI Copilot Assistant for Odoo 19
====================================
The enterprise AI assistant that understands your business data and takes action through natural conversation.

Key Features & Highlights:
--------------------------
* **Search & Read Anything:** Query any Odoo model in plain natural language (unpaid invoices, open tickets, products below reorder point).
* **Create & Update Records Safely:** Safe built-in approval gate with visual diff and savepoint rollback before creating or updating records.
* **Full Financial Reporting:** Instant Profit & Loss, Balance Sheet, Aged Receivables, Aged Payables, and Trial Balance from live GL lines.
* **Run Actions & Send Emails:** Trigger server actions, workflows, print reports, and draft/send emails.
* **Multimodal AI:** Upload images, screenshots, scanned receipts, and documents with instant OCR analysis.
* **RAG & Semantic Document Search:** Chunked full-text and semantic search across all business attachments.
* **Smart Navigation & Context Awareness:** Automatically senses the current active screen, model, and record ID.
* **5+ AI Providers:** Google Gemini (Gemini 2.5 Flash / Pro), OpenAI (GPT-4o), Anthropic Claude, NVIDIA NIM, and OpenRouter.
* **Modern Porcelain Pastel Aesthetic:** Luxurious UI inspired by Ara Dashboard with gentle blush pink and butter yellow porcelain gradients.
* **Dual Display Mode:** Fast Systray Drawer accessible from any screen + Fullscreen Dedicated AI Workspace.
* **Enterprise Audit Trail:** Comprehensive logging of all AI queries, proposal approvals, and executions.
    """,
    'author': 'ARA SOFT',
    'website': 'https://www.arasoft.id',
    'license': 'OPL-1',
    'price': 59.99,
    'currency': 'USD',
    'depends': [
        'base',
        'web',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ai_provider_data.xml',
        'views/ai_copilot_provider_views.xml',
        'views/ai_copilot_thread_views.xml',
        'views/ai_copilot_audit_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ara_ai_copilot_assistant/static/src/scss/copilot.scss',
            'ara_ai_copilot_assistant/static/src/js/copilot_service.js',
            'ara_ai_copilot_assistant/static/src/js/copilot_password_dialog.js',
            'ara_ai_copilot_assistant/static/src/js/copilot_chat_window.js',
            'ara_ai_copilot_assistant/static/src/js/copilot_systray.js',
            'ara_ai_copilot_assistant/static/src/js/copilot_action_client.js',
            'ara_ai_copilot_assistant/static/src/xml/copilot_password_dialog.xml',
            'ara_ai_copilot_assistant/static/src/xml/copilot_chat_window.xml',
            'ara_ai_copilot_assistant/static/src/xml/copilot_systray.xml',
            'ara_ai_copilot_assistant/static/src/xml/copilot_action_client.xml',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
