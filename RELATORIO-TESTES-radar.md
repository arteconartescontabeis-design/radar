# Radar Artecon — Relatório de testes (v0.7.0)

Data: 03/10/2026. Resultado: **395 testes automatizados do Radar, 395 aprovados** (suíte executada
duas vezes seguidas). A IA Central não mudou nesta versão (v1.1.0, 15 testes).

## v0.7.0 — em alta, sem repetição, texto original, imagem realista e assunto por etapas

O que foi comprovado:

- **Nota da IA no robô:** só título, resumo, órgão e data vão para a IA (o texto oficial e a chave
  do banco não); capturas de baixa relevância nem são enviadas; nota fora de 0 a 10, id inventado
  e item repetido na resposta são descartados; só o robô grava a avaliação (editor, administrador
  e visitante são recusados).
- **IA indisponível não derruba a coleta:** sem o segredo, com limite atingido na IA Central e com
  endereço errado, a coleta termina normalmente, o resumo diz o motivo e as capturas são avaliadas
  na coleta seguinte.
- **Em alta:** a tela abre com as 10 de maior nota, sem repetição e sem baixa relevância; o
  contador da aba e o cartão do painel acompanham; nota de corte e quantidade configuráveis, com
  valores inválidos voltando ao padrão.
- **Repetição:** não aponta para si mesma nem forma ciclo; repetição de repetição sobe até a
  origem; abrir (ou ignorar) leva as repetições junto; a repetição que chega depois entra sozinha
  só em assunto em andamento, com marca e registro na auditoria, e "Não é o mesmo fato" a devolve
  para a triagem (recusado para leitor, visitante e robô, e quando há evidência na captura);
  repetição de assunto ignorado fica na triagem com o aviso de qual assunto parece ser; o grupo
  entra em "Em alta" pela maior nota; muitos itens do lote apontando para a mesma origem (direto
  ou em cadeia) são descartados como erro da IA; título alterado pede nova avaliação; só vai
  junto o que o cartão anuncia (ignorar a repetição recolhida ignora só ela; repetições com
  cartão próprio não são levadas por outra); a junção automática procura assunto em andamento
  no grupo todo; o editor não consegue marcar à mão um vínculo como "juntado pela IA".
- **Robô resistente a resposta estranha:** resposta que não é JSON, lista no lugar de objeto,
  campos de tipo errado e lote sem nenhum item aproveitável param a avaliação com aviso, sem
  derrubar a coleta; o token nunca aparece no resumo; as capturas mais novas são avaliadas
  primeiro; resposta parcial é avisada no resumo.
- **Fonte preenchida** com o órgão da captura oficial; o que a pessoa informa ou apaga é respeitado.
- **Cópia da fonte:** trecho de 12 palavras ou mais igual ao texto oficial é apontado e impede a
  aprovação; trocar maiúsculas, acentos e pontuação não disfarça (nem escrever tudo em
  maiúsculas); citação curta entre aspas deixa de contar, mas aspas em volta do texto inteiro ou
  muitas citações somadas não livram; citar o nome da norma com número e data (ou várias normas
  em sequência) não é cópia; aspas vazias, "##" no meio da linha e caractere invisível dentro das
  palavras não disfarçam; o título não é comparado; reescrito, aprova.
- **Imagem:** a descrição opcional entra no pedido; sem ela a IA escolhe; as proibições (texto,
  marca, assinatura, pessoa real, estilo de autor) vêm sempre depois e uma descrição que manda
  ignorar as regras não as remove do pedido; descrição que pede logotipo, marca, brasão,
  assinatura de autor, autoridade ou "estilo de" alguém, ou com mais de 200 caracteres, é recusada
  antes de gerar (nenhuma imagem é pedida nem cobrada); palavras parecidas ("diálogo",
  "assinatura de um contrato", "presidente da empresa", "foto de Florianópolis") não são
  recusadas; a descrição continua no campo depois de gerar.
- **Assunto por etapas:** abre na etapa que falta, os passos e o "Próximo passo" trocam de etapa,
  o que foi digitado ou escolhido em lista não se perde — nem ao trocar de etapa nem quando se
  salva em outra etapa; formulário de evidência aberto e preenchido em outra etapa barra a ação —,
  os passos do alto respondem ao teclado e "Mostrar tudo numa página" fica guardado.
- **Atualização:** o SQL v0.7.0 foi aplicado por cima do SQL da v0.6.0 (o que está em produção)
  com dados, duas vezes seguidas, e a reversão foi executada em seguida.
- **Achado dos testes:** a gravação da junção automática na auditoria falhava por permissão (o
  robô só lê a auditoria) e a junção era descartada em silêncio; corrigido antes da entrega.

## v0.6.1 — IA pela IA Central (Anthropic no texto, OpenAI nas imagens)

Como foi testado: a função `radar-ia` e o `ia-gateway` v1.1.0 rodaram de verdade (Deno), com o
banco `core` montado como réplica da produção (v1.0.0 mais as diferenças lidas da produção em
03/10/2026) e o `ia_central_v1.1.0.sql` por cima. Só a Anthropic, a OpenAI e o hub de e-mail foram
imitados. O que foi comprovado:

- **Caminho completo:** classificar, fundamentar, gerar, "Preparar com IA", ilustração e o teste
  de Configurações passam pela IA Central. À Anthropic vai a chave da IA Central; o token do
  Radar, o token do usuário e o e-mail de quem pediu não saem da Artecon.
- **Custo no Portal:** cada chamada fica em `core.ia_uso` com aplicativo, quem pediu e o custo
  (texto pelos tokens; imagem por unidade, na conta da OpenAI). O saldo de uma conta não se
  mistura com o da outra.
- **Limites e bloqueios:** limite do dia, modelo não liberado, IA do aplicativo desligada e token
  trocado no Portal chegam ao Radar com mensagem que diz o que fazer, sem gastar.
- **Avisos por e-mail:** crédito acabando e crédito esgotado saem uma vez, por conta, com o link
  da página de recarga certa; o relatório mensal traz as duas contas e os dois links.
- **Compatibilidade:** depois do SQL novo, as chamadas no formato do `ia-gateway` v1.0.0 e do
  Portal v1.3.0 continuam aceitas; o Portal v1.4.0 com a IA Central antiga mostra só a Anthropic.
- **Migração e reversão:** o SQL roda duas vezes seguidas sem erro, preserva o uso e o saldo que
  existiam (marcados como Anthropic) e a reversão devolve funções, colunas e aplicativos ao
  estado anterior.

## v0.6.0 — relevância, telas mais simples, capa automática e final do informativo

O que foi comprovado:

- **Filtro de relevância:** títulos do tipo dos que o robô trouxe na primeira coleta real
  ficam onde se espera (Simples Nacional, IBS/CBS, instrução normativa → alta; apreensão,
  leilão, Instagram → baixa); termo no título vale o dobro; só casa palavra inteira ("MEI"
  não casa com "meio"); acento e maiúscula não importam. A fila, o painel e o contador da
  aba contam só o relevante; o assunto herda a relevância. Só o administrador muda as
  regras, e mudar reavalia a fila sem gerar auditoria nem versão de captura. Regras
  malformadas ou com números absurdos não travam a coleta do robô.
- **Capturas:** a tela abre só com alta e média, a mais relevante primeiro; "Ignorar as N
  desta lista" ignora só o que está visível (a busca conta) e o leitor não tem o botão.
- **Assunto:** os cinco passos e o "Próximo passo" acompanham o trabalho do início ao
  registro no site; não diz "Concluído" quando o texto mudou depois do registro, quando a
  fundamentação caiu ou quando há outro conteúdo pendente; conteúdo rejeitado e assunto
  ignorado ou arquivado têm orientação própria; os botões do alto não descartam o que foi
  digitado e não salvo.
- **Capa automática:** todo conteúdo novo nasce com a capa de 1200 × 630 (conferido que é
  um desenho de verdade, não folha em branco); se a capa falhar, o aviso diz isso; a imagem
  trocada não fica sobrando no banco.
- **IA:** "Preparar com IA" registra os trechos e cria o rascunho com capa; a ilustração
  manda à OpenAI só o tema (nunca o texto oficial) e entra no consumo; o teste em
  Configurações mostra função não instalada, chave recusada e modelo indisponível, sem
  revelar a chave; só o administrador roda o teste.
- **Informativo:** o Fale Conosco segue o modelo (WhatsApp x telefone fixo, equipe em duas
  colunas, contadores responsáveis, legenda); com a quantidade real de telefones e pessoas,
  o quadro e o fecho cabem juntos na última página; dados maliciosos ou malformados
  aparecem como texto.
- **Atualização:** o script foi aplicado por cima da v0.5.0 com dados, duas vezes seguidas.

O que a revisão independente desta versão achou e foi corrigido: salvar as regras ficava
lento demais com o banco grande (agora só a fila é reavaliada e a conta ficou cerca de dez
vezes mais rápida); número absurdo nas regras travava a coleta; "Concluído" aparecia com
pendência; o fecho do informativo caía sozinho numa terceira página; a capa que falhava
era anunciada como gerada; imagens trocadas se acumulavam; o rótulo do botão de ignorar em
lote não acompanhava a busca; o teste da IA estava aberto ao editor.

Não corrigido, por escolha: o teste da IA faz dois pedidos mínimos e pagos à OpenAI (frações
de centavo) a cada clique, porque só assim confere chave, crédito e modelo de uma vez.

## v0.5.0 — sem página pública; registro do que foi ao site

Por decisão sua, a página pública "Artecon Informa" foi retirada: as publicações são
feitas nas páginas da Artecon e o Radar registra o link, a data e a cópia do texto
aprovado que saiu. O que foi comprovado:

- **Fonte oficial:** o registro no site é recusado sem o assunto confirmado oficialmente e
  sem trecho conferido em fonte oficial (trecho inventado ou de fonte não oficial não
  conta); a fundamentação fica guardada no registro. O Informativo Mensal segue exigindo
  só o conteúdo aprovado.
- **Fontes em aberto:** o administrador cadastra, altera e exclui fontes pela tela; editor
  e leitor não. O robô, lendo o banco de teste, coletou uma fonte gravada no banco com os
  mesmos campos que a tela grava e registrou, sem parar as demais, três cadastros errados
  (sem padrão, padrão inválido, padrão que não casa com nada). A cadeia tela → banco e a
  cadeia banco → robô foram testadas separadamente, não em um único teste de ponta a ponta.
- **Texto oficial incluído pela equipe:** só editor e administrador; fica marcado como
  manual e auditado; endereço de outro site é recusado; não substitui captura que já tem
  texto (nem com barra no fim, âncora ou outra fonte); completa captura que o robô deixou
  sem texto; trecho inventado continua recusado; quando o robô lê depois, a origem fica
  anotada.
- **Registro mostra a fundamentação** guardada e avisa quando a base cai depois.
- **Sem leitura pública:** quem não fez login não lê nem grava nada — nenhuma tabela, visão
  ou função. Conferido em banco novo e em banco com a v0.4 instalada e atualizado para a
  v0.5.0 (é o caso do seu Supabase): as permissões públicas antigas são retiradas.
- **Registro:** só de conteúdo aprovado; a cópia do título e do texto não se forja nem se
  altera depois; só vale se o texto ainda for o que estava na tela de quem registrou;
  link fora do padrão (javascript:, espaços, aspas, caracteres invisíveis) e data futura
  são recusados; leitor não registra; só o administrador exclui.
- **Avisos:** conteúdo alterado depois do registro é sinalizado; quando há registro mais
  novo com o texto atual, o antigo aparece só como "versão anterior".
- **Fila:** conteúdo marcado como "não vai ao site" (só do Informativo Mensal) sai da fila
  sem deixar de estar aprovado.

Os testes da antiga página pública (página, agendamento, errata, "tirar do ar") foram
retirados junto com ela. As regras antigas de publicação continuam testadas no banco. Os
defeitos encontrados foram corrigidos e viraram teste.

## Correção da v0.4.1 (erro na instalação real)

Na primeira instalação no Supabase, o `radar-setup-v0.4.0.sql` parou no fim com
`relation "_radar_antes" does not exist`. O script guardava o "estado antes" numa tabela
temporária que só vive dentro da transação; reproduzi o mesmo erro aqui executando o script
sem a transação (cada instrução confirmada à parte). A causa exata dentro do SQL Editor não
foi confirmada — a reprodução mostra o mecanismo, não prova que foi isso que o editor fez.

A v0.4.1 não usa tabela temporária e não depende da transação. Três testes novos: instala
sem transação; conclui por cima de um banco deixado pelo erro da v0.4.0, preservando
ajustes; e uma execução interrompida fica registrada sem contar como instalada. Os testes
anteriores não pegaram o defeito porque sempre executavam o script com a transação íntegra.

## O que foi testado

| Grupo | Testes | Como |
|---|---:|---|
| Banco: instalação, atualização da v0.1.0, permissões, fundamentação, aprovação, publicação, auditoria, uso da IA, imagens, configurações, informativo e registro de publicações no site, fontes e texto oficial | 130 | PostgreSQL 16 local, com os papéis e os privilégios padrão do Supabase reproduzidos |
| Leitores das fontes e utilidades | 69 | amostras no formato de cada fonte e os **endereços, títulos e datas reais** lidos em 02/10/2026 |
| Robô de ponta a ponta: robô → API → banco | 27 | PostgREST real (o motor de API do Supabase) e "sites" simulados |
| Telas, IA, Informativo Mensal e PDF em navegador (Chromium) | 115 | banco e API reais; a função de IA rodando de verdade (Deno); login do Supabase e OpenAI simulados |

## Conferência das fontes nos sites reais (02/10/2026)

Feita lendo as páginas reais (endereços, títulos e datas). Resultado por fonte:

| Fonte | Resultado | O que mudou no projeto |
|---|---|---|
| Receita — Notícias | o feed RSS da pasta estava parado em julho/2026 | passou a ler a página "Últimas notícias" (em dia, 30 itens por página) |
| PGFN — Notícias | 16 notícias reconhecidas, nenhum link de menu, busca ou paginação confundido | nada |
| Simples Nacional — Notícias | endereços e datas conferem | nada |
| Receita — Atos normativos | a página inicial só mostra os 15 atos mais recentes; a consulta por período traz 100 por página (385 atos em 17 dias) | passou a consultar por período, em até 6 páginas |
| Receita — texto integral dos atos | o endereço estimado redireciona por JavaScript; não há texto para baixar | captura a **ementa**, e a tela avisa |
| SEF/SC — Últimas legislações | atos DIAT e decreto reconhecidos; `.doc` de resoluções ignorado | nada |
| CGIBS — Notícias | padrão de endereço confere; a lista não traz data | a data passou a ser lida do texto da notícia |

O que essa conferência **não** cobre: o HTML bruto não pôde ser baixado aqui, então a
leitura da estrutura da página pelo robô e a extração do texto de cada item continuam
dependendo do workflow "Radar — diagnóstico das fontes". Também não se sabe se algum site
bloqueia os servidores do GitHub Actions.

## Informativo Mensal: o que foi comprovado

- **Agenda de obrigações:** o cálculo reproduz, dia por dia e obrigação por obrigação, os
  informativos 8, 9 e 10/2026 (agosto: 06, 07, 10, 17, 20, 25, 31; setembro: 04, 10, 15,
  18, 21, 25, 30; outubro: 06, 07, 13, 15, 20, 23, 30). Testados também Carnaval,
  Sexta-feira Santa, Corpus Christi, feriado local, mês curto e virada de ano. A revisão
  independente repetiu o cálculo em cinco fusos horários: o resultado não muda.
- **PDF:** gerado pelo Chromium a partir de um assunto criado na tela, com imagem, tabela,
  autor e fonte. Conferido por código: folha A4, timbrado de topo e de rodapé em todas as
  páginas, nenhum texto por baixo deles, agenda na página 1, artigos a partir da página 2,
  Fale Conosco e fecho na última. Conferido também visualmente contra o seu informativo
  n.º 10/2026. A revisão independente repetiu com 15 páginas (agenda de 28 linhas, artigo
  de 60 parágrafos, tabela de 90 linhas).
- **Regras:** só conteúdo aprovado entra; edição fechada não muda, não perde nem ganha
  artigo; só o administrador reabre; não fecha com artigo não aprovado; artigo alterado
  depois do fechamento gera aviso na edição e na página de impressão.
- **Imagens:** a foto é reduzida no navegador (2400×1600 virou 1200×800, JPEG); o banco
  recusa o que não for JPG, PNG ou WebP; só a equipe lê as imagens.
- **Cópia para o site:** título e texto vão para a área de transferência com subtítulos,
  negrito, lista e tabela.
- **Segurança:** HTML digitado em título, texto, tabela, autor, fonte, agenda e
  configurações aparece como texto nas duas páginas; nada executa.

## IA: o que foi comprovado

- Classificar só sugere: nada é gravado até a pessoa salvar; valor fora das opções não
  apaga o que já estava.
- Buscar trechos: de cinco trechos propostos (um literal, um com número trocado, um
  inventado, um de outro texto, um com artigo inexistente), só os literais entram, e o
  artigo inexistente é descartado. Nenhuma evidência "não conferida" fica gravada.
- Gerar: o texto entra como rascunho, marcado como gerado por IA. A verificação por
  código foi testada com 42 frases: 22 escritas de outro jeito mas presentes no texto
  oficial (não avisa) e 20 ausentes (avisa) — normas, artigos, parágrafos, percentuais,
  valores, datas, mês/ano, prazos e anos.
- A IA não aprova nem publica; avisos e origem do texto não podem ser apagados.
- Leitor, usuário sem perfil, anônimo e token de serviço são recusados; pedidos
  malformados não chegam à OpenAI.
- Para a OpenAI vai o texto oficial delimitado como dado; não vão tokens nem e-mails.
- Erros da OpenAI (chave recusada, sem crédito, modelo inexistente) viram mensagens claras;
  o consumo é registrado por usuário e o teto mensal barra antes de gastar.

## O que NÃO foi testado aqui

| Item | Por quê | Como será coberto |
|---|---|---|
| O site da Artecon | o ambiente não conseguiu abrir www.artecon.cnt.br; a capa automática segue a identidade do papel timbrado e do logotipo, não uma cópia das notícias do site | me envie o link ou a imagem de uma notícia do site para aproximar |
| Ilustração por IA de verdade | a OpenAI é simulada; a qualidade e o custo da imagem só aparecem com a chave real | primeiro uso |
| Regras de relevância no dia a dia | calibradas com os títulos da primeira coleta; é filtro por palavras, não por entendimento | ajustar a lista em Configurações conforme o uso |
| Tempo limite do Supabase ao salvar as regras | medido aqui: cerca de 0,7 ms por captura na fila | se a fila passar de alguns milhares de itens, ignore as de baixa relevância antes |
| A nota da IA de verdade | a IA é imitada nos testes; se as notas fazem sentido para o seu escritório só aparece com as capturas reais | olhar "Em alta" e "Relevantes" nos primeiros dias e ajustar a nota de corte |
| Se a imagem obedece às proibições | o pedido leva as regras, mas quem gera é a OpenAI: pode sair texto ou marca na imagem | conferir cada imagem antes de aprovar |
| Plágio fora do texto capturado | a comparação é só com as capturas do próprio assunto | revisão humana |
| Anthropic e OpenAI de verdade | as duas são imitadas nos testes. A qualidade do texto e da ilustração, o formato exato das respostas e se `gpt-image-2` existe na sua conta da OpenAI só aparecem com as chaves reais | "Testar a IA" e o primeiro uso |
| `ia_central_v1.1.0.sql` no projeto do DP | testado numa réplica montada a partir do que a produção devolveu em 03/10/2026, não na produção | evidência depois de executar |
| Portal inteiro | só a tela Consumo de IA foi exercitada (com o código do Portal v1.4.0, sem o login) | conferência na tela |
| Função de IA dentro do Supabase | aqui ela roda no Deno local; limites de tempo e de memória da plataforma não foram medidos | primeiro uso no Passo 7 |
| HTML real dos sites lido pelo robô | ambiente sem acesso direto aos sites | diagnóstico (Passo 1) |
| Login contra o Supabase Auth de verdade | não testado por mim; **você entrou no painel em 02/10/2026** com a v0.4 (tela do Painel enviada) | — |
| `radar-setup-v0.6.0.sql` no seu Supabase | a v0.5.0 foi instalada por você e a evidência conferiu; a v0.6.0 ainda não foi executada aí. Aqui, a atualização da v0.5.0 para a v0.6.0 foi testada | evidência depois de executar |
| Instalação no Supabase, GitHub Pages e GitHub Actions | só no seu ambiente | evidência do Passo 2 e primeira execução de cada rotina |
| Fontes do Google nas telas | bloqueadas no ambiente de teste | conferência visual no seu navegador |
| Estabilidade do hash em páginas com trechos dinâmicos | só aparece com visitas reais em dias diferentes | observar "Alterados" nas primeiras semanas |
| Uso com leitor de tela | não testado | — |
| PDF do informativo em Firefox ou Safari | só o Chromium foi testado (Chrome e Edge usam o mesmo motor); a repetição do timbrado por página pode variar nos outros | gere o PDF pelo Chrome ou Edge |
| Colar o texto copiado no editor do site da Artecon | a plataforma do site não é conhecida; o teste confere o que vai para a área de transferência, não como o editor do site recebe | primeiro uso |
| Regras da agenda fora dos três meses conferidos | as regras foram deduzidas dos informativos 8, 9 e 10/2026; "31/12 sem expediente bancário" é premissa minha, não veio dos seus PDFs | conferir a agenda de cada edição antes de enviar |
| Prompt novo da IA no estilo do informativo | a OpenAI é simulada nos testes; a qualidade do texto só aparece com a chave real | primeiro uso no Passo 7 |

## Revisão independente

**Banco e robô (v0.1.0), duas rodadas.** Três defeitos críticos e nove importantes
corrigidos (publicação alterável no ar, texto publicado sem vínculo com o aprovado, chave
do robô com poder de publicar, entre outros).

**Telas (v0.2.0), duas rodadas.** Nenhum crítico; nove importantes corrigidos (clique
duplo, falso "salvo", último administrador, navegação travada, entre outros).

**IA e fontes (v0.3.0), uma rodada.** Nenhum crítico: a IA não conseguiu aprovar, publicar
nem gravar fora das regras. Oito pontos importantes corrigidos:

- a verificação do texto gerado deixava passar casos comuns ("9%" quando o oficial dizia
  "0,9%", prazos em dias, listas de artigos) — foi reescrita para comparar pelo valor;
- um trecho aceito pela função e recusado pelo banco ficava gravado como "não conferido" —
  agora quem grava é o banco, e só se conferir;
- a limpeza de HTML apagava trechos como "receita < R$ 500 e multa > 2%";
- um editor podia inflar o registro de consumo e travar a IA de todos;
- sugestão fora das opções apagava a categoria que já existia;
- a paginação dos atos da Receita só aproveitava a primeira página;
- a data lida do texto podia ser a de vigência em vez da de publicação;
- consumo não era registrado quando algo falhava depois da resposta da OpenAI.

**Informativo Mensal, imagens e modelo do site (v0.4.0), uma rodada.** Nenhum crítico: não
houve XSS nem vazamento para o público. Cinco pontos importantes corrigidos:

- a editora via o botão "Remover" artigo, mas o banco só deixava o administrador remover;
- um artigo podia ser tirado de uma edição fechada trocando-o de edição;
- uma tela desatualizada regravava, em silêncio, a agenda salva por outra pessoa;
- o usuário que criou uma edição fechada não podia ser excluído do Supabase;
- artigo alterado e reaprovado depois do fechamento aparecia sem nenhum aviso.

Corrigidos também: confirmação de fechamento gravava antes de confirmar; mês trocado sem
recalcular a agenda; mensagem de número repetido; título só com espaços; dados malformados
que derrubavam a tela; tabela com casos de borda; texto colado no timbrado nas páginas de
continuação; último dia útil de dezembro; sessão renovada em outra aba; limites de tamanho
do texto e da imagem. Seis testes que a revisão apontou como frouxos foram endurecidos.

Antes da revisão, os próprios testes já tinham revelado um defeito: a regra que libera a
imagem ao visitante dependia de uma coluna que ele não podia ler, e a capa não apareceria
na página pública (hoje extinta).

**v0.5.0 (registro do que foi ao site), uma rodada.** Nenhum crítico: o visitante ficou sem
acesso algum, inclusive em banco atualizado, e não houve XSS nem como forjar o registro.
Pontos importantes corrigidos:

- Enter no campo do link salvava o conteúdo em vez de registrar, e o link digitado sumia;
- o registro guardava o texto do momento do registro, que podia ser diferente do que
  estava na tela de quem copiou para o site;
- conteúdo que só vai ao Informativo Mensal ficava para sempre na fila "a publicar";
- este relatório não tinha sido atualizado.

Corrigidos também: regra do link mais frouxa no banco que na tela; data futura aceita;
avisos de "texto alterado" que nunca sumiam de registros antigos; assunto arquivado que
voltava como aprovado; corrida entre excluir e incluir registro; respostas com o texto
inteiro ao corrigir o link; avisos na tela que cobriam botões.

**v0.5.0, segunda parte (fonte oficial, fontes em aberto, texto oficial, visual), uma
rodada.** Nenhum crítico. Pontos importantes corrigidos: o texto colado aceitava endereço
de qualquer site sob qualquer fonte oficial; uma barra no fim do endereço criava captura
paralela à do robô; endereço que o robô registrou sem texto não aceitava o texto colado;
a regra de formato das fontes podia travar a atualização de saúde feita pelo robô em fonte
antiga; a fundamentação guardada não aparecia em nenhuma tela; a marca "manual" sumia
quando o robô atualizava a captura. Ficou sem correção, por ser de baixo risco (só o
administrador cadastra): padrão de links muito complexo pode atrasar a coleta.

As correções das quatro últimas rodadas foram cobertas por testes, mas não passaram por uma
segunda revisão independente.

## Pendências conhecidas

1. **Texto integral dos atos da Receita:** só a ementa é capturada. Para citar artigo de
   uma instrução normativa, a pessoa precisa abrir a fonte; a fundamentação automática
   desses atos fica limitada à ementa.
2. **Verificação da IA tem limites:** não lê números por extenso, incisos nem normas sem
   número, e não avalia a interpretação.
3. **Teto mensal de tokens** pode ser ultrapassado por pedidos simultâneos; a trava real é
   o limite de gasto na conta da OpenAI.
4. **Texto digitado e não salvo se perde** se a sessão cair de vez no meio da edição.
5. **Listas longas mostram só os itens mais recentes**, com aviso; ainda não há paginação.
6. **Aviso por e-mail** de fonte com falha ainda não existe; a falha aparece no painel.
7. **Diário Oficial da União** fora desta versão.
16. **Texto oficial incluído pela equipe depende de quem inclui:** o sistema limita o
    endereço ao site da fonte e marca a origem, mas não compara o texto colado com a
    página. Um editor sozinho consegue satisfazer a exigência de fonte oficial.
17. **Sem limite de tempo por fonte no robô:** um padrão de links mal escrito pode atrasar
    a coleta.
18. **Diagnóstico das fontes** (Passo 1) só cobre as seis fontes iniciais.
13. **O Radar não confere o site:** o registro depende de alguém informar o link certo. Se
    a notícia for alterada ou retirada no site, o Radar não fica sabendo.
14. **Tabela `radar_publicacoes` sem uso:** continua no banco, com as regras antigas, e
    ainda pode ser gravada por um editor pela API (nenhuma tela mostra essas linhas).
15. **Assunto com dois conteúdos:** ao registrar um, o assunto passa a "Publicado" e sai da
    lista "Em andamento"; o outro conteúdo aparece pela aba Publicações.
8. **Edição fechada não guarda cópia dos artigos:** o registro definitivo é o PDF salvo.
   Alteração posterior é avisada, não impedida.
9. **Imagens substituídas ficam no banco** sem uso; não há tela de limpeza.
10. **Tabela no texto:** o caractere "|" sempre separa colunas (não dá para usá-lo dentro
    de uma célula) e a linha de título não se repete quando a tabela atravessa a página.
11. **Número sugerido da nova edição** considera o ano corrente; se o mês escolhido for de
    outro ano, ajuste o número à mão.
12. **Envio de imagem que falha no meio** pode deixar uma imagem sem uso no banco.
19. **Relevância é por palavras:** uma notícia importante escrita sem nenhum dos termos
    fica como baixa. Vale olhar o filtro "Baixa relevância" de vez em quando e ajustar a
    lista.
20. **Termos com pontuação nas pontas** (ex.: "S.A.") não são aceitos nas regras: o Radar
    compara palavras inteiras.
21. **A capa automática não é refeita sozinha** quando o título muda: use o botão.
22. **Painel novo com função de IA antiga:** os recursos novos da IA só funcionam depois de
    colar o `index.ts` desta versão; o painel avisa.
23. **A nota da IA usa só título e resumo:** notícia importante com título vago pode receber
    nota baixa. Ela continua em "Relevantes".
26. **Repetição apontada pela IA pode estar errada:** por isso a que entra sozinha num assunto
    vem marcada e tem o botão "Não é o mesmo fato", e a de assunto ignorado ou publicado fica
    na triagem com aviso em vez de sumir.
27. **A verificação de cópia pode ser contornada** (trocar uma palavra a cada poucas, por
    exemplo) e só compara com as capturas do próprio assunto: é apoio à revisão, não garantia.
28. **A recusa de descrição de imagem é por palavras:** não reconhece nome de pessoa real
    escrito sem cargo ("foto de Fulano de Tal"), nem variações que não estão na lista, e não
    confere o título do conteúdo. A proteção principal é o pedido à OpenAI, que repete sempre
    as proibições — e a conferência da imagem por quem aprova.
29. **Formulário de evidência ou de texto oficial aberto** em outra etapa barra as ações que
    redesenham a tela até ser registrado ou cancelado.
