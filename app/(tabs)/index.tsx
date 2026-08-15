import { useRouter } from "expo-router";
import { FlatList, Pressable, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import * as WebBrowser from "expo-web-browser";

import { ScreenContainer } from "@/components/screen-container";
import { periods, type ChurchPeriod } from "@/data/theologians";

export default function HomeScreen() {
  const router = useRouter();
  const openLibrary = async () => {
    await WebBrowser.openBrowserAsync("https://t.me/+5xOk2gVhhCtmNjMx");
  };

  const renderPeriod = ({ item, index }: { item: ChurchPeriod; index: number }) => (
    <Pressable
      onPress={() => router.push(`/period/${item.id}` as any)}
      style={({ pressed }) => [
        { opacity: pressed ? 0.78 : 1, transform: [{ scale: pressed ? 0.985 : 1 }] },
      ]}
    >
      <View className="mb-3 overflow-hidden rounded-2xl border border-border bg-surface p-5">
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
          <Text className="text-xs font-semibold text-primary">{item.theologians.length} pensadores para explorar</Text>
        </View>
      </View>
    </Pressable>
  );

  return (
    <ScreenContainer className="px-5 pt-3" containerClassName="bg-background">
      <StatusBar style="light" />
      <FlatList
        data={periods}
        keyExtractor={(item) => item.id}
        renderItem={renderPeriod}
        showsVerticalScrollIndicator={false}
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
            <Text className="mt-3 max-w-[340px] text-base leading-6 text-muted">Explore séculos de pensamento cristão através de conversas contextualizadas com seus principais intérpretes.</Text>
            <Pressable onPress={openLibrary} style={({ pressed }) => [{ opacity: pressed ? 0.78 : 1, transform: [{ scale: pressed ? 0.985 : 1 }] }]} className="mt-6 flex-row items-center rounded-2xl border border-primary/60 bg-primary/10 p-4">
              <View className="mr-3 h-11 w-11 items-center justify-center rounded-xl bg-primary">
                <Text className="text-xl text-background">▤</Text>
              </View>
              <View className="flex-1">
                <Text className="text-xs font-bold uppercase tracking-widest text-primary">Biblioteca</Text>
                <Text className="mt-1 text-sm leading-5 text-foreground">Acervo de livros teológicos no Telegram</Text>
              </View>
              <Text className="text-2xl text-primary">↗</Text>
            </Pressable>
          </View>
        }
        ListFooterComponent={
          <View className="mt-3 rounded-2xl border border-border bg-surface/70 p-4">
            <Text className="text-xs font-bold uppercase tracking-widest text-primary">Nota do editor</Text>
            <Text className="mt-2 text-xs leading-5 text-muted">As respostas são simulações educativas baseadas em obras e contextos históricos. Não substituem a leitura das fontes originais.</Text>
          </View>
        }
      />
    </ScreenContainer>
  );
}
