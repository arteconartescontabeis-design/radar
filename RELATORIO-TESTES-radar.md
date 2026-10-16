# Radar Artecon — Relatório de testes (v0.26.0)

Data: 16/10/2026. **A suíte inteira da v0.26.0 roda no GitHub (CI) antes de juntar**; neste ambiente rodaram o arquivo inteiro dos testes
de tela (`testes/test_radar_telas.py`) e o `testes/test_radar_repositorio.py` (resultados na seção da v0.26.0, logo abaixo). Na v0.25.1
(16/10/2026), a suíte inteira deu **1.051 aprovados, 0 falhas, 67 pulados**, em 1.171 s (19min30s); a v0.26.0 tem 13 testes novos (de
1.118 para 1.131 no total). Dos pulados, 61 são os testes de tela que sobem a IA Central de verdade (pacote `ia-central`, fora deste
repositório: aqui não há a pasta `../ia-central`), 3 são os da transcrição com o Speech SDK de verdade (o SDK não está instalado neste
ambiente; o CI instala), 2 são os do contêiner do ffmpeg (aqui o `docker` não tem o serviço rodando) e 1 é o dos commits do push, que só
roda no `radar-repositorio.yml` (precisa do commit de antes do push). Na v0.25.0 (depois da revisão, 16/10/2026), a mesma suíte deu 1.048
aprovados, 0 falhas e 67 pulados, em 1.000 s; na v0.24.0 (até a etapa 5, 15/10/2026), 1.039 aprovados; na etapa 1 da v0.24.0, 1.025;
na v0.23.0, 996. As funções `radar-ia`, `radar-itc`, `radar-redes`, `radar-concorrentes` e `radar-video` rodam de verdade no Deno nos
testes delas, e o ffmpeg do corretor de vídeo roda de verdade. Nenhum teste chama a Microsoft, a Azure, o GitHub, o Supabase, a OpenAI
ou a IA Central de verdade; todo boletim da ITC dos testes é inventado, toda pessoa é fictícia ("Ana Teste", domínios `.test`), nenhuma
imagem de teste tem pessoa (são cores lisas e formas desenhadas na hora), e todo vídeo e toda voz são **sintéticos**, gerados na hora.
Entre a v0.7.1 e a v0.19.1 este relatório não foi atualizado: as seções da v0.26.0, da v0.25.1, da v0.25.0, da v0.24.0 (etapas 5 e 1),
da v0.23.0, da v0.22.0, da v0.21.0 e da v0.20.0 vêm logo abaixo e as seguintes são das versões até a v0.7.1.

## v0.26.0 — o assunto em 3 passos (Preparar · Conferir e aprovar · Publicar)

Só a tela muda (o banco continua no `sql/radar-setup-v0.25.0.sql`; as funções e o robô não mudam). São **13 testes novos** (12 de tela e 1
do repositório) e 24 ajustados (23 de tela e 1 do repositório). Resultado neste ambiente, depois da revisão: `testes/test_radar_telas.py`
inteiro, **217 aprovados, 0 falhas, 61 pulados**, em 513 s (os pulados são os da IA Central de verdade); `testes/test_radar_repositorio.py`, **16 aprovados, 0 falhas,
1 pulado** (o dos commits do push); `testes/test_radar_publicidade.py`, **4 aprovados**. **A suíte inteira roda no GitHub (CI) antes de
juntar**; aqui ela não foi rodada. Estes resultados saíram da fila compartilhada dos testes (o mesmo banco de teste e as mesmas portas da
outra equipe, uma rodada de cada vez). Antes da revisão, com a fila parada, o mesmo arquivo tinha rodado num banco de teste só desta
etapa: 215 aprovados, 0 falhas, 61 pulados. Uma verificação à parte, fora dos testes,
desenhou a trilha em 18 situações (os ramos 1a a 1e, 2a a 2c, o passo 3 em cada estado, fora do site e assunto ignorado) para o
administrador, a editora e quem só lê, com um servidor de mentira dentro do navegador: nenhum erro de página e nenhuma das frases que
os testes clicam sem escopo ("Novo conteúdo", "Registrar publicação no site", "Gerar texto com IA", "Concluído"…) dentro da trilha.

- **Os 3 passos** (`test_assunto_em_tres_passos_do_preparar_ao_publicar`): a barra e a trilha com 3 passos ("Preparar", "Conferir e
  aprovar", "Publicar"); no passo 1, "Preparar a publicação", o tamanho do texto ao lado do "Preparar com IA" e "Escrever sem IA" em "Mais
  opções"; os passos 2 e 3 "Aguardando", sem botões. O Preparar faz, numa consulta só e sem a senha, o trecho, o texto, a capa padrão
  (1200×630), a conferência e o kit ("fundamentar", "gerar", "revisar" com o `lido` e "kit") e deixa o texto "em revisão". Sem o trecho
  que comprova, o passo 2 não oferece "Conferi na fonte oficial"; com ele, oferece; confirmado, aprova pela trilha e o passo 3 mostra
  "Site: falta · Instagram: depois do site · Facebook: depois do site" e o "Publicar em todos (site, Instagram e Facebook)". Aprovado
  sem a confirmação, "Para o site: confirmar o assunto" fica no passo 3 (a trilha não volta). Passos feitos: 0 → 1 → 2.
- **A Conferência dentro do Preparar** (`test_preparar_confere_os_10_criterios_de_verdade_e_nao_marca_confirmado`, com a conferência
  de verdade): os 10 ✓ no passo 2, o formulário em `data-conferencia="ok"` e o Aprovar ligado; o aviso mostrou "Preparar · etapa 1 de 4"
  e "Preparar · etapa 3 de 4 — A IA está conferindo o texto…" (com a etapa 3 segurada para o print); a situação da confirmação do assunto
  não muda e não há pedido de imagem.
- **O tamanho ao lado do botão e o trecho já conferido** (`test_preparar_usa_o_tamanho_ao_lado_e_pula_o_trecho_ja_conferido`): "Longo
  (artigo)" no seletor da trilha vale para os três seletores e vai no "gerar"; com o trecho oficial já conferido, o Preparar não busca
  outro ("gerar", "revisar", "kit") e usa o tamanho do seletor ao lado do botão; sem texto capturado, não há Preparar e o "Novo conteúdo
  (sem IA)" cria o rascunho com o tamanho escolhido.
- **"Preparar este texto"** (`test_preparar_este_texto_completa_o_rascunho_do_robo_sem_escrever_outro`): o rascunho do robô fica em
  "Preparar o rascunho" ("preparado pelo robô"); o Preparar completa o mesmo texto ("fundamentar", "revisar", "kit"; um conteúdo só),
  tira o [VERIFICAR] do título, refaz a capa feita agora com o título novo e a conferência continua valendo; o texto que virou rejeitado
  em outra tela não chama a IA ("Este texto não está mais em rascunho").
- **Falha no meio** (`test_preparar_com_falha_no_meio_deixa_cada_passo_claro`): o "gerar" com 500 não grava nada e o passo 1 continua;
  a conferência com 502 deixa o texto "em revisão" com os 10 "?", "Conferir com IA" e o Aprovar desligado (e o recado diz isso); o kit com
  400 aponta o botão do kit e, no passo 3, a legenda é a montada pelo Radar.
- **Conferir e aprovar** (`test_conferir_e_aprovar_mostra_os_10_criterios_e_trava_o_aprovar`): os 10 "?" e o Aprovar desligado; "Revisei
  e assumo" não aparece com "?" só; "Conferir com IA" usa o "Revisar com IA" do quadro; com ✗ no 7, o motivo aparece e a editora não tem
  "Revisei e assumo"; o administrador assume pela trilha e aprova. A lista da trilha não repete o quadro (`data-item` só no formulário).
- **Travas do Aprovar da trilha** (`test_aprovar_pela_trilha_continua_com_todas_as_travas`): desligado com [VERIFICAR] (e, forçado, o
  formulário recusa), com o trecho igual ao da fonte e com o campo Fonte vazio, com o resumo do que falta; o Informativo esperando e o
  texto rejeitado não têm Aprovar na trilha.
- **Informativo** (`test_informativo_no_passo_2_e_a_liberacao_na_linha_da_fonte`): "Autorizar o Informativo" no passo 2, com "vale para
  o assunto inteiro"; autorizado, "Conferir e aprovar o texto" e a liberação na linha da fonte do passo 1 (motivo e "Desfazer"); desfeita,
  volta; o rótulo do "Publicar mesmo assim" diz que libera o Informativo do assunto.
- **Os 3 canais** (`test_publicar_mostra_os_tres_canais_e_so_conclui_com_cada_um_resolvido`): as linhas do site (publicado), do
  Instagram (da vez) e do Facebook, sem botões; o passo 3 só fica feito com cada rede publicada ou "Não publicar", e o "Concluído" diz
  "(o Facebook ficou de fora)"; quem só lê vê as linhas, sem "Desfazer".
- **Cancelar só uma rede** (`test_cancelar_so_uma_rede_que_ia_junto_com_o_site`): com a confirmação recusada, nada muda; aceita, só o
  Instagram é cancelado (o Facebook continua junto com o site e o site continua autorizado).
- **Numeração antiga** (`test_radar_repositorio.py::test_tela_sem_a_numeracao_antiga_dos_passos`): fora da aba Versões, a tela não fala
  mais dos passos de antes ("passo 4", "2. Escrever", "4. Publicar no site", "passos7"…).
- **Ajustados:** os testes da trilha passaram para os 3 passos (`data-passo` preparar/conferir/publicar, as linhas `data-canal` do passo
  3, "Preparar a publicação", "Preparar o rascunho", "Conferir e aprovar o texto", "✓ Conferi na fonte oficial", os nomes das etapas
  "1. Preparar" e "2. Conferir e aprovar"); os do "Gerar com IA" passaram a esperar o "revisar" antes do kit e o texto "em revisão"; os de
  versão, a v0.26.0 (a `FUNCAO_MINIMA` continua "0.25.0"); o do celular ganhou o print dos 3 passos. No `test_radar_repositorio.py`, a
  `radar-ia` pode ficar na versão em que mudou por último (0.25.1), nunca à frente da tela.
- **Mutações** (cada uma derrubou o teste dela, e o `index.html` foi restaurado da cópia): **14 mutações**, todas derrubaram o teste delas: o "✓ Aprovar" nunca desligado (novos 6 e
  7); o Preparar sem a etapa "revisar" (novos 1 e 2); o Preparar marcando "confirmado oficialmente" (novo 2); o Preparar sem levar o texto
  para "em revisão" (novo 1); o filtro do status aceitando o rejeitado (novo 4); o Preparar ignorando o `data-id` e escrevendo outro texto
  (novo 4); a busca do trecho mesmo com trecho conferido (novo 3); o tamanho lido só da barra do passo 2 (novo 3); "Revisei e assumo" na
  trilha também com "?" (novo 6); o passo 3 feito só com o site (novo 9 — a 1ª versão do teste não pegava: ganhou a conferência do
  círculo "3" enquanto falta rede); "Desfazer" e "Cancelar só o …" sem a conferência do administrador (novo 9 e
  `test_trilha_desfaz_a_liberacao_e_leitor_nao_ve_botoes`); "Cancelar só o Instagram" chamando o cancelamento do site (novo 10); o passo
  2 do Informativo sem o `data-informativo` (`test_informativo_so_publica_depois_da_autorizacao_do_administrador` e novo 8); a lista da
  trilha com `data-item` (novo 6).
- **Revisão** (7 achados, 2 deles o mesmo; os 6 problemas foram reproduzidos por um teste que falhava antes e corrigidos):
  - Texto Informativo cuja conferência falhou no Preparar: o recado manda clicar em "Conferir com IA", mas o passo 2 ("Autorizar o
    Informativo") não tinha esse botão. Agora tem, com "?" ou ✗, para a editora e para o administrador (a conferência não depende da
    autorização). Teste: `test_preparar_com_falha_no_meio_deixa_cada_passo_claro`, com um assunto só de fonte não oficial (print 56b).
  - "Preparar este texto" num assunto sem texto oficial: o recado mandava "conferir na fonte oficial". Agora diz que o site exige o
    texto oficial (o passo 3 mostra como resolver) e o Informativo Mensal, não. Novo: `test_preparar_este_texto_sem_texto_oficial_nao_manda_conferir_na_fonte`.
  - "Preparar este texto" com texto digitado e não salvo neste navegador (quadro "Texto não salvo"): não chama mais a IA; abre o passo 2
    com o quadro à vista e pede para recuperar e salvar, ou descartar, como o "Revisar com IA". Teste: o do rascunho do robô, no modo
    "um passo de cada vez".
  - A capa refeita com o título novo que não sai: a capa feita antes, com o título antigo (que podia ter o "[VERIFICAR]"), agora fica
    com o lembrete de refazer, no recado e no conteúdo. Novo: `test_preparar_este_texto_avisa_quando_a_capa_nova_nao_sai`.
  - A linha da fonte do passo 1, com o texto aprovado que não vai ao site, dizia "falta você confirmar (no passo 3)"; agora diz "no
    passo 2", onde o botão está (no aviso do alto da seção). Teste: o dos 3 passos, nos dois modos de exibição.
  - Quem só lê: a conferência de que não vê "Preparar este texto", "Conferir com IA" nem "✓ Aprovar" estava só num teste pulado (sem a
    IA Central). Agora `test_assunto_leitor_ve_os_passos_sem_botoes` abre o rascunho e o texto em revisão e confere que não há botão na
    trilha.
  - **7 mutações** (cada uma desfaz uma correção; o `index.html` foi restaurado da cópia), todas derrubaram o teste delas.
  - Não procede, em parte: a linha da fonte com o texto rejeitado diz "no passo 2" e está certa, porque o botão "✓ Conferi na fonte
    oficial" fica no aviso "Ainda não pode ser publicado no site", no alto da seção do passo 2, que é a que abre nesse caso.
- **Fora do plano, de propósito:** a capa refeita com o título novo não deixa 2 imagens no banco (o gatilho `radar_fn_imagem_sem_uso`
  apaga a que ficou sem uso): o teste confere que foram desenhadas 2 capas e ficou 1, a nova. E o passo 2 do Informativo tem também o
  "Conferir com IA" (o plano previa só o "Autorizar…"): sem ele, o recado do Preparar mandava para um botão que não existia.
## v0.25.1 — legenda do Radar com os itens de lista em linhas próprias, kit das redes sem a arte e rótulo único da imagem

São 3 testes novos (de 1.115 para 1.118 no total) e 18 ajustados — 7 só pelo número da versão (a função `radar-ia` e os scripts na
v0.25.1). Cada parte foi conferida desfazendo-a no arquivo (o teste falha) e restaurando: **11 mutações** (7 na tela, 3 na função
`radar-ia` e 1 na aba Versões), todas derrubaram o teste delas:

- **Legenda montada pelo Radar** (`test_radar_telas.py`, 1 novo: `test_legenda_montada_pelo_radar_poe_os_itens_de_lista_em_linhas_proprias`):
  um conteúdo com a imagem da IA e um texto com parágrafo, subtítulo, lista ("- item", com **negrito** num deles, "eSocial" e "30 dias")
  e parágrafo depois da lista. No passo do Instagram e no "Publicar nos canais que faltam" (Facebook), a legenda inteira é a esperada:
  o título, o parágrafo, cada item na sua linha como "• Item" (a inicial maiúscula; "eSocial" e "30 dias" como estão; sem o negrito; sem
  o subtítulo), o parágrafo seguinte na linha dele, o caminho até o site, a fonte, "Imagem ilustrativa gerada por IA." e a identificação
  legal no fim e, no Instagram, as hashtags; nada de "transição. revisar" nem "produtos; confirmar". No "Publicar em todos" (2.000, com o
  `{LINK DO SITE}`), o mesmo. No limite (360 e 450 no Instagram, 300 e 400 no Facebook) a legenda é exatamente o título e as primeiras
  linhas inteiras do resumo (nenhum item pela metade), com o aviso de IA, a identificação e as hashtags inteiros. Os marcadores "1. ",
  "2) ", "* " e "• " também viram "• " ("e-CAC" fica como está; "“lucro presumido”" vira "“Lucro presumido”"; "3 dias depois…", sem
  marcador, não é item). O resumo que passa de 600 caracteres (um item comprido, sem ponto) para no fim da linha de antes, sem o item
  pela metade. Sem lista, o resumo é o de antes (os parágrafos numa linha só). Mutações: os itens emendados como antes, o item sem a
  inicial maiúscula, "1. item" sem ser item e o corte dos 600 só no ponto (como antes).
- **Kit das redes sem a arte — função `radar-ia`** (`test_radar_funcao_ia.py`, 6 ajustados): o kit imitado da IA não tem mais a
  "arte"; o pedido tem o esquema `required` = instagram, facebook e reel (sem a propriedade "arte") e as instruções sem a regra da arte
  ("'chamada'", "'apoio'", "linha de apoio"), com as letras de (b) a (f); o kit gravado não tem a chave "arte", mesmo quando a IA a
  devolve fora do esquema (com HTML e link, que também não entram); sem as legendas, o kit não é gravado ("A IA devolveu o kit
  incompleto (sem as legendas)"); os termos de publicidade e a marca [VERIFICAR] que estavam na arte do teste passaram para o gancho e a
  chamada final do reel (os mesmos avisos); o "CRC em 2026" que estava no apoio passou para o gancho (fica, não é registro). A peça da
  Pauta (`peca`) continua pedindo e devolvendo a arte (os testes dela não mudaram). Mutações: o esquema ainda pedindo a arte, as
  instruções ainda com a regra da arte e a arte da resposta entrando no kit.
- **Kit das redes sem a arte — tela** (`test_radar_telas.py`, 1 novo: `test_kit_sem_a_arte_vale_e_o_kit_antigo_com_a_arte_continua_valendo`,
  e 3 ajustados): o kit da função nova (sem a arte) vale — as legendas dele entram no passo da trilha, nos canais que faltam e no quadro
  "Kit das redes" ("gerado em", o roteiro); o kit gravado antes, com a arte, continua valendo igual, e a arte não aparece em lugar nenhum
  da tela (nem no que está fechado), sem erro de página. O `KIT_EXEMPLO`/`KIT_TELA` dos testes perdeu a arte (o `KIT_ANTIGO` é o de
  antes, com ela). Mutação: a tela exigindo a chamada da arte (como na v0.25.0: o kit novo caía em "incompleto").
- **Rótulo único da imagem** (`test_radar_telas.py`, 1 novo: `test_campo_de_arquivo_da_imagem_tem_um_rotulo_so_com_a_mesma_aparencia`):
  o campo de arquivo da imagem tem um rótulo só, "enviar uma foto própria" (`label[for]`, `input.labels` e o `get_by_label` do
  Playwright); "Imagem da publicação" não é mais rótulo, é um título (`div.rotulo`) com a mesma aparência de um rótulo no mesmo lugar
  (letra, tamanho, peso, cor, margens, altura de linha e tamanho na tela iguais); nenhum rótulo do formulário aponta para campo que não
  existe; quem só lê não tem o campo nem rótulo para ele, e o título continua. Mutações: os dois `<label for>` de volta e o título sem
  a aparência de rótulo.
- **Versão** (`test_radar_telas.py`, 2 ajustados com conteúdo e 3 só pelo número; `test_radar_funcao_ia.py`, 4 só pelo número): a aba
  Versões abre com a v0.25.1 (os três ajustes em português simples e "Administrador: instalar a radar-ia 0.25.1; o banco não muda"), e
  as entradas seguintes passam uma posição; a `FUNCAO_MINIMA` continua "0.25.0" (a tela nova funciona com a função da v0.25.0: o kit
  dela traz a arte, que a tela ignora), com a tela na v0.25.1. O `test_radar_repositorio.py` não mudou: ele lê as versões dos próprios
  arquivos (a tela, os scripts, a função, o LEIAME, o relatório) e passou com a v0.25.1 e o banco na v0.25.0. Mutação: a entrada da
  v0.25.1 sem o item do kit.

## v0.25.0 (etapa 6) — uma imagem só para o site, o Instagram e o Facebook, com aparência de foto e o aviso de IA no canto

São 15 testes novos — 11 inteiramente novos (4 deles da revisão, abaixo) e 4 que reescrevem, com nome novo, um teste antigo cuja regra
mudou (a ilustração plana, a capa refeita com a ilustração, a arte vertical e o "Revisar com IA" que refazia a capa) — e 2 testes da
arte vertical das notícias que saíram com ela (os campos que redesenham a arte e o texto que não cabia nela): de 1.106 para 1.115 no
total, como a v0.24.0 e esta versão coletam neste ambiente. 33 testes antigos foram ajustados (11 deles só pelo número da versão). Cada
parte foi conferida desfazendo-a no arquivo (o teste novo falha) e restaurando: **36 mutações** (6 na função `radar-ia`, 25 na tela, 3
no banco e 2 no robô do site), todas derrubaram o teste delas:

- **Função `radar-ia`** (`test_radar_funcao_ia.py`, 3 novos e 3 ajustados): o pedido da imagem é de **fotografia realista de estilo
  editorial** (luz natural, profundidade de campo, cores naturais, de preferência sóbrias, ambiente brasileiro de trabalho), sem a regra
  fixa da v0.20.0 ("Ilustração editorial digital, plana", "figuras estilizadas", a paleta da marca); `quality: "high"`, `size:
  "1536x1024"`, modelo `gpt-image-2` (o padrão do `RADAR_IA_MODELO_IMAGEM`); a cena pedida vem logo depois do estilo, as preferências do
  escritório depois dela e antes da composição (3:2, o essencial no centro, o canto inferior direito livre), e as proibições por último,
  sempre (agora também a cena que induz a erro: documento oficial simulado, fachada de órgão público com nome, dinheiro em destaque). A
  descrição de 500 caracteres passa inteira e a de 501 é recusada antes de gerar; o filtro de marca, logotipo, pessoa conhecida e estilo
  de autor vale no texto inteiro (também depois dos 200 primeiros caracteres). A IA Central que recusa a qualidade alta (pela mensagem
  dela ou da OpenAI) vira o recado para o administrador, num pedido só (sem cair para "medium") e sem consumo registrado; outro erro da
  imagem continua com a mensagem de antes. Mutações: a qualidade "medium", a regra fixa da ilustração plana de volta, sem a proibição da
  cena que induz a erro, as preferências fora do pedido, a descrição até 200 e a recusa da qualidade alta sem o recado.
- **Tela: a imagem da publicação** (`test_radar_telas.py`, 2 novos e 3 ajustados): "Gerar imagem com IA" grava **uma** imagem, a da IA,
  inteira, em 3:2, guardada também como a ilustração (imagem_id = ilustracao_id) — os pontos da imagem gravada mostram o azul da imagem
  da IA no alto (nada de logotipo, título ou degradê) e o aviso no canto inferior direito (a faixa escura com a letra branca); a capa
  antiga sai do banco. "Usar a capa padrão Artecon (sem imagem)" mantém a imagem da IA guardada e mostra "Usar a imagem da IA de novo",
  que a traz de volta sem nova consulta; a foto própria vai em 3:2 (900×900 vira 900×600), sem aviso; o aviso de título mudado só aparece
  com a capa padrão; a prévia do site termina com "Imagem ilustrativa gerada por IA." só com a imagem da IA. O conteúdo antigo (a capa
  1200×630 montada com a ilustração crua) não muda ao abrir; "Usar a imagem da IA de novo" faz dela, sem consultar a IA, a imagem em 3:2
  (945×630) com o aviso, e o critério 6 do banco passa de ✗ a ✓. A imagem criada e não gravada é gravada de novo ("Gravar a imagem de
  novo") como uma imagem só, em 3:2. Mutações: a imagem da IA sem o aviso, a capa com o título por cima, a imagem da IA não guardada
  como a ilustração, a capa padrão apagando a imagem da IA guardada, a foto fora de 3:2, o lembrete de título mudado com qualquer imagem, a prévia
  sem a linha e o "Usar a imagem da IA de novo" sem refazer a antiga em 3:2.
- **Tela: as redes** (`test_radar_telas.py`, 3 novos e 16 ajustados): o passo de cada rede, o "Publicar em todos" e o "Publicar nos
  canais que faltam" mostram a imagem da publicação, a mesma do site (o mesmo data URL de `radar_imagens`), e o que vai para
  `radar_redes_envios.imagem` (no Instagram, no Facebook e nos dois de uma vez) são **os mesmos bytes**; nada da arte vertical aparece
  (chamada, apoio, fundo, corte). A legenda continua com a identificação legal antes das hashtags (sem CNPJ e CRC, só o nome da empresa e
  o aviso do que falta); com a imagem da IA, as legendas montadas e as do kit ganham "Imagem ilustrativa gerada por IA." logo antes da
  identificação, nunca cortada, e a legenda sem a linha não é autorizada. Sem imagem nenhuma, os quadros das redes mostram o aviso e o
  "Publicar em todos" não autoriza nada. Os termos da publicidade e a frase do boletim pago passam a ser conferidos só na legenda; o kit
  das redes não mostra mais a chamada e o apoio da arte. Mutações: as redes com a imagem regravada (outros bytes), a legenda sem a linha
  do aviso, a legenda sem a linha autorizada e as redes saindo sem imagem.
- **Banco** (`test_radar_banco.py`, 1 novo e 5 ajustados só pelo número da versão da instalação): o critério 6 atende com a imagem da IA
  em uso (imagem_id = ilustracao_id, em 3:2) e com ela guardada fora da publicação (a capa padrão ou a foto no lugar, sem mudar a versão
  da conferência); a capa antiga montada com a ilustração crua (1200×630) continua ✗ sem o aviso escrito no texto (com o motivo novo, que
  aponta "Usar a imagem da IA de novo") e ✓ com ele; a crua posta como imagem continua ✗. Mutações: o critério como na v0.24.0, a
  guardada fora da publicação não reconhecida e a imagem da IA aceita sem conferir o 3:2.
- **Robô do site** (`test_radar_site_publicar.py`, 1 novo): a capa da notícia é a imagem da publicação, com os mesmos bytes; com a imagem
  da IA, o texto termina com "Imagem ilustrativa gerada por IA." depois dos créditos (e depois de "Conteúdo informativo"); com a foto, a
  capa padrão ou a capa antiga (imagem_id diferente da ilustração), não. Mutações: sem a linha e a linha também na capa antiga.
- **Versão** (`test_radar_telas.py`, ajustado): a aba Versões abre com a v0.25.0 (os pontos da imagem única, do aviso, da qualidade
  alta, dos botões e da instalação), a função `radar-ia` e a tela na v0.25.0, o SQL (setup e reversão) renomeado para a v0.25.0 e citado
  no aviso da Pauta e do corretor de vídeo; a `radar-redes` continua na v0.22.0 (atende à mínima). O `test_radar_repositorio.py` não
  mudou: ele lê as versões dos próprios arquivos (a tela, os scripts, as funções, o SQL e o LEIAME) e passou com a v0.25.0.
- **Revisão da v0.25.0** (`test_radar_telas.py`, 4 novos e 2 ajustados), dos achados dos revisores: (1) a imagem da publicação aparece
  **inteira** nos quadros das redes (o passo da trilha e os canais que faltam) e na prévia "Ver como fica no site": a caixa tem a mesma
  proporção da imagem (1,5 na 3:2; antes, a caixa 4:5 da arte vertical mostrava só o miolo e a prévia cortava 380 px de altura, e o aviso
  do canto sumia); (2) o conteúdo antigo (a capa montada e a ilustração crua 1200×630 guardada) trocado pela capa padrão ou por uma foto
  guarda a imagem da IA já em 3:2 (945×630), com o aviso, sem consultar a IA — o critério 6 do banco passa a atender, a tela diz "Capa
  padrão da Artecon" ou "Foto ou imagem enviada pela equipe", "Usar a imagem da IA de novo" continua, a confirmação não fala em
  "refazer"; a crua que não pode ser lida sai, como na v0.24.0; (3) a capa antiga montada com a ilustração vai às redes com a linha
  "Imagem ilustrativa gerada por IA." nas legendas (a legenda sem ela não é autorizada), e a tela diz o que ela é; sem a crua guardada,
  nada da linha; (4) a foto enviada antes da v0.25.0 fora de 4:5 a 1,91:1 (900×1200, 2400×1000) tem o aviso no quadro e não autoriza o
  Instagram — no passo da trilha, nos canais que faltam e no "Publicar em todos" (que não deixa nem o site sair) —; desmarcado o
  Instagram, o Facebook (e o site) vão; 1080×1350, 1200×630, 1500×1000 e 1910×1000 servem. **13 mutações**, todas derrubaram o teste
  delas: a caixa 4:5 de volta nas redes, a prévia cortada de volta, a capa padrão e a foto sem guardar a IA em 3:2, a crua ilegível
  travando a troca, a confirmação dizendo "refazer" na capa montada, a capa antiga sem a linha na legenda e sem exigi-la, cada um dos três
  caminhos das redes sem conferir a proporção, o limite de 4:5 exclusivo e o quadro sem o aviso da proporção.

Os 2 testes de tela que sobem a IA Central de verdade e geram a imagem foram ajustados (botão, recado, imagem 3:2, `quality: "high"`; o
custo da imagem em qualidade alta não é mais conferido pelo valor, que é o da tabela da IA Central) — são pulados aqui.

Também na revisão, o `test_peca_nao_publicar_neste_canal_com_o_outro_ja_publicado` (Pauta, `test_radar_telas.py`) dependia do dia em
que a suíte roda (na madrugada de sexta-feira, 16/10, a peça de "daqui a 3 dias" caía na semana seguinte e a tela não a achava na semana
aberta; falhava igual no código da v0.24.0): agora ele abre a segunda peça pela semana dela. Com isso, a suíte inteira da v0.25.0, depois
da revisão, deu 1.048 aprovados, 0 falhas e 67 pulados, em 1.000 s (16min40s).

Comandos (neste ambiente): os arquivos afetados (`test_radar_funcao_ia.py`, `test_radar_banco.py`, `test_radar_telas.py`,
`test_radar_site_publicar.py` e `test_radar_repositorio.py`), as mutações (um script que troca o trecho, roda o teste dele, confere que
falhou e restaura o arquivo) e, no fim, a suíte inteira (`python -m pytest testes -q`).

## v0.24.0, etapa 5 — humanização dos textos, linha "Fonte oficial" e revisão editorial automática

São 14 testes novos (de 1.092 para 1.106 no total, como a etapa 1 e esta etapa coletam neste ambiente; 2 deles dos acertos da revisão
e 1 da norma seguida de vírgula, abaixo) e 23 testes antigos ajustados (3 com nome novo, porque a regra mudou), mais a IA de mentira dos testes da função e da tela, que
agora também faz a revisão editorial (por padrão, devolve o texto que recebeu, com as 10 perguntas "ok"), e a conferência automática dos
testes, que guarda a revisão editorial. Cada parte foi conferida desfazendo-a numa cópia temporária do arquivo (o teste novo falha) e
restaurando: **47 mutações** (28 na função `radar-ia`, 6 no banco, 9 na tela, 3 no robô de rascunhos e 1 no robô do site), todas
derrubaram o teste delas:

- **Humanização em toda ação que escreve** (`test_radar_funcao_ia.py`, 1 novo): a regra (9) nova (a persona do jornalista
  especializado, as 10 expressões a evitar, a estrutura que o conteúdo pede, nada de chamada comercial automática nem urgência
  artificial e o exemplo dos combustíveis só como modelo de tom) vai inteira no gerar, na segunda passada, na revisão editorial, nos
  títulos, no revisar, no kit e na peça, e não no classificar nem no fundamentar; a regra antiga do "contador explicando ao cliente"
  sumiu. Nos textos curtos (títulos, kit e peça), a autoconferência vai na mesma chamada. O gerar pede a Análise Artecon só quando
  acrescenta (nunca inventando interpretação jurídica nem consequência econômica) e a linha "Fonte oficial"; o formato não pede mais
  "quando vale procurar a Artecon" nem "o risco de não agir"; o kit não pede mais o convite para conversar com a Artecon; na Pauta, o
  convite moderado no fim fica só na Captação. Mutações: a regra sem a proibição da chamada comercial, o kit com o convite de volta, a
  peça com convite em todos os tipos, o formato com o "procurar a Artecon" de volta e o kit sem a autoconferência.
- **Revisão editorial no gerar** (`test_radar_funcao_ia.py`, 3 novos): depois da redação (e da segunda passada, se houver o que
  corrigir), a chamada "editorial" (esquema fixo: título e texto inteiros, as 10 perguntas com "ok" ou "ajustado" e o motivo, os
  trechos reescritos e as pendências), com as 10 perguntas do dono, "Não é detector de IA", os limites e o mesmo material (texto oficial,
  verificação e links); o texto que fica é o revisado e o resultado, limpo (sem HTML nem link, até 8 trechos), vai ao banco e à resposta;
  o consumo soma as duas chamadas como "gerar". A reescrita é **recusada** (fica o rascunho, a revisão fica "não feita" com o motivo)
  quando acrescenta valor ("R$ 5 mil"), lei ("Lei nº 9.999"), número solto ("37"), norma pelo nome ("CLT") ou trecho igual ao da fonte,
  ou tira a linha "Fonte oficial", a marca [VERIFICAR] ou a citação entre aspas; a data do texto oficial escrita de outro jeito passa, e o
  link fora dos dados do assunto sai do texto, com aviso. Se a IA Central recusa, a resposta vem sem uma pergunta ou cortada, o gerar
  grava o rascunho do mesmo jeito (200) e a revisão fica "não feita". Mutações: sem a revisão no gerar, a reescrita nunca recusada, sem
  cada uma das 8 conferências da reescrita, a pergunta faltando aceita, a falha que derruba o gerar e a resposta cortada aceita.
- **Ação "editorial"** (`test_radar_funcao_ia.py`, 1 novo): o botão "Fazer a revisão editorial" faz a revisão num conteúdo gravado:
  grava o texto revisado (só se o conteúdo for o que a tela leu; 409 se mudou, sem chamar a IA), com o aviso "Revisão editorial com IA
  em …", e o resultado; sem nada a mudar, só o resultado (a data do conteúdo não muda); a reescrita recusada volta como erro e nada
  muda; o texto para análise é recusado sem chamar a IA. Mutações: sem conferir a versão lida e aceitando o texto para análise.
- **Linha "Fonte oficial"** (`test_radar_funcao_ia.py`, ajustados; `test_radar_banco.py`, 1 ajustado): o gerar pede a norma uma vez no
  corpo e a linha curta "Fonte oficial: <norma> — <link>" (e não mais a seção), e a segunda passada a acrescenta quando falta; o banco e
  a função dizem igual, em 45 exemplos (os 35 de antes e 10 novos: a linha em negrito, como item, no plural, em maiúsculas; sem link
  oficial, no meio da frase ou sem os dois-pontos não vale), que o texto tem a linha (ou a seção de antes); a Conferência das Diretrizes
  marca ✓ no critério 2 com a linha e o link oficial, e ✗ sem link, com link que não é oficial ou com a linha no meio da frase.
  Mutações: o gerar de volta com a seção, a função e o banco sem aceitar a linha.
- **Banco** (`test_radar_banco.py`, 1 novo e 3 ajustados: as 2 funções novas na lista das expostas, os casos da linha "Fonte oficial" e o
  setup rodado de novo, que mantém a revisão editorial): a revisão editorial fica no conteúdo (`conferencia->'editorial'`) só pela função,
  com a versão do corpo do texto (`radar_texto_versao`), quando e quem; as chaves de fora não ficam; gravar não muda a data do
  conteúdo; é validada (RADAR189: as 10 perguntas, "ok" ou "ajustado", o motivo, até 12 trechos de até 400 caracteres; "não feita" com
  o motivo), só o editor e o administrador gravam (RADAR188) e só para o texto lido (RADAR190); o UPDATE direto e o INSERT não a forjam;
  ela não trava nem libera a aprovação; gravar a Conferência ou o "Revisei e assumo" depois não a apaga; trocar só o título não muda a
  versão, mudar o texto sim; fica na trilha. Mutações: a Conferência apagando a revisão, sem validar as perguntas, sem conferir a versão
  lida, a versão com o título e as chaves de fora guardadas.
- **Tela** (`test_radar_telas.py`, 3 novos e 1 ajustado, a entrada da aba Versões): o quadro "Revisão editorial" logo abaixo da
  Conferência das Diretrizes, com as 10 perguntas (✓ e ✎, com o motivo) e "O que foi reescrito" (antes → depois, "saiu do texto"), sem
  mudar a trava do Aprovar; trocar só o título não muda nada; o texto editado à mão faz o quadro avisar que a revisão era da versão
  anterior, com o botão "Fazer a revisão editorial de novo"; o texto da equipe não tem o quadro; o Histórico mostra "Revisão editorial: 2
  pergunta(s) com ajuste, 2 trecho(s) reescrito(s)". A revisão "não feita" mostra o motivo e o botão "Fazer a revisão editorial" (também
  no texto da IA sem revisão nenhuma), que chama a ação "editorial" com a versão lida; ela não trava o Aprovar. O critério 2 da
  Conferência aceita a linha "Fonte oficial" com link oficial, e a prévia do site a mostra como link. Mutações: sem o quadro, sem o aviso
  de versão anterior, ✓ no lugar do ✎, sem o "antes → depois", sem a versão do corpo na leitura, sem a linha no Histórico, sem o botão,
  a revisão não feita travando o Aprovar e o botão sem a versão lida. Um teste antigo (a frase do boletim de outro assunto) achou o
  "Aprovar" no texto do quadro novo: o quadro passou a dizer "quem trava a aprovação" (o botão continua sendo o único "Aprovar").
- **Robôs** (`test_radar_rascunhos.py`, 1 novo; `test_radar_site_publicar.py`, 1 novo; `test_radar_e2e.py`, 1 ajustado): os rascunhos do
  robô usam a mesma regra (9) da função (conferido letra por letra), com a Análise Artecon opcional e sem "quando vale procurar a
  Artecon"; o robô do site publica a linha "Fonte oficial" como parágrafo, com o link, e não acrescenta chamada comercial nenhuma.
  Mutações: o robô com o "procurar a Artecon" de volta, com a regra antiga e o robô do site com uma chamada no fim.
- **Ajustados por causa da chamada a mais** (`test_radar_funcao_ia.py`, 16 no total com os da linha "Fonte oficial"): os testes do gerar
  que contavam as chamadas à IA ou olhavam "o último pedido" passam a conferir a ordem das ferramentas (redação, segunda passada,
  revisão editorial) e o pedido da redação pelo nome; o consumo do gerar com segunda passada passa de 2 para 3 chamadas; o texto de fora
  não fecha o bloco de dados também na revisão editorial; as orientações do escritório vão também no fim dela. Os 2 testes de tela que
  usam a IA Central de verdade e contavam as chamadas foram ajustados do mesmo jeito (são pulados aqui).
- **Norma seguida de vírgula** (`test_radar_rascunhos.py`, 1 novo e 1 amostra nova no teste que compara o robô com a função): "nº
  2.290," era lido como "nº 2" (a vírgula barrava o número inteiro), e o texto ganhava o aviso falso "Norma citada que não aparece no
  texto oficial capturado" quando o texto oficial não tinha a mesma vírgula; com a linha "Fonte oficial" isso apareceria mais. A vírgula
  agora só barra quando vem decimal ("2,5%"), igual na função e no robô de rascunhos. Mutações: a regra antiga no robô e na função.
- **Acertos da revisão da etapa 5** (`test_radar_funcao_ia.py`, 2 novos e 1 ampliado; `test_radar_telas.py`, 1 corrigido): a reescrita
  da revisão editorial passa a ser recusada também quando **troca o link** da linha "Fonte oficial" por um fora dos dados do assunto
  (antes, a troca passava e o link certo saía depois, com o inventado), quando tira a linha "Fonte oficial" **sem link** e quando traz
  um trecho igual ao da fonte **no lugar de outro** que já estava (a conta era pelo número de trechos); o link que a redação inventou sai
  antes da revisão (ela nem o vê). Na ação "editorial", o material é o do gerar: com texto oficial, só ele (o dado que só o portal traz,
  "R$ 5 mil", é recusado, e o portal nem vai no pedido). A revisão pode encurtar o texto (tirar a Análise Artecon que não acrescenta)
  quando diz o que tirou; sem dizer, o texto que perde mais de 40% é recusado com o motivo certo ("encurtou o texto sem dizer o que
  tirou", não mais "texto incompleto"), e abaixo de um terço sempre. O teste de tela da IA Central (pulado aqui) contava 4 chamadas e
  3 custos ao mesmo tempo e não previa a segunda passada do texto sem a linha "Fonte oficial": o texto de exemplo ganhou a linha
  (conferido no ambiente dos testes da função: só a redação e a revisão editorial, sem nenhum aviso) e o teste confere as 4 ferramentas
  e os 4 custos. Mutações: sem conferir o link, a linha só com link, o material com a fonte não oficial, a cópia pela contagem, o limite
  fixo de 60% e sem tirar o link inventado antes da revisão.

Comandos (neste ambiente): os 7 arquivos afetados (`test_radar_funcao_ia.py`, `test_radar_banco.py`, `test_radar_telas.py`,
`test_radar_site_publicar.py`, `test_radar_rascunhos.py`, `test_radar_e2e.py` e `test_radar_repositorio.py`), as 45 mutações (um
script que troca o trecho, roda o teste dele, confere que falhou e restaura o arquivo) e, no fim, a suíte inteira
(`python -m pytest testes -q`).

## v0.24.0 — Diretrizes editoriais, Conferência das Diretrizes, texto Informativo e Orientações para a IA

São 28 testes novos (de 1.064 para 1.092 no total, como a v0.23.0 e esta versão coletam neste ambiente) e 25 testes antigos
ajustados (3 deles com nome novo, porque a regra mudou), mais a conferência automática dos testes (abaixo). Cada parte foi conferida
desfazendo-a numa cópia temporária do arquivo (o teste novo falha) e restaurando — 24 mutações das Diretrizes, da Conferência e do
Informativo, 17 das Orientações para a IA e 18 dos acertos da revisão desta etapa, todas derrubaram ao menos um teste (mais 1 da
correção do reel, abaixo):

- **Conferência das Diretrizes no banco** (`test_radar_banco.py`, 6 novos e 5 ajustados, estes só pelo nome do setup e da reversão e
  pelas 3 funções novas na lista das expostas): sem a lista dos 10 critérios do texto que está no conteúdo, nem o editor nem o
  administrador aprovam (RADAR181); com critério que não atende, também não (RADAR182, com os números); quem não é o administrador não
  tira o ✗ gravando outra lista para o mesmo texto (a lista do administrador vale inteira); mudou o título, o texto, a fonte ou a
  capa, a lista deixa de valer; gravar a lista não muda a data do conteúdo, e o UPDATE direto e o INSERT não a forjam. A lista é
  validada (10 itens, 1 a 10, sem repetir, situação e motivo; RADAR185), só o editor e o administrador gravam (RADAR183) e só se o
  texto ainda for o que foi à IA (RADAR184). O banco confere sozinho, por cima da lista da IA, o [VERIFICAR] (2 e 8), a norma citada
  sem a seção "Fundamentação legal" com link oficial (2; no Informativo, que não tem a seção, não), o Informativo sem a fonte (3), a
  frase do boletim pago (4) e a capa (6). "Revisei e assumo": só o administrador (RADAR186), com motivo de 10 a 500 caracteres
  (RADAR187), na conferência e na trilha; mudou o texto, cai; o [VERIFICAR] e o boletim pago continuam travando. O texto Informativo
  não é aprovado, nem pela API, sem a autorização do administrador (RADAR180), e tirar o aviso por fora não adianta; desfeita a
  autorização, o Informativo aprovado volta para a revisão (o texto comum aprovado, não). Rodar o setup de novo mantém a lista e a
  trava.
- **Diretrizes na função de IA** (`test_radar_funcao_ia.py`, 7 novos e 11 ajustados: o esquema do gerar com "sem_base_legal", a
  revisão que agora também confere, o aviso da revisão e as regras na ordem nova): as Diretrizes 1, 2, 3, 5 e 6 vão inteiras nas
  instruções do gerar (e da segunda passada), dos títulos, do revisar, do kit e da peça, depois das regras de cada ação e antes da
  regra dos blocos de dados; classificar e fundamentar ficam sem elas; o verificar pede a vigência. O gerar recebe os links oficiais
  do assunto (só os conferidos) e pede a seção "Fundamentação legal", com a data e o artigo só quando estão no texto oficial; o
  endereço que a IA inventou sai do texto, com aviso; a norma sem link ou sem a vigência confirmada vai num aviso à parte (ela fica no
  texto). No pedido, o formato "informativo" se chama "NOTÍCIA MÉDIA" e o modo da Diretriz 2 "SEM BASE LEGAL" (campo
  "sem_base_legal", com a descrição), para a IA não confundir os dois. O revisar confere os 10 critérios (ferramenta com esquema
  fixo; lista incompleta é recusada) e o banco grava; sem nada a corrigir, só confere; a seção que falta é acrescentada só com os
  links do assunto; no Informativo, sem links, e a conferência é avisada de que a norma só mencionada não reprova o critério 2. Sem
  texto oficial, o gerar faz o texto Informativo (o aviso "INFORMATIVO…" em primeiro), que só é aprovado depois da autorização. O
  trecho igual citado fora de aspas pede a segunda passada (também no kit, que o aponta nos avisos); a citação curta entre aspas, com
  a fonte, não; a transcrição longa (mais de 40 palavras) entre aspas e com a fonte citada só é conferida, não reescrita. A regra
  "cita norma" e "tem a seção Fundamentação legal" dá o mesmo resultado no banco e na função, em 35 exemplos (um por tipo de norma, e
  os que não são norma).
- **Detector de cópia** (`test_radar_rascunhos.py`, 1 novo): a tela, a função e o robô dizem igual, em 5 casos, se o trecho estava
  numa citação longa entre aspas (com e sem a fonte citada, fora de aspas, com cópia depois das aspas e do boletim pago).
- **Tela** (`test_radar_telas.py`, 4 novos e 7 ajustados): o quadro "Conferência das Diretrizes" com os 10 critérios (✓, ✗, —, ?),
  o Aprovar travado com ✗ ou ?, o "Revisar com IA" que confere e o recado com os critérios que não atendem; conferir de novo o mesmo
  texto não tira o ✗, o texto corrigido sim; o trecho igual citado fora de aspas marca 4 e 5 com ✗ (e "Autorizar mesmo assim"
  libera), e a transcrição longa entre aspas com a fonte fica num quadro azul, sem ✗; o [VERIFICAR] marca 2 e 8; "Revisei e assumo"
  só para o administrador e só sem [VERIFICAR] no texto, com o motivo no quadro, na trilha e legível na aba Histórico; o Informativo
  com o selo "Informativo — aguardando autorização" (e o tamanho como "Médio (notícia)", sem a palavra "Informativo"), sem o Aprovar,
  com o passo "Autorizar o Informativo" na trilha e o botão dele só para o administrador, que autoriza por ele (o quadro do motivo diz
  que a autorização vale para o assunto inteiro); autorizado, o selo "Conteúdo informativo" e a prévia do site com a linha "Conteúdo
  informativo" no fim. Ajustados: o teste do texto citado (agora só aprova entre aspas), o do "Gerar com IA" sem fonte oficial (agora
  Informativo), o da função antiga (FUNCAO_MINIMA 0.24.0), o da aba Versões, o da aba Como usar e os avisos de banco antigo da Pauta e
  do corretor de vídeo (que apontam o setup da v0.24.0).
- **Robô do site** (`test_radar_site_publicar.py`, 1 novo): o Informativo sai com a linha "Conteúdo informativo" no fim, depois dos
  créditos; o endereço do texto vira link, com a pontuação de fora, como na prévia; o texto comum não leva a linha.
- **Orientações para a IA** (`test_radar_funcao_ia.py`, 5 novos; `test_radar_telas.py`, 4 novos): o bloco vai depois das regras no
  gerar, no kit e na peça (e nos títulos e nas revisões), nunca onde não se escreve para publicar; na peça, sem nome da equipe, link
  nem dado de identificação; a orientação da imagem com marca ou pessoa conhecida fica de fora, com aviso; as preferências da imagem
  vêm antes das proibições. Na tela, só o administrador altera, com o limite de caracteres e a conferência do boletim pago.
- **Versão** (`test_radar_repositorio.py`, 1 ajustado; e os de versão da tela e do banco): a tela, os scripts, a `radar-ia`, o banco
  (setup e reversão), o LEIAME e este relatório na 0.24.0.
- **Reel aprovado antes da v0.22.0** (`test_radar_video_banco.py`, 1 ajustado): com o banco instalado direto na v0.24.0 (sem a linha
  da v0.22.0 em `radar_instalacoes`), o registro do link sem o vídeo corrigido continua recusado (RADAR317) só para a aprovação
  feita depois da primeira instalação da v0.22.0 ou mais nova. Com a regra de volta em "só a v0.22.0", o teste falha.

**Conferência automática dos testes.** Os testes antigos aprovam conteúdo sem passar pela IA. Para eles continuarem conferindo o
que conferiam, o banco de teste ganha (só nos testes, em `testes/conftest.py`) um gatilho que grava a lista dos 10 critérios
"atende" da versão do texto em todo INSERT e UPDATE de conteúdo. Nesses testes, só as travas que a aprovação confere à parte (o
[VERIFICAR] e a frase do boletim pago) continuam valendo; a "Fundamentação legal" e a capa, que o banco confere ao gravar a lista
(`radar_registrar_conferencia`), não. Os testes novos da conferência desligam esse gatilho (fixture `conferencia_de_verdade`) e
passam pelo caminho de verdade, onde as quatro valem.

Comandos (neste ambiente): os 5 arquivos afetados (`test_radar_banco.py`, `test_radar_funcao_ia.py`, `test_radar_telas.py`,
`test_radar_site_publicar.py` e `test_radar_rascunhos.py`), mais `test_radar_repositorio.py` e `test_radar_publicidade.py`, um a um,
as mutações e, no fim, a suíte inteira (`python -m pytest testes -q`).

## v0.23.0 — boletim da ITC na caixa inteira, agendas que rodam de novo e INLABS

São 7 testes novos (de 1.056 para 1.063 no total) e 10 testes antigos ajustados, mais as duas funções de apoio que aplicam no banco de
teste os SQL das agendas e da `radar-concorrentes`. Cada mudança foi conferida desfazendo-a numa cópia temporária do arquivo (o teste
falha) e restaurando:

- **Caixa inteira, menos o Lixo Eletrônico e os Itens Excluídos** (`test_radar_funcao_itc.py`; o Graph de mentira passou a ter as
  quatro pastas — a Caixa de Entrada, a subpasta "ITC Consultoria", o Lixo Eletrônico e os Itens Excluídos —, a caixa inteira e a pasta
  só, e respeita o `$top`): o boletim da subpasta é lido; o forjado no Lixo, o dos Itens Excluídos e o que vem sem a pasta não vão à
  IA; 12 forjados mais recentes no Lixo não deixam de fora o boletim da subpasta (a busca pede o dobro da cota). Sem o id do Lixo ou
  dos Itens Excluídos (erro do Graph, ou resposta sem o id), a função para com o motivo e nunca lista a caixa sem o filtro. Desfeitos o
  filtro das pastas, a folga do `$top` ou a parada sem o id, os testes falham.
- **"Já lido" pelo internetMessageId**: o boletim movido de pasta (outro id do Graph, o mesmo internetMessageId) não volta à IA; a
  cópia do mesmo e-mail em duas pastas entra uma vez só; sem o internetMessageId, vale o id do Graph. Com a chave de volta no id do
  Graph (5 testes falham) ou sem tirar a cópia repetida, os testes falham.
- **`ITC_PASTA`** (outra instância da função, com o segredo preenchido): lê só aquela pasta, sem procurar o Lixo e os Itens Excluídos,
  e o diagnóstico diz que é só a pasta.
- **403**: a dica nova ("confira a atribuição 'Application Mail.Read' no Exchange (só esta caixa) — ela leva de 30 minutos a 2 horas
  para valer depois de criada"), com o código da Microsoft e sem o recado dela, na resposta, na aba Fontes e no diagnóstico.
- **Diagnóstico**: conta os boletins dos últimos 7 dias na caixa inteira (14 em duas pastas; os do Lixo e dos Itens Excluídos fora),
  sem pedir o corpo nem o assunto, e mostra a versão 0.23.0. Os 4 testes antigos da função passaram a ter a pasta e o
  internetMessageId nos e-mails de mentira, e o "já lido" gravado é o internetMessageId.
- **Agendas que rodam de novo** (`test_radar_agenda.py`): num banco com um gatilho de mentira no lugar do da Supabase (falha em
  qualquer `create extension` e em qualquer grant), as três agendas (ITC, Pauta e corretor de vídeo) rodam duas vezes seguidas sem
  erro, com os mesmos agendamentos e as mesmas chaves do Vault; a agenda da ITC (sem teste até aqui) agenda às 05h55 UTC e, só com
  boletim para depois, às 06h10 e 06h25, e chama a função com a chave do Vault lida na hora; sem a extensão, cada arquivo (e o
  `sql/radar-concorrentes.sql`) tenta criá-la e para ali. Com os grants do pg_cron fora do bloco que confere a extensão, o teste
  falha. Os testes das agendas (Pauta e corretor) e da `radar-concorrentes` passam a rodar os arquivos como estão, com as extensões
  contando como instaladas (antes, sem as linhas `create extension`).
- **INLABS** (`test_radar_coletores.py`, 1 teste ajustado): o e-mail e a senha com espaço, tabulação e quebra de linha nas pontas
  chegam limpos ao login; só espaço conta como sem cadastro. Sem o `.strip()`, o teste falha.
- **Versão** (`test_radar_repositorio.py`, 1 ajustado; `test_radar_telas.py`, 4 ajustados): a tela, os dois scripts, a `radar-itc`,
  o LEIAME e este relatório na 0.23.0; o banco (setup e reversão) continua na 0.22.0, como a `radar-video` e o robô do vídeo (da
  mesma versão entre si), e nenhuma função fica à frente da tela; os avisos de banco antigo da tela apontam o setup que existe. A aba
  Versões traz a 0.23.0 no topo e a 0.22.0 logo abaixo.

Comandos (neste ambiente): os módulos da ITC, das agendas, da `radar-concorrentes`, do repositório, os testes de agenda do
`test_radar_video_banco.py`, os do INLABS e os 5 de tela afetados, um a um, e depois a suíte inteira (`python -m pytest testes -q`).

## v0.22.0 — varredura geral, rodada 2 (correções)

São 18 testes novos (de 1.038 para 1.056 no total) e 19 testes antigos ajustados. Cada correção foi conferida desfazendo-a numa cópia
temporária do arquivo (o teste novo falha) e restaurando:

- **Boletim pago, na tela como no banco** (`test_radar_banco.py`, `test_radar_funcao_ia.py`, `test_radar_telas.py`): o banco diz onde
  está, no próprio texto, a frase de uma matéria do boletim que não está no assunto (`radar_copia_paga_trechos`: só as posições, por
  letra, com emoji; a janela que também está na captura livre do assunto não entra; só o editor e o administrador, RADAR147); o
  quadro vermelho a mostra, sem o selo verde e sem "Autorizar mesmo assim", e o Aprovar recusa; o "Revisar com IA" recebe a frase
  (e o boletim nunca vai à IA); a legenda com a frase é recusada na tela, com o trecho, antes do banco (RADAR146).
- **Ementa do ato oficial** (`test_radar_banco.py`): a matéria do boletim que é o próprio ato ("… (DOU DE …)", "(DOE-SC de …)") não
  conta na notícia nem na Pauta; a mesma frase numa matéria comum do boletim conta; o reconhecimento do título não pega "Leilão…",
  "(Doença…)", notícia sobre a lei nem título sem o Diário Oficial.
- **CRC com acento** (`test_radar_banco.py`): "CRC-SC 012345/O-9 (Originário)" casa com a linha no texto, com e sem acento e com o
  acento separado da letra (NFD).
- **"Usar a sugestão" da Pauta** (`test_radar_telas.py`): com 10 fontes da tabela das obrigações, a linha "Fonte: …" sai inteira (só
  a norma, sem o endereço, quando não cabe com ele) e o texto da IA é encurtado no fim de uma frase ("art. 79," não é fim de frase); o
  recado avisa; o Facebook, que coube, leva as fontes com os endereços.
- **Aviso da Pauta** (`test_radar_e2e.py`): com o aviso aberto por um erro antigo, a falha de outra peça ganha um comentário (um
  e-mail), a mesma lista não comenta de novo, a marca forjada por outra conta não conta, o aviso da versão anterior (sem marca) ganha
  um comentário só, e a falha do GitHub ao ler os comentários não para os outros avisos.
- **Robôs agendados e Painel** (`test_radar_funcao_redes.py`, `test_radar_agenda.py`, `test_radar_banco.py`, `test_radar_telas.py`):
  "manter_robos" religa o desligado por inatividade, renova o ativo e deixa o desligado à mão (só a agenda e o administrador); o
  acionamento do robô do site desligado o religa e aciona, ou diz onde religar sem prometer a rodada automática; a agenda pede o
  "manter_robos" uma vez por dia; o Painel avisa a coleta parada há mais de 12 horas (não com a fonte do e-mail só).
- **Imagem da notícia** (`test_radar_funcao_redes.py`): vai ao bucket privado, com nome aleatório e link assinado de 10 minutos;
  nenhum bucket público é criado; o envio antigo com o link público sai por ele e, excluído, a imagem sai do bucket público.
- **Exclusão no site** (`test_radar_site_publicar.py`, com o painel de mentira encurtando o título): só exclui a notícia cortada se o
  título inteiro, no formulário de edição, for o pedido; a outra da mesma série fica; sem o formulário, não exclui.
- **Sessão só na aba** (`test_radar_telas.py`): nada no localStorage; outra aba da mesma origem não acha sessão; a da versão
  anterior passa para a aba e sai do localStorage; o informativo aberto numa aba nova usa a sessão da aba do Radar, não guarda
  cópia, e a renovação é feita pela aba do Radar.
- **Chaves novas do Supabase** (`test_radar_telas.py`, `test_radar_agenda.py`, `test_radar_funcao_redes.py`,
  `test_radar_site_publicar.py`, `test_radar_video_corrigir.py`): com a `sb_publishable_…`, a tela entra mandando a chave só no
  apikey; as duas agendas aceitam e mandam só no apikey (o teste do fim de cada arquivo também); a função usa a publishable no apikey
  quando o Supabase a fornece; os robôs mandam a `sb_secret_…` só no apikey; o robô do vídeo aceita a publishable (e recusa a anon de
  outro projeto). A `radar-redes` e a `radar-concorrentes` passam a 0.22.0 (3 testes ajustados).

## v0.22.0 — varredura geral, rodada 1 (correções)

São 17 testes novos (de 1.021 para 1.038 no total) e 9 testes antigos ajustados. Cada correção foi conferida desfazendo-a numa cópia
temporária do arquivo (o teste novo falha) e restaurando:

- **Notícia, "Publicar em todos"** (`test_radar_banco.py`, `test_radar_telas.py`, `test_radar_funcao_redes.py`): com o site na vez do
  robô, o registro à mão é recusado (RADAR145) e o "Registrar publicação no site" some da tela; o registro com link de outro endereço
  (mesmo vindo do robô) derruba as redes que esperavam o site, com o motivo, e a legenda nunca recebe esse link; depois que o envio do
  site saiu, a pessoa registra com o link do site e as redes saem. Os 2 testes da função `radar-redes` passaram a registrar como o robô.
- **Boletim pago na notícia** (`test_radar_banco.py`, `test_radar_telas.py`): "Autorizar mesmo assim" some com trecho pago; o banco
  recusa (RADAR146, sem mostrar o trecho) a autorização da cópia, a aprovação, o site, a rede, o "Publicar em todos" e a saída de uma
  autorização antiga; a janela que também está numa captura livre do assunto não conta. A frase de um boletim com mais de 90 dias
  também trava (notícia e Pauta).
- **Notícia, nunca duas vezes** (`test_radar_banco.py`, `test_radar_telas.py`): a publicação cancelada no meio do envio pede a caixa
  "Conferi no …: não saiu" na rede e no "Publicar em todos" (RADAR166); o outro canal não pede; depois que uma publicação do canal sai
  de fato, não pede mais.
- **Pauta** (`test_radar_banco.py`, `test_radar_video_banco.py`, `test_radar_telas.py`): o CRC da identificação é conferido inteiro
  (UF, número e categoria; "CRC-PR", "/0-9", "/O-5", "/O-91" e o telefone com os mesmos algarismos não passam); a pessoa de um vídeo
  ainda guardado não se apaga (RADAR174) e a apagada antes da trava conta como revogada na limpeza; o leitor lê só as imagens ligadas a
  um conteúdo; a caixa "A pessoa viu o vídeo final" aparece para quem foi desmarcada depois do envio; o selo com motivo longo cabe em
  375 px.
- **IA** (`test_radar_funcao_ia.py`, `test_radar_rascunhos.py`): no gerar e nos títulos (e no robô de rascunhos) o "<<<FIM>>>" do texto
  de fora vira aspas; o nome com apóstrofo curvo, sem apóstrofo, com hífen trocado por espaço ou com hífen suave e espaço de largura
  zero vai mascarado. A versão da função passa a 0.22.0 (3 testes ajustados).
- **Boletim da ITC pela função** (`test_radar_funcao_itc.py`): a falha no login da Microsoft fica na aba Fontes (sem o segredo) e a IA
  não é chamada; o assunto e o corpo do e-mail ficam dentro do bloco, sem as marcas; o relógio é de cada pedido.
- **Corretor de vídeo** (`test_radar_funcao_video.py`): o 500, o 503 e o 504 do banco viram 502 (o robô repete); a recusa de regra
  continua 400.
- **Robôs e repositório** (`test_radar_site_admin.py`, `test_radar_repositorio.py`, `test_radar_e2e.py`, `test_radar_coletores.py`): o
  relatório do "teste do site" não traz célula da lista, nome de quem cadastrou nem código de link de editar/excluir (nem a chave de
  biblioteca no caminho); o `.gitignore` barra os clipes brutos `ent/<n>`; o primeiro push de um ramo confere os commits que só ele tem;
  toda ação dos workflows fixada pelo commit e o `robo/requirements.txt` com versão exata e hash; os avisos contam só as issues do robô;
  a fonte de atos da Receita diz o motivo quando o sistema Normas devolve a aplicação nova. Os títulos de notícia usados nos testes
  de triagem foram reescritos para o teste (nenhum título do boletim pago no repositório).

## v0.22.0 — corretor de vídeo dos reels, "Preencher fontes oficiais" e o CRC certo

São 215 testes novos (de 806 para 1.021 no total, com as duas varreduras). O que foi comprovado, por área:

- **Receita de edição** (`test_radar_video_robo.py`, novo, 21 testes; fixtures geradas pelo ffmpeg: vertical, horizontal, 60 fps
  girado, HEVC HLG com o áudio atrasado 0,478 s, PQ 4:5, silêncio e pausas, sem áudio, longo, m3u8 renomeado, Matroska):
  - entrada não confiável: a playlist `.m3u8` renomeada é recusada **sem chamar o ffprobe** (o `ftyp` é conferido antes), e também o
    `ftyp` falso, o Matroska e o arquivo maior que o declarado; recusas `sem_audio`, `deitado` e `longo_demais`; a sondagem lê o giro,
    os 60 fps e o HLG/PQ sem dado do aparelho;
  - o áudio de trabalho fica no zero do vídeo, preserva o atraso de 0,478 s e tem o tamanho exato; os cortes de começo, fim e pausas
    seguem os limites das Configurações; um trecho nunca passa de um clipe para o outro; o clipe sem fala sai inteiro;
  - a montagem vertical sai H.264 High 1080×1920 a 30/1, AAC 48 kHz em 2 canais, com o índice no começo, **sem lista de edição, sem
    GPS e sem a marca do aparelho** (também nos JPG), a -14 LUFS no modo linear, com a duração exata, a voz a ±6 ms do plano, o branco
    da imagem e a voz juntos (até 1 quadro) em cada palavra e o fim da fala intacto; 4 clipes (girado a 60 fps, HLG com atraso, PQ
    4:5) sincronizados palavra a palavra; o ajuste só muda a legenda (o md5 do áudio é igual);
  - a conferência recusa o MP4 padrão do ffmpeg (faststart, fps, resolução, áudio, GPS, metadados, volume); a legenda e o gancho ficam
    na área livre, medidos em pixels pelo libass, com a DM Sans; a cartela recusa o que não cabe (`cartela_nao_cabe`), nunca "…";
  - o log e os erros não levam dado pessoal; o ffmpeg não recebe o ambiente do robô (nem as chaves); o teste estático confere o
    isolamento (`--network none`, só leitura, nenhum `-e`), o `-protocol_whitelist file`, nenhuma IA, o Dockerfile (a imagem pelo
    digest; o ffmpeg **e as bibliotecas libav\*** na mesma versão exata — o pacote ffmpeg só as pede com ">=", e as outras
    bibliotecas seguem as correções da 24.04) e o `requirements.txt` com hash; o contêiner roda sem rede, sem ambiente e só leitura
    (no GitHub Actions, a imagem que não monta falha o teste, em vez de pular).
- **Alinhamento** (`test_radar_video_alinhar.py`, novo, 82 casos em 32 funções; 6 roteiros fictícios, com "Ana Teste" e "Bruno
  Exemplo", e transcrições escritas à mão): a fala igual ao roteiro dá 0 divergências e a legenda igual ao roteiro (também com a
  transcrição já na forma de exibição, a do serviço pago); "dia 15" contra "dia 25" (com "a transcrição errou"), ano, ordinal, termo
  faltando e mês a mais são divergência; "30 de outubro" é "30/10", "50 mil reais" é "R$ 50.000,00", "IPS" vira "IBS" só onde o roteiro
  tem IBS, "é social" e "dctf web" viram os termos; hesitação, repetição e falso início; "um", "uma", "e" e "é" nunca saem ("é dia 30",
  "um milhão", "um salário mínimo", "e o MEI", "é social" ditos devagar); a voz entre palavras seguidas do roteiro sai e a entre
  palavras não seguidas vira sugestão; o editor de legenda recusa número, data, termo e palavra a mais; e um teste de ponta a ponta com
  o ffmpeg: o "ééé" e o "hum" saem do vídeo, e a legenda gravada tem "eSocial" e "30/10.".
- **Transcrição** (`test_radar_video_transcrever.py`, novo, 19 testes, 3 com o SDK de verdade, pulados sem ele): o pedido ao F0
  (pt-BR, saída detalhada, tempo por palavra, palavrão sem máscara, lista de frases) e a leitura dos tempos; 429 espera e tenta de novo,
  e passados 10 minutos dá `transcricao_ocupada`; a recusa por cota espera e termina em `azure_cota`; 401 e pedido inválido não tentam
  de novo; a rede tenta 3 vezes (também o SDK que trava); a configuração, o WAV e a cota do Radar são conferidos antes de qualquer
  chamada; o modo pago (REST) com multipart, Retry-After, sem seguir redirecionamento, sem o proxy do ambiente e só endereço da Azure;
  a chave nunca aparece em mensagem, traceback, saída ou log; o passo do workflow roda com `python -I`.
- **Banco** (`test_radar_video_banco.py`, novo, 29 testes em 26 funções; `test_radar_banco.py`, 262, eram 254): 27 tabelas e 36 com as visões, 8
  configurações; criar recusa a fala fora do roteiro, o boletim, a pessoa sem o termo novo, menor ou com o termo revogado, a cartela
  sem CNPJ ou com "contador" sem registro e a cota acabada; pegar com `skip locked`, a cota e o limite de 3 tentativas; concluir decide
  de novo (não confia no robô) e força regravar com o boletim na fala; aprovar exige o sha256 do vídeo pronto e as caixas `video` e
  `viu`; desaprovar solta a amarra e o gatilho a protege; o registro manual do reel sem o vídeo dá RADAR317; a trilha não guarda a fala;
  o `service_role` não lê os vídeos; a limpeza respeita a revogação; a agenda do vídeo (chaves no Vault, reserva só com fila, limpeza)
  e as reversões. Os 2 testes de reel da v0.21.0 passaram a exigir o vídeo pronto.
- **Função `radar-video`** (`test_radar_funcao_video.py`, novo, 11 testes, no Deno, com o armazenamento e o GitHub de mentira):
  chave interna como chamador dá 403 e a chave errada dá sempre "Chave não confere."; a prévia tem 600 s, venha o que vier no pedido,
  e o baixar, 300 s; o robô lê só os caminhos do pedido; o corrigido nunca é sobrescrito; concluir confere o vídeo e os 4 quadros;
  o envio confere tamanho e tipo; o bucket público volta a privado; o token de envio vai sem `x-upsert`; a limpeza mantém a versão
  atual; nada de link nem mensagem do armazenamento no log ou na resposta.
- **Robô de ponta a ponta** (`test_radar_video_corrigir.py`, novo, 21 testes, com a função e o armazenamento simulados e, num deles,
  a função de verdade no Deno com o banco real): 2 clipes (MP4 e MOV) com um "ééé" saem prontos, com o texto final igual à fala, o
  palavras.json guardado, a cota contada uma vez, o parcial antes da montagem, o sha256 e os quadros conferidos e a sincronia palavra a
  palavra; o ajuste refaz sem Azure e sem contar de novo, com o mesmo áudio; recusas e falhas (sem pedido, chave recusada, sem áudio
  com o link vencido renovado, arquivo grande, erro da Azure sem contar segundos, transcrição vazia pela reserva dos silêncios,
  pedido perdido, armazenamento em 3 tentativas, corrigido já existente, job cancelado, vídeo mexido depois da conferência); a
  conversa não segue redirecionamento, ignora o proxy e recusa link adulterado; os passos com a chave só carregam a biblioteca padrão;
  o modelo do workflow; e o robô inteiro com o ffmpeg no contêiner.
- **Telas** (`test_radar_telas.py`, no Chromium; 239 no arquivo, eram 209: 178 aprovados e 61 pulados): o envio TUS em pedaços de 6 MiB com o
  `x-signature`, a retomada, a renovação e a tela acesa durante o envio; o endereço do envio só do armazenamento do projeto (o token
  nunca vai a outro endereço); a fala para conferência nos 3 formatos (igual à do robô, roteiro por roteiro); a cartela só com as
  Configurações e Pessoas e termos; o relatório parcial e o final; "Manter este trecho", "A transcrição errou" e o editor de legenda
  (25 casos comparados com o robô) montam os ajustes; termo barrado na fala trava a aprovação; a aprovação manda o sha256 da prévia e
  as caixas; baixar só depois de aprovado; o relatório hostil (HTML e códigos como `constructor`) sai escapado; Pessoas e termos
  com os 3 campos e a lista das peças da pessoa; Configurações → Corretor de vídeo; 375 px sem rolagem lateral; o "Preencher fontes
  oficiais" (só onde falta, com confirmação, gravando como o Salvar; só para o administrador); o CRC padronizado com o 007129/O-0; a
  entrada da v0.22.0 nas Versões (o corretor, a Azure gratuita, o botão e o CRC) e o passo a passo do reel em "Como usar" (só para
  quem edita).
- **Repositório** (`test_radar_repositorio.py`, 14 testes, eram 5): nenhum vídeo, áudio ou foto (pela extensão ou pelo começo do
  arquivo, com qualquer nome; só as imagens do pacote), nenhum arquivo de trabalho do robô e nenhuma transcrição (a resposta da Azure,
  as palavras com tempo, a legenda ASS, SRT ou VTT) fora do código do robô e dos geradores sintéticos; os detectores pegam o vídeo
  renomeado e não pegam o código nem o texto em UTF-16; o `.gitignore` barra vídeo, áudio, foto e os arquivos de trabalho; o
  `radar-testes.yml` roda os testes do vídeo (ffmpeg, o Python do robô com hash, Ubuntu 24.04, tempo-limite de 45 minutos); e a
  versão é a mesma em todos os arquivos do pacote (tela, scripts, função nova, robô do vídeo, SQL, LEIAME e este relatório).
- **Testes antigos que mudaram:** as contagens do banco (27 tabelas, 8 configurações, a lista das funções da tela); os 2 testes de
  reel da v0.21.0 (o reel exige o vídeo corrigido pronto: RADAR165 sem ele); o teste do reel à mão nas telas; 8 formulários nas
  Configurações; o botão Salvar da agenda de obrigações achado por `button:not([type=button])` (o bloco ganhou o 2º botão); o servidor
  dos testes de tela ignora a conexão cortada por um reload (antes imprimia um traceback); o CRC dos testes passou a 007129/O-0; o
  armazenamento de mentira da `radar-redes` guarda os bytes e responde ao link assinado.
- **Prova de que os testes pegam o erro:** em cada etapa, cada proteção foi desfeita numa cópia do repositório, o teste ligado a ela
  rodou e falhou, e a cópia foi comparada com o repositório no fim: receita, 13 de 13 (sincronia, metadados, lista de edição, trechos
  entre clipes, `ftyp`, rede do contêiner, legenda em pixels, cartela com "…", ambiente do ffmpeg, limitador); alinhamento, 17 de 17;
  transcrição, 20 de 20; banco e função, 36 de 36; robô de ponta a ponta e workflow, 30 de 30; telas do corretor, 45 de 45 (na 1ª
  rodada, uma mutação do CSS de 375 px passou por ser equivalente e foi trocada); "Preencher fontes oficiais" e o CRC, 16 de 16 (e o
  controle: com o número antigo, terminado em 5, a troca do dígito pela letra O passava, e com o 007129/O-0 é pega); versão,
  documentos e repositório (etapa 9), 29 de 29 (vídeo, áudio, foto e transcrição com outro nome ou fora do `.gitignore`; as linhas novas do `.gitignore`; o
  `radar-testes.yml` sem o Ubuntu 24.04, o tempo, o ffmpeg, o Python do robô ou com parte dos testes; a versão diferente em cada
  arquivo, o SQL antigo esquecido e a `FUNCAO_MINIMA` acima da função do pacote; a entrada das Versões sem o botão, sem o CRC certo,
  sem o que o corretor não corrige ou com outra versão; o passo a passo do reel em "Como usar" para o leitor ou sumido).
- **1ª varredura: 21 achados corrigidos** (cada um com o teste dele; a correção desfeita numa cópia do arquivo fez o teste falhar, e o
  arquivo voltou): o termo conferido em todo o caminho do processamento (o robô não pega o pedido de quem revogou, ficou inativa, foi
  marcada menor ou com o termo vencido depois do envio — erro "termo", antes de baixar os clipes e de mandar o áudio à Azure —, e o
  ajuste, "Conferir com o roteiro novo", "Tentar de novo" e o fim do envio recusam), e nada de link novo nem de relatório depois que a
  limpeza apagou os clipes ou os textos; o bucket criado sem limite próprio (vale o do projeto; no Free o limite maior seria recusado);
  o envio novo só substitui o vídeo vivo quando os clipes chegam (o abandonado não leva o pronto junto), com o armazenamento conferido
  antes do registro; a limpeza conta o prazo do vídeo aprovado que espera o dia de postar a partir do dia da peça e leva os textos com
  o corrigido vencido; a reserva da agenda para no 3º acionamento sem o robô pegar ("robo_nao_pegou", um aviso só); o limite padrão de
  30 minutos no mês; o áudio somado uma vez por rodada (o robô repete a chamada que falhou no caminho); o RADAR317 só para a
  aprovação feita com a v0.22.0; a chave do robô e a da agenda comparadas pelo resumo (sha256); as edições da legenda numa lista, na
  ordem em que o robô aplica, com as palavras do roteiro perto de cada bloco (a tela recusa como o robô); na tela, o vivo e o envio a
  caminho lado a lado, só quem começou o envio (ou o administrador) continua, a tela acesa de novo ao voltar ao Radar, o fim do envio
  que falha volta ao "Continuar o envio", o quadro do corretor refeito sem apagar o texto não salvo e o "Apaguei" do vídeo baixado à
  parte do dos clipes.
- **2ª varredura: 23 achados, todos procedentes** (três se repetem, no todo ou em parte: o "60 por padrão" das Versões, como parar
  o corretor e as imagens no `.gitignore`), corrigidos no código, nos documentos ou nos dois, cada um com o teste dele:
  - as marcas dos ajustes apontam o trecho pelo que ele é, e não pela posição na lista: "A transcrição errou" pelo id da divergência
    (o instante e o texto, falado e do roteiro) e "Manter este trecho" pela chave do corte ("<clipe>:<quadro>" de onde começa o que
    ele corta). Com uma variante nova no glossário, a marca do termo não cai mais no valor dito errado (a legenda nunca diz um valor que
    o áudio não diz), e "A transcrição errou" na data não leva o "manter" para o corte novo da pausa entre frases; o banco confere pelo
    id (`test_a_transcricao_errou_marca_a_divergencia_pelo_conteudo…`, `test_manter_este_trecho_aponta_o_corte_pela_chave…`, os do banco
    e da tela);
  - o banco guarda as pessoas do vídeo (`radar_videos.pessoas`: as marcadas no envio e quando os clipes chegaram): desmarcar na peça
    não tira a pessoa das travas (pendência, prévia, robô, aprovação no dia da peça, baixar) nem da limpeza da revogação; a prévia
    confere as pessoas como o baixar; a limpeza leva os arquivos e os textos também quando o termo do corretor é retirado ou a pessoa é
    marcada menor (`test_desmarcar_quem_aparece_nao_tira_a_pessoa_do_video`, `test_previa_e_limpeza_param_quando_a_pessoa…`, 4 casos);
  - o texto do gancho gravado (a cópia da chamada no envio) e o texto extra da cartela que o robô gravou (agora no relatório) passam
    pelas travas como estão no vídeo, e a pendência pede o vídeo em dia quando a chamada ou o `cartela_extra` mudam depois; a tela
    confere os termos de publicidade no gancho no envio e na aprovação (`test_gancho_e_texto_extra_da_cartela_conferidos…`,
    `test_video_texto_do_gancho_gravado_passa_pelos_termos…`);
  - "Tentar de novo" na cartela que não coube refaz as linhas com a Assinatura e Pessoas e termos de hoje (antes, parava de novo
    sempre); "Conferir com o roteiro novo" com a mesma fala só registra o roteiro novo (sem a fila e sem perder as marcas); o envio
    cuja gravação não cabe no que sobra da cota do mês é recusado antes de qualquer arquivo sair, e o quadro mostra o que sobra
    (`radar_video_cota`); a função aciona o robô de novo ao concluir ou falhar, se ainda há fila (sem a pausa de 30 s); o vídeo
    corrigido acima do limite de arquivo do armazenamento (413) para com "limite_armazenamento", sem voltar à fila 3 vezes; a tela
    orienta a guardar os clipes até o relatório e apagar no mesmo dia, com o "Apaguei" em destaque no vídeo pronto;
  - o `.gitignore` e o conferir do repositório barram PNG, WEBP, GIF, TIFF, BMP, DNG e as outras extensões de imagem e áudio (fora as 3
    imagens do pacote) e todos os arquivos de trabalho do robô (o pedido, o estado, o resultado, o erro, os temporários e a luz); o
    detector de transcrição acha o estado (palavras com "ini"), o relatório e o pedido; o `radar-repositorio.yml` baixa o histórico
    inteiro e confere cada commit do push (o arquivo enviado e apagado no mesmo push);
  - o Dockerfile fixa também as bibliotecas libav* (o pacote ffmpeg as pede só com ">="), e no GitHub Actions a imagem que não monta
    falha o teste, em vez de pular;
  - o teste do reel aprovado à mão voltou a conferir o roteiro copiado com "Último quadro: <identificação legal>", "Reel: sem lâmina",
    nenhum "Baixar as lâminas" e nenhuma arte aprovada; a aba Versões diz "30 por padrão" no limite de minutos do mês (e o teste
    confere);
  - LEIAME: o termo novo assinado antes da instalação (do SQL em diante, nenhum reel fica pronto sem ele), o SQL antes da tela (a tela
    nova com o banco antigo não abre peça nenhuma da Pauta), o teste numa peça de teste importada por CSV (nunca numa real), o limite
    de 50 MB do Free também no vídeo corrigido, como parar o corretor de verdade (desligar o workflow; tirar o token não para, e a
    reserva vira "robo_nao_pegou"), o que fica fora do banco na reversão (o workflow com a agenda própria, os segredos do repositório
    privado, a função `radar-video` com o token e o token fino no GitHub), as marcas pelo trecho, desmarcar no reel não tira a pessoa
    do vídeo e quando apagar os clipes; o cabeçalho da reversão e o modelo do workflow dizem o mesmo (`test_leiame_da_v0220_ordem…`);
  - prova de que os testes pegam o erro: 49 mutações, cada correção desfeita numa cópia do arquivo (que voltou no fim), com o
    teste dela rodando e falhando: 49 de 49 (as do banco, do robô, da função, da tela, do repositório e, nos documentos,
    o LEIAME, a reversão e o modelo do workflow de antes).
- **O que não foi testado aqui** (os testes reais, na instalação, na ordem): a Azure F0 de verdade (como saem as siglas, os números
  e as hesitações na forma léxica; o tempo de um áudio de 60 s; a cota esgotada; a lista de frases; se a tentativa interrompida conta
  na cota) e a calibração dos limiares de corte, do ruído e do limitador com gravação real; o robô no repositório privado (o
  `python3 -m venv` do Ubuntu 24.04, o tempo do `docker build` e do job em 2 processadores, o `GITHUB_OUTPUT` e o `job.status`); o
  armazenamento de verdade (o envio retomável com o token assinado no PC e no celular, o `cache-control` de 60 s, o 409 do caminho
  que já existe, o CORS do `Location`, a tela acesa no iPhone e no Android); HDR e 4:5 só com vídeo sintético; e um reel real, com o
  termo novo assinado, até o download aprovado.
- **Tempo:** a suíte inteira levou 915 s (15min15s), com os 3 testes do Speech SDK de verdade e os 2 do contêiner neste ambiente (a da v0.21.0, 817 s): os 7 arquivos do corretor levaram 151 s
  nas rodadas por etapa, com a imagem do contêiner já montada (no GitHub, montar a imagem com o apt soma 1 a 2 minutos). O `radar-testes.yml` passou a rodar no
  `ubuntu-24.04` (o Ubuntu do robô: o ffmpeg 6.1.1 com que os testes do vídeo foram medidos e o Speech SDK, que só lista até a 24.04;
  o `ubuntu-latest` vira 26.04 em novembro de 2026) e o `timeout-minutes` passou de 30 para 45. Meça o tempo no Actions depois do
  merge: se passar de uns 30 minutos, separe os testes de tela ou os do vídeo num trabalho à parte.

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
- **Tempo** (corrigido na segunda revisão): neste ambiente, a suíte inteira da v0.20.0 levou 539 s (634 aprovados e 61 pulados);
  a da v0.21.0, 818 a 850 s depois da primeira revisão e 817 s (13min37s) depois da segunda. São uns 5 minutos a mais, e não
  perto de 1, como estava escrito antes (a conta pela soma das etapas subestimou os testes de tela). No GitHub, a v0.20.0 inteira
  (instalação e testes) levou menos de 9 minutos; com uns 5 minutos a mais de testes, a folga até o antigo limite de 20 minutos
  cairia para uns 5 minutos, e mais umas rodadas de tela na v0.21.1 cortariam o `radar-testes` (o resultado sairia como
  "cancelado", e não como falha). Por isso o `timeout-minutes` do `radar-testes.yml` passou de 20 para 30; meça o tempo no Actions
  depois do merge e, se passar de uns 20 minutos, separe os testes de tela num trabalho à parte. O workflow passou a rodar também
  quando muda o `radar-pauta.js`, o `radar-config.js` ou o `.gitignore`.

### Correções da revisão (18 achados)

Os 18 achados da revisão foram conferidos no código: todos eram reais e foram corrigidos (os 2 dos canais da aprovação à mão e os 2
do canal que não saiu eram o mesmo defeito, visto do banco e da tela; o do Safari, pelo comportamento documentado do WebKit, sem
iPhone aqui). Cada correção tem teste, e cada teste foi rodado com a correção desfeita (no banco e na tela, no próprio arquivo, com a
cópia guardada e restaurada; nas funções e no "Testar conexão", numa cópia do repositório) e falhou: 32 de 32 reversões.

- **Banco** (`test_radar_banco.py`): desfazer a aprovação à mão pede "Conferi no Instagram e no Facebook: não foi postada à mão" e a
  nova aprovação pede "Conferi … não saiu" (`manual_desfeita_em`); os canais aprovados ficam na peça (`aprovado_canais`): copiar,
  conferir o termo e registrar o link valem só neles; com o Instagram publicado e o Facebook em erro (ou esperando a hora), o
  administrador desiste só do Facebook, a peça continua aprovada e a falha sai do painel; o RADAR169 manda cancelar na Pauta;
  "(conferir)" na fonte ou no texto trava; o cartão a mais que as fotos no carrossel de fotos trava; a evidência da instalação mostra
  a versão da instalação mais nova (antes, `max(versao)` dava "v0.7.0"); a conferência do boletim pago para a IA
  (`radar_pauta_copia_paga_ia`) só para quem edita a Pauta.
- **Tela** (`test_radar_telas.py`): à mão, só os botões e o campo de link dos canais aprovados; a cópia começa no toque (antes da
  resposta do banco) e, recusada pelo navegador, o texto aprovado aparece num campo só de leitura; "Desfazer aprovação" à mão pede a
  caixa; "Não publicar neste canal" na peça e no quadro "Não saíram"; a agenda calculada deixa a fonte em branco; a foto HEIC é
  avisada no fim, com o resultado; o CSV do Excel com colunas vazias no fim é aceito; a arte junta as pessoas da mesma área e avisa o
  que não coube (pessoas e vencimento longo da agenda) e a faixa legal vai até 3 linhas; o "Testar conexão" mostra a versão da
  `radar-redes` e avisa a anterior à v0.21.0.
- **Funções:** a máscara de nomes da `radar-ia` não diferencia acento nem a forma NFC/NFD; o plano e as informações conferidas com
  frase do boletim pago são recusados antes da IA; a `radar-redes` desiste do armazenamento preso em 10 s (nos testes, 1,5 s) e grava
  "erro" em vez de ficar "enviando".
- **Robô** (`test_radar_e2e.py`): o aviso da Pauta fecha quando o administrador desiste do canal que não saiu, e a falha seguinte
  abre outro.

São 11 testes novos (de 782 para 793 no total). Testes antigos ajustados: a fonte provisória "(conferir)" dos testes virou "Agenda
Tributária da Receita Federal"; a cópia à mão aprova os dois canais, e o termo revogado é conferido no canal copiado; a evidência da
instalação, a agenda calculada, a foto HEIC, o "Testar conexão" e a contagem das funções da Pauta (26). A suíte inteira levou de
818 a 850 s neste ambiente (732 aprovados e 61 pulados nas duas rodadas).

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
vai à IA, que não diferencia maiúsculas nem acentos: uma palavra comum igual a um nome cadastrado também é trocada no texto que vai
à IA (nada vaza; só a sugestão pode ficar estranha).

### Correções da segunda revisão (18 achados)

Os 18 achados foram conferidos no código: todos eram reais e foram corrigidos (os dois da máscara de nomes da `radar-ia` eram o mesmo
defeito, visto duas vezes, e os dois do nome com acento e caixa alta também). Cada correção de código tem teste, e cada teste foi
rodado com a correção desfeita (no próprio arquivo, com a cópia guardada e restaurada e o sha256 conferido no fim) e falhou: 38 de
38 reversões. Os 3 achados só de documentação (o tempo deste relatório, a fonte das obrigações e o termo revogado no LEIAME) não
têm teste.

- **Banco** (`test_radar_banco.py`, 5 novos):
  - a trava dos números aceita o registro no CRC da pessoa marcada, os telefones do Fale Conosco (dos setores e dos responsáveis) e
    os `fatos_fixos` com fonte de Configurações → Pauta ("desde 1984"); o número fora volta como está escrito ("0530", não "530"),
    com o que fazer ("Acrescente cada um em Informações conferidas, com a fonte"); o roteiro do reel não conta as marcações de tempo
    ("0 a 3 s", "12–32s", "cerca de 44 segundos", "0:15", "110 palavras");
  - qualquer marcador dos modelos entre chaves (`{formação}`, `{ano de entrada}`, `{PESSOA2}`…) trava na lista (legendas, chamada,
    apoio, cartões e roteiro), no "Publicar agora", antes de sair pela agenda e na cópia à mão; `{}` vazio não conta;
  - o nome cadastrado é achado sem acento, em caixa alta e em NFD (texto colado do Mac), na pessoa não marcada, no sobrenome que o
    termo não autoriza e no "contador"/"técnico" (este em qualquer caixa); em minúsculas, não (palavra comum), e por isso a caixa
    "Conferi: … só aparecem as pessoas marcadas" passou a ser pedida em toda aprovação;
  - na Agenda da semana em Imagem 4:5, a lista desenhada na lâmina passa pelas travas de [VERIFICAR], `{confirmar}`, chaves e nome;
  - a chave do robô não lê `radar_imagens` (a capa vem pela vista nova `radar_v_capas`), a auditoria, nem a legenda, a imagem e o erro
    dos envios (lê o andamento, como o robô e a `radar-redes` pedem); o leitor não lê as fotos nem as lâminas da Pauta, nem a cópia da
    lâmina no envio; o editor lê tudo.
- **Robô** (`test_radar_site_publicar.py`, 1 novo): a capa do site vem de `radar_v_capas`; com o banco antigo (404), de
  `radar_imagens`, como antes; outro erro não é engolido. O teste antigo da publicação no site confere que a capa continua indo.
- **Agenda** (`test_radar_agenda.py`, 1 novo): o `agenda_teste` do fim do `sql/radar-redes-agenda.sql` roda como está, só sem os
  `--`: a chave anon vem do próprio agendamento (sem marcador para trocar e sem repetir a chave no arquivo).
- **Função `radar-ia`** (`test_radar_funcao_ia.py`, 1 novo): o nome que está só no "quem aparece" de outra peça (a pessoa ainda sem
  cadastro, citada no assunto e na observação desta) também não vai à IA.
- **Termos da Pauta** (`test_radar_publicidade.py`, casos novos): o desconto da folha (perto de INSS, IRRF, parcela, 13º, salário
  ou vale-transporte, antes ou depois, na mesma linha) não trava, nas duas cópias da lista; "desconto no honorário" continua travando.
- **Repositório** (`test_radar_repositorio.py`, 2 novos): o cabeçalho do calendário é achado com vírgula, tabulação, aspas e
  maiúsculas, no `.md` do calendário e na tabela das pessoas dos `.md` do plano; o `.gitignore` barra qualquer CSV novo (com acento ou
  maiúscula) e os 7 `.md` do plano em qualquer pasta; o workflow novo `radar-repositorio.yml` roda em todo push, sem filtro de caminho.
- **Telas** (`test_radar_telas.py`, 3 novos): a peça agendada com todos os canais cancelados diz "Aprovada, sem canal (não vai sair)"
  na semana e na peça; o termo da publicidade na lista da agenda trava, dizendo a linha; o leitor não vê foto nem lâmina, e a lâmina
  da peça agendada some quando o termo de alguém deixa de valer no dia da peça; na peça à mão, as lâminas só aparecem em "Baixar as
  lâminas"; Configurações → Pauta confere os `fatos_fixos`. Testes antigos ajustados: a mensagem dos números, a caixa das pessoas
  (pedida em toda aprovação) e a contagem de tabelas e visões (34) e das funções da Pauta (29).

São 13 testes novos (de 793 para 806 no total). A suíte inteira levou 817 s neste ambiente (745 aprovados e 61 pulados).

O que não foi testado aqui: as permissões por coluna e a vista `radar_v_capas` no PostgREST do Supabase (no 12.2.3 dos testes
funcionam; o robô novo lê a vista e, sem ela, a tabela antiga); o `agenda_teste` com o pg_cron e o pg_net de verdade (o teste usa os
esquemas de mentira; a consulta lê a chave de `cron.job`, onde o arquivo a grava).

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
  mensagem própria; o CRC de SC escrito de outro jeito ("SC-007129/0-0") sai "CRC-SC 007129/O-0", e o formato que não é
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
