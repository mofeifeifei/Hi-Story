import { useEffect, useState } from "react";
import { CheckCircle2, Eye, EyeOff, KeyRound, LoaderCircle, RefreshCw, Save, Wifi } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/api";
import { useAppStore } from "../stores/appStore";

const agents = [["planner","策划模型"],["writer","正文写作模型"],["reviewer","审稿模型"],["reviser","修订模型"],["memory","记忆模型"]] as const;
type AvailableModel = { id: string; owned_by?: string };

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

  useEffect(() => {
    if (!query.data) return;
    const configured = String(query.data.api_key || "") === "********";
    const models = (query.data.agent_models as Record<string, string>) || {};
    setForm({ ...query.data, api_key: undefined });
    setNewKey(""); setKeyConfigured(configured);
    setSingleModel(agents.every(([key]) => !models[key] || models[key] === query.data?.default_model));
  }, [query.data]);
  function set(key: string, value: unknown) { setForm((current) => ({ ...current, [key]: value })); }
  function setAgent(key: string, value: string) { set("agent_models", { ...((form.agent_models as Record<string, string>) || {}), [key]: value }); }
  async function fetchModels() {
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
      };
      if (newKey.trim()) body.api_key = newKey.trim();
      const result = await api<{ models: AvailableModel[]; count: number }>("/api/config/models", { method: "POST", body });
      setAvailableModels(result.models || []);
      const text = result.count > 0 ? `已获取 ${result.count} 个可用模型，可在模型输入框中搜索选择。` : "接口返回了空模型列表，可继续手动填写模型名称。";
      setMessage(text);
      store.notify(text, result.count > 0 ? "success" : "warning");
    } catch (error) {
      const text = (error as Error).message;
      setAvailableModels([]);
      setMessage(text);
      store.notify(text, "danger");
    } finally {
      setModelsLoading(false);
    }
  }
  async function save(test = false) {
    try {
      const mainModel = String(form.default_model || "").trim();
      const body: Record<string, unknown> = { ...form, review_model: singleModel ? mainModel : form.review_model, agent_models: singleModel ? Object.fromEntries(agents.map(([key]) => [key, mainModel])) : form.agent_models || {} };
      delete body.api_key;
      if (newKey.trim()) body.api_key = newKey.trim();
      const data = await api<Record<string, unknown>>("/api/config", { method: "PUT", body });
      setForm({ ...data, api_key: undefined }); setKeyConfigured(String(data.api_key || "") === "********"); setNewKey("");
      if (test) { const result = await api<{ message?: string }>("/api/config/test", { method: "POST" }); setMessage(result.message || "连接测试完成。"); }
      else setMessage("设置已保存，下次调用模型时生效。");
      store.notify(test ? "接口连接测试完成。" : "模型设置已保存。", "success");
    } catch (error) { setMessage((error as Error).message); store.notify((error as Error).message, "danger"); }
  }
  if (query.isLoading) return <div className="page"><PageHeader title="设置" /><div className="loading-block">正在读取设置...</div></div>;
  if (query.isError) return <div className="page"><PageHeader title="设置" /><EmptyState title="设置读取失败" /></div>;
  return <div className="page"><PageHeader title="模型与服务设置" description="配置保存在本机，旧密钥不会发送到浏览器。" actions={<><button className="btn" onClick={() => save(true)}><Wifi size={16} />保存并测试</button><button className="btn primary" onClick={() => save()}><Save size={16} />保存设置</button></>} />
    <main className="settings-page"><div className="content-width">
      <section className="form-section"><h3 className="section-title">接口</h3><div className="form-grid">
        <Field label="服务商" value={form.provider} onChange={(v) => set("provider", v)} /><Field label="接口地址" value={form.base_url} onChange={(v) => set("base_url", v)} />
        <SelectField label="接口协议" value={form.wire_api || "chat_completions"} options={[["chat_completions","对话补全接口"],["responses","响应接口"]]} onChange={(v) => set("wire_api", v)} /><ModelField label="主模型" value={form.default_model} models={availableModels} loading={modelsLoading} onChange={(v) => set("default_model", v)} onFetch={fetchModels} />
        <label className="field span-all">API 密钥<span className={`key-state ${keyConfigured ? "configured" : ""}`}><KeyRound size={13} />{keyConfigured ? "已配置，留空将保留原密钥" : "尚未配置"}</span><div className="input-with-action"><input type={showKey ? "text" : "password"} value={newKey} placeholder={keyConfigured ? "输入新密钥才会替换原密钥" : "输入 API 密钥"} autoComplete="new-password" onChange={(event) => setNewKey(event.target.value)} /><button className="icon-button" type="button" title={showKey ? "隐藏新密钥" : "显示新密钥"} onClick={() => setShowKey(!showKey)}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
      </div><div className="settings-toggles"><label className="check-field"><input type="checkbox" checked={Boolean(form.mock_mode)} onChange={(e) => set("mock_mode", e.target.checked)} />使用本地模拟模式</label><label className="check-field"><input type="checkbox" checked={singleModel} onChange={(e) => setSingleModel(e.target.checked)} />所有智能体使用主模型</label></div></section>
      <section className="form-section"><h3 className="section-title">生成参数</h3><div className="form-grid three">
        <Field label="请求超时（秒）" type="number" value={form.timeout} onChange={(v) => set("timeout", Number(v))} /><Field label="最大重试次数" type="number" value={form.max_retries} onChange={(v) => set("max_retries", Number(v))} /><Field label="最大输出令牌" type="number" value={form.max_output_tokens} onChange={(v) => set("max_output_tokens", Number(v))} />
        <SelectField label="推理强度" value={form.model_reasoning_effort || ""} options={[["","自动，由模型决定"],["low","低"],["medium","中"],["high","高"],["xhigh","极高"]]} onChange={(v) => set("model_reasoning_effort", v)} /><Field label="上下文窗口" type="number" value={form.model_context_window} onChange={(v) => set("model_context_window", Number(v))} /><Field label="自动压缩阈值" type="number" value={form.model_auto_compact_token_limit} onChange={(v) => set("model_auto_compact_token_limit", Number(v))} />
      </div></section>
      <details className="settings-advanced"><summary>高级模型与网络设置</summary><div className="form-section"><div className="form-grid three">
        <Field label="独立审稿模型" value={form.review_model} list="available-models" disabled={singleModel} onChange={(v) => set("review_model", v)} />{agents.map(([key,label]) => <Field key={key} label={label} value={(form.agent_models as Record<string,string>)?.[key]} list="available-models" disabled={singleModel} onChange={(v) => setAgent(key, v)} />)}<Field label="温度" type="number" value={form.temperature} onChange={(v) => set("temperature", Number(v))} /><Field label="手动代理地址" value={form.proxy_url} onChange={(v) => set("proxy_url", v)} />
      </div><div className="settings-toggles"><label className="check-field"><input type="checkbox" checked={Boolean(form.disable_response_storage)} onChange={(e) => set("disable_response_storage", e.target.checked)} />关闭服务端响应存储</label><label className="check-field"><input type="checkbox" checked={Boolean(form.use_system_proxy)} onChange={(e) => set("use_system_proxy", e.target.checked)} />使用系统代理</label></div></div></details>
      {message && <p className="settings-message"><CheckCircle2 size={16} />{message}</p>}
    </div></main>
  </div>;
}

function Field({ label, value, onChange, type = "text", disabled = false, list }: { label: string; value: unknown; onChange: (value: string) => void; type?: string; disabled?: boolean; list?: string }) { return <label className="field">{label}<input type={type} list={list} value={String(value ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value)} /></label>; }
function SelectField({ label, value, options, onChange }: { label: string; value: unknown; options: Array<[string,string]>; onChange: (value: string) => void }) { return <label className="field">{label}<select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>{options.map(([key,text]) => <option key={key} value={key}>{text}</option>)}</select></label>; }
function ModelField({ label, value, models, loading, onChange, onFetch }: { label: string; value: unknown; models: AvailableModel[]; loading: boolean; onChange: (value: string) => void; onFetch: () => void }) { return <label className="field">{label}<div className="model-picker"><input list="available-models" value={String(value ?? "")} placeholder="可手动填写或获取后选择" onChange={(e) => onChange(e.target.value)} /><button className="btn model-fetch-button" type="button" disabled={loading} onClick={onFetch}>{loading ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}{loading ? "正在获取" : "获取可用模型"}</button></div><datalist id="available-models">{models.map((model) => <option key={model.id} value={model.id}>{model.owned_by || model.id}</option>)}</datalist></label>; }
