import AsyncStorage from "@react-native-async-storage/async-storage";

const SETTINGS_KEY = "flowcore.connection.v1";
const DEFAULT_PUBLIC_URL = "https://flowcore.admissaoazusa.com.br";

export type ConnectionPreference = "auto" | "cloudflare" | "tailscale";
export type FlowCoreSettings = { publicUrl: string; privateUrl: string; preference: ConnectionPreference };
export type ConnectionState = { endpoint: string; source: "cloudflare" | "tailscale"; reachable: boolean; version?: string; updatedAt: string; error?: string };
export type MarketItem = { symbol: string; label?: string; level: number | null; delta_pct_1d: number | null; status: "ok" | "no_data" | "error"; source?: string; observation_date?: string };
export type MarketAlert = { label: string; severity: "info" | "warning" | "critical" | string; fired_at?: string };
export type MarketOverview = { items: MarketItem[]; alerts: MarketAlert[]; updated_at?: number; available: boolean; source?: string };
export type MarketBriefing = { lines: string[]; generated_at?: string; available: boolean };
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
  if (settings.preference === "tailscale") return tailscale ? [tailscale, cloudflare] : [cloudflare];
  if (settings.preference === "cloudflare") return tailscale ? [cloudflare, tailscale] : [cloudflare];
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

export async function checkConnection(settings?: FlowCoreSettings): Promise<ConnectionState> {
  const candidates = orderedEndpoints(settings ?? (await loadSettings()));
  let lastError: unknown = new Error("Nenhum endpoint configurado");
  for (const candidate of candidates) {
    try {
      const health = await requestJson<{ version?: string }>(candidate.endpoint, "/api/health");
      return { ...candidate, reachable: true, version: health.version, updatedAt: new Date().toISOString() };
    } catch (error) { lastError = error; }
  }
  return { endpoint: candidates[0]?.endpoint ?? "", source: candidates[0]?.source ?? "cloudflare", reachable: false, updatedAt: new Date().toISOString(), error: lastError instanceof Error ? lastError.message : "Falha de conexão" };
}

export const getMarketOverview = () => flowCoreRequest<MarketOverview>("/api/market/overview");
export const getMarketBriefing = () => flowCoreRequest<MarketBriefing>("/api/market/briefing");
export const getPortfolioSummary = () => flowCoreRequest<PortfolioSummary>("/api/portfolios/moderate-ia-1m/summary");

export function formatNumber(value: number | null, options: Intl.NumberFormatOptions = {}) { return value === null || Number.isNaN(value) ? "—" : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2, ...options }).format(value); }
export function formatDelta(value: number | null) { return value === null || Number.isNaN(value) ? "—" : `${value > 0 ? "+" : ""}${formatNumber(value)}%`; }
