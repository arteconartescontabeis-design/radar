"""Radar Artecon — avisos por e-mail: fonte com falha e link publicado fora do ar ou com texto diferente (v0.8.0).

Depois da coleta, abre um aviso (issue) no repositório do GitHub para cada fonte ativa que falhou
3 vezes seguidas. O GitHub manda e-mail ao dono do repositório quando um aviso é aberto, então não
é preciso serviço de e-mail. Um aviso por fonte: enquanto ele estiver aberto, nada novo é criado.
Quando a fonte volta a funcionar (ou é desligada na aba Fontes), o aviso é fechado com um comentário.

Também confere os links registrados em "Publicações no site": o que responder 404 ou 410 (página
que não existe mais) abre um aviso; quando o link volta a abrir, ou o registro é corrigido ou
excluído, o aviso fecha. Erro de rede ou do site (tempo esgotado, 5xx) não conta: pode ser passageiro.

Fonte ativa que ficou mais de 3 ciclos sem rodar ("atrasada") também abre aviso (v0.9.0). É o vigia da
rotina diária do boletim da ITC, que não passa pelo robô: se ela parar, o aviso chega em até 3 dias.

E confere, nas notícias do próprio site da Artecon, se a página ainda traz o texto que foi aprovado e
registrado (v0.8.0): se mais da metade das palavras sumiu, abre o aviso "texto do site diferente do
aprovado"; ele fecha quando o texto volta, ou o registro é corrigido ou excluído.

E a Pauta (v0.21.0): enquanto houver publicação agendada que não saiu (com erro, parada em "enviando" ou com
a hora passada sem sair), fica aberto UM aviso só, "publicação agendada não saiu". O corpo nunca é editado
(cada edição seria mais um e-mail) e leva só a quantidade e a data, o canal e o número da mais antiga: nunca o
assunto, o nome de quem aparece, a legenda ou o erro (o repositório é público). Fecha quando a lista esvazia.
v0.22.0 (rodada 2 da varredura geral): a publicação que entra na lista com o aviso já aberto ganha UM comentário
(um e-mail), com o mesmo tanto de informação; antes, um erro antigo deixado sem resolver calava todas as falhas
seguintes. Os números já avisados ficam numa marca escondida no corpo e nos comentários do robô.

E a agenda de obrigações (v0.30.0): enquanto houver notícia dos últimos 30 dias que fala em prorrogar ou adiar o prazo de uma
obrigação da agenda e que o administrador ainda não marcou como conferida (radar_prorrogacoes, a mesma regra da tela), fica aberto
UM aviso só, "possível prorrogação na agenda de obrigações", do mesmo jeito do da Pauta: o corpo nunca é editado, cada notícia nova
ganha um comentário (no máximo um por rodada) e ele fecha quando nenhuma espera conferência. O Radar não muda nenhuma data sozinho.
O repositório é público: das notícias de sites públicos vão a obrigação, o título, o link e a fonte (como no resumo semanal); as do
boletim da ITC aparecem só como contagem (nunca a obrigação, o título nem o endereço).

Uso (no workflow, depois da coleta):
    python radar_alertas.py
Variáveis: SUPABASE_URL, SUPABASE_SERVICE_KEY, GITHUB_TOKEN e GITHUB_REPOSITORY (o Actions preenche
as duas últimas). Sem elas, não faz nada. Nunca deixa a coleta vermelha: erros só vão para o log.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

import radar_site
from radar_banco import Banco, ErroBanco
from radar_util import BRASILIA, ErroDownload, baixar

PREFIXO = "Radar: fonte com falha — "
PREFIXO_LINK = "Radar: link publicado fora do ar — "
PREFIXO_TEXTO = "Radar: texto do site diferente do aprovado — "
PREFIXO_PARADA = "Radar: fonte parada — "
PREFIXO_PAUTA = "Radar: publicação agendada não saiu"        # v0.21.0: um aviso só para toda a Pauta (o título é só isso)
PREFIXO_PRORROGACAO = "Radar: possível prorrogação na agenda de obrigações"   # v0.30.0: um aviso só (o título é só isso)
PREFIXOS_PADRAO = (PREFIXO, PREFIXO_LINK, PREFIXO_TEXTO, PREFIXO_PARADA, PREFIXO_PAUTA,
                   PREFIXO_PRORROGACAO)                                    # os avisos que o executar() abre e fecha
# v0.22.0 (varredura geral): o login com que a API mostra o autor das issues abertas pelo GITHUB_TOKEN dos workflows (o robô)
AUTOR_DOS_AVISOS = "github-actions[bot]"
FORA_DO_AR = (404, 410)
CANAIS = {"instagram": "Instagram", "facebook": "Facebook"}
try:
    FUSO = ZoneInfo("America/Sao_Paulo")                     # a hora da peça é de Brasília, como no banco e na tela
except ZoneInfoNotFoundError:                                # sistema sem a base de fusos: Brasília não tem horário de verão
    FUSO = BRASILIA
FALHAS_PARA_AVISAR = 3
# v0.22.0 (rodada 2): os números dos envios da Pauta já avisados, numa marca que não aparece no aviso nem no e-mail (comentário HTML)
MARCA_PAUTA = re.compile(r"<!-- radar-pauta-avisados: ([0-9 ]*) -->")
# v0.30.0: os números das capturas já avisadas no aviso de possível prorrogação (a mesma ideia da marca da Pauta)
MARCA_PRORROGACAO = re.compile(r"<!-- radar-prorrogacao-avisadas: ([0-9 ]*) -->")
MAX_PRORROGACOES = 20          # notícias de sites públicos listadas por corpo ou comentário (as outras: "e mais N — veja no Radar")
API = "https://api.github.com"


def titulo(slug: str) -> str:
    return PREFIXO + slug


def corpo_aviso(f: dict) -> str:
    sucesso = f.get("ultimo_sucesso_em") or "nunca"
    return (f"A fonte **{f.get('nome') or f['slug']}** (`{f['slug']}`) falhou nas últimas "
            f"**{f.get('falhas_consecutivas')}** coletas seguidas.\n\n"
            f"- Último erro: {str(f.get('ultimo_erro') or '—')[:500]}\n"
            f"- Último sucesso: {sucesso}\n\n"
            "O que fazer:\n"
            "1. No Radar, aba **Fontes**: veja a observação da fonte em \"Últimas execuções do robô\".\n"
            "2. GitHub → Actions → \"Radar — diagnóstico das fontes\" → Run workflow: o relatório mostra "
            "como a página está montada hoje.\n"
            "3. Se o site mudou, ajuste em Fontes → Configurar; se a fonte não serve mais, desmarque "
            "\"Fonte ativa\".\n\n"
            "Este aviso fecha sozinho quando a fonte voltar a funcionar ou for desligada.")


def decidir(saude: list[dict], abertos: dict[str, int]) -> tuple[list[dict], list[tuple[int, str]]]:
    """Devolve (fontes para abrir aviso, [(número do aviso, motivo do fechamento)])."""
    abrir, fechar = [], []
    por_slug = {f["slug"]: f for f in saude}
    for f in saude:
        if f.get("ativo") and (f.get("falhas_consecutivas") or 0) >= FALHAS_PARA_AVISAR and titulo(f["slug"]) not in abertos:
            abrir.append(f)
    for t, numero in abertos.items():
        if not t.startswith(PREFIXO):
            continue
        slug = t[len(PREFIXO):]
        f = por_slug.get(slug)
        if f is None:
            fechar.append((numero, "A fonte não existe mais no Radar."))
        elif not f.get("ativo"):
            fechar.append((numero, "A fonte foi desligada na aba Fontes."))
        elif (f.get("falhas_consecutivas") or 0) == 0:
            fechar.append((numero, f"A fonte voltou a funcionar (último sucesso: {f.get('ultimo_sucesso_em')})."))
    return abrir, fechar


def corpo_parada(f: dict) -> str:
    sucesso = f.get("ultimo_sucesso_em") or "nunca"
    if (f.get("config") or {}).get("origem") == "email":
        oque = ("A rotina diária que lê o boletim no e-mail e grava no Radar não rodou nos últimos dias.\n\n"
                "O que fazer: peça ao Claude, na conversa do Radar, para conferir a rotina do boletim "
                "(Outlook e Supabase conectados, rotina ligada).")
    else:
        oque = ("O robô não conseguiu passar por ela no prazo esperado.\n\n"
                "O que fazer: GitHub → Actions → \"Radar — coleta\": confira se as coletas estão rodando.")
    return (f"A fonte **{f.get('nome') or f['slug']}** (`{f['slug']}`) está parada: último funcionamento em {sucesso}.\n\n"
            f"{oque}\n\nEste aviso fecha sozinho quando a fonte voltar a funcionar ou for desligada.")


def decidir_paradas(saude: list[dict], abertos: dict[str, int]) -> tuple[list[dict], list[tuple[int, str]]]:
    """Fonte ativa "atrasada" (passou de 3 ciclos sem funcionar): abre um aviso; fecha quando volta ou é desligada."""
    abrir, fechar = [], []
    por_slug = {f["slug"]: f for f in saude}
    for f in saude:
        if f.get("ativo") and f.get("saude") == "atrasada" and PREFIXO_PARADA + f["slug"] not in abertos:
            abrir.append(f)
    for t, numero in abertos.items():
        if not t.startswith(PREFIXO_PARADA):
            continue
        f = por_slug.get(t[len(PREFIXO_PARADA):])
        if f is None:
            fechar.append((numero, "A fonte não existe mais no Radar."))
        elif not f.get("ativo"):
            fechar.append((numero, "A fonte foi desligada na aba Fontes."))
        elif f.get("saude") != "atrasada":
            fechar.append((numero, f"A fonte voltou a funcionar (último sucesso: {f.get('ultimo_sucesso_em')})."
                           if f.get("saude") != "falhando" else
                           "A fonte voltou a rodar, mas com falhas: o aviso de fonte com falha cuida dela daqui em diante."))
    return abrir, fechar


def _hora(valor) -> datetime | None:
    """Data e hora de um campo timestamptz do banco, em Brasília (None se vazio ou ilegível)."""
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).astimezone(FUSO) if valor else None
    except (TypeError, ValueError):
        return None


def _mais_antiga(problemas: list[dict]) -> str:
    """A data e hora de Brasília, o canal e o número do envio mais antigo da lista (nada mais: o repositório é público)"""
    datadas = [(h, e) for e in problemas if (h := _hora(e.get("agendado_para")))]
    h, e = min(datadas, key=lambda x: (x[0], x[1]["id"])) if datadas else (None, min(problemas, key=lambda x: x["id"]))
    return (f"{h:%d/%m/%Y %H:%M}, " if h else "") + f"{CANAIS.get(e.get('canal'), str(e.get('canal') or '—'))}, nº {e['id']}"


def marca_pauta(ids) -> str:
    """A marca escondida com os números dos envios já avisados (rodada 2), no fim do corpo ou do comentário"""
    return "\n\n<!-- radar-pauta-avisados: " + " ".join(str(i) for i in sorted(set(ids))) + " -->"


def avisados_pauta(textos: list[str]) -> set[int]:
    """Os números já avisados, das marcas do corpo e dos comentários do robô (o aviso aberto antes desta versão não tem marca:
    a primeira rodada comenta a lista toda, uma vez)"""
    return {int(n) for t in textos for m in MARCA_PAUTA.finditer(t or "") for n in m.group(1).split()}


def corpo_pauta(problemas: list[dict]) -> str:
    """Corpo do aviso da Pauta (v0.21.0): só a quantidade e a mais antiga (data e hora de Brasília, canal e número do envio). Nunca
    o assunto, o nome de quem aparece, a legenda ou o texto do erro: o repositório é público, e o corpo não muda depois de aberto."""
    ref = _mais_antiga(problemas)
    if len(problemas) == 1:
        abre = f"**1** publicação da Pauta não saiu ou está atrasada ({ref})."
    else:
        abre = f"**{len(problemas)}** publicações da Pauta não saíram ou estão atrasadas (a mais antiga: {ref})."
    return (f"{abre}\n\n"
            "O que fazer: abra o Radar → **Pauta** → **Não saíram**. Lá aparecem o motivo de cada uma e o que fazer "
            "(Publicar agora, Tentar de novo, Não publicar neste canal ou Desfazer aprovação). Se nada sai pela agenda, confira "
            "Publicações → Testar conexão e Configurações → Pauta (\"agenda_ligada\").\n\n"
            "Este aviso não é editado depois de aberto (cada mudança mandaria outro e-mail): cada publicação nova que não sair ganha "
            "um comentário aqui, e a lista do momento está sempre na Pauta. Ele fecha sozinho quando nenhuma publicação da Pauta "
            "estiver parada ou com erro." + marca_pauta(e["id"] for e in problemas))


def comentario_pauta(problemas: list[dict], avisados: set[int]) -> str | None:
    """v0.22.0 (rodada 2 da varredura geral): com o aviso da Pauta aberto, a publicação que entrou na lista e ainda não foi avisada
    ganha UM comentário (um e-mail por rodada, com o mesmo tanto de informação do corpo); None se não há novidade. A marca do
    comentário leva os já avisados e os de agora."""
    novas = [e for e in problemas or [] if e["id"] not in avisados]
    if not novas:
        return None
    ref = _mais_antiga(novas)
    abre = (f"**1** publicação nova da Pauta não saiu ou está atrasada ({ref})." if len(novas) == 1 else
            f"**{len(novas)}** publicações novas da Pauta não saíram ou estão atrasadas (a mais antiga: {ref}).")
    return (f"{abre} Ao todo, {len(problemas)} na lista agora.\n\n"
            "O que fazer: abra o Radar → **Pauta** → **Não saíram**." + marca_pauta(avisados | {e["id"] for e in problemas}))


def decidir_pauta(problemas: list[dict] | None, abertos: dict[str, int]) -> tuple[str | None, list[tuple[int, str]]]:
    """Um aviso só para toda a Pauta (v0.21.0): abre quando há publicação que não saiu e nenhum aviso aberto; fecha quando a lista
    esvazia; nunca edita o corpo. Devolve (corpo do aviso a abrir, ou None; [(número, motivo) para fechar]). `problemas` None
    (banco ainda sem o SQL da v0.21.0): não abre nem fecha."""
    meus = sorted(n for t, n in abertos.items() if t.startswith(PREFIXO_PAUTA))
    if problemas is None:
        return None, []
    if problemas:
        return (None if meus else corpo_pauta(problemas)), []
    return None, [(n, "Nenhuma publicação da Pauta está parada ou com erro agora (saiu, foi remarcada, ficou sem aquele canal "
                      "ou a aprovação foi desfeita).") for n in meus]


# ------------------------------------------------- v0.30.0: possível prorrogação na agenda de obrigações
def marca_prorrogacao(ids) -> str:
    """A marca escondida com os números das capturas já avisadas, no fim do corpo ou do comentário"""
    return "\n\n<!-- radar-prorrogacao-avisadas: " + " ".join(str(i) for i in sorted(set(ids))) + " -->"


def avisadas_prorrogacao(textos: list[str]) -> set[int]:
    """Os números já avisados, das marcas do corpo e dos comentários do robô"""
    return {int(n) for t in textos for m in MARCA_PRORROGACAO.finditer(t or "") for n in m.group(1).split()}


def pendentes_prorrogacao(lista: list[dict] | None) -> list[dict]:
    """As que o administrador ainda não marcou como conferidas (as de mais de 30 dias já não vêm do banco)"""
    return [p for p in lista or [] if not p.get("conferida")]


def _texto_publico(t, limite: int = 200) -> str:
    """Título, fonte ou nome da obrigação de site público, como vão ao aviso (repositório público): numa linha só, sem os caracteres que
    mudariam o aviso ("<" e ">" de uma marca escondida, colchetes e crase do Markdown) e sem "@" (que chamaria alguém do GitHub)"""
    s = re.sub(r"\s+", " ", re.sub(r"[<>\[\]`|*_]", " ", str(t or ""))).strip().replace("@", "(a)")
    return s if len(s) <= limite else s[:limite - 1].rstrip() + "…"


def _linha_prorrogacao(p: dict) -> str:
    """Uma notícia de site público: as obrigações, o título com o link, a fonte e a data (dd/mm/aaaa)"""
    url = str(p.get("url") or "")
    titulo = _texto_publico(p.get("titulo")) or "notícia"
    link = f"[{titulo}]({url})" if re.fullmatch(r"https?://[^\s<>()\[\]\"'`]+", url) else titulo
    quando = str(p.get("data_publicacao") or p.get("capturado_em") or "")[:10]
    data = f" ({quando[8:10]}/{quando[5:7]}/{quando[:4]})" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", quando) else ""
    return (f"- **{_texto_publico('; '.join(p.get('obrigacoes') or []), 300)}**: {link} — "
            f"{_texto_publico(p.get('fonte')) or 'fonte'}{data}")


def _lista_prorrogacoes(itens: list[dict]) -> str:
    """As de sites públicos (até MAX_PRORROGACOES) e, das do boletim da ITC, só a contagem"""
    publicas = [p for p in itens if not p.get("do_email")]
    do_email = len(itens) - len(publicas)
    linhas = [_linha_prorrogacao(p) for p in publicas[:MAX_PRORROGACOES]]
    if len(publicas) > MAX_PRORROGACOES:
        linhas.append(f"- e mais {len(publicas) - MAX_PRORROGACOES} — veja no Radar")
    if do_email:
        linhas.append(f"- Mais {do_email} do boletim da ITC — veja no Radar (o conteúdo do boletim não é reproduzido aqui)")
    return "\n".join(linhas)


def corpo_prorrogacao(pendentes: list[dict], ja_avisadas: set[int] = frozenset()) -> str | None:
    """Corpo do aviso (v0.30.0). O repositório é público: das notícias de sites públicos, a obrigação, o título com o link, a fonte e
    a data; do boletim da ITC, só a contagem. O corpo não muda depois de aberto. `ja_avisadas`: as notícias que um aviso anterior (já
    fechado, por exemplo à mão no GitHub) avisou: não entram de novo (uma vez por notícia); None se não sobra nenhuma nova."""
    novas = [p for p in pendentes if p["captura_id"] not in ja_avisadas]
    if not novas:
        return None
    n = len(novas)
    abre = ("O Radar captou **1** notícia que fala em prorrogar ou adiar o prazo de uma obrigação da agenda de obrigações"
            if n == 1 else f"O Radar captou **{n}** notícias que falam em prorrogar ou adiar o prazo de uma obrigação da agenda de "
                            "obrigações")
    antes = (f" Ao todo, {len(pendentes)} esperando conferência no Radar (as outras já foram avisadas num aviso anterior)."
             if len(pendentes) > n else "")
    return (f"{abre} (usada no Informativo Mensal e na agenda da semana da Pauta). O Radar **não muda a data sozinho**.{antes}\n\n"
            f"{_lista_prorrogacoes(novas)}\n\n"
            "O que fazer: abra o Radar → **Painel** → \"Possível prorrogação de prazo\" e confira na fonte oficial. Se o prazo mudou, "
            "ponha a nova data na obrigação (Configurações → Agenda de obrigações, \"prorrogacoes\") e confira as edições do "
            "Informativo e a agenda da semana da Pauta já montadas. Depois, clique em **Conferido**.\n\n"
            "Este aviso não é editado depois de aberto (cada mudança mandaria outro e-mail): cada notícia nova ganha um comentário aqui. "
            "Ele fecha sozinho quando nenhuma estiver esperando conferência (conferidas no Radar ou com mais de 30 dias). Fechar o aviso "
            "aqui no GitHub não tira a notícia do Painel (só o \"Conferido\" tira), e o Radar não avisa de novo a mesma notícia."
            + marca_prorrogacao(set(ja_avisadas) | {p["captura_id"] for p in pendentes}))


def comentario_prorrogacao(pendentes: list[dict], avisadas: set[int]) -> str | None:
    """Com o aviso aberto, as notícias que ainda não foram avisadas ganham UM comentário (um e-mail por rodada); None se não há
    novidade. A marca do comentário leva as já avisadas e as de agora."""
    novas = [p for p in pendentes or [] if p["captura_id"] not in avisadas]
    if not novas:
        return None
    abre = ("**1** notícia nova fala em prorrogar ou adiar o prazo de uma obrigação da agenda." if len(novas) == 1 else
            f"**{len(novas)}** notícias novas falam em prorrogar ou adiar o prazo de uma obrigação da agenda.")
    return (f"{abre} Ao todo, {len(pendentes)} esperando conferência.\n\n{_lista_prorrogacoes(novas)}\n\n"
            "O que fazer: abra o Radar → **Painel** → \"Possível prorrogação de prazo\". O Radar não muda a data sozinho."
            + marca_prorrogacao(avisadas | {p["captura_id"] for p in pendentes}))


def decidir_prorrogacao(lista: list[dict] | None, abertos: dict[str, int],
                        ja_avisadas: set[int] = frozenset()) -> tuple[str | None, list[tuple[int, str]]]:
    """Um aviso só (v0.30.0), como o da Pauta: abre quando há notícia esperando conferência e nenhum aviso aberto; fecha quando nenhuma
    espera; nunca edita o corpo. `lista` None (banco ainda sem o SQL da v0.30.0): não abre nem fecha. `ja_avisadas` (as da marca do
    último aviso fechado): sem notícia nova fora delas, não abre outro (o aviso fechado à mão no GitHub não volta a cada rodada)."""
    meus = sorted(n for t, n in abertos.items() if t.startswith(PREFIXO_PRORROGACAO))
    if lista is None:
        return None, []
    pendentes = pendentes_prorrogacao(lista)
    if pendentes:
        return (None if meus else corpo_prorrogacao(pendentes, ja_avisadas)), []
    return None, [(n, "Nenhuma possível prorrogação esperando conferência (conferidas no Radar ou com mais de 30 dias).") for n in meus]


def titulo_link(url: str) -> str:
    return (PREFIXO_LINK + url)[:250]


def corpo_link(reg: dict, status: int) -> str:
    return (f"O link registrado em **Publicações no site** para \"{reg.get('titulo') or '—'}\" "
            f"respondeu **HTTP {status}** (página não encontrada):\n\n{reg['url']}\n\n"
            "O que fazer: confira se a notícia foi retirada ou mudou de endereço no site da Artecon. "
            "No Radar, aba **Publicações**, use \"Corrigir link\" (ou exclua o registro, se a notícia saiu do ar "
            "de propósito).\n\nEste aviso fecha sozinho quando o link voltar a abrir ou o registro for corrigido.")


def conferir_links(registros: list[dict], status_de) -> dict[str, tuple[dict, int]]:
    """{link: (registro mais novo com ele, status HTTP)} só dos links fora do ar. Cada link é acessado uma vez;
    `status_de(url)` devolve o status ou None (erro de rede, que não conta)."""
    por_url: dict[str, dict] = {}
    for r in registros:
        url = r.get("url") or ""
        if url.startswith(("http://", "https://")) and (url not in por_url or r["id"] > por_url[url]["id"]):
            por_url[url] = r
    fora = {}
    for url, reg in por_url.items():
        st = status_de(url)
        if st in FORA_DO_AR:
            fora[url] = (reg, st)
    return fora


def decidir_links(registros: list[dict], fora: dict[str, tuple[dict, int]], abertos: dict[str, int]):
    """Um aviso por link. Devolve ([(registro, status) para abrir], [(número, motivo) para fechar])."""
    abrir = [(reg, st) for url, (reg, st) in fora.items() if titulo_link(url) not in abertos]
    em_uso = {titulo_link(r["url"]) for r in registros if r.get("url")}
    fora_titulos = {titulo_link(url) for url in fora}
    fechar = []
    for t, numero in abertos.items():
        if not t.startswith(PREFIXO_LINK) or t in fora_titulos:
            continue
        fechar.append((numero, "O link voltou a abrir." if t in em_uso else "O link não está mais registrado no Radar (corrigido ou excluído)."))
    return abrir, fechar


def titulo_texto(url: str) -> str:
    return (PREFIXO_TEXTO + url)[:250]


def corpo_texto(reg: dict) -> str:
    return (f"A notícia publicada no site para \"{reg.get('titulo') or '—'}\" não traz mais a maior parte do texto "
            f"que foi aprovado e registrado no Radar:\n\n{reg['url']}\n\n"
            "O que fazer: compare a página com o conteúdo aprovado (aba **Publicações**). Se a mudança no site foi "
            "de propósito, aprove o texto novo no Radar e registre de novo; se não foi, corrija a notícia no site."
            "\n\nEste aviso fecha sozinho quando o texto do site voltar a corresponder ao registrado, ou o registro "
            "for corrigido ou excluído.")


def conferir_textos(registros: list[dict], cfg: dict, pagina_de) -> tuple[dict[str, dict], set[str]]:
    """({link: registro mais novo} das notícias do site da Artecon cujo texto mudou, {links que não abriram}).
    `pagina_de(url)` devolve o HTML ou None (erro de rede: o link fica sem conferir, o aviso não muda)."""
    por_url: dict[str, dict] = {}
    for r in registros:
        url = r.get("url") or ""
        if url.startswith(("http://", "https://")) and radar_site.no_site(url, cfg) and (url not in por_url or r["id"] > por_url[url]["id"]):
            por_url[url] = r
    alterados, sem_conferir = {}, set()
    for url, reg in por_url.items():
        html = pagina_de(url)
        if html is None:
            sem_conferir.add(url)
        elif radar_site.texto_alterado(reg.get("corpo"), html):
            alterados[url] = reg
    return alterados, sem_conferir


def decidir_textos(registros: list[dict], alterados: dict[str, dict], abertos: dict[str, int], sem_conferir: set[str]):
    """Um aviso por link. Link que não pôde ser conferido (fora do ar, erro de rede) não abre nem fecha aviso."""
    abrir = [reg for url, reg in alterados.items() if titulo_texto(url) not in abertos]
    em_uso = {titulo_texto(r["url"]) for r in registros if r.get("url")}
    manter = {titulo_texto(url) for url in alterados} | {titulo_texto(url) for url in sem_conferir}
    fechar = []
    for t, numero in abertos.items():
        if not t.startswith(PREFIXO_TEXTO) or t in manter:
            continue
        fechar.append((numero, "O texto do site voltou a corresponder ao registrado." if t in em_uso
                       else "O link não está mais registrado no Radar (corrigido ou excluído)."))
    return abrir, fechar


def html_ou_nada(url: str) -> str | None:
    try:
        return baixar(url, tentativas=2)[1]
    except ErroDownload:
        return None


def status_http(url: str, sessao: requests.Session | None = None) -> int | None:
    try:
        r = (sessao or requests).get(url, timeout=20, allow_redirects=True, stream=True,
                                     headers={"User-Agent": "Mozilla/5.0 (RadarArtecon; conferencia de links)"})
        r.close()
        return r.status_code
    except requests.RequestException:
        return None


class GitHub:
    def __init__(self, repositorio: str, token: str, sessao: requests.Session | None = None):
        self.base = f"{API}/repos/{repositorio}"
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                    "X-GitHub-Api-Version": "2022-11-28"})

    def _pedir(self, metodo: str, caminho: str, **kw):
        r = self.sessao.request(metodo, self.base + caminho, timeout=30, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"GitHub {metodo} {caminho}: HTTP {r.status_code} — {r.text[:300]}")
        return r.json() if r.text else None

    def avisos_abertos(self, *prefixos: str) -> dict[str, int]:
        """Os avisos abertos PELO ROBÔ (título → número). v0.22.0 (varredura geral): o repositório é público e qualquer conta do GitHub
        abre issue: a de outra pessoa com o mesmo título não conta (nem esconde o aviso de uma falha de verdade, nem é fechada pelo robô)."""
        prefixos = prefixos or PREFIXOS_PADRAO
        abertos, pagina = {}, 1
        while True:
            lote = self._pedir("GET", "/issues", params={"state": "open", "per_page": 100, "page": pagina})
            for i in lote:
                if "pull_request" not in i and str(i.get("title", "")).startswith(prefixos) \
                        and (i.get("user") or {}).get("login") == AUTOR_DOS_AVISOS:
                    abertos[i["title"]] = i["number"]
            if len(lote) < 100:
                return abertos
            pagina += 1

    def abrir_aviso(self, titulo_aviso: str, corpo: str) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo_aviso[:250], "body": corpo})["number"]

    def abrir(self, f: dict) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo(f["slug"]), "body": corpo_aviso(f)})["number"]

    def abrir_parada(self, f: dict) -> int:
        return self.abrir_aviso(PREFIXO_PARADA + f["slug"], corpo_parada(f))

    def abrir_link(self, reg: dict, status: int) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo_link(reg["url"]), "body": corpo_link(reg, status)})["number"]

    def abrir_texto(self, reg: dict) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo_texto(reg["url"]), "body": corpo_texto(reg)})["number"]

    def textos_do_robo(self, numero: int) -> list[str]:
        """O corpo e os comentários de um aviso, só os escritos pelo robô (v0.22.0, rodada 2: guardam a marca dos envios da Pauta já
        avisados). O comentário de outra conta não vale: o repositório é público e qualquer um comenta."""
        aviso = self._pedir("GET", f"/issues/{numero}") or {}
        textos = [aviso.get("body") or ""] if (aviso.get("user") or {}).get("login") == AUTOR_DOS_AVISOS else []
        pagina = 1
        while True:
            lote = self._pedir("GET", f"/issues/{numero}/comments", params={"per_page": 100, "page": pagina}) or []
            textos += [c.get("body") or "" for c in lote if (c.get("user") or {}).get("login") == AUTOR_DOS_AVISOS]
            if len(lote) < 100:
                return textos
            pagina += 1

    def ultimo_aviso_fechado(self, titulo_aviso: str, dias: int = 31) -> int | None:
        """v0.30.0: o número do aviso do robô com este título que foi fechado e mexido nos últimos `dias` (o mais novo), ou None. A marca
        dele diz quais notícias já foram avisadas: o aviso de possível prorrogação fechado à mão no GitHub não volta a avisar as mesmas."""
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
        achados, pagina = [], 1
        while True:
            lote = self._pedir("GET", "/issues", params={"state": "closed", "since": desde, "sort": "updated", "direction": "desc",
                                                        "per_page": 100, "page": pagina}) or []
            achados += [i["number"] for i in lote if "pull_request" not in i and i.get("title") == titulo_aviso
                        and (i.get("user") or {}).get("login") == AUTOR_DOS_AVISOS]
            if len(lote) < 100:
                return max(achados) if achados else None
            pagina += 1

    def comentar(self, numero: int, corpo: str) -> None:
        self._pedir("POST", f"/issues/{numero}/comments", json={"body": corpo})

    def fechar(self, numero: int, motivo: str) -> None:
        self._pedir("POST", f"/issues/{numero}/comments", json={"body": motivo})
        self._pedir("PATCH", f"/issues/{numero}", json={"state": "closed", "state_reason": "completed"})


def executar(banco: Banco, github: GitHub, status_de=status_http, pagina_de=html_ou_nada) -> list[str]:
    abertos = github.avisos_abertos()
    saude = banco.saude_fontes()
    pauta = banco.pauta_com_problema()          # v0.21.0: lida antes de abrir qualquer aviso (erro no banco não deixa nada pela metade)
    prorrogacoes = banco.prorrogacoes()         # v0.30.0: idem (None: banco sem o SQL da v0.30.0)
    abrir, fechar = decidir(saude, abertos)
    feito = []
    for f in abrir:
        feito.append(f"aviso #{github.abrir(f)} aberto: {f['slug']} ({f.get('falhas_consecutivas')} falhas seguidas)")
    abrir_p, fechar_p = decidir_paradas(saude, abertos)
    for f in abrir_p:
        feito.append(f"aviso #{github.abrir_parada(f)} aberto: {f['slug']} parada")
    fechar += fechar_p
    corpo_pa, fechar_pa = decidir_pauta(pauta, abertos)
    if corpo_pa:                                # no registro, só a quantidade
        feito.append(f"aviso #{github.abrir_aviso(PREFIXO_PAUTA, corpo_pa)} aberto: {len(pauta)} publicação(ões) da Pauta não saíram")
    elif pauta:                                 # v0.22.0 (rodada 2): o aviso já aberto ganha um comentário por publicação nova
        numero = min(n for t, n in abertos.items() if t.startswith(PREFIXO_PAUTA))
        try:                                    # o GitHub falhou aqui: fica para a próxima rodada, sem parar os outros avisos
            comentario = comentario_pauta(pauta, avisados_pauta(github.textos_do_robo(numero)))
            if comentario:
                github.comentar(numero, comentario)
                feito.append(f"aviso #{numero} comentado: publicação(ões) nova(s) da Pauta não saíram ({len(pauta)} na lista)")
        except (RuntimeError, requests.RequestException) as e:
            feito.append(f"aviso #{numero}: a conferência das publicações novas fica para a próxima rodada ({type(e).__name__})")
    fechar += fechar_pa
    # v0.30.0: possível prorrogação na agenda de obrigações (no registro, só números)
    pendentes = pendentes_prorrogacao(prorrogacoes)
    ja_avisadas: set[int] = set()
    try:
        # sem aviso aberto: as notícias da marca do último aviso fechado (à mão no GitHub, por exemplo) não abrem outro aviso
        if pendentes and not any(t.startswith(PREFIXO_PRORROGACAO) for t in abertos) \
                and (fechado := github.ultimo_aviso_fechado(PREFIXO_PRORROGACAO)):
            ja_avisadas = avisadas_prorrogacao(github.textos_do_robo(fechado))
        corpo_pr, fechar_pr = decidir_prorrogacao(prorrogacoes, abertos, ja_avisadas)
    except (RuntimeError, requests.RequestException) as e:
        corpo_pr, fechar_pr = None, []
        feito.append(f"aviso de possível prorrogação: a conferência dos avisos anteriores fica para a próxima rodada ({type(e).__name__})")
    if corpo_pr:
        novas = sum(p["captura_id"] not in ja_avisadas for p in pendentes)
        feito.append(f"aviso #{github.abrir_aviso(PREFIXO_PRORROGACAO, corpo_pr)} aberto: {novas} possível(is) "
                     "prorrogação(ões) para conferir")
    elif pendentes and any(t.startswith(PREFIXO_PRORROGACAO) for t in abertos):   # o aviso aberto ganha um comentário com as novas
        numero = min(n for t, n in abertos.items() if t.startswith(PREFIXO_PRORROGACAO))
        try:
            comentario = comentario_prorrogacao(pendentes, avisadas_prorrogacao(github.textos_do_robo(numero)))
            if comentario:
                github.comentar(numero, comentario)
                feito.append(f"aviso #{numero} comentado: possível(is) prorrogação(ões) nova(s) ({len(pendentes)} para conferir)")
        except (RuntimeError, requests.RequestException) as e:
            feito.append(f"aviso #{numero}: a conferência das possíveis prorrogações novas fica para a próxima rodada ({type(e).__name__})")
    fechar += fechar_pr
    registros = banco.links_publicados()
    fora = conferir_links(registros, status_de)
    abrir_l, fechar_l = decidir_links(registros, fora, abertos)
    for reg, st in abrir_l:
        feito.append(f"aviso #{github.abrir_link(reg, st)} aberto: {reg['url']} responde {st}")
    fechar += fechar_l
    alterados, sem_conferir = conferir_textos([r for r in registros if r.get("url") not in fora],
                                              radar_site.configuracao(banco), pagina_de)
    abrir_t, fechar_t = decidir_textos(registros, alterados, abertos, sem_conferir | set(fora))
    for reg in abrir_t:
        feito.append(f"aviso #{github.abrir_texto(reg)} aberto: texto diferente em {reg['url']}")
    fechar += fechar_t
    for numero, motivo in fechar:
        github.fechar(numero, motivo)
        feito.append(f"aviso #{numero} fechado: {motivo}")
    return feito


def main() -> int:
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (url and chave and token and repo):
        print("Avisos de fonte com falha: sem as variáveis necessárias; nada a fazer.")
        return 0
    try:
        feito = executar(Banco(url, chave), GitHub(repo, token))
    except (ErroBanco, RuntimeError, requests.RequestException) as e:
        print(f"! avisos de fonte com falha não foram atualizados: {e}", file=sys.stderr)
        return 0
    print("Avisos de fonte com falha: " + ("; ".join(feito) if feito else "nada a abrir nem fechar."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
