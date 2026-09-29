# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, date
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class AiCopilotTool(models.AbstractModel):
    _name = 'ai.copilot.tool'
    _description = 'Odoo AI Copilot Tool Execution Engine'

    @api.model
    def get_tools_definitions(self):
        """
        Returns JSON-Schema tool definitions in OpenAI function format.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "odoo_search_read",
                    "description": "Search and read records from any Odoo model using domain filters. Use this to find invoices, sales orders, contacts, products, tickets, inventory, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {
                                "type": "string",
                                "description": "The Odoo technical model name, e.g. 'sale.order', 'res.partner', 'account.move', 'hr.employee' (for employees & salaries, query 'hr.employee' with fields ['name', 'wage', 'job_title'])"
                            },
                            "query": {
                                "type": "string",
                                "description": "Text search keyword to match record name (e.g. 'Apple Pie', 'PT ABC', 'SO001')"
                            },
                            "domain": {
                                "type": "array",
                                "description": "Odoo domain list of tuples, e.g. [['name', 'ilike', 'Apple Pie']], [['name', 'ilike', 'PT ABC']], [['state', '=', 'sale']]. Specify domain whenever user asks for a specific name/record.",
                                "items": {"type": "array"}
                            },
                            "fields": {
                                "type": "array",
                                "description": "List of technical field names to retrieve, e.g. ['name', 'partner_id', 'amount_total', 'state']",
                                "items": {"type": "string"}
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of records to return (default 15, max 50)",
                                "default": 15
                            },
                            "order": {
                                "type": "string",
                                "description": "Sort order, e.g. 'create_date desc', 'id asc'",
                                "default": "id desc"
                            }
                        },
                        "required": ["model"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_read_record",
                    "description": "Read full details of a specific record by its ID in Odoo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string", "description": "Odoo model name, e.g. 'res.partner'"},
                            "res_id": {"type": "integer", "description": "The numeric ID of the record"},
                            "fields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Specific fields to read. If omitted, common descriptive fields are returned."
                            }
                        },
                        "required": ["model", "res_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_aggregate",
                    "description": "Perform aggregations such as counts, sums, or averages grouped by field (e.g. total sales by salesperson, count of open tickets by priority, inventory value).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string", "description": "Odoo model name, e.g. 'sale.order', 'account.move'"},
                            "domain": {"type": "array", "description": "Filter domain", "items": {"type": "array"}},
                            "groupby": {"type": "array", "description": "List of fields to group by, e.g. ['user_id'], ['state']", "items": {"type": "string"}},
                            "fields": {"type": "array", "description": "Aggregated fields, e.g. ['amount_total:sum']", "items": {"type": "string"}}
                        },
                        "required": ["model", "groupby"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_financial_report",
                    "description": "Generate real-time executive financial statements: Profit & Loss (P&L), Balance Sheet, Aged Receivables, Aged Payables, or Trial Balance.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "report_type": {
                                "type": "string",
                                "enum": ["profit_loss", "balance_sheet", "aged_receivables", "aged_payables", "trial_balance"],
                                "description": "The type of financial report to generate"
                            },
                            "date_from": {
                                "type": "string",
                                "description": "Start date in 'YYYY-MM-DD' format (optional)"
                            },
                            "date_to": {
                                "type": "string",
                                "description": "End date in 'YYYY-MM-DD' format (optional)"
                            }
                        },
                        "required": ["report_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_propose_record_create",
                    "description": "Propose creating a new record in any Odoo model (Contact, Sale Order, Product, Task, Lead, etc.). Supports relational Many2one (pass string name to auto-find or auto-create missing contact) and One2many lines (e.g. order_line: [{'product_id': 'Apple Pie', 'product_uom_qty': 5, 'price_unit': 30}]). This triggers a safe user approval preview step before saving.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string", "description": "Odoo technical model, e.g. 'sale.order', 'res.partner', 'crm.lead', 'project.task'"},
                            "values": {
                                "type": "object",
                                "description": "Dictionary of field name and value pairs to populate in the new record. E.g. for sale.order: {'partner_id': 'PT ABC', 'order_line': [{'product_id': 'Apple Pie', 'product_uom_qty': 5, 'price_unit': 30}]}"
                            },
                            "summary": {
                                "type": "string",
                                "description": "Human-readable summary of what will be created, e.g. 'Create Quotation for PT ABC with 5x Apple Pie @ $30'"
                            }
                        },
                        "required": ["model", "values", "summary"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_propose_record_update",
                    "description": "Propose updating an existing record. This triggers a safe user approval preview showing old vs new values before execution.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string", "description": "Odoo model, e.g. 'res.partner'"},
                            "res_id": {"type": "integer", "description": "ID of the record to update"},
                            "values": {
                                "type": "object",
                                "description": "Dictionary of fields to update with their new values"
                            },
                            "summary": {
                                "type": "string",
                                "description": "Human-readable summary of the proposed update"
                            }
                        },
                        "required": ["model", "res_id", "values", "summary"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_propose_record_delete",
                    "description": "Propose deleting or archiving an existing record. This triggers a strict user confirmation step before deleting anything.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string", "description": "Odoo model, e.g. 'res.partner', 'sale.order'"},
                            "res_id": {"type": "integer", "description": "ID of the record to delete"},
                            "summary": {"type": "string", "description": "Human-readable explanation of the deletion"}
                        },
                        "required": ["model", "res_id", "summary"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_propose_execute_action",
                    "description": "Propose executing a business workflow action or server action (e.g. confirm sales order, validate invoice, send quotation). Requires user approval.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string", "description": "Model of the record, e.g. 'sale.order'"},
                            "res_id": {"type": "integer", "description": "Record ID"},
                            "action_name": {
                                "type": "string",
                                "description": "Technical method name to invoke, e.g. 'action_confirm', 'action_post', 'action_cancel'"
                            },
                            "summary": {
                                "type": "string",
                                "description": "Human readable explanation of what this action does"
                            }
                        },
                        "required": ["model", "res_id", "action_name", "summary"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_propose_send_email",
                    "description": "Propose sending an email to a customer, vendor, or colleague regarding a specific record. Triggers user approval preview.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string", "description": "Related model (e.g. 'sale.order', 'res.partner')"},
                            "res_id": {"type": "integer", "description": "ID of the record"},
                            "email_to": {"type": "string", "description": "Recipient email address"},
                            "subject": {"type": "string", "description": "Email subject"},
                            "body_html": {"type": "string", "description": "Email body in HTML or rich text"}
                        },
                        "required": ["email_to", "subject", "body_html"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_navigate",
                    "description": "Navigate user interface to open a specific view, form, or list of records in Odoo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string", "description": "Target model, e.g. 'sale.order'"},
                            "res_id": {"type": "integer", "description": "Specific record ID to open form view for (optional)"},
                            "view_type": {"type": "string", "enum": ["form", "list", "kanban"], "default": "form"},
                            "domain": {"type": "array", "description": "Domain filter if opening list view", "items": {"type": "array"}},
                            "title": {"type": "string", "description": "Action title banner"}
                        },
                        "required": ["model"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "odoo_semantic_search_docs",
                    "description": "Search attachments, notes, knowledge documents, and uploaded files across Odoo using semantic and keyword matching.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query or question about documents"},
                            "limit": {"type": "integer", "default": 5}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    @api.model
    def execute_tool(self, tool_name, arguments, user_context=None):
        """
        Main dispatcher for tool execution.
        Handles permission checking, safety checks, and returns JSON-serializable results.
        """
        _logger.info("AI Copilot Tool executing: %s with args %s", tool_name, arguments)
        try:
            if tool_name == 'odoo_search_read':
                return self._tool_search_read(arguments)
            elif tool_name == 'odoo_read_record':
                return self._tool_read_record(arguments)
            elif tool_name == 'odoo_aggregate':
                return self._tool_aggregate(arguments)
            elif tool_name == 'odoo_financial_report':
                return self._tool_financial_report(arguments)
            elif tool_name == 'odoo_propose_record_create':
                return self._tool_propose_record_create(arguments)
            elif tool_name == 'odoo_propose_record_update':
                return self._tool_propose_record_update(arguments)
            elif tool_name == 'odoo_propose_record_delete':
                return self._tool_propose_record_delete(arguments)
            elif tool_name == 'odoo_propose_execute_action':
                return self._tool_propose_execute_action(arguments)
            elif tool_name == 'odoo_propose_send_email':
                return self._tool_propose_send_email(arguments)
            elif tool_name == 'odoo_navigate':
                return self._tool_navigate(arguments)
            elif tool_name == 'odoo_semantic_search_docs':
                return self._tool_semantic_search_docs(arguments)
            else:
                return {"error": f"Unknown tool name: {tool_name}"}
        except Exception as e:
            _logger.exception("Error executing tool %s: %s", tool_name, str(e))
            return {"error": f"Tool execution failed: {str(e)}"}

    # -------------------------------------------------------------------------
    # TOOL IMPLEMENTATIONS
    # -------------------------------------------------------------------------

    def _tool_search_read(self, args):
        model_name = args.get('model')
        if not model_name or model_name not in self.env:
            return {"error": f"Model '{model_name}' does not exist in this Odoo installation."}

        model = self.env[model_name]

        # Explicit ORM Access Rights Check
        try:
            model.check_access('read')
        except AccessError as e:
            return {"error": f"Access Denied: Your Odoo user account does not have read permissions for model '{model_name}'. {str(e)}"}

        domain = args.get('domain') or []
        query = args.get('query')
        if query and not domain:
            rec_name = model._rec_name or 'name'
            if rec_name in model._fields:
                domain = [[rec_name, 'ilike', query]]

        fields_to_read = args.get('fields') or []
        limit = min(int(args.get('limit') or 15), 50)
        order = args.get('order') or 'id desc'

        # Sanitize domain
        domain = self._sanitize_domain(model, domain)

        # Default fields if not specified
        if not fields_to_read:
            rec_name = model._rec_name or 'name'
            common = ['id', rec_name, 'create_date']
            for f in ['state', 'stage_id', 'amount_total', 'total_amount', 'partner_id', 'user_id', 'qty_available', 'active', 'job_title', 'wage', 'work_email']:
                if f in model._fields:
                    common.append(f)
            fields_to_read = list(set(common))

        # Filter fields to only existing ones and check field-level group permissions
        valid_fields = []
        for f in fields_to_read:
            field_obj = model._fields.get(f)
            if not field_obj:
                continue
            if field_obj.groups:
                if not any(self.env.user.has_group(g.strip()) for g in field_obj.groups.split(',')):
                    continue
            valid_fields.append(f)

        if 'id' not in valid_fields:
            valid_fields.append('id')

        try:
            records = model.search_read(domain, valid_fields, limit=limit, order=order)
        except AccessError as e:
            return {"error": f"Access Denied by Odoo ORM: {str(e)}"}

        # Format Many2one / date values for readability
        records = self._format_records_output(records)
        # Add proof access links for easy user verification
        for r in records:
            if 'id' in r:
                r['record_url'] = f"/#id={r['id']}&model={model_name}&view_type=form"
                r['model'] = model_name

        total_count = model.search_count(domain)
        return {
            "model": model_name,
            "count_found": len(records),
            "total_count": total_count,
            "records": records,
        }

    def _tool_read_record(self, args):
        model_name = args.get('model')
        res_id = args.get('res_id')
        if not model_name or model_name not in self.env:
            return {"error": f"Model '{model_name}' does not exist."}

        model = self.env[model_name]
        try:
            model.check_access('read')
        except AccessError as e:
            return {"error": f"Access Denied: Your Odoo user account does not have read permissions for model '{model_name}'. {str(e)}"}

        record = model.browse(int(res_id))
        if not record.exists():
            return {"error": f"Record #{res_id} in model '{model_name}' does not exist."}

        fields_to_read = args.get('fields') or []
        if not fields_to_read:
            fields_to_read = [
                fname for fname, field in model._fields.items()
                if not field.compute or field.store
            ][:30]

        valid_fields = []
        for f in fields_to_read:
            field_obj = model._fields.get(f)
            if not field_obj:
                continue
            if field_obj.groups:
                if not any(self.env.user.has_group(g.strip()) for g in field_obj.groups.split(',')):
                    continue
            valid_fields.append(f)

        try:
            data = record.read(valid_fields)
        except AccessError as e:
            return {"error": f"Access Denied by Odoo ORM: {str(e)}"}

        return {"model": model_name, "id": res_id, "data": self._format_records_output(data)[0] if data else {}}

    def _tool_aggregate(self, args):
        model_name = args.get('model')
        if not model_name or model_name not in self.env:
            return {"error": f"Model '{model_name}' does not exist."}

        model = self.env[model_name]
        try:
            model.check_access('read')
        except AccessError as e:
            return {"error": f"Access Denied: Your Odoo user account does not have read permissions for model '{model_name}'. {str(e)}"}

        domain = self._sanitize_domain(model, args.get('domain') or [])
        groupby = args.get('groupby') or []
        fields_arg = args.get('fields') or ['id:count']

        valid_groupby = [g for g in groupby if g.split(':')[0] in model._fields]
        if not valid_groupby:
            count = model.search_count(domain)
            return {"model": model_name, "total_count": count}

        res = model.read_group(domain, fields_arg, valid_groupby, limit=30)
        return {"model": model_name, "aggregation": self._format_records_output(res)}

    def _tool_financial_report(self, args):
        """
        Executes instant real-time financial reporting directly from account.move.line.
        Requires Accounting role permissions.
        """
        user = self.env.user
        has_accounting = (
            user._is_admin() or
            user.has_group('account.group_account_user') or
            user.has_group('account.group_account_readonly') or
            user.has_group('account.group_account_manager')
        )
        if not has_accounting:
            return {
                "error": "Access Denied: You do not have permission to access financial accounting reports (Profit & Loss, Balance Sheet, Aged Receivables). Only authorized Accounting users can view this financial data."
            }

        report_type = args.get('report_type')
        date_from = args.get('date_from')
        date_to = args.get('date_to')

        if 'account.move.line' not in self.env:
            return {"error": "Accounting module (account.move.line) is not installed."}

        domain = [('parent_state', '=', 'posted')]
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))

        aml_model = self.env['account.move.line']

        if report_type == 'profit_loss':
            # Income: account.account_type in ('income', 'income_other')
            # Expense: account.account_type in ('expense', 'expense_depreciation', 'expense_direct_cost')
            income_lines = aml_model.search_read(
                domain + [('account_id.account_type', 'in', ['income', 'income_other'])],
                ['account_id', 'credit', 'debit', 'balance'],
                limit=100
            )
            expense_lines = aml_model.search_read(
                domain + [('account_id.account_type', 'in', ['expense', 'expense_depreciation', 'expense_direct_cost'])],
                ['account_id', 'credit', 'debit', 'balance'],
                limit=100
            )

            total_income = sum(l['credit'] - l['debit'] for l in income_lines)
            total_expense = sum(l['debit'] - l['credit'] for l in expense_lines)
            net_profit = total_income - total_expense

            return {
                "report_name": "Profit and Loss Statement (P&L)",
                "period": f"{date_from or 'Beginning'} to {date_to or 'Present'}",
                "currency": self.env.company.currency_id.name,
                "summary": {
                    "Total Revenue/Income": f"{total_income:,.2f}",
                    "Total Expenses": f"{total_expense:,.2f}",
                    "Net Profit / (Loss)": f"{net_profit:,.2f}",
                },
                "status": "Profitable" if net_profit >= 0 else "Deficit"
            }

        elif report_type == 'balance_sheet':
            asset_lines = aml_model.search_read(
                domain + [('account_id.account_type', 'in', ['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments', 'asset_fixed'])],
                ['balance'], limit=200
            )
            liability_lines = aml_model.search_read(
                domain + [('account_id.account_type', 'in', ['liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current'])],
                ['balance'], limit=200
            )
            equity_lines = aml_model.search_read(
                domain + [('account_id.account_type', 'in', ['equity', 'equity_unaffected'])],
                ['balance'], limit=200
            )

            total_assets = sum(l['balance'] for l in asset_lines)
            total_liabilities = sum(-l['balance'] for l in liability_lines)
            total_equity = sum(-l['balance'] for l in equity_lines)

            return {
                "report_name": "Balance Sheet",
                "as_of_date": date_to or str(date.today()),
                "currency": self.env.company.currency_id.name,
                "summary": {
                    "Total Assets": f"{total_assets:,.2f}",
                    "Total Liabilities": f"{total_liabilities:,.2f}",
                    "Total Equity": f"{total_equity:,.2f}",
                    "Total Liabilities & Equity": f"{(total_liabilities + total_equity):,.2f}",
                }
            }

        elif report_type == 'aged_receivables':
            # Invoices unpaid
            invoices = self.env['account.move'].search_read(
                [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])],
                ['name', 'partner_id', 'invoice_date', 'invoice_date_due', 'amount_residual', 'currency_id'],
                limit=25, order='invoice_date_due asc'
            )
            total_unpaid = sum(inv['amount_residual'] for inv in invoices)
            return {
                "report_name": "Aged Receivables (Unpaid Customer Invoices)",
                "total_receivable": f"{total_unpaid:,.2f}",
                "invoice_count": len(invoices),
                "invoices": self._format_records_output(invoices),
            }

        elif report_type == 'aged_payables':
            bills = self.env['account.move'].search_read(
                [('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])],
                ['name', 'partner_id', 'invoice_date', 'invoice_date_due', 'amount_residual', 'currency_id'],
                limit=25, order='invoice_date_due asc'
            )
            total_unpaid = sum(bill['amount_residual'] for bill in bills)
            return {
                "report_name": "Aged Payables (Unpaid Vendor Bills)",
                "total_payable": f"{total_unpaid:,.2f}",
                "bill_count": len(bills),
                "bills": self._format_records_output(bills),
            }

        elif report_type == 'trial_balance':
            lines = aml_model.read_group(
                domain,
                ['debit:sum', 'credit:sum', 'balance:sum'],
                ['account_id'],
                limit=50
            )
            return {
                "report_name": "Trial Balance Summary",
                "accounts": self._format_records_output(lines)
            }

        return {"error": f"Unsupported report type: {report_type}"}

    def _tool_propose_record_create(self, args):
        model_name = args.get('model')
        values = args.get('values') or {}
        summary = args.get('summary') or f"Create new record in {model_name}"

        if not model_name or model_name not in self.env:
            return {"error": f"Model '{model_name}' does not exist."}

        model = self.env[model_name]
        clean_values = self._prepare_record_values(model, values, auto_create_missing=True)

        return {
            "is_proposal": True,
            "action_type": "create",
            "model": model_name,
            "values": clean_values,
            "summary": summary,
            "status": "pending_approval",
            "message": f"Proposal created: {summary}. Awaiting user confirmation."
        }

    def _tool_propose_record_update(self, args):
        model_name = args.get('model')
        res_id = args.get('res_id')
        values = args.get('values') or {}
        summary = args.get('summary') or f"Update record #{res_id} in {model_name}"

        if not model_name or model_name not in self.env:
            return {"error": f"Model '{model_name}' does not exist."}

        model = self.env[model_name]
        record = model.browse(int(res_id))
        if not record.exists():
            return {"error": f"Record #{res_id} does not exist in '{model_name}'."}

        # Collect old values for diff comparison
        old_values = {}
        clean_values = {}
        for k, v in values.items():
            if k in model._fields:
                clean_values[k] = v
                field = model._fields[k]
                raw_val = getattr(record, k)
                if field.type == 'many2one':
                    old_values[k] = raw_val.display_name if raw_val else False
                else:
                    old_values[k] = raw_val

        return {
            "is_proposal": True,
            "action_type": "update",
            "model": model_name,
            "res_id": int(res_id),
            "record_display_name": record.display_name,
            "record_url": f"/#id={res_id}&model={model_name}&view_type=form",
            "values": clean_values,
            "old_values": old_values,
            "summary": summary,
            "status": "pending_approval",
            "message": f"Proposal created: {summary}. Awaiting user confirmation."
        }

    def _tool_propose_record_delete(self, args):
        model_name = args.get('model')
        res_id = args.get('res_id')
        summary = args.get('summary') or f"Delete record #{res_id} from {model_name}"

        if not model_name or model_name not in self.env:
            return {"error": f"Model '{model_name}' does not exist."}

        model = self.env[model_name]
        record = model.browse(int(res_id))
        if not record.exists():
            return {"error": f"Record #{res_id} does not exist in '{model_name}'."}

        return {
            "is_proposal": True,
            "action_type": "delete",
            "model": model_name,
            "res_id": int(res_id),
            "record_display_name": record.display_name,
            "summary": summary,
            "status": "pending_approval",
            "message": f"Proposal: {summary}. Confirmation required before deleting records."
        }

    def _tool_propose_execute_action(self, args):
        model_name = args.get('model')
        res_id = args.get('res_id')
        action_name = args.get('action_name')
        summary = args.get('summary') or f"Execute '{action_name}' on {model_name} #{res_id}"

        if not model_name or model_name not in self.env:
            return {"error": f"Model '{model_name}' does not exist."}

        model = self.env[model_name]
        record = model.browse(int(res_id))
        if not record.exists():
            return {"error": f"Record #{res_id} does not exist."}

        if not hasattr(record, action_name):
            return {"error": f"Action method '{action_name}' does not exist on model '{model_name}'."}

        return {
            "is_proposal": True,
            "action_type": "execute_action",
            "model": model_name,
            "res_id": int(res_id),
            "record_display_name": record.display_name,
            "action_name": action_name,
            "summary": summary,
            "status": "pending_approval",
            "message": f"Proposal: {summary}. Awaiting user confirmation."
        }

    def _tool_propose_send_email(self, args):
        model_name = args.get('model') or 'res.partner'
        res_id = args.get('res_id')
        email_to = args.get('email_to')
        subject = args.get('subject')
        body_html = args.get('body_html')

        summary = f"Send email to {email_to}: '{subject}'"

        return {
            "is_proposal": True,
            "action_type": "send_email",
            "model": model_name,
            "res_id": int(res_id) if res_id else False,
            "email_to": email_to,
            "subject": subject,
            "body_html": body_html,
            "summary": summary,
            "status": "pending_approval",
            "message": f"Email prepared: {summary}. Awaiting approval."
        }

    def _tool_navigate(self, args):
        model_name = args.get('model')
        res_id = args.get('res_id')
        view_type = args.get('view_type') or ('form' if res_id else 'list')
        domain = args.get('domain') or []
        title = args.get('title') or f"Open {model_name}"

        return {
            "client_action": "navigate",
            "model": model_name,
            "res_id": int(res_id) if res_id else False,
            "view_type": view_type,
            "domain": domain,
            "title": title,
            "message": f"Navigating to {title}..."
        }

    def _tool_semantic_search_docs(self, args):
        query = args.get('query', '')
        limit = min(int(args.get('limit') or 5), 10)
        results = self.env['ai.copilot.knowledge'].search_knowledge(query, limit=limit)
        return {
            "query": query,
            "results_found": len(results),
            "documents": results,
        }

    # -------------------------------------------------------------------------
    # SAFE EXECUTION (APPROVED PROPOSALS)
    # -------------------------------------------------------------------------

    @api.model
    def execute_approved_proposal(self, proposal_dict):
        """
        Executes an approved proposal inside an isolated database savepoint.
        Maintains an enterprise audit log.
        """
        action_type = proposal_dict.get('action_type')
        model_name = proposal_dict.get('model')
        user_id = self.env.user.id

        audit_vals = {
            'user_id': user_id,
            'action_type': action_type,
            'model_name': model_name,
            'summary': proposal_dict.get('summary', ''),
            'payload': json.dumps(proposal_dict),
            'status': 'success',
        }

        try:
            with self.env.cr.savepoint():
                if action_type == 'create':
                    model = self.env[model_name]
                    raw_vals = proposal_dict.get('values', {})
                    create_vals = self._prepare_record_values(model, raw_vals, auto_create_missing=True)
                    new_rec = model.create(create_vals)
                    audit_vals['res_id'] = new_rec.id
                    audit_vals['result'] = f"Created record ID #{new_rec.id} ({new_rec.display_name})"
                    res = {
                        "status": "success",
                        "message": f"Successfully created {new_rec.display_name} (ID: {new_rec.id})",
                        "res_id": new_rec.id,
                        "model": model_name,
                        "display_name": new_rec.display_name,
                        "record_url": f"/#id={new_rec.id}&model={model_name}&view_type=form",
                    }

                elif action_type == 'update':
                    model = self.env[model_name]
                    res_id = proposal_dict.get('res_id')
                    rec = model.browse(res_id)
                    raw_vals = proposal_dict.get('values', {})
                    update_vals = self._prepare_record_values(model, raw_vals, auto_create_missing=True)
                    rec.write(update_vals)
                    audit_vals['res_id'] = res_id
                    audit_vals['result'] = f"Updated record ID #{res_id} ({rec.display_name})"
                    res = {
                        "status": "success",
                        "message": f"Successfully updated {rec.display_name} (ID: {res_id})",
                        "res_id": res_id,
                        "model": model_name,
                        "display_name": rec.display_name,
                        "record_url": f"/#id={res_id}&model={model_name}&view_type=form",
                    }

                elif action_type == 'execute_action':
                    model = self.env[model_name]
                    res_id = proposal_dict.get('res_id')
                    action_name = proposal_dict.get('action_name')
                    rec = model.browse(res_id)
                    method = getattr(rec, action_name)
                    act_result = method()
                    audit_vals['res_id'] = res_id
                    audit_vals['result'] = f"Executed {action_name} on #{res_id}. Result: {str(act_result)[:200]}"
                    res = {
                        "status": "success",
                        "message": f"Successfully executed '{action_name}' on {rec.display_name}",
                        "res_id": res_id,
                        "model": model_name,
                        "display_name": rec.display_name,
                        "record_url": f"/#id={res_id}&model={model_name}&view_type=form",
                    }

                elif action_type == 'send_email':
                    email_to = proposal_dict.get('email_to')
                    subject = proposal_dict.get('subject')
                    body_html = proposal_dict.get('body_html')
                    mail_vals = {
                        'subject': subject,
                        'body_html': body_html,
                        'email_to': email_to,
                        'email_from': self.env.user.email_formatted or self.env.company.email,
                        'auto_delete': False,
                    }
                    if proposal_dict.get('model') and proposal_dict.get('res_id'):
                        mail_vals['model'] = proposal_dict['model']
                        mail_vals['res_id'] = proposal_dict['res_id']
                    mail = self.env['mail.mail'].create(mail_vals)
                    mail.send()
                    audit_vals['res_id'] = mail.id
                    audit_vals['result'] = f"Sent email to {email_to} with subject '{subject}'"
                    res = {
                        "status": "success",
                        "message": f"Email successfully sent to {email_to}",
                    }

                elif action_type == 'delete':
                    model = self.env[model_name]
                    res_id = proposal_dict.get('res_id')
                    rec = model.browse(res_id)
                    rec_name = rec.display_name
                    rec.unlink()
                    audit_vals['res_id'] = res_id
                    audit_vals['result'] = f"Deleted record ID #{res_id} ({rec_name}) from {model_name}"
                    res = {
                        "status": "success",
                        "message": f"Record #{res_id} ({rec_name}) successfully deleted from database.",
                        "res_id": res_id,
                        "model": model_name,
                    }

                else:
                    raise UserError(_("Unsupported action type: %s") % action_type)

            # Record in audit trail
            self.env['ai.copilot.audit'].sudo().create(audit_vals)
            return res

        except Exception as e:
            _logger.exception("Failed to execute approved proposal: %s", str(e))
            audit_vals['status'] = 'failed'
            audit_vals['error_message'] = str(e)
            self.env['ai.copilot.audit'].sudo().create(audit_vals)
            return {"status": "error", "message": f"Execution failed: {str(e)}"}

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _prepare_record_values(self, model, vals, auto_create_missing=True):
        """
        Prepares and normalizes values for model create/write operations:
        - Resolves Many2one strings to IDs (creates record if missing, e.g. partner).
        - Converts One2many list of dicts to Odoo command format [(0, 0, line_vals)].
        - Cleans types and ignores invalid fields.
        """
        if not isinstance(vals, dict):
            return {}

        clean = {}
        for k, v in vals.items():
            if k not in model._fields:
                continue
            field = model._fields[k]

            if field.type == 'many2one':
                if isinstance(v, (int, float)):
                    clean[k] = int(v)
                elif isinstance(v, str) and v.isdigit():
                    clean[k] = int(v)
                elif isinstance(v, str) and v.strip():
                    target_name = v.strip()
                    comodel = self.env[field.comodel_name]
                    rec_name = comodel._rec_name or 'name'
                    target_rec = comodel.search([(rec_name, 'ilike', target_name)], limit=1)
                    if not target_rec and auto_create_missing:
                        # Auto create record if it has name field (e.g. res.partner)
                        if rec_name in comodel._fields:
                            try:
                                target_rec = comodel.create({rec_name: target_name})
                            except Exception as ex:
                                _logger.warning("Could not auto-create missing %s '%s': %s", field.comodel_name, target_name, str(ex))
                    if target_rec:
                        clean[k] = target_rec.id

            elif field.type == 'one2many':
                comodel = self.env[field.comodel_name]
                clean_lines = []
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            line_vals = self._prepare_record_values(comodel, item, auto_create_missing=auto_create_missing)
                            if line_vals:
                                clean_lines.append((0, 0, line_vals))
                        elif isinstance(item, (tuple, list)) and len(item) == 3:
                            clean_lines.append(item)
                clean[k] = clean_lines

            elif field.type == 'many2many':
                if isinstance(v, list):
                    int_ids = []
                    for item in v:
                        if isinstance(item, int):
                            int_ids.append(item)
                        elif isinstance(item, str) and item.isdigit():
                            int_ids.append(int(item))
                    clean[k] = [(6, 0, int_ids)]

            elif field.type in ('integer',):
                try:
                    clean[k] = int(v)
                except (ValueError, TypeError):
                    clean[k] = v

            elif field.type in ('float', 'monetary'):
                try:
                    clean[k] = float(v)
                except (ValueError, TypeError):
                    clean[k] = v

            elif field.type == 'boolean':
                clean[k] = bool(v)

            else:
                clean[k] = v

        return clean

    def _sanitize_domain(self, model, domain):
        """Sanitizes user/LLM supplied domain to prevent syntax errors."""
        if not isinstance(domain, list):
            return []
        clean_domain = []
        for leaf in domain:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3:
                field_name = leaf[0]
                if field_name in model._fields or field_name == 'id':
                    clean_domain.append(leaf)
            elif leaf in ('&', '|', '!'):
                clean_domain.append(leaf)
        return clean_domain

    def _format_records_output(self, records):
        """Prettify records output for AI and frontend display."""
        if not records:
            return []
        formatted = []
        for rec in records:
            item = {}
            for k, v in rec.items():
                if isinstance(v, (datetime, date)):
                    item[k] = str(v)
                elif isinstance(v, bytes):
                    item[k] = f"<{len(v)} bytes>"
                elif isinstance(v, tuple) and len(v) == 2:
                    # Many2one (id, display_name)
                    item[k] = {"id": v[0], "display_name": v[1]}
                else:
                    item[k] = v
            formatted.append(item)
        return formatted
