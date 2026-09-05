import AsyncStorage from "@react-native-async-storage/async-storage";

const SETTINGS_KEY = "flowcore.connection.v1";
const DEFAULT_PUBLIC_URL = "https://flowcore.admissaoazusa.com.br";

export type ConnectionPreference = "auto" | "cloudflare" | "tailscale";
export type FlowCoreSettings = { publicUrl: string; privateUrl: string; preference: ConnectionPreference };

// Estado detalhado de cada componente de conexão
export type ComponentStatus = {
  name: string;
  status: "ok" | "warning" | "error" | "unknown";
  message?: string;
  details?: string;
};

export type DiagnosticResult = {
  internet: ComponentStatus;
  dns: ComponentStatus;
  cloudflare: ComponentStatus;
  tailscale: ComponentStatus;
  z3Private: ComponentStatus;
  flowcorePublic: ComponentStatus;
  flowcorePrivate: ComponentStatus;
  exitNodeActive: boolean;
  exitNodeBreakingInternet: boolean;
};

export type ConnectionState = { 
  endpoint: string; 
  source: "cloudflare" | "tailscale"; 
  reachable: boolean; 
  version?: string; 
  updatedAt: string; 
  error?: string;
  diagnostic?: DiagnosticResult;
};

export type MarketItem = { symbol: string; label?: string; level: number | null; delta_pct_1d: number | null; status: "ok" | "no_data" | "error"; source?: string; observation_date?: string };
export type MarketAlert = { label: string; severity: "info" | "warning" | "critical" | string; fired_at?: string };
export type MarketOverview = { items: MarketItem[]; alerts: MarketAlert[]; updated_at?: number; available: boolean; source?: string };
export type MarketBriefing = { lines: string[]; generated_at?: string; available: boolean };
export type MarketNewsProvider = { id: string; name: string; url: string };
export type MarketNewsItem = {
  id: string;
  headline: string;
  section_tags: string[];
  category: string;
  related_region: string;
  publisher: string | null;
  provider: MarketNewsProvider;
  canonical_url: string | null;
  published_at: string | null;
  collected_at: string;
  related_assets: string[];
  status: "ok" | "no_data" | "error" | string;
};
export type MarketNewsFeed = {
  items: MarketNewsItem[];
  groups: string[];
  section: string;
  supported_sections: string[];
  next_cursor: string | null;
  fetched_at?: string;
  partial_errors: string[];
  available: boolean;
  updated_at?: number;
  source?: string;
};
export type PortfolioPosition = { id: string; label: string; weight: number; amount: number; class: string; role: string };
export type PortfolioSummary = { positions: PortfolioPosition[]; total_value: number; currency: string; mode: string };

export const defaultSettings: FlowCoreSettings = { publicUrl: DEFAULT_PUBLIC_URL, privateUrl: "", preference: "auto" };

function normalizedUrl(url: string) { return url.trim().replace(/\/+$/, ""); }

export async function loadSettings(): Promise<FlowCoreSettings> {
  const saved = await AsyncStorage.getItem(SETTINGS_KEY);
  if (!saved) return defaultSettings;
  try { return { ...defaultSettings, ...JSON.parse(saved) } as FlowCoreSettings; } catch { return defaultSettings; }
}

export async function saveSettings(settings: FlowCoreSettings) {
  const safeSettings: FlowCoreSettings = { ...settings, publicUrl: normalizedUrl(settings.publicUrl), privateUrl: normalizedUrl(settings.privateUrl) };
  await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(safeSettings));
}

function orderedEndpoints(settings: FlowCoreSettings): Array<{ endpoint: string; source: "cloudflare" | "tailscale" }> {
  const cloudflare = { endpoint: normalizedUrl(settings.publicUrl || DEFAULT_PUBLIC_URL), source: "cloudflare" as const };
  const tailscale = settings.privateUrl ? { endpoint: normalizedUrl(settings.privateUrl), source: "tailscale" as const } : null;
  
  // AUTOMÁTICO: testa privado primeiro, depois público
  if (settings.preference === "auto") {
    return tailscale ? [tailscale, cloudflare] : [cloudflare];
  }
  
  // PRIVADO: só usa Tailscale
  if (settings.preference === "tailscale") {
    return tailscale ? [tailscale] : [cloudflare];
  }
  
  // PÚBLICO: só usa Cloudflare
  if (settings.preference === "cloudflare") {
    return [cloudflare];
  }
  
  // Default: auto
  return tailscale ? [tailscale, cloudflare] : [cloudflare];
}

async function requestJson<T>(endpoint: string, path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 9000);
  try {
    const response = await fetch(`${endpoint}${path}`, { ...init, headers: { Accept: "application/json", ...(init?.headers ?? {}) }, signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return (await response.json()) as T;
  } finally { clearTimeout(timeout); }
}

export async function flowCoreRequest<T>(path: string, init?: RequestInit): Promise<{ data: T; endpoint: string; source: "cloudflare" | "tailscale" }> {
  const settings = await loadSettings();
  let lastError: unknown = new Error("Nenhum endpoint configurado");
  for (const candidate of orderedEndpoints(settings)) {
    try { return { data: await requestJson<T>(candidate.endpoint, path, init), ...candidate }; } catch (error) { lastError = error; }
  }
  throw lastError;
}

// Testa conectividade básica com a internet
async function testInternet(): Promise<ComponentStatus> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    // Usa endpoint público confiável (Google DNS ou Cloudflare DNS)
    const response = await fetch("https://1.1.1.1/dns-query?name=google.com", { 
      method: "GET",
      headers: { "Accept": "application/dns-json" },
      signal: controller.signal 
    });
    clearTimeout(timeout);
    if (response.ok) {
      return { name: "Internet", status: "ok", message: "Conectada" };
    }
    return { name: "Internet", status: "warning", message: "Resposta inesperada", details: `HTTP ${response.status}` };
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Falha desconhecida";
    // Verifica se é erro de rede (sem internet) ou DNS
    if (msg.includes("NETWORK") || msg.includes("netfailed")) {
      return { name: "Internet", status: "error", message: "Sem conexão", details: msg };
    }
    if (msg.includes("DNS") || msg.includes("dns")) {
      return { name: "Internet", status: "error", message: "Falha DNS", details: msg };
    }
    return { name: "Internet", status: "error", message: "Indisponível", details: msg };
  }
}

// Testa resolução DNS
async function testDNS(): Promise<ComponentStatus> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const response = await fetch("https://1.1.1.1/dns-query?name=flowcore.admissaoazusa.com.br&type=A", {
      method: "GET",
      headers: { "Accept": "application/dns-json" },
      signal: controller.signal
    });
    clearTimeout(timeout);
    const data = await response.json() as any;
    if (data.Answer && data.Answer.length > 0) {
      return { name: "DNS", status: "ok", message: "Resolvendo normalmente" };
    }
    return { name: "DNS", status: "warning", message: "DNS não retornou registros", details: JSON.stringify(data) };
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Falha desconhecida";
    return { name: "DNS", status: "error", message: "Falha na resolução", details: msg };
  }
}

// Testa acesso ao endpoint Cloudflare público
async function testCloudflare(publicUrl: string): Promise<ComponentStatus> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const response = await fetch(`${publicUrl}/api/health`, {
      method: "GET",
      headers: { "Accept": "application/json" },
      signal: controller.signal
    });
    clearTimeout(timeout);
    if (response.ok) {
      const data = await response.json() as any;
      return { name: "Cloudflare", status: "ok", message: "Disponível", details: `FlowCore ${data.version ?? "?"}` };
    }
    return { name: "Cloudflare", status: "error", message: "HTTP " + response.status, details: `Status ${response.status}` };
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Falha desconhecida";
    if (msg.includes("CERTIFICATE") || msg.includes("SSL") || msg.includes("tls")) {
      return { name: "Cloudflare", status: "error", message: "Erro de certificado", details: msg };
    }
    return { name: "Cloudflare", status: "error", message: "Indisponível", details: msg };
  }
}

// Testa conectividade Tailscale (verifica se está conectado à tailnet)
async function testTailscale(privateUrl: string): Promise<ComponentStatus> {
  if (!privateUrl || privateUrl.trim() === "") {
    return { name: "Tailscale", status: "unknown", message: "Não configurado" };
  }
  
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    
    // Tenta acessar o hostname Tailscale diretamente
    const response = await fetch(`${privateUrl}/api/health`, {
      method: "GET",
      headers: { "Accept": "application/json" },
      signal: controller.signal
    });
    clearTimeout(timeout);
    
    if (response.ok) {
      const data = await response.json() as any;
      return { name: "Tailscale", status: "ok", message: "Conectado", details: `FlowCore ${data.version ?? "?"}` };
    }
    
    // Se falhar, verifica se é erro de certificado (comum em IPs Tailscale)
    return { name: "Tailscale", status: "warning", message: "Acessível mas com problemas", details: `HTTP ${response.status}` };
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Falha desconhecida";
    
    // Verifica erros específicos de Tailscale
    if (msg.includes("CERTIFICATE") || msg.includes("SSL") || msg.includes("tls")) {
      return { 
        name: "Tailscale", 
        status: "warning", 
        message: "Servidor acessível, certificado inválido", 
        details: "Certificado HTTPS não corresponde ao hostname/IP privado" 
      };
    }
    
    if (msg.includes("NETWORK") || msg.includes("netfailed") || msg.includes("Failed to fetch")) {
      return { name: "Tailscale", status: "error", message: "Não conectado à tailnet", details: msg };
    }
    
    return { name: "Tailscale", status: "error", message: "Falha de conexão", details: msg };
  }
}

// Testa acesso direto ao Z3 via IP Tailscale
async function testZ3Private(ipAddress: string): Promise<ComponentStatus> {
  if (!ipAddress) {
    return { name: "Z3 Privado", status: "unknown", message: "IP não configurado" };
  }
  
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    const url = `https://${ipAddress}/api/health`;
    
    const response = await fetch(url, {
      method: "GET",
      headers: { "Accept": "application/json" },
      signal: controller.signal
    });
    clearTimeout(timeout);
    
    if (response.ok) {
      const data = await response.json() as any;
      return { name: "Z3 Privado", status: "ok", message: "Disponível", details: `FlowCore ${data.version ?? "?"}` };
    }
    return { name: "Z3 Privado", status: "warning", message: "HTTP " + response.status };
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Falha desconhecida";
    
    if (msg.includes("CERTIFICATE") || msg.includes("SSL") || msg.includes("tls")) {
      return { 
        name: "Z3 Privado", 
        status: "warning", 
        message: "Acessível, certificado inválido", 
        details: "Certificado HTTPS não corresponde ao IP" 
      };
    }
    
    return { name: "Z3 Privado", status: "error", message: "Indisponível", details: msg };
  }
}

// Detecta se Exit Node está ativo e quebrando a internet
async function testExitNode(): Promise<{ exitNodeActive: boolean; exitNodeBreakingInternet: boolean }> {
  try {
    // Compara tempo de resposta para endpoints públicos vs privados
    const startPublic = Date.now();
    let publicOk = false;
    try {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 3000);
      const resp = await fetch("https://1.1.1.1/dns-query?name=google.com", {
        headers: { "Accept": "application/dns-json" },
        signal: controller.signal
      });
      publicOk = resp.ok;
    } catch { /* ignora */ }
    const timePublic = Date.now() - startPublic;
    
    // Se internet pública está lenta (>5s) ou falhando, pode ser Exit Node
    const exitNodeActive = timePublic > 5000 || !publicOk;
    const exitNodeBreakingInternet = !publicOk && timePublic > 5000;
    
    return { exitNodeActive, exitNodeBreakingInternet };
  } catch {
    return { exitNodeActive: false, exitNodeBreakingInternet: false };
  }
}

export async function runFullDiagnostic(settings: FlowCoreSettings): Promise<DiagnosticResult> {
  const publicUrl = normalizedUrl(settings.publicUrl || DEFAULT_PUBLIC_URL);
  const privateUrl = settings.privateUrl ? normalizedUrl(settings.privateUrl) : "";
  
  // Extrai IP do hostname Tailscale se presente
  let tailscaleIp = "";
  if (privateUrl) {
    try {
      const url = new URL(privateUrl);
      // Se for IP direto
      if (/^\d+\.\d+\.\d+\.\d+$/.test(url.hostname)) {
        tailscaleIp = url.hostname;
      }
      // Se for hostname .ts.net, tenta extrair IP (não possível diretamente no JS)
      // O usuário deve configurar manualmente se quiser testar por IP
    } catch { /* ignora */ }
  }
  
  const [internet, dns, cloudflare, tailscale, z3Private, exitNode] = await Promise.all([
    testInternet(),
    testDNS(),
    testCloudflare(publicUrl),
    testTailscale(privateUrl),
    testZ3Private(tailscaleIp),
    testExitNode()
  ]);
  
  // Determina status dos endpoints FlowCore
  const flowcorePublic: ComponentStatus = {
    name: "FlowCore Público",
    status: cloudflare.status === "ok" ? "ok" : "error",
    message: cloudflare.status === "ok" ? "Disponível" : "Indisponível",
    details: cloudflare.details
  };
  
  const flowcorePrivate: ComponentStatus = {
    name: "FlowCore Privado",
    status: tailscale.status === "ok" ? "ok" : (tailscale.status === "warning" ? "warning" : "error"),
    message: tailscale.status === "ok" ? "Disponível" : (tailscale.status === "warning" ? "Certificado inválido" : "Indisponível"),
    details: tailscale.details
  };
  
  return {
    internet,
    dns,
    cloudflare,
    tailscale,
    z3Private,
    flowcorePublic,
    flowcorePrivate,
    exitNodeActive: exitNode.exitNodeActive,
    exitNodeBreakingInternet: exitNode.exitNodeBreakingInternet
  };
}

export async function checkConnection(settings?: FlowCoreSettings): Promise<ConnectionState> {
  const currentSettings = settings ?? (await loadSettings());
  const candidates = orderedEndpoints(currentSettings);
  let lastError: unknown = new Error("Nenhum endpoint configurado");
  
  // REGRA FUNDAMENTAL: nunca deixar falha da rota privada bloquear rota pública
  // Testa cada candidato na ordem definida, mas continua mesmo após falhas
  for (const candidate of candidates) {
    try {
      const health = await requestJson<{ version?: string }>(candidate.endpoint, "/api/health");
      return { ...candidate, reachable: true, version: health.version, updatedAt: new Date().toISOString() };
    } catch (error) {
      lastError = error;
      // Continua para o próximo candidato (não retorna imediatamente)
    }
  }
  
  // Se todos falharam, executa diagnóstico completo para entender o problema
  const diagnostic = await runFullDiagnostic(currentSettings);
  
  // Mensagem de erro mais informativa baseada no diagnóstico
  let errorMessage = lastError instanceof Error ? lastError.message : "Falha de conexão";
  
  if (diagnostic.exitNodeBreakingInternet) {
    errorMessage = "Exit Node Tailscale está alterando a rota da internet";
  } else if (diagnostic.internet.status === "error") {
    errorMessage = "Sem conexão com a internet";
  } else if (diagnostic.dns.status === "error") {
    errorMessage = "Falha na resolução DNS";
  } else if (diagnostic.cloudflare.status === "error" && diagnostic.tailscale.status === "error") {
    errorMessage = "Ambos os endpoints (público e privado) indisponíveis";
  } else if (diagnostic.tailscale.status === "warning" && diagnostic.cloudflare.status === "error") {
    errorMessage = "Servidor privado acessível, mas certificado HTTPS não corresponde ao endereço";
  }
  
  return { 
    endpoint: candidates[0]?.endpoint ?? "", 
    source: candidates[0]?.source ?? "cloudflare", 
    reachable: false, 
    updatedAt: new Date().toISOString(), 
    error: errorMessage,
    diagnostic
  };
}

export const getMarketOverview = () => flowCoreRequest<MarketOverview>("/api/market/overview");
export const getMarketBriefing = () => flowCoreRequest<MarketBriefing>("/api/market/briefing");
export const getMarketNews = (section = "all", cursor?: string | null, limit = 12) => {
  const query = new URLSearchParams({ section, limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  return flowCoreRequest<MarketNewsFeed>(`/api/market/news?${query.toString()}`);
};
export const getPortfolioSummary = () => flowCoreRequest<PortfolioSummary>("/api/portfolios/moderate-ia-1m/summary");

export function formatNumber(value: number | null, options: Intl.NumberFormatOptions = {}) { return value === null || Number.isNaN(value) ? "—" : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2, ...options }).format(value); }
export function formatDelta(value: number | null) { return value === null || Number.isNaN(value) ? "—" : `${value > 0 ? "+" : ""}${formatNumber(value)}%`; }
export function formatNewsTimestamp(value?: string | null) {
  if (!value) return "Horário não informado";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}
