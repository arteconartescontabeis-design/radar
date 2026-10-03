# Radar Artecon — v0.5.0

Plataforma de Inteligência Contábil e Tributária — Fase 1 enxuta.

Esta versão entrega a Fase 1 enxuta completa: o **banco**, os **coletores das fontes
oficiais**, as **telas** (dashboard de curadoria) e a
**inteligência artificial** (OpenAI) para sugerir classificação, buscar trechos de
fundamentação e redigir rascunhos.

A v0.4.0 acrescenta o **Informativo Mensal** no padrão enviado aos clientes (agenda de
obrigações, artigos, Fale Conosco e fecho, no papel timbrado, pronto para salvar em PDF),
**imagem de capa, autor e fonte** nos conteúdos, e os botões para **copiar a notícia para o
site** da Artecon. É o modo de trabalho até a parte oficial (robô e fontes) estar validada.

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
| `sql/radar-setup-v0.5.0.sql` | Cria (ou atualiza) as tabelas `radar_*`, as regras e as 6 fontes iniciais. Pode ser executado mais de uma vez. |
| `sql/radar-reversao-v0.5.0.sql` | Desfaz a instalação (apaga só objetos `radar_*`). |
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
3. SQL Editor → cole e execute `sql/radar-setup-v0.5.0.sql` inteiro.
4. O resultado final é a **evidência**: exporte em CSV e guarde.
   Esperado: 21 linhas de tabela, todas com `rls = true`; `fontes = 6`; `categorias = 8`;
   `instalacoes concluidas` com ao menos 1 e a versão `v0.5.0`.
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

### Passo 7 — Inteligência artificial (OpenAI)

1. Na OpenAI (platform.openai.com): crie uma chave de API e defina um **limite mensal de
   gasto** na conta. Esse limite é a trava real de custo.
2. No Supabase: Edge Functions → criar função pelo editor → nome **`radar-ia`** → cole o
   conteúdo de `supabase/functions/radar-ia/index.ts` → Deploy. Deixe ligada a opção de
   verificar o JWT.
3. Edge Functions → Secrets → crie `OPENAI_API_KEY` com a chave da OpenAI.
4. No dashboard, abra um assunto e clique em "Sugerir classificação com IA".

Segredos opcionais:

| Segredo | Padrão | Para quê |
|---|---|---|
| `RADAR_OPENAI_MODELO` | `gpt-6.1-sol` | modelo que busca trechos e redige |
| `RADAR_OPENAI_MODELO_RAPIDO` | `gpt-6-luna` | modelo que classifica |
| `RADAR_IA_LIMITE_MENSAL_TOKENS` | `3000000` | teto de consumo por mês dentro do Radar |
| `RADAR_OPENAI_API` | `responses` | use `chat` se a conta só aceitar a API antiga |

Os nomes dos modelos padrão foram lidos da documentação da OpenAI em 02/10/2026. Se a
sua conta não tiver um deles, a tela mostra a mensagem dizendo qual segredo ajustar.
A função não usa a chave service_role: age com a sessão de quem clicou.

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
- O Radar não publica nem altera nada no site da Artecon: o registro depende de alguém
  informar o link. Um conteúdo pode ter mais de um registro (site, rede social,
  republicação).
- As tabelas e regras da antiga página pública (`radar_publicacoes`) continuam no banco,
  sem uso pelas telas, para o caso de a publicação automática voltar na parte oficial.
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

Como ler o resultado da primeira coleta: **ok** com itens novos = funcionando;
**vazio_suspeito** = o padrão dos links não casou com nada (ajuste o padrão); **falha** =
o site não respondeu ou o cadastro está incompleto (a observação diz o motivo);
**parcial** = achou os itens, mas não leu o texto de alguns (ajuste "Onde está o texto").

Fonte que já tem capturas não é excluída: desmarque "Fonte ativa". Excluir uma fonte sem
capturas apaga junto o histórico de execuções dela. O tipo "Atos normativos da Receita" é
específico do site Normas e não aparece para fontes novas. O padrão dos links é conferido
pelo navegador; o robô usa Python, que recusa algumas construções aceitas pelo navegador
(nesse caso a execução vem como "falha", com o motivo). Não há limite de tempo por fonte:
um padrão muito complexo pode atrasar a coleta inteira. O robô acessa o endereço
cadastrado a partir do GitHub; cadastre só sites públicos. O diagnóstico do
Passo 1 continua lendo só as seis fontes iniciais (arquivo `robo/radar_fontes.json`); as
fontes cadastradas pela tela são conferidas pela própria coleta.

Outras opções, no campo "Outras opções de leitura (JSON)":

| Chave | Efeito |
|---|---|
| `titulo_do_contexto` | usar o título do bloco em volta do link (links "Acessar") |
| `excluir_url` / `excluir_orgao` | o que ignorar |
| `revisitar_dias` | por quantos dias um item é relido para detectar alteração |
| `data_do_texto` | ler a data de publicação no texto do item, quando a lista não traz |

## Atualizações futuras

Se você já instalou uma versão anterior: execute `sql/radar-setup-v0.5.0.sql` no SQL
Editor (ele atualiza sem apagar dados), envie os arquivos novos ao repositório, **apague o
`informa.html` do repositório** e, se a função de IA já estiver instalada, cole de novo o
`index.ts`.

Substitua `index.html`, `informativo.html`, as imagens do timbrado e as pastas `robo/`, `sql/`, `testes/`,
`supabase/` e `.github/`. Se a função de IA mudar, cole de novo o `index.ts` no Supabase. **Não** substitua o `radar-config.js`. Se a versão trouxer um novo
`radar-setup`, execute-o no SQL Editor. A versão em uso aparece no topo do dashboard e
a aba **Versões** lista o que mudou.

## Rodar os testes

No GitHub: Actions → "Radar — testes". Localmente: PostgreSQL 16, `postgrest` no PATH,
`deno` no PATH, `pip install playwright && playwright install chromium` e
`python -m pytest testes -q`.
