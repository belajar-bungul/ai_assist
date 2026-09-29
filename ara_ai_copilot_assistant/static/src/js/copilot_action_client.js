/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { CopilotPasswordConfirmDialog } from "./copilot_password_dialog";
import { CopilotChatWindow } from "./copilot_chat_window";

export class AraCopilotActionWorkspace extends Component {
    static template = "ara_ai_copilot_assistant.Workspace";
    static components = { CopilotChatWindow };
    static props = ["*"];

    setup() {
        this.rpc = rpc;
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.state = useState({
            threads: [],
            activeThreadId: null,
            searchQuery: "",
            showOnlyFavorites: false,
            isLoading: false,
        });

        this.searchTimeout = null;

        onWillStart(async () => {
            await this.loadThreads();
        });
    }

    onSearchInput(ev) {
        const val = ev.target.value;
        this.state.searchQuery = val;
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.performSearch(val);
        }, 200);
    }

    async clearSearch() {
        this.state.searchQuery = "";
        clearTimeout(this.searchTimeout);
        await this.performSearch("");
    }

    async performSearch(query) {
        try {
            const results = await this.rpc("/ara_copilot/search_threads", { query: query });
            this.state.threads = results || [];
        } catch (err) {
            console.error("Search failed:", err);
        }
    }

    async loadThreads() {
        this.state.isLoading = true;
        try {
            const res = await this.rpc("/ara_copilot/init", {});
            this.state.threads = res.threads || [];
            if (!this.state.activeThreadId && res.active_thread_id) {
                this.state.activeThreadId = res.active_thread_id;
            }
        } catch (err) {
            console.error("Failed to load threads:", err);
        } finally {
            this.state.isLoading = false;
        }
    }

    get displayedThreads() {
        if (this.state.showOnlyFavorites) {
            return this.state.threads.filter((t) => t.is_favorite);
        }
        return this.state.threads;
    }

    get favoriteCount() {
        return this.state.threads.filter((t) => t.is_favorite).length;
    }

    setFilterFavorites(onlyFavorites) {
        this.state.showOnlyFavorites = onlyFavorites;
    }

    async onToggleFavorite(ev, threadId) {
        ev.stopPropagation();
        try {
            const res = await this.rpc("/ara_copilot/toggle_favorite_thread", { thread_id: threadId });
            if (res.success) {
                const thread = this.state.threads.find((t) => t.id === threadId);
                if (thread) {
                    thread.is_favorite = res.is_favorite;
                }
                // Re-sort threads: favorites on top, then newest
                this.state.threads.sort((a, b) => {
                    if (a.is_favorite !== b.is_favorite) {
                        return b.is_favorite ? 1 : -1;
                    }
                    return new Date(b.write_date) - new Date(a.write_date);
                });
                const msg = res.is_favorite
                    ? _t("Conversation marked as favorite.")
                    : _t("Conversation removed from favorites.");
                this.notification.add(msg, { type: "info" });
            }
        } catch (err) {
            console.error("Failed to toggle favorite:", err);
            this.notification.add(_t("Failed to update favorite status"), { type: "danger" });
        }
    }

    onSelectThread(threadId) {
        this.state.activeThreadId = threadId;
    }

    async onNewChat() {
        try {
            const res = await this.rpc("/ara_copilot/create_thread", {});
            this.state.activeThreadId = res.thread_id;
            await this.loadThreads();
        } catch (err) {
            console.error("Failed to create new chat:", err);
        }
    }

    async onDeleteThread(ev, threadId) {
        ev.stopPropagation();
        this.dialog.add(CopilotPasswordConfirmDialog, {
            title: _t("Security Verification - Delete Session"),
            body: _t("To delete this conversation session permanently, please enter your user account password to verify your identity."),
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
                    this.state.threads = this.state.threads.filter((t) => t.id !== threadId);
                    if (this.state.activeThreadId === threadId) {
                        if (this.state.threads.length > 0) {
                            this.onSelectThread(this.state.threads[0].id);
                        } else {
                            await this.onNewChat();
                        }
                    }
                    this.notification.add(_t("Conversation session deleted successfully."), { type: "info" });
                    return null;
                } catch (err) {
                    return err.message || _t("Failed to delete conversation.");
                }
            },
        });
    }
}

registry.category("actions").add("ara_ai_copilot_main", AraCopilotActionWorkspace);
