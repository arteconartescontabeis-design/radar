# Radar Artecon — v0.30.0

Plataforma de Inteligência Contábil e Tributária — Fase 1 enxuta.

Esta versão entrega a Fase 1 enxuta completa: o **banco**, os **coletores das fontes
oficiais**, as **telas** (dashboard de curadoria) e a
**inteligência artificial** (pela IA Central do Portal Artecon: Anthropic para o texto, OpenAI só para a imagem da publicação) para sugerir classificação, buscar trechos de
fundamentação e redigir rascunhos.

A v0.4.0 acrescenta o **Informativo Mensal** no padrão enviado aos clientes (agenda de
obrigações, artigos, Fale Conosco e fecho, no papel timbrado, pronto para salvar em PDF),
**imagem de capa, autor e fonte** nos conteúdos, e os botões para **copiar a notícia para o
site** da Artecon. É o modo de trabalho até a parte oficial (robô e fontes) estar validada.

A v0.30.0 traz a **agenda de obrigações com o 13º salário e as obrigações anuais** e o **aviso de possível prorrogação de
prazo**. A agenda de obrigações (Informativo Mensal e agenda da semana da Pauta) passa a ter obrigações anuais (`"mes"`: só entram na
agenda do mês delas) e a prorrogação de um vencimento (`"prorrogacoes"`, que só o administrador escreve). A agenda padrão ganha o 13º
salário (1ª parcela até 30/11; 2ª até 20/12, Lei 4.749/1965, arts. 2º e 1º; a lei não trata do fim de semana: por segurança, a agenda
antecipa para o dia útil anterior), a DEFIS (31/03, Res. CGSN 140/2018, art. 72, § 1º), a DASN-SIMEI (último dia de maio, art. 109), a
ECD (último dia útil de junho, IN RFB 2.003/2021, art. 5º) e a ECF (último dia útil de julho, IN RFB 2.004/2021, art. 3º), cada uma com a
fonte oficial. A agenda da semana da Pauta passa a ir de segunda a domingo. Na instalação que já existe, o administrador as acrescenta
pelo botão **"Acrescentar o 13º e as obrigações anuais"** (Configurações → Agenda de obrigações). Quando o Radar capta notícia que fala
em prorrogar o prazo de uma obrigação da agenda, avisa no Painel, na edição do Informativo e por e-mail ao administrador (uma vez por
notícia), **sem mudar data nenhuma**: quem confere na fonte oficial e põe a nova data é o administrador.

Mudam o banco (`sql/radar-setup-v0.30.0.sql`: duas funções novas, `radar_prorrogacao_obrigacoes` e `radar_prorrogacoes`; nenhuma
tabela nova, nada é apagado; a lista de obrigações do escritório não muda), a tela (`index.html` e `radar-pauta.js`; o `radar-video.js`
só muda a versão) e o robô dos avisos (`robo/radar_alertas.py` e `robo/radar_banco.py`, que entram no ar pelo merge). **Nenhum segredo
novo.** As funções `radar-ia`, `radar-redes` e `radar-video`, as agendas do banco (`sql/radar-*-agenda.sql`) e o robô dos lembretes não
mudam. **Rode o SQL antes de publicar a tela**: veja "Da v0.29.0 para a v0.30.0".

A v0.29.0 traz os **lembretes por e-mail antes do dia**, pedidos pelo escritório. Até aqui o Radar só avisava depois que algo
falhava (a Pauta "não saiu", a fonte parada, o resumo de segunda). Agora ele lembra **antes**:

- **a peça da Pauta de amanhã** que ainda não está aprovada (e a de hoje que ainda não saiu), na véspera, a partir das **16:00** de
  Brasília; e a peça aprovada para publicar à mão que, **uma hora depois da hora marcada**, ainda não tem a publicação registrada;
- **a peça pronta esperando a aprovação** do administrador há mais de **24 horas**;
- **o vídeo do reel que o corretor terminou** (pronto para conferir, precisa regravar ou parou);
- **a notícia que não saiu**: o envio ao site ou às redes deu erro, ou a autorização está parada há mais de **3 horas** (o robô do
  site depende do GitHub, que às vezes atrasa horas).

**Sem enxurrada:** cada tipo manda no máximo **um e-mail por dia**; cada pendência é lembrada **uma vez só** (a peça lembrada na
véspera não é lembrada de novo no dia) e, resolvida, sai da lista sozinha. O e-mail é um aviso no GitHub, como os avisos de hoje: um
aviso fixo por tipo ("Radar: lembrete — …"); o primeiro lembrete abre o aviso e os seguintes chegam como um comentário nele. O
lembrete leva só a data, a hora, o formato e o número da peça ou do envio: **nunca** o nome de alguém, o assunto, a legenda, o erro ou
o texto do boletim pago. O aviso fica na aba Issues do repositório, que é **público**: qualquer pessoa pode ler a data, a hora, o
formato e a situação das peças lembradas. Nada é publicado pelo lembrete. Horário e liga/desliga: Configurações → **Lembretes por
e-mail** (só o administrador).

Quem decide o que lembrar e quando é o **banco**, com o relógio dele (o pg_cron, que o GitHub não atrasa nem desliga): de 15 em 15
minutos ele confere e, só quando há lembrete para mandar, pede à função `radar-redes` que acione o robô dos lembretes no GitHub. O
próprio workflow também roda de hora em hora, de reserva.

Mudam o banco (`sql/radar-setup-v0.29.0.sql`, hoje `radar-setup-v0.30.0.sql`: a tabela nova `radar_lembretes`, as funções `radar_lembretes_*` e a chave "lembretes"
das Configurações; nada é apagado), a agenda do banco (`sql/radar-redes-agenda.sql`: o agendamento novo `radar-redes-agenda-lembretes`),
a função `radar-redes` (0.22.0 → **0.29.0**: a ação nova `acionar_lembretes`, só da agenda do banco, e o robô dos lembretes na lista
dos robôs que ela religa) e a tela (Configurações). Entram o robô `robo/radar_lembretes.py` e o workflow
`.github/workflows/radar-lembretes.yml` ("Radar — lembretes por e-mail"). **Nenhum segredo novo.** As funções `radar-ia` e
`radar-video`, as outras funções, a coleta (robô 0.21.0), os avisos de hoje e o resumo semanal não mudam. **Rode o SQL antes de
publicar a tela**: veja "Da v0.28.1 para a v0.29.0".

A v0.28.1 corrige a **trava da peça** na Pauta. Uma linha em branco em "Informações conferidas" (do botão "Acrescentar
informação") ou um cartão em branco (do "Acrescentar cartão") contava como alteração não salva. Como o Salvar não grava linha em
branco, ele respondia "Nada mudou na peça." e a peça continuava barrada com o aviso **"Há alterações não salvas na peça"**: o envio
do vídeo no "Corretor de vídeo", a conferência, o Gerar com IA, a aprovação e o "Cancelar a peça" só voltavam depois de recarregar
a página. Agora a linha em branco não conta, o aviso diz **o que mudou e não foi salvo** (por exemplo, "Informações conferidas" ou
"Quem aparece") e o Salvar sem nada para gravar destrava a peça. O texto digitado e não salvo continua barrando, como antes. Só a
tela muda (`index.html`, `radar-pauta.js` e `radar-video.js`): o banco continua no `sql/radar-setup-v0.28.0.sql` (hoje
`radar-setup-v0.30.0.sql`) e as funções e os
robôs não mudam. Veja "Da v0.28.0 para a v0.28.1".

A v0.28.0 traz duas novidades na **Pauta**, pedidas pelo escritório:

- **"+ Nova peça" num dia vazio:** na semana da Pauta, cada dia que ainda não tem peça (de hoje em diante, no horário de Brasília)
  mostra o botão **"+ Nova peça"** para o **administrador**. Ele pede o tipo, o formato e o assunto (objetivo, quem aparece e observação
  são opcionais) e cria a peça desse dia, que abre como qualquer outra: roteiro, "Quem aparece", fotos e, no reel, o quadro "Corretor de
  vídeo". A peça nova nasce **planejada** e **não publica nem agenda nada sozinha**: segue o caminho de sempre (preparar, marcar como
  pronta e a aprovação do administrador). Continua valendo **uma peça por dia**: o dia que já tem peça (mesmo cancelada) não ganha outra,
  e dia que já passou não recebe peça nova.
- **"Sócio(a) da Artecon":** em Pauta → Pessoas e termos, o administrador marca a pessoa como sócio(a). Para ela, o Radar **não pede o
  termo de uso de imagem** (datas, canais e finalidades) **nem o termo do corretor de vídeo**, e a pessoa aparece com o selo
  **"Sócio(a) — termos dispensados"**. **Continuam valendo:** a pessoa estar ativa, ser maior de idade, estar marcada em "Quem aparece"
  na peça e as **quatro declarações** do envio do vídeo (só aparecem as pessoas marcadas; sem tela, documento ou cliente ao fundo; só a
  voz; a fala é a do roteiro). Marcar e tirar a marca pedem confirmação; para sócio(a), a data em "Revogado em" não vale (para tirar a
  pessoa das peças e dos vídeos, desmarque "Ativa"). Marcar e desmarcar fica no Histórico, sem o nome.

Mudam o banco (`sql/radar-setup-v0.28.0.sql`, hoje `radar-setup-v0.30.0.sql`: a coluna `socio` em `radar_pessoas`, a função nova `radar_pauta_criar` e a regra dos
termos; nenhuma tabela nova, nada é apagado) e a tela (`index.html`, `radar-pauta.js` e `radar-video.js`). As funções `radar-ia`,
`radar-redes` e `radar-video`, as outras funções e os robôs não mudam. **Rode o SQL antes de publicar a tela**: veja "Da v0.27.0 para a
v0.28.0".

A v0.27.0 põe na **Pauta** o **cronograma de publicações**: no alto da semana, um quadro com a semana mostrada e o mês dela, o
**mínimo** de cada tipo de publicação ao lado do que já foi **feito**, e em **vermelho** o que já devia ter saído e não saiu. O mínimo
vem do plano da Pauta (posts no feed, reels, captação de clientes) e da busca do Radar (as notícias de relevância alta achadas no
período; a notícia ignorada na triagem enquanto ainda era alta não entra). O quadro só lê e conta: não publica nem cria nada, e mostra
só números. Os três perfis (administrador, editor e leitor) veem o mesmo quadro. O banco e as funções não mudam: a instalação é só a
tela (veja "Da v0.26.0 para a v0.27.0").

A v0.26.0 organiza a tela do assunto em **3 passos, sempre para a frente**: **1. Preparar**, **2. Conferir e aprovar** e
**3. Publicar**. Em cada passo aparece um botão principal; os outros ficam numa linha "Mais opções", sempre à vista. Só a tela muda:
o banco, as funções e o robô continuam como estão.

- **1. Preparar:** o botão **"Preparar com IA"** (antes "Gerar com IA"), com o tamanho do texto ao lado, faz tudo de uma vez: acha no
  texto oficial o trecho que comprova a notícia (só se ainda não houver um conferido) ou procura a fonte oficial na internet, escreve
  o texto, faz a capa padrão, **confere os 10 critérios das Diretrizes** e monta as legendas do Instagram e do Facebook. Leva de 2 a 5
  minutos, conta como uma consulta só (a senha é pedida no máximo uma vez) e leva o texto para "em revisão" — isso não é aprovação.
  Se o assunto já tem um rascunho (o do robô, por exemplo), **"Preparar este texto"** completa esse rascunho em vez de escrever outro;
  sem IA, "Enviar para revisão (sem IA)". A imagem com IA continua opcional (é paga), no botão do texto. A linha da fonte, no fim do
  passo, diz se a fonte oficial está confirmada ou liberada pelo administrador (com o motivo e o "Desfazer").
- **2. Conferir e aprovar:** os 10 critérios aparecem no próprio passo, com ✓/✗. O **"✓ Aprovar"** só liga com tudo certo, e a tela
  escreve o que falta: [VERIFICAR] no texto, frase do boletim pago, trecho igual ao da fonte sem autorização, campo Fonte vazio ou
  critério com ✗ ou "?" ("Conferir com IA" confere; com ✗, o administrador pode usar "Revisei e assumo", com o motivo — nunca com
  [VERIFICAR] ou boletim pago). **A confirmação da fonte continua sendo um clique de quem conferiu**: a IA acha o trecho, mas não
  confirma sozinha; o botão é **"✓ Conferi na fonte oficial"** (só o site exige). O texto Informativo fica em "Autorizar o
  Informativo" (só o administrador, com o motivo); a tela avisa que a autorização vale para o assunto inteiro, como o "Publicar mesmo
  assim".
- **3. Publicar:** uma linha por canal (Site, Instagram e Facebook) e o botão **"Publicar em todos (site, Instagram e Facebook)"**:
  cada rede tem a sua caixa e a sua legenda, e a tela pede a sua confirmação. O site sai primeiro; o Instagram e o Facebook saem
  sozinhos logo depois que a notícia entra no site. O passo só fica concluído quando cada canal foi publicado ou recebeu "Não
  publicar". Dá para cancelar só o Instagram (ou só o Facebook) que ia junto com o site. Depois de aprovado, o que falta para o site
  (texto oficial, trecho, confirmação) aparece aqui: a trilha não volta para o começo.

Nada muda nas travas: o robô só cadastra a notícia, nada é publicado sem a autorização do administrador (canal por canal), e o
[VERIFICAR], o boletim pago e o texto Informativo continuam travando. Muda só a tela (`index.html`; no `radar-pauta.js` e no
`radar-video.js`, só o número da versão). **O banco continua na v0.25.0** (`radar-setup-v0.25.0.sql`, sem SQL novo), e a `radar-ia`
(continua a v0.25.1; a tela pede a v0.25.0 ou mais nova), a `radar-redes`, a `radar-video`, a `radar-itc`, a `radar-concorrentes` e
os robôs não mudam. Para instalar, "Da v0.25.1 para a v0.26.0".

A v0.25.1 traz três ajustes pequenos, anotados na revisão da v0.25.0:

- **Legenda montada pelo Radar com os itens de lista em linhas próprias:** quando não há kit da IA, a legenda do Instagram e a do
  Facebook resumem o começo do texto. Os itens de lista ("- item", "* item", "• item", "1. item" ou "1) item") saíam emendados no fim
  da frase de antes ("…com 0,9% na fase de transição. revisar o cadastro fiscal dos produtos e serviços; confirmar com o fornecedor…").
  Agora cada item sai na sua linha, como "• Item", com a primeira letra maiúscula e sem o negrito (a palavra que já tem maiúscula no
  meio, como "eSocial" ou "e-CAC", e o item que começa com número ficam como estão). O resto da montagem não muda: o título, o resumo
  de cerca de 280 caracteres, o caminho até o site, a fonte, a linha "Imagem ilustrativa gerada por IA." (quando a imagem é da IA) e a
  identificação legal no fim, que nunca são cortadas, e as hashtags no Instagram. O limite (2.200 caracteres, ou 2.000 no "Publicar em
  todos") continua, e o corte tira só o fim do texto, numa linha inteira. As legendas já gravadas, editadas na tela ou publicadas não
  mudam.
- **Kit das redes sem a arte:** a função `radar-ia` não pede mais à IA a chamada e o apoio da arte, que só serviam à arte vertical das
  notícias (ela saiu na v0.25.0). O pedido e o esquema da resposta do kit ficam com as legendas do Instagram e do Facebook e o roteiro
  do reel. A tela aceita o kit novo e também o kit gravado antes, com a arte (que ela ignora). A peça da Pauta (ação `peca`) tem a
  própria arte e não muda.
- **Acessibilidade:** o campo de arquivo da imagem do conteúdo tinha dois rótulos ligados a ele ("Imagem da publicação" e "enviar uma
  foto própria"); fica um só, "enviar uma foto própria". "Imagem da publicação" continua como título do bloco, com a mesma aparência.

Mudam a função `radar-ia` (v0.25.1: o kit sem a arte) e a tela (`index.html`; no `radar-pauta.js` e no `radar-video.js`, só o número
da versão). **O banco continua na v0.25.0** (`radar-setup-v0.25.0.sql`, sem SQL novo); a `radar-redes`, a `radar-video`, a
`radar-itc`, a `radar-concorrentes` e os robôs não mudam. A versão mínima da `radar-ia` que a tela pede continua a v0.25.0: a tela nova
funciona com a função da v0.25.0 (o kit dela traz a arte, que a tela ignora). Para instalar, "Da v0.25.0 para a v0.25.1".

A v0.25.0 faz da imagem **uma só para todas as publicações**: a mesma imagem (o mesmo arquivo) vai para o **site**, o **Instagram** e
o **Facebook**, e a imagem da IA passa a ter **aparência de foto** e a ir **inteira**, com o aviso de IA pequeno no canto:

- **Imagem única:** no conteúdo, o bloco **"Imagem da publicação"** diz "A mesma imagem vai para o site, o Instagram e o Facebook." É
  a imagem que o robô manda ao site e a que o administrador vê e autoriza no passo de cada rede, no "Publicar em todos" e no "Publicar
  nos canais que faltam" (os mesmos bytes). A **arte vertical** das notícias nas redes (1080×1350, com chamada, apoio e rodapé por cima,
  v0.20.0) saiu, e com ela os campos "Chamada da arte", "Linha de apoio" e "Fundo da arte". A arte vertical continua **só nas peças da
  Pauta** (posts de pessoas com foto, carrossel, captação, agenda), que não mudam. O Instagram aceita imagens de 4:5 a 1,91:1: a 3:2 e a
  capa padrão (1200×630) servem como estão, e a função `radar-redes` não muda.
- **Imagem com aparência de foto:** o "Gerar imagem com IA" pede uma **fotografia realista de estilo editorial** (luz natural,
  profundidade de campo, cores naturais, ambiente brasileiro de trabalho), coerente com o assunto. **A cena que você descreve e as
  orientações do escritório para as imagens mandam na cena** (antes, uma regra fixa de "ilustração plana, nas cores da marca, com figuras
  estilizadas" vinha antes do pedido e passava por cima dele). Pessoas sempre fictícias e adultas, sem foco em rosto reconhecível; nunca
  texto, logotipo, marca-d'água, pessoa real ou conhecida, estilo de artista ou fotógrafo, nem cena que induza a erro (documento oficial
  simulado, fachada de órgão público com nome, dinheiro em destaque). A descrição vai até **500 caracteres** (antes 200).
- **Inteira, em 3:2, com o aviso no canto:** a imagem da IA é gravada inteira, no formato horizontal 3:2 em que a IA cria (até
  1500×1000), sem título, logotipo, selo, degradê nem rodapé por cima, e com o aviso **"Imagem ilustrativa gerada por IA"** pequeno no
  canto de baixo, à direita (letra branca numa faixa escura translúcida). No site, o texto termina com a linha **"Imagem ilustrativa
  gerada por IA."**; nas legendas do Instagram e do Facebook, a mesma linha vem logo antes da **identificação legal** (empresa · CNPJ ·
  CRC), que continua no fim de toda legenda. A legenda sem a linha não é autorizada.
- **Qualidade alta:** a imagem sai em qualidade alta (`quality: "high"`), que **custa mais por imagem** do que a média de antes (o valor
  fica no Portal → Consumo de IA). Se a IA Central não aceitar a qualidade alta, a função não troca de qualidade sozinha: a tela mostra o
  recado para o administrador liberar.
- **Os botões:** "Gerar imagem com IA" (vira a imagem da publicação, com o aviso), enviar uma **foto própria** (vai em 3:2, cortada no
  centro, sem nada por cima e sem aviso; foto de alguém da equipe só com o termo de uso de imagem assinado), **"Usar a capa padrão
  Artecon (sem imagem)"** (o fundo azul com o título) e, quando há uma imagem da IA guardada, **"Usar a imagem da IA de novo"** (sem
  nova cobrança). Sem nenhuma imagem escolhida, vai a capa padrão (todo conteúdo nasce com ela). O aviso de título mudado só aparece com
  a capa padrão, a única que leva o título. Saíram "Atualizar a capa (com a ilustração)", "Capa padrão, sem a ilustração" e "Remover
  imagem".
- **O que é antigo não muda sozinho:** a capa montada antes com a ilustração ao fundo continua até alguém trocar a imagem ("Usar a imagem
  da IA de novo" faz dela a imagem inteira, em 3:2, com o aviso, sem consultar a IA; trocada pela capa padrão ou por uma foto, a
  ilustração fica guardada já em 3:2, com o aviso, e o critério 6 atende); o que já foi publicado fica como está. Enquanto não é
  trocada, a capa antiga vai às redes com a linha "Imagem ilustrativa gerada por IA." na legenda (sem ela, não autoriza). A foto
  enviada antes desta versão ficou na proporção original: fora de 4:5 a 1,91:1, a tela avisa no quadro das redes e não autoriza o
  Instagram até a foto ser enviada de novo (vai em 3:2) ou trocada pela capa padrão; o Facebook aceita.
- **A prévia mostra a imagem inteira:** nos quadros das redes e no "Ver como fica no site", a imagem aparece inteira, na proporção dela,
  com o aviso do canto à vista (antes, a caixa 4:5 da arte vertical e a prévia do site cortavam as bordas).
- **Conferência das Diretrizes, critério 6:** a imagem da IA em uso, com o aviso no canto, atende sozinha; a capa padrão e a foto da
  equipe atendem como antes (também com a imagem da IA guardada fora da publicação); a capa antiga montada com a ilustração continua
  pedindo o aviso escrito no fim do texto (✗ sem ele).

Mudam o banco (`radar-setup-v0.25.0.sql`: só a função `radar_conferencia_codigo`, do critério 6; nenhuma tabela nem coluna nova, nada
apagado), a função `radar-ia` (v0.25.0: o pedido da imagem, a qualidade alta e a descrição até 500), a tela (`index.html`; no
`radar-pauta.js` e no `radar-video.js`, só o número da versão e o nome do SQL no aviso) e o robô do site (`robo/radar_site_publicar.py`:
a linha do aviso de IA no fim do texto). A `radar-redes` continua na v0.22.0 (ela não confere tamanho nem proporção da imagem, só que
seja JPEG); as agendas não mudam. As fotos do banco gratuito (Pexels) ficam para uma etapa seguinte. Para instalar, "Da v0.24.0 para a
v0.25.0".

A v0.24.0 põe as **Diretrizes editoriais do escritório** dentro do Radar: a IA escreve seguindo-as, o texto sem base legal vira
**Informativo** (que só o administrador autoriza), a aprovação passa pela **Conferência das Diretrizes** (os 10 critérios), o escritório
ensina a IA pelas **"Orientações para a IA"**, sem programador, e (etapa 5) os textos ficam **mais humanos**, com uma **revisão editorial
automática** antes da aprovação:

- **Textos mais humanos (etapa 5):** a IA escreve como um jornalista especializado em economia, contabilidade e tributos, para
  empresários: começa pelo fato mais importante, varia as frases, não usa as fórmulas de texto automático ("Nesse cenário", "Vale
  ressaltar que", "abre uma janela de oportunidades"…), não repete a informação e não exagera. A organização segue o assunto (notícia
  simples em poucos parágrafos; mudança de lei com subtítulos, datas e impactos). A **"Análise Artecon" é opcional**: só entra quando
  acrescenta conhecimento técnico de verdade. **Sem chamada comercial automática** ("fale com a Artecon", urgência) nos textos e nas
  legendas. Vale para o "Gerar com IA" (e as passadas dele), os títulos, o "Revisar com IA", o kit das redes, as peças da Pauta e os
  rascunhos do robô. Veja "Diretrizes editoriais e como ensinar a IA", "Humanização dos textos".
- **Fonte oficial (etapa 5):** a norma é citada uma vez, com naturalidade, no próprio texto, e o texto termina com uma linha curta
  **"Fonte oficial: norma — link"**, no lugar da seção pesada "Fundamentação legal" (os textos de antes, com a seção, continuam valendo).
- **Revisão editorial automática (etapa 5):** depois de escrever, a IA relê o rascunho com as **10 perguntas** do escritório e reescreve
  os trechos com problema; o conteúdo mostra o quadro **"Revisão editorial"** (cada pergunta com ✓ ou ✎ e o que foi reescrito). Não é
  detector de IA, nunca acrescenta dado e não trava o Aprovar. Custa uma consulta a mais à IA por texto gerado.

- **Diretrizes na IA:** em todo texto que a IA escreve para publicar (o "Gerar com IA" e a segunda passada dele, os outros títulos, o
  "Revisar com IA", o kit das redes e o "Gerar com IA" da peça da Pauta), depois das regras de sempre: obrigação, direito, prazo ou
  benefício só com a norma que o sustenta; o que não tem base legal, só como informação; texto próprio (transcrição literal só de
  artigo de lei ou de declaração importante, entre aspas e com a fonte; citar a fonte não autoriza copiar); projeto de lei não é lei
  aprovada e previsão não é fato; linguagem clara, sem exagero. As regras de antes continuam valendo (só fatos do texto oficial, nada
  de memória, boletim pago nunca copiado, publicidade contábil, palavras barradas). Veja "Diretrizes editoriais e como ensinar a IA".
- **Fonte oficial com link:** o texto com base legal termina com a linha **"Fonte oficial"** (até a etapa 4, a seção "Fundamentação
  legal"): a norma, o número (e o artigo, quando precisa) e o **link do documento oficial**. A IA só usa link que está no assunto (a página oficial capturada, a das evidências
  conferidas, o endereço oficial da norma e as páginas oficiais da "Verificar em fontes oficiais"); o link que ela inventar **sai do
  texto sozinho**, com aviso. Sem link, a norma fica sem ele e vai para os pontos a conferir, num aviso à parte ("Norma que ficou no
  texto, a conferir…"). A vigência (em vigor, alterada, revogada) só é afirmada se o texto oficial ou a verificação mostrar; sem isso,
  vai para o mesmo aviso. A data e o artigo da norma só entram quando estão no texto oficial (nada de memória). O robô do site e a
  prévia transformam o endereço do texto em link.
- **Texto Informativo:** sem texto oficial (ou quando a IA diz que o assunto não tem base legal específica), o "Gerar com IA" escreve um
  texto **Informativo**: os fatos e o que eles mudam na prática, com palavras próprias, sem nada apresentado como obrigação,
  separando fato de estimativa e dizendo de onde veio a informação (do boletim pago, só a informação, com palavras próprias e
  atribuída a ele). Ele fica em análise, com o selo **"Informativo — aguardando autorização"**, sem o botão Aprovar: **só o
  administrador autoriza a publicação** ("Autorizar a publicação do Informativo", com o motivo, que fica no assunto e no Histórico; é
  o mesmo "Publicar mesmo assim" de antes). Autorizado, segue a aprovação, o site e as redes como os outros, com o selo "Conteúdo
  informativo"; no site, a notícia sai com a linha **"Conteúdo informativo"** no fim. O banco não aprova o Informativo antes da
  autorização, nem pela API. A autorização é a do **assunto inteiro** (o mesmo "Publicar mesmo assim"): ela também dispensa a
  fundamentação oficial dos outros textos do assunto, e o Informativo gerado depois num assunto já liberado já nasce autorizado
  (mostrando o motivo de antes). "Desfazer a liberação" devolve o Informativo aprovado para a revisão. No pedido à IA, o modo se chama
  "SEM BASE LEGAL", para não se confundir com o tamanho "Médio (notícia)" (antes chamado "Informativo" na tela): o selo do tamanho
  passa a ser "Curto (aviso rápido)", "Médio (notícia)" ou "Longo (artigo)", e a palavra "Informativo" fica só para o texto sem base
  legal. O "texto para análise" antigo continua como estava.
- **Conferência das Diretrizes antes de aprovar:** no conteúdo, um quadro com os **10 critérios** do escritório, cada um com ✓
  (atende), ✗ (não atende), — (não se aplica) ou ? (não conferido) e o motivo numa linha. O que dá para conferir por código o Radar
  confere sozinho: [VERIFICAR] (critérios 2 e 8), texto igual ao da fonte fora de aspas (4 e 5), frase do boletim pago (4), texto que
  cita norma sem a linha "Fonte oficial" com link oficial (2), Informativo sem a fonte (3) e a capa (6: padrão da Artecon ou foto da
  equipe atende; ilustração da IA só com o aviso "Imagem ilustrativa gerada por IA" escrito no fim do texto; sem capa, não se aplica).
  O resto, a IA confere: o **"Revisar com IA"** agora sempre confere o texto (fontes, título × conteúdo, atualidade, clareza, risco
  de induzir a erro) e devolve a lista, que o banco grava presa à versão do texto; se houver marca, cópia ou a linha "Fonte oficial"
  faltando, ele corrige antes, como antes. Com ✗ ou ?, **o Aprovar fica travado**; o administrador pode liberar com **"Revisei e
  assumo"**, com o motivo (aparece no Histórico, com o texto do motivo). Conferir de novo o mesmo texto não tira um ✗ (só o texto
  corrigido, que é outra versão, ou o "Revisei e assumo"). Mudou o título, o texto, a fonte ou a capa, a conferência deixa de valer. O
  banco confere de novo na aprovação. As travas de antes continuam: [VERIFICAR] e boletim pago não passam nem com o "Revisei e assumo"
  (com eles no texto, o botão nem aparece). No Informativo, que não tem a linha "Fonte oficial", a norma só mencionada não leva ✗
  no critério 2 por código: a IA confere se nada foi apresentado como obrigação.
- **Texto igual ao da fonte citada:** até a v0.23.0, o trecho igual ao da fonte podia ficar quando o parágrafo dizia de onde veio
  (quadro azul). Agora, fora de aspas, ele marca os critérios 4 e 5 com ✗: reescreva com palavras próprias (o "Revisar com IA" faz
  isso) ou ponha entre aspas só a frase indispensável; ou use "Autorizar mesmo assim", com o motivo, como no trecho sem a fonte. A
  transcrição literal (de artigo de lei ou de declaração importante) **entre aspas e com a fonte citada no parágrafo** pode ficar,
  mesmo longa (quadro azul). No kit das redes, o trecho igual fora de aspas também aparece nos pontos a conferir. O detector é o mesmo
  (na tela, na função e no robô), só que agora diz também se o trecho estava entre aspas.
- **Orientações para a IA:** Configurações → Inteligência artificial → "Orientações para a IA". Dois campos de texto livre, com o
  contador de caracteres e um exemplo dentro de cada um: **"Orientações para os textos"** (até 2.000 caracteres: tom, estilo, tamanho,
  o que evitar e exemplos de posts de que o escritório gostou) e **"Orientações para as imagens"** (até 500: estilo, cenas preferidas,
  o que evitar). Só o administrador altera; o Salvar é o de sempre ("Configuração salva.") e a mudança fica no Histórico. Valem nos
  mesmos pedidos das Diretrizes e em toda ilustração; vão no fim das instruções da IA, num bloco à parte, **depois** das regras e das
  Diretrizes, como preferência de estilo (as regras passam por cima). Os exemplos de posts servem só de modelo de estilo: a IA não usa
  os fatos, os números nem as datas deles. Na peça da Pauta, os nomes da equipe, os links e os números de CNPJ, CRC e telefone escritos
  nas orientações também não vão à IA. Na imagem, as preferências entram antes das proibições (sem texto, sem pessoa real, sem marca);
  se pedirem marca, logotipo, pessoa conhecida ou o estilo de um autor, ficam de fora daquela imagem e a tela avisa, com a palavra que
  travou (a ilustração sai do mesmo jeito). Em branco, a IA trabalha como antes. Frase igual à do boletim pago (ITC) não entra nas
  orientações: a tela recusa ao salvar.

Mudam o banco (`radar-setup-v0.24.0.sql`: coluna `conferencia` em `radar_conteudos`, as funções da Conferência das Diretrizes e a trava
do Informativo na aprovação; na etapa 5, a revisão editorial guardada na mesma coluna, com as funções `radar_registrar_revisao_editorial`
e `radar_texto_versao`, e a linha "Fonte oficial" aceita na conferência; nenhuma tabela nem coluna nova), a função `radar-ia` (v0.24.0),
a tela (`index.html`; no `radar-pauta.js` e no `radar-video.js`, o número da versão e o aviso do SQL) e o robô do site
(`robo/radar_site_publicar.py`: o link no texto e a linha "Conteúdo informativo"). As orientações ficam em `radar_config`, na chave
`ia_orientacoes` (a equipe lê, só o administrador altera). A `radar-itc` continua na v0.23.0; a `radar-redes`, a `radar-video`, a
`radar-concorrentes` e o robô do vídeo, na v0.22.0; as agendas (`sql/radar-*-agenda.sql`) não mudam. Os rascunhos automáticos do robô
(`robo/radar_rascunhos.py`) seguem a escrita humana e a Análise Artecon opcional (etapa 5), mas ainda não usam as Diretrizes, as
orientações nem a revisão editorial (o quadro do conteúdo oferece "Fazer a revisão editorial"): passam pela Conferência das Diretrizes
como qualquer texto (o "Revisar com IA" acrescenta a linha "Fonte oficial" que faltar). A Pauta
(peças das redes) continua com a aprovação dela, sem a Conferência. Correção junto: o reel aprovado à mão antes da v0.22.0 (sem o
corretor) continua registrando o link também em quem vai da v0.21.0 direto para a v0.24.0 (a regra conta a primeira instalação da
v0.22.0 ou de uma versão mais nova). Para instalar, "Da v0.23.0 para a v0.24.0".

A v0.23.0 deixou a **leitura do boletim da ITC** pronta para a troca do acesso à caixa e as **agendas do banco** prontas para rodar
de novo:

- **A caixa inteira:** a função `radar-itc` lê o boletim em qualquer pasta da caixa, **menos o Lixo Eletrônico e os Itens
  Excluídos**. O boletim pode ser movido da Caixa de Entrada para a subpasta "ITC Consultoria" (ou outra) a qualquer hora, até antes
  da leitura das 02h55; o e-mail com o remetente da ITC que caiu no Lixo Eletrônico (pode ser forjado) nunca entra. Se não conseguir
  saber quais são essas duas pastas, a função para com o motivo, em vez de ler sem o filtro. O segredo `ITC_PASTA`, se preenchido,
  mantém a leitura só daquela pasta (como antes); vazio é o padrão novo.
- **Sem ler duas vezes:** mover o e-mail de pasta muda o id dele no Microsoft Graph. O controle de "já lido" passa a usar o
  identificador da mensagem (`internetMessageId`), que é o mesmo em qualquer pasta: o boletim movido depois de lido não volta à IA, e
  a cópia do mesmo e-mail em duas pastas entra uma vez só. A coluna de `radar_itc_lidos` já aceitava esse identificador: o banco não
  muda (e a tabela está vazia em produção: nada a migrar).
- **O Lixo não esconde o boletim:** a lista do Microsoft Graph vem em pedaços, e o Lixo Eletrônico e os Itens Excluídos só saem
  depois. A função segue os pedaços (até 5) até achar os boletins: muitos e-mails com o remetente da ITC no Lixo (forjados, por
  exemplo) não deixam mais o boletim de fora. Se forem tantos que a lista não acaba, a aba Fontes mostra a falha ("muitos e-mails com
  o remetente da ITC no Lixo Eletrônico ou nos Itens Excluídos… confira a caixa") e a leitura não conta como boa; o "Testar conexão"
  também acusa.
- **Acesso só à caixa do boletim:** o passo a passo troca o Mail.Read do Entra (que abre todas as caixas do escritório) pela
  atribuição **"Application Mail.Read" do Exchange Online, só na caixa do boletim** (RBAC for Applications; a
  `New-ApplicationAccessPolicy` é legado). Quando falta a permissão, o "Testar conexão com o e-mail" e a aba Fontes dizem o que
  conferir e que a atribuição leva **de 30 minutos a 2 horas** para valer; o teste conta os boletins dos últimos 7 dias na caixa
  inteira. Veja "Boletim da ITC pelo Microsoft Graph".
- **Agendas que rodam de novo** (a pendência anotada para a v0.22.1): o `sql/radar-itc-agenda.sql`, o `sql/radar-redes-agenda.sql`, o
  `sql/radar-video-agenda.sql` e o `sql/radar-concorrentes.sql` só criam o pg_cron e o pg_net (e só fazem os grants do pg_cron)
  quando a extensão ainda não existe. Antes, rodar de novo no Supabase parava em **"ERROR: dependent privileges exist"**: com a
  extensão instalada, o `create extension` e os grants do cabeçalho disparavam o gatilho `grant_pg_cron_access` da Supabase. Agora
  cada um pode rodar de novo sempre que o LEIAME pedir (a troca da chave pública, por exemplo): as chaves do Vault ficam e a agenda é
  refeita, igual.
- **INLABS:** o robô tira os espaços e as quebras de linha das pontas do `INLABS_EMAIL` e do `INLABS_SENHA` (um espaço colado no
  segredo do GitHub fez o login falhar em produção).

Mudam a função `radar-itc` (v0.23.0), o cabeçalho das extensões nos quatro SQL acima, o robô (`robo/radar_inlabs.py`) e o número da
versão na tela (`index.html`, `radar-pauta.js` e `radar-video.js`). **O banco continua na v0.22.0** (`radar-setup-v0.22.0.sql`, sem
SQL novo de instalação); a `radar-ia`, a `radar-redes`, a `radar-video`, a `radar-concorrentes` e o robô do vídeo continuam na v0.22.0.
Para instalar, "Da v0.22.0 para a v0.23.0".

A v0.22.0 trouxe o **corretor de vídeo dos reels**: a equipe grava o reel no celular, envia pela peça da Pauta e recebe o vídeo pronto
para postar, conferido contra o roteiro:

- **Enviar:** na peça reel, a **"Fala para conferência"** mostra o que o corretor compara (tirada do roteiro: a coluna "Fala" da
  tabela do plano ou as linhas "Fala:" do kit). A equipe grava por bloco (1080p, 30 quadros por segundo, Vídeo HDR desligado, na
  vertical), escolhe de 1 a 12 clipes na ordem, quem fala e as 4 declarações e clica em "Enviar a gravação". Os clipes vão direto do
  navegador para um armazenamento **privado** do Radar, num envio que continua de onde parou se a internet cair. Antes de qualquer
  arquivo sair, o banco confere a fala no roteiro, o boletim pago, o termo de cada pessoa (o **termo novo**, que cita o corretor), a
  idade e a cartela.
- **O robô** roda no GitHub Actions de um **repositório privado** (`radar-video`), com o código deste repositório num commit fixo:
  transcreve a fala pela **Azure gratuita** do escritório (o recurso F0 da Agenda, pelo Speech SDK: 5 horas por mês divididas com a
  Agenda, um pedido por vez), compara com o roteiro **só por código, sem IA**, corta o começo, o fim, as pausas longas e as
  hesitações, limpa o som e acerta o volume, grava a legenda na grafia do roteiro, o texto do gancho (opcional) e a cartela final com
  a identificação legal, e confere o MP4 no formato do Instagram e do Facebook, sem a localização do celular. O ffmpeg roda num
  contêiner sem rede e sem segredo, e o robô não tem chave do Supabase: fala só com a função `radar-video`, com um token estreito.
- **O que não corrige:** nenhuma palavra é trocada, acrescentada ou inventada, e "um", "uma", "e" e "é" nunca saem. Número, data ou
  termo diferente do roteiro, termo que a publicidade contábil não usa e frase do boletim pago na fala viram **"Precisa regravar"**.
  Nada de IA que crie ou imite rosto ou voz, de música ou de conserto de imagem.
- **Relatório, prévia e ajustes:** o relatório parcial (o que precisa regravar) chega antes do vídeo; o final traz a duração, os
  cortes, a legenda, o som e 4 quadros. A prévia abre por um link de 10 minutos. O administrador pode manter um corte, marcar "A
  transcrição errou (vale o roteiro)", editar a legenda palavra por palavra (sem mudar número, data ou termo), pedir a legenda
  compacta, tirar o gancho ou refazer a cartela: o vídeo é montado de novo sem transcrever de novo, e o áudio não muda.
- **Aprovar, baixar e postar:** a aprovação do reel (só o administrador) fica amarrada ao vídeo que ele viu na prévia (o sha256 do
  arquivo). Aprovado, "Baixar o vídeo aprovado" (link de 5 minutos), postar à mão, "Apaguei do celular e da nuvem pessoal" e
  registrar o link. A publicação automática do reel fica para a **v0.22.1**, depois dos primeiros reels reais.
- **Guarda:** o original sai ao publicar, substituir, descartar ou revogar o termo, ou em 30 dias; o vídeo final, 30 dias depois de
  publicado (os prazos ficam nas Configurações). Nada do vídeo, da fala ou dos nomes vai ao repositório público nem aos registros:
  **neste repositório entram só vídeos sintéticos**, gerados pelo ffmpeg na hora dos testes.

Também nesta versão: **"Preencher fontes oficiais"** (Configurações → Agenda de obrigações), que põe a fonte oficial conferida de cada
vencimento nas obrigações da agenda das redes que estão sem fonte, e o **CRC certo da Artecon**, "CRC-SC 007129/O-0", na ajuda e nos
exemplos das Configurações e deste LEIAME (o que está salvo nas Configurações não muda sozinho: confira).

Na agenda padrão, o **Simples Doméstico (DAE)** passa a **antecipar** quando o dia 20 não é dia útil, como mandam a Lei 8.212/1991
(art. 30, V, e § 2º, II) e o Manual do Empregador Doméstico do eSocial (exemplo: 20/11/2026 é feriado nacional, então vence em 19/11).
Vale para a instalação nova; na que já existe, o administrador troca o `"ajuste"` para `"antecipa"` em Configurações → Agenda de
obrigações (na Artecon, já trocado em 13/10/2026).

Mudam o banco (`radar-setup-v0.22.0.sql`: 2 tabelas novas, `radar_videos` e `radar_video_acessos`; 3 campos em `radar_pessoas`; a
amarra do vídeo na peça; as funções `radar_video_*`; a configuração `corretor_video`) e a tela (`index.html`, `radar-pauta.js` e o
arquivo novo `radar-video.js`). Entram a função `radar-video`, o `sql/radar-video-agenda.sql` (as chaves no Vault, a reserva da fila e
a limpeza diária) e o robô do vídeo (`robo/video/`, com o modelo do workflow do repositório privado em
`robo/video/workflow/radar-video.yml`). A `radar-ia`, a `radar-itc`, a `radar-redes` e a `radar-concorrentes` mudam só pelas
correções da varredura geral (abaixo) e vão para a v0.22.0. Detalhes em "Corretor de vídeo do reel" e, para instalar, "Da v0.21.0
para a v0.22.0".

**Varredura geral (13/10/2026), nesta mesma versão:**
- **Notícia, "Publicar em todos":** só o registro da publicação feito pelo robô do site (ou por uma pessoa depois que o envio do site
  saiu), com link do próprio site, libera o Instagram e o Facebook; enquanto o robô está na vez, "Registrar publicação no site" some
  da tela e o banco recusa o registro à mão (RADAR145). Link de outro endereço derruba as redes que esperavam, com o motivo.
- **Boletim pago na notícia:** a frase do boletim pago (ITC) não se autoriza mais ("Autorizar mesmo assim" some quando há trecho
  pago), e o banco recusa a autorização da cópia, a aprovação e a publicação no site, no Instagram e no Facebook com ela (RADAR146).
  A comparação (na notícia e na Pauta) usa todas as capturas do boletim guardadas, não só as dos últimos 90 dias.
- **Notícia, nunca duas vezes:** a publicação cancelada no meio do envio ("publicando" parada) pode ter saído; autorizar de novo o
  mesmo canal pede a caixa "Conferi no Instagram/Facebook: … não saiu" (RADAR166), como na Pauta.
- **Pauta:** a linha de identificação confere o registro no CRC inteiro (UF, número e categoria, "CRC-SC 007129/O-0"), não só os
  algarismos; a pessoa que está num vídeo do corretor ainda guardado não se apaga (marque a revogação: RADAR174); a caixa "A pessoa
  viu o vídeo final" aparece também para quem foi desmarcada depois do envio (ela continua no vídeo); o leitor lê só as imagens ligadas
  a um conteúdo (nunca a foto tirada da peça ou a lâmina de uma aprovação recusada); o selo com motivo longo quebra a linha no celular.
- **IA:** o texto de fora (página capturada, boletim, assunto, conteúdo) não fecha mais o bloco de dados em nenhuma ação (antes, só
  no kit e na peça); o nome da equipe escrito com apóstrofo curvo, hífen ou caractere invisível também vai mascarado.
- **Boletim da ITC pela função:** a falha no login da Microsoft ou na caixa fica na aba Fontes (antes, pela agenda, ninguém via).
- **Robôs e GitHub:** o "Radar — teste do site" não mostra mais o texto das notícias, quem cadastrou nem o código dos links de
  editar/excluir do painel; os workflows usam as ações fixadas pelo commit e os pacotes do `robo/requirements.txt` com versão exata
  e hash; o conferir do repositório olha também os commits do primeiro push de um ramo; os avisos (issues) contam só os abertos pelo
  robô; a fonte "Receita Federal — Atos normativos" diz o motivo de não ler nada (o sistema Normas virou aplicação montada no
  navegador); os clipes brutos do corretor (`ent/<n>`) ficam fora do Git.

**Varredura geral, rodada 2 (13/10/2026), nesta mesma versão:**
- **Boletim pago, na tela como no banco:** o banco compara o texto com **todas** as capturas do boletim (de outro assunto ou ainda na
  fila); a tela comparava só com as do assunto e mostrava "✓ nenhum trecho copiado" enquanto o banco recusava (RADAR146) sem dizer
  qual frase. Agora o banco diz **onde** está a frase no próprio texto (`radar_copia_paga_trechos`, só as posições: nada do boletim
  sai), e o quadro vermelho a mostra como "boletim pago: conferido pelo banco com todas as matérias do boletim"; o "Revisar com IA" a recebe e
  reescreve; e a legenda e a arte do Instagram e do Facebook também são conferidas assim antes de autorizar.
- **Ementa do ato oficial não é frase do boletim:** a matéria do boletim que é o próprio ato ("Legislação Federal": título
  "Lei nº … (DOU DE …)", texto = a ementa oficial, de domínio público) fica fora da comparação do boletim. A ementa copiada do DOU
  para as "Informações conferidas", o roteiro ou a legenda da Pauta (e a fala do reel) não trava mais como "frase do boletim pago".
- **CRC com acento:** o CRC das Configurações com letra acentuada ("… (Originário)") não trava mais toda peça como "falta a linha
  de identificação".
- **Pauta, "Usar a sugestão":** a linha "Fonte: …" das informações conferidas nunca é cortada (com as 9 fontes da agenda de fim de
  mês, a citação saía quebrada, "…; LC 155/2016, art."): quem encurta é o texto da IA, no fim de uma frase ("art. 9º" não é fim de
  frase); se não couber com os endereços, as fontes vão só com a norma; o recado avisa.
- **Aviso da Pauta que não sai:** com o aviso já aberto (um erro antigo sem resolver), cada publicação nova que não sai ganha **um
  comentário** no aviso (um e-mail); antes, o aviso aberto calava as falhas seguintes.
- **Robôs agendados do GitHub:** no repositório público, o GitHub desliga sozinho a coleta, o robô do site e o resumo depois de 60
  dias sem atividade. A agenda do banco pede uma vez por dia à `radar-redes` que religue os desligados por inatividade
  (`sql/radar-redes-agenda.sql`, com o `RADAR_GITHUB_TOKEN`); o acionamento do robô do site religa o dele e, se não der, diz onde
  religar, sem prometer "a próxima rodada automática"; e o **Painel** avisa quando a coleta não roda há mais de 12 horas.
- **Imagem da notícia nas redes:** vai, como a da Pauta, para o armazenamento **privado** (nome aleatório; a Meta recebe um link de
  10 minutos). Antes ia para o bucket público `radar-redes`, com nome fácil de adivinhar, e ficava lá mesmo depois de excluída da
  rede; ao excluir pela função, a imagem antiga sai do bucket público.
- **Exclusão no site:** a notícia achada só pelo começo do título (o painel encurta o título longo) é excluída só se o título
  inteiro, lido no formulário de edição do painel, for o pedido; senão, não exclui (era possível sair outra notícia da mesma série).
- **Sessão só na aba:** a sessão do Radar fica na aba (sessionStorage), não mais no localStorage da origem
  `arteconartescontabeis-design.github.io`, que é a mesma dos outros aplicativos da conta no GitHub Pages (qualquer script deles lia
  a sessão). Cada aba entra à parte; fechada a aba, a sessão some. O informativo aberto numa aba nova usa a sessão da aba do Radar.
- **Chaves novas do Supabase:** a tela, as agendas do banco, as funções e os robôs aceitam a chave pública nova (`sb_publishable_…`) e
  a interna nova (`sb_secret_…`), cada uma só no `apikey` (o Supabase desliga a anon e a service_role antigas até o fim de 2026).
  O passo a passo da troca está em "Chaves novas do Supabase (até o fim de 2026)".

A v0.21.0 trouxe a aba **Pauta**: o calendário de publicações no Instagram e no Facebook (uma peça por dia), com as peças
preparadas no Radar e publicadas pela API da Meta **na hora marcada, depois da aprovação do administrador**:

- **Calendário:** o plano de publicações entra por "Importar o calendário (CSV)" (a tela confere o arquivo inteiro e mostra todos os
  erros de uma vez, com a linha da planilha) e aparece semana a semana, de segunda a domingo. A peça que já entrou em produção não
  muda na importação. O CSV tem nomes da equipe e **nunca vai para o GitHub**.
- **Peça:** fotos da equipe (1080×1350, enviadas uma de cada vez), quem aparece (só pessoas cadastradas em **Pessoas e termos**, com o
  termo de uso de imagem), informações conferidas com a fonte oficial, chamada, apoio, cartões do carrossel, roteiro do reel e as
  legendas. A arte é desenhada na tela, com a faixa legal (empresa, CNPJ e CRC) em letra de pelo menos 28 px de altura.
- **"Gerar com IA" da peça:** a IA sugere a chamada, o apoio, as legendas e os cartões. Os nomes da equipe não vão à IA (a pessoa
  vai como `{PESSOA1}`; quem está cadastrado ou no "quem aparece" de qualquer peça do calendário vira "uma pessoa da equipe"), e o
  fato que não está nas informações conferidas volta marcado com [VERIFICAR].
- **Pronta, aprovada, publicada:** "Salvar e marcar como pronta" mostra a lista do que falta; só o administrador aprova; a peça
  aprovada não se edita. A imagem única (foto ou arte) sai **sozinha** pela agenda do banco (de 5 em 5 minutos), que confere tudo de
  novo antes; o carrossel e o reel saem **à mão** (baixar as lâminas, copiar a legenda e registrar o link).
- **Aviso quando não sai:** cartão no Painel, quadro "Não saíram" na Pauta e um aviso por e-mail ("Radar: publicação agendada não
  saiu"), sem nomes.

Mudam o banco (2 tabelas novas, `radar_pessoas` e `radar_pauta_pecas`; a tabela das publicações nas redes passa a aceitar a peça da
Pauta; a configuração `pauta`), a tela (`index.html` e o arquivo novo `radar-pauta.js`), as funções `radar-redes` (v0.21.0: a peça
da Pauta, no armazenamento privado, e a chamada da agenda) e `radar-ia` (v0.21.0: a ação `peca`) e o robô (v0.21.0: o aviso da
Pauta). Entra o `sql/radar-redes-agenda.sql`, que liga a agenda no Supabase. Detalhes em "Pauta: o calendário das redes e a
publicação agendada" e, para instalar, "Da v0.20.0 para a v0.21.0".

A v0.20.0 completou o **"Gerar com IA" para as redes**, dentro das regras da publicidade contábil:

- **Kit das redes:** o "Gerar com IA" ganha a etapa 3, que monta a partir do texto final a **legenda do Instagram**, a do
  **Facebook**, a **chamada e a linha de apoio da arte** (v0.25.1: saíram do kit) e o **roteiro de um reel** (de 30 a 45 segundos,
  com a fala e o texto na tela de cada cena, para alguém da equipe gravar). Fica no quadro **"Kit das redes"**, no conteúdo, com
  "Copiar legenda" e "Copiar roteiro"; **"Gerar kit das redes com IA"** refaz só o kit. As caixas de legenda das redes (passo da
  trilha, "Publicar em todos" e "Publicar nos canais que faltam") já vêm com o texto do kit. Se o texto mudar depois, o kit fica
  **desatualizado** e as redes voltam à legenda montada pelo Radar até gerar de novo; se só o título mudar (por exemplo, outro título
  sugerido pela IA), o kit continua valendo e a tela pede para conferir a chamada da arte (desde a v0.25.0, a primeira linha das
  legendas). O kit é sugestão: gravá-lo não muda o conteúdo nem derruba autorização, e só vai ao ar o que o administrador autoriza. O
  reel é gravado e postado à mão. Antes de a notícia estar no site, o "Copiar legenda do Facebook" leva o endereço do site da Artecon
  no lugar do `{LINK DO SITE}`.
- **Arte vertical (1080×1350)** para o Instagram e o Facebook (v0.25.0: na notícia, deu lugar à imagem da publicação, a mesma do
  site; continua nas peças da Pauta): chamada grande, linha de apoio, "Matéria completa em
  www.artecon.cnt.br" e a faixa legal com a identificação da empresa; o selo "NORMA ESTADUAL · SC" só nas normas estaduais. A
  chamada, o apoio e o fundo (padrão, ilustração da IA ou imagem de capa) podem ser trocados na hora de publicar. Se a chamada
  ou o apoio não couberem, a arte corta com "…" e a tela avisa embaixo da imagem e na confirmação.
- **Identificação legal:** empresa, CNPJ e CRC ficam em Configurações → "Fecho, assinatura e identificação legal" (campos `cnpj`
  e `crc`, conferidos ao salvar; o CRC sai sempre como "CRC-SC 007129/O-0", com a letra O de originário depois da barra, mesmo
  que tenha sido escrito "SC-007129/0-0"). Quem os acrescenta à arte e às legendas é o Radar, nunca a IA; enquanto faltarem, sai
  só o que existe (o nome da empresa) e a tela avisa. A legenda editada na tela antes de preencher ganha a linha nova ao salvar
  as Configurações, e a legenda sem a linha (apagada à mão) é lembrada na confirmação.
- **Publicidade da profissão contábil:** a tela aponta os termos que a publicidade contábil evita (lista inicial, a confirmar com
  o contador responsável: não há no pacote a norma do CFC com a lista). A forma de oferta, de promessa e de convite
  ("garantimos", "economia garantida", "consulta grátis", "abertura de empresa grátis", "primeiro mês de graça", "ganhe um
  brinde", "blinde seu patrimônio", "pague menos com a Artecon", "troque de contador") **impede** a publicação da legenda e da
  arte, e o recado diz onde está o termo (legenda do Instagram, do Facebook, chamada ou apoio da arte); "grátis", "de graça",
  "pague menos", "blindar o patrimônio", "100%", "o melhor", "definitivo", "brindes", "blindado", "pagar menos imposto" e "troca
  de contador" pedem confirmação (podem ser fato ou assunto da notícia, como "emissor de NFS-e grátis para o MEI", "quem ganha
  até R$ 5 mil pague menos", "isenção de 100%" ou "ICMS na distribuição de brindes"). Outras promessas a tela não reconhece:
  confira sempre o texto. No texto do site é só aviso. Frase do boletim pago (ITC) também não sai, nem na legenda nem na
  chamada e no apoio da arte, e os botões de copiar do quadro "Kit das redes" seguem as mesmas regras (o reel é postado à mão).
- **Ilustração opcional:** o "Gerar com IA" e o "Gerar texto com IA" fazem a **capa padrão** da Artecon, sem custo de imagem. A
  ilustração da IA passa a ser uma ilustração editorial nas cores da marca (não mais foto de banco de imagens) e sai só pelo
  botão "Gerar ilustração com IA".

Mudam o banco (passa a guardar o kit das redes de cada conteúdo, e a assinatura ganha os campos `cnpj` e `crc`, vazios), a tela
e a função `radar-ia` (o kit das redes e o pedido novo da ilustração). A função `radar-redes` e os robôs não mudam (continuam na
v0.19.0).

A v0.19.0 juntou a IA num botão só e acelerou a publicação:

- **"Gerar com IA"** (passo 1 Fonte, quadro do próximo passo e passo 2): sem texto oficial, procura a fonte oficial na internet
  (a busca rápida, de até 1 minuto e meio: se demorar, segue sem ela); com texto oficial, busca o trecho que comprova. Depois
  escreve o rascunho e faz a capa com a ilustração da IA. O aviso mostra a etapa (1 de 3, 2 de 3, 3 de 3) e uma etapa que
  falha não impede as outras.
- **Texto com ou sem fundamentação legal:** sem texto oficial, a IA escreve um **rascunho normal** (não mais o "texto para
  análise"), com o aviso de fonte não oficial no topo dos pontos a conferir. Revisão e aprovação continuam da equipe; para o
  site continua valendo a fundamentação, ou o "Publicar mesmo assim" do administrador (com o motivo).
- **Mínimo de texto igual ao da fonte:** a IA escreve com palavras próprias e só repete a frase da fonte quando é indispensável
  (dispositivo legal, definição legal), entre aspas, com a menção de quem é **só naquele parágrafo**; os outros parágrafos não
  citam a fonte (ela sai no fim da notícia, no campo Fonte). O "Revisar com IA" reescreve o trecho igual com palavras próprias.
  O boletim pago (ITC) continua nunca copiado.
- **Ilustração:** o "Gerar texto com IA" também faz a capa com a ilustração; se a ilustração falha, o recado diz o motivo; se a
  imagem foi criada e a gravação falhou, aparece **"Gravar a ilustração de novo"** (sem nova consulta nem cobrança). A capa ao
  lado do assunto passa a ser a do conteúdo que acabou de ser gerado.
- **Publicar em todos** fica à vista: o quadro já vem aberto no passo Publicar, o próximo passo tem o botão "Publicar em todos
  (site, Instagram e Facebook)" e a aba **Publicações** tem "Publicar em todos" nos aprovados que faltam.
- **Publicar nos canais que faltam:** com a notícia já no site, o quadro "Publicar nos canais que faltam" publica no Instagram e
  no Facebook (cada um ou os dois) na hora, sem um canal esperar o outro. Na aba Publicações, o canal que falta (ou excluído)
  tem o botão "Publicar".
- **Robô do site na hora:** o agendamento do GitHub ("a cada 15 minutos") chegava a rodar só a cada 3 a 7 horas. Agora, ao
  autorizar a publicação no site (ou "Publicar em todos", ou pedir a exclusão), o Radar pede à função `radar-redes` que acione
  o robô na hora: a notícia sai em 1 a 2 minutos. O botão **"Acionar o robô agora"** aparece no que estiver esperando. Precisa do
  segredo `RADAR_GITHUB_TOKEN` no Supabase (passo a passo em "Robô do site na hora", abaixo); sem ele, vale o agendamento, que
  passou para os minutos 7, 22, 37 e 52 de cada hora.

Mudam o `index.html`, as funções `radar-ia` (v0.19.0) e `radar-redes` (v0.19.0), o robô de rascunhos (`radar_rascunhos.py`:
a regra nova de escrita) e o workflow `radar-site-publicar.yml` (horário). O banco não muda (o `radar-setup-v0.19.0.sql` só
registra a versão).

A v0.18.0 mudou a regra do **texto igual ao da fonte**:

- **Pode ficar igual, desde que a fonte esteja citada.** O texto pode usar as frases da norma, do comunicado oficial ou da
  notícia quando isso der precisão, desde que **cada parágrafo** em que o trecho está diga de onde veio ("Segundo a Receita
  Federal, …", "Conforme o Portal Contábil SC, …"; num item de lista, a frase que apresenta a lista) e o campo **Fonte** esteja preenchido
  (ele sai no fim da notícia, com o link). Base: atos oficiais não têm proteção de direito autoral (Lei 9.610/98, art. 8º, IV) e
  notícia pode ser reproduzida com a menção de onde foi publicada (art. 46, I, "a").
  - Na tela, o trecho igual **com** a fonte citada aparece num quadro azul e não impede aprovar; **sem** a fonte citada,
    continua no quadro vermelho, e **Revisar com IA** acrescenta a fonte no parágrafo em vez de reescrever.
  - O Radar reconhece a fonte pelo nome do órgão ou do veículo (ex.: "Receita Federal do Brasil" ou "Receita Federal"),
    pela sigla entre parênteses, pela sigla do nome da fonte ("PGFN", "SEF/SC") e pelo nome da publicação ("Diário Oficial
    da União"). Se o campo Fonte estiver vazio, o quadro pede só que ele seja preenchido.
- **A IA segue a mesma regra** no "Gerar com IA", nos rascunhos do robô e no "Revisar com IA".
- **Boletim pago (ITC):** as frases do boletim de assinatura nunca são reproduzidas, nem citando a ITC (o contrato da
  assinatura não permite republicar). A IA usa só a informação, com palavras próprias, atribuída ao boletim ("segundo o boletim da ITC") ou, quando o texto oficial confirmar, ao órgão que publicou o ato.
- **Campo Fonte:** no conteúdo novo, além do órgão oficial, entra também o portal de notícias de onde veio a informação
  (ex.: "Receita Federal do Brasil, Portal Contábil SC"); o boletim pago não entra. O link que vai com a Fonte também nunca
  leva ao site do boletim pago quando o assunto tem outra captura.

Mudam o banco (`radar-setup-v0.18.0.sql`, hoje `radar-setup-v0.30.0.sql`: só a função `radar_fn_conteudo_fonte`, que preenche o campo Fonte), o `index.html`,
a função `radar-ia` (v0.18.0), o robô de rascunhos (`radar_rascunhos.py`) e o robô do site (`radar_site_publicar.py`: o link
da fonte). A função `radar-redes` não muda.

A v0.17.0 trouxe duas opções em **Publicações**:

- **Publicar em todos de uma vez.** No passo da publicação (tela do assunto), o quadro "Publicar em todos de uma vez" autoriza
  o **site, o Instagram e o Facebook** com um clique, depois de conferir a categoria do site, a imagem quadrada e as duas
  legendas (dá para desmarcar uma das redes). O robô publica no site em até 15 minutos; logo que a notícia entra no site, as
  redes ficam prontas — no Facebook, o link da notícia entra no lugar de `{LINK DO SITE}` — e o próprio robô pede à função
  `radar-redes` que publique (ela confere de novo tudo o que confere quando o administrador publica). Se a publicação no site
  for cancelada ou não sair, ou se o texto mudar, as redes caem junto e é preciso autorizar de novo. Valem as mesmas
  exigências de antes: só o administrador, conteúdo aprovado, fundamentação, nenhuma marca [VERIFICAR] no texto nem nas legendas.
- **Excluir publicação, individual ou em grupo.** Na aba Publicações, cada canal publicado tem o botão **Excluir**; e dá para
  marcar vários conteúdos (primeira coluna) e excluir de uma vez, escolhendo site, Instagram e/ou Facebook.
  - **Instagram e Facebook:** a função `radar-redes` apaga o post na hora, pela Meta. Se a Meta não deixar apagar pelo
    aplicativo, a tela explica e oferece **Já apaguei**, para registrar a exclusão feita direto na rede.
  - **Site:** fica o pedido, e o robô do site (o mesmo do "publicar no site", a cada 15 minutos) entra no painel, acha a notícia
    pelo título na lista do painel e a exclui como o botão "Excluir" do painel faz. Na dúvida, não exclui: título não encontrado
    ou mais de uma notícia com o mesmo título vira erro para conferir à mão. v0.22.0: a notícia que a lista mostra com o título
    cortado ("…") só é excluída se o título inteiro, lido no formulário de edição do painel (o robô só abre, não grava), for o
    pedido; se for outra notícia da mesma série, ela fica, e o pedido para (ou é dado por concluído, se a página pedida já saiu do ar). Depois de excluída, o registro em "Publicações no
    site" sai (a cópia fica no histórico de exclusões e na auditoria) e o conteúdo pode ser publicado de novo, se for o caso.
  - "Excluir só o registro" (em Publicados no site) continua apagando só o registro no Radar, sem mexer no site.
  - Autorização do escritório (09/10/2026): o robô do site, que até aqui só cadastrava notícias, passa a **excluir** também,
    sempre e só com o pedido do administrador gravado no banco.

Mudam o banco (`radar-setup-v0.17.0.sql`, hoje `radar-setup-v0.30.0.sql`: tabela `radar_site_exclusoes`; situações `aguardando_site` e `excluido` nas
publicações; funções `radar_autorizar_todos`, `radar_pedir_exclusao_site`, `radar_cancelar_exclusao_site`,
`radar_site_exclusao_concluir` e `radar_rede_marcar_excluida`), o `index.html`, a função `radar-redes` (v0.17.0: ação `excluir`
e a chamada do robô para as redes que vão junto com o site), o robô do site (`radar_site_publicar.py` e o novo
`radar_site_excluir.py`) e o workflow "Radar — publicar no site". A função `radar-ia` não muda.

A v0.16.0 cuida do **texto da IA**, da **capa** e da **triagem**:

- **Sem marca nem comentário de dúvida no texto.** A IA não escreve mais "[VERIFICAR: a fonte indica 30/9, mas não especifica
  o ano]" nem "a fonte cita tanto ADI 5.161 quanto ADI nº 5.161/DF". O que não está confirmado sai do texto (ou é escrito sem o
  detalhe incerto) e vai para os pontos a conferir, na linha "Ficou fora do texto por falta de confirmação". Diferença só de
  grafia entre fontes não é dúvida: a IA usa a forma mais completa. Comentário de dúvida escrito sem colchetes ("a fonte não
  especifica o ano") também é apanhado. No "Gerar texto para análise" (e no "Preparar tudo") de assunto sem fonte oficial, a IA
  primeiro procura a fonte oficial na internet (uma vez por assunto) e usa o que ela confirmar; no texto para análise o dado da
  fonte não oficial fica no texto, atribuído a ela, e vai para os pontos a conferir.
- **Sem cópia.** A IA diz de onde veio a informação ("segundo a Receita Federal…"). Se o texto gerado ainda tiver marca
  [VERIFICAR] ou trecho igual ao da fonte (o mesmo detector da tela: 12 palavras seguidas), uma segunda passada da IA corrige
  só isso antes de gravar (no botão "Gerar com IA" e também nos rascunhos automáticos do robô); se ela falhar, o texto fica como
  veio e os pontos a conferir avisam. Na revisão, só o texto oficial (ou a verificação em fontes oficiais) confirma uma
  informação. No conteúdo, o quadro "Texto igual ao da fonte" traz **Revisar com IA** (reescreve só esses trechos, citando a
  fonte, e também resolve as marcas; o que ela afirmar é conferido de novo contra o texto oficial) e **Autorizar mesmo assim**
  (editor ou administrador, com o motivo; vale para o texto atual e cai se o texto mudar; a revisão não mexe no trecho
  autorizado; nunca para frase do boletim pago). Se a revisão mudar o título, a capa com a ilustração é refeita sozinha. Os pontos a conferir agora só crescem:
  a revisão acrescenta o que tirou do texto, ninguém apaga o que a IA apontou.
- **Capa com imagem.** A capa feita pela IA é a ilustração ao fundo com o logotipo da Artecon, a categoria e o título por cima
  (antes ficava só a foto). A ilustração fica guardada: depois de trocar o título, **Atualizar a capa** refaz a capa sem gerar
  outra imagem; **Capa padrão, sem a ilustração** volta ao fundo marinho.
- **Triagem.** A IA não junta mais como "mesmo fato" notícias que citam tributos diferentes (por exemplo, uma sobre o crédito
  presumido de ICMS na base do PIS/Cofins posta atrás de outra sobre a base do IRPJ/CSLL), nem pelo caminho até a origem nem com o
  que já está no grupo dela. O cartão da captura mostra os títulos das
  repetições, cada uma com **Não é o mesmo fato**, que a devolve à lista; a decisão fica, mesmo que a fonte mude o texto e a IA
  avalie de novo.
- **Fontes.** Fonte RSS cadastrada com o endereço da página do site (e não do feed) passa a funcionar: o robô segue o feed que
  a página anuncia (a página de uma categoria fica com o feed da categoria); se ela não anunciar, o erro diz o que cadastrar
  (antes: "ParseError: undefined entity"). Feed com entidades do HTML (&nbsp;) também é lido. A fonte nova começa como
  **não oficial**.

Mudam o banco (`radar-setup-v0.16.0.sql`, hoje `radar-setup-v0.30.0.sql`: colunas `ilustracao_id` e `copia_autorizada_*` em `radar_conteudos`, funções
`radar_autorizar_copia` e `radar_separar_repeticao`), o `index.html`, a função `radar-ia` (v0.16.0: ação nova `revisar` e a
segunda passada no `gerar`), o robô (triagem, rascunhos e coletor RSS).

A v0.15.0 mostra na aba **Capturas** se cada notícia tem **fundamentação legal**:

- **"com fundamentação legal"** (selo verde) e a linha *Fundamentação legal:* com as normas citadas no texto capturado: lei,
  lei complementar, decreto, decreto-lei, medida provisória, emenda constitucional, instrução normativa, resolução, portaria,
  solução de consulta ou de divergência, resposta à consulta tributária, ato declaratório, ato conjunto e ato técnico conjunto (RFB/CGIBS), parecer normativo,
  convênio ICMS, ajuste SINIEF, protocolo ICMS, ato COTEPE, ato DIAT, edital de transação (o "Edital" sozinho, só o da PGFN,
  PGDAU, PGF, AGU ou RFB — edital de concurso ou de licitação não conta) e súmula (também pelas siglas LC, MP, IN, EC e DL, no
  singular e no plural, e pelas abreviaturas Res., Dec., Dec.-Lei e Port.), e os códigos citados pelo nome (Constituição Federal,
  ADCT, CTN, RIR, RICMS, Código Civil e CLT; o código que já aparece pela lei que o criou, como a Lei nº 5.172/1966 do CTN, não se
  repete). O órgão por extenso e a sigla são o mesmo ("Comitê Gestor do Simples Nacional" = CGSN). Do texto, são lidos os
  primeiros 100 mil caracteres. A mesma norma escrita de jeitos diferentes ("LC 214/2025" e "Lei Complementar
  nº 214, de 16 de janeiro de 2025") aparece uma vez só; o mesmo número em anos diferentes (Resolução CGIBS nº 1/2025 e
  Resolução CGIBS nº 1/2026) são duas. Mostra até 12 e diz quantas faltam; a Constituição e os códigos não ficam escondidos.
- Quando a captura **é o próprio ato** (o título é a norma, sozinha ou seguida de " - ementa", como "Solução de Consulta
  Cosit nº 190, de 30/09/2026"), a linha diz "é o próprio ato" e o que ele cita. "Lei nº 15.270/2025: o que muda" é notícia
  sobre a lei, não a lei.
- **"sem fundamentação legal"** (selo amarelo): o texto capturado não cita norma nenhuma. Confira na fonte antes de usar.
  Se outra captura do mesmo fato, ainda na fila, cita norma, o cartão mostra a dela.
- **"fundamentação legal não identificada"** (selo amarelo): o texto capturado está cortado (termina em "...", "…" ou
  "Leia mais", ou é a parte inicial de uma matéria, como a do boletim da ITC) e não cita norma; ela pode estar no restante.
  Confira na fonte antes de usar.
- É uma **leitura do texto**, feita pelo banco, sem custo de IA: diz o que está citado, não se a citação está certa nem se a
  norma está em vigor. Ficam de fora a jurisprudência (Tema, RE, ADI), os projetos de lei, as propostas de emenda e as
  minutas. Não muda a nota nem a relevância.

Muda só o banco (`radar-setup-v0.15.0.sql`, hoje `radar-setup-v0.30.0.sql`: coluna `base_legal` em `radar_capturas`, calculada por gatilho na entrada e
quando o título, o resumo ou o texto mudam; função `radar_base_legal`; coluna nova nas visões `radar_v_fila` e
`radar_v_em_alta`; as capturas que já estavam no banco são lidas na instalação) e o `index.html`. Robô e funções não mudam.

A v0.14.3 impede que um ponto marcado com **[VERIFICAR]** chegue ao leitor: enquanto o título, o texto ou a legenda
tiver alguma marca, o banco não deixa aprovar nem autorizar a publicação no site, no Instagram ou no Facebook, e a mensagem
de erro lista cada marca (`RADAR139`). A tela mostra as marcas num quadro vermelho no conteúdo. Junto vêm a v0.14.1 (o
`META_PAGE_TOKEN` aceita o token do usuário do sistema da Meta) e a v0.14.2 (as funções `radar-redes` e `radar-itc` usam a
chave interna nova do Supabase, `sb_secret_…`, só no cabeçalho `apikey`). Muda o banco (`radar-setup-v0.14.3.sql`, hoje `radar-setup-v0.30.0.sql`: função
`radar_marcas_verificar` e as conferências na aprovação e nas autorizações) e o `index.html`.

A v0.14.0 confere a informação em **fontes oficiais na internet** e melhora os textos da IA:

- **"Verificar em fontes oficiais"** (passo 1 do assunto, e na trilha): a IA procura o assunto na internet, **só em sites de órgão
  público** (gov.br, jus.br, leg.br, mp.br), e mostra se a informação foi **confirmada**, **confirmada em parte**, **não encontrada**
  ou **diverge**, com o link de cada página oficial e o que ela confirma. Só ficam as páginas que apareceram de fato na busca.
  Cada verificação faz até 4 buscas (custo da busca da Anthropic, além dos tokens).
- **"Incluir como texto oficial"**: traz o texto da página oficial para o formulário "Incluir texto oficial", com endereço, título,
  data e a fonte já escolhidos. A equipe confere e grava; daí segue o caminho normal (trecho que comprova e confirmação).
- **Textos sem aviso de origem**: o texto gerado não traz mais frases como "este informativo é baseado em material de fonte não
  oficial" (o aviso continua interno, nos pontos a conferir). "Transformar em texto para publicar" também tira essas linhas.
- **Análise Artecon mais útil**: quem é afetado e como, o que conferir ou providenciar e até quando, o risco de não agir e quando
  procurar a Artecon. Ao gerar, a IA usa a verificação: o que a fonte oficial confirmou deixa de ser marcado com [VERIFICAR].

Mudam o banco (`radar-setup-v0.14.0.sql`, hoje `radar-setup-v0.30.0.sql`: colunas `verificacao` e `verificado_em` no assunto), o `index.html`, o robô de rascunhos
(a nova Análise Artecon) e a função `radar-ia` (v0.14.0: ações `verificar` e `pagina`). Configuração: nenhuma nova — a busca passa
pela mesma IA Central.

A v0.13.0 leva as notícias ao **Instagram e ao Facebook** da Artecon, sempre com a autorização do administrador:

- **Passos 6 e 7 da trilha de autorização.** Depois que a notícia está no site, a trilha mostra a **imagem quadrada** (1080×1080,
  montada a partir da capa, com "Artecon Informa", a categoria e o endereço do site) e a **legenda** (título, começo do texto,
  fonte e o caminho até o site; no Instagram, as hashtags). O administrador confere, ajusta a legenda e clica em
  **"Autorizar e publicar"**: a publicação sai na hora pela API da Meta e o link do post fica registrado. Também há
  **"Não publicar"** neste canal (pode ser desfeito).
- **Nunca publica duas vezes**; se a Meta recusar, a mensagem aparece com **"Tentar de novo"**; se o texto mudar depois de
  autorizado, a autorização cai sozinha.
- **Publicações › Canais** mostra o Instagram e o Facebook de cada conteúdo e tem **"Testar conexão com o Instagram e o Facebook"**.

Mudam o banco (`radar-setup-v0.13.0.sql`, hoje `radar-setup-v0.30.0.sql`: tabela `radar_redes_envios` e as funções de autorização), o `index.html` e entra a
função nova `radar-redes`. Configuração: "Instagram e Facebook pela API da Meta".

A v0.12.0 traz o **boletim da ITC para dentro do aplicativo** e publica o texto **justificado**:

- **Boletim da ITC pela função `radar-itc`**: lê no Outlook (Microsoft Graph) os e-mails de itc@itcnet.com.br 1 vez por dia, às 02h55,
  a IA separa as matérias e elas entram na triagem como antes. Não depende mais de uma conversa do Claude aberta. Só leitura:
  o e-mail não é marcado como lido, movido nem respondido; nada do boletim vai para o GitHub (que é público) nem para os logs.
- Na aba **Fontes**, o administrador tem **"Ler boletim agora"** (últimos 3 dias) e **"Testar conexão com o e-mail"**.
- **Texto justificado** na notícia que o robô cadastra no site (a prévia e o "Copiar texto" já eram); os créditos continuam à direita.
- **"Ainda não pode ser publicado no site"** agora traz os botões para resolver ("Marcar como confirmado oficialmente", "Buscar o
  trecho que comprova") e, para o administrador, **"Publicar mesmo assim"**: pede o motivo, que fica registrado no histórico do
  assunto, e pode ser desfeito. O texto para análise continua sem ir ao site.
- **Ilustração:** "Gerar texto para análise" também cria a ilustração com IA; "Preparar tudo" num assunto sem fonte oficial prepara
  o texto para análise com a ilustração; se a ilustração falhar, a próxima tentativa pelo botão dela não pede senha.

Mudam o banco (`radar-setup-v0.12.0.sql`: tabela `radar_itc_lidos` e as funções do boletim), o `index.html`, o robô de
publicação e entra a função nova `radar-itc`. A função `radar-ia` não muda. Configuração: "Boletim da ITC pelo Microsoft Graph".

A v0.11.1 corrige o que a varredura de erros encontrou:

- **IA presa ao assunto pedido**: se você trocar de tela enquanto ela trabalha, o resultado não é aplicado no outro assunto (o aviso diz onde ficou).
- **Clique durante ação longa avisa** para aguardar, em vez de não fazer nada.
- **A notícia oficial nunca fica escondida atrás do boletim da ITC** (ou de outra fonte não oficial): o boletim é que vira a repetição dela. As que já estavam assim foram arrumadas ao aplicar o SQL (menos as que já viraram assunto).
- **Consumo de IA do mês** contado no mês de Brasília (antes virava o mês às 21h do último dia).
- **Coleta com prazo total** (13 minutos; variável `RADAR_PRAZO_MINUTOS`): a fonte que não couber aparece como "sem tempo" no resumo e entra na próxima rodada, sem contar falha; a nota da IA e os rascunhos também respeitam o prazo.
- **Robôs do GitHub com permissão mínima** (só leitura onde não precisam de mais; o token não fica gravado na cópia do repositório).

Mudam o banco (`radar-setup-v0.11.1.sql`, hoje `radar-setup-v0.30.0.sql`), o `index.html`, os robôs, os workflows e a função `radar-ia` (v0.11.1: "Classificar" não chama mais o boletim de "texto oficial").

A v0.11.0 ajusta a IA e a publicação a partir do uso:

- **Aviso enquanto a IA trabalha** (no alto da tela, com o que ela está fazendo e há quantos segundos).
- **Senha a partir da 2ª consulta** à IA no mesmo assunto (a 1ª é livre; "Preparar tudo" conta como uma só).
- **"Preparar tudo com IA" cria a ilustração** da capa com IA (se falhar, fica a capa padrão).
- **"Gerar texto para análise"** em assunto que só tem fonte não oficial (ITC, Econet, Portal Contábil): texto marcado, que não vai ao site.
- **Fonte com link** no fim do texto (prévia, "Copiar texto" e publicação no site).
- **Publicações por canal**: Site (publicado / aguardando o robô / falta) e as colunas Instagram e Facebook (em breve).
- **Notícia com mais de 5 dias vira baixa relevância** (`dias_baixa` em Configurações → Relevância; 0 desliga).

Mudam o banco (`radar-setup-v0.11.0.sql`, hoje `radar-setup-v0.30.0.sql`), o `index.html`, o robô de publicação e a função `radar-ia` (v0.11.0).

A v0.10.0 refaz só a **tela do assunto** (o resto do Radar não muda) e liga a **publicação no site com autorização**:

- **4 passos**: 1. Conferir a fonte (título original da captura, órgão, data e "Abrir na fonte") →
  2. Escrever → 3. Revisar e aprovar → 4. Publicar no site, com o **próximo passo** em destaque.
- **Quadro ao lado**: base do texto (texto oficial, trechos que comprovam, confirmação), capa e "Mais detalhes".
- **Opções de título** sugeridas pela IA (clique para usar; "↻ Sugerir outros" pede mais) e
  **Tamanho do texto** Curto (aviso rápido), Médio (notícia) ou Longo (artigo). A IA escreve de forma mais natural.
- **Ver como fica no site**: a notícia como vai aparecer em artecon.cnt.br/news, com o que está na tela.
- **Autorizar publicação no site** (só o administrador): o robô cadastra a notícia no site em até 15 minutos
  e registra o link sozinho. Dá para cancelar enquanto o robô não começou; se o texto mudar, a autorização cai.

Mudam o banco (`radar-setup-v0.10.0.sql`, hoje `radar-setup-v0.30.0.sql`), o robô, o `index.html` e a função `radar-ia` (v0.10.0).
Workflow novo: `radar-site-publicar.yml` (a cada 15 minutos; sem autorização pendente, termina em segundos).

A v0.9.0 deixa a fila mais limpa e começa a automação dos textos:

- **Rascunhos automáticos**: o robô prepara sozinho o rascunho das notícias de topo (fonte oficial,
  relevância alta, nota da IA 9+, no máximo 2 por dia). A equipe confere, gera a capa e envia para revisão.
- **Nota da IA rebaixa**: "alta" pelas palavras da lista, mas com nota da IA até 3, desce para "média".
- **A fila não acumula**: o que ficou mais de 10 dias na triagem sem importância sai sozinho (vai para Ignorado).
- **DOU Destaques filtrado**: só atos fiscais e leis, decretos e MPs.
- **Aviso de fonte parada** (vigia da rotina da ITC) e **fontes sem novidade** no resumo de segunda.

Mudam o banco (`radar-setup-v0.9.0.sql`, hoje `radar-setup-v0.30.0.sql`), o robô e o `index.html`. A função `radar-ia` **não muda**.

A v0.8.0 tira trabalho manual e aumenta o alcance, sem enxurrada de avisos:

- **Publicação no site registrada sozinha** (o robô acha a notícia em artecon.cnt.br/news) e aviso quando
  o texto do site deixa de bater com o aprovado.
- **Para o site** com passos numerados e a categoria do site indicada.
- **Resumo semanal**: um único e-mail por semana com o mais relevante, agrupado por tema.
- **Diário Oficial completo pelo INLABS** (Receita, PGFN, CGSN e CGIBS), desligado até o cadastro.
- **Nota da IA na relevância** e fontes novas (DOU Destaques, Econet, Portal Contábil SC, boletim da ITC).
- **Limpeza** da antiga publicação dentro do Radar.

Mudam o banco (`radar-setup-v0.8.0.sql`, hoje `radar-setup-v0.30.0.sql`), o robô e o `index.html`. A função `radar-ia` **não muda**.

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

Mudam o banco (`radar-setup-v0.7.1.sql`, hoje `radar-setup-v0.30.0.sql`), o robô e o `index.html`. A função `radar-ia` **não muda**.

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
| `radar-pauta.js` | A aba Pauta (v0.21.0), carregada pelo `index.html`. Vai sempre junto com ele: com os dois de versões diferentes, a aba pede Ctrl+F5. |
| `radar-video.js` | O corretor de vídeo do reel (v0.22.0), carregado pelo `index.html` depois do `radar-pauta.js`. Vai sempre junto com os dois. |
| `informativo.html` | Informativo Mensal para imprimir / salvar em PDF (uso interno, usa o login do dashboard). |
| `radar-logo-artecon.png` | Logotipo usado no topo do painel e na tela de entrada (recortado do timbrado). |
| `radar-timbrado-topo.png`, `radar-timbrado-rodape.png` | Papel timbrado do informativo (recortado do seu PDF). Para trocar, substitua os arquivos mantendo os nomes. |
| `radar-config.js` | Endereço do projeto Supabase e chave **anon**. Preenchido uma vez; não é substituído nas atualizações. |
| `sql/radar-setup-v0.30.0.sql` | Cria (ou atualiza) as tabelas `radar_*`, as regras e as 6 fontes iniciais. Pode ser executado mais de uma vez. |
| `sql/radar-reversao-v0.30.0.sql` | Desfaz a instalação (apaga só objetos `radar_*`; tira também as agendas da Pauta (com a dos lembretes) e do corretor de vídeo do pg_cron; os arquivos do armazenamento `radar-videos` saem pelo painel). |
| `supabase/functions/radar-ia/index.ts` | Função de IA (Edge Function do Supabase). |
| `supabase/functions/radar-itc/index.ts` | Função que lê o boletim da ITC no e-mail (v0.12.0; desde a v0.23.0, na caixa inteira, menos o Lixo Eletrônico e os Itens Excluídos). |
| `supabase/functions/radar-redes/index.ts` | Função que publica no Instagram e no Facebook (v0.13.0; a peça da Pauta e a chamada da agenda desde a v0.21.0; desde a v0.29.0, também aciona, a pedido da agenda do banco, o robô dos lembretes por e-mail). |
| `supabase/functions/radar-video/index.ts` | Função do corretor de vídeo (v0.22.0): o envio dos clipes, a prévia, o baixar, a conversa com o robô e a agenda. É a única que toca no armazenamento privado `radar-videos`. |
| `sql/radar-itc-agenda.sql` | Agenda (1 vez por dia, às 02h55) da leitura do boletim da ITC; roda uma vez no Supabase (desde a v0.23.0, pode rodar de novo, como as outras agendas). |
| `sql/radar-redes-agenda.sql`, `sql/radar-redes-agenda-reversao.sql` | Agenda (de 5 em 5 minutos) que publica a Pauta aprovada na hora marcada (v0.21.0; roda uma vez no Supabase, depois do setup) e como desfazer. Desde a v0.29.0, também pede (de 15 em 15 minutos, só quando há o que lembrar) o robô dos lembretes por e-mail. |
| `sql/radar-video-agenda.sql`, `sql/radar-video-agenda-reversao.sql` | As chaves do corretor de vídeo no Vault (a do robô e a da agenda), a reserva da fila (de 10 em 10 minutos, só com vídeo esperando, até 3 vezes por pedido: depois, erro "robo_nao_pegou" na peça) e a limpeza diária dos prazos de guarda (v0.22.0; roda uma vez no Supabase, depois do setup) e como desfazer. |
| `supabase/functions/radar-concorrentes/index.ts` | Opcional (v0.19.1): lê, só para análise, os dados públicos de perfis comerciais de outros escritórios no Instagram. |
| `sql/radar-concorrentes.sql`, `sql/radar-concorrentes-reversao.sql` | Opcional (v0.19.1): chave da função `radar-concorrentes` no Vault (roda uma vez) e como desfazer. |
| `robo/` | Robô de coleta, diagnóstico das fontes e a lista de fontes. Desde a v0.29.0, também o robô dos lembretes por e-mail (`robo/radar_lembretes.py`); desde a v0.30.0, o robô dos avisos (`robo/radar_alertas.py`) avisa também a possível prorrogação de prazo na agenda de obrigações. |
| `robo/video/` | O robô do corretor de vídeo (v0.22.0): o código, o `Dockerfile` do ffmpeg isolado, as fontes DM Sans da legenda e da cartela (licença OFL) e o **modelo** do workflow do repositório privado (`workflow/radar-video.yml`). Roda no repositório privado `radar-video`, nunca neste. |
| `.github/workflows/` | Rotinas do GitHub Actions: coleta agendada, resumo de segunda, publicação no site, teste do login do site, diagnóstico das fontes, testes e, desde a v0.29.0, os lembretes por e-mail (`radar-lembretes.yml`, "Radar — lembretes por e-mail"). |
| `testes/` | Suíte de testes automatizados. O `testes/amostras/pauta-ficticia.csv` é um calendário de mentira, só com nomes inventados; os vídeos e as falas dos testes do corretor são sintéticos, gerados na hora (nenhuma gravação real). |
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

O Diário Oficial da União entrou depois por dois caminhos: os Destaques do DOU (v0.9.0) e o INLABS,
com os XML oficiais (v0.8.0; exige cadastro gratuito; veja "Diário Oficial pelo INLABS").

## Instalação — nesta ordem

### Passo 1 — Repositório e diagnóstico das fontes (não precisa de banco nem de chave)

1. Crie o repositório `radar` no GitHub e envie o conteúdo deste zip.
   A pasta `.github` precisa ir junto. Se ela não aparecer no envio por arrastar,
   crie cada arquivo de `.github/workflows/` por "Add file → Create new file", digitando o caminho
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
3. SQL Editor → cole e execute `sql/radar-setup-v0.30.0.sql` inteiro.
4. O resultado final é a **evidência**: exporte em CSV e guarde.
   Esperado: 28 linhas de tabela, todas com `rls = true`; `fontes = 6`; `categorias = 8`;
   `instalacoes concluidas` com ao menos 1 e a versão do script (hoje `v0.30.0`).
   Se o script parar com erro, corrija a causa e execute de novo: ele continua de onde parou.

### Passo 3 — Chaves do robô no GitHub

Repositório → Settings → Secrets and variables → Actions → New repository secret:

| Nome | Valor |
|---|---|
| `RADAR_SUPABASE_URL` | URL do projeto (`https://xxxx.supabase.co`) |
| `RADAR_SUPABASE_SERVICE_KEY` | chave **service_role** (secreta; só aqui) |

Opcionais, cada um liga um recurso (sem eles, o resto funciona):

| Nome | Para quê |
|---|---|
| `RADAR_IA_GATEWAY_TOKEN` | nota da IA nas capturas e rascunhos automáticos (Passo 7) |
| `INLABS_EMAIL`, `INLABS_SENHA` | Diário Oficial pelo INLABS |
| `ARTECON_SITE_USUARIO`, `ARTECON_SITE_SENHA` | publicação no site com autorização (v0.10.0) |

Na aba **Variables** (não secretas, opcionais): `RADAR_IA_MODELO`, `RADAR_IA_MODELO_RAPIDO`, `IA_GATEWAY_URL` e
`RADAR_PRAZO_MINUTOS` (prazo da coleta, até 14).

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
6. (Opcional, v0.24.0) Em **Configurações → Inteligência artificial → Orientações para a IA**, escreva como o escritório quer o
   texto e as imagens e salve (veja "Diretrizes editoriais e como ensinar a IA").

Segredos opcionais (no projeto do Radar):

| Segredo | Padrão | Para quê |
|---|---|---|
| `RADAR_IA_MODELO` | `claude-sonnet-4-6` | modelo que busca trechos e redige |
| `RADAR_IA_MODELO_RAPIDO` | `claude-haiku-4-5` | modelo que classifica |
| `RADAR_IA_MODELO_IMAGEM` | `gpt-image-2` | modelo da imagem da publicação (OpenAI). v0.25.0: sempre em qualidade alta (`quality: "high"`, 1536×1024), que custa mais por imagem que a média de antes |
| `RADAR_IA_LIMITE_MENSAL_TOKENS` | `3000000` | teto de consumo por mês dentro do Radar, além dos limites em dólar da IA Central |
| `IA_GATEWAY_URL` | endereço do `ia-gateway` do projeto do DP | só muda se a IA Central mudar de projeto |

Os modelos são os que a IA Central já tem com preço cadastrado e que os outros aplicativos usam.
Para usar outro modelo, cadastre o preço em `core.ia_precos` e libere em `core.ia_apps.modelos`
do aplicativo `radar` antes de trocar o segredo; senão a IA Central recusa a chamada.

Custo da imagem (v0.25.0): a imagem da IA sai em **qualidade alta**, que custa mais por imagem do que a qualidade média usada até a
v0.24.0; o valor de cada uma fica no Portal → Consumo de IA (na conta da OpenAI). A qualidade não é configurável por segredo: se a IA
Central recusar a qualidade alta, a função **não troca de qualidade sozinha** e o recado diz para liberar a qualidade alta do modelo de
imagem do Radar no Portal. A imagem só é gerada quando alguém clica em "Gerar imagem com IA" (o "Gerar com IA" faz a capa padrão, sem
custo de imagem).

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
6. **Pauta** (v0.21.0): as publicações próprias das redes (equipe, orientação, agenda da semana, captação), uma por dia, com
   aprovação do administrador e publicação na hora marcada. Veja "Pauta: o calendário das redes e a publicação agendada".

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
precisam ser cadastrados em Configurações. As regras reproduzem os informativos 8, 9 e 10/2026.

Desde a v0.30.0, a agenda também tem as **obrigações anuais**: a obrigação com `"mes"` (de 1 a 12) só entra
na agenda desse mês. A agenda padrão traz o **13º salário** (1ª parcela até 30/11 e 2ª até 20/12, Lei
4.749/1965, arts. 2º e 1º; a lei não trata do fim de semana nem do feriado: por segurança, a agenda
antecipa para o dia útil anterior, como em 20/12/2026, domingo, que fica 18/12; é uma escolha do
escritório, não da lei), a **DEFIS** (31/03) e a **DASN-SIMEI** (31/05), que não mudam no fim de semana
(Resolução CGSN 140/2018, art. 72, § 1º, e art. 109), a **ECD** (último dia útil de junho, IN RFB
2.003/2021, art. 5º) e a **ECF** (último dia útil de julho, IN RFB 2.004/2021, art. 3º), cada uma com a
fonte oficial. Na
instalação que já existia, o administrador acrescenta essas seis em Configurações → Agenda de obrigações →
**"Acrescentar o 13º e as obrigações anuais"** (o SQL não mexe na lista do escritório).

**Prorrogação oficial de prazo.** Quando o Radar capta uma notícia (dos últimos 30 dias) que fala em
prorrogar ou adiar o prazo de uma obrigação da agenda, o **Painel** mostra "Possível prorrogação de
prazo", a edição do Informativo que tem essa obrigação mostra um aviso e o administrador recebe **um**
e-mail (aviso no GitHub; cada notícia nova ganha um comentário). O Radar **nunca muda a data sozinho**:
o administrador confere na fonte oficial e, se o prazo mudou, põe a nova data na obrigação, em
`"prorrogacoes"` (por exemplo `[{"de": "2027-03", "para": "2027-04-30", "fonte": "norma, artigo —
endereço"}]`: vale só para aquele vencimento e para as próximas edições; a edição já criada se ajusta à
mão ou com "Recalcular pelo mês escolhido"). Depois clica em **"Conferido"** (no Painel), e a notícia sai
do Painel e do aviso. Fechar o aviso pelo GitHub não tira a notícia do Painel, mas o robô também não avisa
de novo a mesma notícia. Para a regra achar a obrigação por outro nome nas notícias, use `"termos"` (ex.:
`["DASN"]`, com pelo menos 3 letras ou números). A regra pede as três coisas: uma palavra de prorrogação
(prorroga, adia, posterga, novo prazo, nova data; "adiantamento", "prorrogável" e "pode ser prorrogado" não
contam), uma palavra de prazo (prazo, vencimento, entrega, pagamento, recolhimento, apresentação,
transmissão, data limite; "prazo de vigência", "prazo de validade" e "folha de pagamento" não contam) e o
nome da obrigação, a sigla do começo do nome (como FGTS, ECD, DEFIS; a de órgão, como INSS, não) ou um dos
termos. Pode avisar o que não é prorrogação (ECF também é "Emissor de Cupom Fiscal"; "Simples Nacional"
aparece na prorrogação da opção): por isso quem decide é o administrador.

No quadro do Fale Conosco vieram só os setores, os e-mails e o telefone geral. Os nomes
da equipe e os demais telefones você preenche em Configurações (ficam no banco, não no
repositório). A assinatura digital continua sendo aplicada por você no PDF.

Perfis: **leitor** só consulta; **editor** cria assuntos, escreve, aprova e registra o que
foi ao site; **administrador** também configura fontes, usuários e vê o histórico. Na Pauta, o editor prepara as peças e
o administrador cadastra as pessoas e aprova o que vai ao ar.

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

### Texto igual ao da fonte, com a fonte citada (v0.18.0 e v0.24.0; comparação com a fonte desde a v0.7.0)

O Radar compara cada conteúdo (escrito pela equipe ou pela IA) com o texto das capturas do assunto: sequência de 12 palavras
ou mais igual à fonte é um **trecho igual ao da fonte**. A comparação ignora maiúsculas, acentos e pontuação. Não contam para
as 12 palavras: números, datas, nomes próprios e siglas, o nome de uma norma ("Instrução Normativa RFB nº 2.300, de 5 de março
de 2026") e as palavras de ligação entre eles ("de", "e", "na"). Citação curta entre aspas não conta (até 40 palavras cada e
120 no total do texto). A mais longa entre aspas é comparada (v0.24.0): com a fonte citada no parágrafo, é a transcrição literal que a
Diretriz 3 aceita e fica num quadro azul ("Transcrição literal entre aspas…"; deixe só o indispensável); sem a fonte citada, é como o
trecho sem a fonte. O título do conteúdo não entra na comparação.

- **Com a fonte citada, mas fora de aspas** (quando **cada parágrafo** em que o trecho está diz de onde veio, pelo nome da fonte:
  "Segundo a Receita Federal, …", "Conforme o Portal Contábil SC, …", "Conforme publicado no Diário Oficial da União, …"; num item
  de lista, vale a frase que apresenta a lista; **e** o campo **Fonte** está preenchido): da v0.18.0 à v0.23.0 podia ficar, num
  quadro azul. Desde a v0.24.0 (Diretriz 3: citar a fonte não autoriza copiar), o quadro é amarelo e a Conferência das Diretrizes
  marca os critérios 4 e 5 com ✗, o que trava o Aprovar: reescreva com palavras próprias (o **Revisar com IA** faz isso), deixe
  entre aspas só a frase indispensável (a citação curta entre aspas não conta) ou use **Autorizar mesmo assim**, com o motivo. O
  Radar reconhece a fonte pelo nome do órgão (também sem "do Brasil"), pela sigla entre parênteses e pelo começo do nome da fonte
  quando é uma sigla ("PGFN", "SEF/SC") ou o nome da publicação ("Diário Oficial da União").
- **Não pode ficar** (quadro vermelho; o Aprovar recusa): o trecho sem a fonte citada no parágrafo, ou com o campo Fonte
  vazio, e qualquer trecho com frases do **boletim pago** (ITC), mesmo citando a ITC. O botão **Revisar com IA** reescreve o
  trecho com palavras próprias (só a frase indispensável fica, entre aspas, com a fonte no parágrafo) e o do boletim pago;
  **Autorizar mesmo assim** deixa como está, com o motivo registrado,
  só o trecho igual ao de fonte livre. A frase do boletim pago **não se autoriza** (v0.22.0): com ela, o botão não aparece, e o
  banco também recusa (RADAR146) a autorização, a aprovação e a publicação no site, no Instagram e no Facebook (texto e legenda),
  comparando com todas as capturas do boletim guardadas, em janelas de 12 palavras, menos o que também está numa captura livre
  do assunto (o artigo de lei que o boletim copiou do DOU). Rodada 2: a frase de uma matéria do boletim que **não está no
  assunto** (de outro assunto ou ainda na fila) também aparece no quadro vermelho, marcada "conferido pelo banco com todas as matérias
  do boletim": o banco diz só onde ela está no próprio texto (nada do boletim sai do banco), e o Revisar com IA a reescreve. A matéria
  do boletim que é o **próprio ato oficial** (título "Lei nº … (DOU DE …)", texto = a ementa, de domínio público) não conta como
  frase do boletim, na notícia e na Pauta.

A IA (Gerar com IA, rascunhos do robô e Revisar com IA) segue a mesma regra. Limites: a comparação é só com o texto
capturado do próprio assunto (não com a internet nem com outros sites de notícia), não detecta paráfrase muito próxima e é
feita na tela: quem grava direto no banco não passa por ela (só pela trava do boletim pago, que está no banco). É um apoio à revisão, não um detector de plágio. O campo
**Fonte** é preenchido só na criação do conteúdo (com os órgãos das capturas oficiais do assunto e, depois deles, os portais
de notícia; o boletim pago não entra); capturas incluídas depois não o alteram.

### Assunto em 3 passos (v0.26.0; por etapas desde a v0.7.0)

Até a v0.25.1 eram 7 passos (Fonte, Texto, Revisão, Aprovar, Site, Instagram e Facebook; antes deles, os 4 da v0.10.0). Desde a
v0.26.0 são 3, sempre para a frente, e a tela mostra um de cada vez: **1. Preparar** (título original, órgão, data, texto oficial e
trechos que comprovam; "Preparar com IA", com o tamanho do texto ao lado, "Verificar em fontes oficiais", "Buscar trecho que comprova
com IA" e "Classificar com IA"), **2. Conferir e aprovar** (os textos do assunto, com as opções de título, "Texto elaborado por", a
fonte já preenchida com o órgão, a imagem, "Ver como fica no site", a Conferência das Diretrizes e o Aprovar; na barra, "Gerar texto
com IA" e "Novo conteúdo (sem IA)" para outro texto) e **3. Publicar** (prévia, categoria do site, "Publicar em todos" e as redes). Os
dados do assunto (categoria, relevância, situação, público, etapa) ficam ao lado, em "Mais detalhes". Abre no passo que falta (com o
texto aprovado e a fonte pendente, no 3); os passos do alto e os botões da trilha trocam de passo.
Trocar de etapa não perde o que foi digitado, e uma ação feita em outra etapa (salvar a
classificação, por exemplo) também não: o que estava digitado ou escolhido e não salvo é devolvido
aos campos. Se houver um formulário de evidência ou de texto oficial aberto e preenchido em outra
etapa, a ação é barrada com o aviso de onde está a pendência.
Os passos do alto funcionam também pelo teclado. "Mostrar tudo numa página" volta ao formato
anterior e a escolha fica guardada no navegador.

**Trilha (v0.12.2; v0.26.0: os 3 passos).** No alto do assunto ficam os passos numerados — 1 Preparar, 2 Conferir e
aprovar, 3 Publicar — e, abaixo, a trilha com um passo de cada vez: o passo de **Agora** tem o botão principal e, na linha "Mais
opções", os outros (por exemplo "Preparar com IA" e "Escrever sem IA"; "✓ Aprovar", "Conferir com IA" e "Ver como fica no site";
"Publicar em todos" e "Ir para publicar"); os **Feitos** dizem o que foi feito; os seguintes ficam **Aguardando**. A linha da fonte (no
passo 1) diz se a fonte oficial está confirmada ou liberada — com o motivo e, para o administrador, "Desfazer" — e as linhas dos canais
(no passo 3) dizem como está o site, o Instagram e o Facebook ("Desfazer" o "não vai" e "Cancelar só o Instagram/Facebook" que ia junto
com o site, para o administrador). No passo 2, o "✓ Aprovar" da trilha clica o Aprovar do texto, que confere tudo de novo e só aprova o
texto que estava na tela. "Publicar mesmo assim…" abre o campo do motivo na própria tela (mínimo de 10 caracteres).

### Imagem da publicação (v0.6.0; v0.25.0: uma só para o site, o Instagram e o Facebook)

**A mesma imagem vai para o site, o Instagram e o Facebook.** Cada conteúdo tem uma imagem da publicação (o mesmo arquivo nos três
lugares): o robô a manda ao site como capa da notícia, e o administrador a vê e autoriza no passo de cada rede, no "Publicar em todos"
e no "Publicar nos canais que faltam". É uma destas três:

- **A imagem gerada pela IA** ("Gerar imagem com IA"): uma imagem com **aparência de foto**, de estilo editorial (luz natural,
  profundidade de campo, cores naturais, ambiente brasileiro de trabalho), coerente com o assunto e com a cena pedida no campo "Como
  você quer a imagem" (opcional, até 500 caracteres; em branco, a IA escolhe a cena pela notícia). As orientações do escritório para as
  imagens (Configurações) também valem para a cena. Ela vai **inteira**, no formato horizontal **3:2** em que a IA cria (gravada em até
  1500×1000, JPEG), sem título, logotipo, selo, degradê nem rodapé por cima, com o aviso **"Imagem ilustrativa gerada por IA"** pequeno
  no canto de baixo, à direita, colocado pelo Radar (letra branca de uns 2% da altura, numa faixa escura translúcida). No site, o texto
  termina com a linha "Imagem ilustrativa gerada por IA."; nas legendas das redes, a mesma linha vem logo antes da identificação legal.
  É gerada em **qualidade alta** (custa mais por imagem que antes) e fica guardada: se outra imagem entrar no lugar, **"Usar a imagem
  da IA de novo"** a traz de volta sem nova cobrança.
- **Uma foto própria** (enviar o arquivo): vai em 3:2, cortada no centro, sem nada por cima e sem aviso. Foto de alguém da equipe só
  com a foto tirada de verdade e o termo de uso de imagem assinado (Pauta → Pessoas e termos).
- **A capa padrão Artecon** ("Usar a capa padrão Artecon (sem imagem)"): 1200 × 630, fundo azul-marinho com o logotipo, a categoria e o
  título, desenhada no próprio navegador, sem IA. Todo conteúdo novo já nasce com ela, e é ela que vai quando nenhuma outra foi
  escolhida. Como leva o título, depois de mudar o título a tela lembra de refazê-la (o mesmo botão).

A **arte vertical** (1080×1350, com chamada, apoio e rodapé legal) ficou **só nas peças da Pauta**; a notícia vai às redes com a
imagem da publicação. O pedido da imagem proíbe sempre: texto, letra, número ou legenda; logotipo, marca, brasão, bandeira ou símbolo
oficial; marca-d'água, assinatura ou crédito; pessoa real, pública ou identificável (ou parecida com alguém conhecido: as pessoas são
fictícias, adultas, em ambiente profissional, sem foco em rostos); obra ou estilo de artista ou fotógrafo existente; e cena que induza a
erro (documento oficial simulado, fachada de órgão público com nome, dinheiro em destaque). A descrição é recusada, antes de gerar e de
cobrar, se pedir marca, logotipo, brasão, assinatura de autor, autoridade ou pessoa famosa, ou "no estilo de" alguém. É um filtro por
palavras: não reconhece nome de pessoa real escrito sem cargo — por isso o pedido enviado à OpenAI repete sempre as proibições, e a
imagem deve ser conferida antes de aprovar. Trocar a imagem de um conteúdo aprovado devolve-o à revisão. A capa montada antes da
v0.25.0 com a ilustração ao fundo (título e logotipo por cima) continua até alguém trocar a imagem; enquanto isso, vai às redes com a
linha do aviso na legenda. Trocada pela capa padrão ou por uma foto, a ilustração dela fica guardada já em 3:2, com o aviso. A foto
enviada antes da v0.25.0 ficou na proporção original: o Instagram só aceita de 4:5 (em pé) a 1,91:1 (deitada), e a tela não autoriza o
Instagram com uma foto fora disso (envie a foto de novo, que ela vai em 3:2, ou use a capa padrão).

### Fale Conosco do informativo (v0.6.0)

A última página segue o modelo do escritório. Em Configurações → Fale Conosco, cada setor
tem `nome`, `rotulo`, `telefones`, `emails`, `equipe` e, opcionalmente, `responsaveis` (com
`responsaveis_rotulo`). Telefone é um texto (telefone fixo) ou
`{"numero": "…", "whatsapp": true, "nome": "opcional"}`. O arquivo
`radar-fale-conosco-v0.6.0.json`, entregue à parte, já vem preenchido: copie o conteúdo
para o campo e salve. Ele não vai no repositório porque traz nomes e celulares da equipe.

### Diretrizes editoriais e como ensinar a IA (v0.24.0)

As **Diretrizes editoriais** do escritório valem para todo conteúdo publicado no site e nas redes. A IA do Radar as recebe em todo
texto que escreve para publicar, depois das regras de sempre (nenhuma diretriz autoriza o que as regras proíbem), e a equipe as confere
antes de aprovar, no quadro "Conferência das Diretrizes". Em resumo:

1. **Fundamentação legal.** Toda informação apresentada como obrigação, direito, proibição, benefício fiscal ou exigência legal traz a
   norma que a sustenta (o número e, quando precisa, o artigo, o inciso ou o parágrafo), de preferência da fonte oficial (Receita
   Federal, Diário Oficial da União, Planalto, CONFAZ, SEFAZ, Comitê Gestor do IBS), com o link do documento oficial e a vigência
   conferida (alterações e revogações). Uma citação basta quando uma basta. Nunca inventar número de lei, artigo, link ou
   interpretação atribuída a órgão. No Radar: a norma citada uma vez no texto e a linha "Fonte oficial" no fim (etapa 5; antes, a
   seção "Fundamentação legal"), só com links dos dados do assunto.
2. **Conteúdo informativo.** O que não tem fundamentação legal específica é só informação: fatos e consequências práticas, em
   linguagem clara, sem caráter de obrigação legal e sem fundamentação jurídica artificial, separando o fato confirmado da estimativa,
   da projeção, da tendência ou da opinião e dizendo qual é a fonte. Decisão do escritório: a IA escreve esse texto como
   **Informativo**, ele fica em análise e só é publicado se o administrador autorizar.
3. **Originalidade.** Texto próprio: não copiar frases, parágrafos nem a estrutura de terceiros, nem disfarçar cópia trocando poucas
   palavras. Transcrição literal só quando indispensável (dispositivo legal, declaração relevante), sempre entre aspas e com a fonte.
   Citar a fonte não é o mesmo que poder copiar.
4. **Imagens.** Fotografia real com autorização ou licença, a capa institucional, ou ilustração de IA com o aviso "Imagem ilustrativa
   gerada por IA". Nesta versão, o Radar confere só o critério 6 da lista abaixo; as fotos reais (banco de imagens) e o aviso
   automático na imagem chegam na próxima etapa.
5. **Verificação.** Confirmar que a informação existe e de onde veio, dando preferência à fonte oficial e ao documento original;
   conferir datas, vigência e atualizações; não tratar proposta de lei como norma aprovada nem previsão como fato; em assunto
   controverso, buscar fontes independentes; sem confirmação suficiente, dizer a limitação ou mandar para a revisão humana.
6. **Estilo.** Profissional, claro e tecnicamente preciso; títulos objetivos e fiéis ao conteúdo; parágrafos organizados; compreensível
   para quem não é da área; destaque para o impacto prático nas empresas, nos empresários e nos contribuintes; sem sensacionalismo nem
   exagero; fundamentação proporcional ao texto.
7. **Critérios para aprovar.** Só se aprova o que atende integralmente aos critérios que se aplicam (a lista abaixo); senão, o texto é
   corrigido ou passa pela validação humana do administrador ("Revisei e assumo").

**Os 10 critérios da Conferência das Diretrizes** (no conteúdo, antes de aprovar; cada um com ✓ atende, ✗ não atende, — não se aplica
ou ? ainda não conferido, e o motivo numa linha):

| Nº | Critério | Quem confere |
|---|---|---|
| 1 | As informações estão confirmadas em fontes confiáveis? | a IA, no "Revisar com IA" |
| 2 | As afirmações legais têm fundamentação correta e vigente? | a IA; o Radar marca ✗ com [VERIFICAR] ou com norma citada sem a linha "Fonte oficial" com link oficial (ou a seção "Fundamentação legal" dos textos de antes; no Informativo, que não tem a linha, só com [VERIFICAR]) |
| 3 | O que não tem fundamento normativo está só como informativo? | a IA; o Radar marca ✗ no Informativo sem a fonte (campo Fonte) |
| 4 | O texto é original, sem reproduzir terceiros indevidamente? | a IA; o Radar marca ✗ com trecho igual ao da fonte fora de aspas ou frase do boletim pago (a transcrição entre aspas com a fonte citada não) |
| 5 | As citações literais estão identificadas (entre aspas e com a fonte)? | a IA; o Radar marca ✗ com trecho igual ao da fonte fora de aspas |
| 6 | A imagem é foto real autorizada, a capa institucional ou ilustração de IA com o aviso? | o Radar: capa padrão ou foto da equipe ✓; v0.25.0: a imagem da IA inteira, com o aviso no canto, ✓; a capa antiga montada com a ilustração da IA sem o aviso "Imagem ilustrativa gerada por IA" escrito no texto ✗; sem capa, não se aplica |
| 7 | O título corresponde exatamente à informação? | a IA |
| 8 | O conteúdo está atualizado? | a IA; o Radar marca ✗ com [VERIFICAR] |
| 9 | A redação é profissional e compreensível? | a IA |
| 10 | Nada no texto pode induzir o leitor a erro? | a IA |

Com algum ✗ ou ?, o **Aprovar fica travado** (na tela e no banco). Para destravar: corrija o texto e clique em **"Revisar com IA"** de
novo (ele também corrige [VERIFICAR], trecho copiado e a linha "Fonte oficial" que falta), ou, se você é o administrador e revisou o
texto, **"Revisei e assumo"**, com o motivo (fica no Histórico). Conferir de novo o mesmo texto, sem mudar nada, não tira um ✗. A
conferência vale para aquela versão: mudou o título, o texto, a fonte ou a capa, confira de novo. [VERIFICAR] e frase do boletim pago
continuam travando mesmo com o "Revisei e assumo" (com eles, o botão não aparece: resolva no texto).

**Humanização dos textos (etapa 5 da v0.24.0).** A Diretriz de Humanização do escritório vale para todo texto e legenda que a IA
escrever daqui para frente (o "Gerar com IA" e as passadas dele, os outros títulos, o "Revisar com IA", o kit das redes, as peças da
Pauta e os rascunhos do robô); o que já foi escrito não muda sozinho (os 9 roteiros de reel já gravados na Pauta ficam como estão). Em
resumo:

1. **Linguagem natural e profissional.** A IA escreve como um jornalista especializado em economia, contabilidade e legislação
   tributária, para empresários e profissionais da contabilidade: frases de tamanhos diferentes, palavras simples e precisas, sem
   "sofisticar", sem repetir a mesma informação com outras palavras e sem frase genérica que serviria para qualquer notícia.
2. **Sem as fórmulas de texto automático.** "Nesse cenário", "Diante desse contexto", "É importante destacar que", "Vale ressaltar
   que", "representa um avanço significativo", "abre uma janela de oportunidades", "Mais do que nunca", "Em um cenário de constantes
   transformações", "O momento de agir é agora" e "traz desafios e oportunidades" só aparecem se acrescentarem sentido. O texto começa
   pelo fato mais importante, sem introdução que só anuncia o assunto.
3. **A estrutura segue o assunto:** notícia simples em poucos parágrafos; mudança de lei com subtítulos, datas e impactos; análise
   técnica com exemplos e orientações práticas; Informativo mais direto e resumido; sem "conclusão" quando o último parágrafo já fecha.
4. **Base legal com naturalidade.** A norma é citada **uma vez**, no ponto em que sustenta a afirmação (com o artigo, quando importa),
   separando o que a lei determina da interpretação técnica. No fim, no lugar da seção "Fundamentação legal", uma linha curta:
   **"Fonte oficial: Instrução Normativa RFB nº 2.290, art. 2º — https://…"** (só com link que está no assunto; sem link, a linha cita a
   norma e ela vai para os pontos a conferir). Sem base legal específica, o texto é Informativo, sem justificativa jurídica artificial.
   A Conferência das Diretrizes aceita a linha nova e também a seção dos textos de antes.
5. **"Análise Artecon" só quando acrescenta:** impactos práticos, setores afetados, o que é obrigação legal e o que é boa prática,
   incertezas. Se a notícia não pedir, a seção não aparece. A IA nunca inventa interpretação jurídica nem consequência econômica.
6. **Sem publicidade automática.** Nada de convite para contratar ou procurar a Artecon no fim de todo texto, nem de urgência
   artificial; quando o assunto pede orientação profissional (a decisão depende do caso de cada empresa), uma menção discreta, no ponto
   certo. A identificação legal (empresa, CNPJ, CRC), o selo e os avisos de IA e o selo do Informativo continuam: são exigência legal e
   transparência, não propaganda.
7. **Revisão editorial antes da aprovação** (abaixo).
8. **Regra principal:** naturalidade, originalidade, precisão técnica e utilidade para o leitor, preservando as regras de fonte
   oficial, direitos autorais (boletim pago nunca copiado) e aprovação.

O exemplo do dono, que vai à IA **só como modelo de tom** (os fatos, os números e os setores dele nunca entram no texto):

> Antes (genérico): "A publicação das alíquotas abre a janela para revisar sistemas de precificação, adequar a escrituração fiscal e
> atualizar orçamentos que estavam rodando com estimativas internas."
> Depois (natural e técnico): "Com a definição das alíquotas da CBS sobre combustíveis, as empresas já podem conferir se os valores estão
> contemplados em seus sistemas fiscais e nas projeções de custos para 2027. Para distribuidoras, transportadoras e postos revendedores,
> essa verificação ajuda a identificar eventuais necessidades de ajustes antes do início dos efeitos tributários."

**Revisão editorial automática.** Depois que a IA escreve o texto (e da segunda passada, quando havia [VERIFICAR] ou trecho copiado a
corrigir), o "Gerar com IA" faz uma consulta a mais: a IA relê o rascunho com as **10 perguntas** do escritório — o texto está natural ou
mecânico? há frase que não acrescenta? repetição? os parágrafos fluem? o título reflete o fato principal? a base legal está certa e
integrada com naturalidade? a informação foi conferida nas fontes? a análise acrescenta conhecimento? há publicidade desnecessária? um
jornalista especializado publicaria assim? — e **reescreve só os trechos com problema**, antes de o texto ir para a aprovação. No
conteúdo, logo abaixo da Conferência das Diretrizes, o quadro **"Revisão editorial"** mostra cada pergunta com **✓** (sem problema) ou
**✎** (ajustado) e o motivo, e **"O que foi reescrito"** (antes → depois).

- **O que ela NÃO é:** não é detector de IA (não serve para "disfarçar" texto de máquina: olha clareza, originalidade, repetição,
  precisão técnica e utilidade para o leitor); não aprova nada (o quadro só informa: quem trava o Aprovar continua sendo a Conferência
  das Diretrizes); não substitui a leitura da equipe.
- **O que ela nunca faz:** acrescentar fato, número, norma ou link que não esteja no texto ou nos dados do assunto (com texto oficial,
  o que só o portal ou o boletim traz não conta como dado do assunto); tirar [VERIFICAR], citação entre aspas ou a linha "Fonte
  oficial" (com ou sem link); trocar ou tirar o link que já estava no texto; trazer frase igual à da fonte (mesmo trocando uma que já
  estava por outra). Pode encurtar (tirar a Análise Artecon que não acrescenta, frase e repetição que sobram), mas o texto que perde mais
  de 40% só vale se ela disser o que tirou, e nunca abaixo de um terço. O Radar confere isso por código: a reescrita que tentar é
  **recusada** e fica o texto de antes (o link novo fora do assunto sai do texto, com aviso, como sempre; o que a redação inventou sai
  antes da revisão).
- **Se falhar ou não couber no tempo:** o texto do rascunho segue normalmente e o quadro mostra **"Revisão editorial não feita"**, com o
  motivo e o botão **"Fazer a revisão editorial"** (uma consulta à IA, só da revisão). O mesmo botão aparece nos rascunhos do robô e nos
  textos da IA de antes desta versão. Se ela mudar o texto, confira e clique em "Revisar com IA" (a Conferência das Diretrizes é do texto
  novo) e gere o kit das redes de novo.
- **Texto mudado depois:** se o texto for editado à mão (ou pelo "Revisar com IA"), o quadro avisa que a revisão se refere à versão
  anterior, com o botão para fazer de novo. Trocar só o título por uma das sugestões não conta.
- **Tempo:** o pedido inteiro do "Gerar" tem até 140 segundos (a tela espera 150). A revisão editorial só começa se sobrarem pelo
  menos 30 segundos, e espera a IA por até 110.
- **Custo:** **uma chamada a mais à IA por texto gerado**: o material do assunto vai de novo na entrada (até uns 30 mil tokens no texto
  mais longo) e o texto revisado volta na saída (até uns 3 mil). Na prática, perto do dobro dos tokens do "Gerar" de antes. Conta no
  limite mensal do Radar (`RADAR_IA_LIMITE_MENSAL_TOKENS`) e aparece na IA Central como "gerar". Nos títulos, no kit das redes e nas
  peças da Pauta, a IA faz essa conferência sozinha, **na mesma consulta** (sem custo a mais).

**Chamadas comerciais automáticas: o que havia e o que mudou (etapa 5).**

- O formato "Médio (notícia)" mandava a "Análise Artecon" terminar com "o risco de não agir e quando vale procurar a Artecon" (no "Gerar
  com IA" e nos rascunhos do robô): saiu, e a seção ficou opcional.
- O kit das redes pedia, em toda legenda do Instagram e do Facebook, "um convite moderado para conversar com a Artecon": saiu. O fim do
  reel ("chamada final") convida a ler a matéria completa, sem convite comercial.
- As peças da Pauta terminavam sempre com "Fale com a gente" / "Agende uma conversa": agora só a **Captação** (a peça que o plano faz para
  isso) termina com o convite moderado; as outras (Quem cuida, Bastidor, Educativo, Agenda, Data com a equipe) não.
- A regra de escrita da IA proíbe chamada para contratar, "fale conosco" no fim e urgência artificial; orientação profissional, só
  discreta e quando o assunto pedir.
- Ficam como estão (não são chamada automática): "Leia a matéria completa no site" nas legendas (leva à notícia), a identificação legal
  das redes, a cartela do reel e a página "Fale Conosco" do Informativo Mensal (os contatos do escritório, uma vez por edição, no modelo
  enviado aos clientes). O robô do site e a tela não acrescentam chamada nenhuma ao texto. Termos de propaganda ("garantimos", "consulta
  grátis", "não perca") continuam travados ou avisados como antes.

**O texto Informativo, passo a passo:**

1. Assunto sem texto oficial (só boletim, portal ou editora): o "Preparar com IA" (antes "Gerar com IA") escreve o texto Informativo,
   faz a capa, a conferência dos 10 critérios e as legendas, e leva o texto para "em revisão". Com texto oficial, a IA também pode
   dizer que o assunto não tem base legal específica (um alerta, um dado econômico); aí o texto também é Informativo.
2. O conteúdo aparece com o selo **"Informativo — aguardando autorização"**, sem o botão Aprovar. No passo 2 (Conferir e aprovar), a
   trilha mostra "Autorizar o Informativo", com a lista dos 10 critérios e o aviso de que a autorização vale para o assunto inteiro.
   Se algum critério estiver "?" ou com ✗, o "Conferir com IA" já aparece ali: a conferência não precisa esperar a autorização.
3. O administrador confere e clica em **"Autorizar a publicação do Informativo…"** (no conteúdo ou na trilha), escreve o motivo e
   confirma: quem, quando e o motivo ficam no assunto e no Histórico. A autorização vale para o assunto inteiro (é o "Publicar mesmo
   assim"): os outros textos dele também podem ir ao site sem a fundamentação oficial. "Desfazer a liberação" devolve o Informativo
   aprovado para a revisão.
4. O selo vira **"Conteúdo informativo"** e o conteúdo segue o caminho de sempre: Conferência das Diretrizes, aprovar, site e redes.
   No site, a notícia sai com a linha "Conteúdo informativo" no fim (a prévia mostra).

**Como ensinar a IA.** Em **Configurações → Inteligência artificial → "Orientações para a IA"** (só o administrador). Escreva como explicaria o trabalho a
um redator novo: frases curtas, uma ideia por linha. A IA lê as orientações em todo pedido; depois de salvar, elas valem a partir do
próximo "Gerar com IA" (o que já foi gerado não muda sozinho: gere de novo). Em branco, a IA trabalha como antes.

**Orientações para os textos** (até 2.000 caracteres): tom, estilo, tamanho, o que evitar e exemplos de posts de que o escritório
gostou. Um exemplo bom:

> Tom próximo e direto, como quem conversa com o dono de uma pequena empresa. Frases curtas, sem juridiquês; explique a sigla na
> primeira vez. Comece pelo que muda para o cliente e termine dizendo o que ele precisa fazer e até quando. Nada de exclamação, emoji
> ou "fique atento". Na legenda do Instagram, no máximo 4 parágrafos curtos.
> Post de que gostamos: "O prazo mudou. Veja o que a sua empresa precisa conferir até o fim do mês."

**Orientações para as imagens** (até 500 caracteres): estilo, cenas preferidas e o que evitar. Um exemplo bom:

> Fotos claras, com luz natural e pessoas em situação real de trabalho. Prefira cenas de escritório, de pequenos comércios e de
> atendimento ao cliente. Evite cofres, pilhas de dinheiro, martelo de juiz e setas de gráfico subindo.

(v0.25.0: a imagem já sai com aparência de foto; as orientações e a cena pedida mandam no que aparece nela.)

**O que não adianta pedir** (as regras e as Diretrizes passam por cima das orientações, e o Radar confere por código):

- **Texto dentro da imagem** (título, número, nome da empresa): a imagem da IA nunca tem letra nem número, e vai inteira (v0.25.0):
  o único texto nela é o aviso "Imagem ilustrativa gerada por IA", colocado pelo Radar no canto. O título só aparece na capa padrão.
- **Pessoa real ou conhecida** (alguém da equipe, um político, um artista), **marca ou logotipo** (da Artecon ou de outra empresa) e
  **"no estilo de"** um artista ou estúdio: o pedido da imagem proíbe isso sempre. Se as orientações para as imagens pedirem, elas
  ficam de fora daquela imagem inteira e a tela avisa, com a palavra que travou; reescreva só com o estilo e as cenas.
- **Copiar notícia** (de portal, de concorrente ou do boletim pago): o texto é sempre escrito com palavras próprias, a partir da fonte
  oficial. Os exemplos de posts mostram só o estilo: a IA não usa os fatos, os números nem as datas deles. Frase do boletim pago não
  entra nem nas orientações (a tela recusa ao salvar).
- **Fato, número ou data** que não esteja na fonte, **promessa** ("garantimos", "pague menos imposto"), **oferta** ("consulta
  grátis") ou **comparação** com outros escritórios: a publicidade contábil não admite, e a tela trava ou avisa como sempre.
- **CNPJ, CRC e telefone** no texto: a identificação legal é acrescentada pela tela, a partir de "Fecho, assinatura e identificação
  legal", nunca pela IA.

Se o resultado ainda não sair como quer, mude uma coisa de cada vez e gere de novo: fica mais fácil saber o que funcionou.

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
- **Conferência das Diretrizes (v0.24.0):** nenhum conteúdo é aprovado, nem pela API, sem a lista dos 10 critérios da versão do texto
  que está no conteúdo, sem critério que não atende (ou com o "Revisei e assumo", que só o administrador faz, com o motivo). A lista
  só muda pelas funções do banco (a da IA, gravada como quem pediu, e a do administrador), e o banco confere sozinho, por cima dela, o
  que dá por código: a capa, [VERIFICAR], a linha "Fonte oficial" com link oficial (ou a seção "Fundamentação legal" dos textos de
  antes), a fonte do Informativo e o boletim pago.
  Gravar a lista não muda a data do conteúdo; mudar o título, o texto, a fonte ou a capa a deixa sem valer. Quem não é o
  administrador não tira o ✗ que a lista do mesmo texto já tinha, nem gravando outra lista pela API: o ✗ cai com o texto corrigido ou
  com o "Revisei e assumo". No Informativo, a norma só mencionada não leva ✗ no critério 2 por código (ele não tem a linha). Limite: a
  lista da IA é gravada com o login de quem pediu (a função não a assina), então um editor que gravasse pela API, antes da IA, uma
  lista inventada conseguiria aprovar o que o banco não confere por código, e ficaria com o nome dele na lista e no Histórico.
- **Revisão editorial (v0.24.0, etapa 5):** o resultado da revisão editorial da IA fica no conteúdo só pela função do banco
  (`radar_registrar_revisao_editorial`: editor ou administrador, as 10 perguntas com "ok" ou "ajustado" e o motivo, até 12 trechos
  reescritos, ou "não feita" com o motivo; só para o texto que foi à IA), com a versão do corpo do texto; o UPDATE direto e o INSERT não
  a forjam, e gravar a Conferência das Diretrizes ou o "Revisei e assumo" depois não a apaga. Ela só informa: não trava nem libera a
  aprovação.
- **Informativo (v0.24.0):** o texto Informativo só é aprovado depois que o administrador autoriza a publicação do assunto (com o
  motivo); o aviso que o marca como Informativo não sai do texto (os pontos a conferir só crescem); desfeita a autorização, o
  Informativo aprovado volta para a revisão (e as autorizações de publicação dele que esperavam caem, porque o conteúdo mudou).
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
- **Pauta (v0.21.0):** só o administrador aprova a peça, e o que vai ao ar é exatamente o que ele aprovou (a peça aprovada não
  muda; os campos de aprovação e os links não podem ser gravados à mão, nem pelo editor). Só se marca na peça quem está
  cadastrado, e a aprovação exige o termo de uso de imagem válido no dia, no canal e na finalidade (nas fotos, quem confere é o
  administrador, com a caixa "Conferi" da aprovação); a legenda precisa da identificação legal (CNPJ e CRC das Configurações);
  número fora das informações conferidas, [VERIFICAR], fonte ou frase do boletim pago, nome no texto de pessoa que não está
  marcada e "contador" para quem não tem registro impedem a aprovação. Antes de cada publicação automática, o banco confere tudo de novo, e uma publicação nunca sai
  duas vezes: a que deu erro ou ficou sem resposta clara da Meta só é tentada de novo com "Conferi no Instagram e no Facebook: não
  saiu". A trilha de auditoria guarda o que foi ao ar, mas não os nomes, o CRC das pessoas, o plano nem a sugestão da IA.
- **Peça nova (v0.28.0):** só o administrador cria a peça de um dia vazio ("+ Nova peça"), de hoje em diante (de Brasília), uma
  peça por dia (o dia com peça, mesmo cancelada, não ganha outra); os campos passam pela mesma conferência da importação do
  calendário, e o assunto é obrigatório. A peça nasce planejada, sem pessoas, sem aprovação e sem envio: não publica nem agenda nada.
- **Sócio(a) da Artecon (v0.28.0):** só o administrador marca. Para o(a) sócio(a) maior de idade, o banco não exige o termo de uso de
  imagem nem o termo do corretor de vídeo; continuam exigidos: a pessoa ativa, maior de idade, marcada em "Quem aparece", e as quatro
  declarações do envio do vídeo. Sem a marca, os dois termos voltam a ser exigidos (a peça não fica pronta nem sai, e o vídeo do
  corretor com a pessoa é apagado na limpeza do dia seguinte). A marca vai à trilha, sem o nome.

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
  oficial): ele é enviado à IA (Anthropic, pela IA Central) e serve de base para os "pontos a conferir".
- Qualquer evidência conferida em fonte oficial satisfaz a exigência, inclusive as
  marcadas como "interpretação técnica" ou "hipótese", e o sistema não avalia se o trecho
  tem relação com o texto escrito. Era assim na antiga publicação e continua.
- O Radar só publica no site da Artecon com a autorização do administrador (v0.10.0, "Publicar no site
  com autorização"): o robô só cadastra notícias e nunca contorna o reCAPTCHA do painel. Desde a v0.8.0, o robô **encontra sozinho** a notícia
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
- Imagem substituída ou sem uso é apagada sozinha (na hora, ou pelo robô ao fim da coleta, depois de 24 h).
- A coleta só deixa o workflow vermelho quando **nenhuma** fonte funciona. Falha isolada
  aparece no painel ("Fontes que pedem atenção") e, depois de 3 falhas seguidas, vira aviso por
  e-mail (issue no GitHub).
- Reexecutar o setup refaz permissões e políticas `radar_*` do zero, mas não altera dados
  nem fontes já configuradas.
- A verificação do texto gerado pela IA não lê números por extenso, incisos nem normas
  citadas sem número (CTN, CLT), e não avalia a interpretação. A revisão técnica continua
  sendo de uma pessoa.
- O teto mensal de tokens é conferido antes de cada pedido; pedidos simultâneos podem
  ultrapassá-lo um pouco. Por isso os limites de gasto da IA Central (Portal → Consumo de IA)
  continuam indispensáveis. O uso da IA pelo robô (nota das capturas e rascunhos automáticos)
  aparece só na IA Central, não no painel do Radar.
- O texto oficial capturado é enviado à IA (Anthropic, pela IA Central do Portal) para análise;
  a imagem da publicação é pedida à OpenAI só com o tema (e a cena pedida). Nada de dados de clientes, tokens ou
  e-mails de usuários é enviado.

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
(tempo esgotado, erro 500) não abre aviso, porque costuma ser passageiro. Desde a v0.21.0, enquanto houver publicação da
**Pauta** que não saiu (com erro, parada em "publicando" ou com a hora passada), fica aberto um aviso só, "Radar: publicação
agendada não saiu" (veja "Pauta: o calendário das redes e a publicação agendada").

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

### Lembretes por e-mail antes do dia (v0.29.0)

Os avisos de antes (fonte com falha, a Pauta "não saiu", o resumo de segunda) chegam **depois** que algo aconteceu. Os lembretes chegam
**antes**, para dar tempo de resolver:

| Lembrete (título do aviso) | Quando chega | O que lembra |
|---|---|---|
| "Radar: lembrete — Pauta de amanhã sem aprovação" | na véspera, a partir da `hora` (padrão 16:00), até o fim do dia | a peça de amanhã que ainda não está aprovada (planejada, em produção ou pronta) e a de hoje que ainda não saiu; e a aprovada para publicar à mão que, **uma hora depois da hora marcada**, ainda não tem o link registrado (antes disso a equipe ainda vai postar). Se o e-mail da Pauta do dia já saiu antes dessa hora, ela vai no do dia seguinte, como "ontem" |
| "Radar: lembrete — peça pronta esperando aprovação" | entre `de` e `ate` (padrão 08:00 e 20:00) | a peça pronta há mais de `aprovacao_horas` (padrão 24) esperando a aprovação do administrador; a de hoje e a de amanhã ficam no lembrete da Pauta (um lembrete só por peça) |
| "Radar: lembrete — vídeo do reel para conferir" | entre `de` e `ate` | o reel que o corretor terminou: "Vídeo corrigido pronto", "Precisa regravar" ou "O corretor parou" (cada resultado novo do corretor é lembrado uma vez, até a peça ser aprovada com o vídeo) |
| "Radar: lembrete — notícia que não saiu" | entre `de` e `ate` | a notícia cujo envio ao site, ao Instagram ou ao Facebook deu erro, ou cuja autorização está parada há mais de `parada_horas` (padrão 3). A peça da Pauta não entra aqui: ela já tem o aviso "publicação agendada não saiu" |

**As regras (sem enxurrada):**

- **No máximo um e-mail por tipo por dia** (dia de Brasília). O que aparecer depois do e-mail do dia espera o dia seguinte (dentro
  do horário). Na prática, de 0 a 2 e-mails por dia; no máximo 4.
- **Cada pendência é lembrada uma vez só.** A peça lembrada na véspera como "amanhã" não é lembrada de novo no dia como "hoje"; a de
  hoje entra só se ainda não foi lembrada (criada hoje, por exemplo). A pendência volta a ser lembrada só se acontecer de novo: a
  peça saiu de "pronta" e voltou, o corretor devolveu outro resultado, outro envio deu erro.
- **Resolvida, ela sai da lista sozinha**: a peça foi aprovada, cancelada ou mudou de dia; o vídeo foi aprovado com a peça ou voltou
  para a fila; o envio saiu, foi cancelado ou autorizado de novo. O aviso no GitHub não é fechado nem editado (cada mudança mandaria
  mais um e-mail): ele fica aberto, como a "caixa" daquele tipo.
- **Sem nome:** o repositório é público. O lembrete leva só a data, a hora, o formato e o número da peça ou do envio, e o que fazer.
  Nunca o assunto, quem aparece, a legenda, o texto do erro ou do boletim pago (o banco nem entrega isso ao robô).
- **Nada é publicado pelo lembrete.** Ele só avisa; a publicação continua dependendo da aprovação do administrador.
- Erro com mais de 7 dias não entra (a primeira rodada não traz o que é antigo).
- **Mudar as Configurações não repete lembrete.** Subir ou baixar `parada_horas` ou `aprovacao_horas`, ou ligar e desligar um tipo,
  muda só quando a pendência pode ser lembrada; a que já foi lembrada não volta.
- O dia que conta no "um por dia" é o da hora em que o robô pegou o lembrete (se ele só confirmar depois da meia-noite, o e-mail
  continua sendo do dia em que saiu).

**Quem recebe:** como os outros avisos do Radar, o e-mail é a notificação do GitHub quando o robô abre um aviso (issue) ou comenta
nele. Recebe quem acompanha o repositório: o dono já acompanha (confira em github.com → Settings → Notifications se "Issues" está com
e-mail ligado). Outro administrador que também queira receber: no repositório, **Watch → Custom → Issues** (e "Issues" com e-mail
ligado nas Notifications dele). Como o repositório é público, qualquer pessoa poderia acompanhar e qualquer pessoa pode ler os avisos
na aba Issues: por isso o lembrete não leva nomes nem o assunto. O que fica à vista é a data, a hora, o formato e a situação das peças
lembradas (por exemplo, "Amanhã, 28/10 às 09:30 — Reel (peça nº 412): em produção"). Se o escritório preferir não deixar isso à vista,
desligue o tipo em Configurações (por exemplo, `"pauta": false`).

**Como funciona por dentro:** o banco guarda cada pendência na tabela `radar_lembretes` e decide o que lembrar (as funções
`radar_lembretes_*`). De 15 em 15 minutos, a agenda do banco (`sql/radar-redes-agenda.sql`, agendamento `radar-redes-agenda-lembretes`)
pergunta ao banco e, só com lembrete para mandar, pede à `radar-redes` (ação `acionar_lembretes`) que acione o workflow "Radar —
lembretes por e-mail" no GitHub, com o mesmo `RADAR_GITHUB_TOKEN` do robô do site (o pedido para a mesma pendência sai no máximo uma
vez a cada 30 minutos). O workflow também roda sozinho de hora em hora (no minuto 29), de reserva: se o GitHub atrasar ou o acionamento
falhar, o lembrete sai na rodada seguinte. Sem nada a lembrar, ele termina em segundos. O robô (`robo/radar_lembretes.py`) nunca fica
vermelho: um erro vai só para o registro, sem segredo, e a próxima rodada tenta de novo.

**Configurações → Lembretes por e-mail** (só o administrador; o valor fora dos limites a tela recusa e, se chegar ao banco, vale o
padrão):

| Chave | O que é | Padrão |
|---|---|---|
| `ligado` | `false` desliga todos os lembretes | `true` |
| `pauta`, `aprovacao`, `video`, `noticia` | `false` desliga só aquele tipo | `true` |
| `hora` | a hora (de Brasília, "HH:MM") a partir da qual sai o lembrete da Pauta de amanhã; vai até `"23:45"` (o Radar confere de 15 em 15 minutos) | `"16:00"` |
| `de`, `ate` | o horário dos outros três lembretes (`de` antes de `ate`, com pelo menos 15 minutos entre os dois) | `"08:00"` e `"20:00"` |
| `aprovacao_horas` | quantas horas a peça pronta espera antes do lembrete (1 a 168) | `24` |
| `parada_horas` | quantas horas a notícia autorizada fica parada antes do lembrete (1 a 48) | `3` |

Embaixo do bloco aparece a **situação**: se a agenda do banco está instalada (e a última rodada), o último lembrete de cada tipo (quando
e o número do aviso no GitHub) e quantas pendências já podem ser lembradas e esperam o próximo lembrete.

**Limites desta versão:** se alguém fechar à mão o aviso de um tipo, o GitHub manda um e-mail curto de "fechado", e o próximo lembrete
abre outro aviso (o robô nunca fecha). Dia sem peça no calendário não gera lembrete (ideia anotada para o futuro). A exclusão no site
que deu erro continua aparecendo só em Publicações. O aviso "publicação agendada não saiu" continua com a coleta (de 6 em 6 horas).

### Publicar no site com autorização (v0.10.0)

Regras combinadas com o escritório: o robô **só cadastra notícias** no painel do site
(artecon.cnt.br/admin → Notícias → cadastrar) e **nada vai ao ar sem a autorização** do administrador.

1. Conteúdo aprovado e assunto pronto para o site (confirmado oficialmente e com trecho conferido
   em fonte oficial) → passo 4 → confira em **Ver como fica no site**, escolha a **categoria do site**
   e clique em **Autorizar publicação no site** (só o administrador vê o botão).
2. Na hora da autorização, o Radar aciona o workflow `radar-site-publicar.yml` pela função `radar-redes` (v0.19.0, segredo
   `RADAR_GITHUB_TOKEN`); sem o segredo, vale o agendamento (minutos 7, 22, 37 e 52 de cada hora, que o GitHub pode atrasar).
   O workflow confere se há autorização. Havendo, o robô
   (`robo/radar_site_publicar.py`) marca "enviando" (nunca reenvia), entra no painel do site, preenche
   título, palavras-chave, descrição, texto (com subtítulos, listas e negrito), categoria e capa, e clica
   em "Gravar notícia" — **o site publica na hora**.
3. Em seguida o robô acha a notícia em artecon.cnt.br/news, registra o link em "Publicações no site"
   e marca "publicado". Se a notícia não aparecer em 2 horas, marca "erro" e pede para conferir no
   painel do site antes de autorizar de novo (para não duplicar).

- **Cancelar**: enquanto o robô não começou, "Cancelar autorização" no passo 4.
- **Texto mudou depois de autorizado** (título, texto, autor, fonte, capa, situação): a autorização cai
  sozinha e é preciso autorizar de novo.
- **reCAPTCHA**: o usuário do Radar foi liberado pelo site para entrar só com usuário e senha. O robô
  nunca resolve nem contorna a verificação: se o site passar a exigir, ele para e mostra o motivo no passo 4.
- **Segredos do GitHub**: `ARTECON_SITE_USUARIO` e `ARTECON_SITE_SENHA` (além dos do banco). Nunca no código,
  no banco ou no chat. O registro do GitHub Actions não mostra texto, usuário, senha nem cookie.

### Robô do site na hora (v0.19.0)

O agendamento do GitHub atrasa muito (em outubro de 2026 rodou a cada 3 a 7 horas). Para a publicação e a exclusão no site
saírem em 1 a 2 minutos, a função `radar-redes` aciona o robô logo depois da autorização. Ela precisa de um **token de acesso
fino do GitHub**, só deste repositório, guardado **só** no Supabase:

1. GitHub → foto do perfil → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** →
   **Generate new token**.
2. **Token name:** "Radar — acionar o robô do site". **Expiration:** até 1 ano (anote a data para renovar).
   **Resource owner:** `arteconartescontabeis-design`.
3. **Repository access:** "Only select repositories" → `radar`.
4. **Permissions → Repository permissions → Actions:** "Read and write" (o "Metadata: Read-only" vem junto). Nada mais.
5. **Generate token** e copie o valor (aparece uma vez só).
6. Supabase (projeto do Radar) → **Edge Functions → Secrets → Add new secret**: nome `RADAR_GITHUB_TOKEN`, valor = o token.
   **Nunca** pelo chat, nos segredos do GitHub, no `index.html` ou no `radar-config.js`.
7. Teste: autorize uma publicação; o recado diz "Robô acionado: a publicação deve sair em 1 a 2 minutos." Sem o segredo, o
   recado explica que falta o `RADAR_GITHUB_TOKEN` e a publicação sai na próxima rodada automática.

Segurança: a função aciona sempre o mesmo workflow (`radar-site-publicar.yml`, fixo no código), só a pedido do administrador,
só quando há publicação ou exclusão esperando e no máximo uma vez a cada 30 segundos. O token nunca vai para a tela nem para
os registros. Quando ele vencer, o recado avisa ("o GitHub recusou o token") e basta gerar outro e trocar o segredo.

**Robôs desligados pelo GitHub (v0.22.0).** Neste repositório público, o GitHub desliga sozinho os workflows agendados (a coleta, o
robô do site e o resumo) depois de **60 dias sem atividade** no repositório (o recesso de fim de ano é o caso provável), e eles só
voltam com "Enable workflow" — mesmo que entre commit novo depois. Com o mesmo token, a agenda do banco (`sql/radar-redes-agenda.sql`)
pede uma vez por dia à `radar-redes` que religue os desligados por inatividade (o desligado à mão fica; v0.29.0: o dos lembretes por
e-mail também). Se o robô do site estiver
desligado na hora de acionar, a função o religa e aciona; se não conseguir, o recado diz onde religar (GitHub → Actions → "Radar —
publicar no site" → Enable workflow), sem prometer a rodada automática. O **Painel** avisa quando a coleta não roda há mais de 12 horas.
- **Sessão no site**: o login do robô pode encerrar a sessão de quem estiver usando o mesmo usuário no
  painel do site. O ideal é um usuário só do Radar, com acesso apenas ao cadastro de notícias.
- O registro manual ("Registrar publicação no site") e o registro automático da v0.8.0 continuam valendo.

### Fila, rascunhos automáticos e vigia das fontes (v0.9.0)

- **Nota da IA rebaixa:** captura "alta" com nota da IA até 3 desce para "média" (sai do topo, continua
  na fila). Configurações → Relevância → `nota_rebaixa` (padrão 3; -1 desliga). Sem nota, nada muda.
- **A fila não acumula:** ao fim de cada coleta, o que está na triagem há mais de `arquivar_dias`
  (padrão 10) e é baixa, ou tem nota da IA até `arquivar_nota` (padrão 2), sai como "Ignorado"
  (Assuntos → Ignorado; as repetições vão junto). Configurações → Relevância; 0 dias desliga.
  O botão "Ignorar as N desta lista" (filtro Baixa) continua para limpar à mão.
- **Rascunhos automáticos:** depois da nota da IA, o robô escolhe as capturas de fonte oficial, com
  texto oficial, relevância alta, nota da IA 9 ou mais, dos últimos 3 dias e ainda na fila; abre o
  assunto e grava o rascunho (formato informativo) com as mesmas regras do "Gerar com IA" e os pontos
  a conferir. No máximo 2 por dia. Ele **não** envia para revisão, não aprova e não publica; a capa é
  gerada pela equipe. Aparecem no Painel em "Rascunhos preparados pelo robô". Configurações →
  Rascunhos automáticos (`ligado`, `nota_minima`, `por_dia`, `dias`, `formato`). Usa o segredo
  `RADAR_IA_GATEWAY_TOKEN` (o mesmo da nota da IA) e o modelo `claude-sonnet-4-6` (variável
  `RADAR_IA_MODELO` na aba Variables do GitHub para trocar). Custo estimado: cerca de 10 mil tokens por rascunho.
- **DOU Destaques:** só entram links de atos da Receita, PGFN, CGSN, CGIBS, Fazenda (MF, Cosit) e
  leis, decretos e medidas provisórias (`padrao_url` da fonte).
- **Aviso "fonte parada":** fonte ativa sem funcionar há mais de 3 ciclos abre o aviso
  "Radar: fonte parada — …" (fecha sozinho quando volta). Para o boletim da ITC, a rotina diária
  registra cada execução, mesmo sem e-mail; se ela parar, o aviso chega em até 3 dias.
- **Resumo de segunda:** lista as fontes ativas sem notícia nova há mais de 5 dias.

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
estragar nada). Ele cadastra, **desligadas**, estas três fontes testadas pelo diagnóstico (além do INLABS,
também desligado, e do boletim da ITC, descrito abaixo):

| Fonte | Oficial | Observação |
|---|---|---|
| Diário Oficial da União — Destaques | sim | só a seleção diária da Imprensa Nacional (pouco volume, sem enxurrada) |
| Econet Editora — Blog (RSS) | não | a área de assinantes pede login e fica de fora |
| Portal Contábil SC — Notícias (RSS) | não | site lento: o texto vem do feed |

Ligue cada uma em Fontes → Configurar → Fonte ativa. Fontes não oficiais servem de alerta e pauta;
a fundamentação continua vindo só das oficiais.

### Instagram e Facebook pela API da Meta (v0.13.0)

A função `radar-redes` publica o que o administrador autorizou nos passos 6 e 7 da trilha. Nada sai sem essa autorização.

1. **Contas (você):** Instagram profissional (Empresa) ligado à Página do Facebook da Artecon; as duas no portfólio da
   Meta Business Suite; aplicativo "Radar Artecon" na Meta for Developers (tipo Empresa, com "Login do Facebook para Empresas").
2. **Permissões do aplicativo** (pedidas na análise da Meta): `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
   `pages_read_engagement`, `pages_manage_posts` e `business_management`.
3. **Segredos no Supabase** (Edge Functions → Secrets; nunca pelo chat nem no GitHub):
   - `META_PAGE_ID`: id da Página do Facebook (business.facebook.com → Contas → Páginas → a Página → ID);
   - `META_PAGE_TOKEN`: o token do **usuário do sistema** (business.facebook.com → Usuários do sistema → Gerar token, expiração
     "Nunca", com a Página atribuída com acesso parcial — Conteúdo, mensagens, atividade da comunidade e insights; não ligue
     "Tudo", que permite apagar a Página e tirar pessoas). A função `radar-redes` (v0.14.1) busca sozinha o token da Página a
     partir dele; o próprio token da Página também é aceito;
   - `META_IG_USER_ID`: id da conta do Instagram profissional ligada à Página (o "Testar conexão" mostra o número a gravar);
   - `META_IG_TOKEN` (v0.14.4, opcional): token do usuário do sistema gerado no aplicativo do Instagram (caso de uso
     "Gerenciar mensagens e conteúdo no Instagram", com `instagram_basic`, `instagram_content_publish`, `instagram_manage_contents`
     — esta para excluir publicações —, `pages_show_list`, `pages_read_engagement` e `business_management`). Sem ele, o
     Instagram usa o mesmo token da Página;
   - opcional `META_GRAPH_URL` (padrão `https://graph.facebook.com/v23.0`).
4. **Instalar a função:** Supabase → Edge Functions → nova função `radar-redes` com o arquivo `supabase/functions/radar-redes/index.ts`
   (com "Verify JWT" ligado). A Meta só aceita imagem por link: a função cria sozinha o armazenamento **privado** `radar-pauta`
   (v0.21.0, para as peças da Pauta, com foto da equipe; desde a v0.22.0, também para a imagem da notícia), e a Meta recebe um link
   assinado que vale 10 minutos: o arquivo não fica aberto na internet. Ele precisa continuar privado: se alguém o deixar público no
   painel do Supabase, a função recusa a publicação (nada sai) e o teste do item 5 aponta. Até a v0.21.0, a imagem da notícia ia
   para o bucket **público** `radar-redes`, com nome fácil de adivinhar, e ficava lá: apague pelo painel (Storage → `radar-redes`) as
   que ainda estiverem lá (a função apaga a de cada publicação que ela mesma excluir da rede).
5. **Testar:** Publicações → "Testar conexão com o Instagram e o Facebook". Todos os itens devem ficar OK (desde a v0.22.0, o item
   "Armazenamento das imagens" mostra o bucket privado `radar-pauta`).

Sem os segredos, o botão "Autorizar e publicar" grava a autorização e avisa que a Meta ainda não está configurada; depois é
só usar "Publicar agora" no mesmo passo.

6. **Antes do primeiro post (v0.20.0):** em Configurações → "Fecho, assinatura e identificação legal", preencha `cnpj` e `crc`
   (o registro da empresa no CRC-SC, como "CRC-SC 007129/O-0", com a letra O depois da barra) e salve: as legendas (e a arte das
   peças da Pauta) levam essa identificação no fim. Confira também o link da bio do Instagram, que deve abrir artecon.cnt.br/news. Sem eles, a Pauta
   (v0.21.0) não aprova nenhuma peça.
7. **Agenda da Pauta (v0.21.0):** rode uma vez `sql/radar-redes-agenda.sql` no SQL Editor, **depois** do setup e do Deploy da
   `radar-redes` v0.21.0. Ele liga o pg_cron (como manda a página "Install pg_cron" do Supabase), cria no Vault a chave
   `radar_redes_agenda`, que só o banco conhece, e agenda de 5 em 5 minutos a chamada da função para cada peça aprovada cuja hora
   chegou (sem nada vencido, nenhum pedido sai). A função continua com **"Verify JWT" ligado**: a agenda manda no `Authorization`
   a chave anon, que é pública (a mesma do `radar-config.js`, escrita no arquivo; o próprio SQL recusa qualquer chave que não seja
   a anon), e a chave do Vault no cabeçalho `x-radar-agenda`. Com ela, a função só publica peça da Pauta cuja hora chegou, e mais
   nada. **Teste**, sem publicar nada: copie as 5 linhas do `select net.http_post(…)` com `{"acao":"agenda_teste"}` que está no
   comentário do fim do arquivo para uma consulta nova, **sem os `--` do começo** (selecione e aperte Ctrl+/), e execute — não há
   nada para trocar: a chave anon vem do próprio agendamento e a da agenda, do Vault. Alguns segundos depois, rode a consulta a
   `net._http_response` (também sem os `--`): o esperado é 200 com `{"ok":true,"versao":"0.22.0"}` (com a radar-redes v0.21.0,
   "0.21.0"). v0.22.0: o mesmo arquivo agenda também, uma vez por dia (05h13), o pedido "manter_robos": a `radar-redes` religa os
   robôs agendados do GitHub (coleta, robô do site e resumo) que o GitHub desligou por 60 dias sem atividade no repositório público
   (precisa do segredo `RADAR_GITHUB_TOKEN`, o mesmo do "Robô do site na hora"; o workflow desligado à mão fica desligado). Se o projeto do Supabase ou a
   chave anon mudarem, troque no arquivo e rode de novo (os testes conferem que a chave do arquivo é a do `radar-config.js`). Para desfazer: `sql/radar-redes-agenda-reversao.sql` (a chave fica no Vault).

### Pauta: o calendário das redes e a publicação agendada (v0.21.0)

A aba **Pauta** organiza as publicações próprias da Artecon no Instagram e no Facebook (Quem cuida, Bastidor, Educativo, Captação,
Agenda da semana, Data com a equipe, reels), uma peça por dia. As notícias continuam pelo caminho de sempre: no dia de notícia, a
Pauta só aponta para Assuntos e Publicações. Todos veem a Pauta; o leitor não tem botões e não vê as pessoas. Desde a v0.27.0, os
três perfis (o leitor inclusive) veem no alto da semana o mesmo quadro "Cronograma de publicações", só com números (veja
"Cronograma de publicações da Pauta (v0.27.0)"). A semana vai de segunda a domingo, e "hoje" é sempre o dia de Brasília.

**1. Pessoas e termos** (Pauta → "Pessoas e termos"; o administrador cadastra e altera, o editor só consulta, o leitor e o robô não
leem). Para cada pessoa que pode aparecer: nome completo (interno), **nome na peça** (como o termo autoriza: completo ou só o
primeiro), área, categoria e registro no CRC (só contador e técnico; "contador(a)" e "técnico(a)" só com o registro), as datas do
termo de uso de imagem (assinado, válido até, revogado), os canais e as finalidades que a pessoa marcou (Apresentar a equipe,
Orientação, Datas da empresa, Captação de clientes). **Registre só com o termo assinado em mãos** e marque exatamente o que a
pessoa marcou. Fica só no banco: o repositório do Radar é público. A linha que sai na arte é montada pelo Radar ("Ana, contadora ·
CRC-SC 000000"; sem registro, "Ana · Departamento Pessoal"). Pessoa que está numa peça não é excluída: desmarque "Ativa". O termo é
conferido no selo da semana, ao marcar como pronta e ao aprovar (no dia da peça) e de novo antes de publicar, copiar ou baixar
(no dia de hoje): revogado ou vencido, a peça não sai. A lâmina aprovada só aparece na peça agendada com o termo valendo no dia
dela; na peça à mão, só em "Baixar as lâminas", depois dessa conferência; o leitor não vê foto nem lâmina.

**Sócio(a) da Artecon** (v0.28.0; só o administrador marca, o editor vê a caixa desabilitada). Os sócios da empresa não assinam o
termo: marque **"Sócio(a) da Artecon"** no cadastro da pessoa (no fieldset "Situação"). Com a marca, o Radar não confere as datas,
os canais e as finalidades do termo de uso de imagem nem o termo do corretor de vídeo, e a pessoa aparece com o selo **"Sócio(a) —
termos dispensados"** (no cadastro, no dia da semana e em "Quem aparece"); o aviso "sem o termo novo, que cita o corretor de vídeo"
não aparece para ela no reel. **Continuam valendo:** "Ativa" (para tirar o(a) sócio(a) das próximas peças e dos vídeos, desmarque
"Ativa"; para sócio(a), a data em "Revogado em" não conta), a idade (menor de idade: os termos continuam exigidos, e o selo diz
"Sócio(a), menor de idade: termos exigidos"), estar marcado(a) em "Quem aparece" e, no reel, as **quatro declarações** do envio.
**Marcar** pede confirmação ("Marcar como sócio(a) da Artecon?"): marque só quem é sócio(a) da empresa. Se a pessoa tem data em
"Revogado em", a pergunta avisa que, para sócio(a), a revogação não vale e que as peças e os vídeos com ela podem sair; o mesmo aviso
aparece quando a data é preenchida em quem já é sócio(a). **Tirar a marca** também pede confirmação: a pessoa volta a precisar dos
dois termos, e sem eles as peças com ela não ficam prontas nem saem, e o vídeo do corretor com ela é apagado na limpeza do dia
seguinte. O sobrenome no texto continua barrado como para todos (o recado fala do "Nome na peça" do cadastro, não do termo), e o
"Excluir" e a lista de peças publicadas da pessoa inativa falam de "Ativa", não do prazo do termo. Marcar e desmarcar fica no
Histórico ("socio: false → true"), sem o nome.

**Quando o termo é revogado (ou a pessoa sai da equipe).** Marcar a data em "revogado" impede as próximas publicações, mas **não
apaga nada**: o Radar não apaga sozinho foto, lâmina nem post (nem a faxina das imagens, nem a reversão). Só os vídeos dos reels
(v0.22.0) têm prazo de guarda: os do corretor e os textos deles saem sozinhos na limpeza do dia seguinte ("Corretor de vídeo do
reel", item 10), e a tela de Pessoas e termos lista as peças publicadas com a pessoa, com os links. No mesmo dia, o administrador:
1. nas peças **publicadas** com a pessoa, se o combinado for tirar do ar: "Excluir do Instagram/Facebook" (na peça agendada) ou
   apague o post direto na rede (na peça à mão);
2. nas peças **ainda não publicadas**: "Desfazer aprovação" (se aprovada), "Tirar" cada foto dela, desmarque a pessoa e salve; a
   foto e a lâmina que ninguém mais usa são apagadas pela faxina do robô no dia seguinte. **No reel, desmarcar não tira a pessoa do
   vídeo**: o Radar guarda quem estava marcado quando a gravação foi enviada, continua recusando o vídeo (a prévia fecha, a peça não
   fica pronta) e a limpeza do dia seguinte apaga os clipes, a transcrição, o vídeo corrigido e os textos dele; para o reel sair,
   **descarte a gravação** e grave de novo sem a pessoa;
3. o que sobra (as lâminas das peças publicadas e a cópia da lâmina nos envios), liste no SQL Editor, trocando o 7 pelo número da
   pessoa (a consulta `select id, nome_na_peca from radar_pessoas` mostra o número):
   `select p.data, p.situacao, p.artes, e.canal, e.situacao, e.imagem_url from radar_pauta_pecas p left join radar_redes_envios e
   on e.peca_id = p.id where 7 = any(p.pessoas) order by p.data;` — e apague em Supabase → Storage → `radar-pauta` os arquivos da
   coluna `imagem_url` (o post já publicado continua na rede até o passo 1).

**2. Importar o calendário** (editor e administrador): "Importar o calendário (CSV)", com o arquivo do plano de publicações (as
colunas `data;dia;semana;tipo;formato;assunto;quem_aparece;objetivo;observacao`, separadas por ponto e vírgula ou vírgula, do
Excel ou não; data no formato 26/10/2026). A tela confere o arquivo inteiro antes de gravar e mostra **todos os erros de uma vez**,
com a linha da planilha (data errada, dia da semana que não bate, tipo ou formato desconhecido, data repetida, texto comprido
demais). Sem erro, a prévia diz o que é novo, o que muda, o que fica igual e o que é mantido; "Gravar" grava. Importar de novo não
duplica: a peça que já saiu de "Planejada" não muda. As pessoas **não** são ligadas sozinhas: a coluna `quem_aparece` vira só um
lembrete na peça. A hora de cada peça nova é a de Configurações → Pauta (`hora_padrao`). O CSV e os `.md` do plano de publicações
têm nomes da equipe: **nunca vão para o GitHub** (o `.gitignore` barra qualquer CSV novo e os `.md` do plano, e o workflow
`radar-repositorio.yml` confere em todo envio; mas o envio pelo site do GitHub não passa pelo `.gitignore`, e o aviso chega depois
que o arquivo já ficou público).

**2a. Peça nova num dia vazio** (v0.28.0; só o administrador): na semana, cada dia que ainda não tem peça, de hoje em diante (de
Brasília), mostra **"+ Nova peça"**. O formulário curto pede o **tipo** e o **formato** (os mesmos da importação), o **assunto**
(obrigatório) e, se quiser, o objetivo, "quem aparece" (só lembrete, como na importação) e a observação; "Criar a peça" grava e abre a
peça, que segue como qualquer outra: roteiro, "Quem aparece" (as pessoas são marcadas na própria peça), fotos e, no reel, o quadro
"Corretor de vídeo". A peça nasce **planejada**, na hora de Configurações → Pauta (`hora_padrao`; se for para hoje, confira a hora
na peça), e **não publica nem agenda nada**: sai só depois de pronta e aprovada pelo administrador. O banco confere tudo de novo: só
o administrador, o dia sem peça nenhuma (a cancelada também ocupa o dia: use "Reabrir") e de hoje em diante. O editor continua
importando o calendário (CSV), como antes. **Importar o calendário depois:** a peça criada à mão é tratada como qualquer outra do
mesmo dia — se o CSV tiver uma linha para esse dia e a peça ainda estiver **planejada**, ela recebe o tipo, o formato, o assunto,
"quem aparece", o objetivo e a observação do arquivo (a hora fica; a prévia mostra "alterada" antes de gravar); se ela já entrou em
produção (ou está pronta, aprovada ou cancelada), fica como está ("mantida"). A importação nunca cria um segundo dia igual nem apaga
peça. Se a prévia de uma importação estiver aberta, ela fecha (sem gravar nada) quando se abre a "+ Nova peça": a prévia foi
calculada antes da peça nova e diria "nova" para o dia dela; depois de criar a peça, escolha o arquivo de novo.

**3. Preparar a peça** ("Abrir", na semana; editor e administrador):
- **Fotos**, no alto: cada foto vira 1080×1350 (corte no centro), enviada uma de cada vez, até 10. A foto do iPhone em HEIC
  fica de fora, com o recado de como trocar (Ajustes → Câmera → Formatos → Mais compatível, ou captura de tela), dado no fim, junto
  com o que aconteceu com as outras; a foto pequena recebe o aviso de que pode ficar sem nitidez. ↑, ↓ e "Tirar" mudam a ordem.
- **Quem aparece:** as pessoas ativas, com o selo do termo (vale no dia da peça ou não).
- **Informações conferidas:** cada fato que a peça usa (número, data, prazo, valor, norma), com a **fonte oficial**. O boletim
  pago da ITC não serve de fonte. Na Agenda da semana (domingo), **"Calcular a agenda da semana"** traz os vencimentos de segunda a
  domingo seguintes (até a v0.29.0, de segunda a sexta; no sábado e no domingo só vence o que não muda de data, como a DEFIS e a
  DASN-SIMEI em alguns anos), das regras das Configurações (sem as obrigações com `"redes": false`, como o honorário contábil), já como
  informações conferidas: confira cada data antes de aprovar. A fonte vem da obrigação (a chave `"fonte"` na agenda de
  obrigações); sem ela, fica **em branco**, e a peça só fica pronta depois que alguém escreve a fonte oficial em que conferiu (a
  regra das Configurações não é fonte, e o texto da fonte vai ao ar no "Fonte: …" da legenda). "(conferir)" no texto ou na fonte
  também trava.
- **Gerar com IA** (opcional; abaixo) e os **textos:** chamada e apoio da arte, cartões (carrossel), roteiro (reel, colado à
  mão), as legendas do Instagram e do Facebook (com contador de caracteres e o botão "Pôr a identificação legal e as hashtags").
  No roteiro, cole a fala e o texto na tela (a tabela "Tempo | Fala | Texto na tela" do plano serve; desde a v0.22.0, a coluna
  "Fala" é o que o corretor de vídeo compara com a gravação): as marcações de tempo ("0 a 3 s", "cerca de 44 segundos", "0:15",
  "110 palavras") não contam como número; as notas de produção (o dia da gravação, a cena) ficam de fora, porque o número delas
  pediria informação conferida.
- Os **marcadores dos modelos do plano** entre chaves (`{formação}`, `{ano de entrada}`, `{frase da pessoa}`…) precisam virar texto:
  esquecido em qualquer texto que vai ao ar, a peça não fica pronta.
- **Plano** (assunto, objetivo, observação e quem aparece, do CSV): só referência, não vai ao ar.
- **Salvar** grava só o que mudou. Se outra pessoa salvou a peça antes, a tela avisa "alterada em outra tela" e nada é gravado
  por cima.

A peça muda de situação assim: **Planejada** → **Em produção** (sozinha, quando algo que vai ao ar muda) → **Pronta** ("Salvar e
marcar como pronta") → **Aprovada** (só o administrador). Pronta que muda volta para Em produção ("Voltar para produção" também).
"Cancelar a peça" e "Reabrir" valem até a aprovação.

**4. A arte** é desenhada na própria tela, em 1080×1350, com a margem de 72 px nas laterais: a foto em página cheia (Quem cuida,
Bastidor, Captação, Data com a equipe), com o selo, a chamada, o apoio e a linha de cada pessoa; ou o fundo azul-marinho com o
texto (imagem, cartões do carrossel, agenda da semana). No carrossel, a capa e uma lâmina por cartão; no carrossel de fotos, uma
lâmina por foto. Embaixo vai a faixa branca com a **identificação legal** das Configurações (empresa, CNPJ e CRC), em letra de **pelo
menos 28 px de altura** (a altura medida da letra maiúscula), em até 3 linhas quebradas nos " · ": se não couber, a peça não é
aprovada. Até 6 linhas de pessoas: com mais, as pessoas sem registro da mesma área dividem a linha ("Ana, Bruno e Carla ·
Departamento Pessoal"); se ainda não couber, e também no vencimento longo da agenda, a tela avisa o que ficou de fora. A arte da
notícia não mudou (faixa de 24 px). Os 28 px estão como altura da letra: se o combinado for o tamanho da fonte, muda só um número
(`FAIXA_LEGAL`, em `radar-pauta.js`).

**5. Conferir e marcar como pronta.** "Salvar e marcar como pronta" (ou só "Conferir o que falta") mostra numa lista **tudo** o
que falta resolver: a peça sem o que o formato pede (foto, pessoa, 2 a 10 fotos no carrossel de fotos, um cartão a mais que as
fotos, 2 a 9 cartões, roteiro, informações conferidas na agenda), legenda sem a identificação legal (CNPJ e CRC das Configurações precisam estar preenchidos),
[VERIFICAR], `{confirmar}` ou outro marcador entre chaves, informação conferida sem fonte ou com fonte do boletim pago, frase igual
à do boletim pago, número que não está nas informações conferidas (mostrado como está escrito, com o que fazer: acrescentar em
Informações conferidas, com a fonte; o registro no CRC da pessoa marcada, os telefones do Fale Conosco e os `fatos_fixos` das
Configurações valem sem isso), termo de imagem que não vale, nome de pessoa cadastrada que aparece no texto sem estar marcada (com
ou sem acento, em caixa alta, colado do Mac; em minúsculas, como palavra comum, não), sobrenome que o termo não autoriza,
"contador(a)", "técnico(a)" ou "especialista" perto de quem não tem registro (em qualquer caixa), e os
termos que a publicidade contábil evita na Pauta (preço, desconto, grátis, brinde, promoção, promessa, comparação com outros
escritórios ou contadores, superlativo, apelo ao medo; lista inicial, a confirmar com o contador responsável; o desconto da folha,
perto de INSS, IRRF, parcela, 13º, salário ou vale-transporte, não trava). Na Agenda da semana em Imagem 4:5, a lista desenhada na
lâmina passa pelas mesmas travas (marcas, chaves, nomes e termos). Em amarelo, o que é
só para conferir (texto cortado na arte; na Data com a equipe, dado sensível). O administrador vê no alto da Pauta a lista
**"Prontas para aprovar"**.

**6. Aprovar** (só o administrador; "Aprovar a peça", na peça pronta): os canais (os que têm legenda); **como sai** ("Agendar para
sáb, 31/10/2026, às 09:30", só imagem única: Imagem 4:5 e Foto; ou "Vou publicar à mão"; carrossel e reel saem à mão nesta
versão); e as conferências obrigatórias: "Conferi: nas fotos e nos textos só aparecem as pessoas marcadas (ou ninguém)" (em toda
peça: o nome escrito de um jeito que a lista não reconhece só quem aprova vê), "Conferi as datas da agenda" (Agenda da semana) e,
se um envio anterior caiu no meio ou se uma aprovação à mão foi
desfeita, "Conferi no Instagram e no Facebook: não saiu". Os canais marcados ficam guardados na aprovação: à mão, só eles são
copiados e registrados. A tela confere tudo de novo, guarda as lâminas desenhadas e o banco aprova: **vai ao ar exatamente o que
está na tela**. A hora marcada no passado vale se estiver dentro da janela (Configurações → Pauta → `janela_horas`, 6 horas): a
peça sai na próxima rodada; mais que isso, mude a hora. A Agenda da semana não é aprovada depois da segunda-feira. Aprovada, a peça
não se edita: para mudar, **"Desfazer aprovação"** (editor ou administrador; não dá enquanto está publicando, nem depois que saiu
numa rede: exclua da rede antes; na aprovada à mão, marque antes "Conferi no Instagram e no Facebook: não foi postada à mão" — se
foi postada, registre o link em vez de desfazer).

**7. Publicação sozinha** (modo agendar). A agenda do banco (`sql/radar-redes-agenda.sql`, item 7 de "Instagram e Facebook pela API
da Meta") roda de 5 em 5 minutos e pede à função `radar-redes` cada peça cuja hora chegou. Antes de qualquer coisa ir à Meta, o
banco confere de novo: a peça continua aprovada como estava, o termo de imagem vale **hoje**, não passou da janela, a Agenda da
semana não ficou velha e não há [VERIFICAR]. A foto vai ao armazenamento privado e a Meta recebe um link que vale 10 minutos. Se a
função não responder, a agenda tenta até 3 vezes, de 10 em 10 minutos; depois disso, ou com qualquer problema, a publicação vira
"não saiu", com o motivo, e **nunca sai atrasada sozinha**. Na peça, cada canal mostra "agendada para…", "publicando", "publicada"
(com o link do post) ou "não saiu". O administrador tem:
- **"Publicar agora"**: só remarca a hora para agora e confere tudo de novo. Com a agenda rodando, sai em até 5 minutos; sem ela,
  a tela chama a função na hora, um canal depois do outro;
- **"Tentar de novo"** (publicação que não saiu): pede antes a caixa "Conferi no Instagram e no Facebook: não saiu", para nunca
  publicar duas vezes;
- **"Não publicar neste canal"** (na peça e no quadro "Não saíram"), na publicação que não saiu ou que ainda espera a hora:
  cancela só aquele canal, mesmo com o outro já publicado; a peça continua aprovada e o aviso do robô fecha. Com todos os canais
  cancelados, a semana e a peça mostram "Aprovada, sem canal (não vai sair)": para publicar, Desfazer aprovação e aprove de novo;
- **"Cancelar"**, na publicação parada em "publicando" há mais de 10 minutos (confira na rede se saiu antes), e **"Excluir do
  Instagram/Facebook"**, na publicada.

Para **pausar** a agenda sem SQL: Configurações → Pauta → `"agenda_ligada": false` (o que está agendado espera; sai só com
"Publicar agora"). Desligada, não instalada ou pausada no pg_cron, o administrador vê o aviso no alto da Pauta e na confirmação da
aprovação.

**8. Publicar à mão** (carrossel, carrossel de fotos, reel, ou quando o administrador escolheu): na peça aprovada, "Baixar as
lâminas" (`pauta-AAAA-MM-DD-1.jpg`…; no reel, desde a v0.22.0, "Baixar o vídeo aprovado", do corretor de vídeo), "Copiar legenda do
Instagram/Facebook" (só dos canais aprovados) e "Copiar roteiro" (com a identificação legal no último quadro). O banco confere antes a versão aprovada, o canal e o termo de cada pessoa **hoje**. Se o
navegador não deixar copiar (no iPhone pode acontecer), o texto aprovado aparece logo abaixo para selecionar e copiar: não
redigite. Depois de postar, "Registrar a
publicação": o link do post (`https://www.instagram.com/…`, `https://www.facebook.com/…` ou `https://fb.watch/…`) e o dia
(entre a aprovação e hoje). O carrossel pela API e o roteiro do reel pela IA ficam para a v0.21.1.

**9. Quando não sai.** O que não saiu (com erro, parado em "publicando" há mais de 15 minutos ou agendado com a hora passada há
mais de 20 minutos) aparece no **Painel** ("Publicações da Pauta que não saíram") e no quadro **"Não saíram"**, no alto da Pauta,
com o motivo, "Abrir" e (no que não saiu ou espera a hora) "Não publicar neste canal". O robô de avisos (depois de cada coleta,
de 6 em 6 horas) abre **um aviso só** no GitHub, "Radar: publicação agendada não saiu", com a quantidade e a data, o canal e o
número da mais antiga (nunca assunto, nome, legenda ou o texto do erro, porque o repositório é público). O corpo do aviso não é
editado; v0.22.0: cada publicação **nova** que não sai, com o aviso já aberto, ganha **um comentário** nele (um e-mail, com o mesmo
tanto de informação) — antes, um erro antigo deixado sem resolver calava as falhas seguintes. O aviso fecha sozinho quando
nada mais está parado. Nos 2 primeiros fins de semana pela agenda (a partir de 31/10), abra a Pauta por volta das 09h35: o aviso
por e-mail pode levar horas.

**10. Gerar com IA da peça** (editor e administrador; a peça precisa estar salva). A IA (a mesma `radar-ia`, ação `peca`) sugere a
chamada e o apoio, as legendas e os cartões do carrossel a partir do tipo, do formato, do plano e das informações conferidas.
**Os nomes da equipe não vão à IA**: a pessoa marcada vai como `{PESSOA1}` (com a área e a categoria; o número do CRC nunca vai), e
o nome de qualquer outra pessoa cadastrada, ou escrito com maiúscula no "quem aparece" de **qualquer** peça do calendário (quem
ainda não tem termo e é citado no assunto de outra peça), vira "uma pessoa da equipe" (também nas informações conferidas). O que
sobra: o nome que não está cadastrado nem em nenhum "quem aparece" não é reconhecido; não o escreva no assunto, no objetivo, na
observação nem nas informações conferidas. Não vão foto, link, CNPJ, telefone nem o boletim. O fato que não está nas informações conferidas volta marcado com
[VERIFICAR], e a sugestão mostra o que falta conferir e os avisos (termos, "contador" para quem não tem registro, termo de imagem).
**"Usar a sugestão"** põe os textos nos campos (com o nome na peça no lugar de `{PESSOA1}` e, nas legendas, a fonte, a identificação
legal e as hashtags), **sem salvar**: o que se aprova é o texto salvo. Se as pessoas, o tipo ou o formato mudaram, gere de novo. A
senha é pedida a partir da 2ª consulta da mesma peça, e o consumo entra no limite mensal como "gerar". Não gera para dia de
notícia (use o kit das redes do assunto), reel (roteiro à mão nesta versão), Story ou "Sem post", nem para a Agenda da semana sem
as informações conferidas.

**11. Configurações → Pauta e agenda automática:** `agenda_ligada` (true ou false), `hora_padrao` (a hora de Brasília das peças
novas, da importação e da "+ Nova peça", "09:30"), `janela_horas` (de 1 a 48; padrão 6), `hashtags` (as fixas, até 3, como "#Contabilidade" e "#Palhoça") e
`fatos_fixos` (opcional: os fatos da Artecon que valem em toda peça, cada um com a fonte, como `[{"informacao": "A Artecon atende
empresas desde 1984", "fonte": "Contrato social"}]`; os números deles não pedem informação conferida). Na
agenda de obrigações, `"redes": false` tira a obrigação da Agenda da semana das redes e `"fonte"` é a fonte oficial da regra de
vencimento, que vai junto na informação conferida. Desde a v0.22.0, **"Preencher fontes oficiais"** (no mesmo bloco, só o
administrador) põe a fonte conferida pelo Radar (norma, artigo e link oficial, abertos em 12/10/2026) nas obrigações das redes que
estão sem fonte, pelo nome, e salva; não muda regra, dia, ajuste, nome nem fonte já escrita, e a obrigação que não está na tabela
aparece para conferir à mão.

**Limites desta versão.** Uma peça por dia (o calendário não tem dia repetido). Story e "Sem post no feed" ficam fora da Pauta. O link
assinado do armazenamento privado segue o código do Supabase; que a Meta aceita esse link (ele termina em `?token=…`) não foi
conferido na documentação da Meta: confere-se na primeira peça pela agenda, com o administrador acompanhando às 09:30 (a reserva é o modo à mão). Cada foto e cada lâmina aprovada ocupa no
banco até cerca de 450 KB: confira o tamanho em Supabase → Usage de vez em quando. A lista de termos que travam na Pauta inclui
palavras que também servem para informar ("garante", "ganhe", "definitivo", "100%", "a maioria") e precisa da confirmação do
contador responsável. O leitor vê o plano e as legendas, mas não as fotos nem as lâminas. A chave do robô (segredo do GitHub
Actions) não lê as **tabelas** das pessoas, das peças, das fotos, das lâminas, das legendas dos envios nem a auditoria; **os arquivos
do armazenamento ela lê**: é a chave `service_role`, que no Supabase alcança todos os buckets privados (`radar-pauta`, com as lâminas
aprovadas, e `radar-videos`, com os clipes e as transcrições) — por isso os pacotes dos robôs públicos vão com versão exata e hash
(`robo/requirements.txt`, v0.22.0) e a chave nunca sai dos segredos do GitHub. Nada é apagado sozinho (foto,
lâmina, arquivo no armazenamento privado nem post): veja "Quando o termo é revogado", no item 1. As recusas do banco na Pauta vêm com os códigos RADAR159 a RADAR176 (por
exemplo, RADAR161 "alterada depois que a tela foi aberta", RADAR162 "aprovada não muda", RADAR165 "há pontos a resolver",
RADAR166 "falta marcar uma conferência", RADAR167 "hora fora do permitido", RADAR170 "já saiu numa rede", RADAR174 "pessoa em
uso", RADAR176 "pessoa ou foto que não está cadastrada, repetida ou foi apagada").

### Cronograma de publicações da Pauta (v0.27.0)

No alto da semana da **Pauta**, o quadro **"Cronograma de publicações"** mostra lado a lado (no celular, um embaixo do outro) a
semana que está na tela e o mês dela. Cada linha tem o **mínimo** e o que já foi **feito**:

| Linha | Mínimo | Feito |
|---|---|---|
| Posts no feed | as peças de imagem, foto ou carrossel do plano da Pauta no período, com os dias de notícia (sem as canceladas) | a peça publicada no Instagram ou no Facebook (pela agenda ou registrada à mão), no dia dela na Pauta; no dia de notícia, uma notícia do Radar publicada nas redes (a mesma nas duas redes conta uma vez) |
| Reels | os reels do plano no período | o reel publicado numa das redes |
| Captação de clientes | a peça de captação do plano (só aparece quando o período tem uma) | a peça publicada numa das redes |
| Notícias do Radar (alta) | as notícias de relevância alta que a busca do Radar achou no período, cada fato uma vez | as que já estão no site, publicadas em qualquer dia |

- **Vermelho:** fica vermelho o que já devia ter saído até ontem e não saiu. No período que já passou, a linha diz "faltou 1" ou
  "faltaram N" e fica vermelha em tudo o que ficou abaixo do mínimo; na semana e no mês em andamento, só conta o que já passou do dia
  ("1 em atraso"; a semana não começa toda vermelha na segunda-feira); o período que ainda não começou nunca fica vermelho.
- **O mês:** na semana de hoje, o mês é o de hoje; nas outras semanas, o da maior parte da semana. "← Semana anterior" e "Próxima
  semana →" trocam a semana e o mês do quadro juntos.
- **O que não entra nas notícias:** as repetições do mesmo fato, o texto oficial colado à mão, a notícia que já chegou velha, a que a IA
  rebaixou e a notícia **ignorada na triagem enquanto ainda era alta** (o quadro avisa quantas foram). A que só desceu para baixa por
  ficar velha na fila continua contando, mesmo se for ignorada depois (o robô também ignora essa sozinho).
- **Privacidade:** o quadro mostra só números. Não lê pessoas, quem aparece, fotos, lâminas nem títulos; do boletim da ITC, que é pago,
  só entra na conta (nunca o título, o texto ou o link). O leitor vê o mesmo quadro que o administrador e o editor.
- **Limites:** os números da semana em curso mudam durante o dia (a nota da IA chega depois da busca); a notícia excluída do site sai
  do feito; o mesmo fato achado em duas capturas principais que não foram juntadas conta duas vezes; o fato achado de novo em outra
  semana ou outro mês conta em cada um; cada leitura vai até 1.000 registros (passando disso, o quadro avisa que algum número pode
  estar abaixo do real); stories e o Informativo Mensal ficam de fora; não há meta fixa por mês (o mínimo é o plano e o que a busca
  achou). Se a leitura falhar, aparece um aviso amarelo e a semana continua na tela.

### Corretor de vídeo do reel (v0.22.0)

O reel da Pauta passa pelo **corretor de vídeo**: a equipe grava no celular e envia pela peça; um robô transcreve, compara com o
roteiro, corta, limpa o som, grava a legenda e a cartela e confere o arquivo; o administrador ouve, ajusta e aprova; o vídeo aprovado
é baixado e postado à mão. Quem edita (editor e administrador) vê o quadro **"Corretor de vídeo"** na peça reel; o leitor não vê.

**1. Gravar (orientação para a equipe).**
- Celular **na vertical**, em **1080p a 30 quadros por segundo**, com o **Vídeo HDR desligado** (no iPhone: Ajustes → Câmera →
  Gravar Vídeo). Enquadre do peito para cima, com o rosto no terço de cima da tela: a legenda entra na altura do peito.
- Lugar silencioso: **sem música, rádio ou TV** (nem ao longe), sem ventilador ou ar-condicionado barulhento perto; o microfone do
  celular livre e a até 1 metro da boca.
- Fundo: **sem tela de computador, documento, cliente ou quadro de avisos**; no vídeo, só as pessoas marcadas na peça.
- Grave **por bloco** do roteiro (uma ou duas frases por clipe): 1 segundo de silêncio antes de falar e 1 depois de terminar. Errou,
  pare e grave o bloco de novo; **apague as tomadas ruins** antes de enviar. O corretor recebe de 1 a 12 clipes, já na ordem, e
  soma até 120 s de gravação.
- Fale o roteiro **como está escrito**, com os números, as datas e os termos (é o que o corretor compara). Trocar uma palavra comum
  não trava; número, data ou termo diferente pede regravar.
- **Não edite** no celular (sem filtro, música, legenda ou corte) e envie os arquivos originais da câmera (MP4 ou MOV).
- **Guarde os clipes no celular até o relatório dizer "Vídeo corrigido pronto"** (em alguns minutos): o envio novo substitui todos
  os clipes, e quem apagou cedo regrava tudo por causa de um bloco só; com "Precisa regravar", regrave só o bloco errado e mande os
  outros como estão. Então, **no mesmo dia do envio** (o termo pede), **apague do celular e da nuvem pessoal** (inclusive da lixeira,
  "Apagados recentemente") e marque "Apaguei" (o botão fica em destaque quando o vídeo fica pronto).

**2. Enviar** (Pauta → peça reel → quadro "Corretor de vídeo"). A **"Fala para conferência"** mostra o que o corretor compara: a
coluna "Fala" da tabela do plano (`Tempo | Fala | Texto na tela`, sem as aspas), as linhas "… — Fala: …" do kit ou, sem nenhum dos
dois, o roteiro inteiro (com o aviso para conferir). "Na tela", "Tarja", "Gancho" e "Chamada final" nunca entram. Escolha os clipes
(↑ e ↓ mudam a ordem), quem fala, as 4 declarações ("só aparecem as pessoas marcadas", "sem tela, documento ou cliente ao fundo",
"só a voz", "a fala para conferência é o que foi gravado") e, se a peça tiver o **texto do gancho** preenchido, se ele aparece de 0 a
3 s; a tela mostra as linhas da cartela. "Enviar a gravação": o banco confere tudo **antes** de qualquer arquivo sair (a fala no
roteiro, palavra por palavra e na ordem; o boletim pago; o termo de cada pessoa marcada, com o termo novo do corretor; menor de
idade; a cartela; os clipes; a cota do mês — com a duração que o navegador leu dos clipes, a gravação tem de caber no que sobra do
mês, que o quadro mostra antes —; e, na tela, os termos que a publicidade contábil não usa na fala e no texto do gancho) e só então
os clipes sobem, um de cada vez, direto do navegador ao armazenamento privado
`radar-videos`, em pedaços de 6 MB. No celular, **não feche nem bloqueie a tela até 100%** (a tela pede para ficar acesa); se a
internet cair, reabra a peça e escolha os mesmos arquivos: o envio continua de onde parou (só quem começou o envio, ou o
administrador, continua; os outros podem descartá-lo). Enviar de novo substitui a gravação anterior **só quando os clipes da nova
chegam**: o envio que para no meio ou é abandonado não leva junto o vídeo que já estava pronto (enquanto ele espera os arquivos, a peça
pede "termine de enviar a gravação" — ou descarte o envio — antes de aprovar).

**3. O que o robô faz** (repositório privado `radar-video`, acionado na hora pela função `radar-video`; o robô trata um pedido por
execução e, ao terminar, a função o aciona de novo se ainda há pedido na fila — o envio que chegou enquanto ele trabalhava não espera;
a reserva da agenda, de 10 em 10 minutos, aciona se o GitHub não atender — até 3 vezes por pedido: sem o robô pegar, o pedido para
com o erro "robo_nao_pegou", um aviso só na peça, e o administrador confere a `RADAR_VIDEO_ROBO_CHAVE`, a `RADAR_VIDEO_URL` e o
`RADAR_VIDEO_COMMIT` do repositório privado e o `RADAR_VIDEO_GITHUB_TOKEN` do Supabase, e usa "Tentar de novo"; com o token do GitHub
vencido, é esse aviso que aparece, uns 30 a 40 minutos depois do envio. O próprio workflow também roda às 10h47 e às 16h47 dos dias
úteis e pega o que ainda estiver na fila — por exemplo, se a agenda do banco parar). Antes de baixar os clipes, o pedido confere de
novo as pessoas do vídeo (as marcadas na peça e as que estavam marcadas no envio: o termo de hoje, a idade, quem fala marcada): a
pessoa que revogou o termo depois do envio não passa mais pelo robô nem pela Azure (erro "termo"). Um pedido de cada vez, na ordem
da fila:
- confere cada clipe como **entrada não confiável** (MP4 ou MOV de câmera, com imagem e som, de pé, até o tamanho declarado; soma
  até 120 s) e recusa com o motivo;
- transcreve pela **Azure gratuita** (o recurso F0 `artecon-voz`, o mesmo da Agenda, pelo Speech SDK, em pt-BR, com a lista de
  termos do glossário e os nomes do roteiro). O F0 atende **um pedido por vez** e é dividido com o WhatsApp da Agenda: ocupado, o
  robô espera e tenta de novo por até uns 10 minutos e, se não der, para com "Transcrição ocupada; tente de novo";
- compara a fala com o roteiro **só por código, sem IA** (números, datas, valores e termos pelo sentido: "trinta de outubro" é
  "30/10", "cinquenta mil reais" é "R$ 50.000,00", "é social" é "eSocial") e manda o **relatório parcial**;
- **cortes:** o começo (fica 0,12 s antes da 1ª palavra) e o fim (0,45 s depois da última) de cada clipe; a pausa acima de 1,0 s
  dentro da frase fica com 0,30 s, e acima de 0,8 s entre frases, com 0,40 s (`pausa_max_s` e `pausa_bloco_s`); as hesitações
  ("ãh", "hum", "ééé") e a voz sem palavra entre duas palavras seguidas do roteiro. Repetição e falso início viram **sugestão** (não
  saem sozinhos). Cada corte no meio da fala é listado no relatório;
- **som:** filtro de grave, redução de ruído, compressor e volume de -14 LUFS (`lufs`), sem cortar a última palavra;
- **imagem:** 1080×1920 (9:16, sem distorcer), 30 quadros por segundo, cor leve; o HDR é convertido;
- **legenda** gravada no vídeo, em DM Sans branca sobre a caixa azul-marinho, dentro da área livre do Instagram, em blocos de até 2
  linhas, **na grafia e na pontuação do roteiro** nos trechos alinhados (fora deles, como a Azure escreveu); o **texto do gancho**
  de 0 a 3 s, acima da legenda;
- **cartela final** (3 s, `cartela_s`): o logotipo, a identificação legal das Configurações, a linha de quem fala (com o CRC, de
  Pessoas e termos) e o `cartela_extra`, em letra de pelo menos 28 px de altura; se não couber, para com o erro (nunca corta com
  "…");
- **confere a saída:** MP4 H.264 1080×1920 a 30/1 e AAC 48 kHz estéreo, o índice no começo do arquivo, sem lista de edição, **sem a
  localização nem a marca do celular**, volume dentro de 1 LU do alvo, de 3 a 90 s e até 300 MB; tira 4 quadros e entrega.
O tempo no repositório privado (2 processadores) ainda não foi medido: pela conta, 3 a 6 minutos, mais a espera pela vaga da Azure.

**4. O que o corretor NÃO corrige.** Nenhuma palavra é trocada, acrescentada ou inventada, e **"um", "uma", "e" e "é" nunca saem**
(nem palavra alinhada ao roteiro). **Precisa regravar:** número, data, mês, ano, valor, ordinal ou termo do glossário diferente do
roteiro (trocado, faltando ou a mais), termo que a publicidade contábil não usa na fala e frase do boletim pago. Não cria nem imita
rosto ou voz, não põe música, não tira nada do fundo e não conserta imagem tremida, escura ou fora de foco, nem a luz ou o
enquadramento diferentes de um clipe para o outro: isso se resolve gravando de novo.

**5. Relatório e prévia.** A peça mostra a situação ("Na fila do corretor", "O corretor está trabalhando", "Vídeo corrigido pronto",
"Precisa regravar", "O corretor parou") e se atualiza sozinha enquanto o robô trabalha. O relatório, com os tempos do vídeo corrigido:
o que precisa regravar (o que foi dito e o que o roteiro diz), a duração (acima do limite de 45 s, `duracao_max_s`, a aprovação pede
confirmação; acima de 90 s, não aprova), os cortes, as sugestões, as trocas de grafia, a legenda, o som, a imagem e **4 quadros**
para conferir o fundo, as pessoas e a posição da legenda. A prévia abre por um link de **10 minutos** (vencido, a tela pede outro),
e quem viu fica registrado. Quando o robô para, a peça diz o motivo em português (por exemplo: um clipe sem som, deitado ou que não
é de câmera; "Transcrição ocupada; tente de novo"; a cota grátis da Azure do mês acabou; o limite de minutos do Radar no mês; a
cartela não coube — "Tentar de novo" refaz a cartela com a Assinatura e Pessoas e termos de hoje —; o vídeo corrigido passou do
limite de tamanho de arquivo do armazenamento) e, depois de corrigir, **"Tentar de novo"**. A prévia só abre com as pessoas do vídeo
podendo aparecer nele hoje (o termo revogado, o do corretor retirado ou a pessoa marcada menor fecham a prévia na hora). Falha do armazenamento, da rede ou do GitHub volta à fila sozinha,
até 3 vezes.

**6. Ajustes do administrador** (depois de ouvir a prévia): "Manter este trecho" (num corte no meio da fala); **"A transcrição
errou (vale o roteiro)"**, quando a pessoa falou certo e a Azure ouviu errado (a legenda daquele trecho passa a usar o roteiro; se a
pessoa falou errado, regrave); **editar a legenda** palavra por palavra, com o mesmo número de palavras, cada uma a do roteiro ou
parecida com a ouvida, sem mudar número, data, mês ou termo (o robô recusa o resto e lista); legenda compacta (1 linha, quando a
legenda cobre a boca); sem o texto do gancho; e refazer a cartela com as Configurações e Pessoas e termos de hoje. Tudo vai num
pedido só, e o vídeo é montado de novo **sem transcrever de novo** (não gasta a cota) e **sem mudar o áudio**. As marcas apontam o
trecho pelo que ele é — a divergência pelo instante e pelo texto dela, o corte pelo lugar na gravação —, e não pela posição na
lista: a montagem alinha de novo com as Configurações de hoje (uma variante ou um termo novo no glossário tiram uma divergência da
lista; "A transcrição errou" pode criar um corte), e a marca que não confere com o relatório novo fica sem efeito (a divergência volta
a pedir regravar): confira o relatório depois de cada ajuste. "Conferir com o roteiro novo" (quando o roteiro mudou depois da
gravação e a fala continua valendo) e "Descartar" valem para editor e administrador; se a fala para conferência é a mesma (mudou
só o "Texto na tela", os tempos ou a tarja), o Radar só registra o roteiro novo: o vídeo e os ajustes continuam valendo, sem passar
pelo robô. O texto do gancho gravado é a cópia da chamada no envio, e o texto extra da cartela é o das Configurações na montagem: o
que está no vídeo passa pelas travas, e se a chamada ou o `cartela_extra` mudarem depois, a peça pede "Sem o texto do gancho" ou
"Refazer a cartela" (ou um envio novo).

**7. Aprovar, baixar e postar.** O reel só fica pronto com o vídeo corrigido pronto e conferido (o roteiro de quando foi gravado,
quem fala ainda marcada, a cartela de hoje, até 90 s). Na aprovação (só o administrador, modo "à mão"), a tela manda o hash do vídeo
que ele abriu na prévia e o banco confere com o vídeo pronto: a peça fica **amarrada a esse arquivo**. Ela pede "Conferi o vídeo: só
aparecem as pessoas marcadas; sem tela, documento ou cliente ao fundo; só a voz" e, se alguma pessoa marcada pediu no termo para ver a
peça antes, "A pessoa viu o vídeo final". Aprovado: **"Baixar o vídeo aprovado"** (`reel-AAAA-MM-DD.mp4`, link de 5 minutos; o
banco confere de novo o termo de hoje e o hash), poste no Instagram e no Facebook com a legenda copiada da peça (a capa se escolhe
no aplicativo), marque **"Apaguei do celular e da nuvem pessoal (depois de postar)"** (fica registrado quem apagou o vídeo final) e
registre o link. O registro do reel aprovado com esta versão sem o vídeo aprovado é recusado (RADAR317). "Desfazer aprovação" solta a amarra, e o vídeo pode mudar de novo.

**8. Configurações → Corretor de vídeo** (só o administrador): `glossario` (os termos que a legenda escreve sempre do mesmo jeito, de
1 a 200), `variantes` (como a transcrição erra cada termo, até 20 por termo: "é social" → eSocial), `duracao_max_s` (15 a 90; 45),
`pausa_max_s` (0,6 a 2; 1,0), `pausa_bloco_s` (0,4 a 2; 0,8), `lufs` (-24 a -9; -14), `cartela_s` (2 a 5; 3), `cartela_extra` (até
120 caracteres, como "Desde 1984 · (48) 3242-0530 · artecon.cnt.br"; os termos que a publicidade contábil não usa são recusados),
`limite_min_mes` (1 a 300; 30), `retencao_dias` (7 a 120; 30) e `retencao_publicado_dias` (0 a 365; 30). **"Testar o corretor de
vídeo"** confere o armazenamento privado (e o devolve a privado se alguém o abriu), o token do GitHub, o workflow do robô, a fila e os
minutos do mês, sem mostrar segredo.

**9. A cota da Azure.** O F0 dá **5 horas de transcrição por mês para o recurso inteiro**, divididas com o WhatsApp da Agenda (que se
limita a 270 minutos). Cada envio conta a duração de toda a gravação enviada (antes dos cortes); o ajuste não conta. O quadro do envio
mostra quanto sobra no mês, e o envio cuja gravação não cabe no que sobra é recusado antes de qualquer arquivo sair (quando o
navegador lê a duração dos clipes; senão, o robô confere). O Radar para sozinho em `limite_min_mes`: o padrão, **30 minutos**, é o que sobra dos 300 depois dos 270 da Agenda, e assim nenhum dos dois chega
à recusa da Azure. **Não aumente o `limite_min_mes` no F0** (acima de 30, o Radar pode gastar os minutos que a Agenda reservou, e o
WhatsApp dela passa a receber a recusa de cota da Azure antes do limite próprio), a não ser que a Agenda passe a reservar menos.
Passando da cota, a Azure recusa (não cobra). Para trocar pelo serviço pago (*fast transcription*, num recurso S0) sem mudar código:
cadastre no repositório privado os segredos `AZURE_FALA_MODO` = `rapido` e `AZURE_FALA_ENDPOINT` (o endereço do recurso), troque a
`AZURE_FALA_CHAVE` e, aí sim, aumente o `limite_min_mes` (até 300).

**10. Guarda, acesso e privacidade.**

| Dado | Onde | Quem vê | Até quando (a limpeza diária, 03h37) |
|---|---|---|---|
| Clipes originais (rosto, voz, GPS e aparelho no arquivo) | `radar-videos/bruto/<id>/` | ninguém pela tela; o robô, por link de 10 minutos | ao publicar (registro do link), substituir, descartar, revogar o termo, inativar a pessoa, retirar o termo do corretor ou marcar a pessoa menor de idade (uma pessoa do vídeo: marcada na peça ou no envio, ainda que desmarcada depois), ou `retencao_dias` (30) depois do envio |
| Transcrição com os tempos | `radar-videos/trabalho/<id>/` | o robô | junto com os originais |
| Vídeo corrigido e 4 quadros | `radar-videos/corrigido/…`, `quadros/…` | administrador e editor, por link de 10 minutos (registrado) | as versões antigas, na limpeza seguinte; o atual, `retencao_dias` depois do envio (o aprovado que espera o dia de postar, `retencao_dias` depois do dia da peça) ou `retencao_publicado_dias` (30) depois de publicado, ou na revogação |
| Fala, relatório, ajustes e cartela | tabela `radar_videos` (fora da trilha de auditoria) | administrador e editor | `retencao_publicado_dias` depois de publicar, 30 dias depois de substituir ou descartar, junto com o vídeo corrigido que sai pelo prazo sem a peça ter saído (peça cancelada, reel adiado), ou na revogação; ficam o hash, a data e o link da publicação |
| Áudio de 16 kHz | só no disco do robô, durante a execução; a Azure, no Brasil, sem gravação do áudio no serviço | — | apagado com a máquina do GitHub, no fim da execução |
| Quem enviou, viu e baixou | `radar_videos`, `radar_video_acessos` | administrador (acessos) | com a peça |
| Registros do GitHub | repositório privado `radar-video` | quem tem acesso a ele | 7 dias (Settings → Actions → General) |

O robô não tem chave do Supabase: usa só o token estreito do Vault (`radar_video_robo`), que serve só para pegar o pedido, pedir os
links dos arquivos desse pedido e entregar o resultado; cada link vale 10 minutos e para um caminho só. O ffmpeg roda num contêiner
**sem rede, sem segredo e só de leitura**, e o robô só escreve no registro a fase, o número do pedido, números e códigos (nunca a fala,
um nome, um link ou a mensagem do ffmpeg). A chave da Azure só existe no passo da transcrição, e a do robô só nos passos que falam
com a função. **No repositório público entram só vídeos sintéticos**, gerados pelo ffmpeg na hora dos testes, com nomes inventados
("Ana Teste", "Bruno Exemplo"): nunca um vídeo, áudio, foto, transcrição ou relatório de gravação real, nem para "testar com um caso
de verdade". O `.gitignore` barra as extensões de vídeo, áudio e foto e os arquivos de trabalho do robô, e o `radar-repositorio.yml`
confere em todo envio (também o vídeo com outro nome); mas esse aviso chega depois que o arquivo já ficou público.

**11. Termo de imagem e voz (texto para o advogado).** O termo de hoje diz que os vídeos são editados no aplicativo Edits e que a
Artecon não usa outros aplicativos ou empresas sem informar. **Antes do primeiro reel pelo corretor**, ele precisa citar o corretor,
quem trata os dados, o país e os prazos; cada pessoa assina de novo, e o administrador grava a data em Pessoas e termos ("Termo do
corretor de vídeo"; sem ela, o envio é recusado). Proposta para o item 12 ("Meus dados") do modelo do plano, no lugar da frase do
Edits (o advogado ajusta e confirma; os prazos são os padrões das Configurações):

> As fotos e os vídeos são publicados nas redes da Meta (Instagram e Facebook), que também guardam os dados em servidores fora do
> Brasil, conforme as regras delas, e podem ser editados no aplicativo Edits (Meta) ou no editor do Instagram. Os vídeos dos reels
> também passam pelo corretor de vídeo do Radar, o sistema interno da Artecon, que corta o começo, o fim, as pausas e as hesitações,
> ajusta o som e a cor e grava a legenda, com as palavras que eu disse, e a identificação legal da Artecon no fim, sem mudar o
> sentido do que eu disse e sem inteligência artificial que crie, troque ou imite meu rosto ou minha voz. Para isso: os arquivos
> ficam no armazenamento privado do Radar (Supabase), que só a equipe autorizada da Artecon acessa; a minha voz é transformada em
> texto pela Microsoft Azure, num recurso contratado pela Artecon na região Brasil, com a gravação do áudio no serviço desligada; e
> a edição é feita por um programa da Artecon no GitHub (empresa da Microsoft), num repositório privado, em computadores da
> Microsoft que podem ficar fora do Brasil (transferência internacional de dados, Lei 13.709/2018, art. 33). O vídeo original é
> apagado depois da publicação ou em até 30 dias, e o vídeo editado, em até 30 dias depois de publicado; a Artecon guarda só o
> registro da publicação (data, link e a identificação do arquivo). A Artecon não usa outros aplicativos ou empresas para tratar
> minha imagem e minha voz sem me informar.

Para o advogado conferir: a região do projeto do Supabase (Settings → General; fora do Brasil, também é transferência
internacional); a máquina do GitHub não tem região informada; a transferência internacional pede o art. 33 da LGPD e a Resolução
CD/ANPD nº 19/2024 (citada no parecer de privacidade); autorização genérica é nula (art. 8º, § 4º, e art. 9º, V); o corretor não usa
identificação de voz nem separa quem fala (nada de dado biométrico); depois de publicado, a Meta trata os dados como controladora
própria; menor de 18 anos não passa pelo corretor nesta versão; e se corte, redução de ruído e legenda contam como "alteração com
IA" no checklist do plano (para o Radar, não: não há IA no corretor).

**Limites desta versão.** Os limiares de corte, o ruído e a Azure ainda serão calibrados com gravações reais (o 1º reel acompanhado):
como o F0 escreve as siglas, os números e as hesitações, e se a tentativa interrompida conta na cota. HDR e 4:5 foram testados só com
vídeo sintético (grave com o HDR desligado). O envio retomável com o token assinado no celular, o tempo do robô no repositório
privado e o plano do Supabase se confirmam na instalação: no Free, **cada arquivo vai até 50 MB, os clipes e também o vídeo
corrigido** (o robô grava com qualidade alta, até 12 Mbps: um reel de 45 s fica entre 25 e 70 MB, e com pouca luz passa dos 50 MB);
passando, o robô para com o aviso do limite de tamanho do armazenamento. O Pro (limite global de 500 MB) resolve antes do 1º reel;
no Free, grave blocos de até uns 20 s e reels curtos. Enquanto o robô transcreve (cerca da duração da gravação), o WhatsApp da Agenda pode receber "ocupado" da Azure. O editor
de legenda da tela é um pouco mais rígido que o robô no número escrito de outro jeito ("20" e "vinte"). O telefone falado algarismo por
algarismo não casa com o roteiro: deixe o telefone só na cartela (`cartela_extra`). A publicação automática do reel e a capa escolhida
num dos quadros ficam para a v0.22.1. As recusas do banco do corretor vêm com os códigos RADAR300 a RADAR317 (por exemplo, RADAR302 "a
fala para conferência não está no roteiro", RADAR304 "pessoa ou termo", RADAR305 "cartela", RADAR312 "cota do mês", RADAR313 "o vídeo
da aprovação não confere", RADAR317 "registro do reel sem o vídeo aprovado").

### Concorrentes no Instagram (v0.19.1, opcional)

A função `radar-concorrentes` **só lê**: para uma lista de perfis comerciais (ou de criador) do Instagram de outros
escritórios de contabilidade, busca pela API oficial da Meta (Business Discovery) os dados públicos da conta (nome, bio, site,
seguidores, seguindo, total de posts) e dos posts recentes (data, formato, curtidas, comentários, visualizações quando a Meta
informa, legenda, link e o endereço da imagem). Não publica, não grava nada no banco e não guarda imagem; o registro (log) da
função só tem contagens.

- **O que não dá para ler:** alcance, salvamentos, compartilhamentos, visitas ao perfil e quem são os clientes dos
  concorrentes — são dados privados de cada conta. Curtidas ocultas pelo dono voltam vazias (`null`). Perfis pessoais não
  aparecem: a Meta só mostra contas comerciais ou de criador.
- **Permissão:** o `META_IG_TOKEN` (aplicativo "Radar Artecon Publicações") precisa de `instagram_basic` e
  **`instagram_manage_insights`**. Se faltar, gere o token de novo no Business (Usuários do sistema) marcando as duas e troque
  o segredo no Supabase (nunca pelo chat). A função usa os segredos que já existem (`META_IG_USER_ID`, `META_IG_TOKEN` e o
  opcional `META_GRAPH_URL`); o `META_PAGE_TOKEN` não é usado aqui.
- **Instalar:** (1) Supabase → Edge Functions → nova função `radar-concorrentes` com o
  `supabase/functions/radar-concorrentes/index.ts`, com **Verify JWT desligado** (a função confere sozinha: a chave do Vault ou
  o administrador logado); (2) rode uma vez `sql/radar-concorrentes.sql` no SQL Editor (cria a chave no Vault e a função que
  a confere). Para desfazer: `sql/radar-concorrentes-reversao.sql` e apague a função no Supabase.
- **Usar:** pelo SQL Editor, com `net.http_post` (o exemplo pronto está no fim do `sql/radar-concorrentes.sql`), mandando
  `{"perfis": ["escritorio1", "escritorio2"], "posts": 50}` — de 1 a 12 perfis por chamada e de 1 a 100 posts por perfil. A
  resposta chega em `net._http_response`. Perfil que não existe ou não é comercial volta com o motivo
  sem derrubar os outros. Já o limite de chamadas da Meta, a falta de permissão, o token vencido e o META_IG_USER_ID errado
  valem para todos: os perfis seguintes nem são pedidos e voltam com o mesmo aviso (corrija ou espere e peça de novo). Os que
  não couberem nos ~2 minutos voltam com "não coube no tempo; peça de novo só esses".
  `{"acao": "diagnostico"}` confere os segredos e a permissão lendo a própria conta da Artecon.
- **Ética:** a análise serve para entender **formatos e temas** que funcionam, nunca para copiar posts, textos ou imagens de
  outros escritórios (Código de Ética Profissional do Contador, NBC PG 01). O que se aprende vira conteúdo próprio da Artecon.

### Boletim da ITC pelo Microsoft Graph (v0.12.0; v0.23.0: a caixa inteira e o acesso só a ela)

A função `radar-itc` lê o boletim na caixa do Microsoft 365 onde ele chega (o segredo `ITC_CAIXA`). Desde a v0.23.0, ela lê a
**caixa inteira, menos o Lixo Eletrônico e os Itens Excluídos**: o boletim pode ser movido da Caixa de Entrada para uma subpasta
(por exemplo, "ITC Consultoria"), à mão ou por uma regra do Outlook, a qualquer hora — até antes da leitura das 02h55. O e-mail com o
remetente da ITC que caiu no Lixo Eletrônico (pode ser forjado) nunca entra, nem o que está nos Itens Excluídos. O boletim já lido e
movido depois não é lido de novo: o Radar o reconhece pelo identificador da mensagem (`internetMessageId`), que não muda de uma pasta
para outra. A função só lê: não marca como lido, não move e não responde.

O acesso é dado **só à caixa do boletim**, pelo método atual da Microsoft para aplicativos no Exchange Online ("Role Based Access
Control for Applications"; a `New-ApplicationAccessPolicy` das versões anteriores deste LEIAME é legado e não deve ser usada). Feito
uma vez por quem administra o Microsoft 365 do escritório:

1. Entre em https://entra.microsoft.com → **Identidade → Aplicativos → Registros de aplicativo → Novo registro**.
   Nome: `Radar Artecon — boletim ITC`; tipos de conta: **somente este diretório**; sem URI de redirecionamento → **Registrar**.
2. Na página do aplicativo, anote o **ID do aplicativo (cliente)** e o **ID do diretório (locatário)**. Depois, em **Identidade →
   Aplicativos → Aplicativos empresariais** → o mesmo aplicativo, anote o **ID do objeto** (o do aplicativo empresarial, que é
   diferente do ID do objeto do registro).
3. **Não** dê permissão de e-mail no Entra (Permissões de API: nada de Mail.Read de aplicativo). Se houver Mail.Read de aplicativo de
   antes, remova a permissão e retire o consentimento do administrador: **as permissões somam**, e o Mail.Read do Entra abre todas as
   caixas do escritório, por cima do escopo do passo 5 (o escopo deixa de valer).
4. **Certificados e segredos → Novo segredo do cliente** (validade de até 24 meses) → copie o **Valor** (aparece uma vez só).
   Anote a data de validade: quando vencer, gere outro e troque no Supabase.
5. No **Exchange Online PowerShell** (`Connect-ExchangeOnline`, com uma conta de administrador do Exchange), com os valores do passo
   2 e o e-mail da caixa do boletim no lugar dos `<…>`:

   ```powershell
   New-ServicePrincipal -AppId <ID do aplicativo> -ObjectId <ID do objeto do aplicativo empresarial>
   New-ManagementScope -Name "Radar - caixa do boletim ITC" -RecipientRestrictionFilter "PrimarySmtpAddress -eq '<e-mail da caixa>'"
   New-ManagementRoleAssignment -App <ID do aplicativo> -Role "Application Mail.Read" -CustomResourceScope "Radar - caixa do boletim ITC"
   Test-ServicePrincipalAuthorization -Identity <ID do aplicativo> -Resource <e-mail da caixa>
   ```

   O último comando mostra a função `Application Mail.Read` com **InScope = True**; com outra caixa do escritório no `-Resource`, o
   certo é **False**. A liberação leva **de 30 minutos a 2 horas** para valer: até lá, o teste do passo 7 mostra "O aplicativo ainda
   não tem permissão de ler esta caixa".
6. Supabase (projeto radar-artecon) → **Edge Functions → Secrets** → crie: `GRAPH_TENANT_ID` (ID do diretório),
   `GRAPH_CLIENT_ID` (ID do aplicativo), `GRAPH_CLIENT_SECRET` (o Valor do passo 4) e `ITC_CAIXA` (o e-mail da caixa onde o
   boletim chega, o mesmo do passo 5). **Nunca mande esses valores pelo chat.** O `IA_GATEWAY_TOKEN` já existe (é o mesmo da função
   radar-ia).
7. Radar → **Fontes** → boletim da ITC → **Testar conexão com o e-mail**: todos os itens devem ficar OK, e "Leitura da caixa" conta os
   boletins dos últimos 7 dias na caixa inteira (fora o Lixo Eletrônico e os Itens Excluídos), sem ler o conteúdo.
8. Rode `sql/radar-itc-agenda.sql` no SQL Editor (liga a leitura diária às 02h55; se ficar boletim para depois, ela se completa às
   03h10 e às 03h25; desde a v0.23.0, pode rodar de novo). **No mesmo momento, apague a rotina antiga** "Radar — boletim ITC
   (e-mail)" (a que acorda a conversa do Claude): com as duas, o boletim é lido duas vezes e a IA é paga duas vezes. Enquanto a
   função não estiver ligada, a rotina antiga é o caminho em produção (varredura geral de 13/10/2026: a agenda da ITC ainda não estava
   no pg_cron).

Opcional: `RADAR_ITC_MODELO` (padrão `claude-haiku-4-5`), `ITC_REMETENTE` (padrão `itc@itcnet.com.br`) e `ITC_PASTA`: vazio (o
padrão) = a caixa inteira, menos o Lixo Eletrônico e os Itens Excluídos; preenchido com o id de uma pasta (ou `inbox`), a função lê
só ela, como antes da v0.23.0 (o boletim movido para outra pasta deixa de ser lido). Deixe vazio. Cada leitura com boletim novo usa a
IA (cerca de 10 a 20 mil tokens por boletim); sem boletim novo, não usa. A lista de e-mails do Microsoft Graph vem em pedaços (até 5):
se os e-mails com o remetente da ITC no Lixo Eletrônico ou nos Itens Excluídos forem tantos que a lista não acaba, a aba Fontes mostra
"muitos e-mails com o remetente da ITC no Lixo Eletrônico ou nos Itens Excluídos… confira a caixa" e a leitura não conta como boa:
esvazie o Lixo (ou bloqueie o remetente falso) e leia de novo.

O e-mail do Portal Contábil (que às vezes fica na mesma pasta) não é lido pela função: as notícias dele entram pelo RSS do site.

O mesmo SQL cadastra **ITC Consultoria — boletim por e-mail** (`itc-email`) e a função
`radar_receber_email`, que grava as matérias do boletim lido no e-mail (a mesma manchete nos dois
boletins da ITC entra uma vez só). O robô não visita essa fonte. Os boletins **não** vão para o
repositório, que é público: a rotina diária grava direto no banco.

### Chaves novas do Supabase (até o fim de 2026)

O Supabase desliga as chaves antigas (a **anon**, pública, e a **service_role**, interna, as duas em formato JWT) até o fim de 2026.
Desligadas, a tela não entra, as agendas do banco recebem 401 e os robôs param. Desde a v0.22.0 (rodada 2 da varredura geral), o
Radar aceita as novas: a **publishable** (`sb_publishable_…`, pública) e a **secret** (`sb_secret_…`, interna). Cada uma vai **só no
cabeçalho `apikey`**: no `Authorization` o Supabase as recusa (não são JWT). Por isso, as funções chamadas sem sessão (pela agenda do
banco ou pelos robôs) ficam com o **"Verify JWT" desligado** e conferem quem chama no próprio código (a chave da agenda no Vault, a
chave do robô, a sessão pelo banco). Faça a troca num dia útil, **antes de dezembro**, nesta ordem (nada de chave pelo chat):

1. Supabase → **Settings → API Keys**: confira a publishable `default` e crie uma secret só para os robôs do GitHub ("radar-robos").
2. Edge Functions: as funções desta versão (`radar-ia`, `radar-redes`, `radar-video`, `radar-itc` e, se instalada,
   `radar-concorrentes`) já usam a publishable no `apikey` quando o Supabase a fornece (`SUPABASE_PUBLISHABLE_KEYS`). Na
   **`radar-redes`** e na **`radar-video`**, desligue o **"Verify JWT"** (as duas conferem no código: a sessão do administrador pelo
   banco, a chave da agenda no Vault, a chave do robô); a `radar-itc` e a `radar-concorrentes` já estão assim.
3. `radar-config.js`: troque o valor de `SUPABASE_ANON_KEY` pela publishable (o nome do campo fica), publique no GitHub e
   Ctrl+F5 em todos os aparelhos. A tela manda a chave só no `apikey` quando não há sessão.
4. SQL Editor: troque a chave escrita em `sql/radar-redes-agenda.sql` e em `sql/radar-video-agenda.sql` (o `v_anon`) pela
   publishable e rode os dois de novo (as chaves do Vault ficam; desde a v0.23.0, sem o "dependent privileges exist"); faça o teste do
   fim de cada arquivo (200).
5. GitHub, repositório `radar` → Secrets → **`SUPABASE_SERVICE_KEY`** = a secret do passo 1 (os robôs a mandam só no `apikey`).
   Rode "Radar — coleta" à mão e confira que fica verde.
6. Repositório privado `radar-video`: troque o `RADAR_VIDEO_COMMIT` pelo SHA do commit com o `radar-config.js` novo (o robô lê a
   chave pública de lá) e rode o workflow à mão (verde, sem vídeo na fila).
7. Só então: Supabase → Settings → API Keys → **Legacy API keys → Disable**. Se algo parar, reative as antigas (o mesmo botão) e
   confira o passo que faltou.

## Atualizações futuras

**Da v0.29.0 para a v0.30.0** (muda o banco: SQL novo, que pode rodar de novo; o robô dos avisos muda, mas sem segredo novo; as funções
`radar-ia`, `radar-redes` e `radar-video` e as agendas do banco não mudam; nada de chave ou segredo pelo chat). Supõe a v0.29.0
instalada. **Nesta ordem** (o banco antes da tela):

1. Supabase → **SQL Editor** → execute o `sql/radar-setup-v0.30.0.sql` inteiro, **antes de publicar a tela**. Confira no fim: **28
   tabelas** e "instalacoes concluidas" com a **v0.30.0**. Ele acrescenta as funções do aviso de possível prorrogação
   (`radar_prorrogacoes` e a regra `radar_prorrogacao_obrigacoes`): nenhuma tabela nem coluna nova, nada é apagado, e pode rodar de novo
   (é assim que ele é aplicado: o arquivo inteiro). **A lista de obrigações do escritório não muda** (o 13º e as anuais entram pelo
   passo 3). As agendas (`sql/radar-*-agenda.sql`) não mudam: não precisa rodá-las de novo.
2. Publique a versão no repositório (`main`): a tela (`index.html`, `radar-pauta.js` e `radar-video.js`) e o robô dos avisos
   (`robo/radar_alertas.py` e `robo/radar_banco.py`) vão juntos. Aperte **Ctrl+F5** em todos os aparelhos (no celular, recarregue a
   página). A aba Versões mostra a v0.30.0. Se a tela for publicada antes do SQL, nada quebra: as Configurações dizem ao administrador
   "O aviso de prorrogação precisa do banco da v0.30.0" (rode o passo 1 e recarregue).
3. Configurações → **Agenda de obrigações** → **"Acrescentar o 13º e as obrigações anuais"**, **antes do Informativo de novembro** (a 1ª
   parcela do 13º vence em 30/11/2026, segunda-feira). A tela mostra o que vai entrar (13º salário, 1ª e 2ª parcelas; DEFIS; DASN-SIMEI;
   ECD; ECF) e pede confirmação. **Antes de confirmar, confira se a agenda já não tem alguma delas com outro nome** (por exemplo, "13º
   Salário" numa linha só): se tiver, cancele, apague a repetida na caixa e clique de novo. Cada uma entra no fim da lista com a fonte
   oficial; as que já estavam não mudam. Clicar de novo diz "Nada a acrescentar".
4. Confira, **sem publicar nada**:
   - (a) Informativos → uma edição de teste de **novembro de 2026**: a agenda traz "13º Salário (1ª parcela)" em 30/11; uma de
     **dezembro**, "13º Salário (2ª parcela)" em 18/12 (o dia 20 é domingo: antecipa). Exclua as edições de teste depois.
   - (b) **Painel**: se houver notícia dos últimos 30 dias que fala em prorrogar o prazo de uma obrigação da agenda, aparece "Possível
     prorrogação de prazo", com a obrigação, a notícia e o link da fonte. Confira na fonte oficial. Se o prazo mudou, ponha a nova data
     na obrigação (Configurações → Agenda de obrigações, em "prorrogacoes", por exemplo `[{"de": "2027-03", "para": "2027-04-30",
     "fonte": "norma, artigo — endereço oficial"}]`, dentro da obrigação) e, nas edições do Informativo e na agenda da semana da Pauta já
     montadas, ajuste a data (ou "Recalcular pelo mês escolhido"). Depois clique em **"Conferido"**. A notícia sai do Painel e do aviso.
   - (c) Se não houver nenhuma agora, não há o que fazer: o Painel avisa quando aparecer.
   - (d) **Pauta**: numa Agenda da semana de teste, "Calcular a agenda da semana" diz "de seg, … a dom, …" (agora vai até o domingo).
     Exclua a peça de teste depois.
5. O **robô** não muda nada na sua rotina: ele entra no ar pelo merge e, depois de cada coleta (4 vezes por dia), abre **um** aviso no
   GitHub "Radar: possível prorrogação na agenda de obrigações" (o GitHub manda o e-mail). Cada notícia nova ganha um comentário (um
   e-mail); ele fecha sozinho quando todas forem conferidas (ou passarem de 30 dias). Se alguém fechar o aviso à mão, o robô não abre
   outro com as mesmas notícias (só com uma notícia nova). O repositório é público: do boletim da ITC, o aviso só conta quantas são.
   **Nenhum segredo novo.** Se o robô rodar antes do SQL, ele simplesmente não abre esse aviso. Os lembretes por e-mail (v0.29.0)
   continuam como estão.

Para desfazer: volte a tela da v0.29.0 (`index.html`, `radar-pauta.js` e `radar-video.js`, no histórico do GitHub; Ctrl+F5), volte o
robô (`robo/radar_alertas.py` e `robo/radar_banco.py` da v0.29.0) e rode o `sql/radar-setup-v0.29.0.sql` da v0.29.0 (histórico do
GitHub). As duas funções novas ficam no banco sem uso (para tirar: `drop function if exists public.radar_prorrogacoes(int);` e `drop
function if exists public.radar_prorrogacao_obrigacoes(text, jsonb);` no SQL Editor). O aviso aberto no GitHub fica aberto: feche à
mão. As obrigações acrescentadas pelo botão continuam na lista; a tela antiga não conhece "mes" e passa a pôr as anuais em **todos** os
meses: tire-as da lista (Configurações → Agenda de obrigações) **antes** de voltar a tela. A chave `prorrogacoes_conferidas`
(Configurações) fica no banco, sem uso.

**Da v0.28.1 para a v0.29.0** (muda o banco: SQL novo, que pode rodar de novo; mudam a função `radar-redes` e a agenda do banco;
entram um robô e um workflow; **nenhum segredo novo**; nada de chave ou segredo pelo chat). Supõe a v0.28.1 instalada. **Nesta ordem**
(o banco antes da tela; a função antes da agenda):

1. Supabase → **SQL Editor** → execute o `sql/radar-setup-v0.29.0.sql` inteiro, **antes de publicar a tela**. Confira no fim: **28
   tabelas** e "instalacoes concluidas" com a **v0.29.0**. Ele acrescenta a tabela `radar_lembretes` (vazia), as funções dos lembretes
   e a chave "lembretes" das Configurações, com os padrões; nada é apagado, e pode rodar de novo (é assim que ele é aplicado: o arquivo
   inteiro). Ainda não sai lembrete nenhum pela agenda: falta o passo 4.
2. Publique a versão no repositório (`main`): a tela (`index.html`, `radar-pauta.js` e `radar-video.js`), o robô
   (`robo/radar_lembretes.py` e `robo/radar_banco.py`) e o workflow (`.github/workflows/radar-lembretes.yml`) vão juntos. Aperte
   **Ctrl+F5** em todos os aparelhos (no celular, recarregue a página). A aba Versões mostra a v0.29.0. Se a tela for publicada antes
   do SQL, Configurações → Lembretes por e-mail mostra "A situação dos lembretes precisa do banco da v0.29.0": rode o passo 1 e
   recarregue.
3. Supabase → **Edge Functions** → `radar-redes` → cole o `supabase/functions/radar-redes/index.ts` desta versão e clique em
   **Deploy** (deixe o "Verify JWT" como está). O segredo `RADAR_GITHUB_TOKEN` (o do robô do site) já serve: o token fino tem
   "Actions: leitura e escrita" no repositório `radar`, e aciona o workflow novo também.
4. Supabase → **SQL Editor** → execute de novo o `sql/radar-redes-agenda.sql` inteiro. Ele refaz a agenda da Pauta com o agendamento
   novo `radar-redes-agenda-lembretes` (de 15 em 15 minutos); a chave do Vault continua a mesma. Confira no resultado os 4
   agendamentos: `radar-redes-agenda`, `radar-redes-agenda-lembretes`, `radar-redes-agenda-limpeza` e `radar-redes-agenda-robos`. O teste
   do fim do arquivo agora responde `{"ok":true,"versao":"0.29.0"}` (é a função nova). Se o arquivo parar em "Rode antes o
   radar-setup-v0.29.0.sql", faça o passo 1.

**O que configurar:** os padrões já servem (a Pauta de amanhã às 16:00; os outros das 08:00 às 20:00; a peça pronta depois de 24 horas;
a notícia parada depois de 3 horas). Para mudar: Configurações → **Lembretes por e-mail** → mude o valor → Salvar. Confira quem
recebe: github.com → Settings → Notifications → "Issues" com e-mail ligado; outro administrador que queira receber: no repositório,
**Watch → Custom → Issues**.

**O que conferir, sem publicar nada:**

- (a) GitHub → Actions → "Radar — lembretes por e-mail" → **Run workflow**: sem nada a lembrar, o registro diz "Há lembrete para mandar:
  nao" (ou, se o robô chegar a rodar, "Lembretes: nada a lembrar agora."). Fica verde.
- (b) Uns 15 minutos depois do passo 4, Configurações → Lembretes por e-mail → situação: "Agenda do banco: instalada (última rodada
  …)".
- (c) Para ver um lembrete de verdade antes do calendário: na Pauta, num dia de amanhã sem peça, "+ Nova peça" (por exemplo, Bastidor /
  Foto, assunto "Teste do lembrete"). A partir das 16:00, em até 15 minutos chega o e-mail "Radar: lembrete — Pauta de amanhã sem
  aprovação", sem nome nenhum. Depois, "Cancelar a peça" (o lembrete fecha sozinho e a peça sai do cronograma). Nada é publicado: a
  peça fica planejada até ser cancelada.
- O primeiro lembrete do calendário de verdade sai no domingo, 25/10, a partir das 16:00 (a peça de segunda, 26/10).

**Como desligar:** sem SQL, Configurações → Lembretes por e-mail → `"ligado": false` (todos) ou só um tipo (por exemplo,
`"video": false`) → Salvar. **Para parar de vez:** GitHub → Actions → "Radar — lembretes por e-mail" → "…" → **Disable workflow**, e
no SQL Editor `select cron.unschedule('radar-redes-agenda-lembretes');` (ou rode o `sql/radar-redes-agenda.sql` do commit 441bcfe, que
não tem o agendamento novo).

**Para desfazer** (nesta ordem):

1. GitHub → Actions → "Radar — lembretes por e-mail" → **Disable workflow**.
2. SQL Editor → rode o `sql/radar-redes-agenda.sql` do commit 441bcfe (histórico do GitHub): a agenda volta sem os lembretes (a chave
   do Vault fica a mesma).
3. Volte a tela da v0.28.1 (`index.html`, `radar-pauta.js` e `radar-video.js` do commit 441bcfe) e aperte Ctrl+F5.
4. Opcional: a `radar-redes` 0.22.0 (o `index.ts` do commit 441bcfe → Deploy). A 0.29.0 também funciona com a agenda antiga.
5. Opcional: rode o `sql/radar-setup-v0.28.0.sql` do commit 441bcfe. A tabela e as funções dos lembretes ficam no banco, sem uso. Para
   apagar de vez, no SQL Editor:

   ```sql
   drop table if exists public.radar_lembretes;
   drop function if exists public.radar_lembretes_cfg(), public.radar_lembretes_madura(text, text, jsonb, timestamptz, jsonb, timestamptz),
     public.radar_lembretes_observar(timestamptz), public.radar_lembretes_devidos(timestamptz), public.radar_lembretes_acionar(),
     public.radar_lembretes_ha_envio(), public.radar_lembretes_lote_em(timestamptz), public.radar_lembretes_lote(),
     public.radar_lembretes_enviado_em(uuid, int, bigint[], timestamptz), public.radar_lembretes_enviado(uuid, int, bigint[]),
     public.radar_lembretes_situacao();
   delete from public.radar_config where chave = 'lembretes';
   ```
6. No GitHub, feche à mão os avisos "Radar: lembrete — …" que estiverem abertos (aba Issues): o robô nunca fecha.

**Da v0.28.0 para a v0.28.1** (o banco não muda: não há SQL para rodar; as funções e os robôs não mudam; nada de chave ou segredo
pelo chat). Supõe a v0.28.0 instalada, com o `sql/radar-setup-v0.28.0.sql` já rodado.

1. A tela chega pelo repositório: publique juntos o `index.html`, o `radar-pauta.js` e o `radar-video.js` e aperte **Ctrl+F5** em
   todos os aparelhos (no celular, recarregue a página). A aba Versões mostra a v0.28.1. Sem o Ctrl+F5, o navegador pode continuar
   com o `radar-pauta.js` antigo guardado, e a trava antiga junto.
2. O que conferir, **sem publicar nada**, numa peça de teste: clique em "Acrescentar informação" e deixe a linha em branco; "Conferir
   o que falta" (e, no reel, o envio do vídeo) roda sem o aviso. Escreva algo na linha sem salvar: o aviso volta e termina com "O que
   mudou e não foi salvo: Informações conferidas.". Se o aviso aparecer sem você ter mudado nada, clique em **Salvar**: com nada para
   gravar, ele responde "Nada mudou na peça." e destrava a peça.

O banco continua no `sql/radar-setup-v0.28.0.sql`. Para desfazer: volte o `index.html`, o `radar-pauta.js` e o `radar-video.js` da
v0.28.0 (no histórico do GitHub) e aperte Ctrl+F5; nada muda no banco.

**Da v0.27.0 para a v0.28.0** (muda o banco: SQL novo, que pode rodar de novo; as funções `radar-ia`, `radar-redes` e `radar-video`
não mudam; nada de chave ou segredo pelo chat). Supõe a v0.27.0 instalada. Nesta ordem:

1. Supabase → **SQL Editor** → execute o `sql/radar-setup-v0.28.0.sql` inteiro, **antes de publicar a tela**. Confira no fim: 27
   tabelas e "instalacoes concluidas" com a **v0.28.0**. Ele acrescenta a coluna `socio` em `radar_pessoas` (desmarcada para todos), a
   função da "+ Nova peça" e a regra dos termos para sócio(a): nenhuma tabela nova, nada é apagado, e pode rodar de novo (é assim que
   ele é aplicado: o arquivo inteiro). As agendas (`sql/radar-*-agenda.sql`) não mudam.
2. A tela chega pelo repositório: publique juntos o `index.html`, o `radar-pauta.js` e o `radar-video.js` e aperte Ctrl+F5 em todos os
   aparelhos (no celular, recarregue a página). A aba Versões mostra a v0.28.0. Se a tela for publicada antes do SQL, a Pauta mostra
   "A Pauta desta versão precisa do banco da v0.28.0": rode o passo 1 e recarregue.
3. O que conferir, **sem publicar nada**:
   - (a) Pauta → **Pessoas e termos**: marque **"Sócio(a) da Artecon"** em cada sócio(a) e salve (a tela pergunta antes: confirme). O
     cadastro mostra o selo "Sócio(a) — termos dispensados", e o Histórico mostra "socio: false → true" (sem o nome).
   - (b) Na semana de 12/10 a 18/10/2026, os dias sem peça de hoje em diante (sábado 17/10 e domingo 18/10, por exemplo) mostram
     "+ Nova peça". Crie, por exemplo, um **Bastidor / Foto**
     em 17/10 e um **Reel da semana / Reel** em 18/10. Cada peça abre como as outras: "Planejada", o roteiro, "Quem aparece", as fotos e,
     no reel, o quadro "Corretor de vídeo". Marque o(a) sócio(a) em "Quem aparece" e salve: o selo é "Sócio(a) — termos dispensados".
     No reel, o envio do vídeo continua pedindo as **quatro declarações**.
   - (c) Nada sai sozinho: a peça nova fica planejada até ser preparada, marcada como pronta e aprovada pelo administrador.
   - (d) Depois do teste, use **"Cancelar a peça"** nas duas peças de teste: a peça cancelada sai do cronograma (sem isso, o quadro
     "Cronograma de publicações" conta as duas no mínimo e as marca em vermelho quando o dia passar). O dia cancelado não recebe outra
     peça: para usar o dia de novo, "Reabrir".
4. Depois, ao importar o calendário (CSV) com uma linha para um dia que já tem a peça criada à mão: se ela ainda estiver planejada, a
   prévia mostra "alterada" e ela recebe o que está no arquivo; se já entrou em produção, fica como está ("mantida").

Para desfazer: volte a tela da v0.27.0 (`index.html`, `radar-pauta.js` e `radar-video.js`, no histórico do GitHub; Ctrl+F5) e rode o
`sql/radar-setup-v0.25.0.sql` do commit 722b1c4 (histórico do GitHub). Os termos voltam a ser exigidos de todos (o banco antigo não
conhece a marca); a "+ Nova peça" perde a permissão; a coluna `socio` fica no banco, sem uso; as peças criadas à mão continuam como
peças normais. **Atenção:** com o banco antigo, o vídeo do corretor com um(a) sócio(a) que não tem o termo do corretor é apagado na
limpeza do dia seguinte; antes de desfazer, registre os termos dessa pessoa (ou baixe o que precisar).

**Da v0.26.0 para a v0.27.0** (o banco não muda: não há SQL para rodar; as funções `radar-ia` e `radar-redes` não mudam; nada de
chave ou segredo pelo chat). Supõe a v0.26.0 instalada (se não estiver, faça antes o "Da v0.25.1 para a v0.26.0").

1. A tela chega pelo repositório: publique juntos o `index.html`, o `radar-pauta.js` e o `radar-video.js` (no `radar-video.js`, só o
   número da versão) e aperte Ctrl+F5 em todos os aparelhos (no celular, recarregue a página). A aba Versões mostra a v0.27.0.
2. Na Pauta, confira o quadro "Cronograma de publicações" no alto da semana: "← Semana anterior" troca a semana e o mês do quadro, e
   "Como o quadro conta" explica cada linha. O quadro não grava nada.

O banco continua no `sql/radar-setup-v0.25.0.sql`. Para desfazer: volte o `index.html`, o `radar-pauta.js` e o `radar-video.js` da
v0.26.0 e aperte Ctrl+F5; como o quadro só lê, não há nada para apagar no banco.

**Da v0.25.1 para a v0.26.0** (o banco não muda: não há SQL; as funções `radar-ia` e `radar-redes` não mudam; nada de chave ou
segredo pelo chat).

1. Se a produção ainda estiver na v0.25.0, faça antes o "Da v0.25.0 para a v0.25.1" (a tela da v0.26.0 também funciona com a `radar-ia`
   0.25.0).
2. A tela chega pelo repositório: `index.html`, `radar-pauta.js` e `radar-video.js` juntos; Ctrl+F5 em todos os aparelhos. A aba
   Versões mostra a v0.26.0.
3. Teste num assunto de teste, **sem autorizar nada**: (a) "Preparar com IA" mostra "Preparar · etapa X de 4" e o texto aparece no
   passo 2 com os 10 critérios; (b) com um ✗, o "✓ Aprovar" fica desligado e a tela diz o que falta; (c) no passo 3 aparecem as linhas
   Site/Instagram/Facebook e o "Publicar em todos".

O banco continua no `sql/radar-setup-v0.25.0.sql`. Para desfazer: volte os três arquivos da tela da v0.25.1. Os textos que o Preparar
deixou "em revisão" continuam em revisão na tela antiga.

**Da v0.25.0 para a v0.25.1** (o banco não muda: não há SQL para rodar; nada de chave ou segredo pelo chat). Nesta ordem:

1. A tela chega pelo repositório: `index.html`, `radar-pauta.js` e `radar-video.js` juntos (nos dois scripts, só o número da versão);
   Ctrl+F5 em todos os aparelhos. A aba Versões mostra a v0.25.1. A tela nova funciona também com a função `radar-ia` da v0.25.0 (o kit
   dela traz a chamada e o apoio da arte, que a tela ignora): por isso ela vem primeiro.
2. Edge Functions → `radar-ia` → cole o `index.ts` desta versão → Deploy, com "Verify JWT" como já está. Nenhum segredo muda. A
   `radar-redes` não muda.
3. Configurações → Inteligência artificial → **Testar a IA**: a função aparece como **v0.25.1**.
4. Teste num assunto de teste, sem publicar: (a) num conteúdo com lista no texto e sem kit, o passo Publicar mostra a legenda com cada
   item na sua linha ("• Item", com a primeira letra maiúscula) e a identificação legal no fim; (b) "Gerar kit das redes com IA" gera as
   legendas e o roteiro do reel (sem chamada nem apoio da arte), e um conteúdo com o kit antigo continua mostrando as legendas dele.

O banco continua na v0.25.0 (`sql/radar-setup-v0.25.0.sql`). Se a função for instalada antes da tela (ou se algum aparelho ainda
estiver com a tela da v0.25.0 guardada), o kit gerado nesse meio-tempo aparece como "incompleto" na tela antiga e as redes usam a
legenda montada pelo Radar; com a tela nova (Ctrl+F5), ele vale normalmente, sem gerar de novo.

Para desfazer: cole de novo o `index.ts` da `radar-ia` da v0.25.0 (no histórico do GitHub) e volte a tela da v0.25.0. O kit gerado pela
v0.25.1 (sem a arte) aparece como "incompleto" na tela da v0.25.0: gere o kit de novo, se quiser usá-lo. As legendas já gravadas ou
publicadas não mudam.

**Da v0.24.0 para a v0.25.0** (muda o banco: SQL novo, só uma função, que pode rodar de novo; nada de chave ou segredo pelo chat).
Faça tudo de uma vez, num momento em que ninguém esteja gerando imagem nem aprovando conteúdo:

1. Supabase → **SQL Editor** → execute o `sql/radar-setup-v0.25.0.sql` inteiro. Confira no fim: 27 tabelas e "instalacoes concluidas"
   com a **v0.25.0**. Ele só atualiza a conferência do critério 6 (`radar_conferencia_codigo`): nenhuma tabela nem coluna nova, nada é
   apagado, a conferência já gravada continua valendo, e pode rodar de novo. As agendas (`sql/radar-*-agenda.sql`) não mudam.
2. Edge Functions → `radar-ia` → cole o `index.ts` desta versão → Deploy, com "Verify JWT" como já está. Nenhum segredo muda (o
   `RADAR_IA_MODELO_IMAGEM` continua `gpt-image-2`). A `radar-redes` **não muda** (continua na v0.22.0).
3. A tela e o robô do site chegam pelo repositório: `index.html`, `radar-pauta.js` e `radar-video.js` juntos, e o
   `robo/radar_site_publicar.py`. Ctrl+F5 em todos os aparelhos. A aba Versões mostra a v0.25.0.
4. Configurações → Inteligência artificial → **Testar a IA**: a função aparece como **v0.25.0** (o painel avisa se ela for mais velha).
5. Teste num assunto de teste, sem publicar: no conteúdo, "Gerar imagem com IA" (com uma descrição, por exemplo "contadora conversando
   com o casal dono de uma padaria, no balcão da loja"): a imagem aparece inteira, com aparência de foto e o aviso pequeno no canto; "Ver
   como fica no site" termina com "Imagem ilustrativa gerada por IA."; "Usar a capa padrão Artecon" e depois "Usar a imagem da IA de
   novo" trocam a imagem sem nova cobrança. No passo Publicar, a imagem dos quadros das redes é a mesma, e as legendas terminam com a
   linha do aviso antes da identificação legal. Se aparecer o recado "A IA Central não aceitou a imagem em qualidade alta", libere a
   qualidade alta do modelo de imagem do Radar no Portal → Consumo de IA (o Radar não troca a qualidade sozinho) e tente de novo.

Depois da instalação: os conteúdos com a capa antiga (montada com a ilustração ao fundo) e o que já foi publicado não mudam; a regra
nova vale quando se gera ou troca a imagem. A imagem da IA custa mais por imagem (qualidade alta).

Para desfazer: rode o `sql/radar-setup-v0.24.0.sql` da v0.24.0 (no histórico do GitHub): o critério 6 volta a pedir o aviso escrito no
texto também para a imagem da IA. Cole de novo o `index.ts` da `radar-ia` da v0.24.0 e volte a tela e o robô do site da v0.24.0. As
imagens gravadas nesta versão ficam como estão (no site e nas redes já publicadas, com o aviso no canto).

**Da v0.23.0 para a v0.24.0** (muda o banco: SQL novo, que pode rodar de novo; nada de chave ou segredo pelo chat). Faça tudo de uma
vez, num momento em que ninguém esteja aprovando conteúdo: do SQL até a tela nova, a aprovação passa a pedir a Conferência das
Diretrizes, que só a função e a tela novas fazem.

1. Supabase → **SQL Editor** → execute o `sql/radar-setup-v0.24.0.sql` inteiro. Confira no fim: 27 tabelas e "instalacoes concluidas"
   com a **v0.24.0**. Ele cria a Conferência das Diretrizes (coluna `conferencia` em `radar_conteudos` e as funções), a trava do
   Informativo e a revisão editorial (guardada na mesma coluna; aceita também a linha "Fonte oficial"); não apaga nada e pode rodar de
   novo. As agendas (`sql/radar-*-agenda.sql`) não mudam.
2. Edge Functions → `radar-ia` → cole o `index.ts` desta versão → Deploy, com "Verify JWT" como já está. Nenhum segredo muda.
3. A tela e o robô do site chegam pelo repositório: `index.html`, `radar-pauta.js` e `radar-video.js` juntos, e o
   `robo/radar_site_publicar.py` (o workflow "Radar — publicar no site" já usa o novo). Ctrl+F5 em todos os aparelhos. A aba Versões
   mostra a v0.24.0.
4. Configurações → Inteligência artificial → **Testar a IA**: a função aparece como **v0.24.0** (o painel avisa se ela for mais velha).
5. Teste num assunto de teste, sem publicar: (a) um conteúdo em revisão mostra o quadro "Conferência das Diretrizes" com "?"; o
   "Revisar com IA" preenche os 10 critérios; com ✗, o Aprovar recusa; como administrador, "Revisei e assumo" (com o motivo) libera;
   (b) num assunto sem texto oficial, o "Gerar com IA" faz um texto com o selo "Informativo — aguardando autorização"; o administrador
   clica em "Autorizar a publicação do Informativo…", escreve o motivo, e a prévia ("Ver como fica no site") termina com "Conteúdo
   informativo"; (c) num assunto com texto oficial, o "Gerar com IA" faz o texto com a linha "Fonte oficial" no fim (sem a seção
   "Fundamentação legal") e, abaixo da Conferência das Diretrizes, o quadro "Revisão editorial" com as 10 perguntas (✓ ou ✎) e o que foi
   reescrito; edite uma frase à mão, salve, e o quadro avisa que a revisão era da versão anterior.
6. (Opcional) Em Configurações → Inteligência artificial, escreva as **Orientações para a IA** (veja "Diretrizes editoriais e como
   ensinar a IA") e clique em Salvar; gere um texto e uma ilustração num assunto de teste e confira; ajuste quantas vezes quiser.

Depois da instalação: o que já estava aprovado continua aprovado (e publica como antes); o conteúdo em rascunho ou em revisão precisa
da Conferência ("Revisar com IA") ou do "Revisei e assumo" para ser aprovado. O texto gerado antes, sem texto oficial, não vira
Informativo (só os gerados daqui em diante). A humanização, a linha "Fonte oficial" e a revisão editorial valem para o que a IA escrever
depois da instalação: os textos de antes, os roteiros de reel já gravados e o que está na Pauta não são reescritos (nos textos da IA
ainda em revisão, o quadro "Revisão editorial" mostra "não feita", com o botão, se quiser usar).

Para desfazer: rode o `sql/radar-setup-v0.22.0.sql` da v0.23.0 (no histórico do GitHub): a aprovação volta a ser como antes (sem a
Conferência e sem a trava do Informativo; a coluna nova fica, sem efeito, com a revisão editorial guardada nela, e as duas funções da
revisão editorial ficam sem uso). Cole de novo o `index.ts` da `radar-ia` da v0.22.0 e volte a
tela e o robô do site da v0.23.0. As orientações ficam guardadas nas Configurações, sem efeito; para só parar de usá-las, deixe os dois
campos em branco e salve.

**Da v0.22.0 para a v0.23.0** (o banco não muda; nada de chave ou segredo pelo chat):

1. A tela chega pelo repositório: `index.html`, `radar-pauta.js` e `radar-video.js` juntos (só o número da versão muda); Ctrl+F5 em
   todos os aparelhos. A aba Versões mostra a v0.23.0.
2. Edge Functions → `radar-itc` → cole o `index.ts` desta versão → Deploy, com "Verify JWT" como já está. Se existir o segredo
   `ITC_PASTA`, apague-o (vazio = a caixa inteira, menos o Lixo Eletrônico e os Itens Excluídos), a não ser que queira mesmo ler só
   uma pasta.
3. Acesso só à caixa do boletim: em "Boletim da ITC pelo Microsoft Graph", os passos 2 (o ID do objeto do aplicativo empresarial),
   3 (nada de Mail.Read no Entra) e 5 (os 4 comandos do Exchange, com `InScope = True`), e confira o `ITC_CAIXA`. Espere de 30
   minutos a 2 horas.
4. Fontes → boletim da ITC → **Testar conexão com o e-mail**: "Função radar-itc instalada" mostra **versão 0.23.0** e "Leitura da
   caixa" fica OK, com a contagem dos últimos 7 dias na caixa inteira. "O aplicativo ainda não tem permissão de ler esta caixa" =
   a atribuição ainda não vale (espere e teste de novo) ou falta um passo.
5. Só com o teste OK: SQL Editor → `sql/radar-itc-agenda.sql` (passo 8 de "Boletim da ITC pelo Microsoft Graph") e, **no mesmo dia,
   apague a rotina antiga** "Radar — boletim ITC (e-mail)" (`robo/rotina-itc-email.md`).
6. O robô (`robo/radar_inlabs.py`) chega pelo repositório: os segredos `INLABS_EMAIL` e `INLABS_SENHA` ficam como estão.

As agendas da Pauta e do corretor (`sql/radar-redes-agenda.sql` e `sql/radar-video-agenda.sql`) não precisam rodar de novo nesta
versão; quando precisarem (na troca da chave pública, em "Chaves novas do Supabase"), rodam sem o "dependent privileges exist".
Para desfazer: cole de novo o `index.ts` da `radar-itc` da v0.22.0 (no histórico do GitHub). Ela lê só a Caixa de Entrada (o boletim
movido para a subpasta deixa de ser lido) e não reconhece o "já lido" desta versão: os boletins das últimas 50 horas vão uma vez de
novo à IA (as matérias não duplicam).

**Da v0.21.0 para a v0.22.0** (instale num **dia útil**, com tempo para o teste do corretor com um vídeo de teste; nesta ordem; nada
de chave ou token passa pelo chat):

**Atenção: do passo 1 (o SQL) em diante, nenhum reel do calendário fica pronto nem é aprovado sem o corretor funcionando (passos 1
a 8) e sem o termo novo de cada pessoa assinado e gravado em Pessoas e termos.** Por isso o termo vem antes de tudo (passo 0).

0. Antes:
   - **O termo novo** ("Termo de imagem e voz", em "Corretor de vídeo do reel", item 11): o advogado confere o texto, e cada pessoa
     que vai gravar assina **antes da instalação**. Anote no papel, para cada pessoa, a data da assinatura, "pediu para ver a peça
     antes" e "menor de idade": os campos só existem depois do SQL, e o administrador grava logo depois do passo 1 (passo 9). Sem o
     termo novo, o envio de qualquer reel é recusado (RADAR304).
   - Supabase → **Settings → Billing**: confira o plano. No Free, cada arquivo do armazenamento vai até **50 MB** — os clipes (por
     bloco, de 10 a 20 s em 1080p, ficam abaixo disso; um clipe longo ou em 4K não passa) **e o vídeo corrigido** (um reel de 45 s fica
     entre 25 e 70 MB; acima de 50 MB, o robô para com o aviso do limite). Recomendado: o **Pro antes do 1º reel**, com **Storage →
     Settings**: limite global de arquivo em 500 MB. No Free, reels curtos.
   - **Azure** (portal.azure.com): a avaliação grátis da assinatura vence por volta de **08/11/2026**. Antes disso, passe a
     assinatura para "pagamento conforme o uso"; o recurso `artecon-voz` continua no F0, grátis, e sem isso ele para (a transcrição
     do WhatsApp da Agenda e a do corretor).
   - O repositório **privado** `arteconartescontabeis-design/radar-video` já existe, com os segredos `AZURE_FALA_CHAVE` (a CHAVE 2
     do `artecon-voz`) e `AZURE_FALA_REGIAO` (`brazilsouth`).
   - Reel já aprovado à mão na v0.21.0 (vídeo do Edits): continua como antes, também depois do SQL — baixe e poste o vídeo de
     sempre e registre o link. O registro do reel sem o vídeo corrigido (RADAR317) vale só para a aprovação feita com a v0.22.0.
1. SQL Editor → execute `sql/radar-setup-v0.22.0.sql` inteiro (a linha `instalacoes concluidas` mostra `v0.22.0`; 27 tabelas). Ele
   cria as tabelas do corretor, os 3 campos de Pessoas e termos e a configuração `corretor_video` com os padrões. Daqui em diante, a
   peça reel só fica pronta com o vídeo corrigido pronto. O SQL vem **antes** da tela: a tela antiga (v0.21.0) com o banco novo
   continua abrindo e aprovando o que não é reel (o reel mostra "Reel: envie a gravação" até a tela nova); já a tela nova com o banco
   antigo não abre nenhuma peça da Pauta nem salva Pessoas e termos (ela lê os campos novos).
2. A tela nova chega pelo repositório: o `index.html`, o `radar-pauta.js` **e o arquivo novo `radar-video.js`**, sempre juntos, na
   branch principal do GitHub. Aperte **Ctrl+F5 em todos os aparelhos** e confira no rodapé **Radar v0.22.0**.
3. Edge Functions → **Deploy a new function** → nome exatamente **`radar-video`** → cole `supabase/functions/radar-video/index.ts`
   → **"Verify JWT" ligado** → Deploy. Ela cria sozinha o armazenamento **privado** `radar-videos` no primeiro uso (passo 8), sem limite
   de tamanho próprio: vale o limite global do projeto (Storage → Settings), que o passo 0 confere.
4. SQL Editor → execute `sql/radar-video-agenda.sql` (as chaves `radar_video_robo` e `radar_video_agenda` no Vault, a reserva de 10
   em 10 minutos e a limpeza diária) e faça o **teste** `agenda_teste` do comentário do fim do arquivo: copie as linhas **sem os
   `--`** do começo (não há nada para trocar) e execute; o esperado é 200 com `{"ok":true,"versao":"0.22.0"}`. 401 "Invalid JWT": a
   chave anon escrita no arquivo não é a deste projeto (a do `radar-config.js`): troque e rode o arquivo de novo; 404: a função não
   se chama `radar-video` (passo 3).
5. **A chave do robô, do Vault para o GitHub privado:** Supabase → **Vault** → `radar_video_robo` → revelar → copiar → GitHub,
   repositório `radar-video` → **Settings → Secrets and variables → Actions → New repository secret**: nome
   **`RADAR_VIDEO_ROBO_CHAVE`**, valor colado direto. Nunca pelo chat, num arquivo ou no repositório público. Com ela o robô fala só
   com a função `radar-video`: nenhuma chave do Supabase vai para o GitHub.
6. **O token do GitHub, só para o `radar-video`, no Supabase:** GitHub → foto do perfil → **Settings → Developer settings →
   Personal access tokens → Fine-grained tokens → Generate new token**. Token name: "Radar — acionar o corretor de vídeo";
   Expiration: até 1 ano (anote a data para renovar); Resource owner: `arteconartescontabeis-design`; Repository access: "Only
   select repositories" → **`radar-video`** (só ele); Permissions → Repository permissions → **Actions: "Read and write"** (o
   "Metadata: Read-only" vem junto), nada mais. Generate token, copie e grave em Supabase → **Edge Functions → Secrets → Add new
   secret**: nome **`RADAR_VIDEO_GITHUB_TOKEN`**. Fica **só** no Supabase. É outro token, diferente do `RADAR_GITHUB_TOKEN` (o do
   robô do site, só do repositório `radar`).
7. **O repositório privado `radar-video`:**
   - crie `.github/workflows/radar-video.yml` com o conteúdo de `robo/video/workflow/radar-video.yml` deste pacote, tal qual, na
     branch `main`;
   - **Settings → Secrets and variables → Actions → aba Variables**: **`RADAR_VIDEO_URL`** =
     `https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-video` e **`RADAR_VIDEO_COMMIT`** = o SHA (40 caracteres) do
     commit deste repositório público com a v0.22.0, depois que o "Radar — testes" passou nele (GitHub → `radar` → Commits → copiar
     o SHA completo). Mudar o robô é publicar aqui, esperar os testes e trocar esse SHA lá;
   - **Settings → Actions → General**: retenção dos registros e artefatos em **7 dias**; se aparecer "Allow forking", desligue;
   - os segredos opcionais `AZURE_FALA_MODO` e `AZURE_FALA_ENDPOINT` ficam sem cadastrar (vazio = Azure gratuita).
   Teste: Actions → "Radar — corretor de vídeo" → **Run workflow**. Sem vídeo na fila, termina verde em cerca de 1 minuto. Vermelho
   em "Pegar o pedido": a `RADAR_VIDEO_ROBO_CHAVE` ou a `RADAR_VIDEO_URL` não confere (o registro mostra só o código, como
   `robo_chave`); em "Conferir o commit": o `RADAR_VIDEO_COMMIT` não é um SHA completo deste repositório.
8. Ctrl+F5 no Radar. Configurações → **Corretor de vídeo** → **"Testar o corretor de vídeo"**: tudo OK ("Armazenamento dos vídeos:
   bucket privado", "Token do GitHub", "Workflow do robô: ativo", a fila e os minutos do mês). No mesmo bloco, confira o glossário,
   o `cartela_extra` (por exemplo, "Desde 1984 · (48) 3242-0530 · artecon.cnt.br"), o `limite_min_mes` e os prazos de guarda. Em
   "Fecho, assinatura e identificação legal", confira que o CRC é **"CRC-SC 007129/O-0"** (ele vai à cartela de todo reel). Na
   **Agenda de obrigações**, se faltar fonte em alguma obrigação, **"Preencher fontes oficiais"**.
9. **Termo e pessoas** (logo depois do passo 1, com o papel do passo 0): o administrador grava em Pauta → **Pessoas e termos** a
   data do **termo do corretor de vídeo**, "pediu para ver a peça antes" e "menor de idade" de cada pessoa, exatamente como no papel.
10. **Equipe:** passe a orientação de gravação ("Corretor de vídeo do reel", item 1): vertical, 1080p, 30 quadros por segundo, Vídeo
    HDR desligado, por bloco, sem música, sem tela ou documento ao fundo, sem editar, e guardar os clipes até o relatório dizer
    "Vídeo corrigido pronto" — então apagar do celular e da nuvem pessoal, no mesmo dia do envio.
11. **Primeiro reel acompanhado:** antes do primeiro reel do calendário, o administrador grava um vídeo de teste com um roteiro
    inventado (sem dado de cliente), com uma pessoa que já assinou o termo novo. **Nunca numa peça real** (o roteiro inventado
    substituiria o do calendário): importe, por "Importar o calendário (CSV)", uma peça de teste numa data sem peça — depois do fim
    do calendário, por exemplo `01/02/2027;seg;1;Reel da semana;Reel;Teste do corretor (apagar);—;teste;Peça de teste` com a linha de
    cabeçalho de sempre (o CSV fica no computador: nunca no GitHub) —, cole nela o roteiro inventado, marque a pessoa e envie.
    Confira o relatório, a prévia, os cortes, a legenda e a cartela, e anote só os números (tempo do robô, cortes, volume) para a
    calibração. No fim, **"Descartar esta gravação"** e **"Cancelar a peça"**; apague do celular. O vídeo, o áudio e o relatório de
    teste **não vão para o GitHub**.

12. **Correções da varredura geral:** Edge Functions → `radar-ia` → cole o `index.ts` desta versão → Deploy (Configurações →
    Inteligência artificial → "Testar a IA" mostra **v0.22.0**); Edge Functions → `radar-itc` → cole o `index.ts` desta versão →
    Deploy, com "Verify JWT" como já está (o "Testar conexão" da ITC mostra **versão 0.23.0**, a do `index.ts` atual; veja também
    "Da v0.22.0 para a v0.23.0").
13. **Rodada 2 da varredura geral:** Edge Functions → `radar-redes` → cole o `index.ts` desta versão → Deploy, com "Verify JWT"
    ligado, como já está; Publicações → "Testar conexão" mostra **"Função radar-redes v0.22.0"** e "Armazenamento das imagens: bucket
    privado radar-pauta". Se a `radar-concorrentes` (opcional) estiver instalada, o mesmo com o `index.ts` dela (o teste mostra
    0.22.0). SQL Editor → execute de novo `sql/radar-redes-agenda.sql` (mantém a chave do Vault e acrescenta o pedido diário
    "manter_robos") e faça o teste do fim do arquivo: 200 com `{"ok":true,"versao":"0.22.0"}`. No Storage → `radar-redes` (público),
    apague as imagens das notícias que ainda estiverem lá (a Meta já tem a cópia; as publicações excluídas, principalmente). No
    repositório privado `radar-video`, troque o `RADAR_VIDEO_COMMIT` pelo SHA do commit com esta rodada (o robô aceita a chave pública
    nova). A sessão passa a ficar só na aba: depois do Ctrl+F5, cada aba pede a entrada uma vez.

Nenhum segredo da Azure vai ao Supabase: a transcrição é do robô, no repositório privado. A agenda da Pauta muda só pelo pedido
diário "manter_robos" (passo 13).

Cuidados nesta versão:
- **No repositório público (este), só vídeos sintéticos.** Nunca envie ao GitHub um vídeo, áudio, foto, transcrição, relatório ou
  legenda de gravação real, nem para testar, nem arrastando pelo site ("Upload files" não passa pelo `.gitignore`). O
  `radar-repositorio.yml` confere em todo envio e avisa, mas depois que o arquivo já ficou público (e no histórico).
- A tela antiga (v0.21.0) com o banco novo continua aprovando o que não é reel; o reel precisa da tela nova (o hash do vídeo vai na
  aprovação). Não volte a tela depois do primeiro reel enviado.
- **Para parar o corretor sem SQL** (a cota da Azure no fim, um problema no robô): no repositório privado `radar-video`, **Actions →
  "Radar — corretor de vídeo" → ⋯ → Disable workflow**. Isso para tudo, inclusive a agenda própria do workflow (10h47 e 16h47 dos
  dias úteis). Tirar só o `RADAR_VIDEO_GITHUB_TOKEN` **não** para: a agenda do workflow pega e processa o pedido sem ele. Com o
  workflow desligado, o pedido que estiver na fila vira o aviso "robo_nao_pegou" na peça em uns 30 a 40 minutos (3 acionamentos da
  reserva); para voltar, "Enable workflow" e, na peça, "Tentar de novo".
- **Para desfazer a versão** (além da tela antiga): a agenda sai com o `sql/radar-video-agenda-reversao.sql` e o banco com o
  `sql/radar-reversao-v0.22.0.sql` (hoje `radar-reversao-v0.30.0.sql`), que não apaga os arquivos (antes: Storage → `radar-videos` → apague tudo e depois o bucket; e
  também `radar-pauta`, o bucket privado onde a `radar-redes` guarda as lâminas aprovadas da Pauta, com foto e nome da equipe: sem
  as tabelas, ninguém mais saberia de quem é cada arquivo, e a revogação de um termo não teria como ser atendida — se precisar
  guardar a relação, rode antes a consulta do passo 3 da revogação e guarde o resultado fora do repositório público). Fora do
  banco, ficariam rodando ou valendo: no repositório privado `radar-video`, desative o workflow (Disable workflow, como acima, ou apague
  `.github/workflows/radar-video.yml`: a agenda dele roda duas vezes por dia útil e, sem o banco, falharia a cada vez) e apague os
  segredos `RADAR_VIDEO_ROBO_CHAVE`, `AZURE_FALA_CHAVE` e `AZURE_FALA_REGIAO` (e os opcionais `AZURE_FALA_MODO` e
  `AZURE_FALA_ENDPOINT`); no Supabase, apague a função `radar-video` (Edge Functions) ou, pelo menos, o segredo
  `RADAR_VIDEO_GITHUB_TOKEN`; no GitHub, **revogue o token fino** "Radar — acionar o corretor de vídeo" (foto do perfil → Settings →
  Developer settings → Personal access tokens → Fine-grained tokens → Delete). As chaves `radar_video_robo` e `radar_video_agenda`
  ficam no Vault de propósito (para reinstalar); para zerar, o `delete` do comentário do `sql/radar-video-agenda-reversao.sql`. Nunca
  regenere as chaves do Azure: a do `artecon-voz` é a mesma da Agenda.
- Enquanto o robô transcreve, o WhatsApp da Agenda pode receber "ocupado" da Azure (o F0 atende um pedido por vez): prefira
  enviar o reel fora do horário de pico do atendimento.

**Da v0.20.0 para a v0.21.0** (instale num **dia útil**, com tempo para o teste da agenda; nesta ordem):

0. Supabase → **Usage**: anote o tamanho atual do banco e o limite do plano. A Pauta guarda no banco as fotos e as lâminas
   aprovadas (até cerca de 450 KB cada; pelo plano até 31/01, no máximo uns 125 MB, pela conta, não medido).
1. A tela nova chega pelo repositório: o `index.html` **e o arquivo novo `radar-pauta.js`**, sempre juntos, na branch principal do
   GitHub; o GitHub Pages publica em 1 a 2 minutos. Aperte **Ctrl+F5 em todos os aparelhos** que usam o Radar (computadores e
   celulares) e confira no rodapé **Radar v0.21.0**. Com a tela nova e o banco antigo, a aba Pauta pede o SQL e o resto funciona
   como antes.
2. SQL Editor → execute `sql/radar-setup-v0.22.0.sql` inteiro (o do pacote; a linha `instalacoes concluidas` mostra a versão do
   script). Ele cria a configuração `pauta` (agenda ligada, 09:30, janela de 6 horas, #Contabilidade e #Palhoça) e acrescenta `"redes": false`
   ao "Honorário contábil" da agenda de obrigações.
3. Edge Functions → `radar-redes` → cole o `index.ts` desta versão e faça o Deploy, com **"Verify JWT" ligado**, como já está.
   Publicações → "Testar conexão com o Instagram e o Facebook": tudo OK, inclusive o item novo "Armazenamento privado da Pauta" (a
   função cria sozinha o `radar-pauta`, privado), e embaixo "Função radar-redes v0.21.0" (com a anterior, aparece o aviso para
   fazer o Deploy).
4. Edge Functions → `radar-ia` → cole o `index.ts` desta versão e faça o Deploy (o painel pede a função `radar-ia` v0.21.0:
   Configurações → Inteligência artificial → Testar a IA deve mostrar v0.21.0). Com a função antiga, o "Gerar com IA" da peça
   avisa que ela é de uma versão anterior; o resto da IA funciona igual.
5. Ctrl+F5 no Radar de novo.
6. SQL Editor → execute `sql/radar-redes-agenda.sql` (item 7 de "Instagram e Facebook pela API da Meta") e faça o **teste**
   `agenda_teste` do comentário do fim do arquivo: copie as linhas **sem os `--`** do começo (não há nada para trocar) e execute; o
   esperado é 200 com `{"ok":true,"versao":"0.21.0"}`. Outra resposta: 404 ou "acao desconhecida", a `radar-redes` não é a v0.21.0
   (passo 3); 401 "Invalid JWT", a chave anon escrita no arquivo não é a deste projeto (a do `radar-config.js`): troque e rode o
   arquivo de novo; nenhuma linha em `net._http_response`, as linhas foram executadas ainda com os `--`. Até este passo, a peça
   aprovada para agendar só sai pelo "Publicar agora".
7. Pauta → **Pessoas e termos** (administrador): cadastre quem vai aparecer, **só com o termo assinado em mãos**, marcando
   exatamente o que a pessoa marcou.
8. Pauta → **Importar o calendário (CSV)**: o arquivo do plano de publicações (guardado no seu computador; nunca no GitHub).
   Confira a prévia e grave.
9. Configurações → **Pauta e agenda automática**: confira a hora padrão, a janela e as hashtags e, se quiser, acrescente os
   `fatos_fixos` (como "desde 1984", com a fonte). Confira também o CNPJ e o CRC em "Fecho, assinatura e identificação legal": sem
   eles, nenhuma peça é aprovada.
   Configurações → **Agenda de obrigações** (uma vez só, antes do 1º domingo, 01/11): em cada obrigação que vai às redes, acrescente
   `"fonte": "<a página oficial do vencimento>"` (por exemplo, a Agenda Tributária da Receita Federal). Nenhuma obrigação vem com a
   fonte: sem ela, "Calcular a agenda da semana" deixa a fonte em branco e a Agenda da semana só fica pronta depois que alguém
   escreve a fonte de cada linha, todo domingo. Desde a v0.22.0, o botão **"Preencher fontes oficiais"** (no mesmo bloco) põe a
   fonte conferida nas obrigações da agenda padrão que estão sem ela.
10. Primeiras peças acompanhadas: a 1ª pela agenda (28/10) com o administrador olhando às 09:30 (até umas 09:35 a peça deve
    aparecer publicada, com o link do post; é a prova de que a Meta aceita o link do armazenamento privado), o 1º carrossel à mão
    (29/10) e os 2 primeiros fins de semana (a partir de 31/10), abrindo a Pauta por volta das 09h35.

O robô atualiza sozinho pelo GitHub (v0.21.0, com o aviso da Pauta); antes do SQL, só o aviso da Pauta não roda, e os outros seguem
normais. Nenhum segredo novo: a chave da agenda é criada no Vault pelo próprio `sql/radar-redes-agenda.sql`.

Cuidados nesta versão:
- O CSV e os `.md` do plano (`1-PLANO-resumo.md`, `2-calendario-…md`, `3-roteiros-dos-reels.md`, `4-serie-pessoas.md`,
  `4b-captacao-mensal.md`, `5-guia-de-producao.md`, `6-regras-legais-e-termo.md`) têm nomes da equipe: **nunca** os envie ao
  GitHub, nem dentro de outra pasta, nem arrastando pelo site ("Add file → Upload files" **não passa pelo `.gitignore`**). O
  `.gitignore` barra qualquer CSV novo e os nomes desses `.md` (com ou sem acento e maiúscula), e o workflow `radar-repositorio.yml`
  roda em todo envio e falha se um calendário ou a tabela das pessoas aparecer no repositório — mas esse aviso chega **depois**: o
  arquivo já ficou público (e no histórico). Confira o que vai em cada envio.
- **Depois da primeira peça aprovada, não volte a tela para a v0.20.0.** A tela antiga não tem a Pauta: não mostra o que está
  agendado nem o que não saiu, não desfaz a aprovação e não tem nas Configurações o bloco que pausa a agenda, que continua
  publicando. A aba Publicações dela também não foi feita para as publicações da Pauta (com o PostgREST dos testes, só faz um pedido
  a mais, sem erro; no Supabase não foi conferido). Para parar a publicação automática, use `"agenda_ligada": false` (Configurações
  → Pauta) ou o `sql/radar-redes-agenda-reversao.sql`. Se precisar mesmo voltar a tela, desfaça antes as aprovações agendadas na
  Pauta e rode o `sql/radar-redes-agenda-reversao.sql`.
- Ordem trocada não publica nada errado: a `radar-redes` antiga (v0.19.0) com o banco novo recusa a peça da Pauta sem publicar
  ("atualize a função radar-redes para a v0.21.0") e continua publicando as notícias; a `radar-redes` nova com o banco antigo
  publica as notícias normalmente. O robô precisa chegar antes do SQL (passo 1 antes do 2): a chave dele deixa de ler
  `radar_imagens`, e o robô novo lê a capa do site pela vista `radar_v_capas` (com o banco antigo, como antes); o robô antigo com o
  banco novo não consegue ler a capa e a publicação da notícia no site para com erro até o GitHub ter a v0.21.0.

**Da v0.19.0 para a v0.20.0:**

0. A tela nova chega pelo repositório: com esta versão na branch principal do GitHub (repositório `radar`), o GitHub Pages
   publica em 1 a 2 minutos. Abra o Radar, aperte Ctrl+F5 e confira no rodapé que aparece **Radar v0.20.0** antes de seguir (se
   ainda aparecer v0.19.0, espere mais um pouco e recarregue).
1. SQL Editor → execute `sql/radar-setup-v0.22.0.sql` inteiro (o do pacote; a linha `instalacoes concluidas` mostra a versão do
   script). Quem usa a função `radar-concorrentes` (v0.19.1, opcional) não precisa rodar de novo o `sql/radar-concorrentes.sql`: o
   setup devolve o acesso da função que confere a chave (para conferir, faça o teste de conexão do fim do
   `sql/radar-concorrentes.sql`, com `{"acao": "diagnostico"}`).
2. Edge Functions → `radar-ia` → cole o `index.ts` desta versão e faça o Deploy (o painel pede a função `radar-ia` v0.20.0:
   Configurações → Inteligência artificial → Testar a IA deve mostrar v0.20.0).
3. Ctrl+F5 no Radar de novo.
4. Configurações → "Fecho, assinatura e identificação legal": o SQL já acrescentou `"cnpj": ""` e `"crc": ""` ao texto; escreva
   entre as aspas o CNPJ (com ou sem pontuação) e o registro da empresa no CRC-SC, com a **letra O** depois da barra (de
   originário), não o número zero, e salve. No caso da Artecon, o texto completo fica assim:
   `{"local": "Palhoça, SC", "empresa": "Artecon Artes Contábeis ME", "responsavel": "Cleiver Gonçalves", "cnpj": "79.876.769/0001-28", "crc": "CRC-SC 007129/O-0"}`.
   Embaixo do campo aparece a linha como vai ao rodapé da arte e ao fim das legendas; confira. Até salvar, a arte e as legendas
   saem só com o nome da empresa (a tela avisa).
5. Antes do primeiro post, confira o link da bio do Instagram: ele deve abrir a página de notícias do site,
   **artecon.cnt.br/news** (a legenda do Instagram termina com "Leia a matéria completa no site (link na bio)").

A função `radar-redes`, os robôs e os segredos não mudam. Sem o SQL, o "Gerar kit das redes com IA" avisa que falta rodar o
SQL (a mensagem da função `radar-ia` v0.21.0 cita o `radar-setup-v0.21.0.sql`: rode o do pacote, `radar-setup-v0.22.0.sql`); com a
função antiga, avisa que ela é de uma versão anterior (o texto e a capa do "Gerar com IA" saem do mesmo jeito).

**Da v0.18.0 para a v0.19.0:** (1) Edge Functions → `radar-ia` e `radar-redes` → cole o `index.ts` de cada uma desta versão e
faça o Deploy ("Verify JWT" ligado nas duas; o painel pede a função `radar-ia` v0.19.0); (2) Supabase → Edge Functions → Secrets →
`RADAR_GITHUB_TOKEN` (veja "Robô do site na hora"); (3) Ctrl+F5 no Radar. O banco não muda (o `radar-setup-v0.19.0.sql` só
registra a versão). O robô de rascunhos e o workflow atualizam sozinhos pelo GitHub.

**Da v0.17.0 para a v0.18.0:** (1) SQL Editor → execute `sql/radar-setup-v0.22.0.sql` (ou a atualização rápida do pacote
zip, que é só a partir da v0.17.0); (2) Edge Functions → `radar-ia` → cole o `index.ts` desta versão e faça o Deploy (o painel
pede a função v0.18.0); (3) Ctrl+F5 no Radar. O robô de rascunhos atualiza sozinho pelo GitHub. Segredos não mudam.

**Da v0.16.0 para a v0.17.0:** (1) SQL Editor → execute `sql/radar-setup-v0.22.0.sql` (ou a atualização rápida do pacote
zip, que é só a partir da v0.16.0); (2) Edge Functions → `radar-redes` → cole o `index.ts` desta versão e faça o Deploy (com
**Verify JWT ligado**, como já está); (3) Ctrl+F5 no Radar. O robô e o workflow atualizam sozinhos pelo GitHub. Segredos não mudam
(o robô chama a função `radar-redes` com a mesma chave interna que já usa no banco, RADAR_SUPABASE_SERVICE_KEY).

**Da v0.15.0 para a v0.16.0:** (1) SQL Editor → execute `sql/radar-setup-v0.22.0.sql` (ou a atualização rápida do pacote
zip, que é só a partir da v0.15.0); (2) Edge Functions → `radar-ia` → cole o `index.ts` desta versão e faça o Deploy (o painel
pede a função v0.16.0 para o botão "Revisar com IA"); (3) Ctrl+F5 no Radar. O robô atualiza sozinho pelo GitHub. Segredos não mudam.

**Da v0.14.3 (ou v0.14.4) para a v0.15.0:** (1) SQL Editor → execute `sql/radar-setup-v0.15.0.sql` (ou a atualização
rápida do pacote zip, que é só a partir da v0.14.3; no fim ela mostra `capturas com fundamentacao lida`, que deve ser "N de N");
(2) Ctrl+F5 no Radar. Robô, funções e segredos não mudam. De versões anteriores, use o `radar-setup-v0.15.0.sql` inteiro.

**Da v0.11.1 para a v0.12.0:** (1) SQL Editor → execute `sql/radar-setup-v0.22.0.sql` (ou a atualização rápida do pacote
zip); (2) Edge Functions → crie a função `radar-itc` com o `index.ts` desta versão (com **Verify JWT desligado**: a função confere
sozinha quem chama); (3) siga "Boletim da ITC pelo Microsoft Graph"; (4) Ctrl+F5 no Radar.

**Da v0.11.0 para a v0.11.1:** (1) SQL Editor → execute `sql/radar-setup-v0.22.0.sql` (ou o arquivo de atualização rápida
que vem no pacote zip); (2) Edge Functions → `radar-ia` → cole o `index.ts` desta versão e faça o Deploy; (3) Ctrl+F5 no Radar.
Os workflows e os robôs chegam pelo repositório. Nada de segredo novo.

**Da v0.10.0 para a v0.11.0:** (1) SQL Editor → execute o SQL da versão (ou o arquivo de atualização rápida do pacote zip);
(2) Edge Functions → `radar-ia` → cole o `index.ts` desta versão e faça o Deploy; (3) Ctrl+F5 no Radar. Ao aplicar, as
capturas da fila com mais de 5 dias passam a "Baixa relevância" (continuam lá; dá para ignorar em lote).

**Da v0.9.0 para a v0.10.0**, nesta ordem: (1) Supabase radar-artecon → SQL Editor → execute
`sql/radar-setup-v0.22.0.sql` inteiro (a linha `instalacoes concluidas` mostra a versão do script);
(2) Edge Functions → `radar-ia` → cole o `supabase/functions/radar-ia/index.ts` desta versão e faça o Deploy
(Configurações → Inteligência artificial → Testar deve mostrar a função v0.10.0); (3) a tela e os robôs chegam
pelo repositório (Ctrl+F5 no Radar). Segredos: `ARTECON_SITE_USUARIO` e `ARTECON_SITE_SENHA` já cadastrados.

**Da v0.8.0 para a v0.9.0:** Supabase radar-artecon → SQL Editor → execute
`sql/radar-setup-v0.22.0.sql` inteiro (a linha `instalacoes concluidas` mostra a versão do script).
A tela e o robô chegam pelo repositório. A função `radar-ia` não muda. Nada de segredo novo.

**Da v0.7.1 para a v0.8.0:** Supabase radar-artecon → SQL Editor → execute
`sql/radar-setup-v0.22.0.sql` inteiro (a linha `instalacoes concluidas` deve mostrar a versão) e,
se ainda não rodou, `sql/radar-fontes-novas-2026-10.sql`. A tela e o robô chegam pelo repositório.
A função `radar-ia` não muda. Para o DOU completo (INLABS), veja "Diário Oficial pelo INLABS".

**Da v0.7.0 para a v0.7.1:** Supabase radar-artecon → SQL Editor → cole e execute
`sql/radar-setup-v0.22.0.sql` inteiro (o nome muda a cada versão) e guarde a evidência (a linha `instalacoes concluidas` mostra
a versão do script). O resto já chega pelo repositório: a tela (GitHub Pages; Ctrl+F5 no Radar) e o
robô (próxima coleta). A função `radar-ia` não muda. Antes do SQL, o robô novo funciona normalmente,
só sem a limpeza de imagens; os termos com pontuação nas regras só passam a pontuar depois dele.

**Da v0.6.1 para a v0.7.0**, nesta ordem:

1. Supabase radar-artecon → SQL Editor → execute o SQL da versão (hoje, `sql/radar-setup-v0.22.0.sql`). Guarde a evidência.
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

**Da v0.5.0 para a v0.6.0:** (1) execute `radar-setup-v0.22.0.sql` no SQL Editor; (2) envie
`index.html` e `informativo.html` ao repositório; (3) cole o `radar-fale-conosco-v0.6.0.json`
em Configurações → Fale Conosco; (4) se usa a IA, cole de novo o `index.ts` na função
`radar-ia` e faça o Deploy. O robô não mudou de comportamento (só o número da versão).

Se você já instalou uma versão anterior: execute `sql/radar-setup-v0.22.0.sql` no SQL
Editor (ele atualiza sem apagar dados), envie os arquivos novos ao repositório e, se a função de IA
já estiver instalada, cole de novo o `index.ts`.

Substitua `index.html`, `radar-pauta.js` (desde a v0.21.0, sempre junto com o `index.html`), `radar-video.js` (desde a v0.22.0,
também junto), `informativo.html`, as imagens do
timbrado e as pastas `robo/`, `sql/`, `testes/`, `supabase/` e `.github/`. Se a função de IA mudar, cole de novo o `index.ts` no Supabase. **Não** substitua o `radar-config.js`. Se a versão trouxer um novo
`radar-setup`, execute-o no SQL Editor. A versão em uso aparece no topo do dashboard e
a aba **Versões** lista o que mudou.

## Ideias anotadas para o futuro

Pedidos do escritório para quando chegar a hora (não implementados):

- **Instagram (05/10/2026):** quando o Radar for integrado ao Instagram, ver a possibilidade de
  **buscar o que mais está sendo publicado** sobre os temas do escritório (hashtags e perfis de
  contabilidade e tributação), para sugerir assuntos e comparar com o que o Radar já capturou.

## Rodar os testes

No GitHub: Actions → "Radar — testes". Localmente: PostgreSQL 16, `postgrest` no PATH,
`deno` no PATH, `pip install playwright && playwright install chromium` e
`python -m pytest testes -q`.

Os testes do corretor de vídeo (v0.22.0, `testes/test_radar_video_*.py`) precisam também do `ffmpeg` (o 6.1 do Ubuntu 24.04, o mesmo
do robô) e do Python do robô, com hash: `pip install --require-hashes --no-deps -r robo/video/requirements.txt` (sem o Speech SDK,
os 3 testes com o SDK de verdade são pulados, com o motivo). Os 2 testes do contêiner montam a imagem `robo/video/Dockerfile` com o
`docker` (sem ele, ou com o Docker Hub recusando, são pulados). Nenhum teste chama a Azure, o GitHub ou o Supabase de verdade: a Azure
e a função são simuladas em `127.0.0.1`, e os vídeos e as vozes são **sintéticos**, gerados na hora numa pasta temporária. Os testes
não podem rodar em paralelo (as portas são fixas).
