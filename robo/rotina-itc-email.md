# Rotina diária — boletim da ITC Consultoria (e-mail → Radar)

Roda todo dia às 02h55 (horário de Brasília), numa sessão nova do Claude Code com os conectores
**Microsoft 365** (ler o e-mail) e **Supabase** (gravar no banco). Nada é gravado no repositório,
que é público: as matérias vão direto para o banco pela função `radar_receber_email`
(criada por `sql/radar-fontes-novas-2026-10.sql`). A rotina não abre aviso, não manda e-mail
nem mensagem: as matérias só aparecem na tela do Radar, com a nota de relevância de sempre.

## Texto da rotina

```
Tarefa diária do Radar Artecon: copiar para o banco as matérias do boletim da ITC Consultoria.

1. No Outlook (conector Microsoft 365), procure os e-mails do remetente itc@itcnet.com.br
   recebidos nas últimas 26 horas. São três tipos: "ITCNET Mail", "LEGISLAÇÃO & TRIBUNAIS -
   Destaques do Dia" e "Edição Extra". Não marque como lido, não mova, não responda.
2. Em cada e-mail, leia o corpo e separe cada matéria: título (a manchete), área (o cabeçalho
   da seção, ex.: "Área Federal", "Área Trabalhista e Previdenciária", "Área Estadual"), texto
   (o parágrafo de chamada que vem logo abaixo da manchete, sem alterar) e data (a data do
   boletim, AAAA-MM-DD). Não guarde links do e-mail (são links de rastreio pessoais).
   Fica de fora (para não encher o Radar): "Capacitação profissional" (cursos, "AO VIVO",
   "CURSO PRESENCIAL"), "Artigos/Matérias - Últimas Publicações", "Vencimentos", "Nota ITC",
   rodapé e "Visualizar este e-mail como página web". Nas áreas estaduais (notícias e
   legislação), só Santa Catarina (SC) e o que vale para todos os estados; ignore os outros
   estados. Na "Legislação Federal - Últimas Publicações", cada ato conta como matéria:
   título = o nome do ato, ex.: "Lei nº 15526/2026 (DOU DE 30/09/2026)"; texto = a ementa.
   Subtítulos de local ("Todos os Municípios", "Santa Catarina") não são matérias.
3. No Supabase (projeto radar-artecon, id jhxlsvzvqvufyhkjnmeq), execute uma única chamada:
   select public.radar_receber_email('itc-email', '<lista JSON>'::jsonb);
   onde a lista é [{"titulo": "...", "data": "AAAA-MM-DD", "area": "...", "texto": "...",
   "assunto_email": "<assunto do e-mail>"}, ...]. Escape aspas simples dobrando-as ('').
   A função ignora repetidas (a mesma manchete nos dois boletins entra uma vez).
4. Se não houver e-mail da ITC no período, não faça nada. Não altere nenhuma outra tabela,
   não rode outro SQL, não crie arquivos no repositório, não abra PR nem issue.
5. Termine com uma linha: quantos e-mails lidos, quantas matérias enviadas e o retorno da função.
```

## Como criar (uma vez)

Feito em 05/10/2026: Supabase conectado ao Claude, `sql/radar-fontes-novas-2026-10.sql`
aplicado no banco e rotina "Radar — boletim ITC (e-mail)" criada (agenda
`CRON_TZ=America/Sao_Paulo 55 2 * * *`, sessão nova a cada execução, conectores Microsoft 365
e Supabase, sem notificação). Para pausar: claude.ai → Code → Rotinas, ou peça ao Claude.
