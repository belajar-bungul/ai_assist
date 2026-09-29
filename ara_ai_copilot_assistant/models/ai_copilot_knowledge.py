# -*- coding: utf-8 -*-
import base64
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AiCopilotKnowledge(models.Model):
    _name = 'ai.copilot.knowledge'
    _description = 'AI Copilot Document Knowledge & RAG Index'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Document Title', required=True)
    content = fields.Text(string='Extracted Content', required=True)
    source_model = fields.Char(string='Source Model')
    source_res_id = fields.Integer(string='Source Record ID')
    attachment_id = fields.Many2one('ir.attachment', string='Original Attachment', ondelete='cascade')
    chunk_index = fields.Integer(string='Chunk Index', default=0)

    @api.model
    def index_attachment(self, attachment_id):
        """Extracts text from attachment and saves to knowledge index."""
        attachment = self.env['ir.attachment'].browse(attachment_id)
        if not attachment.exists() or not attachment.datas:
            return False

        try:
            raw_bytes = base64.b64decode(attachment.datas)
            mimetype = attachment.mimetype or ''

            text = ""
            if 'text' in mimetype or 'csv' in mimetype or 'json' in mimetype:
                text = raw_bytes.decode('utf-8', errors='ignore')
            elif 'pdf' in mimetype:
                # Basic PDF text extraction if pypdf is available
                try:
                    import io
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
                    extracted = [p.extract_text() for p in reader.pages if p.extract_text()]
                    text = "\n".join(extracted)
                except Exception:
                    text = f"PDF Document: {attachment.name} ({len(raw_bytes)} bytes)"
            else:
                text = f"Document: {attachment.name} ({attachment.mimetype})"

            if text.strip():
                # Store chunk(s)
                chunk_size = 2000
                chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
                for idx, chunk in enumerate(chunks[:10]):  # Cap at 10 chunks
                    self.create({
                        'name': f"{attachment.name} (Part {idx + 1})",
                        'content': chunk,
                        'source_model': attachment.res_model,
                        'source_res_id': attachment.res_id,
                        'attachment_id': attachment.id,
                        'chunk_index': idx,
                    })
                return True
        except Exception as e:
            _logger.warning("Failed to index attachment %s: %s", attachment.name, str(e))
        return False

    @api.model
    def search_knowledge(self, query, limit=5):
        """
        Retrieves relevant document chunks based on query terms.
        Also searches ir.attachment for recent business files.
        """
        results = []
        if not query:
            return results

        # 1. Search in indexed knowledge
        query_terms = [w.strip() for w in query.split() if len(w.strip()) > 2]
        domain = []
        for term in query_terms[:4]:
            domain.append(('content', 'ilike', term))

        if domain:
            # Build OR domain
            or_domain = ['|'] * (len(domain) - 1) + domain if len(domain) > 1 else domain
            knowledge_recs = self.search(or_domain, limit=limit)
            for rec in knowledge_recs:
                results.append({
                    "title": rec.name,
                    "content_snippet": rec.content[:400] + ("..." if len(rec.content) > 400 else ""),
                    "source": f"{rec.source_model or 'File'} #{rec.source_res_id or ''}".strip(),
                })

        # 2. Also search recent attachments (e.g. invoices, orders)
        if len(results) < limit:
            att_domain = ['|', ('name', 'ilike', query), ('description', 'ilike', query)]
            attachments = self.env['ir.attachment'].search(att_domain, limit=limit - len(results))
            for att in attachments:
                results.append({
                    "title": att.name,
                    "content_snippet": f"Attachment on {att.res_model or 'General'} #{att.res_id or ''} ({att.mimetype})",
                    "source": f"{att.res_model or 'Attachment'} #{att.res_id or ''}",
                })

        return results
