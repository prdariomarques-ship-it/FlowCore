import { useMemo, useState } from "react";
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable, Text, TextInput, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { ScreenContainer } from "@/components/screen-container";
import { getTheologian, getPeriod } from "@/data/theologians";
import { trpc } from "@/lib/trpc";

type Message = { id: string; role: "user" | "assistant"; content: string };

export default function ChatScreen() {
  const router = useRouter();
  const { periodId, slug } = useLocalSearchParams<{ periodId: string; slug: string }>();
  const theologian = getTheologian(periodId ?? "", slug ?? "");
  const period = getPeriod(periodId ?? "");
  const respondMutation = trpc.chat.respond.useMutation();
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>(() => theologian ? [{ id: "welcome", role: "assistant", content: `A paz. Sou ${theologian.name}. Pode me apresentar uma questão; procurarei respondê-la a partir das preocupações e convicções do meu tempo.` }] : []);

  const history = useMemo(() => messages.map(({ role, content }) => ({ role, content })), [messages]);

  if (!theologian || !period) {
    return (
      <ScreenContainer className="items-center justify-center px-6" containerClassName="bg-background">
        <Text className="font-serif text-2xl text-foreground">Pensador não encontrado</Text>
        <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.65 : 1 })} className="mt-5 rounded-full bg-primary px-5 py-3">
          <Text className="font-bold text-background">Voltar</Text>
        </Pressable>
      </ScreenContainer>
    );
  }

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    setError(null);
    setInput("");
    const userMessage: Message = { id: `${Date.now()}-user`, role: "user", content: trimmed };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setIsLoading(true);
    try {
      const response = await respondMutation.mutateAsync({ theologianSlug: theologian.slug, messages: [...history, { role: "user", content: trimmed }] });
      setMessages([...nextMessages, { id: `${Date.now()}-assistant`, role: "assistant", content: response.message }]);
    } catch {
      setError("Não foi possível obter uma resposta agora. Verifique sua conexão e tente novamente.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ScreenContainer edges={["top", "left", "right"]} containerClassName="bg-background">
      <StatusBar style="light" />
      <KeyboardAvoidingView className="flex-1" behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View className="border-b border-border bg-surface px-5 pb-4 pt-2">
          <View className="flex-row items-center">
            <Pressable onPress={() => router.back()} style={({ pressed }) => ({ opacity: pressed ? 0.55 : 1 })} className="mr-3 h-9 w-9 items-center justify-center rounded-full border border-border">
              <Text className="text-2xl text-primary">‹</Text>
            </Pressable>
            <View className="mr-3 h-11 w-11 items-center justify-center rounded-full bg-primary">
              <Text className="font-serif text-lg font-bold text-background">{theologian.name.split(" ").map((part) => part[0]).slice(0, 2).join("")}</Text>
            </View>
            <View className="flex-1">
              <Text className="font-serif text-xl font-semibold text-foreground">{theologian.name}</Text>
              <Text className="text-xs font-semibold uppercase tracking-widest text-muted">{period.title} · {theologian.dates}</Text>
            </View>
          </View>
        </View>

        <FlatList
          data={messages}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{ padding: 20, paddingBottom: 12 }}
          showsVerticalScrollIndicator={false}
          renderItem={({ item }) => (
            <View className={`mb-4 max-w-[88%] ${item.role === "user" ? "self-end" : "self-start"}`}>
              <Text className="mb-1 px-1 text-[10px] font-bold uppercase tracking-widest text-muted">{item.role === "user" ? "Você" : theologian.name}</Text>
              <View className={`rounded-2xl px-4 py-3 ${item.role === "user" ? "rounded-br-sm bg-userBubble" : "rounded-bl-sm border border-border bg-surface"}`}>
                <Text className={`text-[15px] leading-6 ${item.role === "user" ? "text-parchment" : "text-foreground"}`}>{item.content}</Text>
              </View>
            </View>
          )}
          ListFooterComponent={
            <View>
              {isLoading && <View className="mb-4 self-start rounded-2xl rounded-bl-sm border border-border bg-surface px-4 py-3"><ActivityIndicator color="#C99A4A" /><Text className="mt-2 text-xs text-muted">Consultando as obras e o contexto...</Text></View>}
              {error && <View className="mb-3 rounded-xl border border-terracotta/60 bg-terracotta/10 p-3"><Text className="text-sm leading-5 text-foreground">{error}</Text><Pressable onPress={() => setError(null)} style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })} className="mt-2"><Text className="text-xs font-bold uppercase tracking-widest text-primary">Tentar novamente</Text></Pressable></View>}
            </View>
          }
        />

        <View className="border-t border-border bg-background px-4 pb-3 pt-3">
          <View className="flex-row items-end rounded-2xl border border-border bg-surface px-3 py-2">
            <TextInput value={input} onChangeText={setInput} placeholder="Faça uma pergunta..." placeholderTextColor="#8B9695" multiline maxLength={1200} className="max-h-28 min-h-10 flex-1 px-2 py-2 text-[15px] leading-5 text-foreground" returnKeyType="send" onSubmitEditing={sendMessage} />
            <Pressable onPress={sendMessage} disabled={!input.trim() || isLoading} style={({ pressed }) => [{ opacity: !input.trim() || isLoading ? 0.35 : pressed ? 0.65 : 1 }]} className="h-10 w-10 items-center justify-center rounded-full bg-primary">
              <Text className="text-xl font-bold text-background">↑</Text>
            </Pressable>
          </View>
          <Text className="mt-2 text-center text-[10px] leading-4 text-muted">Simulação educativa · consulte as obras originais para aprofundar.</Text>
        </View>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}
