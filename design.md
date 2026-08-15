# Teólogos Chat — Plano de Interface

## Direção visual

O Teólogos Chat terá uma linguagem visual de biblioteca teológica: fundo azul-marinho quase preto, superfícies em azul-petróleo profundo, acentos em dourado envelhecido e texto marfim. A experiência deve lembrar uma sala de leitura clássica, sem parecer pesada. A navegação prioriza o alcance do polegar, cards altos e ações primárias na metade inferior da tela. A interface usa fontes serifadas para nomes, períodos e mensagens do pensador, combinadas com uma sans-serif discreta para rótulos e controles.

## Telas

| Tela | Conteúdo e função |
|---|---|
| Início | Cabeçalho com “Teólogos Chat”, subtítulo explicativo, indicador de catálogo e lista vertical de períodos em cards. Cada card exibe número de pensadores, período e uma frase-resumo. |
| Período | Cabeçalho com voltar, nome e descrição do período, seguido de lista de teólogos em cards com nome serifado, datas, tradição/ênfase e botão implícito de seleção. |
| Chat | Cabeçalho com avatar monogramático, nome do teólogo, período e ação para voltar. Área de mensagens com balões distintos para usuário e pensador, estado de carregamento e aviso de contextualização histórica. Campo de texto fixado na base com botão de envio. |
| Estado vazio/erro do chat | Mensagem clara sobre falha de conexão ou ausência de texto, com ação para tentar novamente. |

## Fluxos principais

1. O usuário abre a tela inicial e percorre os períodos disponíveis.
2. O usuário toca em um período; o app navega para a tela do período e apresenta os teólogos associados.
3. O usuário toca em um teólogo; o app abre o chat com uma saudação inicial contextualizada.
4. O usuário escreve uma pergunta e toca em enviar; a mensagem aparece imediatamente, o campo é limpo e o app mostra um indicador de resposta.
5. O cliente envia ao backend o identificador do teólogo e o histórico da conversa; o backend monta o system prompt contextualizado e chama a API da OpenAI sem expor a chave no dispositivo.
6. A resposta do pensador aparece no balão do assistente. Se houver falha, o usuário pode tentar novamente.

## Cores

| Token | Cor | Uso |
|---|---|---|
| ink | `#0B1720` | Fundo principal |
| midnight | `#122733` | Superfícies e cabeçalhos |
| slate | `#1B3540` | Cards e campo de mensagem |
| parchment | `#F4EBDD` | Texto principal e mensagens do pensador |
| mutedParchment | `#B7B7AA` | Texto secundário |
| antiqueGold | `#C99A4A` | Ações, divisores e destaque |
| terracotta | `#B86B52` | Pequenos estados de atenção |
| userBubble | `#294E5B` | Balão do usuário |

## Tipografia e interação

Nomes de teólogos e títulos usam uma serifada editorial; rótulos, metadados e controles usam uma sans-serif legível. Os cards possuem feedback de opacidade e leve escala ao toque. O botão de envio fica sempre acessível junto ao teclado. Listas longas usam `FlatList`, e todas as telas usam o contêiner de área segura do template.
