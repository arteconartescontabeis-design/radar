"""Radar Artecon — leitores de listagem (um por tipo de fonte).

Cada função recebe o CONTEÚDO já baixado e a configuração da fonte e devolve
os itens encontrados. Não acessam rede nem banco: por isso são testáveis com
amostras salvas, e uma mudança de layout se resolve ajustando a `config` da
fonte (padrão de URL/seletor), sem mexer em código.

v0.31.0: o filtro de tema ("palavras" e "excluir_palavras", em qualquer tipo de fonte), a data marcada como "publicado" nos cartões
do gov.br e o sistema Normas da Receita pela pesquisa pública nova (JSON; a rede fica em radar_normas.py).
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from html.entities import name2codepoint
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from radar_util import (RE_DATA_BR, RE_DATA_EXTENSO, canonizar_url, hoje_brasilia, interpretar_data, normalizar_espacos,
                        sem_acentos)

RE_ANCORA_GENERICA = re.compile(
    r"^(acess(e|ar)|baix(e|ar)|leia|saiba|ver|veja|clique|continue|mais|download|abrir)\b", re.I)
LIMITES_DO_CARTAO = ("li", "article", "tr", "dd")
TAMANHO_MAXIMO_DO_CARTAO = 700
# v0.31.0: gov.br (summary_view) — o resumo vem antes da linha "publicado 27/08/2026 17h11" e costuma citar prazos
RE_DATA_PUBLICADO = re.compile(r"\bpublicad[oa]\s*(?:em\s*)?:?\s*(\d{1,2}º?[/.]\d{1,2}[/.]\d{4})", re.I)


def _ancora_generica(texto: str) -> bool:
    """'Acessar esta legislação', 'Leia mais'… — curto E começando por verbo de navegação.
    'Mais de 2 milhões de contribuintes regularizam débitos' é título de verdade."""
    if len(texto) < 3:
        return True
    return len(texto) <= 30 and len(texto.split()) <= 4 and bool(RE_ANCORA_GENERICA.match(texto))


@dataclass
class Item:
    url: str
    titulo: str
    data: date | None = None
    resumo: str | None = None
    url_texto: str | None = None          # de onde baixar o texto, se diferente da url
    texto_da_listagem: str | None = None  # o que a própria listagem traz de texto oficial (ex.: ementa)
    metadados: dict = field(default_factory=dict)
    trecho_do_tema: str | None = None     # v0.31.0: onde o filtro de tema também procura (DOU sem ementa: o começo do texto)


@dataclass
class Listagem:
    brutos: int                            # itens reconhecidos antes do filtro de data
    itens: list[Item]                      # itens dentro da janela, já sem repetição
    incompleta: str | None = None          # motivo, se alguma página além da primeira não pôde ser lida
    fora_do_tema: int = 0                  # v0.31.0: itens da janela que o filtro de tema deixou de fora (não viram captura)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _na_janela(d: date | None, config: dict, hoje: date) -> bool:
    if d is None:
        return not config.get("exigir_data", False)
    return d >= hoje - timedelta(days=int(config.get("janela_dias", 30)))


def _data_de_publicacao(d: date | None, hoje: date) -> date | None:
    """Data futura não é data de publicação (é prazo, vigência…): fica 'sem data'."""
    return None if (d is not None and d > hoje + timedelta(days=1)) else d


def data_no_texto(texto: str, config: dict, hoje: date | None = None) -> tuple[date | None, bool]:
    """Data de publicação lida do próprio texto (quando a listagem não traz). Prefere a que vem
    depois de "Publicado em"/"Atualizado em"; data futura não vale (é prazo ou vigência).
    Devolve (data, está na janela de coleta?)."""
    hoje = hoje or hoje_brasilia()
    inicio = (texto or "")[:1500]
    m = re.search(r"(?:publicad[oa]|atualizad[oa])\s+em\s*:?\s*(\d{1,2}º?[/.]\d{1,2}[/.]\d{4})", inicio, re.I)
    candidatas = [m.group(1)] if m else [x.group(0) for x in RE_DATA_BR.finditer(inicio)]
    for c in candidatas:
        d = _data_de_publicacao(interpretar_data(c), hoje)
        if d is not None:
            return d, _na_janela(d, config, hoje)
    return None, True


# ------------------------------------------------------------ filtro de tema (v0.31.0)
CHAVES_DO_TEMA = ("palavras", "excluir_palavras")


def expressao_do_tema(valor, campo: str = "palavras") -> re.Pattern | None:
    """config.palavras / config.excluir_palavras: uma expressão regular (texto) ou uma lista de pedaços de expressão (basta um casar).
    Sem diferença de maiúsculas e de acentos: o acento sai da expressão e do texto ("contribuiç" casa com "CONTRIBUIÇÃO" e com
    "contribuicao"; atenção: "nº" vira "no"). Vazio = sem filtro. Expressão inválida vira erro claro (a fonte fica com falha)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, str):
        partes = [valor]
    elif isinstance(valor, list) and all(isinstance(v, str) for v in valor):
        partes = [v for v in valor if v.strip()]
    else:
        raise ValueError(f"as palavras do tema ({campo}) precisam ser um texto ou uma lista de textos, como [\"FGTS\", \"eSocial\"]")
    if not partes:
        return None
    for n, parte in enumerate(partes, 1):
        try:
            re.compile(sem_acentos(parte), re.I)
        except re.error as e:
            qual = f'o item {n} ("{parte[:60]}")' if isinstance(valor, list) else f'"{parte[:60]}"'
            raise ValueError(f"as palavras do tema ({campo}) não são uma expressão válida: {qual} — {e}") from e
    junta = partes[0] if isinstance(valor, str) else "|".join(f"(?:{p})" for p in partes)
    return re.compile(sem_acentos(junta), re.I)


def filtro_de_tema(config: dict):
    """O item entra se "palavras" achar algo E "excluir_palavras" não achar nada, no título + resumo (ementa) do item, mais o
    trecho_do_tema (DOU sem ementa: o começo do texto). Nunca no texto inteiro: o preâmbulo dos atos ("O MINISTRO DE ESTADO DO
    TRABALHO...") faria tudo passar — a não ser com "palavras_no_texto": true (procura também no texto que veio no feed ou no XML).
    Devolve None quando a fonte não tem filtro de tema."""
    incluir = expressao_do_tema(config.get("palavras"), "palavras")
    excluir = expressao_do_tema(config.get("excluir_palavras"), "excluir_palavras")
    if incluir is None and excluir is None:
        return None
    no_texto = bool(config.get("palavras_no_texto"))

    def passa(it: Item) -> bool:
        alvo = sem_acentos(" ".join(p for p in (it.titulo, it.resumo, it.trecho_do_tema,
                                                it.texto_da_listagem if no_texto else None) if p))
        return (incluir is None or incluir.search(alvo) is not None) and not (excluir is not None and excluir.search(alvo))
    return passa


def _finalizar(itens: list[Item], config: dict, hoje: date | None) -> Listagem:
    hoje = hoje or hoje_brasilia()
    tema = filtro_de_tema(config)          # expressão inválida: erro antes de qualquer coisa
    vistos: dict[str, Item] = {}
    for it in itens:
        if not re.match(r"https?://", it.url, re.I):
            continue                      # só endereços http(s) entram no banco
        it.data = _data_de_publicacao(it.data, hoje)
        if it.url not in vistos:
            vistos[it.url] = it
    unicos = list(vistos.values())
    janela = [it for it in unicos if _na_janela(it.data, config, hoje)]
    fora = 0
    if tema is not None:
        # v0.31.0: depois da janela (conta só o que viraria captura) e depois de "brutos": a página lida em que nada é do tema
        # não vira "nenhum item reconhecido" (vazio_suspeito)
        no_tema = [it for it in janela if tema(it)]
        fora, janela = len(janela) - len(no_tema), no_tema
    janela.sort(key=lambda i: (i.data or date.min), reverse=True)
    return Listagem(brutos=len(unicos), itens=janela[: int(config.get("max_itens", 40))], fora_do_tema=fora)


# ---------------------------------------------------------------- RSS / Atom
class PaginaNaoEhFeed(ValueError):
    """v0.16.0: o endereço de uma fonte RSS devolveu uma página (HTML), não o feed. `feed` é o que a página anuncia, se anunciar."""
    def __init__(self, feed: str | None):
        self.feed = feed
        super().__init__("o endereço cadastrado é uma página do site, não um feed RSS; " +
                         (f"o feed que ela anuncia é {feed}: cadastre esse endereço" if feed
                          else "cadastre o endereço do feed (em sites WordPress, costuma ser o endereço do site com /feed/ no fim)"))


def _parece_html(texto: str) -> bool:
    inicio = re.sub(r"^(\s|<\?xml[^>]*\?>|<!--.*?-->)*", "", texto[:4000].lstrip("\ufeff"), flags=re.S)
    return bool(re.match(r"<(!doctype\s+html|html[\s>])", inicio, re.I))


def feed_da_pagina(conteudo: str, base: str) -> str | None:
    """O feed que a página anuncia (<link rel="alternate" type="application/rss+xml" href="...">). Página de categoria
    (…/categoria/noticias/) fica com o feed dela, não com o geral do site; feed de comentários só se não houver outro."""
    candidatos = []
    for link in BeautifulSoup(conteudo or "", "lxml").find_all("link", href=True):
        rel = [r.lower() for r in (link.get("rel") or [])]
        if "alternate" in rel and (link.get("type") or "").lower() in ("application/rss+xml", "application/atom+xml", "application/rdf+xml"):
            url = urljoin(base, link["href"].strip())
            if re.match(r"https?://", url, re.I):
                candidatos.append((url, (link.get("title") or "").lower()))
    if not candidatos:
        return None
    sem_comentarios = [c for c in candidatos if "/comments/" not in c[0].lower() and not re.search(r"coment|comment", c[1])] or candidatos
    partes = [p for p in re.sub(r"/page/\d+/?$", "/", urlsplit(base).path).split("/") if p]     # sem a paginação do WordPress
    for n in range(len(partes), min(2, len(partes)) - 1, -1):   # …/categoria/noticias/page/2/ → …/categoria/noticias/ (não sobe a /categoria/)
        prefixo = "/" + "/".join(partes[:n]) + "/"
        for url, _ in sem_comentarios:
            if urlsplit(url).path.startswith(prefixo):
                return url
    return sem_comentarios[0][0]


def _entidades_html(texto: str) -> str:
    """Feeds que usam entidades do HTML (&nbsp;, &ccedil;…), que o XML não conhece: viram o número do caractere."""
    return re.sub(r"&([A-Za-z][A-Za-z0-9]{1,30});", lambda m: m.group(0) if m.group(1) in ("amp", "lt", "gt", "quot", "apos")
                  else f"&#{name2codepoint[m.group(1)]};" if m.group(1) in name2codepoint else m.group(0), texto)


def listar_rss(conteudo: str, fonte: dict, hoje: date | None = None) -> Listagem:
    """RSS 1.0 (RDF, usado pelo gov.br), RSS 2.0 e Atom."""
    config = fonte.get("config") or {}
    excluir = re.compile(config["excluir_url"], re.I) if config.get("excluir_url") else None
    if isinstance(conteudo, bytes):
        try:
            texto = conteudo.decode("utf-8")
        except UnicodeDecodeError:
            texto = None
        if texto is not None and _parece_html(texto):
            raise PaginaNaoEhFeed(feed_da_pagina(texto, fonte["url"]))
    if isinstance(conteudo, str):
        if _parece_html(conteudo):
            raise PaginaNaoEhFeed(feed_da_pagina(conteudo, fonte["url"]))
        # o texto já foi decodificado: a declaração <?xml encoding=...?> não vale mais
        conteudo = _entidades_html(re.sub(r"^\s*<\?xml[^>]*\?>", "", conteudo.lstrip("\ufeff"))).encode("utf-8")
    raiz = ET.fromstring(conteudo)
    itens: list[Item] = []
    for no in raiz.iter():
        if _local(no.tag) not in ("item", "entry"):
            continue
        campos: dict[str, str] = {}
        for filho in no:
            nome = _local(filho.tag)
            valor = (filho.text or "").strip()
            if nome == "link" and not valor:
                valor = filho.attrib.get("href", "")
                if filho.attrib.get("rel", "alternate") != "alternate":
                    continue        # Atom: self, enclosure… não são o endereço da notícia
            if valor and nome not in campos:
                campos[nome] = valor
        url = canonizar_url(campos["link"]) if campos.get("link") else ""
        titulo = normalizar_espacos(campos.get("title", ""))
        if not url or not titulo:
            continue
        if excluir and excluir.search(url):
            continue
        quando = interpretar_data(campos.get("date") or campos.get("pubdate")
                                  or campos.get("published") or campos.get("updated"))
        resumo = campos.get("description") or campos.get("summary")
        if resumo:
            resumo = normalizar_espacos(BeautifulSoup(resumo, "lxml").get_text(" ", strip=True)) or None
        # <content:encoded> (WordPress) ou <content> (Atom): o texto completo da notícia, no próprio feed
        completo = campos.get("encoded") or campos.get("content")
        if completo:
            completo = normalizar_espacos(BeautifulSoup(completo, "lxml").get_text(" ", strip=True)) or None
        elif config.get("sem_pagina_de_texto") and resumo:
            # v0.31.0 (DOM/SC): a fonte não abre a página de cada item; o resumo oficial do feed (título, ementa e começo do ato)
            # é o texto guardado, marcado como parcial
            completo = resumo
        itens.append(Item(url=url, titulo=titulo, data=quando, resumo=resumo, texto_da_listagem=completo))
    return _finalizar(itens, config, hoje)


# ------------------------------------------------------- página com links
def _cartao(ancora, urls_por_no) -> object:
    """Maior ancestral que contém UM único link de interesse: é o 'cartão' do item."""
    cartao = ancora
    no = ancora.parent
    while no is not None and getattr(no, "name", None) not in (None, "body", "html", "[document]"):
        if len(urls_por_no(no)) > 1:
            break
        if len(no.get_text(" ", strip=True)) > TAMANHO_MAXIMO_DO_CARTAO:
            break               # grande demais para ser o cartão de um item só
        cartao = no
        if no.name in LIMITES_DO_CARTAO:
            break
        no = no.parent
    return cartao


def listar_html_links(conteudo: str, fonte: dict, hoje: date | None = None) -> Listagem:
    """Lista montada a partir dos links cujo endereço casa com `config.padrao_url`.

    Não depende de classes CSS: o título vem do texto do link (ou do 'cartão'
    em volta, quando o link é genérico como "Acessar") e a data é a primeira
    encontrada no cartão.
    """
    config = fonte.get("config") or {}
    if not config.get("padrao_url"):
        raise ValueError("falta o padrão dos links (padrao_url) no cadastro da fonte")
    try:
        padrao = re.compile(config["padrao_url"], re.I)
    except re.error as e:
        raise ValueError(f"o padrão dos links (padrao_url) não é uma expressão válida: {e}") from e
    excluir = re.compile(config["excluir_url"], re.I) if config.get("excluir_url") else None
    base = fonte["url"]
    sopa = BeautifulSoup(conteudo or "", "lxml")
    for lixo in sopa(["script", "style", "noscript"]):
        lixo.decompose()

    ancoras: dict[str, list] = {}
    for a in sopa.find_all("a", href=True):
        if a["href"].strip().startswith("#"):
            continue
        url = canonizar_url(urljoin(base, a["href"].strip()))
        if not padrao.search(url) or (excluir and excluir.search(url)):
            continue
        if url == canonizar_url(base):
            continue
        a["data-radar-url"] = url
        ancoras.setdefault(url, []).append(a)

    def urls_por_no(no) -> set[str]:
        return {x["data-radar-url"] for x in no.find_all("a", attrs={"data-radar-url": True})}

    itens: list[Item] = []
    for url, lista in ancoras.items():
        melhor = max(lista, key=lambda x: len(normalizar_espacos(x.get_text(" ", strip=True))))
        texto_ancora = normalizar_espacos(melhor.get_text(" ", strip=True)) or normalizar_espacos(melhor.get("title", ""))
        cartao = _cartao(melhor, urls_por_no)
        texto_cartao = normalizar_espacos(cartao.get_text(" ", strip=True))

        # Data de publicação: 1º a marcação <time>; depois o texto do cartão FORA do
        # título (data dentro do título é prazo/vigência, não data de publicação).
        quando = None
        tempo = cartao.find("time") if hasattr(cartao, "find") else None
        if tempo is not None:
            quando = interpretar_data(tempo.get("datetime") or tempo.get_text())
        if quando is None:
            fora_do_titulo = texto_cartao
            for a in lista:
                fora_do_titulo = fora_do_titulo.replace(normalizar_espacos(a.get_text(" ", strip=True)), " ", 1)
            # v0.31.0: a data marcada como de publicação ("publicado 27/08/2026") vale mais que a primeira data do cartão (no
            # gov.br o resumo vem antes e cita prazos: 7 de 30 notícias do eSocial ficavam com a data errada). Vale a ÚLTIMA: o resumo,
            # que vem antes da linha "publicado", pode dizer "a portaria publicada em 10/03/2026"
            ms = list(RE_DATA_PUBLICADO.finditer(fora_do_titulo))
            m = ms[-1] if ms else None
            if m:
                quando = interpretar_data(m.group(1))
            else:
                m = RE_DATA_BR.search(fora_do_titulo) or RE_DATA_EXTENSO.search(fora_do_titulo)
                quando = interpretar_data(m.group(0)) if m else None

        generica = _ancora_generica(texto_ancora)
        titulo = texto_ancora
        if config.get("titulo_do_contexto") or generica:
            cab = cartao.find(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"]) if hasattr(cartao, "find") else None
            do_contexto = normalizar_espacos(cab.get_text(" ", strip=True)) if cab is not None else ""
            if len(do_contexto) < 6:
                resto = texto_cartao.replace(texto_ancora, " ") if generica else texto_cartao
                do_contexto = normalizar_espacos(RE_DATA_BR.sub(" ", resto))
            if len(do_contexto) >= 6:
                titulo = do_contexto
        titulo = titulo[:300].strip(" -–—|:")
        if len(titulo) < 3:
            continue

        resumo = None
        if texto_cartao and texto_cartao != titulo and len(texto_cartao) > len(titulo) + 30:
            resumo = texto_cartao[:600]
        itens.append(Item(url=url, titulo=titulo, data=quando, resumo=resumo))
    resultado = _finalizar(itens, config, hoje)
    resultado.brutos = len(ancoras)      # links reconhecidos, mesmo os que não viraram item
    return resultado


# ---------------------------------------------------- Normas da Receita
# v0.31.0: desde 04/10/2026 o sistema Normas é uma aplicação montada no navegador. Os dados vêm da mesma pesquisa pública que a
# página usa (POST /api/indexacao/ato/pesquisar, JSON, sem captcha nem login) e o texto de cada ato, da consulta externa
# (GET normasinternet2…/api/consulta-externa/ato/{id}/visao/multivigente). Aqui só a leitura; os pedidos ficam em radar_normas.py.
URL_ATO_NORMAS = "https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{id}"
URL_TEXTO_NORMAS = "https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/{id}/visao/multivigente"
LINK_PERMANENTE_NORMAS = "https://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto={id}"


class SistemaNormasMudou(ValueError):
    """A pesquisa do sistema Normas não respondeu no formato conhecido (página da aplicação no lugar do JSON, ou JSON sem a lista
    de atos): em vez do "nenhum item reconhecido" genérico, a fonte diz o motivo e por onde os atos continuam chegando."""
    def __init__(self, detalhe: str = ""):
        super().__init__("a pesquisa do sistema Normas da Receita mudou de formato" + (f" ({detalhe})" if detalhe else "") +
                         "; o leitor desta fonte precisa de ajuste. Os atos da Receita continuam chegando pelo DOU (dou-inlabs)")


def _sem_html(texto) -> str:
    texto = "" if texto is None else str(texto)
    if "<" not in texto and "&" not in texto:
        return normalizar_espacos(texto)
    return normalizar_espacos(BeautifulSoup(texto, "lxml").get_text(" ", strip=True))


def json_da_pesquisa_normas(conteudo) -> dict:
    """A resposta da pesquisa (texto, bytes ou já lida). Página no lugar do JSON, ou JSON sem "atos": SistemaNormasMudou."""
    if isinstance(conteudo, dict):
        dados = conteudo
    else:
        if isinstance(conteudo, bytes):
            conteudo = conteudo.decode("utf-8", "replace")
        try:
            dados = json.loads(conteudo or "")
        except ValueError:
            pagina = re.search(r"<\s*(app-root|html|!doctype)", conteudo or "", re.I)
            raise SistemaNormasMudou("veio uma página do site no lugar da resposta da pesquisa" if pagina
                                     else "a resposta não é JSON") from None
    if not isinstance(dados, dict) or not isinstance(dados.get("atos"), list):
        raise SistemaNormasMudou("a resposta não traz a lista de atos")
    return dados


def _regex_da_config(config: dict, chave: str) -> re.Pattern | None:
    if not config.get(chave):
        return None
    try:
        return re.compile(config[chave], re.I)
    except re.error as e:
        raise ValueError(f"a opção {chave} da fonte não é uma expressão válida: {e}") from e


def listar_normas_rfb(conteudo, fonte: dict, hoje: date | None = None) -> Listagem:
    """Atos da pesquisa do sistema Normas (JSON). O título é o nome oficial do ato ("Portaria Coana nº 214, de 15/10/2026", a data
    do ato); a data do item é a da publicação. Endereço estável: o da página do ato, sem o sufixo "/vs/..." da consulta."""
    config = fonte.get("config") or {}
    dados = json_da_pesquisa_normas(conteudo)
    excluir_orgao = _regex_da_config(config, "excluir_orgao")
    molde_texto = config.get("url_texto") or URL_TEXTO_NORMAS
    itens: list[Item] = []
    for ato in dados["atos"]:
        if not isinstance(ato, dict):
            continue
        id_ato = str(ato.get("idAto") or "").strip()
        tipo_ato = ato.get("tipoAto") if isinstance(ato.get("tipoAto"), dict) else {}
        tipo = normalizar_espacos(str(tipo_ato.get("nomeTipoAto") or ""))
        if not (id_ato.isdigit() and tipo):
            continue
        numero = normalizar_espacos(str(ato.get("numeroAto") or ""))
        orgao = " / ".join(normalizar_espacos(str(o["siglaOrgao"])) for o in (ato.get("orgaos") or [])
                           if isinstance(o, dict) and o.get("siglaOrgao"))
        if excluir_orgao and excluir_orgao.search(orgao):
            continue
        ementa = _sem_html(ato.get("ementa"))
        data_ato = interpretar_data(str(ato.get("dataAto") or ""))
        publicacao = interpretar_data(str(ato.get("dataPublicacao") or ""))
        de = data_ato or publicacao
        titulo = " ".join(p for p in (tipo, orgao) if p) + (f" nº {numero}" if numero else "") + (f", de {de:%d/%m/%Y}" if de else "")
        url = re.sub(r"/vs/.*$", "", str(ato.get("urlVisualizacao") or "").strip())
        if not re.match(rf"https://[!-~]+/{id_ato}$", url):
            url = URL_ATO_NORMAS.format(id=id_ato)
        itens.append(Item(
            url=url, titulo=titulo, data=publicacao, resumo=ementa or None,
            url_texto=molde_texto.format(id=id_ato),
            metadados={"tipo": tipo, "numero": numero, "orgao": orgao, "id_ato": id_ato,
                       "sigla_tipo": normalizar_espacos(str(tipo_ato.get("siglaTipoAto") or "")) or None,
                       "data_ato": data_ato.isoformat() if data_ato else None,
                       "link_permanente": LINK_PERMANENTE_NORMAS.format(id=id_ato)},
            texto_da_listagem=(f"{titulo}. Ementa: {ementa}" if ementa else None),
        ))
    resultado = _finalizar(itens, config, hoje)
    resultado.brutos = len(dados["atos"])      # atos recebidos, mesmo os filtrados por órgão ou tema
    return resultado


def texto_do_ato_normas(conteudo) -> str:
    """Texto do ato pela consulta externa (JSON da visão "multivigente"): a epígrafe, a ementa e os demais segmentos na ordem do
    ato, sem HTML e sem o que está riscado (revogado) ou omitido. Nada é inventado: o anexo em PDF (nas Soluções de Consulta, a
    íntegra) não entra; a ementa completa que vem como texto basta. Formato inesperado: ValueError."""
    dados = conteudo if isinstance(conteudo, dict) else json.loads(conteudo.decode("utf-8") if isinstance(conteudo, bytes) else conteudo)
    if not isinstance(dados, dict) or not isinstance(dados.get("ementas") or [], list) \
            or not isinstance(dados.get("outrosSegmentos") or [], list):
        raise ValueError("o texto do ato veio em formato inesperado")
    segmentos = [s for s in (dados.get("ementas") or []) + (dados.get("outrosSegmentos") or []) if isinstance(s, dict)]
    segmentos.sort(key=lambda s: s.get("ordemSegmentoAto") if isinstance(s.get("ordemSegmentoAto"), (int, float)) else 10 ** 9)
    partes = [_sem_html(dados.get("epigrafeCompleta"))]
    partes += [_sem_html(s.get("textoIntegra")) for s in segmentos if not s.get("omitir") and not s.get("tachado")]
    return normalizar_espacos(" ".join(p for p in partes if p))


def corpo_pesquisa_normas(fonte: dict, hoje: date | None = None, pagina: int = 1) -> dict:
    """O pedido que a tela de pesquisa do Normas faz (serializarFiltrosPesquisa), pela data de publicação, do mais novo para o mais
    antigo. As datas vão em DD/MM/AAAA (no formato ISO a API responde erro 500). Filtros opcionais da fonte: "tipos_ids" (ids dos
    tipos de ato, separados por ";") e "orgaos_siglas" (siglas dos órgãos, separadas por ";")."""
    config = fonte.get("config") or {}
    hoje = hoje or hoje_brasilia()
    inicio = hoje - timedelta(days=int(config.get("janela_dias", 10)))
    junta = lambda v: ";".join(str(x).strip() for x in v if str(x).strip()) if isinstance(v, list) else str(v or "").strip()
    return {"tipoData": "dataPublicacao", "tiposAtosSelecionados": junta(config.get("tipos_ids")),
            "orgaosSelecionados": junta(config.get("orgaos_siglas")), "numeroAto": "",
            "dataInicio": f"{inicio:%d/%m/%Y}", "dataFim": f"{hoje:%d/%m/%Y}",
            "publicado": True, "internet": True, "apenasAtosVigentes": False, "apenasAtosInternos": False,
            "termo": "", "refino": {}, "paginacaoPaginaAtual": int(pagina),
            "paginacaoQuantidadePorPagina": max(10, min(int(config.get("itens_por_pagina") or 100), 300)),
            "tipoPesquisa": "formulario", "ordenacaoColuna": "publicacao", "ordenacaoDirecao": "desc", "skipAggregations": True}


def enderecos_da_listagem(fonte: dict, hoje: date | None = None) -> list[str]:
    """Endereços a baixar para montar a listagem. Aceita no endereço da fonte os marcadores
    {inicio} e {fim} (janela de datas, dd/mm/aaaa) e {p} (número da página)."""
    hoje = hoje or hoje_brasilia()
    config = fonte.get("config") or {}
    url = fonte["url"]
    datas = {"inicio": f"{hoje - timedelta(days=int(config.get('janela_dias', 30))):%d/%m/%Y}", "fim": f"{hoje:%d/%m/%Y}"}
    paginas = range(1, int(config.get("paginas_max", 1)) + 1) if "{p}" in url else [1]
    return [url.replace("{inicio}", datas["inicio"]).replace("{fim}", datas["fim"]).replace("{p}", str(p)) for p in paginas]


def listar_paginas(baixar_pagina, fonte: dict, hoje: date | None = None) -> tuple[Listagem, int | None]:
    """Baixa e lê a listagem, página a página quando a fonte é paginada. Para na página que
    vier incompleta. O limite de itens vale para o conjunto, não por página. Se uma página
    além da primeira falhar, segue com o que já leu e anota que a leitura ficou incompleta.
    `baixar_pagina(url)` devolve (status HTTP, conteúdo)."""
    config = fonte.get("config") or {}
    por_pagina = int(config.get("itens_por_pagina", 0))
    # o limite de itens e o filtro de tema valem para o conjunto (v0.31.0: o que ficou fora do tema é contado uma vez só, no fim)
    sem_corte = {k: v for k, v in dict(config, max_itens=10 ** 6).items() if k not in CHAVES_DO_TEMA}
    itens, brutos, http, incompleta = [], 0, None, None
    for n, url in enumerate(enderecos_da_listagem(fonte, hoje), start=1):
        try:
            http, conteudo = baixar_pagina(url)
        except Exception as e:
            if n == 1:
                raise
            incompleta = f"a página {n} da listagem não pôde ser lida ({e}); itens das páginas anteriores foram aproveitados"
            break
        try:
            parte = listar(conteudo, dict(fonte, url=url, config=sem_corte), hoje)
        except PaginaNaoEhFeed as e:
            # v0.16.0: cadastraram a página do site como fonte RSS: segue (uma vez) o feed que a página anuncia
            if not e.feed or n > 1 or e.feed == url:
                raise
            http, conteudo = baixar_pagina(e.feed)
            parte = listar(conteudo, dict(fonte, url=e.feed, config=sem_corte), hoje)
            brutos += parte.brutos
            itens += parte.itens
            break                       # o feed anunciado substitui a listagem paginada: não baixa a página 2
        brutos += parte.brutos
        itens += parte.itens
        if not por_pagina or parte.brutos < por_pagina:
            break
    resultado = _finalizar(itens, config, hoje)
    resultado.brutos = brutos
    resultado.incompleta = incompleta
    return resultado, http


LEITORES = {
    "rss": listar_rss,
    "html_links": listar_html_links,
    "normas_rfb": listar_normas_rfb,
}


def listar(conteudo: str, fonte: dict, hoje: date | None = None) -> Listagem:
    tipo = fonte["tipo_coletor"]
    if tipo not in LEITORES:
        raise ValueError(f"tipo de coletor desconhecido: {tipo}")
    return LEITORES[tipo](conteudo, fonte, hoje)
