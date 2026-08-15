# FlowCore Android

Aplicação Android mínima para consultar a API local do FlowCore. Ela usa o mesmo contrato do dashboard web e foi alinhada às rotas atuais `/api/*`.

## Pré-requisitos

O backend precisa estar iniciado no Termux ou na máquina que hospeda o FlowCore:

```bash
cd ~/FlowCore
python3 flowcore.py serve
```

A configuração padrão escuta em `127.0.0.1:8080`.

## Endereço do backend

O endereço é definido em `android/app/build.gradle.kts` por `FLOWCORE_BASE_URL`:

| Cenário | Valor |
|---|---|
| Termux no mesmo aparelho | `http://127.0.0.1:8080` |
| Emulador Android | `http://10.0.2.2:8080` |
| Outro aparelho na mesma LAN | `http://<ip-da-maquina>:8080` |

Para o último cenário, o FlowCore precisa aceitar conexões na LAN, por exemplo com `FLOWCORE__API__HOST=0.0.0.0`, e o firewall deve liberar a porta 8080 apenas na rede confiável. O app usa HTTP apenas para desenvolvimento local; antes de exposição externa, use HTTPS.

## Build e instalação

Com Android SDK, JDK 21 e `sdk.dir` configurados:

```bash
./android/gradlew -p android assembleDebug
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

O APK de debug é gerado em `android/app/build/outputs/apk/debug/app-debug.apk`.

## Verificações disponíveis

O app consulta `GET /api/status`, `GET /api/system`, `GET /api/health` e `GET /api/passport`. A ação “Diagnóstico” usa o bloco `doctor` retornado por `/api/status`, pois não existe uma rota independente `/api/doctor` na API atual.
