import { useLocalSearchParams, useRouter } from "expo-router";
import { FlatList, Pressable, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import { ScreenContainer } from "@/components/screen-container";
import { getPeriod, type Theologian } from "@/data/theologians";

export default function PeriodScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const period = getPeriod(id ?? "");

  if (!period) {
    return (
      <ScreenContainer className="items-center justify-center px-6" containerClassName="bg-background">
        <Text className="font-serif text-2xl text-foreground">Período não encontrado</Text>
        <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.65 : 1 })} className="mt-5 rounded-full bg-primary px-5 py-3">
          <Text className="font-bold text-background">Voltar</Text>
        </Pressable>
      </ScreenContainer>
    );
  }

  const renderTheologian = ({ item }: { item: Theologian }) => (
    <Pressable
      onPress={() => router.push(`/chat/${period.id}/${item.slug}` as any)}
      style={({ pressed }) => [{ opacity: pressed ? 0.78 : 1, transform: [{ scale: pressed ? 0.985 : 1 }] }]}
      className="mb-3"
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
        data={period.theologians}
        keyExtractor={(item) => item.slug}
        renderItem={renderTheologian}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: 36 }}
        ListHeaderComponent={
          <View className="mb-7 pt-2">
            <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.55 : 1 })} className="mb-7 flex-row items-center gap-2">
              <Text className="text-2xl text-primary">‹</Text>
              <Text className="text-sm font-semibold text-muted">Todos os períodos</Text>
            </Pressable>
            <Text className="text-xs font-bold uppercase tracking-[3px] text-primary">{period.era}</Text>
            <Text className="mt-3 font-serif text-4xl font-semibold leading-tight text-foreground">{period.title}</Text>
            <Text className="mt-3 text-base leading-6 text-muted">{period.description}</Text>
            <View className="mt-5 h-px w-16 bg-primary" />
            <Text className="mt-5 text-xs font-bold uppercase tracking-widest text-muted">Escolha uma voz para iniciar</Text>
          </View>
        }
      />
    </ScreenContainer>
  );
}
