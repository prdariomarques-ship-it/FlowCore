import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { Tabs } from "expo-router";
import { Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { HapticTab } from "@/components/haptic-tab";
import { useColors } from "@/hooks/use-colors";

const icons = { index: "dashboard", market: "show-chart", portfolio: "pie-chart", ai: "psychology", connection: "settings-input-component" } as const;

export default function TabLayout() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const bottomPadding = Platform.OS === "web" ? 10 : Math.max(insets.bottom, 8);
  return <Tabs screenOptions={({ route }) => ({ headerShown: false, tabBarButton: HapticTab, tabBarActiveTintColor: "#20C6D8", tabBarInactiveTintColor: "#7893B5", tabBarStyle: { paddingTop: 7, paddingBottom: bottomPadding, height: 58 + bottomPadding, backgroundColor: "#0B1524", borderTopColor: "#223A58" }, tabBarLabelStyle: { fontSize: 10, fontWeight: "700" }, tabBarIcon: ({ color }) => <MaterialIcons name={icons[route.name as keyof typeof icons]} size={23} color={color} /> })}><Tabs.Screen name="index" options={{ title: "Visão" }} /><Tabs.Screen name="market" options={{ title: "Mercado" }} /><Tabs.Screen name="portfolio" options={{ title: "Carteira" }} /><Tabs.Screen name="ai" options={{ title: "IA" }} /><Tabs.Screen name="connection" options={{ title: "Conexão" }} /></Tabs>;
}
