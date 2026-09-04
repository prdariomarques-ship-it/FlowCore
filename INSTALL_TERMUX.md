# Instalar FlowCore no Android (Termux)

URL pública: **https://flowcore.admissaoazusa.com.br**

> Copie e cole os comandos diretamente no Termux.

---

## 1. Pacotes Termux necessários

```bash
pkg update
pkg install python git openssl curl cloudflared libxml2 libxslt clang pkg-config
```

**Capacidades Android (TTS, SMS, Contatos)** — requer o app Termux:API instalado pela F-Droid:

```bash
pkg install termux-api
```

---

## 2. Clonar o repositório

```bash
git clone https://github.com/prdariomarques-ship-it/FlowCore.git ~/FlowCore
cd ~/FlowCore
git checkout claude/flowcore-architecture-consolidation-h95fi2
pip install -r requirements-core.txt -r requirements-api.txt
```

---

## 3. Iniciar o FlowCore

```bash
python3 flowcore.py serve
```

Verificar:

```bash
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/market/snapshot
```

---

## 4. Cloudflare Tunnel (URL permanente)

O túnel nomeado "núcleo de fluxo" expõe o FlowCore em:
`https://flowcore.admissaoazusa.com.br`

### 4.1. Salvar o token

```bash
mkdir -p ~/.config/cloudflared
echo 'TUNNEL_TOKEN=<cole_o_token_aqui>' > ~/.config/cloudflared/tunnel-token
chmod 600 ~/.config/cloudflared/tunnel-token
```

Obter o token em: **Cloudflare Zero Trust → Redes → Túneis → núcleo de fluxo → Configurar → Token**

### 4.2. Testar o túnel manualmente

```bash
source ~/.config/cloudflared/tunnel-token
cloudflared tunnel run --token "$TUNNEL_TOKEN"
```

Em outro terminal, verificar:

```bash
curl https://flowcore.admissaoazusa.com.br/api/health
curl https://flowcore.admissaoazusa.com.br/api/market/snapshot
```

---

## 5. Auto-start com Termux:Boot

Instale o app **Termux:Boot** pela F-Droid e abra-o uma vez para ativar.

```bash
mkdir -p ~/.termux/boot
cp ~/FlowCore/tools/boot.sh ~/.termux/boot/flowcore.sh
chmod 700 ~/.termux/boot/flowcore.sh
```

O script `tools/boot.sh` inicia automaticamente ao ligar o celular:
- FlowCore na porta 8080 (com loop de reinício)
- Bots de Telegram em `~/.flowcore/bots/*.sh`
- cloudflared após o FlowCore responder no health check

**Isenção de bateria (obrigatório):** Configurações → Aplicativos → Termux → Bateria → Sem restrições.
Fazer o mesmo para Termux:Boot.

---

## 6. Bots de Telegram

Cada bot é um script `.sh` executável em `~/.flowcore/bots/`:

```bash
mkdir -p ~/.flowcore/bots
cat > ~/.flowcore/bots/meubot.sh <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
# Token em variável de ambiente ou arquivo privado — nunca no repositório
exec python3 ~/caminho/do/bot.py
EOF
chmod +x ~/.flowcore/bots/meubot.sh
```

O `boot.sh` inicia cada bot e o reinicia automaticamente se ele cair.

---

## 7. Configurar provedor de IA (Hermes/Nemotron)

Se o Hermes Agent estiver rodando no PC com Windows (API OpenAI-compatível):

```bash
curl -s -X PATCH http://127.0.0.1:8080/api/ai-runtime/config \
  -H "Content-Type: application/json" \
  -d '{"openai_url":"http://IP_DO_PC:PORTA","openai_model":"nemotron-3.5-lightning"}'
```

Substituir `IP_DO_PC` pelo IP privado do computador no Tailscale ou pelo IP local na mesma rede Wi-Fi. A API salva essa configuração em `~/.flowcore/ai.json`; tokens ou chaves do provedor não devem ser inseridos nesse arquivo ou nesta documentação.

Verificar a configuração sem exibir credenciais:

```bash
curl -s http://127.0.0.1:8080/api/ai-runtime/config
```

---

## 8. Capacidades Android

Disponíveis após instalar o Termux:API:

| Endpoint | Descrição |
|---|---|
| `POST /api/android/tts` | Falar texto em voz alta (`{"text":"Olá"}`) |
| `GET /api/android/sms` | Ler caixa de entrada de SMS |
| `POST /api/android/sms` | Enviar SMS (`{"number":"+55...","message":"..."}`) |
| `GET /api/android/contacts` | Listar ou buscar contatos (`?q=nome`) |

---

## 9. Logs

```bash
tail -f ~/.config/flowcore/flowcore.log
tail -f ~/.config/flowcore/cloudflared.log
tail -f ~/.config/flowcore/boot.log
```

---

## 10. Atualizar FlowCore

```bash
cd ~/FlowCore
git fetch origin
git checkout claude/flowcore-architecture-consolidation-h95fi2
git pull --ff-only origin claude/flowcore-architecture-consolidation-h95fi2
pip install -r requirements-core.txt -r requirements-api.txt
# Reiniciar: matar o processo e deixar o boot.sh relançar, ou
pkill -f 'flowcore.py serve' && python3 flowcore.py serve &
```

---

## Desinstalar

```bash
pkill -f 'flowcore.py serve'
pkill -f cloudflared
rm -rf ~/.termux/boot/flowcore.sh
# Repositório: rm -rf ~/FlowCore  (mantém ~/.config/flowcore e ~/.flowcore)
```
