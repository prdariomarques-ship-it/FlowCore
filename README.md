# FlowCore

```bash
git clone https://github.com/prdariomarques-ship-it/FlowCore.git
cd FlowCore
./install.sh
python3 flowcore.py version
```

## Dois clones, dois branches -- não misture

Este repositório tem duas linhas de trabalho ativas e um único diretório
compartilhado entre elas já causou incidentes reais em produção (um merge
de `main` para dentro do branch de deploy apagou autenticação, cadastro
de clientes e outras features por alguns minutos -- ver o histórico de
commits de reversão em `claude/dario-os-platform-gcg6i2`).

| Clone (Termux) | Branch | Uso |
|---|---|---|
| `~/FlowCore` | `claude/dario-os-platform-gcg6i2` | **Produção.** É o que `deploy/restart.sh` e `~/.termux/boot/flowcore.sh` rodam. Só `git pull` deste branch aqui -- nunca `checkout main` ou `merge main` neste diretório. |
| `~/FlowCore-main` | `main` | Trabalho separado no branch `main` (legado/experimental). Clone independente: `git clone https://github.com/prdariomarques-ship-it/FlowCore.git ~/FlowCore-main && cd ~/FlowCore-main && git checkout main`. |

Se uma sessão precisar trabalhar em `main`, faça isso em `~/FlowCore-main`,
nunca em `~/FlowCore`. `deploy/restart.sh` já foi corrigido para puxar
sempre o branch que estiver checked out no clone onde roda (em vez de um
`main` fixo), mas isso não substitui manter os dois diretórios separados.
