# FlowCore Android

Aplicação Android para consultar a API local do FlowCore. Ela usa o mesmo contrato do dashboard web e as rotas atuais `/api/*`.

## Pré-requisitos

O backend precisa estar iniciado no Termux ou na máquina que hospeda o FlowCore:

```bash
cd ~/FlowCore
python3 flowcore.py serve
```

A interface principal do dashboard/API usa a porta `8080`. Alguns ambientes de validação e proxy protegido usam a porta `8090` com o header `X-FlowCore-Token`.

## Configuração dentro do aplicativo

A tela inicial possui o campo **Endereço do FlowCore**. Digite o endereço, toque em **Salvar endereço** e depois em **Testar conexão**. O endereço base é salvo no aparelho e continua disponível nas próximas aberturas.

| Cenário | Endereço |
|---|---|
| Termux no mesmo aparelho | `http://127.0.0.1:8080` |
| Emulador Android | `http://10.0.2.2:8080` |
| Outro aparelho na mesma LAN | `http://<ip-da-maquina>:8080` |
| Proxy protegido local | `http://127.0.0.1:8090` |

Os botões **Celular / Termux**, **Emulador**, **Rede local** e **Usar proxy protegido · porta 8090** ajudam a selecionar o cenário. No modo **Rede local**, informe o IP do computador, por exemplo `http://192.168.1.50:8080`.

> `127.0.0.1` significa o próprio aparelho Android. Use esse endereço somente quando o FlowCore estiver rodando no Termux do mesmo celular. Se o servidor estiver no PC, use o IP do PC na rede local.

## Token da API

O campo **Token da API** é opcional e fica apenas em memória durante a sessão do app. Ele não é salvo em SharedPreferences, não aparece no output e só é enviado como `X-FlowCore-Token` quando preenchido.

Use o token apenas para o endpoint protegido, normalmente em `8090`. Para o dashboard/API local em `8080`, deixe o campo vazio se o ambiente não exigir autenticação. Nunca coloque um token real em código-fonte, screenshot, comando literal ou arquivo versionado.

Quando a API retornar `401`, o app informa que o token está ausente ou inválido. Quando houver falha de conexão, ele mostra uma dica diferente para loopback, proxy 8090 e endereço de rede.

## Acesso por rede local

Para acessar o FlowCore a partir de outro aparelho, o servidor precisa escutar na interface LAN, por exemplo com `FLOWCORE__API__HOST=0.0.0.0`, e o firewall deve permitir a porta somente na rede confiável. HTTP é apropriado apenas para desenvolvimento local; antes de exposição externa, use HTTPS e uma política de autenticação adequada.

## Build e instalação

Com Android SDK, JDK 21 e `sdk.dir` configurados:

```bash
./android/gradlew -p android assembleDebug
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

O APK de debug é gerado em `android/app/build/outputs/apk/debug/app-debug.apk`.

## Verificações disponíveis

O app consulta `GET /api/status`, `GET /api/system`, `GET /api/health` e `GET /api/passport`. A ação “Diagnóstico” usa o bloco `doctor` retornado por `/api/status`, pois não existe uma rota independente `/api/doctor` na API atual.

A branch de Market Intelligence também contém `POST /api/telegram/briefing`, `POST /api/outlook/auth/start` e `GET /api/outlook/auth/status`. Esses fluxos não são disparados automaticamente pelo app Android atual, pois envolvem credenciais e autorização externa; devem ser executados pelo dashboard ou por um cliente administrativo autenticado.

## Validação

O contrato Android é verificado por:

```bash
python3 -m pytest -q tests/test_android_app_contract.py
```

A melhoria de configuração e proxy protegido deve ser validada novamente antes de distribuir o APK.
