# Radar Artecon — v0.8.0

Plataforma de Inteligência Contábil e Tributária — Fase 1 enxuta.

Esta versão entrega a Fase 1 enxuta completa: o **banco**, os **coletores das fontes
oficiais**, as **telas** (dashboard de curadoria) e a
**inteligência artificial** (OpenAI) para sugerir classificação, buscar trechos de
fundamentação e redigir rascunhos.

A v0.4.0 acrescenta o **Informativo Mensal** no padrão enviado aos clientes (agenda de
obrigações, artigos, Fale Conosco e fecho, no papel timbrado, pronto para salvar em PDF),
**imagem de capa, autor e fonte** nos conteúdos, e os botões para **copiar a notícia para o
site** da Artecon. É o modo de trabalho até a parte oficial (robô e fontes) estar validada.

A v0.8.0 tira trabalho manual e aumenta o alcance, sem enxurrada de avisos:

- **Publicação no site registrada sozinha** (o robô acha a notícia em artecon.cnt.br/news) e aviso quando
  o texto do site deixa de bater com o aprovado.
- **Para o site** com passos numerados e a categoria do site indicada.
- **Resumo semanal**: um único e-mail por semana com o mais relevante, agrupado por tema.
- **Diário Oficial completo pelo INLABS** (Receita, PGFN, CGSN e CGIBS), desligado até o cadastro.
- **Nota da IA na relevância** e fontes novas (DOU Destaques, Econet, Portal Contábil SC, boletim da ITC).
- **Limpeza** da antiga publicação dentro do Radar.

Mudam o banco (`radar-setup-v0.8.0.sql`), o robô e o `index.html`. A função `radar-ia` **não muda**.

A v0.7.1 é de manutenção e conforto, sem mudar o jeito de trabalhar:

- **Texto não salvo não se perde**: o que foi digitado num conteúdo fica guardado no navegador até
  ser salvo; se a sessão cair, aparece "Recuperar o texto não salvo".
- **Listas longas com "Mostrar mais"** em vez de cortar nos itens mais recentes.
- **Robô**: cada fonte tem até 5 minutos por coleta, e as imagens sem uso são apagadas ao fim de cada coleta.
- **Aviso por e-mail de fonte com falha**: depois de 3 falhas seguidas, o robô abre um aviso (issue)
  no repositório do GitHub, e o GitHub manda e-mail ao dono do repositório; o aviso fecha sozinho
  quando a fonte volta ou é desligada (veja "Fontes: cadastrar e ajustar").
- **Diagnóstico** confere as fontes ativas do banco e explica a página que não reconheceu.
- Regras de relevância aceitam termos com pontuação ("S.A.", "Ltda."); número da nova edição segue o ano
  do mês; lembrete de capa desatualizada quando o título muda; rotinas do GitHub em Node 24.

Mudam o banco (`radar-setup-v0.7.1.sql`), o robô e o `index.html`. A função `radar-ia` **não muda**.

A v0.7.0 reduz o volume e a repetição e simplifica o trabalho:

- **Só o que está em alta.** Depois de cada coleta, o robô pede à IA uma nota de 0 a 10 para cada
  captura nova (pelo título e pelo resumo) e a tela de Capturas abre com as 10 melhores.
- **Sem repetição.** A IA aponta quando duas capturas tratam do mesmo fato; as repetições ficam
  recolhidas atrás de uma delas (o cartão diz quantas são) e entram junto no assunto. Só vai junto
  o que o cartão anuncia; se a IA juntar errado, o botão "Não é o mesmo fato" desfaz.
- **Fonte já preenchida** no conteúdo, com o órgão da captura oficial.
- **Texto nunca copiado.** A IA redige com palavras próprias e o Radar compara o texto com a
  fonte: trecho de 12 palavras ou mais igual impede a aprovação (citação curta entre aspas é aceita).
- **Texto justificado** na prévia, no texto copiado para o site e no Informativo.
- **Imagens realistas**, com pessoas fictícias quando fizer sentido, sem texto, marca,
  assinatura nem estilo de autor; campo opcional para dizer como você quer a imagem.
- **Assunto por etapas**: Fonte e fundamentação, Conteúdo e Classificação, uma de cada vez.

Mudam o banco (`radar-setup-v0.7.0.sql`), o robô, a função `radar-ia` e o `index.html`.

A v0.6.1 ligou a IA do Radar à **IA Central do Portal Artecon**: texto pela Anthropic, imagens
pela OpenAI, custo e limites no Portal → Consumo de IA. Mudam só o `index.html` e a função
`radar-ia`; o banco e o robô são os da v0.6.0.

A v0.6.0 trata de quatro coisas: **filtro de relevância** das capturas (a triagem abre só
com o que interessa ao escritório), telas de **Capturas e Assunto mais simples** (cartões,
cinco passos e "Próximo passo"), **imagem de capa automática** em todo conteúdo e o **final
do Informativo Mensal no modelo do escritório** (Fale Conosco com ícones, contadores
responsáveis, legenda e fecho). Traz também um **teste da IA** em Configurações, que diz o
que falta quando a IA não funciona.

A v0.5.0 **retira a página pública "Artecon Informa"**: as publicações são feitas nas
páginas da Artecon. O Radar passa a registrar o que foi ao site (link, data e a cópia do
texto aprovado e da fundamentação). Sem login, ninguém lê nada do banco. **A exigência de
fonte oficial não mudou**: só se registra a publicação de assunto confirmado oficialmente,
com trecho conferido em fonte oficial. Também nesta versão: **cadastro de fontes pela
tela**, inclusão de **texto oficial pela equipe**, visual no padrão da Artecon e a aba
**Como usar**.

## O que tem no pacote

| Pasta / arquivo | Para que serve |
|---|---|
| `index.html` | Dashboard de curadoria (uso interno, com login). Não há página pública. |
| `informativo.html` | Informativo Mensal para imprimir / salvar em PDF (uso interno, usa o login do dashboard). |
| `radar-logo-artecon.png` | Logotipo usado no topo do painel e na tela de entrada (recortado do timbrado). |
| `radar-timbrado-topo.png`, `radar-timbrado-rodape.png` | Papel timbrado do informativo (recortado do seu PDF). Para trocar, substitua os arquivos mantendo os nomes. |
| `radar-config.js` | Endereço do projeto Supabase e chave **anon**. Preenchido uma vez; não é substituído nas atualizações. |
| `sql/radar-setup-v0.8.0.sql` | Cria (ou atualiza) as tabelas `radar_*`, as regras e as 6 fontes iniciais. Pode ser executado mais de uma vez. |
| `sql/radar-reversao-v0.8.0.sql` | Desfaz a instalação (apaga só objetos `radar_*`). |
| `supabase/functions/radar-ia/index.ts` | Função de IA (Edge Function do Supabase). |
| `robo/` | Robô de coleta, diagnóstico das fontes e a lista de fontes. |
| `.github/workflows/` | Rotinas do GitHub Actions: diagnóstico, coleta agendada e testes. |
| `testes/` | Suíte de testes automatizados. |
| `RELATORIO-TESTES-radar.md` | O que foi testado, o que não foi e o que as revisões independentes encontraram. |

## Fontes iniciais (conferidas nos sites reais em 02/10/2026)

| Fonte | Como é lida | O que a conferência mostrou |
|---|---|---|
| Receita Federal — Notícias | página "Últimas notícias" | o feed RSS da pasta estava parado em julho; a fonte foi trocada para a página, que estava em dia |
| PGFN — Notícias | página de notícias | endereços e datas conferem |
| Simples Nacional — Notícias | página "Todas as notícias" | endereços e datas conferem |
| Receita Federal — Atos normativos | consulta por período, até 6 páginas de 100 atos | só a **ementa** é capturada: o texto integral não tem endereço direto (o sistema abre por JavaScript) |
| SEF/SC — Últimas legislações | página inicial da SEF | atos DIAT e decretos conferem; resoluções em `.doc` ficam de fora |
| Comitê Gestor do IBS — Notícias | página inicial | a lista não traz data; a data é lida do texto da notícia |

A conferência foi feita lendo os endereços, títulos e datas das páginas reais. O HTML
bruto não pôde ser baixado no ambiente de desenvolvimento, então a leitura pelo robô
(estrutura da página e extração do texto) ainda se confirma no Passo 1. Unidades regionais
da Receita (SRRF, DRF, ALF, Disit…) são filtradas por padrão; ajuste em Fontes → Configurar.
Outras fontes você mesmo cadastra na aba Fontes (veja "Fontes: cadastrar e ajustar").

O Diário Oficial da União ficou fora: o site recusou a leitura automática no teste.
O caminho previsto é o INLABS (XML oficial, exige cadastro gratuito).

## Instalação — nesta ordem

### Passo 1 — Repositório e diagnóstico das fontes (não precisa de banco nem de chave)

1. Crie o repositório `radar` no GitHub e envie o conteúdo deste zip.
   A pasta `.github` precisa ir junto. Se ela não aparecer no envio por arrastar,
   crie os três arquivos por "Add file → Create new file", digitando o caminho
   completo (`.github/workflows/radar-diagnostico.yml`) e colando o conteúdo.
2. Aba **Actions** → "Radar — diagnóstico das fontes" → **Run workflow**.
3. Ao terminar, a página da execução mostra o veredito de cada fonte e, no fim,
   o arquivo **radar-diagnostico** para baixar.
4. Envie esse arquivo de volta. Com as páginas reais, a configuração de cada fonte
   é ajustada.

### Passo 2 — Banco

1. Crie o projeto novo no Supabase.
2. **Authentication → Sign In / Providers:** desligue "Allow new users to sign up".
   Sem isso, qualquer pessoa cria conta (não ganha acesso, mas polui a lista de usuários).
3. SQL Editor → cole e execute `sql/radar-setup-v0.8.0.sql` inteiro.
4. O resultado final é a **evidência**: exporte em CSV e guarde.
   Esperado: 21 linhas de tabela, todas com `rls = true`; `fontes = 6`; `categorias = 8`;
   `instalacoes concluidas` com ao menos 1 e a versão `v0.7.1`.
   Se o script parar com erro, corrija a causa e execute de novo: ele continua de onde parou.

### Passo 3 — Chaves do robô no GitHub

Repositório → Settings → Secrets and variables → Actions → New repository secret:

| Nome | Valor |
|---|---|
| `RADAR_SUPABASE_URL` | URL do projeto (`https://xxxx.supabase.co`) |
| `RADAR_SUPABASE_SERVICE_KEY` | chave **service_role** (secreta; só aqui) |

### Passo 4 — Primeira coleta

Actions → "Radar — coleta das fontes oficiais" → Run workflow.
Depois disso ela roda sozinha a cada 6 horas.

### Passo 5 — Telas

1. Edite `radar-config.js` no repositório e preencha a URL do projeto e a chave **anon**
   (Project Settings → API). Nunca a service_role: as telas recusam e avisam.
2. Settings → Pages → publique a partir da branch principal, pasta raiz.
3. O dashboard fica em `https://SEU-USUARIO.github.io/radar/`. É de uso interno: quem não
   tem login não vê nenhum dado.

O repositório não guarda nenhum segredo: a chave anon é pública por natureza e quem
protege os dados são as regras do banco.

### Passo 6 — Primeiro administrador

Crie o seu usuário em Authentication → Users (com senha) e rode, trocando o e-mail:

```sql
insert into radar_perfis (user_id, nome, papel)
select id, 'Cleiver', 'admin' from auth.users where email = 'SEU-EMAIL';
```

Os demais usuários você cria no Supabase e libera pela aba **Usuários** do dashboard.

### Passo 7 — Inteligência artificial (pela IA Central do Portal Artecon)

Desde a v0.6.1 o Radar não guarda chave da OpenAI nem da Anthropic. Ele usa a **IA Central**
(função `ia-gateway` do projeto Departamento Pessoal): texto pela Anthropic, imagens pela OpenAI.
Custo, limites, avisos por e-mail, relatório mensal e link de recarga ficam em
**Portal → Consumo de IA**.

Pré-requisito: IA Central v1.1.0 instalada (pacote `ia-central-v1.1.0`) e Portal v1.4.0.

1. No Portal → Consumo de IA, no cartão **Radar — informativos e publicações**, clique em
   **Gerar token** e copie (começa com `iagw_radar_`; aparece uma única vez).
2. No Supabase do Radar: Edge Functions → função **`radar-ia`** (o nome precisa ser exatamente
   este) → cole o conteúdo de `supabase/functions/radar-ia/index.ts` → Deploy. Deixe ligada a
   opção de verificar o JWT.
3. Edge Functions → Secrets → crie **`IA_GATEWAY_TOKEN`** com o token do item 1. Se existir um
   `OPENAI_API_KEY` neste projeto, pode excluir: não é mais usado.
4. No Radar: **Configurações → Inteligência artificial → Testar a IA**. O teste confere a
   função, o token e os dois modelos de texto, e diz o que corrigir.
5. Abra um assunto que tenha texto oficial e clique em "Preparar com IA".

Segredos opcionais (no projeto do Radar):

| Segredo | Padrão | Para quê |
|---|---|---|
| `RADAR_IA_MODELO` | `claude-sonnet-4-6` | modelo que busca trechos e redige |
| `RADAR_IA_MODELO_RAPIDO` | `claude-haiku-4-5` | modelo que classifica |
| `RADAR_IA_MODELO_IMAGEM` | `gpt-image-2` | modelo da ilustração de capa (OpenAI) |
| `RADAR_IA_LIMITE_MENSAL_TOKENS` | `3000000` | teto de consumo por mês dentro do Radar, além dos limites em dólar da IA Central |
| `IA_GATEWAY_URL` | endereço do `ia-gateway` do projeto do DP | só muda se a IA Central mudar de projeto |

Os modelos são os que a IA Central já tem com preço cadastrado e que os outros aplicativos usam.
Para usar outro modelo, cadastre o preço em `core.ia_precos` e libere em `core.ia_apps.modelos`
do aplicativo `radar` antes de trocar o segredo; senão a IA Central recusa a chamada.

Quando a IA "não funciona", o teste do item 4 mostra a causa. As mais comuns: a função `radar-ia`
não foi criada com esse nome; falta o segredo `IA_GATEWAY_TOKEN` ou o token foi trocado no
Portal; o limite do dia ou do mês do Radar foi atingido; a conta da Anthropic ou da OpenAI está
sem crédito (o aviso chega por e-mail com o link de recarga).

## Como é o trabalho no dashboard

O mesmo passo a passo está dentro do sistema, na aba **Como usar**.

1. **Capturas:** o que o robô encontrou. "Abrir assunto" para trabalhar o item, ou "Ignorar".
2. **Assunto:** classifique (categoria, relevância, situação da confirmação).
3. **Fundamentação:** selecione o trecho no texto oficial e clique em "Usar trecho
   selecionado". O sistema diz se o trecho confere. Se o robô ainda não capturou a
   página, use "Incluir texto oficial" e cole o texto com o endereço da fonte.
4. **Conteúdo:** escreva (flash, informativo ou artigo), envie para revisão e aprove.
   Com a IA: "Sugerir classificação", "Buscar trechos" e "Gerar" produzem sugestão e
   rascunho; o texto gerado vem com a lista de "Pontos a conferir".
   O título e o texto digitados ficam guardados no navegador até serem salvos: se a sessão
   cair no meio da edição, ao abrir o conteúdo de novo aparece "Recuperar o texto não salvo".
   "Sair" com texto não salvo pede confirmação e apaga esses rascunhos do navegador.
5. **Publicação:** é feita no site da Artecon. No conteúdo aprovado, use "Copiar título",
   "Copiar texto formatado" e "Baixar imagem", publique no site e volte para informar o
   link e a data em "Registrar publicação no site". A aba **Publicações** mostra o que
   está aprovado esperando e o que já foi ao site. Conteúdo que é só do Informativo
   Mensal: clique em "Não vai ao site" para tirá-lo da fila.

### Informativo Mensal e notícias do site (sem depender do robô)

1. **Assuntos → "Novo assunto criado pela equipe":** informe o título do artigo.
2. **Novo conteúdo:** escreva o texto. Subtítulo com `## `, lista com `- `, negrito com
   `**texto**` e tabela com linhas iniciadas por `|` (a primeira é o cabeçalho). Preencha
   "Texto elaborado por" e "Fonte" se quiser, e envie a **imagem de capa** (o sistema reduz
   sozinho). Envie para revisão e aprove.
3. **Para o site da Artecon:** no conteúdo aprovado, "Copiar título", "Copiar texto
   formatado" e "Baixar imagem"; cole no editor do site e depois registre o link.
4. **Informativos → Nova edição:** número e mês. A agenda de obrigações já vem calculada.
   Confira as datas, inclua os artigos aprovados, ordene e clique em "Abrir para imprimir /
   salvar em PDF". Na janela de impressão: papel A4, margens "Nenhuma", "Gráficos de segundo
   plano" marcado. O arquivo já sai com o nome `INFORMATIVO n.º 00010-2026`.
5. **Fechar edição** quando estiver conferida; depois disso só o administrador reabre.
6. **Configurações** (administrador): lista de obrigações e regra de vencimento de cada uma,
   feriados locais, quadro do Fale Conosco e assinatura.

A agenda é uma **sugestão calculada**: considera fins de semana, feriados nacionais,
Carnaval, Sexta-feira Santa, Corpus Christi e o último dia útil do ano (sem expediente
bancário). Feriados de Palhoça e de Santa Catarina
precisam ser cadastrados em Configurações, e prorrogações oficiais de prazo são ajustadas
à mão na edição. As regras reproduzem os informativos 8, 9 e 10/2026.

No quadro do Fale Conosco vieram só os setores, os e-mails e o telefone geral. Os nomes
da equipe e os demais telefones você preenche em Configurações (ficam no banco, não no
repositório). A assinatura digital continua sendo aplicada por você no PDF.

Perfis: **leitor** só consulta; **editor** cria assuntos, escreve, aprova e registra o que
foi ao site; **administrador** também configura fontes, usuários e vê o histórico.

### Relevância das capturas (v0.6.0)

O banco dá uma nota a cada captura no momento em que ela entra, pelas regras guardadas em
**Configurações → Relevância das capturas** (`radar_config`, chave `relevancia`):

- `termos`: palavras ou expressões com `pontos` positivos (somam) ou negativos (tiram).
  No título o termo vale o dobro; no resumo e no começo do texto, os pontos simples. Só
  casa palavra inteira; maiúsculas e acentos não fazem diferença.
- `limite_alta` e `limite_media`: a partir de quantos pontos a captura é alta ou média.
  Abaixo de `limite_media` é baixa.

A tela de Capturas abre com alta e média, da maior nota para a menor; as de baixa
relevância ficam no botão "Baixa relevância", onde "Ignorar as N desta lista" tira todas da
fila de uma vez. Nada é apagado: o que foi ignorado continua em Assuntos → Ignorado. Cada
cartão mostra "Por que apareceu" (os termos que pesaram). Ao salvar as regras, as capturas
são reavaliadas. O assunto aberto a partir de uma captura herda a relevância dela. É um
filtro por palavras, não por entendimento do texto: ajuste a lista conforme o uso.

### O que está em alta e o que é repetição (v0.7.0)

Depois de cada coleta, o robô (`robo/radar_ia.py`) envia à IA, pela IA Central, o título, o resumo,
o órgão e a data das capturas novas que passaram pelo filtro de palavras (as de baixa relevância
não vão). A IA devolve, para cada uma: **nota** de 0 a 10, **motivo**, **tema** e, se for o caso,
de qual outra captura ela é **repetição**. O banco valida cada item (`radar_gravar_avaliacao_ia`).

- **Em alta** = capturas que não são repetição nem de baixa relevância, com nota a partir do corte,
  da maior para a menor. Padrão: nota de corte 6, 10 itens. Para mudar, acrescente em
  Configurações → Relevância das capturas: `"nota_corte": 7, "quantidade": 15`.
- **Repetição**: enquanto a origem está na fila, a captura repetida fica recolhida atrás dela (não
  aparece em "Em alta" nem em "Relevantes"; em "Todas" aparece com o selo). O grupo vale pela
  maior nota entre a origem e as repetições. Ao abrir ou ignorar o cartão, vão junto as repetições
  recolhidas atrás dele ("Mesmo fato em mais N capturas"). Em "Todas", abrir pela repetição leva
  a origem e as demais; ignorar a repetição ignora só ela. Se a repetição chegar depois:
  - há assunto **em andamento** com alguma captura do mesmo fato → ela entra sozinha nele, marcada como "repetição do mesmo
    fato, apontada pela IA", com registro na auditoria. O botão **Não é o mesmo fato** devolve a
    captura para a triagem (só não desfaz se já houver evidência registrada nela);
  - só há assunto **ignorado, publicado ou arquivado** → ela **não** entra sozinha: aparece na
    triagem, com cartão próprio e o aviso "Parece o mesmo fato do assunto …". Você decide: Ignorar
    ou abrir assunto novo (abrir uma não leva as outras que têm cartão próprio).
  Se a IA apontar muitas capturas do mesmo lote para a mesma origem (mais de um terço do lote,
  direto ou em cadeia), o robô trata como erro e não esconde nenhuma. Título alterado na fonte pede nova avaliação.
- **Custo**: modelo rápido (`claude-haiku-4-5`), cerca de US$ 0,01 a cada 25 capturas, registrado no
  Portal em nome de "robô de coleta", dentro dos limites do Radar.
- **Se a IA faltar** (sem crédito, limite do dia, token errado), a coleta não falha: as capturas
  ficam "aguardando nota da IA", entram em "Em alta" pela ordem das palavras e são avaliadas na
  coleta seguinte. O motivo aparece no resumo da execução, no GitHub.
- É uma avaliação por título e resumo, feita por IA: pode errar a nota ou juntar fatos diferentes.
  "Relevantes" mostra todas as de alta e média relevância (sem as repetições recolhidas) e "Todas"
  mostra tudo, inclusive as repetições e as de baixa relevância.
- O resumo da execução nunca mostra o token (`iagw_…` aparece como `iagw_***`).

### Texto original, nunca cópia (v0.7.0)

A IA recebe a regra de redigir com palavras próprias e só transcrever, entre aspas e com no máximo
25 palavras, o trecho de dispositivo legal cuja redação exata seja indispensável. Além disso, o
Radar compara cada conteúdo (escrito pela equipe ou pela IA) com o texto das capturas do assunto:
sequência de 12 palavras ou mais igual à fonte aparece num quadro vermelho e o botão Aprovar
recusa. A comparação ignora maiúsculas, acentos e pontuação. Não contam para as 12 palavras:
números, datas, nomes próprios e siglas, o nome de uma norma ("Instrução Normativa RFB nº 2.300,
de 5 de março de 2026") e as palavras de ligação entre eles ("de", "e", "na"). Citação entre aspas é aceita quando curta:
até 40 palavras cada e 120 no total do texto — pôr o texto inteiro entre aspas não adianta. O
título do conteúdo não entra na comparação.

Limites: a comparação é só com o texto capturado do próprio assunto (não com a internet nem com
outros sites de notícia), não detecta paráfrase muito próxima — quem troca uma palavra a cada
poucas escapa —, pode barrar por engano um trecho legítimo muito parecido com a fonte (basta
reescrever ou citar entre aspas) e é feita na tela: quem grava direto no banco não passa por ela. É um apoio à
revisão, não um detector de plágio. O campo **Fonte** é preenchido só na criação do conteúdo
(com os órgãos das capturas oficiais do assunto); capturas incluídas depois não o alteram.

### Assunto por etapas (v0.7.0)

A tela do assunto mostra uma etapa de cada vez: **Fonte e fundamentação** (texto oficial e
trechos), **Conteúdo** (escrever, aprovar e registrar no site) e **Classificação** (dados do
assunto). Abre na etapa que falta; os cinco passos do alto e o "Próximo passo" trocam de etapa.
Trocar de etapa não perde o que foi digitado, e uma ação feita em outra etapa (salvar a
classificação, por exemplo) também não: o que estava digitado ou escolhido e não salvo é devolvido
aos campos. Se houver um formulário de evidência ou de texto oficial aberto e preenchido em outra
etapa, a ação é barrada com o aviso de onde está a pendência.
Os passos do alto funcionam também pelo teclado. "Mostrar tudo numa página" volta ao formato
anterior e a escolha fica guardada no navegador.

### Imagem de capa (v0.6.0)

Todo conteúdo novo (escrito pela equipe ou gerado pela IA) recebe uma capa de 1200 × 630
no padrão da Artecon — logotipo, faixa, categoria e o título —, desenhada no próprio
navegador, sem depender de IA. Desde a v0.7.0 a ilustração por IA é uma fotografia realista, pode
ter pessoas (sempre fictícias) e tem um campo opcional para dizer como você quer a imagem; o pedido
proíbe texto, marca, assinatura, pessoa real e estilo de autor, e a descrição (até 200 caracteres)
é recusada, antes de gerar e de cobrar, se pedir marca, logotipo, brasão, assinatura de autor,
autoridade ou pessoa famosa, ou "no estilo de" alguém. É um filtro por palavras: não reconhece
nome de pessoa real escrito sem cargo, nem confere o título do conteúdo — por isso o pedido
enviado à OpenAI repete sempre as proibições, e a imagem deve ser conferida antes de aprovar. No conteúdo há três opções: "Gerar capa padrão Artecon"
(refaz com o título atual), "Gerar ilustração com IA" (imagem sem texto, pela OpenAI) e o
envio de uma imagem própria. Trocar a imagem de um conteúdo aprovado devolve-o à revisão.

### Fale Conosco do informativo (v0.6.0)

A última página segue o modelo do escritório. Em Configurações → Fale Conosco, cada setor
tem `nome`, `rotulo`, `telefones`, `emails`, `equipe` e, opcionalmente, `responsaveis` (com
`responsaveis_rotulo`). Telefone é um texto (telefone fixo) ou
`{"numero": "…", "whatsapp": true, "nome": "opcional"}`. O arquivo
`radar-fale-conosco-v0.6.0.json`, entregue à parte, já vem preenchido: copie o conteúdo
para o campo e salve. Ele não vai no repositório porque traz nomes e celulares da equipe.

## Regras que o banco garante

- **Fundamentação:** uma evidência só fica "conferida" se o trecho existir, literalmente,
  no texto oficial guardado. Quem calcula é o banco.
- **Aprovação:** só uma pessoa com perfil de editor ou administrador aprova. O robô e a IA
  não aprovam. Texto alterado depois de aprovado volta para revisão. A aprovação pelo
  dashboard só vale para o texto que estava na tela.
- **Registro de publicação no site:** só de conteúdo aprovado, de assunto confirmado
  oficialmente e com ao menos um trecho conferido em fonte oficial, e só se o texto ainda
  for o que estava na tela de quem registra. O registro guarda a cópia do título, do texto
  e da fundamentação;
  depois, pela tela, corrige-se só o link, e só o administrador exclui. Se o conteúdo
  mudar depois, o registro avisa. Registre logo depois de publicar: se o texto for
  corrigido e aprovado de novo antes do registro, a cópia guardada será a nova.
- **Sem leitura pública:** quem não fez login não lê nenhuma tabela do Radar.
- **IA sob controle:** a IA não aprova nem publica. Trecho proposto por ela só entra se o
  banco o encontrar, literalmente, em texto de fonte oficial do assunto. Todo texto gerado
  é rascunho e traz, calculada por código, a lista do que não aparece no texto oficial:
  número de norma, artigo, parágrafo, percentual, valor, data e prazo. O consumo fica
  registrado por usuário e tem teto mensal.
- **Informativo Mensal:** só entra conteúdo aprovado; edição fechada não muda (nem os
  artigos entram, saem ou trocam de edição) e só o administrador reabre; não fecha se algum artigo deixou de estar aprovado.
- **Imagens:** só JPG, PNG ou WebP, gravadas já reduzidas. Só a equipe lê. Trocar imagem, autor ou fonte de conteúdo aprovado devolve
  para revisão.
- **Histórico:** texto oficial que muda gera nova versão e a anterior é preservada.
- **Auditoria:** registra quem fez o quê; não pode ser alterada nem apagada.
- **Administrador:** o Radar não fica sem ao menos um administrador ativo. Por isso o
  Supabase recusa excluir o usuário que é o único administrador (o painel mostra só
  "Database error deleting user"): nomeie outro administrador antes.
- **Falha não vira silêncio:** site fora do ar, página sem itens reconhecidos ou texto
  que não pôde ser lido ficam registrados como `falha`, `vazio_suspeito` ou `parcial`.

## Decisões de projeto que vale conhecer

- Um editor pode aprovar um texto que ele mesmo escreveu (decisão sua, de 02/10/2026).
- **A fonte oficial continua obrigatória para o site** (decisão sua, de 02/10/2026: "o que
  mudou é só que não haverá página ao público"). Para o Informativo Mensal basta o
  conteúdo aprovado, como já era.
- **Texto oficial incluído pela equipe:** quando o robô ainda não capturou a página, o
  editor cola o texto e o endereço da fonte na tela do assunto. A captura fica marcada
  como "incluída pela equipe", com quem incluiu, e entra no histórico; o registro da
  publicação mostra o selo "texto incluído pela equipe" na fundamentação. O sistema confere
  se o trecho existe no texto colado, mas **não confere se o texto colado é igual ao da
  página oficial**: essa conferência é de quem inclui. Limites que o sistema impõe:
  o endereço tem de ser do site da fonte escolhida (ou de um domínio listado em
  `dominios`, nas outras opções da fonte); se o endereço já foi capturado com texto, o
  texto existente não é substituído; se o robô registrou o endereço sem conseguir ler
  (PDF, página bloqueada), o texto colado entra; se o robô capturar depois, vira nova
  versão, as evidências são reconferidas e fica anotado que o endereço entrou pela equipe.
- A IA trata o texto incluído pela equipe como texto oficial (é de fonte marcada como
  oficial): ele é enviado à OpenAI e serve de base para os "pontos a conferir".
- Qualquer evidência conferida em fonte oficial satisfaz a exigência, inclusive as
  marcadas como "interpretação técnica" ou "hipótese", e o sistema não avalia se o trecho
  tem relação com o texto escrito. Era assim na antiga publicação e continua.
- O Radar não publica nem altera nada no site da Artecon (o login do painel do site tem
  reCAPTCHA, que não deve ser contornado). Desde a v0.8.0, o robô **encontra sozinho** a notícia
  publicada em artecon.cnt.br/news e preenche o registro (link e data) quando o título e a maior
  parte do texto batem com um conteúdo aprovado sem registro; na dúvida, não registra e o
  registro manual continua valendo. Um conteúdo pode ter mais de um registro (site, rede social,
  republicação).
- A antiga página pública (`radar_publicacoes`) saiu na v0.8.0. As tabelas só são apagadas se
  estiverem vazias; uma instalação antiga com registros as mantém como arquivo, sem uso.
- Uma edição fechada do informativo aponta para os conteúdos, não guarda cópia do texto:
  o registro definitivo é o PDF que você salva e assina. Se um artigo for alterado depois
  do fechamento, a edição e a página de impressão avisam (mesmo que ele tenha sido
  aprovado de novo).
- Duas pessoas na mesma edição: quem salvar por último com a tela desatualizada recebe um
  aviso e nada é gravado por cima; é preciso recarregar e refazer a alteração.
- Imagem substituída não é apagada do banco (fica sem uso); a limpeza é do administrador.
- A coleta só deixa o workflow vermelho quando **nenhuma** fonte funciona. Falha isolada
  aparece no painel ("Fontes que pedem atenção"). Aviso por e-mail ainda não existe.
- Reexecutar o setup refaz permissões e políticas `radar_*` do zero, mas não altera dados
  nem fontes já configuradas.
- A verificação do texto gerado pela IA não lê números por extenso, incisos nem normas
  citadas sem número (CTN, CLT), e não avalia a interpretação. A revisão técnica continua
  sendo de uma pessoa.
- O teto mensal de tokens é conferido antes de cada pedido; pedidos simultâneos podem
  ultrapassá-lo um pouco. Por isso o limite de gasto na conta da OpenAI é indispensável.
- O texto oficial capturado é enviado à OpenAI para análise. Nada de dados de clientes,
  tokens ou e-mails de usuários é enviado.

## Fontes: cadastrar e ajustar sem mexer em código

Aba **Fontes** (administrador). **Nova fonte** cadastra um site; **Configurar** altera ou
exclui. O robô lê do banco todas as fontes ativas, então a fonte nova entra na coleta
seguinte (a cada 6 horas, ou em Actions → "Radar — coleta das fontes oficiais" → Run
workflow). O resultado aparece em "Últimas execuções do robô".

| Campo | O que é |
|---|---|
| Nome, órgão, abrangência, categoria | identificação; a categoria vai para os assuntos abertos a partir da fonte |
| Endereço | a página que lista as novidades |
| Como o robô lê | "Página com lista de links" (o caso comum), "Feed RSS" ou "Atos normativos da Receita" |
| Padrão dos links | o trecho que os endereços das notícias têm em comum e os links de menu não têm; é uma expressão regular (ex.: `/noticias/\d{4}/`) |
| Onde está o texto | seletor CSS do texto na página do item; em dúvida, deixe o padrão |
| Idade máxima dos itens | itens mais antigos que isso são ignorados |
| Fonte oficial | marque só para órgãos públicos: é o que permite fundamentar |
| Validada | marque depois de conferir que a fonte está lendo certo |

**Aviso por e-mail.** Quando uma fonte ativa falha 3 coletas seguidas (falha, vazio_suspeito ou
parcial), o robô abre no repositório do GitHub um aviso (issue) "Radar: fonte com falha — slug", com
o último erro e o que fazer. O GitHub manda e-mail ao dono do repositório quando o aviso é aberto
(confira em github.com → Settings → Notifications se "Issues" está com e-mail ligado). Há no máximo
um aviso aberto por fonte; ele fecha sozinho, com um comentário, quando a fonte volta a funcionar
ou é desligada. A cada coleta o robô também confere os links registrados em **Publicações no site**:
o que responder "página não encontrada" (404 ou 410) abre o aviso "Radar: link publicado fora do ar",
que fecha quando o link volta a abrir ou o registro é corrigido ou excluído. Erro de rede ou do site
(tempo esgotado, erro 500) não abre aviso, porque costuma ser passageiro.

Como ler o resultado da primeira coleta: **ok** com itens novos = funcionando;
**vazio_suspeito** = o padrão dos links não casou com nada (ajuste o padrão); **falha** =
o site não respondeu ou o cadastro está incompleto (a observação diz o motivo);
**parcial** = achou os itens, mas não leu o texto de alguns (ajuste "Onde está o texto").

Fonte que já tem capturas não é excluída: desmarque "Fonte ativa". Excluir uma fonte sem
capturas apaga junto o histórico de execuções dela. O tipo "Atos normativos da Receita" é
específico do site Normas e não aparece para fontes novas. O padrão dos links é conferido
pelo navegador; o robô usa Python, que recusa algumas construções aceitas pelo navegador
(nesse caso a execução vem como "falha", com o motivo). Cada fonte tem até 5 minutos por
coleta: passou disso (padrão muito complexo, site lento demais), a fonte é interrompida e vem
como "falha" (ou "parcial", se já tinha gravado algo), sem atrasar as outras. Para mudar o
limite, escreva em "Outras opções de leitura" `"tempo_max_segundos": 120` (de 1 a 3600). O robô acessa o endereço
cadastrado a partir do GitHub; cadastre só sites públicos. O diagnóstico
(Actions → "Radar — diagnóstico das fontes") confere as fontes **ativas** do banco, inclusive
as cadastradas pela tela; antes do Passo 3 (sem as chaves), confere as seis fontes iniciais do
arquivo `robo/radar_fontes.json`. Quando uma fonte não é reconhecida, o relatório mostra como a
página está montada (título, tabelas, links e, se ela for montada por JavaScript, os endereços
de dados que aparecem nos scripts).

Outras opções, no campo "Outras opções de leitura (JSON)":

| Chave | Efeito |
|---|---|
| `titulo_do_contexto` | usar o título do bloco em volta do link (links "Acessar") |
| `excluir_url` / `excluir_orgao` | o que ignorar |
| `revisitar_dias` | por quantos dias um item é relido para detectar alteração |
| `data_do_texto` | ler a data de publicação no texto do item, quando a lista não traz |
| `texto_do_feed` | feed RSS que já traz a notícia inteira (`content:encoded`): o texto vem do feed e a página da notícia não é aberta (site lento ou que recusa robôs) |
| `origem: "email"` | fonte alimentada por fora (boletim lido no e-mail): o robô não visita o endereço |

### Publicação no site, avisos e resumo semanal (v0.8.0)

- **Registro automático:** a cada coleta, o robô lê `artecon.cnt.br/news`, abre as notícias ainda não
  registradas e, quando uma corresponde a um conteúdo aprovado sem registro (título parecido e a maior
  parte do texto presente), registra link e data em "Publicações no site". Para desligar ou mudar o
  endereço: Configurações, chave `site` = `{"desligado": true}` ou `{"lista": "...", "padrao": "..."}`.
- **Texto do site diferente:** se a página publicada deixar de trazer a maior parte do texto registrado,
  abre o aviso "Radar: texto do site diferente do aprovado" (fecha sozinho quando volta a bater).
- **Para o site:** no conteúdo aprovado, os botões estão numerados (1. título, 2. texto, 3. imagem) e a
  tela indica a categoria correspondente no site.
- **Resumo semanal:** toda segunda-feira, 08h47, um único aviso "Radar: resumo da semana" com as notícias
  de relevância alta (ou nota da IA 7 ou mais), agrupadas por tema. O anterior é fechado. Como o
  repositório é público, o boletim da ITC aparece só como contagem. Rodar à mão: Actions →
  "Radar — resumo semanal" → Run workflow.
- **Nota da IA na relevância:** captura que ficou "baixa" por falta de palavras da lista sobe para
  "média" quando a IA dá nota 8 ou mais (`nota_promove` em Configurações → Relevância; 11 desliga).
  A que foi rebaixada por termos negativos (apreensão, concurso, leilão...) continua baixa.

### Diário Oficial pelo INLABS (v0.8.0)

A fonte "Diário Oficial da União — atos da Receita, PGFN e CGSN (INLABS)" lê os XML oficiais do DOU
(seção 1 e edição extra) e guarda só os atos normativos desses órgãos, sem as unidades regionais.
Ela entra **desligada**. Para ligar:
1. Cadastre-se de graça em https://inlabs.in.gov.br.
2. GitHub → repositório `radar` → Settings → Secrets and variables → Actions → New repository secret:
   `INLABS_EMAIL` (o e-mail do cadastro) e `INLABS_SENHA` (a senha). Nunca mande a senha pelo chat.
3. Radar → Fontes → a fonte do INLABS → Configurar → Fonte ativa → Salvar.
Os filtros (órgãos, tipos de ato, regionais excluídas, dias) ficam em "Outras opções de leitura".

### Fontes novas de outubro/2026

Rode uma vez `sql/radar-fontes-novas-2026-10.sql` no SQL Editor (pode rodar de novo sem
estragar nada). Ele cadastra, **desligadas**, três fontes testadas pelo diagnóstico:

| Fonte | Oficial | Observação |
|---|---|---|
| Diário Oficial da União — Destaques | sim | só a seleção diária da Imprensa Nacional (pouco volume, sem enxurrada) |
| Econet Editora — Blog (RSS) | não | a área de assinantes pede login e fica de fora |
| Portal Contábil SC — Notícias (RSS) | não | site lento: o texto vem do feed |

Ligue cada uma em Fontes → Configurar → Fonte ativa. Fontes não oficiais servem de alerta e pauta;
a fundamentação continua vindo só das oficiais.

O mesmo SQL cadastra **ITC Consultoria — boletim por e-mail** (`itc-email`) e a função
`radar_receber_email`, que grava as matérias do boletim lido no e-mail (a mesma manchete nos dois
boletins da ITC entra uma vez só). O robô não visita essa fonte. Os boletins **não** vão para o
repositório, que é público: a rotina diária grava direto no banco.

## Atualizações futuras

**Da v0.7.1 para a v0.8.0:** Supabase radar-artecon → SQL Editor → execute
`sql/radar-setup-v0.8.0.sql` inteiro (a linha `instalacoes concluidas` deve mostrar `v0.8.0`) e,
se ainda não rodou, `sql/radar-fontes-novas-2026-10.sql`. A tela e o robô chegam pelo repositório.
A função `radar-ia` não muda. Para o DOU completo (INLABS), veja "Diário Oficial pelo INLABS".

**Da v0.7.0 para a v0.7.1:** Supabase radar-artecon → SQL Editor → cole e execute
`sql/radar-setup-v0.7.1.sql` inteiro e guarde a evidência (a linha `instalacoes concluidas` deve
mostrar `v0.7.1`). O resto já chega pelo repositório: a tela (GitHub Pages; Ctrl+F5 no Radar) e o
robô (próxima coleta). A função `radar-ia` não muda. Antes do SQL, o robô novo funciona normalmente,
só sem a limpeza de imagens; os termos com pontuação nas regras só passam a pontuar depois dele.

**Da v0.6.1 para a v0.7.0**, nesta ordem:

1. Supabase radar-artecon → SQL Editor → execute o SQL da versão (hoje, `sql/radar-setup-v0.8.0.sql`). Guarde a evidência.
2. GitHub, repositório `radar` → envie `index.html` e a pasta `robo/` (arquivos novos e alterados:
   `radar_ia.py`, `radar_coletar.py`, `radar_util.py`).
3. GitHub → abra `.github/workflows/radar-coletar.yml` → lápis (Edit) → substitua o conteúdo pelo
   do pacote → Commit. A única mudança é a linha `RADAR_IA_GATEWAY_TOKEN`.
4. GitHub → Settings → Secrets and variables → Actions → New repository secret →
   **`RADAR_IA_GATEWAY_TOKEN`** = o token do Radar na IA Central (o mesmo do segredo
   `IA_GATEWAY_TOKEN` da função `radar-ia`). Se não tiver mais o token guardado, gere outro no
   Portal → Consumo de IA → Radar → Trocar token e grave o novo **nos dois lugares**: neste
   segredo do GitHub e no `IA_GATEWAY_TOKEN` do Supabase do Radar.
5. Supabase radar-artecon → Edge Functions → `radar-ia` → cole o `index.ts` novo → Deploy.
6. GitHub → Actions → "Radar — coleta das fontes oficiais" → Run workflow. No resumo da execução
   aparece a linha **Avaliação da IA** com quantas capturas receberam nota. Na primeira vez, as
   que já estavam na fila são avaliadas (até 150 por execução).

**Da v0.6.0 para a v0.6.1:** (1) instale a IA Central v1.1.0 e o Portal v1.4.0; (2) envie o
`index.html` ao repositório do Radar; (3) siga o Passo 7 (função `radar-ia`, segredo
`IA_GATEWAY_TOKEN`). Não há SQL novo para o Radar.

**Da v0.5.0 para a v0.6.0:** (1) execute `radar-setup-v0.8.0.sql` no SQL Editor; (2) envie
`index.html` e `informativo.html` ao repositório; (3) cole o `radar-fale-conosco-v0.6.0.json`
em Configurações → Fale Conosco; (4) se usa a IA, cole de novo o `index.ts` na função
`radar-ia` e faça o Deploy. O robô não mudou de comportamento (só o número da versão).

Se você já instalou uma versão anterior: execute `sql/radar-setup-v0.8.0.sql` no SQL
Editor (ele atualiza sem apagar dados), envie os arquivos novos ao repositório, **apague o
`informa.html` do repositório** e, se a função de IA já estiver instalada, cole de novo o
`index.ts`.

Substitua `index.html`, `informativo.html`, as imagens do timbrado e as pastas `robo/`, `sql/`, `testes/`,
`supabase/` e `.github/`. Se a função de IA mudar, cole de novo o `index.ts` no Supabase. **Não** substitua o `radar-config.js`. Se a versão trouxer um novo
`radar-setup`, execute-o no SQL Editor. A versão em uso aparece no topo do dashboard e
a aba **Versões** lista o que mudou.

## Ideias anotadas para o futuro

Pedidos do escritório para quando chegar a hora (não implementados):

- **Instagram (05/10/2026):** quando o Radar for integrado ao Instagram, ver a possibilidade de
  **buscar o que mais está sendo publicado** sobre os temas do escritório (hashtags e perfis de
  contabilidade e tributação), para sugerir assuntos e comparar com o que o Radar já capturou.
- **Diário Oficial da União:** entrar pelo INLABS (XML oficial, cadastro gratuito), com filtro forte
  por órgão e assunto para **não gerar enxurrada de notificações** diárias.

## Rodar os testes

No GitHub: Actions → "Radar — testes". Localmente: PostgreSQL 16, `postgrest` no PATH,
`deno` no PATH, `pip install playwright && playwright install chromium` e
`python -m pytest testes -q`.
