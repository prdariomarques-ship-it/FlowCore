import { useMemo } from "react";
import { FlatList, Pressable, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { ScreenContainer } from "@/components/screen-container";
import { getPeriod, type Theologian } from "@/data/theologians";

function normalize(value: string) {
  return value
    .toLocaleLowerCase("pt-BR")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export default function PeriodScreen() {
  const router = useRouter();
  const { id, q } = useLocalSearchParams<{ id?: string; q?: string }>();
  const period = getPeriod(id ?? "");
  const query = typeof q === "string" ? q.trim() : "";
  const normalizedQuery = normalize(query);

  const filteredTheologians = useMemo(() => {
    if (!period || !normalizedQuery) return period?.theologians ?? [];

    const periodText = normalize(`${period.title} ${period.era} ${period.description}`);
    if (periodText.includes(normalizedQuery)) return period.theologians;

    return period.theologians.filter((theologian) =>
      normalize(
        `${theologian.name} ${theologian.dates} ${theologian.tradition} ${theologian.summary}`,
      ).includes(normalizedQuery),
    );
  }, [normalizedQuery, period]);

  if (!period) {
    return (
      <ScreenContainer className="items-center justify-center px-6" containerClassName="bg-background">
        <Text className="font-serif text-2xl text-foreground">Período não encontrado</Text>
        <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.65 : 1 })}>
          <View className="mt-5 rounded-full bg-primary px-5 py-3">
            <Text className="font-bold text-background">Voltar</Text>
          </View>
        </Pressable>
      </ScreenContainer>
    );
  }

  const renderTheologian = ({ item }: { item: Theologian }) => (
    <Pressable
      onPress={() => router.push(`/chat/${period.id}/${item.slug}` as never)}
      style={({ pressed }) => [
        { marginBottom: 12, opacity: pressed ? 0.78 : 1 },
        pressed && { transform: [{ scale: 0.985 }] },
      ]}
    >
      <View className="rounded-2xl border border-border bg-surface p-5">
        <View className="flex-row items-start justify-between">
          <View className="flex-1 pr-4">
            <Text className="font-serif text-2xl font-semibold text-foreground">{item.name}</Text>
            <Text className="mt-1 text-xs font-semibold uppercase tracking-widest text-primary">{item.dates} · {item.tradition}</Text>
          </View>
          <View className="h-8 w-8 items-center justify-center rounded-full border border-border">
            <Text className="text-lg text-primary">›</Text>
          </View>
        </View>
        <Text className="mt-4 text-sm leading-5 text-muted">{item.summary}</Text>
        <Text className="mt-4 text-xs font-bold uppercase tracking-widest text-primary">Abrir conversa</Text>
      </View>
    </Pressable>
  );

  return (
    <ScreenContainer className="px-5 pt-2" containerClassName="bg-background">
      <StatusBar style="light" />
      <FlatList
        data={filteredTheologians}
        keyExtractor={(item) => item.slug}
        renderItem={renderTheologian}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: 36 }}
        ListHeaderComponent={
          <View className="mb-7 pt-2">
            <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.55 : 1 })}>
              <View className="mb-7 flex-row items-center gap-2">
                <Text className="text-2xl text-primary">‹</Text>
                <Text className="text-sm font-semibold text-muted">Todos os períodos</Text>
              </View>
            </Pressable>
            <Text className="text-xs font-bold uppercase tracking-[3px] text-primary">{period.era}</Text>
            <Text className="mt-3 font-serif text-4xl font-semibold leading-tight text-foreground">{period.title}</Text>
            <Text className="mt-3 text-base leading-6 text-muted">{period.description}</Text>
            <View className="mt-5 h-px w-16 bg-primary" />
            <Text className="mt-5 text-xs font-bold uppercase tracking-widest text-muted">
              {normalizedQuery ? `${filteredTheologians.length} resultado${filteredTheologians.length === 1 ? "" : "s"} para “${query}”` : "Escolha uma voz para iniciar"}
            </Text>
          </View>
        }
        ListEmptyComponent={
          <View className="items-center rounded-2xl border border-border bg-surface p-6">
            <Text className="text-center font-serif text-2xl font-semibold text-foreground">Nenhum teólogo encontrado</Text>
            <Text className="mt-2 text-center text-sm leading-5 text-muted">Tente outra palavra ou volte ao acervo para pesquisar novamente.</Text>
            <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}>
              <View className="mt-5 rounded-full bg-primary px-5 py-3">
                <Text className="font-bold text-background">Voltar ao acervo</Text>
              </View>
            </Pressable>
          </View>
        }
      />
    </ScreenContainer>
  );
}
