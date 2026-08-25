import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { ScreenContainer } from "@/components/screen-container";
import { EmptyState, SectionCard, StatusPill } from "@/components/flowcore-ui";
import { formatNumber, getPortfolioSummary, PortfolioPosition, PortfolioSummary } from "@/lib/flowcore";

function PositionRow({ item }: { item: PortfolioPosition }) { return <View style={styles.row}><View style={styles.rowCopy}><Text style={styles.label}>{item.label}</Text><Text style={styles.role}>{item.role}</Text></View><View style={styles.values}><Text style={styles.weight}>{formatNumber(item.weight)}%</Text><Text style={styles.amount}>R$ {formatNumber(item.amount)}</Text></View></View>; }

export default function PortfolioScreen() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { setError(null); try { const result = await getPortfolioSummary(); setSummary(result.data); } catch (e) { setError(e instanceof Error ? e.message : "Não foi possível carregar a carteira"); } finally { setLoading(false); } }, []);
  useEffect(() => { load(); }, [load]);
  const ai = summary?.positions.find((position) => position.id === "ai_theme");
  return <ScreenContainer className="px-4"><FlatList data={summary?.positions ?? []} keyExtractor={(item) => item.id} renderItem={({ item }) => <PositionRow item={item} />} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#20C6D8" />} ListHeaderComponent={<View style={styles.header}><Text style={styles.heading}>Carteira</Text><Text style={styles.subtitle}>Alocação de referência — sem execução automática</Text>{summary ? <SectionCard title="Estrutura moderada"><Text style={styles.total}>R$ {formatNumber(summary.total_value)}</Text><Text style={styles.totalCaption}>Valor de referência · {summary.mode.replaceAll("_", " ")}</Text><View style={styles.tags}><StatusPill label={`${summary.positions.length} subdivisões`} tone="neutral" />{ai ? <StatusPill label={`IA ${formatNumber(ai.weight)}%`} tone="ai" /> : null}</View></SectionCard> : null}<Text style={styles.listTitle}>Alocação detalhada</Text></View>} ListEmptyComponent={loading ? <ActivityIndicator color="#20C6D8" /> : <EmptyState title="Carteira indisponível" detail={error ?? "Verifique o endpoint FlowCore configurado."} />} contentContainerStyle={styles.content} /></ScreenContainer>;
}

const styles = StyleSheet.create({ content: { paddingVertical: 16, gap: 9 }, header: { gap: 14, marginBottom: 3 }, heading: { color: "#EAF2FB", fontSize: 30, lineHeight: 36, fontWeight: "800" }, subtitle: { color: "#9CB0C9", fontSize: 14, lineHeight: 20 }, total: { color: "#20C6D8", fontSize: 28, lineHeight: 34, fontWeight: "800" }, totalCaption: { color: "#9CB0C9", fontSize: 12, lineHeight: 18, marginTop: 3 }, tags: { flexDirection: "row", gap: 8, marginTop: 12 }, listTitle: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, letterSpacing: 0.8, textTransform: "uppercase", fontWeight: "700" }, row: { backgroundColor: "#122033", borderColor: "#223A58", borderWidth: 1, borderRadius: 14, padding: 14, flexDirection: "row", gap: 10, justifyContent: "space-between" }, rowCopy: { flex: 1 }, label: { color: "#EAF2FB", fontSize: 14, lineHeight: 19, fontWeight: "700" }, role: { color: "#9CB0C9", fontSize: 12, lineHeight: 17, marginTop: 3 }, values: { alignItems: "flex-end" }, weight: { color: "#20C6D8", fontSize: 16, lineHeight: 20, fontWeight: "800" }, amount: { color: "#9CB0C9", fontSize: 11, lineHeight: 16, marginTop: 3 } });
