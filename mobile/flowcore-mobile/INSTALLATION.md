# Instalação — FlowCore Mobile e rede privada

## 1. Atualizar o FlowCore do Termux

O APK consome a mesma camada de mercado usada pelo briefing e pelos bots Telegram. Antes de instalar o aplicativo, atualize o clone do celular para o commit que inclui a inteligência de mercado compartilhada.

```bash
cd ~/FlowCore
git fetch origin
git checkout claude/flowcore-architecture-consolidation-h95fi2
git pull --ff-only origin claude/flowcore-architecture-consolidation-h95fi2
python3 -m pip install --upgrade -r requirements-api.txt
mkdir -p ~/.termux/boot
cp tools/boot.sh ~/.termux/boot/flowcore.sh
chmod 700 ~/.termux/boot/flowcore.sh
```

Depois, reinicie pelo fluxo já adotado no telefone. A verificação deve responder com dados reais ou estados explícitos de indisponibilidade.

```bash
curl -s https://flowcore.admissaoazusa.com.br/api/market/overview
curl -s https://flowcore.admissaoazusa.com.br/api/market/briefing
```

## 2. Gerar e instalar o APK

Depois de salvar uma versão do projeto mobile, use o botão **Publish** da interface do projeto para iniciar a geração do APK. O processo de publicação é o caminho suportado para criar o artefato Android; ele evita uma compilação manual pesada no ambiente local. Instale o APK no Android e abra a aba **Conexão**.

O endpoint Cloudflare público padrão é `https://flowcore.admissaoazusa.com.br`. O aplicativo não incorpora token do Cloudflare, token Telegram ou credencial do Tailscale.

## 3. Adicionar o novo computador ao Tailscale

No novo computador, instale o cliente Tailscale pelo canal oficial e entre usando a mesma identidade autorizada no tailnet. Um novo dispositivo é adicionado ao tailnet depois da autenticação; se a aprovação de dispositivos estiver habilitada, ele aparecerá como **Needs approval** no painel Machines e precisará ser aprovado por uma conta com papel Owner, Admin ou IT admin [1] [2].

| Etapa | Onde executar | Resultado esperado |
|---|---|---|
| Instalar o cliente | Novo computador | Cliente Tailscale instalado para o sistema operacional correto. |
| Entrar no tailnet | Cliente Tailscale do novo computador | Dispositivo aparece no painel Machines. |
| Aprovar, se necessário | [Machines](https://console.tailscale.com/admin/machines) | O estado deixa de ser **Needs approval**. |
| Testar a rota privada | Novo computador | A URL privada do FlowCore responde a `/api/health`. |
| Configurar o APK | Aba **Conexão** | Inserir somente a URL privada; preferir **Privado** ou **Automático**. |

Evite copiar chaves de autenticação para o APK, repositório, chats ou arquivos de configuração compartilhados. Para um computador pessoal, o login interativo e a aprovação no painel são preferíveis a chaves de automação. Depois do cadastro, registre uma URL privada HTTPS do FlowCore na aba **Conexão** do aplicativo; o app testará primeiro a rota privada quando selecionada e voltará ao Cloudflare em caso de falha.

## 4. Arquitetura de conexão

| Camada | Papel | Exposição |
|---|---|---|
| FlowCore no Termux | Coleta de mercado, carteira, briefing e bots Telegram | Serviço local em `127.0.0.1:8080`. |
| Cloudflare Tunnel | Endpoint HTTPS público para o aplicativo em trânsito | `flowcore.admissaoazusa.com.br`. |
| Tailscale | Caminho privado entre dispositivos autorizados | URL/IP privado configurado pelo operador. |
| FlowCore Mobile | Leitura de mercado, carteira, IA e estado de conexão | APK Android, sem executar ordens. |

## Referências

[1]: https://tailscale.com/docs/features/access-control/device-management/how-to/set-up "Tailscale — Add a device"
[2]: https://tailscale.com/docs/features/access-control/device-management/device-approval "Tailscale — Device approval"
