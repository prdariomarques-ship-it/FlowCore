import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { ScreenContainer } from "@/components/screen-container";
import { EmptyState, SectionCard, StatusPill } from "@/components/flowcore-ui";
import { formatDelta, formatNumber, getMarketBriefing, getMarketOverview, MarketBriefing, MarketItem, MarketOverview } from "@/lib/flowcore";

function MarketRow({ item }: { item: MarketItem }) {
  const positive = (item.delta_pct_1d ?? 0) >= 0;
  const source = item.source ? item.source.replaceAll("_", " ").toUpperCase() : "ORIGEM NÃO INFORMADA";
  return <View style={styles.row}><View style={styles.copy}><Text style={styles.symbol}>{item.label ?? item.symbol}</Text><Text style={styles.level}>{formatNumber(item.level)}</Text><Text style={styles.lineage}>{source}{item.observation_date ? ` · ${item.observation_date}` : ""}</Text></View><StatusPill label={item.status === "ok" ? formatDelta(item.delta_pct_1d) : "Sem dado"} tone={item.status === "ok" ? (positive ? "good" : "bad") : "warning"} /></View>;
}

export default function MarketScreen() {
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [briefing, setBriefing] = useState<MarketBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try { const [market, note] = await Promise.all([getMarketOverview(), getMarketBriefing()]); setOverview(market.data); setBriefing(note.data); }
    catch (e) { setError(e instanceof Error ? e.message : "Não foi possível consultar o FlowCore"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  return <ScreenContainer className="px-4"><FlatList data={overview?.items ?? []} keyExtractor={(item) => item.symbol} renderItem={({ item }) => <MarketRow item={item} />} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#20C6D8" />} ListHeaderComponent={<View style={styles.header}><Text style={styles.heading}>Mercado</Text><Text style={styles.subtitle}>Mesmo feed usado pelo briefing de mercado</Text>{briefing?.lines?.length ? <SectionCard title="Briefing"><View style={styles.briefing}>{briefing.lines.slice(0, 6).map((line, index) => <Text key={`${line}-${index}`} style={styles.briefingLine}>{line}</Text>)}</View></SectionCard> : null}<Text style={styles.listTitle}>Índices e ativos monitorados</Text></View>} ListEmptyComponent={loading ? <ActivityIndicator color="#20C6D8" /> : <EmptyState title="Mercado indisponível" detail={error ?? "A fonte ainda não retornou cotações. Verifique a conexão na aba Conexão."} />} contentContainerStyle={styles.content} /></ScreenContainer>;
}

const styles = StyleSheet.create({ content: { paddingVertical: 16, gap: 10 }, header: { gap: 14, marginBottom: 2 }, heading: { color: "#EAF2FB", fontSize: 30, lineHeight: 36, fontWeight: "800" }, subtitle: { color: "#9CB0C9", fontSize: 14, lineHeight: 20 }, briefing: { gap: 8 }, briefingLine: { color: "#D7E5F4", fontSize: 13, lineHeight: 19 }, listTitle: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, letterSpacing: 0.8, textTransform: "uppercase", fontWeight: "700" }, row: { backgroundColor: "#122033", borderColor: "#223A58", borderWidth: 1, borderRadius: 14, padding: 14, flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 }, copy: { flex: 1 }, symbol: { color: "#EAF2FB", fontSize: 15, lineHeight: 20, fontWeight: "700" }, level: { color: "#9CB0C9", fontSize: 13, lineHeight: 19, marginTop: 2 }, lineage: { color: "#7893B5", fontSize: 10, lineHeight: 15, marginTop: 3, fontWeight: "700" } });
