# FlowCore Android

Aplicação Android para consultar a API local do FlowCore. Ela usa o mesmo contrato do dashboard web e as rotas atuais `/api/*`.

## Pré-requisitos

O backend precisa estar iniciado no Termux ou na máquina que hospeda o FlowCore:

```bash
cd ~/FlowCore
python3 flowcore.py serve
```

A porta padrão do FlowCore é `8080`. Para acesso por outro aparelho na rede, o servidor precisa escutar na interface LAN, por exemplo com `FLOWCORE__API__HOST=0.0.0.0`, e o firewall deve permitir a porta somente na rede confiável.

## Configuração dentro do aplicativo

A tela inicial agora possui o campo **Endereço do FlowCore**. Digite o endereço, toque em **Salvar endereço** e depois em **Testar conexão**. O valor é salvo no aparelho e continua disponível nas próximas aberturas.

| Cenário | Endereço |
|---|---|
| Termux no mesmo aparelho | `http://127.0.0.1:8080` |
| Emulador Android | `http://10.0.2.2:8080` |
| Outro aparelho na mesma LAN | `http://<ip-da-maquina>:8080` |

Os botões **Celular / Termux**, **Emulador** e **Rede local** ajudam a selecionar o cenário. No modo **Rede local**, informe o IP do computador, por exemplo `http://192.168.1.50:8080`.

> `127.0.0.1` significa o próprio aparelho Android. Use esse endereço somente quando o FlowCore estiver rodando no Termux do mesmo celular.

Quando a conexão falha, o app informa o endereço usado e mostra uma dica diferente para `127.0.0.1` e para um host da rede. HTTP é permitido apenas para desenvolvimento local; antes de exposição externa, use HTTPS.

## Build e instalação

Com Android SDK, JDK 21 e `sdk.dir` configurados:

```bash
./android/gradlew -p android assembleDebug
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

O APK de debug é gerado em `android/app/build/outputs/apk/debug/app-debug.apk`.

## Verificações disponíveis

O app consulta `GET /api/status`, `GET /api/system`, `GET /api/health` e `GET /api/passport`. A ação “Diagnóstico” usa o bloco `doctor` retornado por `/api/status`, pois não existe uma rota independente `/api/doctor` na API atual.

## Validação

O contrato Android é verificado por:

```bash
python3 -m pytest -q tests/test_android_app_contract.py
```

A melhoria de configuração foi compilada em `FlowCore-android-improved.apk` após os testes de contrato passarem.
