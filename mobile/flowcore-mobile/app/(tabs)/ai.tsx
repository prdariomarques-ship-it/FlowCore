import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Linking, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { ScreenContainer } from "@/components/screen-container";
import { EmptyState, SectionCard, StatusPill } from "@/components/flowcore-ui";
import { formatNewsTimestamp, formatNumber, getMarketNews, getPortfolioSummary, MarketNewsItem, PortfolioPosition } from "@/lib/flowcore";

function NewsRow({ item }: { item: MarketNewsItem }) { const canOpen = Boolean(item.canonical_url?.startsWith("http")); return <TouchableOpacity disabled={!canOpen} activeOpacity={0.7} onPress={() => canOpen && Linking.openURL(item.canonical_url!)} style={styles.trigger}><View style={styles.triggerCopy}><Text style={styles.triggerText}>{item.headline}</Text><Text style={styles.triggerMeta}>{item.publisher || item.provider.name} · {formatNewsTimestamp(item.published_at)}</Text></View><StatusPill label={canOpen ? "Abrir" : "Sem link"} tone={canOpen ? "ai" : "neutral"} /></TouchableOpacity>; }

export default function AiScreen() {
  const [position, setPosition] = useState<PortfolioPosition | null>(null);
  const [news, setNews] = useState<MarketNewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try { const summary = await getPortfolioSummary(); setPosition(summary.data.positions.find((item) => item.id === "ai_theme") ?? null); } catch { /* posição IA é opcional; notícias seguem sem ela */ }
    try { const feed = await getMarketNews("ia"); setNews(feed.data.items); } catch (e) { setError(e instanceof Error ? e.message : "Não foi possível carregar notícias de IA"); }
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);
  return <ScreenContainer className="px-4"><FlatList data={news} keyExtractor={(item) => item.id} renderItem={({ item }) => <NewsRow item={item} />} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#A78BFA" />} ListHeaderComponent={<View style={styles.header}><Text style={styles.heading}>Inteligência artificial</Text><Text style={styles.subtitle}>Parcela satélite de crescimento dentro da carteira moderada</Text>{position ? <SectionCard title="Exposição alvo" accent="#A78BFA"><Text style={styles.weight}>{formatNumber(position.weight)}%</Text><Text style={styles.amount}>R$ {formatNumber(position.amount)} · {position.role}</Text><View style={styles.tags}><StatusPill label="Faixa 4%–10%" tone="ai" /><StatusPill label="Máx. 2% por emissor" tone="warning" /></View></SectionCard> : null}<Text style={styles.listTitle}>Notícias de IA</Text></View>} ListEmptyComponent={loading ? <ActivityIndicator color="#A78BFA" /> : <EmptyState title="Notícias de IA indisponíveis" detail={error ?? "Nenhuma notícia encontrada nesta seção no momento."} />} contentContainerStyle={styles.content} /></ScreenContainer>;
}

const styles = StyleSheet.create({ content: { paddingVertical: 16, gap: 9 }, header: { gap: 14, marginBottom: 3 }, heading: { color: "#EAF2FB", fontSize: 30, lineHeight: 36, fontWeight: "800" }, subtitle: { color: "#9CB0C9", fontSize: 14, lineHeight: 20 }, weight: { color: "#A78BFA", fontSize: 34, lineHeight: 40, fontWeight: "800" }, amount: { color: "#D7E5F4", fontSize: 13, lineHeight: 20, marginTop: 3 }, tags: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 }, listTitle: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, letterSpacing: 0.8, textTransform: "uppercase", fontWeight: "700" }, trigger: { backgroundColor: "#122033", borderColor: "#223A58", borderWidth: 1, borderRadius: 14, padding: 14, flexDirection: "row", justifyContent: "space-between", gap: 12, alignItems: "center" }, triggerCopy: { flex: 1, gap: 3 }, triggerText: { color: "#EAF2FB", fontSize: 14, lineHeight: 19, fontWeight: "600" }, triggerMeta: { color: "#9CB0C9", fontSize: 11, lineHeight: 16 } });
