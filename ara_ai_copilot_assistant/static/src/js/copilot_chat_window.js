/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted, useEffect, onWillUpdateProps, markup } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { CopilotPasswordConfirmDialog } from "./copilot_password_dialog";

export class CopilotChatWindow extends Component {
    static template = "ara_ai_copilot_assistant.ChatWindow";
    static props = {
        isDrawer: { type: Boolean, optional: true },
        onClose: { type: Function, optional: true },
        threadId: { type: [Number, Boolean], optional: true },
        onThreadUpdated: { type: Function, optional: true },
    };

    setup() {
        this.rpc = rpc;
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.copilot = useService("copilot");
        this.dialog = useService("dialog");

        this.messagesScrollRef = useRef("messagesArea");
        this.fileInputRef = useRef("fileInput");

        this.state = useState({
            isLoading: false,
            isSending: false,
            inputText: "",
            activeThreadId: this.props.threadId || null,
            threadName: "",
            isFavorite: false,
            messages: [],
            threads: [],
            availableProviders: [],
            pendingAttachments: [], // [{ id, name, mimetype }]
            currentContext: null,
            providerInfo: null,
        });

        onWillStart(async () => {
            await this.loadInitialData();
        });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.threadId && nextProps.threadId !== this.state.activeThreadId) {
                await this.switchThread(nextProps.threadId);
            }
        });

        onMounted(() => {
            this.updateCurrentContext();
            this.scrollToBottom();
        });

        useEffect(
            () => {
                this.scrollToBottom();
            },
            () => [this.state.messages.length, this.state.isSending]
        );
    }

    updateCurrentContext() {
        this.state.currentContext = this.copilot.getCurrentContext();
    }

    async loadInitialData() {
        this.state.isLoading = true;
        try {
            const ctx = this.copilot.getCurrentContext();
            const res = await this.rpc("/ara_copilot/init", { context_info: ctx });
            this.state.threads = res.threads || [];
            this.state.activeThreadId = res.active_thread_id;
            this.state.providerInfo = res.provider;
            this.state.availableProviders = res.available_providers || [];

            if (res.active_thread_data) {
                this.state.threadName = res.active_thread_data.name;
                this.state.isFavorite = Boolean(res.active_thread_data.is_favorite);
                if (res.active_thread_data.provider && res.active_thread_data.provider.id) {
                    this.state.providerInfo = res.active_thread_data.provider;
                }
                this.state.messages = res.active_thread_data.messages || [];
            }
        } catch (err) {
            console.error("Failed to initialize Copilot:", err);
            this.notification.add("Could not load AI Copilot: " + (err.message || err), { type: "danger" });
        } finally {
            this.state.isLoading = false;
        }
    }

    scrollToBottom() {
        if (this.messagesScrollRef.el) {
            this.messagesScrollRef.el.scrollTop = this.messagesScrollRef.el.scrollHeight;
        }
    }

    onTextareaKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    async sendMessage(prefilledText = null) {
        const textToSend = prefilledText || this.state.inputText.trim();
        if (!textToSend && this.state.pendingAttachments.length === 0) {
            return;
        }

        if (this.state.isSending) return;

        this.updateCurrentContext();

        const attachmentIds = this.state.pendingAttachments.map((a) => a.id);
        const optimisticMsg = {
            id: "temp_" + Date.now(),
            role: "user",
            content: textToSend,
            attachments: [...this.state.pendingAttachments],
            approval_state: "none",
        };

        this.state.messages.push(optimisticMsg);
        this.state.inputText = "";
        this.state.pendingAttachments = [];
        this.state.isSending = true;

        try {
            const res = await this.rpc("/ara_copilot/send_message", {
                thread_id: this.state.activeThreadId,
                content: textToSend,
                attachment_ids: attachmentIds,
                context_info: this.state.currentContext,
            });

            if (res.error) {
                this.notification.add(res.error, { type: "danger" });
                this.state.messages.push({
                    id: "err_" + Date.now(),
                    role: "assistant",
                    content: "⚠️ " + _t("Error: ") + res.error,
                    approval_state: "none",
                });
            } else {
                // Remove optimistic temp message and replace with official user + assistant messages
                const idx = this.state.messages.findIndex((m) => m.id === optimisticMsg.id);
                if (idx !== -1) {
                    this.state.messages.splice(idx, 1);
                }
                if (res.user_message) {
                    this.state.messages.push(res.user_message);
                }
                if (res.assistant_message) {
                    this.state.messages.push(res.assistant_message);

                    // Check for client navigation
                    if (res.assistant_message.client_action) {
                        this.copilot.executeClientAction(res.assistant_message.client_action);
                    }
                }
                if (res.thread_name) {
                    this.state.threadName = res.thread_name;
                    this.props.onThreadUpdated?.();
                }
            }
        } catch (err) {
            console.error("Error sending message:", err);
            this.state.messages.push({
                id: "err_" + Date.now(),
                role: "assistant",
                content: "⚠️ " + _t("Failed to connect to AI Assistant: ") + (err.message || err),
                approval_state: "none",
            });
        } finally {
            this.state.isSending = false;
        }
    }

    async createNewChat() {
        this.state.isLoading = true;
        try {
            const res = await this.rpc("/ara_copilot/create_thread", {});
            this.state.activeThreadId = res.thread_id;
            this.state.threadName = res.thread_data.name;
            this.state.messages = [];
            this.state.threads.unshift({
                id: res.thread_id,
                name: res.thread_data.name,
                write_date: new Date().toISOString(),
            });
            this.props.onThreadUpdated?.();
        } catch (err) {
            console.error("Failed to create new chat:", err);
        } finally {
            this.state.isLoading = false;
        }
    }

    async deleteCurrentChat() {
        if (!this.state.activeThreadId) return;
        const threadId = this.state.activeThreadId;
        this.dialog.add(CopilotPasswordConfirmDialog, {
            title: _t("Security Verification - Delete Session"),
            body: _t("To delete this chat session permanently, please enter your user account password to verify your identity."),
            confirmLabel: _t("Delete Session"),
            confirm: async (password) => {
                try {
                    const res = await this.rpc("/ara_copilot/delete_thread", {
                        thread_id: threadId,
                        password: password,
                    });
                    if (res && res.error) {
                        return res.error;
                    }
                    this.notification.add(_t("Chat session deleted successfully."), { type: "info" });
                    this.props.onThreadUpdated?.();
                    await this.createNewChat();
                    return null;
                } catch (err) {
                    return err.message || _t("Failed to delete chat session.");
                }
            },
        });
    }

    async switchThread(threadId) {
        if (this.state.activeThreadId === threadId) return;
        this.state.isLoading = true;
        try {
            const res = await this.rpc("/ara_copilot/get_thread", { thread_id: threadId });
            this.state.activeThreadId = res.id;
            this.state.threadName = res.name;
            this.state.isFavorite = Boolean(res.is_favorite);
            if (res.provider && res.provider.id) {
                this.state.providerInfo = res.provider;
            }
            this.state.messages = res.messages || [];
        } catch (err) {
            console.error("Failed to switch thread:", err);
        } finally {
            this.state.isLoading = false;
        }
    }

    async copyMessageContent(msg) {
        if (!msg || !msg.content) return;
        try {
            const textToCopy = msg.content;
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(textToCopy);
            } else {
                const textArea = document.createElement("textarea");
                textArea.value = textToCopy;
                textArea.style.position = "fixed";
                textArea.style.left = "-999999px";
                textArea.style.top = "-999999px";
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                document.execCommand("copy");
                textArea.remove();
            }
            msg.isCopied = true;
            this.notification.add(_t("Message copied to clipboard!"), { type: "success" });
            setTimeout(() => {
                msg.isCopied = false;
            }, 2000);
        } catch (err) {
            console.error("Failed to copy message:", err);
            this.notification.add(_t("Could not copy to clipboard"), { type: "danger" });
        }
    }

    async onProviderSelect(ev) {
        const providerId = parseInt(ev.target.value);
        if (!providerId || !this.state.activeThreadId) return;
        try {
            const res = await this.rpc("/ara_copilot/set_thread_provider", {
                thread_id: this.state.activeThreadId,
                provider_id: providerId,
            });
            if (res.success && res.provider) {
                this.state.providerInfo = res.provider;
                this.notification.add(
                    _t(`Switched to model: %s (%s)`).replace("%s", res.provider.name).replace("%s", res.provider.model),
                    { type: "info" }
                );
            }
        } catch (err) {
            console.error("Failed to switch provider:", err);
            this.notification.add(_t("Failed to switch AI model"), { type: "danger" });
        }
    }

    async toggleCurrentFavorite() {
        if (!this.state.activeThreadId) return;
        try {
            const res = await this.rpc("/ara_copilot/toggle_favorite_thread", {
                thread_id: this.state.activeThreadId,
            });
            if (res.success) {
                this.state.isFavorite = res.is_favorite;
                const favThread = this.state.threads.find((t) => t.id === this.state.activeThreadId);
                if (favThread) {
                    favThread.is_favorite = res.is_favorite;
                }
                const msg = res.is_favorite
                    ? _t("Chat session marked as favorite.")
                    : _t("Chat session removed from favorites.");
                this.notification.add(msg, { type: "info" });
                this.props.onThreadUpdated?.();
            }
        } catch (err) {
            console.error("Failed to toggle favorite:", err);
        }
    }

    async approveProposal(message) {
        if (!message || message.approval_state !== "pending") return;
        this.state.isSending = true;
        try {
            const res = await this.rpc("/ara_copilot/approve_proposal", {
                thread_id: this.state.activeThreadId,
                message_id: message.id,
            });

            if (res.error) {
                this.notification.add(res.error, { type: "danger" });
            } else {
                // Update proposal state
                message.approval_state = "approved";
                if (res.response_message) {
                    this.state.messages.push(res.response_message);
                }
                this.notification.add(_t("Action successfully executed!"), { type: "success" });
            }
        } catch (err) {
            this.notification.add(_t("Failed to approve action: ") + (err.message || err), { type: "danger" });
        } finally {
            this.state.isSending = false;
        }
    }

    async rejectProposal(message) {
        if (!message || message.approval_state !== "pending") return;
        this.state.isSending = true;
        try {
            const res = await this.rpc("/ara_copilot/reject_proposal", {
                thread_id: this.state.activeThreadId,
                message_id: message.id,
            });

            if (res.error) {
                this.notification.add(res.error, { type: "danger" });
            } else {
                message.approval_state = "rejected";
                if (res.response_message) {
                    this.state.messages.push(res.response_message);
                }
                this.notification.add(_t("Action canceled."), { type: "info" });
            }
        } catch (err) {
            this.notification.add(_t("Failed to reject action: ") + (err.message || err), { type: "danger" });
        } finally {
            this.state.isSending = false;
        }
    }

    triggerFileInput() {
        if (this.fileInputRef.el) {
            this.fileInputRef.el.click();
        }
    }

    async onFileSelected(ev) {
        const file = ev.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async () => {
            const base64Data = reader.result;
            try {
                const res = await this.rpc("/ara_copilot/upload_attachment", {
                    name: file.name,
                    data_base64: base64Data,
                    mimetype: file.type,
                });
                if (res.id) {
                    this.state.pendingAttachments.push(res);
                }
            } catch (err) {
                this.notification.add(_t("Failed to upload file: ") + (err.message || err), { type: "danger" });
            }
        };
        reader.readAsDataURL(file);
        ev.target.value = "";
    }

    removePendingAttachment(idx) {
        this.state.pendingAttachments.splice(idx, 1);
    }

    formatProposalVal(val) {
        if (val === null || val === undefined) return "-";
        if (typeof val === "object") {
            if (Array.isArray(val)) {
                return val
                    .map((item) => {
                        if (Array.isArray(item) && item.length === 3 && typeof item[2] === "object") {
                            item = item[2];
                        }
                        if (typeof item === "object" && item !== null) {
                            return Object.entries(item)
                                .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
                                .join(", ");
                        }
                        return String(item);
                    })
                    .join(" | ");
            }
            return JSON.stringify(val);
        }
        return String(val);
    }

    openRecordLink(model, resId, viewType = "form") {
        if (!model || !resId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: parseInt(resId, 10),
            views: [[false, viewType]],
            target: "current",
        });
    }

    onMessageContentClick(ev) {
        const linkEl = ev.target.closest("a");
        if (!linkEl) return;

        const href = linkEl.getAttribute("href") || "";
        const dataModel = linkEl.getAttribute("data-model");
        const dataId = linkEl.getAttribute("data-res-id");

        if (dataModel && dataId) {
            ev.preventDefault();
            this.openRecordLink(dataModel, dataId);
            return;
        }

        // Intercept hash-based Odoo record links: /#id=...&model=... or #id=...&model=...
        if (href.includes("model=") && href.includes("id=")) {
            ev.preventDefault();
            try {
                const hashPart = href.includes("#") ? href.split("#")[1] : href;
                const params = new URLSearchParams(hashPart);
                const model = params.get("model");
                const resId = params.get("id");
                const viewType = params.get("view_type") || "form";
                if (model && resId) {
                    this.openRecordLink(model, resId, viewType);
                }
            } catch (e) {
                console.warn("Could not parse record link:", href, e);
            }
        }
    }

    renderMarkdown(rawText) {
        if (!rawText) return markup("");
        let text = String(rawText).trim();

        // 1. Strip raw HTML wrapping tags if the LLM outputted them
        text = text
            .replace(/^<p>\s*/i, "")
            .replace(/\s*<\/p>$/i, "")
            .replace(/&lt;p&gt;/gi, "")
            .replace(/&lt;\/p&gt;/gi, "");

        // 2. Protect Code Blocks: ```code```
        const codeBlocks = [];
        text = text.replace(/```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g, (match, lang, code) => {
            const placeholder = `___ARA_CODE_${codeBlocks.length}___`;
            const cleanCode = code
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");
            codeBlocks.push(`<pre><code class="language-${lang || 'text'}">${cleanCode.trim()}</code></pre>`);
            return placeholder;
        });

        // 3. Normalize any stray HTML tags into clean text or linebreaks
        text = text
            .replace(/<br\s*\/?>/gi, "\n")
            .replace(/<\/?p>/gi, "\n\n")
            .replace(/<\/?div>/gi, "\n");

        text = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // 4. Inline code: `...`
        text = text.replace(/`([^`]+)`/g, "<code>$1</code>");

        // 5. Headings: ###, ##, #
        text = text.replace(/^### (.*$)/gim, "<h5>$1</h5>");
        text = text.replace(/^## (.*$)/gim, "<h4>$1</h4>");
        text = text.replace(/^# (.*$)/gim, "<h3>$1</h3>");

        // 6. Bold: **text**
        text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

        // 7. Italic: *text*
        text = text.replace(/(^|[^*])\*([^*]+)\*([^*]|$)/g, "$1<em>$2</em>$3");

        // 8. Markdown Links: [Label](url)
        // Detect if link is an Odoo record link (/#id=...&model=...)
        text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, label, url) => {
            const cleanUrl = url.trim();
            let dataAttr = "";
            let linkClass = "ara-chat-link";

            if (cleanUrl.includes("model=") && cleanUrl.includes("id=")) {
                linkClass += " ara-record-link";
                try {
                    const hashPart = cleanUrl.includes("#") ? cleanUrl.split("#")[1] : cleanUrl;
                    const params = new URLSearchParams(hashPart);
                    const m = params.get("model");
                    const id = params.get("id");
                    if (m && id) {
                        dataAttr = ` data-model="${m}" data-res-id="${id}"`;
                    }
                } catch (e) {}
            }
            return `<a href="${cleanUrl}" class="${linkClass}"${dataAttr} target="_self">${label}</a>`;
        });

        // 9. Markdown Tables
        if (text.includes("|")) {
            const lines = text.split("\n");
            let inTable = false;
            let tableHtml = '<div class="ara-table-wrapper"><table class="ara-chat-table">';
            const processedLines = [];

            for (let line of lines) {
                const trimmed = line.trim();
                if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
                    if (trimmed.includes("---")) {
                        continue; // table header separator line
                    }
                    if (!inTable) {
                        inTable = true;
                        tableHtml = '<div class="ara-table-wrapper"><table class="ara-chat-table">';
                    }
                    const cells = trimmed
                        .slice(1, -1)
                        .split("|")
                        .map((c) => c.trim());
                    const tag = !tableHtml.includes("</tr>") ? "th" : "td";
                    tableHtml += `<tr>${cells.map((c) => `<${tag}>${c}</${tag}>`).join("")}</tr>`;
                } else {
                    if (inTable) {
                        tableHtml += "</table></div>";
                        processedLines.push(tableHtml);
                        inTable = false;
                    }
                    processedLines.push(line);
                }
            }
            if (inTable) {
                tableHtml += "</table></div>";
                processedLines.push(tableHtml);
            }
            text = processedLines.join("\n");
        }

        // 10. Process paragraphs and linebreaks without wrapping block elements
        const blocks = text.split(/\n{2,}/);
        const renderedBlocks = blocks.map((block) => {
            const b = block.trim();
            if (!b) return "";
            // If block is already a block-level HTML element, don't wrap in <p>
            if (
                b.startsWith("<div") ||
                b.startsWith("<table") ||
                b.startsWith("<pre") ||
                b.startsWith("<h3") ||
                b.startsWith("<h4") ||
                b.startsWith("<h5") ||
                b.startsWith("___ARA_CODE_")
            ) {
                return b;
            }

            // Unordered list items inside a block
            if (b.startsWith("- ") || b.startsWith("* ")) {
                const listItems = b
                    .split("\n")
                    .map((l) => l.replace(/^[-*]\s+/, "").trim())
                    .filter(Boolean)
                    .map((li) => `<li>${li}</li>`)
                    .join("");
                return `<ul class="ara-chat-list">${listItems}</ul>`;
            }

            // Normal paragraph
            return `<p>${b.replace(/\n/g, "<br/>")}</p>`;
        });

        let finalHtml = renderedBlocks.join("\n");

        // 11. Restore Code Blocks
        codeBlocks.forEach((codeHtml, idx) => {
            finalHtml = finalHtml.replace(`___ARA_CODE_${idx}___`, codeHtml);
        });

        return markup(finalHtml);
    }
}
