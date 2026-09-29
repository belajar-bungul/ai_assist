/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";

export const copilotService = {
    dependencies: ["action", "notification"],
    start(env, { action, notification }) {
        const state = reactive({
            isOpen: false,
            activeThreadId: null,
            unreadCount: 0,
            providerInfo: null,
        });

        function toggle() {
            state.isOpen = !state.isOpen;
        }

        function open() {
            state.isOpen = true;
        }

        function close() {
            state.isOpen = false;
        }

        function getCurrentContext() {
            const controller = action.currentController;
            if (!controller) {
                return null;
            }
            const props = controller.props || {};
            const resModel = controller.resModel || props.resModel || props.model;
            const resId = controller.resId || props.resId;
            const displayName = controller.displayName || (controller.action && controller.action.name) || "";
            const viewType = (controller.view && controller.view.type) || "list";

            return {
                resModel: resModel || null,
                resId: resId || null,
                displayName: displayName || null,
                viewType: viewType,
            };
        }

        function executeClientAction(payload) {
            if (!payload) return;
            if (payload.client_action === "navigate") {
                const targetModel = payload.model;
                const targetResId = payload.res_id;
                const viewType = payload.view_type || (targetResId ? "form" : "list");
                const domain = payload.domain || [];

                action.doAction({
                    type: "ir.actions.act_window",
                    name: payload.title || targetModel,
                    res_model: targetModel,
                    res_id: targetResId || undefined,
                    views: targetResId ? [[false, "form"]] : [[false, "list"], [false, "form"]],
                    domain: domain,
                    target: "current",
                });
            }
        }

        return {
            state,
            toggle,
            open,
            close,
            getCurrentContext,
            executeClientAction,
        };
    },
};

registry.category("services").add("copilot", copilotService);
