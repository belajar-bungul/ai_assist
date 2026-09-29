/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class CopilotPasswordConfirmDialog extends Component {
    static template = "ara_ai_copilot_assistant.PasswordConfirmDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: { type: String, optional: true },
        body: { type: String, optional: true },
        confirm: Function,
        confirmLabel: { type: String, optional: true },
        cancel: { type: Function, optional: true },
        cancelLabel: { type: String, optional: true },
    };
    static defaultProps = {
        title: _t("Security Verification"),
        confirmLabel: _t("Delete Session"),
        cancelLabel: _t("Cancel"),
    };

    setup() {
        this.inputRef = useRef("passwordInput");
        this.state = useState({
            password: "",
            showPassword: false,
            errorMessage: "",
            isSubmitting: false,
        });

        onMounted(() => {
            if (this.inputRef.el) {
                this.inputRef.el.focus();
            }
        });
    }

    toggleShowPassword() {
        this.state.showPassword = !this.state.showPassword;
    }

    onInput() {
        if (this.state.errorMessage) {
            this.state.errorMessage = "";
        }
    }

    onKeyDown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onConfirm();
        }
    }

    async onConfirm() {
        if (!this.state.password) {
            this.state.errorMessage = _t("Please enter your password.");
            return;
        }
        this.state.isSubmitting = true;
        this.state.errorMessage = "";
        try {
            const error = await this.props.confirm(this.state.password);
            if (error) {
                this.state.errorMessage = error;
                this.state.isSubmitting = false;
                if (this.inputRef.el) {
                    this.inputRef.el.select();
                }
            } else {
                this.props.close();
            }
        } catch (err) {
            this.state.errorMessage = err.message || _t("Verification failed.");
            this.state.isSubmitting = false;
        }
    }

    onCancel() {
        if (this.props.cancel) {
            this.props.cancel();
        }
        this.props.close();
    }
}
