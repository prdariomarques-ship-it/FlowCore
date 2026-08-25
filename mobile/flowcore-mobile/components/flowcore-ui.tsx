import { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

export function SectionCard({ title, children, accent = "#20C6D8" }: { title: string; children: ReactNode; accent?: string }) {
  return <View style={styles.card}><View style={[styles.rule, { backgroundColor: accent }]} /><Text style={styles.title}>{title}</Text>{children}</View>;
}

export function StatusPill({ label, tone = "neutral" }: { label: string; tone?: "good" | "warning" | "bad" | "neutral" | "ai" }) {
  const color = { good: "#34C38F", warning: "#F2B84B", bad: "#F06B6B", neutral: "#7893B5", ai: "#A78BFA" }[tone];
  return <View style={[styles.pill, { borderColor: color, backgroundColor: `${color}22` }]}><Text style={[styles.pillText, { color }]}>{label}</Text></View>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <View style={styles.empty}><Text style={styles.emptyTitle}>{title}</Text><Text style={styles.emptyDetail}>{detail}</Text></View>;
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#122033", borderColor: "#223A58", borderWidth: 1, borderRadius: 18, padding: 16, overflow: "hidden" },
  rule: { height: 3, width: 42, borderRadius: 2, marginBottom: 11 },
  title: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, letterSpacing: 0.9, fontWeight: "700", textTransform: "uppercase", marginBottom: 10 },
  pill: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 9, paddingVertical: 4, alignSelf: "flex-start" },
  pillText: { fontSize: 11, lineHeight: 14, fontWeight: "700" },
  empty: { paddingVertical: 18, alignItems: "center", gap: 5 },
  emptyTitle: { color: "#EAF2FB", fontSize: 15, lineHeight: 20, fontWeight: "700" },
  emptyDetail: { color: "#9CB0C9", fontSize: 13, lineHeight: 19, textAlign: "center" },
});
