import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { ScreenContainer } from "@/components/screen-container";
import { EmptyState, SectionCard, StatusPill } from "@/components/flowcore-ui";
import { formatNumber, getPortfolioSummary, PortfolioPosition } from "@/lib/flowcore";

const triggers = ["Resultados e guidance", "Capex de infraestrutura e nuvem", "Regulação e concorrência", "Concentração e valuation"];

export default function AiScreen() {
  const [position, setPosition] = useState<PortfolioPosition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { setError(null); try { const summary = await getPortfolioSummary(); setPosition(summary.data.positions.find((item) => item.id === "ai_theme") ?? null); } catch (e) { setError(e instanceof Error ? e.message : "Não foi possível carregar a exposição IA"); } finally { setLoading(false); } }, []);
  useEffect(() => { load(); }, [load]);
  return <ScreenContainer className="px-4"><FlatList data={triggers} keyExtractor={(item) => item} renderItem={({ item }) => <View style={styles.trigger}><Text style={styles.triggerText}>{item}</Text><StatusPill label="Monitorar" tone="warning" /></View>} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#A78BFA" />} ListHeaderComponent={<View style={styles.header}><Text style={styles.heading}>Inteligência artificial</Text><Text style={styles.subtitle}>Parcela satélite de crescimento dentro da carteira moderada</Text>{position ? <SectionCard title="Exposição alvo" accent="#A78BFA"><Text style={styles.weight}>{formatNumber(position.weight)}%</Text><Text style={styles.amount}>R$ {formatNumber(position.amount)} · {position.role}</Text><View style={styles.tags}><StatusPill label="Faixa 4%–10%" tone="ai" /><StatusPill label="Máx. 2% por emissor" tone="warning" /></View></SectionCard> : null}<Text style={styles.listTitle}>Gatilhos de revisão</Text></View>} ListEmptyComponent={loading ? <ActivityIndicator color="#A78BFA" /> : <EmptyState title="Exposição IA indisponível" detail={error ?? "O endpoint de carteira não retornou a posição temática."} />} contentContainerStyle={styles.content} /></ScreenContainer>;
}

const styles = StyleSheet.create({ content: { paddingVertical: 16, gap: 9 }, header: { gap: 14, marginBottom: 3 }, heading: { color: "#EAF2FB", fontSize: 30, lineHeight: 36, fontWeight: "800" }, subtitle: { color: "#9CB0C9", fontSize: 14, lineHeight: 20 }, weight: { color: "#A78BFA", fontSize: 34, lineHeight: 40, fontWeight: "800" }, amount: { color: "#D7E5F4", fontSize: 13, lineHeight: 20, marginTop: 3 }, tags: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 }, listTitle: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, letterSpacing: 0.8, textTransform: "uppercase", fontWeight: "700" }, trigger: { backgroundColor: "#122033", borderColor: "#223A58", borderWidth: 1, borderRadius: 14, padding: 14, flexDirection: "row", justifyContent: "space-between", gap: 12, alignItems: "center" }, triggerText: { color: "#EAF2FB", flex: 1, fontSize: 14, lineHeight: 19, fontWeight: "600" } });
