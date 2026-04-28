import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

/**
 * ComfyUI GPT Image 2 Prompt - Frontend Extension
 * All preview images are served from local files via API.
 * Uses DOM-based image widget for reliable preview display.
 * Supports category-based filtering of prompt selections.
 */

const EXT_NAME = "GPTImage2Prompt";
const RESOLVE_API = "/gpt_image2_prompt/resolve_selection";
const CHOICES_API = "/gpt_image2_prompt/choices_by_category";
const REFRESH_API = "/gpt_image2_prompt/refresh_choices";

/**
 * Build image URL using query parameter approach.
 * Uses the ComfyUI server origin to build an absolute URL.
 */
function buildImageUrl(imagePath) {
    if (!imagePath) return "";
    // Use absolute URL based on current page origin to avoid relative path issues
    const origin = window.location.origin;
    return `${origin}/gpt_image2_prompt/image?path=${encodeURIComponent(imagePath)}`;
}

/**
 * Create a DOM-based image preview container element.
 */
function createImagePreview() {
    const container = document.createElement("div");
    container.style.cssText = [
        "width: 100%",
        "background: #1a1a2e",
        "border-radius: 8px",
        "overflow: hidden",
        "text-align: center",
        "min-height: 60px",
        "position: relative",
    ].join(";");

    const placeholder = document.createElement("div");
    placeholder.style.cssText = "color:#666; font-size:12px; padding:20px;";
    placeholder.textContent = "Select a prompt to see preview";
    container.appendChild(placeholder);

    const imgEl = document.createElement("img");
    imgEl.style.cssText = [
        "max-width: 100%",
        "max-height: 350px",
        "display: none",
        "margin: 0 auto",
        "border-radius: 4px",
    ].join(";");
    // Set crossorigin to avoid tainted canvas issues
    imgEl.crossOrigin = "anonymous";
    container.appendChild(imgEl);

    const label = document.createElement("div");
    label.style.cssText = [
        "position: absolute",
        "top: 0; left: 0; right: 0",
        "background: rgba(0,0,0,0.55)",
        "color: #fff",
        "font-size: 11px",
        "padding: 3px 8px",
        "display: none",
    ].join(";");
    container.appendChild(label);

    imgEl.onload = () => {
        console.log("[GPTImage2Prompt] Image loaded OK:", imgEl.src.substring(0, 80));
        imgEl.style.display = "block";
        placeholder.style.display = "none";
        label.style.display = "block";
    };
    imgEl.onerror = (e) => {
        console.error("[GPTImage2Prompt] Image load FAILED. src:", imgEl.src);
        imgEl.style.display = "none";
        placeholder.style.display = "block";
        placeholder.textContent = "Image load failed - check browser console";
        label.style.display = "none";
    };

    return {
        container,
        imgEl,
        placeholder,
        label,
        setImage(imagePath, title) {
            if (!imagePath) { this.clear(); return; }
            const url = buildImageUrl(imagePath);
            console.log("[GPTImage2Prompt] setImage:", imagePath, "->", url);
            placeholder.textContent = "Loading...";
            placeholder.style.display = "block";
            imgEl.style.display = "none";
            label.style.display = "none";
            // Force reload by clearing src first
            imgEl.src = "";
            // Use setTimeout to ensure the browser registers the src change
            setTimeout(() => { imgEl.src = url; }, 10);
            if (title) label.textContent = title;
        },
        clear() {
            imgEl.style.display = "none";
            imgEl.removeAttribute("src");
            label.style.display = "none";
            placeholder.style.display = "block";
            placeholder.textContent = "Select a prompt to see preview";
        },
    };
}

/**
 * Fetch choices grouped by category from the API.
 */
async function fetchChoicesByCategory() {
    try {
        const resp = await api.fetchApi(CHOICES_API);
        if (resp.ok) {
            const data = await resp.json();
            console.log("[GPTImage2Prompt] choices_by_category loaded:",
                Object.keys(data).map(k => `${k}(${data[k]?.length})`).join(", "));
            return data;
        }
        console.warn("[GPTImage2Prompt] choices_by_category HTTP", resp.status);
    } catch (e) {
        console.warn("[GPTImage2Prompt] Failed to fetch choices:", e);
    }
    return null;
}

/**
 * Create a refresh button DOM element.
 */
function createRefreshButton(label, onClick) {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.style.cssText = [
        "width: 100%",
        "padding: 6px 12px",
        "background: #2d5a27",
        "color: #fff",
        "border: 1px solid #3d7a37",
        "border-radius: 6px",
        "cursor: pointer",
        "font-size: 12px",
        "font-weight: bold",
        "margin-top: 4px",
    ].join(";");
    btn.onmouseenter = () => { btn.style.background = "#3d7a37"; };
    btn.onmouseleave = () => { btn.style.background = "#2d5a27"; };
    btn.onclick = onClick;
    return btn;
}

/**
 * Refresh choices for a node by calling the refresh API.
 * Updates combo widget values, category data, and optionally category widget.
 */
async function refreshNodeChoices(node, comboWidget, categoryWidget) {
    try {
        const resp = await api.fetchApi(REFRESH_API);
        if (!resp.ok) {
            console.warn("[GPTImage2Prompt] Refresh HTTP", resp.status);
            return false;
        }
        const data = await resp.json();

        // Update combo values
        const newChoices = data.choices || [];
        if (newChoices.length > 0 && comboWidget) {
            node._allComboValues = [...newChoices];
            comboWidget.options.values = newChoices;
            // Keep current selection if still valid, else reset
            if (!newChoices.includes(comboWidget.value)) {
                comboWidget.value = newChoices[0];
            }
        }

        // Update grouped choices
        if (data.grouped) {
            node._choicesByCategory = data.grouped;
        }

        // Update category widget if present
        if (categoryWidget && data.categories) {
            categoryWidget.options.values = data.categories;
            if (!data.categories.includes(categoryWidget.value)) {
                categoryWidget.value = "all";
            }
        }

        // Re-apply current category filter
        if (categoryWidget && node._filterByCategory) {
            node._filterByCategory(categoryWidget.value, comboWidget);
        }

        node.setDirtyCanvas(true, true);
        console.log("[GPTImage2Prompt] Refreshed:", newChoices.length, "choices");
        return true;
    } catch (e) {
        console.warn("[GPTImage2Prompt] Refresh error:", e);
        return false;
    }
}

// ============================================================
// Main Extension
// ============================================================
app.registerExtension({
    name: EXT_NAME,

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        // --------------------------------------------------
        // GPTImage2PromptSelector
        // --------------------------------------------------
        if (nodeData.name === "GPTImage2PromptSelector") {
            const origOnNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                origOnNodeCreated?.apply(this, arguments);

                const node = this;

                // Create DOM image preview
                const preview = createImagePreview();
                node._preview = preview;

                // Add as DOM widget
                const domWidget = node.addDOMWidget(
                    "image_preview", "custom", preview.container,
                    {
                        getValue() { return ""; },
                        setValue() {},
                        getMinHeight() { return 200; },
                    }
                );
                domWidget.serializeValue = async () => undefined;

                // Add refresh button
                const refreshBtn = createRefreshButton("🔄 Refresh Prompt List", async () => {
                    refreshBtn.textContent = "⏳ Refreshing...";
                    refreshBtn.style.background = "#555";
                    const comboW = node.widgets?.find(w => w.name === "prompt_selection");
                    const catW = node.widgets?.find(w => w.name === "category");
                    const ok = await refreshNodeChoices(node, comboW, catW);
                    refreshBtn.textContent = ok ? "✅ Refreshed!" : "❌ Failed";
                    refreshBtn.style.background = ok ? "#2d5a27" : "#5a2727";
                    setTimeout(() => {
                        refreshBtn.textContent = "🔄 Refresh Prompt List";
                        refreshBtn.style.background = "#2d5a27";
                    }, 2000);
                });
                const refreshWidget = node.addDOMWidget(
                    "refresh_btn", "custom", refreshBtn,
                    {
                        getValue() { return ""; },
                        setValue() {},
                        getMinHeight() { return 32; },
                    }
                );
                refreshWidget.serializeValue = async () => undefined;
                let setupAttempts = 0;
                const setupWidgets = async () => {
                    setupAttempts++;
                    const categoryWidget = node.widgets?.find(w => w.name === "category");
                    const comboWidget = node.widgets?.find(w => w.name === "prompt_selection");

                    if (!comboWidget) {
                        if (setupAttempts < 20) {
                            setTimeout(setupWidgets, 200);
                        } else {
                            console.error("[GPTImage2Prompt] Could not find prompt_selection widget after 20 attempts");
                        }
                        return;
                    }

                    console.log("[GPTImage2Prompt] Widgets found. category:", !!categoryWidget,
                        "combo values:", comboWidget.options?.values?.length);

                    // Save the full original choices list
                    node._allComboValues = [...(comboWidget.options?.values || [])];

                    // Fetch category-grouped choices from API
                    const grouped = await fetchChoicesByCategory();
                    if (grouped) {
                        node._choicesByCategory = grouped;
                    }

                    // === Hook category widget: callback + value polling ===
                    if (categoryWidget) {
                        // Method 1: Hook callback
                        const origCatCb = categoryWidget.callback;
                        categoryWidget.callback = function (value) {
                            if (origCatCb) origCatCb.call(this, value);
                            console.log("[GPTImage2Prompt] Category callback fired:", value);
                            node._filterByCategory(value, comboWidget);
                        };

                        // Method 2: Poll for value changes (backup)
                        // This handles cases where ComfyUI changes the value
                        // without triggering the callback.
                        let lastCatValue = categoryWidget.value;
                        const pollCategory = () => {
                            if (!node.graph) return; // Node removed
                            const current = categoryWidget.value;
                            if (current !== lastCatValue) {
                                console.log("[GPTImage2Prompt] Category poll detected change:",
                                    lastCatValue, "->", current);
                                lastCatValue = current;
                                node._filterByCategory(current, comboWidget);
                            }
                            requestAnimationFrame(pollCategory);
                        };
                        requestAnimationFrame(pollCategory);
                    }

                    // === Hook combo widget for preview ===
                    const origComboCb = comboWidget.callback;
                    comboWidget.callback = function (value) {
                        if (origComboCb) origComboCb.call(this, value);
                        node._resolveAndPreview(value);
                    };

                    // Also poll combo for changes
                    let lastComboValue = comboWidget.value;
                    const pollCombo = () => {
                        if (!node.graph) return;
                        const current = comboWidget.value;
                        if (current !== lastComboValue) {
                            lastComboValue = current;
                            node._resolveAndPreview(current);
                        }
                        requestAnimationFrame(pollCombo);
                    };
                    requestAnimationFrame(pollCombo);

                    // Apply initial filter if category is not "all"
                    const currentCat = categoryWidget?.value || "all";
                    if (currentCat !== "all") {
                        node._filterByCategory(currentCat, comboWidget);
                    }

                    // Auto-preview the initial selection
                    if (comboWidget.value) {
                        setTimeout(() => node._resolveAndPreview(comboWidget.value), 300);
                    }
                };

                setTimeout(setupWidgets, 150);
                this.setSize([450, 650]);
            };

            /**
             * Filter prompt_selection combo widget by category.
             */
            nodeType.prototype._filterByCategory = function (category, comboWidget) {
                if (!comboWidget) return;

                let filteredValues;

                if (category === "all") {
                    filteredValues = this._allComboValues || [];
                } else if (this._choicesByCategory && this._choicesByCategory[category]) {
                    filteredValues = this._choicesByCategory[category].map(c => c.value);
                } else {
                    // Fallback: filter by category tag in the choice string
                    filteredValues = (this._allComboValues || []).filter(choice => {
                        if (category === "custom") return choice.startsWith("[custom_");
                        return choice.includes(`[${category}]`);
                    });
                }

                if (filteredValues.length === 0) {
                    filteredValues = ["No prompts in this category"];
                }

                console.log("[GPTImage2Prompt] Filter by", category, "=>", filteredValues.length, "items");

                comboWidget.options.values = filteredValues;
                comboWidget.value = filteredValues[0];
                this._resolveAndPreview(filteredValues[0]);
                this.setDirtyCanvas(true, true);
            };

            /**
             * Resolve selection: fetch prompt text + image from API,
             * fill edit_prompt widget and load preview image.
             */
            nodeType.prototype._resolveAndPreview = async function (selection) {
                if (!selection || selection.startsWith("No prompts")) return;

                try {
                    const resp = await api.fetchApi(
                        `${RESOLVE_API}?selection=${encodeURIComponent(selection)}`
                    );
                    if (!resp.ok) {
                        console.warn("[GPTImage2Prompt] Resolve HTTP", resp.status, "for:", selection);
                        return;
                    }
                    const data = await resp.json();

                    // Fill edit_prompt
                    const editWidget = this.widgets?.find(w => w.name === "edit_prompt");
                    if (editWidget) {
                        editWidget.value = data.text || "(No prompt text available)";
                    }

                    // Update preview image
                    if (this._preview) {
                        if (data.image_path && data.has_image) {
                            const title = data.title || data.category || "Preview";
                            this._preview.setImage(data.image_path, `[${data.category}] ${title}`);
                        } else if (data.image_path && !data.has_image) {
                            this._preview.clear();
                            this._preview.placeholder.textContent =
                                `Image not on disk: ${data.image_path}`;
                        } else {
                            this._preview.clear();
                        }
                    }

                    this.setDirtyCanvas(true, true);
                } catch (e) {
                    console.warn("[GPTImage2Prompt] Resolve error:", e);
                }
            };

            /**
             * After execution, update preview from output.
             */
            const origOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (output) {
                origOnExecuted?.apply(this, arguments);
                if (output?.image_path?.[0] && this._preview) {
                    this._preview.setImage(output.image_path[0], "Executed");
                }
            };
        }

        // --------------------------------------------------
        // GPTImage2PromptPreview
        // --------------------------------------------------
        if (nodeData.name === "GPTImage2PromptPreview") {
            const origOnNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                origOnNodeCreated?.apply(this, arguments);

                const node = this;
                const preview = createImagePreview();
                node._preview = preview;

                const domWidget = node.addDOMWidget(
                    "image_preview", "custom", preview.container,
                    {
                        getValue() { return ""; },
                        setValue() {},
                        getMinHeight() { return 200; },
                    }
                );
                domWidget.serializeValue = async () => undefined;

                // --- Add prompt text display widget ---
                const textContainer = document.createElement("div");
                textContainer.style.cssText = [
                    "width: 100%",
                    "background: #16213e",
                    "border-radius: 6px",
                    "padding: 8px",
                    "margin-top: 4px",
                    "color: #ccc",
                    "font-size: 11px",
                    "max-height: 120px",
                    "overflow-y: auto",
                    "white-space: pre-wrap",
                    "word-break: break-word",
                ].join(";");
                textContainer.textContent = "Select a prompt to see text";
                node._textContainer = textContainer;

                const textWidget = node.addDOMWidget(
                    "prompt_text_display", "custom", textContainer,
                    {
                        getValue() { return ""; },
                        setValue() {},
                        getMinHeight() { return 60; },
                    }
                );
                textWidget.serializeValue = async () => undefined;

                // Add refresh button
                const refreshBtn = createRefreshButton("🔄 Refresh Prompt List", async () => {
                    refreshBtn.textContent = "⏳ Refreshing...";
                    refreshBtn.style.background = "#555";
                    const comboW = node.widgets?.find(w => w.name === "prompt_selection");
                    const ok = await refreshNodeChoices(node, comboW, null);
                    refreshBtn.textContent = ok ? "✅ Refreshed!" : "❌ Failed";
                    refreshBtn.style.background = ok ? "#2d5a27" : "#5a2727";
                    setTimeout(() => {
                        refreshBtn.textContent = "🔄 Refresh Prompt List";
                        refreshBtn.style.background = "#2d5a27";
                    }, 2000);
                });
                const refreshWidget = node.addDOMWidget(
                    "refresh_btn", "custom", refreshBtn,
                    {
                        getValue() { return ""; },
                        setValue() {},
                        getMinHeight() { return 32; },
                    }
                );
                refreshWidget.serializeValue = async () => undefined;

                // --- Real-time preview: hook combo widget ---
                let setupAttempts = 0;
                const setupWidgets = async () => {
                    setupAttempts++;
                    const comboWidget = node.widgets?.find(w => w.name === "prompt_selection");
                    if (!comboWidget) {
                        if (setupAttempts < 20) setTimeout(setupWidgets, 200);
                        return;
                    }

                    // Hook callback
                    const origCb = comboWidget.callback;
                    comboWidget.callback = function (value) {
                        if (origCb) origCb.call(this, value);
                        node._resolvePreview(value);
                    };

                    // Poll for changes (backup)
                    let lastValue = comboWidget.value;
                    const poll = () => {
                        if (!node.graph) return;
                        const current = comboWidget.value;
                        if (current !== lastValue) {
                            lastValue = current;
                            node._resolvePreview(current);
                        }
                        requestAnimationFrame(poll);
                    };
                    requestAnimationFrame(poll);

                    // Auto-preview initial selection
                    if (comboWidget.value) {
                        setTimeout(() => node._resolvePreview(comboWidget.value), 300);
                    }
                };
                setTimeout(setupWidgets, 150);

                node.setSize([400, 500]);
            };

            /**
             * Resolve selection and update preview image + text.
             */
            nodeType.prototype._resolvePreview = async function (selection) {
                if (!selection || selection.startsWith("No prompts")) return;
                try {
                    const resp = await api.fetchApi(
                        `${RESOLVE_API}?selection=${encodeURIComponent(selection)}`
                    );
                    if (!resp.ok) return;
                    const data = await resp.json();

                    // Update preview image
                    if (this._preview) {
                        if (data.image_path && data.has_image) {
                            const title = data.title || data.category || "Preview";
                            this._preview.setImage(data.image_path, `[${data.category}] ${title}`);
                        } else {
                            this._preview.clear();
                            if (data.image_path) {
                                this._preview.placeholder.textContent = `Image not on disk: ${data.image_path}`;
                            }
                        }
                    }

                    // Update text display
                    if (this._textContainer) {
                        this._textContainer.textContent = data.text || "(No prompt text)";
                    }

                    this.setDirtyCanvas(true, true);
                } catch (e) {
                    console.warn("[GPTImage2Prompt] Preview resolve error:", e);
                }
            };

            /**
             * After execution, also update from output.
             */
            const origOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (output) {
                origOnExecuted?.apply(this, arguments);
                if (output?.image_path?.[0] && this._preview) {
                    this._preview.setImage(output.image_path[0], "Executed");
                }
                if (output?.text?.[0] && this._textContainer) {
                    this._textContainer.textContent = output.text[0];
                }
            };
        }

        // --------------------------------------------------
        // GPTImage2CustomPromptSaver
        // --------------------------------------------------
        if (nodeData.name === "GPTImage2CustomPromptSaver") {
            const origOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (output) {
                origOnExecuted?.apply(this, arguments);
                if (output?.status?.[0]) {
                    const msg = output.status[0];
                    this.bgcolor = msg.includes("Saved") ? "#1a3d1a" : "#3d1a1a";
                    // Auto-notify: trigger refresh on all Selector/Preview nodes in graph
                    if (msg.includes("Saved") && this.graph) {
                        const allNodes = this.graph._nodes || [];
                        for (const n of allNodes) {
                            if (n.type === "GPTImage2PromptSelector" || n.type === "GPTImage2PromptPreview") {
                                const combo = n.widgets?.find(w => w.name === "prompt_selection");
                                const cat = n.widgets?.find(w => w.name === "category");
                                if (combo) {
                                    refreshNodeChoices(n, combo, cat);
                                }
                            }
                        }
                    }
                }
            };
        }

        // --------------------------------------------------
        // GPTImage2ExecutionChecker
        // --------------------------------------------------
        if (nodeData.name === "GPTImage2ExecutionChecker") {
            const origOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (output) {
                origOnExecuted?.apply(this, arguments);
                if (output?.is_healthy != null) {
                    const isHealthy = output.is_healthy[0];
                    this.bgcolor = isHealthy ? "#1a3d1a" : "#3d1a1a";
                }
            };
        }

        // --------------------------------------------------
        // GPTImage2PromptUpdater
        // --------------------------------------------------
        if (nodeData.name === "GPTImage2PromptUpdater") {
            const origOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (output) {
                origOnExecuted?.apply(this, arguments);
                if (output?.status?.[0]) {
                    const status = output.status[0];
                    if (status.includes("Total")) {
                        this.bgcolor = "#1a3d1a";
                    } else if (status.includes("Failed") || status.includes("error")) {
                        this.bgcolor = "#3d1a1a";
                    } else {
                        this.bgcolor = "#2a2a1a";
                    }
                    // Auto-refresh all Selector/Preview nodes after update
                    if (this.graph) {
                        const allNodes = this.graph._nodes || [];
                        for (const n of allNodes) {
                            if (n.type === "GPTImage2PromptSelector" || n.type === "GPTImage2PromptPreview") {
                                const combo = n.widgets?.find(w => w.name === "prompt_selection");
                                const cat = n.widgets?.find(w => w.name === "category");
                                if (combo) {
                                    refreshNodeChoices(n, combo, cat);
                                }
                            }
                        }
                    }
                }
            };
        }
    },

    async setup() {
        console.log("[GPTImage2Prompt] Extension loaded v2. Images served locally.");
    },
});
