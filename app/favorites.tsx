import { useMemo } from "react";
import { FlatList, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { ScreenContainer } from "@/components/screen-container";
import { getAllTheologians, getPeriod, type Theologian } from "@/data/theologians";
import { useFavorites } from "@/lib/favorites-provider";

const allTheologians = getAllTheologians();

export default function FavoritesScreen() {
  const router = useRouter();
  const { favoriteSlugs, isReady, isFavorite, toggleFavorite } = useFavorites();

  const favoriteTheologians = useMemo(
    () => favoriteSlugs
      .map((slug) => allTheologians.find((theologian) => theologian.slug === slug))
      .filter((theologian): theologian is Theologian => theologian !== undefined),
    [favoriteSlugs],
  );

  const renderTheologian = ({ item }: { item: Theologian }) => {
    const period = getPeriod(item.periodId);
    const saved = isFavorite(item.slug);

    return (
      <View className="mb-3 rounded-2xl border border-border bg-surface p-5">
        <View className="flex-row items-start justify-between">
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Abrir conversa com ${item.name}`}
            onPress={() => router.push(`/chat/${item.periodId}/${item.slug}` as never)}
            style={({ pressed }) => ({ flex: 1, paddingRight: 12, opacity: pressed ? 0.74 : 1 })}
          >
            <Text className="font-serif text-2xl font-semibold text-foreground">{item.name}</Text>
            <Text className="mt-1 text-xs font-semibold uppercase tracking-widest text-primary">
              {period?.title ?? item.periodId}
            </Text>
            <Text className="mt-3 text-sm leading-5 text-muted">{item.summary}</Text>
            <Text className="mt-4 text-xs font-bold uppercase tracking-widest text-primary">Abrir conversa</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Remover ${item.name} dos favoritos`}
            accessibilityState={{ selected: saved }}
            disabled={!isReady}
            onPress={() => toggleFavorite(item.slug)}
            style={({ pressed }) => ({ opacity: !isReady ? 0.4 : pressed ? 0.6 : 1 })}
          >
            <View className="h-10 w-10 items-center justify-center rounded-full border border-primary bg-primary/15">
              <Text className="text-lg text-primary">★</Text>
            </View>
          </Pressable>
        </View>
      </View>
    );
  };

  return (
    <ScreenContainer className="px-5 pt-2" containerClassName="bg-background">
      <StatusBar style="light" />
      <FlatList
        data={favoriteTheologians}
        keyExtractor={(item) => item.slug}
        renderItem={renderTheologian}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: 36 }}
        ListHeaderComponent={
          <View className="mb-7 pt-2">
            <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.55 : 1 })}>
              <View className="mb-7 flex-row items-center gap-2">
                <Text className="text-2xl text-primary">‹</Text>
                <Text className="text-sm font-semibold text-muted">Voltar ao acervo</Text>
              </View>
            </Pressable>
            <Text className="text-xs font-bold uppercase tracking-[3px] text-primary">Sua biblioteca</Text>
            <Text className="mt-3 font-serif text-4xl font-semibold leading-tight text-foreground">Teólogos favoritos</Text>
            <Text className="mt-3 text-base leading-6 text-muted">
              Guarde as vozes que deseja revisitar em suas próximas pesquisas e conversas.
            </Text>
          </View>
        }
        ListEmptyComponent={
          <View className="items-center rounded-2xl border border-border bg-surface p-6">
            <Text className="text-3xl text-primary">☆</Text>
            <Text className="mt-3 text-center font-serif text-2xl font-semibold text-foreground">
              {isReady ? "Sua lista está vazia" : "Carregando favoritos"}
            </Text>
            {isReady && (
              <>
                <Text className="mt-2 text-center text-sm leading-5 text-muted">
                  Abra um período e toque na estrela de um teólogo para mantê-lo por perto.
                </Text>
                <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}>
                  <View className="mt-5 rounded-full bg-primary px-5 py-3">
                    <Text className="font-bold text-background">Explorar acervo</Text>
                  </View>
                </Pressable>
              </>
            )}
          </View>
        }
      />
    </ScreenContainer>
  );
}
