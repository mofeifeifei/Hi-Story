import { useEffect, useState } from "react";
import { Check, CheckCircle2, ChevronDown, CircleDollarSign, Eye, EyeOff, KeyRound, LoaderCircle, RefreshCw, Save, Wifi } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { api, createTaskId } from "../services/api";
import { useAppStore } from "../stores/appStore";

const agents = [["planner","策划模型"],["writer","正文写作模型"],["reviewer","审稿模型"],["reviser","修订模型"],["memory","记忆模型"]] as const;
type AvailableModel = { id: string; owned_by?: string };
type BalanceResult = { supported: boolean; available?: boolean; balances?: Array<{ currency?: string; total?: string; granted?: string; topped_up?: string; used?: string }>; checked_at?: string; message?: string };

export function SettingsPage() {
  const store = useAppStore();
  const query = useQuery({ queryKey: ["config"], queryFn: () => api<Record<string, unknown>>("/api/config") });
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [newKey, setNewKey] = useState("");
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [singleModel, setSingleModel] = useState(true);
  const [message, setMessage] = useState("");
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [balanceLoading, setBalanceLoading] = useState(false);
  const [balance, setBalance] = useState<BalanceResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const configTask = store.tasks.some((task) => String(task.kind || "").startsWith("config"));

  useEffect(() => {
    if (!query.data || dirty) return;
    const configured = String(query.data.api_key || "") === "********";
    const models = (query.data.agent_models as Record<string, string>) || {};
    setForm({ ...query.data, api_key: undefined });
    setNewKey(""); setKeyConfigured(configured);
    setSingleModel(agents.every(([key]) => !models[key] || models[key] === query.data?.default_model) && (!query.data.review_model || query.data.review_model === query.data.default_model));
  }, [query.data]);
  useEffect(() => { store.setNavigationGuard(dirty ? () => window.confirm("模型设置有未保存修改。确定离开当前页面吗？") : null); return () => store.setNavigationGuard(null); }, [dirty]);
  function set(key: string, value: unknown) { setForm((current) => ({ ...current, [key]: value })); if (["provider", "model_provider", "base_url", "balance_url"].includes(key)) setBalance(null); setDirty(true); }
  function setAgent(key: string, value: string) { set("agent_models", { ...((form.agent_models as Record<string, string>) || {}), [key]: value }); }
  async function fetchModels() {
    if (configTask) {
      store.notify("模型列表正在获取，请等待当前请求结束。", "warning");
      return;
    }
    const taskId = createTaskId("configModels");
    const controller = new AbortController();
    store.setTask({ id: taskId, kind: "configModels", title: "获取可用模型", detail: "", startedAt: Date.now(), controller });
    setModelsLoading(true);
    setMessage("");
    try {
      const body: Record<string, unknown> = {
        provider: form.provider,
        model_provider: form.model_provider,
        base_url: form.base_url,
        requires_openai_auth: form.requires_openai_auth,
        timeout: form.timeout,
        max_retries: form.max_retries,
        use_system_proxy: form.use_system_proxy,
        proxy_url: form.proxy_url,
        supports_reasoning: form.supports_reasoning,
        supports_response_format: form.supports_response_format,
        task_id: taskId,
      };
      if (newKey.trim()) body.api_key = newKey.trim();
      const result = await api<{ models: AvailableModel[]; count: number }>("/api/config/models", { method: "POST", signal: controller.signal, body });
      setAvailableModels(result.models || []);
      const text = result.count > 0 ? `已获取 ${result.count} 个可用模型，可在模型输入框中搜索选择。` : "接口返回了空模型列表，可继续手动填写模型名称。";
      setMessage(text);
      store.notify(text, result.count > 0 ? "success" : "warning");
    } catch (error) {
      if ((error as Error).name === "AbortError") setMessage("获取可用模型已停止。");
      else { const text = (error as Error).message; setAvailableModels([]); setMessage(text); store.notify(text, "danger"); }
    } finally {
      setModelsLoading(false);
      useAppStore.getState().removeTask(taskId);
    }
  }
  async function fetchBalance() {
    if (balanceLoading || configTask) {
      if (configTask && !balanceLoading) store.notify("设置诊断任务正在运行，请等待完成。", "warning");
      return;
    }
    const taskId = createTaskId("configBalance");
    const controller = new AbortController();
    store.setTask({ id: taskId, kind: "configBalance", title: "查询账户余额", detail: "", startedAt: Date.now(), controller });
    setBalanceLoading(true);
    setMessage("");
    try {
      const body: Record<string, unknown> = {
        provider: form.provider,
        model_provider: form.model_provider,
        base_url: form.base_url,
        balance_url: form.balance_url,
        requires_openai_auth: form.requires_openai_auth,
        timeout: form.timeout,
        use_system_proxy: form.use_system_proxy,
        proxy_url: form.proxy_url,
        task_id: taskId,
      };
      if (newKey.trim()) body.api_key = newKey.trim();
      const result = await api<BalanceResult>("/api/config/balance", { method: "POST", signal: controller.signal, body });
      setBalance(result);
      const text = result.supported ? "账户余额已更新。" : result.message || "当前服务商不支持余额查询。";
      setMessage(text);
      store.notify(text, result.supported ? "success" : "warning");
    } catch (error) {
      if ((error as Error).name === "AbortError") setMessage("余额查询已停止。");
      else { const text = (error as Error).message; setBalance(null); setMessage(text); store.notify(text, "danger"); }
    } finally {
      setBalanceLoading(false);
      useAppStore.getState().removeTask(taskId);
    }
  }
  async function save(test = false) {
    if (configTask) {
      const running = store.tasks.find((task) => String(task.kind || "").startsWith("config"));
      const text = `“${running?.title || "设置诊断任务"}”仍在运行，请等待任务结束或先停止任务。`;
      setMessage(text);
      store.notify(text, "warning");
      return;
    }
    if (saving || testing) return;
    setSaving(true);
    if (test) setTesting(true);
    try {
      const mainModel = String(form.default_model || "").trim();
      const body: Record<string, unknown> = { ...form, review_model: singleModel ? mainModel : form.review_model, agent_models: singleModel ? Object.fromEntries(agents.map(([key]) => [key, mainModel])) : form.agent_models || {} };
      delete body.api_key;
      if (newKey.trim()) body.api_key = newKey.trim();
      const data = await api<Record<string, unknown>>("/api/config", { method: "PUT", body });
      setDirty(false); setForm({ ...data, api_key: undefined }); setKeyConfigured(String(data.api_key || "") === "********"); setNewKey("");
      if (test) {
        const taskId = createTaskId("configTest");
        const controller = new AbortController();
        store.setTask({ id: taskId, kind: "configTest", title: "接口连接测试", detail: "", startedAt: Date.now(), controller });
        try {
          const result = await api<{ message?: string }>("/api/config/test", { method: "POST", signal: controller.signal, body: { task_id: taskId } });
          setMessage(result.message || "连接测试完成。");
        } finally {
          useAppStore.getState().removeTask(taskId);
        }
      }
      else setMessage("设置已保存，下次调用模型时生效。");
      store.notify(test ? "接口连接测试完成。" : "模型设置已保存。", "success");
    } catch (error) {
      if ((error as Error).name === "AbortError") setMessage("接口连接测试已停止。");
      else { setMessage((error as Error).message); store.notify((error as Error).message, "danger"); }
    }
    finally { setSaving(false); if (test) setTesting(false); }
  }
  if (query.isLoading) return <div className="page"><PageHeader title="设置" /><div className="loading-block">正在读取设置...</div></div>;
  if (query.isError) return <div className="page"><PageHeader title="设置" /><EmptyState title="设置读取失败" /></div>;
  const reasoningCapability = form.supports_reasoning;
  const reasoningSupported = reasoningCapability === true || (reasoningCapability == null && ["openai", "tokenflux"].some((name) => `${String(form.provider || "")} ${String(form.model_provider || "")}`.toLowerCase().includes(name)));
  return <div className="page"><PageHeader title="模型与服务设置" description="配置保存在本机，旧密钥不会发送到浏览器。" actions={<><button className="btn" disabled={configTask || saving || testing} title={configTask ? "请等待设置诊断任务结束" : "保存设置并测试模型连接"} onClick={() => save(true)}>{testing ? <LoaderCircle className="spin" size={16} /> : <Wifi size={16} />}{testing ? "正在测试" : "保存并测试"}</button><button className="btn primary" disabled={configTask || saving || testing} onClick={() => save()}><Save size={16} />{saving && !testing ? "正在保存" : "保存设置"}</button></>} />
    <main className="settings-page"><div className="content-width">
      <section className="form-section"><h3 className="section-title">接口</h3><div className="form-grid">
        <Field label="服务商" value={form.provider} onChange={(v) => set("provider", v)} /><Field label="模型接口类型" value={form.model_provider} onChange={(v) => set("model_provider", v)} /><Field label="接口地址" value={form.base_url} onChange={(v) => set("base_url", v)} />
        <SelectField label="接口协议" value={form.wire_api || "chat_completions"} options={[["chat_completions","对话补全接口"],["responses","响应接口"]]} onChange={(v) => set("wire_api", v)} /><ModelField label="主模型" value={form.default_model} models={availableModels} loading={modelsLoading} onChange={(v) => set("default_model", v)} onFetch={fetchModels} />
        <label className="field span-all">API 密钥<span className={`key-state ${keyConfigured ? "configured" : ""}`}><KeyRound size={13} />{keyConfigured ? "已配置，留空将保留原密钥" : "尚未配置"}</span><div className="input-with-action"><input type={showKey ? "text" : "password"} value={newKey} placeholder={keyConfigured ? "输入新密钥才会替换原密钥" : "输入 API 密钥"} autoComplete="new-password" onChange={(event) => { setNewKey(event.target.value); setDirty(true); setBalance(null); }} /><button className="icon-button" type="button" title={showKey ? "隐藏新密钥" : "显示新密钥"} onClick={() => setShowKey(!showKey)}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
      </div><div className="balance-actions"><button className="btn" type="button" disabled={balanceLoading} onClick={fetchBalance}>{balanceLoading ? <LoaderCircle className="spin" size={16} /> : <CircleDollarSign size={16} />}{balanceLoading ? "正在查询" : "查询余额"}</button>{balance?.supported && <div className="balance-result">{(balance.balances || []).map((item, index) => <span key={`${item.currency || "currency"}-${index}`}><strong>{formatBalance(item.total, item.currency)}</strong><small>{balance.available === false ? "当前不可用" : "可用余额"}</small></span>)}{balance.checked_at && <time>{balance.checked_at}</time>}</div>}{balance && !balance.supported && <p className="balance-unsupported">{balance.message}</p>}</div><div className="settings-toggles"><label className="check-field"><input type="checkbox" checked={Boolean(form.mock_mode)} onChange={(e) => set("mock_mode", e.target.checked)} />使用本地模拟模式</label><label className="check-field"><input type="checkbox" checked={singleModel} onChange={(e) => { setSingleModel(e.target.checked); setDirty(true); }} />所有智能体跟随主模型</label></div>{singleModel && <p className="effective-model">当前策划、写作、审稿、修订和记忆实际使用：<strong>{String(form.default_model || "未设置")}</strong></p>}</section>
      <section className="form-section"><h3 className="section-title">生成参数</h3><div className="form-grid three">
        <Field label="请求超时（秒）" type="number" value={form.timeout} onChange={(v) => set("timeout", Number(v))} /><Field label="最大重试次数" type="number" value={form.max_retries} onChange={(v) => set("max_retries", Number(v))} /><Field label="普通任务输出上限" type="number" value={form.max_output_tokens} onChange={(v) => set("max_output_tokens", Number(v))} /><Field label="正文与修订输出上限" type="number" value={form.long_text_max_output_tokens} onChange={(v) => set("long_text_max_output_tokens", Number(v))} />
        <SelectField label={reasoningSupported ? "推理强度" : "推理强度（当前接口不发送）"} value={reasoningSupported ? form.model_reasoning_effort || "" : ""} disabled={!reasoningSupported} options={[["","自动，由模型决定"],["low","低"],["medium","中"],["high","高"],["xhigh","极高"]]} onChange={(v) => set("model_reasoning_effort", v)} /><SelectField label="接口推理参数" value={form.supports_reasoning == null ? "auto" : form.supports_reasoning ? "yes" : "no"} options={[["auto","自动判断"],["yes","明确支持"],["no","明确不支持"]]} onChange={(v) => set("supports_reasoning", v === "auto" ? null : v === "yes")} /><Field label="上下文窗口" type="number" value={form.model_context_window} onChange={(v) => set("model_context_window", Number(v))} /><Field label="自动压缩阈值" type="number" value={form.model_auto_compact_token_limit} onChange={(v) => set("model_auto_compact_token_limit", Number(v))} />
      </div></section>
      <details className="settings-advanced"><summary>高级模型与网络设置</summary><div className="form-section"><div className="form-grid three">
        <ModelField label="独立审稿模型" value={singleModel ? form.default_model : form.review_model} models={availableModels} disabled={singleModel} onChange={(v) => set("review_model", v)} />{agents.map(([key,label]) => <ModelField key={key} label={label} value={singleModel ? form.default_model : (form.agent_models as Record<string,string>)?.[key]} models={availableModels} disabled={singleModel} onChange={(v) => setAgent(key, v)} />)}<Field label="温度" type="number" value={form.temperature} onChange={(v) => set("temperature", Number(v))} /><Field label="手动代理地址" value={form.proxy_url} onChange={(v) => set("proxy_url", v)} /><SelectField label="接口 JSON 输出" value={form.supports_response_format == null ? "auto" : form.supports_response_format ? "yes" : "no"} options={[["auto","自动判断"],["yes","明确支持"],["no","明确不支持"]]} onChange={(v) => set("supports_response_format", v === "auto" ? null : v === "yes")} /><Field label="余额查询地址（同域，可选）" value={form.balance_url} onChange={(v) => { set("balance_url", v); setBalance(null); }} />
      </div><div className="settings-toggles"><label className="check-field"><input type="checkbox" checked={Boolean(form.disable_response_storage)} onChange={(e) => set("disable_response_storage", e.target.checked)} />关闭服务端响应存储</label><label className="check-field"><input type="checkbox" checked={Boolean(form.use_system_proxy)} onChange={(e) => set("use_system_proxy", e.target.checked)} />使用系统代理</label></div></div></details>
      {message && <p className="settings-message"><CheckCircle2 size={16} />{message}</p>}
    </div></main>
  </div>;
}

function Field({ label, value, onChange, type = "text", disabled = false }: { label: string; value: unknown; onChange: (value: string) => void; type?: string; disabled?: boolean }) { return <label className="field">{label}<input type={type} value={String(value ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value)} /></label>; }
function SelectField({ label, value, options, onChange, disabled = false }: { label: string; value: unknown; options: Array<[string,string]>; onChange: (value: string) => void; disabled?: boolean }) { return <label className="field">{label}<select value={String(value ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value)}>{options.map(([key,text]) => <option key={key} value={key}>{text}</option>)}</select></label>; }
function formatBalance(value?: string, currency?: string) { const amount = Number(value); const code = String(currency || "").toUpperCase(); if (!Number.isFinite(amount)) return `${value || "--"}${code ? ` ${code}` : ""}`; if (["CNY", "USD", "EUR", "JPY", "GBP"].includes(code)) return new Intl.NumberFormat("zh-CN", { style: "currency", currency: code, minimumFractionDigits: 2 }).format(amount); return `${amount.toFixed(2)}${code ? ` ${code}` : ""}`; }
function ModelField({ label, value, models, loading = false, disabled = false, onChange, onFetch }: { label: string; value: unknown; models: AvailableModel[]; loading?: boolean; disabled?: boolean; onChange: (value: string) => void; onFetch?: () => Promise<void> | void }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selected = String(value ?? "");
  const normalizedSearch = search.trim().toLowerCase();
  const filtered = normalizedSearch ? models.filter((model) => `${model.id} ${model.owned_by || ""}`.toLowerCase().includes(normalizedSearch)) : models;
  function choose(model: AvailableModel) { onChange(model.id); setSearch(""); setOpen(false); }
  async function fetchAndOpen() { if (!onFetch) return; await onFetch(); setSearch(""); setOpen(true); }
  return <div className={`field model-field ${disabled ? "disabled" : ""}`}><span>{label}</span><div className="model-picker" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false); }}><div className="model-combobox"><input value={selected} disabled={disabled} placeholder="可手动填写或获取后选择" aria-expanded={open} aria-haspopup="listbox" onFocus={() => { setSearch(""); setOpen(true); }} onChange={(event) => { onChange(event.target.value); setSearch(event.target.value); setOpen(true); }} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }} /><button className="model-toggle" type="button" disabled={disabled} title="展开全部可用模型" aria-label="展开全部可用模型" onClick={() => { setSearch(""); setOpen((current) => !current); }}><ChevronDown size={16} /></button>{open && !disabled && <div className="model-options" role="listbox">{filtered.length ? filtered.map((model) => <button className={`model-option ${model.id === selected ? "selected" : ""}`} type="button" role="option" aria-selected={model.id === selected} key={model.id} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(model)}><span><strong>{model.id}</strong><small>{model.owned_by || "模型服务商未标注"}</small></span>{model.id === selected && <Check size={15} />}</button>) : <p>{models.length ? "没有匹配的模型" : "请先获取可用模型，也可以直接输入模型名称"}</p>}</div>}</div>{onFetch && <button className="btn model-fetch-button" type="button" disabled={loading} onClick={fetchAndOpen}>{loading ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}{loading ? "正在获取" : "获取可用模型"}</button>}</div></div>;
}
