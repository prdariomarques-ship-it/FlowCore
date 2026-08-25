# Bots Telegram — estado e operação

## O que está versionado

O repositório contém a integração de envio em `runtime/telegram.py`, que consulta exclusivamente as variáveis de ambiente `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Também existe a rota `GET /api/telegram/chats`, em `api/router.py`, que lê o resumo local de chats de `~/.flowcore/telegram.json` sem expor token.

O script `tools/boot.sh` já inicia todos os scripts executáveis com extensão `.sh` presentes em `~/.flowcore/bots/`. Cada script recebe um loop próprio de reinício e grava saída em `~/.config/flowcore/<nome-do-bot>.log`.

## O que não está versionado

Não há, no Git, implementação de bot baseada em `aiogram`, `python-telegram-bot` ou `telebot`, nem há scripts de bot específicos. Logo, os três bots usados anteriormente estão no Termux ou em outro ambiente, e não podem ser reconstruídos a partir deste repositório sem os respectivos scripts e configurações privadas.

## Como registrar um bot existente no Termux

Crie ou copie o script privado do bot para `~/.flowcore/bots/<nome>.sh`, torne-o executável e mantenha token e chat ID fora do repositório. Um formato seguro é carregar variáveis de um arquivo com permissão restrita e iniciar o programa do bot.

```bash
mkdir -p ~/.flowcore/bots ~/.flowcore/private
chmod 700 ~/.flowcore/bots ~/.flowcore/private

# O arquivo do bot deve ser criado por você no celular e conter somente referências
# a variáveis; não cole tokens no Git, em chats ou em documentação.
chmod 700 ~/.flowcore/bots/<nome>.sh
```

Depois, reinicie o boot do FlowCore ou o telefone. Para diagnosticar um bot específico, consulte:

```bash
tail -n 100 ~/.config/flowcore/<nome>.log
```

## Verificação segura

No Termux, sem revelar credenciais, os comandos abaixo mostram quais scripts estão disponíveis e se há processos em execução:

```bash
find ~/.flowcore/bots -maxdepth 1 -type f -name '*.sh' -printf '%f\n'
pgrep -af 'python|telegram|bot' || true
```

Um bot somente deve ser marcado como funcional após aparecer como processo ativo e apresentar em seu próprio log uma inicialização bem-sucedida. A ausência de script, processo ou log é um estado de **não configurado**, e não uma falha disfarçada.
