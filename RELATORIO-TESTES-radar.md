# Radar Artecon — Relatório de testes (v0.21.0)

Data: 12/10/2026. Resultado neste ambiente, com a suíte inteira da v0.21.0: **721 aprovados, 0 falhas, 61 pulados**. Os pulados são
os testes de tela que sobem a IA Central de verdade (pacote `ia-central`, fora deste repositório: aqui não há a pasta `../ia-central`). As funções
`radar-ia` e `radar-redes` rodam de verdade no Deno nos testes delas (`test_radar_funcao_ia.py` e `test_radar_funcao_redes.py`).
Entre a v0.7.1 e a v0.19.1 este relatório não foi atualizado: as seções da v0.21.0 e da v0.20.0 vêm logo abaixo e as seguintes são
das versões até a v0.7.1.

## v0.21.0 — aba Pauta, peças das redes e publicação agendada

São 80 testes novos (de 702 para 782 no total). O que foi comprovado, por área:

- **Banco** (`test_radar_banco.py`, 27 novos; 254 no arquivo):
  - a instalação tem 25 tabelas, 33 tabelas e visões e 7 configurações (com a `pauta`); as 10 funções novas da equipe estão na lista
    fechada e cada uma confere o papel; nenhuma função nova usa `current_date` ("hoje" é sempre o dia de Brasília); o setup não
    cria os esquemas `cron` nem `net`; a reversão tira a agenda (num `cron` de mentira) e as tabelas da Pauta; a configuração
    inicial e o "Honorário contábil" com `"redes": false`, também na instalação que já existe;
  - a importação cria e atualiza só a peça planejada, e para na linha errada sem repetir o conteúdo (RADAR173); o editor não forja
    aprovação, links nem situação, nem por inclusão nem por alteração direta; as transições permitidas e as recusadas; a peça
    aprovada não se edita, mas o plano e a sugestão da IA sim, sem mudar a versão publicável;
  - desfazer a aprovação (editor e administrador) cancela os envios e é recusado com envio "enviando" ou publicado; aprovar é só do
    administrador e confere a versão lida, as lâminas (quantidade, JPEG 1080×1350, do próprio usuário, de até 2 horas, com a
    identificação legal), as conferências obrigatórias e a hora (janela, 120 dias, agenda velha);
  - a lista de problemas: identificação legal, [VERIFICAR] e `{confirmar}`, fonte do boletim pago, números fora das informações
    conferidas e frase igual à do boletim; termo de imagem (sem termo, assinado depois, vencido, revogado, canal, finalidade,
    pessoa inativa); nome no texto sem estar marcado, sobrenome que o termo não autoriza e "contador" para quem não tem registro;
  - o início da publicação só na hora e uma vez; janela, agenda velha e termo vencido viram erro sem nome; a `radar_rede_iniciar`
    antiga recusa o envio da Pauta sem mudar nada (RADAR171); a agenda espera 10 minutos entre as tentativas, desiste na 3ª,
    respeita a janela e confere antes de disparar; duas conexões nunca pegam o mesmo envio; pausada nas Configurações, não dispara;
  - "Publicar agora" só remarca o erro com "Conferi … não saiu" e recusa a agenda velha; copiar e o registro manual conferem o modo,
    o termo de hoje e os links; a conferência da chave da agenda sem o Vault nunca confere;
  - a faxina das imagens não apaga foto nem lâmina da Pauta; a trilha de auditoria não guarda o plano, os nomes, o CRC nem a sugestão
    da IA; só o administrador grava pessoas, o editor lê, leitor e robô não leem; pessoa em uso não se apaga (RADAR174); o envio da
    Pauta tem regra própria e fica fora do robô do site; o painel conta as falhas da Pauta.
- **Agenda do banco** (`test_radar_agenda.py`, 6 novos, com `cron`, `net` e `vault` de mentira): o `sql/radar-redes-agenda.sql`
  cria a chave e agenda de 5 em 5 minutos sem a chave no comando gravado; o comando faz um pedido por envio vencido (a chave anon no
  `Authorization` e a da agenda no `x-radar-agenda`) e nenhum quando nada venceu; sem o setup da v0.21.0 para com o recado; recusa a
  chave `service_role` e a `sb_secret_`; a chave anon do SQL é a do `radar-config.js`; roda de novo sem duplicar, e a reversão tira
  tudo.
- **Função `radar-redes`** (`test_radar_funcao_redes.py`, no Deno; 11 novos, 33 no arquivo): a peça vai ao armazenamento privado e
  a Meta recebe o link assinado de 10 minutos, no Instagram e no Facebook (`/photos`), uma vez só; a nova tentativa assina de novo
  sem reenviar a imagem, e a falha ao assinar não publica; com a chave da agenda, só a peça vencida sai, e a notícia, a peça futura,
  a chave errada (curta, longa, junto com a sessão do administrador), `excluir`, `diagnostico`, `acionar_robo` e ação inventada são
  recusados; `agenda_teste` responde sem publicar (também sem a chave no Vault) e só à agenda; a chave interna nova vai só no
  `apikey`; o diagnóstico confere o armazenamento privado (público é recusado); a função nova com o banco antigo publica a notícia;
  os registros (log) não levam legenda, nome, link nem chave; `deno check` limpo. Os 2 testes antigos do diagnóstico passaram a
  procurar o item pelo nome (o item novo entra depois de "Armazenamento das imagens").
- **Função `radar-ia`** (`test_radar_funcao_ia.py`, no Deno; 8 novos, 36 no arquivo): a ação `peca` grava a sugestão conforme o
  formato (sem mudar a versão da peça) e conta como `gerar`; à IA não vão nomes (nem de pessoa inativa, nem em "quem aparece", nem
  nas informações conferidas, nem com parênteses), CRC ou link; o fato fora das informações conferidas vira [VERIFICAR] (a marca vai
  até o fim do número: "Lei nº 8.212"); "contador" perto de quem não tem registro e os termos viram aviso; as recusas não chamam a
  IA; a peça alterada durante a IA não é gravada (409); sem a tabela, a mensagem diz que falta o SQL; o erro inesperado vai ao log
  só com o nome. A mensagem do banco antigo do kit passou a citar o `radar-setup-v0.21.0.sql`.
- **Termos da Pauta** (`test_radar_publicidade.py`, no Node; 2 novos, 4 no arquivo): `TERMOS_PECA` é igual na tela
  (`radar-pauta.js`) e na função, e os casos (o que trava; o sentido técnico que não trava, como "desconto do INSS"; "presente"; "nº
  1") rodam nas duas.
- **Telas** (`test_radar_telas.py`, no Chromium; 21 novos, 209 no arquivo: 148 aprovados e 61 pulados):
  - importação do calendário: todos os erros de uma vez, com a linha; sem duplicar; vírgula, Windows-1252, CRLF e data curta; HTML
    vindo do CSV não executa; o leitor vê a Pauta sem botões, sem pessoas e sem a prévia da arte; a semana navega, mostra "Prontas
    para aprovar" e "Não saíram" e cabe no celular; sem o `radar-pauta.js` (ou com ele de outra versão) a aba pede Ctrl+F5, e com o
    banco antigo pede o SQL;
  - a peça grava com a trava de versão e, aprovada, não se edita; as fotos saem em 1080×1350, uma por vez, a HEIC com o recado, e o
    texto digitado e não salvo continua na tela; a agenda de domingo atravessa o mês, tira o honorário e vira informações conferidas;
  - a arte: faixa legal com a letra de pelo menos 28 px de altura medida, margem de 72 px, sem "Matéria completa" e sem o selo de SC
    de um assunto aberto antes;
  - "Salvar e marcar como pronta" mostra a lista do banco; aprovar é só do administrador, guarda as lâminas e mostra a hora e a
    agenda desligada; termo de promoção e de comparação travam; "Publicar agora" só remarca e, com a agenda desligada, chama a
    função; "Tentar de novo" pede "Conferi no Instagram e no Facebook: não saiu", e a peça parada em "publicando" cancela e a nova
    aprovação pede a mesma caixa; carrossel e reel à mão: baixar e copiar só depois de aprovado, e o registro do link;
  - Pessoas e termos: só o administrador grava, o CRC sai padronizado, cabe no celular; o Painel mostra a falha da Pauta (um cartão
    só); Publicações ignora o envio sem conteúdo; Configurações com o bloco da Pauta e a validação dele; o "Gerar com IA" da peça
    troca `{PESSOA1}` pelo nome e mostra o que falta.
  - Testes antigos que mudaram: a versão (v0.21.0) e o `versaoMenor` com a 0.20.0 e a 0.21.0; 7 formulários nas Configurações;
    "Pauta" na lista do celular; a mensagem do banco antigo cita o `radar-setup-v0.21.0.sql`; o `ia_de_mentira` ganhou o ramo
    `peca`; o servidor dos testes serve também o `radar-pauta.js`.
- **Robô** (`test_radar_e2e.py`; 2 novos, 72 no arquivo): o aviso da Pauta é um só e sem nomes (nem quando o erro cita um nome); não
  abre com a peça agendada no futuro, nem com a hora passada há 10 minutos, nem com "enviando" recente; a notícia com erro não conta;
  a leitura pede só 5 colunas; "Publicar agora" resolve e o aviso fecha; com o banco antigo, não abre nem fecha e os outros avisos
  seguem; erro 500 do banco continua erro. A versão do robô passou a 0.21.0.
- **Repositório** (`test_radar_repositorio.py`, novo; 3 testes): nenhum arquivo versionado tem o cabeçalho do calendário do plano
  (só a amostra inventada, `testes/amostras/pauta-ficticia.csv`, com nomes de mentira); o `.gitignore` barra o CSV do plano; e o
  workflow dos testes roda quando muda o `radar-pauta.js` (antes não rodava) ou o `radar-config.js`.
- **Prova de que os testes pegam o erro:** em cada etapa, cada correção foi desfeita sozinha (com a cópia guardada e restaurada, e
  o sha256 conferido no fim) e o teste ligado a ela falhou: banco e agenda, 21 de 21 (e um arquivo solto com o cabeçalho do
  calendário derrubou o teste do repositório); `radar-redes`, 14 de 14; tela, base e peça, 25 de 25; arte e aprovação, 34 de 34 (na
  1ª rodada passou o "Publicar agora visível ao editor": o teste do "Tentar de novo" foi reforçado com 2 canais e passou a pegar);
  "Gerar com IA" da peça (função e tela), 37 de 37; robô, 15 de 15; workflow dos testes sem o `radar-pauta.js`, 1 de 1.
- **Tempo:** a suíte inteira levou de 661 a 671 s (cerca de 11 minutos, em duas rodadas) neste ambiente. O limite do GitHub Actions
  (`radar-testes.yml`) continua em 20 minutos: na v0.20.0, o trabalho inteiro no GitHub (instalação e testes) levou menos de 9
  minutos, e pela soma das etapas a v0.21.0 acrescenta perto de 1 minuto de testes. O workflow passou a rodar também quando muda
  o `radar-pauta.js`, o `radar-config.js` ou o `.gitignore`.

O que não foi testado aqui: a Meta de verdade (a rota do link assinado veio do código do Storage do Supabase; que a Meta aceita o
link com `?token=…` só se confirma no 1º post pela agenda, com o administrador acompanhando); o pg_cron, o pg_net e o Vault de
verdade (o Postgres dos testes não os tem: os esquemas são de mentira, só com o que os arquivos usam), por isso o teste
`agenda_teste` é feito na instalação; os testes de tela com a IA Central de verdade (61 pulados; a resposta `peca` já está na
fixture, mas nenhum teste de tela com a função de verdade cobre a peça); a arte com a fonte DM Sans (o Google Fonts fica bloqueado
nos testes e a arte usou Arial); o tempo da conferência da frase do boletim pago com 90 dias de capturas reais; e a aba Publicações
da tela antiga com o banco novo no Supabase (no PostgREST 12.2.3 dos testes, o pedido com `in.(null)` não dá erro; o LEIAME pede
para não voltar a tela depois da 1ª peça aprovada por outros motivos: a tela antiga não mostra a Pauta nem pausa a agenda).

Achado, só para registro: o `sql/radar-itc-agenda.sql:12` usa `create extension if not exists pg_cron;`, sem o `with schema
pg_catalog` que a página "Install pg_cron" do Supabase mostra (o `sql/radar-redes-agenda.sql` segue a página). Esse arquivo nunca
rodou em produção e não foi mudado.

Precisam da confirmação do dono: os 28 px da faixa legal como altura da letra, como está (se for o tamanho da fonte, muda só
`FAIXA_LEGAL` em `radar-pauta.js`); a lista de termos que travam na Pauta (`TERMOS_PECA`), com o contador responsável (travam
também palavras que servem para informar, como "garante", "ganhe", "definitivo", "100%" e "a maioria"); e a máscara de nomes que
vai à IA, que não diferencia maiúsculas: uma palavra comum igual a um nome cadastrado também é trocada no texto que vai à IA (nada
vaza; só a sugestão pode ficar estranha).

## v0.20.0 — kit das redes, arte vertical, identificação legal e publicidade contábil

O que foi comprovado:

- **Banco** (`test_radar_banco.py`): gravar o `kit_ia` não muda o `atualizado_em` e não derruba a aprovação nem as autorizações
  do site e das redes (o `radar_rede_iniciar` continua valendo); mudar o texto marca o kit como desatualizado (o kit vazio não;
  um kit novo tira a marca; texto e kit gravados juntos não marcam; só o título, autor e fonte não marcam); o kit precisa ser um
  objeto de até 20.000 caracteres (o que passaria do limite com a marca vira `{"desatualizado": true}`); leitor e anônimo não
  gravam. O valor inicial da `assinatura` traz `cnpj` e `crc` vazios. Instalação, atualização das versões anteriores e reversão
  continuam passando.
- **Função `radar-ia`** (`test_radar_funcao_ia.py`, no Deno): a ação `kit` grava legendas, arte e roteiro e conta no consumo como
  `gerar`; à IA vão só o título e o texto da Artecon (nem o texto oficial nem o boletim pago; nenhum token), com a regra (12) e
  até 4.000 tokens; links, linhas com CNPJ, CRC ou telefone e hashtags saem do texto, o `{LINK DO SITE}` fica uma vez no Facebook e
  o "link na bio" no Instagram; termos da publicidade, número fora do texto e frase do boletim pago viram aviso (do boletim, sem
  repetir a frase); conteúdo alterado (409), inexistente (404) e texto para análise (400) são recusados; reel fora de 30 a 45 s vira
  aviso; banco sem a coluna explica que falta o SQL. O pedido da ilustração (à IA Central de mentira, `?acao=imagem`) passa a ser
  "ilustração editorial" com a paleta da marca, horizontal (1536×1024), com as proibições de sempre, sem "fotografia realista" nem
  "banco de imagens" e sem o texto oficial. Depois da revisão: "CRC" seguido de ano ("anuidade do CRC 2027", "o CRC em 2026") não
  sai do texto, só o número de registro, o CNPJ e o telefone, e só eles (a frase fica; a linha que sobra sem frase sai), com aviso;
  o corte no fim da frase não para em "art." nem em "nº."; o `{LINK DO SITE}` que fica é o da linha "Leia a matéria completa"; o
  texto na tela encurtado vira aviso; o aviso comprido perde os últimos itens inteiros ("e outros"), nunca um valor pela metade;
  título, texto e classificação do assunto vão à IA dentro do bloco de dados, com as marcas `<<<`/`>>>` trocadas; e o `deno check`
  da função passa limpo (o `deno run` dos outros testes não confere tipos).
- **Termos da publicidade** (`test_radar_publicidade.py`, no Node): a lista é a mesma na tela e na função; trava e aviso; acento
  na fronteira da palavra; "garantia do crédito" e "melhoria" não casam. Trava só a forma de oferta, de promessa e de convite
  ("consulta grátis", "primeiro mês de graça", "ganhe um brinde", "blinde seu patrimônio", "pague menos impostos com a Artecon",
  "troque de contador"); "grátis", "de graça", "pague menos", "blindar o patrimônio", "brindes", "blindados", "troca de contador"
  e "pagar menos imposto", que podem ser fato ou assunto da notícia ("emissor de NFS-e grátis para o MEI", "quem ganha até R$ 5
  mil pague menos Imposto de Renda", "holding não serve para blindar o patrimônio"), são aviso (e o "brinde" de "ganhe um brinde"
  não se repete no aviso).
- **Telas** (`test_radar_telas.py`, no Chromium):
  - identificação legal nas Configurações: CNPJ numérico e alfanumérico conferido pelos dígitos verificadores, CRC conferido;
    vazios, a tela avisa e continua com 6 configurações;
  - arte vertical de 1080×1350 com a faixa legal só com o que está nas Configurações (sem CNPJ e CRC, só o nome da empresa; nada
    provisório) e o selo de SC só na norma estadual; os campos da arte (chamada, apoio e fundo) redesenham a imagem nos dois
    quadros sem deixar a tela "com alteração não salva", e a imagem ainda pendente não é autorizada;
  - termo de trava na legenda ou na arte impede a publicação (passo da trilha, canais que faltam e "Publicar em todos", na legenda e
    na chamada da arte); marca [VERIFICAR] na chamada da arte também impede; "100%" e "brindes" vão para a confirmação; frase do
    boletim pago colada na legenda ou no apoio da arte não sai;
  - os botões de copiar do quadro "Kit das redes" recusam o kit com termo de trava (o que é copiado vai ao ar à mão); "Gerar kit das
    redes com IA" pede confirmação antes de trocar as legendas e a arte editadas (recusar não consulta a IA);
  - a chamada muda com um desenho da arte em andamento: a imagem continua pendente até o desenho novo (a arte antiga não pode ser
    autorizada); a capa desenhada pelo Radar (1200×630) não é oferecida como fundo da arte; o apoio de reserva não corta a frase
    em "art. 26";
  - "Gerar com IA" com a função antiga (o kit é "Ação desconhecida.") ou com o banco sem o SQL da v0.20.0 (503): o rascunho e a capa
    padrão saem, sem kit, e o recado em amarelo diz o que houve e aponta "Gerar kit das redes com IA";
  - "Gerar com IA": fundamentar (ou verificar), gerar e kit, com a capa padrão e nenhuma ilustração pedida; "Gerar texto com IA" e
    o texto para análise também ficam com a capa padrão; a ilustração sai pelo botão do conteúdo;
  - o quadro "Kit das redes": arte, as duas legendas já montadas (com a fonte, a identificação legal e as hashtags), o roteiro em
    tabela e os avisos, tudo como texto (HTML vindo da IA não executa); copiar as legendas e o roteiro (área de transferência do
    navegador); "Gerar kit das redes com IA" grava sem mudar a versão do conteúdo e troca o que estava digitado nas redes pelo kit;
  - a legenda do kit nas três caixas: `{LINK DO SITE}` só no "Publicar em todos", o link real no passo da trilha e nos canais que
    faltam; texto longo demais sai do fim do texto, nunca a identificação nem as hashtags (2.000 e 2.200 caracteres); e é a
    legenda da caixa que vai ao ar;
  - kit desatualizado (o texto mudou, ou o kit ficou só com `{"desatualizado": true}`): o quadro avisa e as redes voltam à legenda e
    à arte montadas pelo Radar; gerar de novo pede o texto salvo; quem só lê vê o kit, sem o botão; só o título mudar deixa o kit
    valendo, com o aviso para conferir a chamada da arte (no quadro do kit e embaixo da imagem);
  - no celular (375 px), a arte com os campos e o quadro do kit aberto, com a tabela do roteiro, não criam rolagem lateral.
- **Prova de que os testes pegam o erro:** em cópias temporárias, com erros de propósito, falharam os testes novos do banco (2
  de 3: o kit fora da exceção da data e sem a marca), da função (5 de 7), da tela da arte e dos termos (5 de 5) e da tela do kit (5
  de 5; o HTML do roteiro sem escapar e o kit que não limpa o que estava digitado, cada um sozinho, também derrubam o teste). Os
  arquivos foram restaurados e conferidos. Na rodada de correção da revisão, cada correção foi desfeita sozinha numa cópia e o
  teste dela falhou: 7 na função (ano do CRC, corte em "art.", link do Facebook, aviso do texto na tela, aviso cortado no meio,
  marcas do bloco de dados, tipos), 7 na tela (desenho em andamento, capa desenhada como fundo, cópia sem trava, troca sem
  confirmação, [VERIFICAR] e frase paga na arte, apoio cortado em "art.") e 1 no "Gerar com IA" sem kit.

- **Segunda revisão** (22 pontos; o que foi corrigido tem teste): a legenda editada antes de preencher o CNPJ e o CRC ganha a linha
  nova ao salvar as Configurações, e a legenda sem a linha vai para a confirmação; só o texto deixa o kit desatualizado (o título
  mudar deixa o kit valendo, guardado com o título de quando foi feito, e a tela pede para conferir a chamada); CNPJ sem aspas tem
  mensagem própria; o CRC de SC escrito de outro jeito ("SC-004064/0-5") sai "CRC-SC 004064/O-5", e o formato que não é
  reconhecido é recusado; a cópia da legenda do Facebook antes do site não leva o `{LINK DO SITE}`; com foto, o apoio tem 3 linhas
  (faixa da foto de 460 px; 36 px quando 40 não cabe), o que não cabe vira aviso embaixo da imagem e na confirmação, e os campos
  aceitam o que cabe (90 e 140); a palavra comprida da chamada baixa a letra em vez de sair espremida; a faixa legal fica em 24 px
  e quebra nos " · "; o fundo que falhou faz o autorizar mostrar o erro; os números fora do texto não contam item de lista nem o
  ",00"; o quadro do kit abre quando o recado aponta o botão; a trava dos termos ficou só com a forma de oferta, promessa e convite,
  e o recado diz onde está o termo; o setup devolve à `radar_concorrentes_conferir` (v0.19.1) o acesso do papel interno e a reversão
  a apaga; o setup acrescenta `cnpj` e `crc` vazios à assinatura que já existe; na função, mais de 8 cenas e cenas descartadas viram
  aviso, o marcador do link escrito de outro jeito ("[LINK DO SITE]", "{LINK}") vira o de verdade, o número de norma do CRC
  ("Resolução CRC-SC nº 1.234/2025") não sai do kit, e o pedido do kit vai a 4.000 tokens, com mensagem própria quando é cortado.
  Cada correção foi desfeita sozinha numa cópia do repositório e o teste dela falhou (29 de 29).

O que não foi testado aqui: os testes de tela que dependem da IA Central de verdade (entre eles, o kit pela função de verdade
dentro do "Gerar com IA" e a ilustração pedida pela tela; o teste da ilustração foi corrigido para confirmar a senha a partir da
2ª consulta, como a tela pede desde antes da v0.20.0, mas não rodou aqui — o texto do pedido é conferido no teste da função); a publicação real na Meta (a função `radar-redes` não mudou);
a arte com a fonte DM Sans (o Google Fonts fica bloqueado nos testes e a arte usou Arial: confira o primeiro post e o recorte da
grade do Instagram). A lista de termos e os níveis (trava ou aviso) e o formato da linha "empresa · CNPJ … · CRC-SC …" precisam
da confirmação do dono ou do contador responsável.

## v0.7.1 — manutenção e conforto

O que foi comprovado:

- **Atualização:** o SQL v0.7.1 foi aplicado por cima do SQL v0.7.0 (o que está em produção) com
  dados, duas vezes seguidas: capturas, conteúdos e imagens preservados, nenhuma execução pela metade.
  Também por cima da v0.6.0 e da v0.1.0, e a reversão continua apagando tudo.
- **Termos com pontuação:** "S.A.", "Ltda." e ".gov" pontuam (inclusive com vírgula colada depois);
  "SS.A." e "Ltdax" não. A tela aceita esses termos e recusa os que têm menos de duas letras ou números.
- **Imagens sem uso:** só o robô (service_role) apaga; administrador, editor e visitante são recusados.
  Ficam a imagem usada por um conteúdo e a enviada há menos de 24 horas. Banco ainda sem o SQL novo
  ou fora do ar não derruba a coleta.
- **Limite de tempo por fonte:** um padrão de links que nunca termina é cortado em 1 s (no teste) e a
  outra fonte coleta normalmente; valor inválido volta aos 5 minutos.
- **Diagnóstico:** lê as fontes ativas do banco (as desligadas ficam de fora); sem chave ou com o
  banco fora do ar, usa o arquivo. Página não reconhecida e página montada por JavaScript são descritas.
- **Texto não salvo:** sobrevive à queda da sessão; recuperar não grava sozinho; salvar e descartar
  apagam o rascunho; "Sair" pede confirmação e apaga os rascunhos.
- **"Mostrar mais":** 160 capturas e 301 assuntos — o botão traz o resto e some no fim; trocar o filtro
  recomeça a contagem.
- **Número da edição** acompanha o ano do mês, sem trocar o que foi digitado; **lembrete de capa**
  aparece ao salvar título novo e some ao gerar a capa.
- **Função de IA da versão anterior** (v0.7.0) não é apontada como antiga pelo painel v0.7.1.
- **Aviso de fonte com falha:** a fonte que falha 3 coletas seguidas abre um aviso só (a 4ª falha
  não repete), com o erro e o que fazer; ao voltar a funcionar, o aviso é comentado e fechado.
  Fonte desligada ou apagada fecha o aviso e não abre outro. Pull request e outros avisos do
  repositório não são confundidos; sem as variáveis, ou com o banco ou o GitHub fora do ar, a
  coleta não fica vermelha.
- **Link publicado fora do ar:** o link que responde 404 ou 410 abre um aviso (um por link, mesmo
  com vários registros dele); erro de rede e 200 não contam; endereço que não é http(s) nem é
  acessado; o aviso fecha quando o link volta ou deixa de estar registrado.
- **Tabela no texto:** "\\|" vira uma barra dentro da célula (também no fim da linha), igual no
  painel e no Informativo.
- **Workflows em Node 24:** o diagnóstico rodou no GitHub com as ações novas, sem o aviso de Node 20.

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

1. **Atos normativos da Receita fora do ar para o robô (desde 04/10/2026):** o endereço da
   consulta (`sijut2consulta/consulta.action`) passou a abrir o novo sistema "Normas", que monta a
   tela por JavaScript; a página chega sem nenhum ato e a fonte `rfb-normas` fica em
   "vazio suspeito". Os dados vêm de `POST /api/indexacao/ato/pesquisar`, mas essa API responde
   403 ("Request forbidden by administrative rules") ao acesso automático feito do GitHub, mesmo
   com o filtro idêntico ao da página. Até haver outro caminho (o DOU pelo INLABS, por exemplo),
   as instruções normativas chegam só pelas notícias da Receita. Antes disso, só a ementa era
   capturada (sem texto integral).
2. **Verificação da IA tem limites:** não lê números por extenso, incisos nem normas sem
   número, e não avalia a interpretação.
3. **Teto mensal de tokens** pode ser ultrapassado por pedidos simultâneos; a trava real é
   o limite de gasto na conta da OpenAI.
7. **Diário Oficial da União** fora desta versão.
16. **Texto oficial incluído pela equipe depende de quem inclui:** o sistema limita o
    endereço ao site da fonte e marca a origem, mas não compara o texto colado com a
    página. Um editor sozinho consegue satisfazer a exigência de fonte oficial.
13. **O Radar confere só se o link do site abre:** a notícia retirada (404/410) gera aviso por
    e-mail, mas texto alterado no site não é percebido, e o registro continua dependendo de
    alguém informar o link certo.
14. **Tabela `radar_publicacoes` sem uso:** continua no banco, com as regras antigas, e
    ainda pode ser gravada por um editor pela API (nenhuma tela mostra essas linhas).
15. **Assunto com dois conteúdos:** ao registrar um, o assunto passa a "Publicado" e sai da
    lista "Em andamento"; o outro conteúdo aparece pela aba Publicações.
8. **Edição fechada não guarda cópia dos artigos:** o registro definitivo é o PDF salvo.
   Alteração posterior é avisada, não impedida.
10. **Tabela no texto:** a linha de título não se repete quando a tabela atravessa a página
    (para uma barra dentro da célula, escreva "\\|").
19. **Relevância é por palavras:** uma notícia importante escrita sem nenhum dos termos
    fica como baixa. Vale olhar o filtro "Baixa relevância" de vez em quando e ajustar a
    lista.
21. **A capa automática não é refeita sozinha** quando o título muda (o banco não guarda se a
    imagem é a capa padrão, uma foto enviada ou a ilustração da IA, e trocar sozinho poderia
    apagar uma imagem escolhida): ao salvar um título novo, a tela avisa ao lado da imagem.
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
