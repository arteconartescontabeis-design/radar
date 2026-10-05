"""Radar Artecon — leitores de listagem (um por tipo de fonte).

Cada função recebe o CONTEÚDO já baixado e a configuração da fonte e devolve
os itens encontrados. Não acessam rede nem banco: por isso são testáveis com
amostras salvas, e uma mudança de layout se resolve ajustando a `config` da
fonte (padrão de URL/seletor), sem mexer em código.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from radar_util import RE_DATA_BR, RE_DATA_EXTENSO, canonizar_url, interpretar_data, normalizar_espacos

RE_ANCORA_GENERICA = re.compile(
    r"^(acess(e|ar)|baix(e|ar)|leia|saiba|ver|veja|clique|continue|mais|download|abrir)\b", re.I)
LIMITES_DO_CARTAO = ("li", "article", "tr", "dd")
TAMANHO_MAXIMO_DO_CARTAO = 700


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


@dataclass
class Listagem:
    brutos: int                            # itens reconhecidos antes do filtro de data
    itens: list[Item]                      # itens dentro da janela, já sem repetição
    incompleta: str | None = None          # motivo, se alguma página além da primeira não pôde ser lida


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
    hoje = hoje or date.today()
    inicio = (texto or "")[:1500]
    m = re.search(r"(?:publicad[oa]|atualizad[oa])\s+em\s*:?\s*(\d{1,2}º?[/.]\d{1,2}[/.]\d{4})", inicio, re.I)
    candidatas = [m.group(1)] if m else [x.group(0) for x in RE_DATA_BR.finditer(inicio)]
    for c in candidatas:
        d = _data_de_publicacao(interpretar_data(c), hoje)
        if d is not None:
            return d, _na_janela(d, config, hoje)
    return None, True


def _finalizar(itens: list[Item], config: dict, hoje: date | None) -> Listagem:
    hoje = hoje or date.today()
    vistos: dict[str, Item] = {}
    for it in itens:
        if not re.match(r"https?://", it.url, re.I):
            continue                      # só endereços http(s) entram no banco
        it.data = _data_de_publicacao(it.data, hoje)
        if it.url not in vistos:
            vistos[it.url] = it
    unicos = list(vistos.values())
    janela = [it for it in unicos if _na_janela(it.data, config, hoje)]
    janela.sort(key=lambda i: (i.data or date.min), reverse=True)
    return Listagem(brutos=len(unicos), itens=janela[: int(config.get("max_itens", 40))])


# ---------------------------------------------------------------- RSS / Atom
def listar_rss(conteudo: str, fonte: dict, hoje: date | None = None) -> Listagem:
    """RSS 1.0 (RDF, usado pelo gov.br), RSS 2.0 e Atom."""
    config = fonte.get("config") or {}
    excluir = re.compile(config["excluir_url"], re.I) if config.get("excluir_url") else None
    if isinstance(conteudo, str):
        # o texto já foi decodificado: a declaração <?xml encoding=...?> não vale mais
        conteudo = re.sub(r"^\s*<\?xml[^>]*\?>", "", conteudo.lstrip("\ufeff")).encode("utf-8")
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
RE_ID_ATO = re.compile(r"(?:consulta/externa/|idAto=)(\d+)")


def listar_normas_rfb(conteudo: str, fonte: dict, hoje: date | None = None) -> Listagem:
    """Tabela do sistema Normas (tipo, nº, órgão, publicação, ementa)."""
    config = fonte.get("config") or {}
    excluir_orgao = re.compile(config["excluir_orgao"], re.I) if config.get("excluir_orgao") else None
    molde_texto = config.get("url_texto")
    sopa = BeautifulSoup(conteudo or "", "lxml")
    itens: list[Item] = []
    reconhecidos = 0
    for linha in sopa.find_all("tr"):
        ancora = None
        for a in linha.find_all("a", href=True):
            if RE_ID_ATO.search(a["href"]):
                ancora = a
                break
        celulas = [normalizar_espacos(c.get_text(" ", strip=True)) for c in linha.find_all("td")]
        if ancora is None or len(celulas) < 5:
            continue
        reconhecidos += 1
        id_ato = RE_ID_ATO.search(ancora["href"]).group(1)
        tipo, numero, orgao, publicacao, ementa = celulas[:5]
        if excluir_orgao and excluir_orgao.search(orgao):
            continue
        quando = interpretar_data(publicacao)
        titulo = f"{tipo} {orgao} nº {numero}" + (f", de {quando:%d/%m/%Y}" if quando else "")
        itens.append(Item(
            # endereço estável: sem o sufixo "/vs/..." que muda a cada consulta
            url=f"https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{id_ato}",
            titulo=titulo, data=quando, resumo=ementa or None,
            url_texto=molde_texto.format(id=id_ato) if molde_texto else None,
            metadados={"tipo": tipo, "numero": numero, "orgao": orgao, "id_ato": id_ato},
            texto_da_listagem=(f"{titulo}. Ementa: {ementa}" if ementa else None),
        ))
    resultado = _finalizar(itens, config, hoje)
    resultado.brutos = reconhecidos   # linhas reconhecidas, mesmo as filtradas por órgão
    return resultado


def enderecos_da_listagem(fonte: dict, hoje: date | None = None) -> list[str]:
    """Endereços a baixar para montar a listagem. Aceita no endereço da fonte os marcadores
    {inicio} e {fim} (janela de datas, dd/mm/aaaa) e {p} (número da página)."""
    hoje = hoje or date.today()
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
    sem_corte = dict(config, max_itens=10 ** 6)
    itens, brutos, http, incompleta = [], 0, None, None
    for n, url in enumerate(enderecos_da_listagem(fonte, hoje), start=1):
        try:
            http, conteudo = baixar_pagina(url)
        except Exception as e:
            if n == 1:
                raise
            incompleta = f"a página {n} da listagem não pôde ser lida ({e}); itens das páginas anteriores foram aproveitados"
            break
        parte = listar(conteudo, dict(fonte, url=url, config=sem_corte), hoje)
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
