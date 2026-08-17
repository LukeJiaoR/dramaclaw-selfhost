const state = { services: [], bindings: {}, routes: [], capabilities: [], protocols: [], filter: "all", workflows: [] };
const labels = {
  text: "文本",
  vision: "视觉",
  embedding: "嵌入",
  image: "图片",
  storyboard_image: "分镜图",
  video: "视频",
  tts: "语音",
};
const defaultCapabilities = ["text", "vision", "image", "storyboard_image", "video", "tts"];
const $ = (id) => document.getElementById(id);

function toast(message, error = false) {
  const el = $("toast");
  el.textContent = message;
  el.className = error ? "show error" : "show";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.className = ""; }, 2800);
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(body.detail || body.error || body || `HTTP ${response.status}`);
  return body;
}

async function load() {
  try {
    Object.assign(state, await request("/api/state"));
    $("health").textContent = `${state.services.length} 个服务`;
    $("health").className = "status ok";
    render();
  } catch (error) {
    $("health").textContent = "连接失败";
    $("health").className = "status error";
    toast(error.message, true);
  }
}

function serviceOptions(capability, selected = "") {
  const type = capability === "vision" ? "text" : capability;
  return state.services
    .filter((service) => service.is_active && service.service_type === type)
    .map((service) => `<option value="${service.id}" ${service.id === selected ? "selected" : ""}>${escapeHtml(service.name)}</option>`)
    .join("");
}

function renderBindings() {
  $("bindings").innerHTML = defaultCapabilities.map((capability) => {
    const binding = state.bindings[capability] || {};
    const service = state.services.find((item) => item.id === binding.service_id);
    const model = binding.model || service?.default_model || "";
    return `<div class="binding">
      <strong>${labels[capability]}</strong>
      <select data-binding-service="${capability}">
        <option value="">未配置</option>${serviceOptions(capability, binding.service_id)}
      </select>
      <input data-binding-model="${capability}" value="${escapeAttr(model)}" placeholder="默认模型" />
    </div>`;
  }).join("");
  document.querySelectorAll("[data-binding-service]").forEach((element) => {
    element.addEventListener("change", () => saveBinding(element.dataset.bindingService));
  });
  document.querySelectorAll("[data-binding-model]").forEach((element) => {
    element.addEventListener("change", () => saveBinding(element.dataset.bindingModel));
  });
}

async function saveBinding(capability) {
  const serviceId = document.querySelector(`[data-binding-service="${capability}"]`).value;
  const model = document.querySelector(`[data-binding-model="${capability}"]`).value.trim();
  if (!serviceId) return;
  try {
    await request(`/api/bindings/${capability}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service_id: serviceId, model }),
    });
    $("binding-save-state").textContent = "已保存";
    setTimeout(() => { $("binding-save-state").textContent = ""; }, 1200);
    await load();
  } catch (error) { toast(error.message, true); }
}

function renderFilters() {
  const types = ["all", ...new Set(state.services.map((service) => service.service_type))];
  $("type-filter").innerHTML = types.map((type) => `<button class="${state.filter === type ? "active" : ""}" data-filter="${type}">${type === "all" ? "全部" : labels[type] || type}</button>`).join("");
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => { state.filter = button.dataset.filter; renderServices(); renderFilters(); });
  });
}

function renderServices() {
  const services = state.filter === "all" ? state.services : state.services.filter((service) => service.service_type === state.filter);
  $("services").innerHTML = services.length ? services.map((service) => `<tr>
    <td><span class="name">${escapeHtml(service.name)}</span><span class="sub">${escapeHtml(service.provider)}</span></td>
    <td><span class="badge ${service.is_default ? "default" : ""}">${labels[service.service_type] || service.service_type}</span></td>
    <td>${escapeHtml(service.protocol)}</td>
    <td>${escapeHtml(service.default_model || "-")}</td>
    <td><div class="url" title="${escapeAttr(service.base_url)}">${escapeHtml(service.base_url || "-")}</div></td>
    <td><span class="badge ${service.is_active ? "" : "off"}">${service.is_active ? "启用" : "停用"}</span></td>
    <td class="right"><div class="row-actions"><button class="button small secondary" data-edit="${service.id}">编辑</button><button class="button small danger" data-delete="${service.id}">删除</button></div></td>
  </tr>`).join("") : `<tr><td colspan="7" class="empty">暂无服务</td></tr>`;
  document.querySelectorAll("[data-edit]").forEach((button) => button.addEventListener("click", () => openService(button.dataset.edit)));
  document.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", () => removeService(button.dataset.delete)));
}

function renderRoutes() {
  $("routes").innerHTML = state.routes.length ? state.routes.map((route) => {
    const service = state.services.find((item) => item.id === route.service_id);
    return `<div class="route-row"><code>${escapeHtml(route.incoming_model)}</code><span>${labels[route.capability] || route.capability}</span><span>${escapeHtml(service?.name || "已删除")}</span><span>${escapeHtml(route.upstream_model || service?.default_model || "")}</span><button class="button small danger" data-route-delete="${encodeURIComponent(route.incoming_model)}">删除</button></div>`;
  }).join("") : `<div class="empty">使用默认能力路由</div>`;
  document.querySelectorAll("[data-route-delete]").forEach((button) => button.addEventListener("click", async () => {
    try { await request(`/api/routes/${button.dataset.routeDelete}`, { method: "DELETE" }); await load(); } catch (error) { toast(error.message, true); }
  }));
}

function render() { renderBindings(); renderFilters(); renderServices(); renderRoutes(); fillStaticOptions(); }

function fillStaticOptions() {
  $("service-type").innerHTML = state.capabilities.filter((item) => item !== "vision").map((item) => `<option value="${item}">${labels[item] || item}</option>`).join("");
  $("service-protocol").innerHTML = state.protocols.map((item) => `<option value="${item}">${item}</option>`).join("");
  $("route-capability").innerHTML = state.capabilities.map((item) => `<option value="${item}">${labels[item] || item}</option>`).join("");
  $("route-service").innerHTML = state.services.filter((item) => item.is_active).map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
}

function openService(id = "") {
  const service = state.services.find((item) => item.id === id);
  $("service-dialog-title").textContent = service ? "编辑服务" : "新增服务";
  $("service-id").value = service?.id || "";
  $("service-name").value = service?.name || "";
  $("service-type").value = service?.service_type || "text";
  $("service-provider").value = service?.provider || "openai";
  $("service-protocol").value = service?.protocol || "openai";
  $("service-base-url").value = service?.base_url || "";
  $("service-api-key").value = "";
  $("service-models").value = (service?.models || []).join(", ");
  $("service-default-model").value = service?.default_model || "";
  $("service-priority").value = service?.priority || 0;
  $("service-endpoint").value = service?.endpoint || "";
  $("service-query-endpoint").value = service?.query_endpoint || "";
  const settings = structuredClone(service?.settings || {});
  state.workflows = Array.isArray(settings.workflows) ? settings.workflows : [];
  delete settings.workflows;
  $("service-settings").value = JSON.stringify(settings, null, 2);
  $("service-active").checked = service?.is_active ?? true;
  $("service-default").checked = service?.is_default ?? false;
  renderWorkflowEditor();
  $("service-dialog").showModal();
}

function isComfyProtocol() {
  return ["comfyui", "comfyui_native"].includes($("service-protocol").value);
}

function renderWorkflowEditor() {
  const isComfy = isComfyProtocol();
  $("comfy-workflows-section").hidden = !isComfy;
  $("service-endpoint").closest("label").hidden = isComfy;
  $("service-query-endpoint").closest("label").hidden = isComfy;
  $("service-base-url").placeholder = isComfy ? "http://host.docker.internal:8188" : "https://api.example.com/v1";
  if (isComfy && $("service-provider").value === "openai") $("service-provider").value = "comfyui";
  if (!isComfy) return;
  $("comfy-workflows").innerHTML = state.workflows.length ? state.workflows.map((route, index) => `<div class="workflow-item" data-workflow="${index}">
    <div class="workflow-row">
      <label>Workflow ID<input data-workflow-id value="${escapeAttr(route.id || `workflow-${index + 1}`)}" required /></label>
      <label>适用模式<input data-workflow-modes value="${escapeAttr((route.modes || []).join(", "))}" placeholder="text_to_video, first_frame" /></label>
      <button class="icon-button workflow-remove" data-workflow-remove="${index}" aria-label="删除 Workflow" title="删除 Workflow" type="button">×</button>
    </div>
    <label>Workflow JSON<textarea data-workflow-json rows="9" spellcheck="false">${escapeHtml(JSON.stringify(route.workflow || {}, null, 2))}</textarea></label>
    <label>节点绑定 JSON（可选）<textarea data-workflow-bindings rows="3" spellcheck="false" placeholder='{"prompt":{"node":"6","input":"text"}}'>${escapeHtml(JSON.stringify(route.bindings || {}, null, 2))}</textarea></label>
  </div>`).join("") : `<div class="empty workflow-empty">尚未添加 Workflow</div>`;
  document.querySelectorAll("[data-workflow-remove]").forEach((button) => button.addEventListener("click", () => {
    collectWorkflows();
    state.workflows.splice(Number(button.dataset.workflowRemove), 1);
    renderWorkflowEditor();
  }));
}

function collectWorkflows() {
  if (!isComfyProtocol()) return [];
  return [...document.querySelectorAll("[data-workflow]")].map((element) => {
    let workflow;
    let bindings;
    try { workflow = JSON.parse(element.querySelector("[data-workflow-json]").value || "{}"); }
    catch { throw new Error("Workflow JSON 格式不正确"); }
    try { bindings = JSON.parse(element.querySelector("[data-workflow-bindings]").value || "{}"); }
    catch { throw new Error("节点绑定 JSON 格式不正确"); }
    if (!Object.keys(workflow).length) throw new Error("Workflow JSON 不能为空");
    return {
      id: element.querySelector("[data-workflow-id]").value.trim(),
      modes: element.querySelector("[data-workflow-modes]").value.split(",").map((item) => item.trim()).filter(Boolean),
      workflow,
      bindings,
    };
  });
}

async function saveService() {
  let settings;
  try { settings = JSON.parse($("service-settings").value || "{}"); } catch { throw new Error("附加设置不是有效 JSON"); }
  if (isComfyProtocol()) {
    state.workflows = collectWorkflows();
    if (!state.workflows.length) throw new Error("至少添加一个 ComfyUI Workflow");
    settings.workflows = state.workflows;
  }
  const id = $("service-id").value;
  const body = {
    name: $("service-name").value.trim(), service_type: $("service-type").value,
    provider: $("service-provider").value.trim(), protocol: $("service-protocol").value,
    base_url: $("service-base-url").value.trim(), models: $("service-models").value.split(",").map((item) => item.trim()).filter(Boolean),
    default_model: $("service-default-model").value.trim(), priority: Number($("service-priority").value || 0),
    endpoint: $("service-endpoint").value.trim(), query_endpoint: $("service-query-endpoint").value.trim(),
    is_active: $("service-active").checked, is_default: $("service-default").checked, settings,
  };
  const key = $("service-api-key").value.trim();
  if (key) body.api_key = key;
  await request(id ? `/api/services/${id}` : "/api/services", { method: id ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

async function removeService(id) {
  const service = state.services.find((item) => item.id === id);
  if (!confirm(`删除“${service?.name || "该服务"}”？`)) return;
  try { await request(`/api/services/${id}`, { method: "DELETE" }); await load(); } catch (error) { toast(error.message, true); }
}

function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
function escapeAttr(value) { return escapeHtml(value); }

$("add-service").addEventListener("click", () => openService());
$("service-protocol").addEventListener("change", renderWorkflowEditor);
$("add-workflow").addEventListener("click", () => {
  state.workflows = collectWorkflows();
  state.workflows.push({ id: `workflow-${state.workflows.length + 1}`, modes: [], workflow: {}, bindings: {} });
  renderWorkflowEditor();
});
$("service-form").addEventListener("submit", async (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  try { await saveService(); $("service-dialog").close(); toast("服务已保存"); await load(); } catch (error) { toast(error.message, true); }
});
$("import-button").addEventListener("click", () => $("import-file").click());
$("import-file").addEventListener("change", async () => {
  const file = $("import-file").files[0]; if (!file) return;
  const form = new FormData(); form.append("file", file);
  try { const result = await request("/api/import/localminidrama", { method: "POST", body: form }); toast(`已导入 ${result.total} 个服务`); await load(); } catch (error) { toast(error.message, true); }
});
$("add-route").addEventListener("click", () => { fillStaticOptions(); $("route-form").reset(); $("route-dialog").showModal(); });
$("route-form").addEventListener("submit", async (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  try {
    await request("/api/routes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ incoming_model: $("route-incoming").value.trim(), capability: $("route-capability").value, service_id: $("route-service").value, upstream_model: $("route-upstream").value.trim() }) });
    $("route-dialog").close(); toast("链路覆盖已保存"); await load();
  } catch (error) { toast(error.message, true); }
});

load();
