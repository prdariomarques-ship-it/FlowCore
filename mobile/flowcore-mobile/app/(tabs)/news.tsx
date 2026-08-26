import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Animated, FlatList, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from "react-native";
import { openBrowserAsync, WebBrowserPresentationStyle } from "expo-web-browser";

import { EmptyState, StatusPill } from "@/components/flowcore-ui";
import { ScreenContainer } from "@/components/screen-container";
import { formatNewsTimestamp, getMarketNews, MarketNewsItem } from "@/lib/flowcore";
import { filterNewsItems, loadNewsFavorites, NewsFavorites, persistNewsFavorites } from "@/lib/news-favorites";

const SECTIONS = [
  ["all", "Tudo"], ["brasil", "Brasil"], ["eua", "EUA"], ["mundo", "Mundo"],
  ["juros", "Juros"], ["empresas", "Empresas"], ["commodities", "Commodities"], ["ia", "IA"], ["favorites", "Salvas"],
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  fed: "Fed", copom: "Copom", ecb: "BCE", boj: "BoJ", geopolitics: "Geopolítica",
  commodities: "Commodities", fixed_income: "Renda fixa", inflation: "Inflação",
  employment: "Emprego", technology: "Tecnologia", banking: "Bancos", brazil: "Brasil", global: "Global",
};

function LoadingSkeleton({ opacity }: { opacity: Animated.Value }) {
  return <View style={styles.skeletonGroup}>{["one", "two", "three"].map(key => <Animated.View key={key} style={[styles.skeleton, { opacity }]}><View style={styles.skeletonLineShort} /><View style={styles.skeletonLine} /><View style={styles.skeletonLineWide} /><View style={styles.skeletonLineMeta} /></Animated.View>)}</View>;
}

function NewsCard({ item, isFavorite, onOpen, onToggleFavorite }: { item: MarketNewsItem; isFavorite: boolean; onOpen: (item: MarketNewsItem) => void; onToggleFavorite: (item: MarketNewsItem) => void }) {
  const canOpen = Boolean(item.canonical_url?.startsWith("http"));
  const source = item.publisher || item.provider.name;
  const category = CATEGORY_LABELS[item.category] ?? item.category;
  return <View style={styles.article}>
    <View style={styles.articleTop}>
      <Text style={styles.category}>{category}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel={isFavorite ? "Remover dos favoritos" : "Salvar para leitura posterior"} onPress={() => onToggleFavorite(item)} style={({ pressed }) => [styles.favoriteButton, isFavorite && styles.favoriteButtonActive, pressed && styles.favoritePressed]}>
        <MaterialIcons name={isFavorite ? "bookmark" : "bookmark-border"} size={18} color={isFavorite ? "#F2B84B" : "#9CB0C9"} />
        <Text style={[styles.favoriteText, isFavorite && styles.favoriteTextActive]}>{isFavorite ? "Salva" : "Salvar"}</Text>
      </Pressable>
    </View>
    <Pressable disabled={!canOpen} onPress={() => onOpen(item)} style={({ pressed }) => [styles.articleBody, canOpen && pressed && styles.articlePressed, !canOpen && styles.articleDisabled]}>
      <Text style={styles.headline}>{item.headline}</Text>
      <Text style={styles.lineage}>{source} · Publicada {formatNewsTimestamp(item.published_at)}</Text>
      <View style={styles.articleBottom}>
        <Text style={styles.assets}>{item.related_assets.join(" · ") || "Ativo não informado"}</Text>
        <StatusPill label={canOpen ? "Abrir fonte" : "Sem link"} tone={canOpen ? "neutral" : "warning"} />
      </View>
      <Text style={styles.collected}>Coletada {formatNewsTimestamp(item.collected_at)}</Text>
    </Pressable>
  </View>;
}

export default function NewsScreen() {
  const [section, setSection] = useState("all");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<MarketNewsItem[]>([]);
  const [favorites, setFavorites] = useState<NewsFavorites>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<string | undefined>();
  const [refreshing, setRefreshing] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const [refreshMessage, setRefreshMessage] = useState("Carregando fontes rastreáveis…");
  const favoritesRef = useRef(favorites);
  const pulse = useRef(new Animated.Value(0.42)).current;

  useEffect(() => { favoritesRef.current = favorites; }, [favorites]);
  useEffect(() => { void loadNewsFavorites().then(setFavorites); }, []);
  useEffect(() => {
    const animation = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 0.85, duration: 550, useNativeDriver: true }),
      Animated.timing(pulse, { toValue: 0.42, duration: 550, useNativeDriver: true }),
    ]));
    if (refreshing || loadingMore) animation.start(); else { animation.stop(); pulse.setValue(1); }
    return () => animation.stop();
  }, [loadingMore, pulse, refreshing]);

  const loadFirstPage = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    setRefreshMessage(section === "favorites" ? "Atualizando leituras salvas…" : "Atualizando notícias e proveniência…");
    if (section === "favorites") {
      setItems(Object.values(favoritesRef.current).sort((a, b) => b.collected_at.localeCompare(a.collected_at)));
      setNextCursor(null);
      setFetchedAt(new Date().toISOString());
      setRefreshMessage("Leituras salvas atualizadas agora");
      setRefreshing(false);
      return;
    }
    try {
      const response = await getMarketNews(section);
      setItems(response.data.items);
      setNextCursor(response.data.next_cursor);
      setFetchedAt(response.data.fetched_at);
      setRefreshMessage(response.data.available ? "Feed atualizado agora" : "Feed atualizado sem itens disponíveis");
      if (!response.data.available) setError("O feed respondeu sem dados disponíveis neste momento.");
    } catch (cause) {
      setItems([]);
      setNextCursor(null);
      setRefreshMessage("Atualização não concluída");
      setError(cause instanceof Error ? cause.message : "Não foi possível consultar as notícias do FlowCore.");
    } finally {
      setRefreshing(false);
    }
  }, [section]);

  useEffect(() => { void loadFirstPage(); }, [loadFirstPage]);
  useEffect(() => {
    if (section === "favorites") setItems(Object.values(favorites).sort((a, b) => b.collected_at.localeCompare(a.collected_at)));
  }, [favorites, section]);

  const loadMore = useCallback(async () => {
    if (section === "favorites" || !nextCursor || loadingMore || refreshing) return;
    setLoadingMore(true);
    setRefreshMessage("Carregando mais notícias…");
    try {
      const response = await getMarketNews(section, nextCursor);
      setItems(current => [...current, ...response.data.items.filter(item => !current.some(existing => existing.id === item.id))]);
      setNextCursor(response.data.next_cursor);
      setRefreshMessage("Mais notícias carregadas");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível carregar mais notícias.");
      setRefreshMessage("Não foi possível carregar mais itens");
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, nextCursor, refreshing, section]);

  const toggleFavorite = useCallback((item: MarketNewsItem) => {
    setFavorites(current => {
      const next = { ...current };
      if (next[item.id]) delete next[item.id]; else next[item.id] = item;
      void persistNewsFavorites(next).catch(() => setError("Não foi possível salvar a notícia para leitura posterior."));
      return next;
    });
  }, []);

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

  const visibleItems = useMemo(() => filterNewsItems(items, query), [items, query]);
  const header = useMemo(() => (
    <View style={styles.header}>
      <Text style={styles.heading}>Notícias</Text>
      <Text style={styles.subtitle}>Fontes, horários e leituras salvas pelo FlowCore</Text>
      <View style={styles.searchBox}>
        <MaterialIcons name="search" size={20} color="#7893B5" />
        <TextInput value={query} onChangeText={setQuery} placeholder="Buscar título, fonte ou ativo" placeholderTextColor="#7893B5" returnKeyType="search" style={styles.searchInput} accessibilityLabel="Buscar notícias" />
        {query ? <Pressable accessibilityRole="button" accessibilityLabel="Limpar busca" onPress={() => setQuery("")} style={({ pressed }) => [styles.clearButton, pressed && styles.filterPressed]}><MaterialIcons name="close" size={18} color="#9CB0C9" /></Pressable> : null}
      </View>
      <FlatList horizontal showsHorizontalScrollIndicator={false} data={SECTIONS} keyExtractor={([key]) => key} contentContainerStyle={styles.filters} renderItem={({ item: [key, label] }) => <Pressable onPress={() => setSection(key)} style={({ pressed }) => [styles.filter, key === section && styles.filterActive, pressed && styles.filterPressed]}><Text style={[styles.filterText, key === section && styles.filterTextActive]}>{key === "favorites" ? `${label} (${Object.keys(favorites).length})` : label}</Text></Pressable>} />
      <View style={styles.updateRow}>
        <View style={styles.updateStatus}>{refreshing || loadingMore ? <Animated.View style={[styles.pulseDot, { opacity: pulse }]} /> : <View style={styles.readyDot} />}<Text style={styles.updated}>{refreshing || loadingMore ? refreshMessage : `${refreshMessage} · ${formatNewsTimestamp(fetchedAt)}`}</Text></View>
        {openError ? <Text style={styles.openError}>{openError}</Text> : null}
        {query && !refreshing ? <Text style={styles.searchResult}>{visibleItems.length} resultado(s) para “{query}”</Text> : null}
      </View>
    </View>
  ), [favorites, fetchedAt, loadingMore, openError, pulse, query, refreshMessage, refreshing, section, visibleItems.length]);

  return (
    <ScreenContainer className="px-4">
      <FlatList
        data={visibleItems}
        keyExtractor={item => item.id}
        renderItem={({ item }) => <NewsCard item={item} isFavorite={Boolean(favorites[item.id])} onOpen={openArticle} onToggleFavorite={toggleFavorite} />}
        ListHeaderComponent={header}
        ListEmptyComponent={refreshing ? <LoadingSkeleton opacity={pulse} /> : <EmptyState title={section === "favorites" ? "Nenhuma leitura salva" : "Notícias indisponíveis"} detail={section === "favorites" ? "Use Salvar em uma notícia para montar sua leitura posterior." : error ?? "Nenhuma notícia corresponde aos filtros selecionados."} />}
        ListFooterComponent={loadingMore ? <View style={styles.footerLoading}><Animated.View style={[styles.pulseDot, { opacity: pulse }]} /><Text style={styles.footerText}>Carregando mais notícias…</Text></View> : null}
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
  searchBox: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: 8, borderWidth: 1, borderColor: "#223A58", backgroundColor: "#122033", borderRadius: 12, paddingHorizontal: 12 },
  searchInput: { flex: 1, color: "#EAF2FB", fontSize: 14, lineHeight: 20, paddingVertical: 10 },
  clearButton: { padding: 3 },
  filters: { gap: 8, paddingVertical: 4, paddingRight: 16 },
  filter: { borderRadius: 18, borderWidth: 1, borderColor: "#223A58", backgroundColor: "#122033", paddingHorizontal: 12, paddingVertical: 8 },
  filterActive: { backgroundColor: "#15374A", borderColor: "#20C6D8" },
  filterPressed: { opacity: 0.7 },
  filterText: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, fontWeight: "700" },
  filterTextActive: { color: "#20C6D8" },
  updateRow: { gap: 3, paddingTop: 2 },
  updateStatus: { flexDirection: "row", alignItems: "center", gap: 7 },
  pulseDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#20C6D8" },
  readyDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#34C38F" },
  updated: { color: "#7893B5", fontSize: 11, lineHeight: 16, flex: 1 },
  openError: { color: "#F2B84B", fontSize: 11, lineHeight: 16 },
  searchResult: { color: "#A78BFA", fontSize: 11, lineHeight: 16 },
  article: { backgroundColor: "#122033", borderColor: "#223A58", borderWidth: 1, borderRadius: 14, padding: 14, gap: 9 },
  articleTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 },
  category: { color: "#20C6D8", fontSize: 11, lineHeight: 15, fontWeight: "800", letterSpacing: 0.7, textTransform: "uppercase", flex: 1 },
  favoriteButton: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: "#223A58", borderRadius: 14, paddingHorizontal: 8, paddingVertical: 5 },
  favoriteButtonActive: { borderColor: "#F2B84B", backgroundColor: "#F2B84B22" },
  favoritePressed: { opacity: 0.65, transform: [{ scale: 0.96 }] },
  favoriteText: { color: "#9CB0C9", fontSize: 11, lineHeight: 14, fontWeight: "700" },
  favoriteTextActive: { color: "#F2B84B" },
  articleBody: { gap: 9 },
  articlePressed: { opacity: 0.72, transform: [{ scale: 0.985 }] },
  articleDisabled: { opacity: 0.62 },
  headline: { color: "#EAF2FB", fontSize: 16, lineHeight: 22, fontWeight: "700" },
  lineage: { color: "#9CB0C9", fontSize: 12, lineHeight: 17 },
  articleBottom: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10, borderTopColor: "#223A58", borderTopWidth: 1, paddingTop: 9 },
  assets: { color: "#A78BFA", fontSize: 11, lineHeight: 15, fontWeight: "700", flex: 1 },
  collected: { color: "#7893B5", fontSize: 10, lineHeight: 14, textAlign: "right" },
  footerLoading: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8, paddingVertical: 14 },
  footerText: { color: "#9CB0C9", fontSize: 12, lineHeight: 16 },
  skeletonGroup: { gap: 10, paddingTop: 8 },
  skeleton: { minHeight: 148, backgroundColor: "#122033", borderColor: "#223A58", borderWidth: 1, borderRadius: 14, padding: 14, gap: 12 },
  skeletonLineShort: { width: 68, height: 10, borderRadius: 5, backgroundColor: "#2B4767" },
  skeletonLine: { width: "84%", height: 16, borderRadius: 6, backgroundColor: "#2B4767" },
  skeletonLineWide: { width: "96%", height: 16, borderRadius: 6, backgroundColor: "#2B4767" },
  skeletonLineMeta: { width: "55%", height: 10, borderRadius: 5, backgroundColor: "#223A58", marginTop: 4 },
});
