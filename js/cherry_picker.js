import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function getWorkflowRunId(node) {
    return node._cherryPickerWorkflowRunId ?? node.output?.ui?.workflow_run_id ?? null;
}

app.registerExtension({
    name: "Comfy.CherryPicker",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "CherryPicker") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                onNodeCreated?.apply(this, arguments);

                // Add the Manual Save button
                const btn = this.addWidget("button", "🍒 SAVE IMAGE", "save_button", () => {
                    const oldLabel = btn.name;
                    btn.name = "⏳ SAVING...";

                    const workflowRunId = getWorkflowRunId(this);
                    const promise = api.fetchApi("/cherrypicker/save", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            node_id: this.id,
                            workflow_run_id: workflowRunId,
                        }),
                    });
                    const getData = (result) => {
                        if (result && typeof result.json === "function") {
                            if (!result.ok) throw new Error(`HTTP ${result.status}`);
                            return result.json();
                        }
                        return Promise.resolve(result);
                    };

                    promise
                        .then(getData)
                        .then((data) => {
                            if (data && data.status === "success") {
                                btn.name = "✅ SAVED!";
                                setTimeout(() => {
                                    btn.name = oldLabel;
                                }, 2000);
                            } else {
                                const message = (data && data.message) || "Unknown error";
                                app.ui?.showToast?.(`Save failed: ${message}`);
                                btn.name = oldLabel;
                            }
                        })
                        .catch((err) => {
                            console.error("CherryPicker save failed", err);
                            app.ui?.showToast?.("Save failed. See console for details.");
                            btn.name = oldLabel;
                        });
                });
                btn.serialize = false;
            };
        }
    },
});

// When our node finishes executing, store workflow_run_id so Save uses the right cache entry
api.addEventListener("executed", (event) => {
    const detail = event?.detail ?? event;
    const nodeId = detail?.node;
    const output = detail?.output;
    const workflowRunId = output?.ui?.workflow_run_id;
    if (workflowRunId == null || nodeId == null) return;
    const node = app.graph?.getNodeById?.(nodeId);
    if (node?.type === "CherryPicker") {
        node._cherryPickerWorkflowRunId = workflowRunId;
    }
});