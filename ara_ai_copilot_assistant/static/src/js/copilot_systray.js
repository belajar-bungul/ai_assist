/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CopilotChatWindow } from "./copilot_chat_window";

export class AraCopilotSystray extends Component {
    static template = "ara_ai_copilot_assistant.SystrayItem";
    static props = {};

    setup() {
        this.actionService = useService("action");
    }

    onOpenWorkspace() {
        this.actionService.doAction("ara_ai_copilot_assistant.action_ara_ai_copilot_main");
    }
}

export const araCopilotSystrayItem = {
    Component: AraCopilotSystray,
};

registry.category("systray").add("ara_ai_copilot_assistant.systray", araCopilotSystrayItem, { sequence: 15 });
