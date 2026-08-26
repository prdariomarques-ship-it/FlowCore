import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { openBrowserAsync, WebBrowserPresentationStyle } from "expo-web-browser";

import { EmptyState, StatusPill } from "@/components/flowcore-ui";
import { ScreenContainer } from "@/components/screen-container";
import { formatNewsTimestamp, getMarketNews, MarketNewsItem } from "@/lib/flowcore";

const SECTIONS = [
  ["all", "Tudo"], ["brasil", "Brasil"], ["eua", "EUA"], ["mundo", "Mundo"],
  ["juros", "Juros"], ["empresas", "Empresas"], ["commodities", "Commodities"], ["ia", "IA"],
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  fed: "Fed", copom: "Copom", ecb: "BCE", boj: "BoJ", geopolitics: "Geopolítica",
  commodities: "Commodities", fixed_income: "Renda fixa", inflation: "Inflação",
  employment: "Emprego", technology: "Tecnologia", banking: "Bancos", brazil: "Brasil", global: "Global",
};

function NewsCard({ item, onOpen }: { item: MarketNewsItem; onOpen: (item: MarketNewsItem) => void }) {
  const canOpen = Boolean(item.canonical_url?.startsWith("http"));
  const source = item.publisher || item.provider.name;
  const category = CATEGORY_LABELS[item.category] ?? item.category;
  return (
    <Pressable disabled={!canOpen} onPress={() => onOpen(item)} style={({ pressed }) => [styles.article, canOpen && pressed && styles.articlePressed, !canOpen && styles.articleDisabled]}>
      <View style={styles.articleTop}>
        <Text style={styles.category}>{category}</Text>
        <StatusPill label={canOpen ? "Abrir fonte" : "Sem link"} tone={canOpen ? "neutral" : "warning"} />
      </View>
      <Text style={styles.headline}>{item.headline}</Text>
      <Text style={styles.lineage}>{source} · Publicada {formatNewsTimestamp(item.published_at)}</Text>
      <View style={styles.articleBottom}>
        <Text style={styles.assets}>{item.related_assets.join(" · ") || "Ativo não informado"}</Text>
        <Text style={styles.collected}>Coletada {formatNewsTimestamp(item.collected_at)}</Text>
      </View>
    </Pressable>
  );
}

export default function NewsScreen() {
  const [section, setSection] = useState("all");
  const [items, setItems] = useState<MarketNewsItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<string | undefined>();
  const [refreshing, setRefreshing] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);

  const loadFirstPage = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const response = await getMarketNews(section);
      setItems(response.data.items);
      setNextCursor(response.data.next_cursor);
      setFetchedAt(response.data.fetched_at);
      if (!response.data.available) setError("O feed respondeu sem dados disponíveis neste momento.");
    } catch (cause) {
      setItems([]);
      setNextCursor(null);
      setError(cause instanceof Error ? cause.message : "Não foi possível consultar as notícias do FlowCore.");
    } finally {
      setRefreshing(false);
    }
  }, [section]);

  useEffect(() => { void loadFirstPage(); }, [loadFirstPage]);

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMore || refreshing) return;
    setLoadingMore(true);
    try {
      const response = await getMarketNews(section, nextCursor);
      setItems(current => [...current, ...response.data.items.filter(item => !current.some(existing => existing.id === item.id))]);
      setNextCursor(response.data.next_cursor);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível carregar mais notícias.");
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, nextCursor, refreshing, section]);

  const openArticle = useCallback(async (item: MarketNewsItem) => {
    if (!item.canonical_url?.startsWith("http")) return;
    setOpenError(null);
    try {
      await openBrowserAsync(item.canonical_url, {
        presentationStyle: WebBrowserPresentationStyle.AUTOMATIC,
        toolbarColor: "#0B1524",
        showTitle: true,
      });
    } catch {
      setOpenError("Não foi possível abrir a fonte desta notícia.");
    }
  }, []);

  const header = useMemo(() => (
    <View style={styles.header}>
      <Text style={styles.heading}>Notícias</Text>
      <Text style={styles.subtitle}>Fontes e horários preservados pelo FlowCore</Text>
      <FlatList
        horizontal
        showsHorizontalScrollIndicator={false}
        data={SECTIONS}
        keyExtractor={([key]) => key}
        contentContainerStyle={styles.filters}
        renderItem={({ item: [key, label] }) => (
          <Pressable onPress={() => setSection(key)} style={({ pressed }) => [styles.filter, key === section && styles.filterActive, pressed && styles.filterPressed]}>
            <Text style={[styles.filterText, key === section && styles.filterTextActive]}>{label}</Text>
          </Pressable>
        )}
      />
      <View style={styles.updateRow}>
        <Text style={styles.updated}>Última coleta: {formatNewsTimestamp(fetchedAt)}</Text>
        {openError ? <Text style={styles.openError}>{openError}</Text> : null}
      </View>
    </View>
  ), [fetchedAt, openError, section]);

  return (
    <ScreenContainer className="px-4">
      <FlatList
        data={items}
        keyExtractor={item => item.id}
        renderItem={({ item }) => <NewsCard item={item} onOpen={openArticle} />}
        ListHeaderComponent={header}
        ListEmptyComponent={refreshing ? <ActivityIndicator color="#20C6D8" /> : <EmptyState title="Notícias indisponíveis" detail={error ?? "Nenhuma notícia foi retornada pela fonte selecionada."} />}
        ListFooterComponent={loadingMore ? <ActivityIndicator color="#20C6D8" style={styles.footerLoader} /> : null}
        onEndReached={() => void loadMore()}
        onEndReachedThreshold={0.5}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void loadFirstPage()} tintColor="#20C6D8" />}
        contentContainerStyle={styles.content}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingVertical: 16, gap: 10 },
  header: { gap: 10, marginBottom: 5 },
  heading: { color: "#EAF2FB", fontSize: 30, lineHeight: 36, fontWeight: "800" },
  subtitle: { color: "#9CB0C9", fontSize: 14, lineHeight: 20 },
  filters: { gap: 8, paddingVertical: 4, paddingRight: 16 },
  filter: { borderRadius: 18, borderWidth: 1, borderColor: "#223A58", backgroundColor: "#122033", paddingHorizontal: 12, paddingVertical: 8 },
  filterActive: { backgroundColor: "#15374A", borderColor: "#20C6D8" },
  filterPressed: { opacity: 0.7 },
  filterText: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, fontWeight: "700" },
  filterTextActive: { color: "#20C6D8" },
  updateRow: { gap: 3, paddingTop: 2 },
  updated: { color: "#7893B5", fontSize: 11, lineHeight: 16 },
  openError: { color: "#F2B84B", fontSize: 11, lineHeight: 16 },
  article: { backgroundColor: "#122033", borderColor: "#223A58", borderWidth: 1, borderRadius: 14, padding: 14, gap: 9 },
  articlePressed: { opacity: 0.72, transform: [{ scale: 0.98 }] },
  articleDisabled: { opacity: 0.62 },
  articleTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 },
  category: { color: "#20C6D8", fontSize: 11, lineHeight: 15, fontWeight: "800", letterSpacing: 0.7, textTransform: "uppercase", flex: 1 },
  headline: { color: "#EAF2FB", fontSize: 16, lineHeight: 22, fontWeight: "700" },
  lineage: { color: "#9CB0C9", fontSize: 12, lineHeight: 17 },
  articleBottom: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10, borderTopColor: "#223A58", borderTopWidth: 1, paddingTop: 9 },
  assets: { color: "#A78BFA", fontSize: 11, lineHeight: 15, fontWeight: "700", flex: 1 },
  collected: { color: "#7893B5", fontSize: 10, lineHeight: 14, textAlign: "right", flex: 1 },
  footerLoader: { marginVertical: 12 },
});
