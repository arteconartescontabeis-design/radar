# Radar Artecon — Relatório de testes (v0.4.0)

Data: 02/10/2026. Resultado: **313 testes automatizados, 313 aprovados** (suíte executada
duas vezes seguidas, sem falha intermitente).

Além da suíte, o código passou por seis rodadas de revisão independente (duas do banco e
do robô, duas das telas, uma da IA e uma do Informativo Mensal), que tentaram quebrar as
regras por experimento. Os
defeitos encontrados foram corrigidos e viraram teste.

## O que foi testado

| Grupo | Testes | Como |
|---|---:|---|
| Banco: instalação, atualização da v0.1.0, permissões, fundamentação, aprovação, publicação, auditoria, uso da IA, imagens, configurações e informativo | 110 | PostgreSQL 16 local, com os papéis e os privilégios padrão do Supabase reproduzidos |
| Leitores das fontes e utilidades | 69 | amostras no formato de cada fonte e os **endereços, títulos e datas reais** lidos em 02/10/2026 |
| Robô de ponta a ponta: robô → API → banco | 26 | PostgREST real (o motor de API do Supabase) e "sites" simulados |
| Telas, IA, Informativo Mensal e PDF em navegador (Chromium) | 108 | banco e API reais; a função de IA rodando de verdade (Deno); login do Supabase e OpenAI simulados |

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
  recusa o que não for JPG, PNG ou WebP; o visitante só baixa imagem de publicação no ar.
- **Cópia para o site:** título e texto vão para a área de transferência com subtítulos,
  negrito, lista e tabela.
- **Segurança:** HTML digitado em título, texto, tabela, autor, fonte, agenda e
  configurações aparece como texto nas três páginas; nada executa.

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
| OpenAI de verdade | sem chave; os testes usam uma OpenAI simulada. A qualidade do texto gerado, os nomes dos modelos padrão e o formato exato da API não foram exercitados contra o serviço real | primeiro uso no Passo 7 |
| Função de IA dentro do Supabase | aqui ela roda no Deno local; limites de tempo e de memória da plataforma não foram medidos | primeiro uso no Passo 7 |
| HTML real dos sites lido pelo robô | ambiente sem acesso direto aos sites | diagnóstico (Passo 1) |
| Login contra o Supabase Auth de verdade | sem acesso ao seu projeto | primeiro acesso (Passo 6) |
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
na página pública.

As correções das duas últimas rodadas (IA e Informativo) foram cobertas por testes, mas não
passaram por uma segunda revisão independente.

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
8. **Edição fechada não guarda cópia dos artigos:** o registro definitivo é o PDF salvo.
   Alteração posterior é avisada, não impedida.
9. **Imagens substituídas ficam no banco** sem uso; não há tela de limpeza.
10. **Tabela no texto:** o caractere "|" sempre separa colunas (não dá para usá-lo dentro
    de uma célula) e a linha de título não se repete quando a tabela atravessa a página.
11. **Número sugerido da nova edição** considera o ano corrente; se o mês escolhido for de
    outro ano, ajuste o número à mão.
12. **Envio de imagem que falha no meio** pode deixar uma imagem sem uso no banco.
