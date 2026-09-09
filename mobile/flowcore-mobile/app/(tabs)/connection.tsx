import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { ScreenContainer } from "@/components/screen-container";
import { SectionCard, StatusPill } from "@/components/flowcore-ui";
import { checkConnection, ConnectionPreference, ConnectionState, defaultSettings, FlowCoreSettings, loadSettings, runFullDiagnostic, saveSettings, ComponentStatus } from "@/lib/flowcore";

const preferences = [
  { value: "auto", label: "Automático" },
  { value: "tailscale", label: "Privado" },
  { value: "cloudflare", label: "Público" }
];

function statusColor(status) {
  switch (status) {
    case "ok": return "#34C38F";
    case "warning": return "#F0B94B";
    case "error": return "#F06B6B";
    default: return "#7893B5";
  }
}

function statusIcon(status) {
  switch (status) {
    case "ok": return "🟢";
    case "warning": return "🟡";
    case "error": return "🔴";
    default: return "⚪";
  }
}

export default function ConnectionScreen() {
  const [settings, setSettings] = useState(defaultSettings);
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [showDiagnostic, setShowDiagnostic] = useState(false);

  const test = useCallback(async (nextSettings) => {
    setLoading(true);
    const status = await checkConnection(nextSettings ?? settings);
    setState(status);
    setLoading(false);
  }, [settings]);

  useEffect(() => {
    loadSettings().then((saved) => {
      setSettings(saved);
      test(saved);
    });
  }, [test]);

  const update = (key, value) =>
    setSettings((current) => ({ ...current, [key]: value }));

  const persist = async () => {
    setSaving(true);
    await saveSettings(settings);
    await test(settings);
    setSaving(false);
  };

  const runDiagnostic = async () => {
    setDiagnosing(true);
    setShowDiagnostic(true);
    const diagnostic = await runFullDiagnostic(settings);
    setState((prev) => prev ? { ...prev, diagnostic } : null);
    setDiagnosing(false);
  };

  const renderComponentStatus = (component) => (
    <View key={component.name} style={styles.diagnosticRow}>
      <Text style={styles.diagnosticLabel}>{component.name}</Text>
      <View style={styles.diagnosticRight}>
        <Text style={styles.diagnosticIcon}>{statusIcon(component.status)}</Text>
        <Text style={[styles.diagnosticStatus, { color: statusColor(component.status) }]}>
          {component.message ?? "—"}
        </Text>
      </View>
      {component.details && (
        <Text style={styles.diagnosticDetails} numberOfLines={2}>
          {component.details}
        </Text>
      )}
    </View>
  );

  return (
    <ScreenContainer className="px-4">
      <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
        <View style={styles.content}>
          <Text style={styles.heading}>Conexão</Text>
          <Text style={styles.subtitle}>
            Cloudflare é o acesso HTTPS público. Tailscale é a rota privada entre dispositivos autorizados.
          </Text>

          <SectionCard title="Estado atual" accent={state?.reachable ? "#34C38F" : "#F06B6B"}>
            {loading ? (
              <ActivityIndicator color="#20C6D8" />
            ) : (
              <View style={styles.status}>
                <StatusPill label={state?.reachable ? "Conectado" : "Indisponível"} tone={state?.reachable ? "good" : "bad"} />
                <Text style={styles.endpoint}>{state?.endpoint || "Nenhum endpoint"}</Text>
                <Text style={styles.meta}>
                  {state?.reachable
                    ? `Via ${state.source} · FlowCore ${state.version ?? ""}`
                    : state?.error ?? "Falha de conexão"}
                </Text>
                
                {!state?.reachable && (
                  <TouchableOpacity onPress={runDiagnostic} style={styles.diagnosticButton}>
                    <Text style={styles.diagnosticButtonText}>
                      {diagnosing ? "Testando..." : "[ TESTAR CONEXÃO ]"}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>
            )}
          </SectionCard>

          {showDiagnostic && state?.diagnostic && (
            <SectionCard title="Diagnóstico Completo" accent="#20C6D8">
              {renderComponentStatus(state.diagnostic.internet)}
              {renderComponentStatus(state.diagnostic.dns)}
              {renderComponentStatus(state.diagnostic.cloudflare)}
              {renderComponentStatus(state.diagnostic.tailscale)}
              {renderComponentStatus(state.diagnostic.z3Private)}
              {renderComponentStatus(state.diagnostic.flowcorePublic)}
              {renderComponentStatus(state.diagnostic.flowcorePrivate)}
              
              {state.diagnostic.exitNodeActive && (
                <View style={styles.exitNodeWarning}>
                  <Text style={styles.exitNodeIcon}>⚠️</Text>
                  <Text style={styles.exitNodeText}>
                    {state.diagnostic.exitNodeBreakingInternet
                      ? "Exit Node Tailscale está alterando a rota da internet"
                      : "Exit Node Tailscale detectado"}
                  </Text>
                </View>
              )}
            </SectionCard>
          )}

          <SectionCard title="Preferência de rota">
            <View style={styles.choiceRow}>
              {preferences.map((item) => (
                <TouchableOpacity
                  key={item.value}
                  onPress={() => setSettings((current) => ({ ...current, preference: item.value }))}
                  style={[styles.choice, settings.preference === item.value && styles.choiceActive]}
                >
                  <Text style={[styles.choiceText, settings.preference === item.value && styles.choiceTextActive]}>
                    {item.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={styles.preferenceHint}>
              {settings.preference === "auto" && "Testa privado primeiro, depois usa público se necessário."}
              {settings.preference === "tailscale" && "Usa apenas a rota Tailscale. Se falhar, tenta público."}
              {settings.preference === "cloudflare" && "Usa apenas Cloudflare, ignora rota privada."}
            </Text>
          </SectionCard>

          <SectionCard title="Endpoints">
            <Text style={styles.inputLabel}>Cloudflare público</Text>
            <TextInput
              value={settings.publicUrl}
              onChangeText={(value) => update("publicUrl", value)}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              style={styles.input}
              placeholderTextColor="#6E86A5"
            />

            <Text style={styles.inputLabel}>Tailscale privado</Text>
            <TextInput
              value={settings.privateUrl}
              onChangeText={(value) => update("privateUrl", value)}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              style={styles.input}
              placeholder="https://nome-do-dispositivo.tailnet.ts.net"
              placeholderTextColor="#6E86A5"
            />
            
            <Text style={styles.hint}>
              Hostname sugerido: moto-z3-play.tail9eed6.ts.net{"\n"}
              IP Tailscale: 100.111.64.81
            </Text>
          </SectionCard>

          <TouchableOpacity onPress={persist} disabled={saving} style={[styles.button, saving && styles.buttonDisabled]}>
            <Text style={styles.buttonText}>
              {saving ? "Testando…" : "Salvar e testar conexão"}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={runDiagnostic} disabled={diagnosing} style={[styles.buttonSecondary, diagnosing && styles.buttonDisabled]}>
            <Text style={styles.buttonSecondaryText}>
              {diagnosing ? "Executando diagnóstico..." : "Executar diagnóstico completo"}
            </Text>
          </TouchableOpacity>

          <Text style={styles.footnote}>
            O aplicativo não guarda token do Cloudflare nem credencial do Tailscale. 
            Somente URLs de endpoints autorizados são armazenadas localmente.
          </Text>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  scrollView: { flex: 1 },
  content: { paddingVertical: 16, gap: 14 },
  heading: { color: "#EAF2FB", fontSize: 30, lineHeight: 36, fontWeight: "800" },
  subtitle: { color: "#9CB0C9", fontSize: 14, lineHeight: 20, marginBottom: 8 },
  status: { gap: 8 },
  endpoint: { color: "#EAF2FB", fontSize: 14, lineHeight: 20, fontWeight: "700" },
  meta: { color: "#9CB0C9", fontSize: 12, lineHeight: 18 },
  
  diagnosticButton: {
    marginTop: 8,
    paddingVertical: 10,
    paddingHorizontal: 16,
    backgroundColor: "#123247",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#20C6D8",
    alignItems: "center"
  },
  diagnosticButtonText: {
    color: "#20C6D8",
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "700",
    letterSpacing: 0.5
  },
  
  diagnosticRow: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#1A2F4A",
    gap: 4
  },
  diagnosticLabel: {
    color: "#9CB0C9",
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "600"
  },
  diagnosticRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  diagnosticIcon: {
    fontSize: 14,
    lineHeight: 14
  },
  diagnosticStatus: {
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "700"
  },
  diagnosticDetails: {
    color: "#7893B5",
    fontSize: 11,
    lineHeight: 15,
    marginTop: 2
  },
  
  exitNodeWarning: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "#2A1F0A",
    padding: 12,
    borderRadius: 10,
    marginTop: 12,
    borderWidth: 1,
    borderColor: "#F0B94B"
  },
  exitNodeIcon: {
    fontSize: 18,
    lineHeight: 18
  },
  exitNodeText: {
    color: "#F0B94B",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "600",
    flex: 1
  },
  
  choiceRow: { flexDirection: "row", gap: 8 },
  choice: { flex: 1, borderWidth: 1, borderColor: "#223A58", backgroundColor: "#0E1A2A", borderRadius: 12, paddingVertical: 10, alignItems: "center" },
  choiceActive: { borderColor: "#20C6D8", backgroundColor: "#123247" },
  choiceText: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, fontWeight: "700" },
  choiceTextActive: { color: "#20C6D8" },
  preferenceHint: { color: "#7893B5", fontSize: 11, lineHeight: 15, marginTop: 8, textAlign: "center" },
  
  inputLabel: { color: "#9CB0C9", fontSize: 12, lineHeight: 16, fontWeight: "700", marginTop: 6, marginBottom: 5 },
  input: { color: "#EAF2FB", fontSize: 13, lineHeight: 19, borderColor: "#223A58", borderWidth: 1, borderRadius: 12, backgroundColor: "#0E1A2A", paddingHorizontal: 12, paddingVertical: 11 },
  hint: { color: "#7893B5", fontSize: 11, lineHeight: 15, marginTop: 8, fontStyle: "italic" },
  
  button: { minHeight: 48, backgroundColor: "#20C6D8", borderRadius: 14, alignItems: "center", justifyContent: "center", marginTop: 8 },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: "#08111F", fontSize: 15, lineHeight: 20, fontWeight: "800" },
  
  buttonSecondary: { 
    minHeight: 44, 
    backgroundColor: "transparent", 
    borderRadius: 14, 
    alignItems: "center", 
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#223A58",
    marginTop: 8
  },
  buttonSecondaryText: { color: "#20C6D8", fontSize: 14, lineHeight: 19, fontWeight: "700" },
  
  footnote: { color: "#7893B5", fontSize: 12, lineHeight: 18, textAlign: "center", paddingHorizontal: 10, marginTop: 16 }
});
