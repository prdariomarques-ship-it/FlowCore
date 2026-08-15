import { useMemo, useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import * as WebBrowser from "expo-web-browser";

import { ScreenContainer } from "@/components/screen-container";
import { getAllTheologians, periods, type ChurchPeriod } from "@/data/theologians";

const allTheologians = getAllTheologians();

function normalize(value: string) {
  return value
    .toLocaleLowerCase("pt-BR")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export default function HomeScreen() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const normalizedQuery = normalize(query.trim());

  const filteredPeriods = useMemo(() => {
    if (!normalizedQuery) return periods;

    return periods.reduce<ChurchPeriod[]>((matches, period) => {
      const periodText = normalize(`${period.title} ${period.era} ${period.description}`);
      const periodMatches = periodText.includes(normalizedQuery);
      const matchingTheologians = period.theologians.filter((theologian) =>
        normalize(
          `${theologian.name} ${theologian.dates} ${theologian.tradition} ${theologian.summary}`,
        ).includes(normalizedQuery),
      );

      if (periodMatches) {
        matches.push(period);
      } else if (matchingTheologians.length > 0) {
        matches.push({ ...period, theologians: matchingTheologians });
      }

      return matches;
    }, []);
  }, [normalizedQuery]);

  const matchingTheologianCount = filteredPeriods.reduce(
    (total, period) => total + period.theologians.length,
    0,
  );

  const openLibrary = async () => {
    await WebBrowser.openBrowserAsync("https://t.me/+5xOk2gVhhCtmNjMx");
  };

  const renderPeriod = ({ item, index }: { item: ChurchPeriod; index: number }) => (
    <Pressable
      onPress={() => router.push(`/period/${item.id}` as never)}
      style={({ pressed }) => [
        { marginBottom: 12, opacity: pressed ? 0.78 : 1 },
        pressed && { transform: [{ scale: 0.985 }] },
      ]}
    >
      <View className="overflow-hidden rounded-2xl border border-border bg-surface p-5">
        <View className="mb-4 flex-row items-center justify-between">
          <View className="flex-row items-center gap-3">
            <View className="h-9 w-9 items-center justify-center rounded-full border border-border bg-background">
              <Text className="text-sm font-bold text-primary">{String(index + 1).padStart(2, "0")}</Text>
            </View>
            <Text className="text-xs font-semibold uppercase tracking-widest text-muted">{item.era}</Text>
          </View>
          <Text className="text-2xl text-primary">›</Text>
        </View>
        <Text className="font-serif text-2xl font-semibold text-foreground">{item.title}</Text>
        <Text className="mt-2 text-sm leading-5 text-muted">{item.description}</Text>
        <View className="mt-4 flex-row items-center gap-2">
          <View className="h-1.5 w-1.5 rounded-full bg-primary" />
          <Text className="text-xs font-semibold text-primary">
            {item.theologians.length} {item.theologians.length === 1 ? "pensador encontrado" : "pensadores para explorar"}
          </Text>
        </View>
      </View>
    </Pressable>
  );

  return (
    <ScreenContainer className="px-5 pt-3" containerClassName="bg-background">
      <StatusBar style="light" />
      <FlatList
        data={filteredPeriods}
        keyExtractor={(item) => item.id}
        renderItem={renderPeriod}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingBottom: 36 }}
        ListHeaderComponent={
          <View className="mb-7 pt-3">
            <View className="mb-5 flex-row items-center justify-between">
              <View className="h-11 w-11 items-center justify-center rounded-xl border border-primary/50 bg-surface">
                <Text className="text-xl text-primary">✦</Text>
              </View>
              <View className="rounded-full border border-border px-3 py-1.5">
                <Text className="text-[10px] font-bold uppercase tracking-widest text-muted">Biblioteca viva</Text>
              </View>
            </View>
            <Text className="text-xs font-bold uppercase tracking-[3px] text-primary">Teologia em diálogo</Text>
            <Text className="mt-3 font-serif text-4xl font-semibold leading-tight text-foreground">Converse com a tradição.</Text>
            <Text className="mt-3 max-w-[340px] text-base leading-6 text-muted">
              Pesquise ideias, períodos e vozes cristãs através de conversas contextualizadas com seus principais intérpretes.
            </Text>

            <View className="mt-6 rounded-2xl border border-border bg-surface px-4 py-3">
              <View className="flex-row items-center">
                <Text className="mr-2 text-lg text-primary">⌕</Text>
                <TextInput
                  value={query}
                  onChangeText={setQuery}
                  placeholder="Pesquisar no acervo"
                  placeholderTextColor="#8B9695"
                  autoCapitalize="none"
                  autoCorrect={false}
                  returnKeyType="search"
                  className="min-h-10 flex-1 text-[15px] text-foreground"
                />
                {query.length > 0 && (
                  <Pressable
                    accessibilityLabel="Limpar pesquisa"
                    onPress={() => setQuery("")}
                    style={({ pressed }) => ({ opacity: pressed ? 0.55 : 1 })}
                  >
                    <Text className="px-1 text-xl text-muted">×</Text>
                  </Pressable>
                )}
              </View>
              <Text className="mt-2 text-[11px] leading-4 text-muted">
                Busque por nome, tradição, período ou tema descrito no catálogo.
              </Text>
            </View>

            <View className="mt-3 flex-row items-center justify-between">
              <Text className="text-xs font-semibold uppercase tracking-widest text-muted">
                {normalizedQuery ? `${matchingTheologianCount} resultado${matchingTheologianCount === 1 ? "" : "s"}` : `${periods.length} períodos · ${allTheologians.length} vozes`}
              </Text>
              {normalizedQuery && (
                <Text className="text-xs font-semibold text-primary">Pesquisa ativa</Text>
              )}
            </View>

            <Pressable
              onPress={openLibrary}
              style={({ pressed }) => [
                { marginTop: 20, opacity: pressed ? 0.78 : 1 },
                pressed && { transform: [{ scale: 0.985 }] },
              ]}
            >
              <View className="flex-row items-center rounded-2xl border border-primary/60 bg-primary/10 p-4">
                <View className="mr-3 h-11 w-11 items-center justify-center rounded-xl bg-primary">
                  <Text className="text-xl text-background">▤</Text>
                </View>
                <View className="flex-1">
                  <Text className="text-xs font-bold uppercase tracking-widest text-primary">Biblioteca complementar</Text>
                  <Text className="mt-1 text-sm leading-5 text-foreground">Acervo de livros teológicos no Telegram</Text>
                </View>
                <Text className="text-2xl text-primary">↗</Text>
              </View>
            </Pressable>
          </View>
        }
        ListEmptyComponent={
          <View className="items-center rounded-2xl border border-border bg-surface p-6">
            <Text className="text-3xl text-primary">⌕</Text>
            <Text className="mt-3 text-center font-serif text-2xl font-semibold text-foreground">Nenhuma voz encontrada</Text>
            <Text className="mt-2 text-center text-sm leading-5 text-muted">
              Tente outro nome, período ou palavra relacionada ao tema que deseja estudar.
            </Text>
            <Pressable
              onPress={() => setQuery("")}
              style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}
            >
              <View className="mt-5 rounded-full bg-primary px-5 py-3">
                <Text className="font-bold text-background">Limpar pesquisa</Text>
              </View>
            </Pressable>
          </View>
        }
        ListFooterComponent={
          <View className="mt-3 rounded-2xl border border-border bg-surface/70 p-4">
            <Text className="text-xs font-bold uppercase tracking-widest text-primary">Nota do editor</Text>
            <Text className="mt-2 text-xs leading-5 text-muted">
              As respostas são simulações educativas baseadas em obras e contextos históricos. Não substituem a leitura das fontes originais.
            </Text>
          </View>
        }
      />
    </ScreenContainer>
  );
}
