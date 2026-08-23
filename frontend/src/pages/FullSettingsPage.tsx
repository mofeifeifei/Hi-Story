import { useEffect, useState } from "react";
import { CheckCircle2, CircleDollarSign, Copy, Eye, EyeOff, KeyRound, LoaderCircle, Plus, RefreshCw, Save, Trash2, Wifi } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { api, createTaskId } from "../services/api";
import { useAppStore } from "../stores/appStore";

const agents = [["planner", "策划模型"], ["writer", "正文写作模型"], ["reviewer", "审稿模型"], ["reviser", "修订模型"], ["memory", "记忆模型"], ["title", "标题研判模型"]] as const;
const agentKeys = agents.map(([key]) => key);
const protocolOptions = [["openai_compatible", "OpenAI / 兼容 OpenAI 协议"], ["anthropic", "Claude / Anthropic Messages API"]] as const;
const API_KEY_MASK = "********";
type Channel = Record<string, unknown> & { name?: string; protocol?: string; api_key?: string; api_key_configured?: boolean; default_model?: string; agent_models?: Record<string, string> };
type ConfigData = Record<string, unknown> & { ai?: { default_channel?: string; channels?: Record<string, Channel> } };
type AvailableModel = { id: string; owned_by?: string };
type BalanceResult = { supported: boolean; available?: boolean; balances?: Array<{ currency?: string; total?: string; granted?: string; topped_up?: string; used?: string }>; checked_at?: string; message?: string };

function blankChannel(id = "new-channel"): Channel {
  return { name: id, protocol: "openai_compatible", base_url: "", api_key: "", api_key_configured: false, default_model: "", agent_models: Object.fromEntries(agentKeys.map((key) => [key, ""])), provider: "OpenAI", model_provider: "OpenAI", wire_api: "chat_completions", requires_openai_auth: true, mock_mode: false, timeout: 300, max_retries: 2, max_output_tokens: 12000, long_text_max_output_tokens: 12000, temperature: 0.8, model_reasoning_effort: "", supports_reasoning: null, supports_response_format: null, disable_response_storage: true, model_context_window: 1000000, model_auto_compact_token_limit: 900000, balance_url: "", use_system_proxy: false, proxy_url: "" };
}
function channelIdFromName(name: string, existing: Record<string, Channel>): string { const base = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "new-channel"; if (!existing[base]) return base; let index = 2; while (existing[`${base}-${index}`]) index += 1; return `${base}-${index}`; }
function cloneChannel(channel: Channel): Channel { return { ...channel, agent_models: { ...(channel.agent_models || {}) } }; }

export function SettingsPage() {
  const store = useAppStore();
  const query = useQuery({ queryKey: ["config"], queryFn: () => api<ConfigData>("/api/config") });
  const [channels, setChannels] = useState<Record<string, Channel>>({});
  const [activeChannelId, setActiveChannelId] = useState("");
  const [defaultChannel, setDefaultChannel] = useState("");
  const [draft, setDraft] = useState<Channel>(blankChannel());
  const [apiKeyDraft, setApiKeyDraft] = useState("");
  const [apiKeyChanged, setApiKeyChanged] = useState(false);
  const [revealedKey, setRevealedKey] = useState("");
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

  function loadChannel(id: string, source = channels) {
    const next = source[id] ? cloneChannel(source[id]) : blankChannel(id);
    setActiveChannelId(id); setDraft(next); setApiKeyDraft(""); setApiKeyChanged(false); setRevealedKey(""); setShowKey(false); setAvailableModels([]); setBalance(null);
    const models = next.agent_models || {}; const main = String(next.default_model || "");
    setSingleModel(agentKeys.every((key) => !models[key] || models[key] === main));
  }
  useEffect(() => {
    if (!query.data || dirty) return;
    const ai = query.data.ai || {}; const incoming = ai.channels || {}; const ids = Object.keys(incoming);
    const nextChannels = ids.length ? Object.fromEntries(ids.map((id) => [id, cloneChannel(incoming[id])])) : { legacy: blankChannel("legacy") };
    const selected = String(ai.default_channel || ids[0] || "legacy");
    setChannels(nextChannels); setDefaultChannel(selected); loadChannel(selected, nextChannels);
  }, [query.data]);
  useEffect(() => { store.setNavigationGuard(dirty ? () => window.confirm("模型通道有未保存修改。确定离开当前页面吗？") : null); return () => store.setNavigationGuard(null); }, [dirty]);

  const configured = Boolean(draft.api_key_configured || (String(draft.api_key || "") && String(draft.api_key || "") !== API_KEY_MASK));
  const keyValue = apiKeyChanged ? apiKeyDraft : showKey ? revealedKey : configured ? API_KEY_MASK : "";
  const protocol = String(draft.protocol || "openai_compatible");
  const reasoningSupported = draft.supports_reasoning === true || (draft.supports_reasoning == null && protocol === "openai_compatible");
  const activeName = String(draft.name || activeChannelId || "未命名通道");
  const activeModel = String(draft.default_model || "未设置");
  function setField(key: string, value: unknown) { setDraft((current) => ({ ...current, [key]: value })); if (["protocol", "base_url", "balance_url", "api_key", "model_provider", "provider"].includes(key)) setBalance(null); setDirty(true); }
  function setAgentModel(key: string, value: string) { setDraft((current) => ({ ...current, agent_models: { ...(current.agent_models || {}), [key]: value } })); setDirty(true); }
  function prepareChannel(channel: Channel) { const safe = { ...channel, agent_models: { ...(channel.agent_models || {}) } }; delete safe.api_key_configured; return safe; }
  function channelPayload() { const active = cloneChannel(draft); if (singleModel) { const main = String(active.default_model || "").trim(); active.agent_models = Object.fromEntries(agentKeys.map((key) => [key, main])); } active.api_key = apiKeyChanged ? apiKeyDraft : configured ? API_KEY_MASK : ""; return prepareChannel(active); }
  function buildAiPayload() { return { default_channel: defaultChannel || activeChannelId, channels: { ...Object.fromEntries(Object.entries(channels).map(([id, channel]) => [id, prepareChannel(channel)])), [activeChannelId]: channelPayload() } }; }
  function currentRequestBody(taskId?: string) { return { channel_id: activeChannelId, channel: channelPayload(), ...(taskId ? { task_id: taskId } : {}) }; }

  async function revealKey() {
    if (showKey) { setShowKey(false); return; }
    if (apiKeyChanged) { setShowKey(true); return; }
    if (!configured) { store.notify("当前通道尚未配置 API 密钥。", "warning"); return; }
    try { const result = await api<{ api_key: string }>("/api/config/secret/reveal", { method: "POST", body: { channel_id: activeChannelId } }); setRevealedKey(result.api_key || ""); setShowKey(true); } catch (error) { store.notify((error as Error).message, "danger"); }
  }
  function selectChannel(id: string) { if (id === activeChannelId) return; if (dirty && !window.confirm("当前通道有未保存修改。切换后将放弃这些修改，是否继续？")) return; setDirty(false); loadChannel(id); }
  function addChannel() { if (dirty && !window.confirm("当前通道有未保存修改。新增通道前放弃这些修改吗？")) return; const id = channelIdFromName("新建通道", channels); const next = { ...channels, [id]: blankChannel("新建通道") }; setChannels(next); setDefaultChannel(defaultChannel || id); setDirty(true); loadChannel(id, next); }
  function copyChannel() { const id = channelIdFromName(`${activeName} 副本`, channels); const next = { ...channels, [id]: { ...cloneChannel(draft), name: `${activeName} 副本` } }; setChannels(next); setDirty(true); loadChannel(id, next); setMessage("已创建通道副本，请检查密钥和模型后保存。"); }
  function deleteChannel() { const ids = Object.keys(channels); if (ids.length <= 1) { store.notify("至少需要保留一个 AI 通道。", "warning"); return; } if (!window.confirm(`确定删除“${activeName}”吗？删除将在保存设置后生效。`)) return; const next = { ...channels }; delete next[activeChannelId]; const nextId = Object.keys(next)[0]; setChannels(next); if (defaultChannel === activeChannelId) setDefaultChannel(nextId); setDirty(true); loadChannel(nextId, next); }

  async function fetchModels() {
    if (configTask) { store.notify("设置任务正在运行，请等待当前请求结束。", "warning"); return; }
    const taskId = createTaskId("configModels"); const controller = new AbortController(); store.setTask({ id: taskId, kind: "configModels", title: "获取可用模型", detail: activeName, startedAt: Date.now(), controller }); setModelsLoading(true);
    try { const result = await api<{ models: AvailableModel[]; count: number }>("/api/config/models", { method: "POST", signal: controller.signal, body: currentRequestBody(taskId) }); setAvailableModels(result.models || []); const text = result.count ? `已获取 ${result.count} 个模型，请直接从模型下拉框选择。` : "当前通道未返回模型列表，可以手动填写模型名称。"; setMessage(text); store.notify(text, result.count ? "success" : "warning"); } catch (error) { if ((error as Error).name === "AbortError") setMessage("获取模型列表已停止。"); else { setAvailableModels([]); setMessage((error as Error).message); store.notify((error as Error).message, "danger"); } } finally { setModelsLoading(false); useAppStore.getState().removeTask(taskId); }
  }
  async function fetchBalance() {
    if (balanceLoading || configTask) { if (configTask) store.notify("设置任务正在运行，请等待当前请求结束。", "warning"); return; }
    const taskId = createTaskId("configBalance"); const controller = new AbortController(); store.setTask({ id: taskId, kind: "configBalance", title: "查询账户余额", detail: activeName, startedAt: Date.now(), controller }); setBalanceLoading(true);
    try { const result = await api<BalanceResult>("/api/config/balance", { method: "POST", signal: controller.signal, body: currentRequestBody(taskId) }); setBalance(result); setMessage(result.supported ? "账户余额已更新。" : result.message || "当前通道不支持余额查询。"); } catch (error) { if ((error as Error).name === "AbortError") setMessage("余额查询已停止。"); else { setBalance(null); setMessage((error as Error).message); store.notify((error as Error).message, "danger"); } } finally { setBalanceLoading(false); useAppStore.getState().removeTask(taskId); }
  }
  async function save(test = false) {
    if (!activeChannelId || saving || testing || configTask) return; setSaving(true); if (test) setTesting(true);
    try { const data = await api<ConfigData>("/api/config", { method: "PUT", body: { ai: buildAiPayload() } }); const nextAi = data.ai || {}; const nextChannels = nextAi.channels || {}; setChannels(nextChannels); setDefaultChannel(String(nextAi.default_channel || activeChannelId)); setDirty(false); loadChannel(activeChannelId, nextChannels); setMessage(test ? "设置已保存，正在测试当前通道。" : "设置已保存，后续任务将使用当前通道。");
      if (test) { const taskId = createTaskId("configTest"); const controller = new AbortController(); store.setTask({ id: taskId, kind: "configTest", title: "接口连接测试", detail: activeName, startedAt: Date.now(), controller }); try { const result = await api<{ message?: string }>("/api/config/test", { method: "POST", signal: controller.signal, body: { channel_id: activeChannelId, task_id: taskId } }); setMessage(result.message || "当前通道连接成功。"); } finally { useAppStore.getState().removeTask(taskId); } }
      store.notify(test ? "当前通道连接测试完成。" : "AI 通道设置已保存。", "success");
    } catch (error) { setMessage((error as Error).message); store.notify((error as Error).message, "danger"); } finally { setSaving(false); setTesting(false); }
  }

  if (query.isLoading) return <div className="page"><PageHeader title="设置" /><div className="loading-block">正在读取设置...</div></div>;
  if (query.isError) return <div className="page"><PageHeader title="设置" /><EmptyState title="设置读取失败" /></div>;
  return <div className="page"><PageHeader title="模型与服务设置" description="当前通道决定接口、密钥和协议；高级设置只调整当前通道内的模型。" actions={<><button className="btn" type="button" disabled={configTask || saving || testing} onClick={() => save(true)}>{testing ? <LoaderCircle className="spin" size={16} /> : <Wifi size={16} />}{testing ? "正在测试" : "保存并测试"}</button><button className="btn primary" type="button" disabled={configTask || saving || testing} onClick={() => save()}><Save size={16} />{saving && !testing ? "正在保存" : "保存设置"}</button></>} />
    <main className="settings-page"><div className="content-width">
      <section className="channel-toolbar"><div className="channel-select-wrap"><span>当前通道</span><select value={activeChannelId} onChange={(event) => selectChannel(event.target.value)} aria-label="当前 AI 通道">{Object.entries(channels).map(([id, channel]) => <option key={id} value={id}>{String(channel.name || id)} · {String(channel.default_model || "未设置")}</option>)}</select></div><div className="channel-actions"><button className="btn" type="button" onClick={addChannel}><Plus size={15} />新增</button><button className="btn" type="button" onClick={copyChannel} disabled={!activeChannelId}><Copy size={15} />复制</button><button className={`btn ${defaultChannel === activeChannelId ? "is-active" : ""}`} type="button" onClick={() => { setDefaultChannel(activeChannelId); setDirty(true); }} disabled={defaultChannel === activeChannelId}>设为默认</button><button className="btn danger-outline" type="button" onClick={deleteChannel} disabled={Object.keys(channels).length <= 1}><Trash2 size={15} />删除</button></div></section>
      <section className="channel-summary"><div><strong>编辑当前选择的通道</strong><span>切换下拉框后，下面的地址、密钥、协议和模型会整体切换。</span></div><div className="channel-tags"><span className="channel-tag accent">{defaultChannel === activeChannelId ? "默认通道" : "自定义通道"}</span><span className="channel-tag">{protocol === "anthropic" ? "Anthropic" : "OpenAI 兼容"}</span><span className="channel-tag">{activeModel}</span><span className="channel-tag">{configured ? "密钥已配置" : "未配置密钥"}</span></div></section>
      <section className="form-section"><div className="section-heading"><div><h3 className="section-title">连接信息</h3><p>先确认服务商、地址、密钥和模型，再测试当前通道。</p></div><button className="btn" type="button" disabled={configTask || saving || testing} onClick={() => save(true)}><Wifi size={15} />测试连接</button></div><div className="form-grid">
        <Field label="通道名称" value={draft.name} onChange={(v) => setField("name", v)} /><SelectField label="API 提供商" value={protocol} options={protocolOptions as unknown as Array<[string, string]>} onChange={(v) => setField("protocol", v)} /><Field label="Base URL" value={draft.base_url} onChange={(v) => setField("base_url", v)} full />
        <label className="field span-all"><span className="field-label-line">API Key <span className={`key-state ${configured ? "configured" : ""}`}><KeyRound size={13} />{configured ? "已配置，留空或掩码将保留原密钥" : "尚未配置"}</span></span><div className="input-with-action"><input type={showKey ? "text" : "password"} value={keyValue} placeholder={configured ? "点击眼睛查看，输入新密钥可替换" : "输入 API Key"} autoComplete="new-password" onChange={(event) => { setApiKeyDraft(event.target.value); setApiKeyChanged(true); setShowKey(true); setField("api_key", event.target.value); }} /><button className="icon-button" type="button" title={showKey ? "隐藏 API Key" : "查看 API Key"} onClick={revealKey}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
        <ModelInput label="模型" value={draft.default_model} models={availableModels} onChange={(v) => setField("default_model", v)} onFetch={fetchModels} loading={modelsLoading} />
      </div><div className="available-models-note">{availableModels.length ? `已获取 ${availableModels.length} 个模型，主模型和高级设置中的模型都可以直接从下拉框选择。` : "点击“获取列表”后，可从当前通道返回的模型中选择；接口暂不支持时可手动填写。"}</div><div className="balance-actions"><button className="btn" type="button" disabled={balanceLoading || configTask} onClick={fetchBalance}>{balanceLoading ? <LoaderCircle className="spin" size={16} /> : <CircleDollarSign size={16} />}{balanceLoading ? "正在查询" : "查询余额"}</button>{balance?.supported && <div className="balance-result">{(balance.balances || []).map((item, index) => <span key={`${item.currency || "currency"}-${index}`}><strong>{formatBalance(item.total, item.currency)}</strong><small>{balance.available === false ? "当前不可用" : "可用余额"}</small></span>)}{balance.checked_at && <time>{balance.checked_at}</time>}</div>}{balance && !balance.supported && <p className="balance-unsupported">{balance.message}</p>}</div></section>
      <section className="form-section"><div className="section-heading"><div><h3 className="section-title">生成参数</h3><p>这些参数属于当前通道，切换通道后会同步切换。</p></div></div><div className="form-grid three"><Field label="请求超时（秒）" type="number" value={draft.timeout} onChange={(v) => setField("timeout", Number(v))} /><Field label="最大重试次数" type="number" value={draft.max_retries} onChange={(v) => setField("max_retries", Number(v))} /><Field label="普通任务输出上限" type="number" value={draft.max_output_tokens} onChange={(v) => setField("max_output_tokens", Number(v))} /><Field label="正文与修订输出上限" type="number" value={draft.long_text_max_output_tokens} onChange={(v) => setField("long_text_max_output_tokens", Number(v))} /><SelectField label={reasoningSupported ? "推理强度" : "推理强度（当前接口不发送）"} value={reasoningSupported ? draft.model_reasoning_effort || "" : ""} disabled={!reasoningSupported} options={[["", "自动，由模型决定"], ["low", "低"], ["medium", "中"], ["high", "高"], ["xhigh", "极高"]]} onChange={(v) => setField("model_reasoning_effort", v)} /><SelectField label="接口推理参数" value={draft.supports_reasoning == null ? "auto" : draft.supports_reasoning ? "yes" : "no"} options={[["auto", "自动判断"], ["yes", "明确支持"], ["no", "明确不支持"]]} onChange={(v) => setField("supports_reasoning", v === "auto" ? null : v === "yes")} /><Field label="上下文窗口" type="number" value={draft.model_context_window} onChange={(v) => setField("model_context_window", Number(v))} /><Field label="自动压缩阈值" type="number" value={draft.model_auto_compact_token_limit} onChange={(v) => setField("model_auto_compact_token_limit", Number(v))} /></div><label className="check-field"><input type="checkbox" checked={Boolean(draft.mock_mode)} onChange={(event) => setField("mock_mode", event.target.checked)} />使用本地模拟模式</label></section>
      <details className="settings-advanced"><summary>高级模型与网络设置</summary><div className="form-section"><p className="advanced-rule">当前通道固定提供商、API 地址、密钥和协议；这里仅允许为不同环节选择当前通道可用的模型。</p><div className="form-grid three"><label className="check-field"><input type="checkbox" checked={singleModel} onChange={(event) => { setSingleModel(event.target.checked); setDirty(true); }} />所有智能体跟随主模型</label>{agents.map(([key, label]) => <ModelInput key={key} label={label} value={singleModel ? draft.default_model : draft.agent_models?.[key]} models={availableModels} disabled={singleModel} onChange={(v) => setAgentModel(key, v)} />)}<Field label="温度" type="number" value={draft.temperature} onChange={(v) => setField("temperature", Number(v))} /><Field label="手动代理地址" value={draft.proxy_url} onChange={(v) => setField("proxy_url", v)} /><SelectField label="接口 JSON 输出" value={draft.supports_response_format == null ? "auto" : draft.supports_response_format ? "yes" : "no"} options={[["auto", "自动判断"], ["yes", "明确支持"], ["no", "明确不支持"]]} onChange={(v) => setField("supports_response_format", v === "auto" ? null : v === "yes")} /><Field label="余额查询地址（同域，可选）" value={draft.balance_url} onChange={(v) => { setField("balance_url", v); setBalance(null); }} /></div><div className="settings-toggles"><label className="check-field"><input type="checkbox" checked={Boolean(draft.disable_response_storage)} onChange={(event) => setField("disable_response_storage", event.target.checked)} />关闭服务端响应存储</label><label className="check-field"><input type="checkbox" checked={Boolean(draft.use_system_proxy)} onChange={(event) => setField("use_system_proxy", event.target.checked)} />使用系统代理</label></div></div></details>
      {message && <p className="settings-message"><CheckCircle2 size={16} />{message}</p>}
    </div></main>
  </div>;
}

function Field({ label, value, onChange, type = "text", disabled = false, full = false }: { label: string; value: unknown; onChange: (value: string) => void; type?: string; disabled?: boolean; full?: boolean }) { return <label className={`field ${full ? "span-all" : ""}`}><span>{label}</span><input type={type} value={String(value ?? "")} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>; }
function SelectField({ label, value, options, onChange, disabled = false }: { label: string; value: unknown; options: Array<[string, string]>; onChange: (value: string) => void; disabled?: boolean }) { return <label className="field"><span>{label}</span><select value={String(value ?? "")} disabled={disabled} onChange={(event) => onChange(event.target.value)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>; }
function ModelInput({ label, value, models, onChange, onFetch, loading = false, disabled = false }: { label: string; value: unknown; models: AvailableModel[]; onChange: (value: string) => void; onFetch?: () => void; loading?: boolean; disabled?: boolean }) {
  const selected = String(value ?? "");
  const knownModels = models.filter((model, index, all) => model.id && all.findIndex((item) => item.id === model.id) === index);
  const selectedIsListed = knownModels.some((model) => model.id === selected);
  return <label className={`field model-input-field ${disabled ? "disabled" : ""}`}><span>{label}</span><div className="model-input-row">{knownModels.length ? <select value={selected} disabled={disabled} onChange={(event) => onChange(event.target.value)}><option value="">请选择模型</option>{selected && !selectedIsListed && <option value={selected}>当前模型：{selected}</option>}{knownModels.map((model) => <option key={model.id} value={model.id}>{model.id}{model.owned_by ? ` · ${model.owned_by}` : ""}</option>)}</select> : <input value={selected} disabled={disabled} placeholder="手动填写模型名称" onChange={(event) => onChange(event.target.value)} />}{onFetch && <button type="button" className="text-action" disabled={loading || disabled} onClick={onFetch}>{loading ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}{loading ? "获取中" : "获取列表"}</button>}</div></label>;
}
function formatBalance(value?: string, currency?: string) { const amount = Number(value); const code = String(currency || "").toUpperCase(); if (!Number.isFinite(amount)) return `${value || "--"}${code ? ` ${code}` : ""}`; if (["CNY", "USD", "EUR", "JPY", "GBP"].includes(code)) return new Intl.NumberFormat("zh-CN", { style: "currency", currency: code, minimumFractionDigits: 2 }).format(amount); return `${amount.toFixed(2)}${code ? ` ${code}` : ""}`; }
