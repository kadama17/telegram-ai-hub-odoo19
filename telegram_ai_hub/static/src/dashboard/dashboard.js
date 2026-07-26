/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class TelegramDashboard extends Component {
    static template = "telegram_ai_hub.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.state = useState({ loading: true, data: {} });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "rb.telegram.hub.dashboard",
            "dashboard_data",
            []
        );
        this.state.loading = false;
    }

    get activity() {
        const data = this.state.data;
        const incoming = data.activity_incoming || [];
        const outgoing = data.activity_outgoing || [];
        const maximum = Math.max(1, ...incoming, ...outgoing);
        return (data.activity_labels || []).map((label, index) => ({
            label,
            incoming: incoming[index] || 0,
            outgoing: outgoing[index] || 0,
            incomingHeight: `${Math.max(5, (100 * (incoming[index] || 0)) / maximum)}%`,
            outgoingHeight: `${Math.max(5, (100 * (outgoing[index] || 0)) / maximum)}%`,
        }));
    }

    get successStyle() {
        const rate = Math.max(0, Math.min(100, this.state.data.success_rate || 0));
        return `background: conic-gradient(#229ED9 ${rate}%, #e8eef2 ${rate}% 100%)`;
    }
}

registry.category("actions").add("rb_telegram_dashboard", TelegramDashboard);
