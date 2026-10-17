"""Radar Artecon — registro automático das publicações no site da Artecon (v0.8.0).

Depois da coleta, lê a lista de notícias do site (artecon.cnt.br/news), abre as notícias que ainda
não estão registradas em "Publicações no site" e procura, entre os conteúdos aprovados que ainda
não têm registro, o que foi publicado: título parecido E a maior parte das palavras do texto
aprovado presente na página. Achou um só, sem dúvida: registra o link e a data da notícia, como se
alguém tivesse preenchido "Registrar publicação no site". Na dúvida (dois candidatos parecidos, ou
título igual com texto diferente), não registra nada: o registro manual continua valendo.

Também serve aos avisos (radar_alertas.py): `texto_alterado` diz se a página publicada ainda traz o
texto que foi aprovado e registrado.

v0.32.0: o título vai ao site sem "nº" e sem "º"/"ª"/"°" depois de números (titulo_para_o_site: o site da Artecon monta o endereço
da notícia com o título e não abre a página quando o endereço tem esses sinais); a notícia é achada pelo título do Radar ou por esse.

Configuração (opcional) na chave `site` de Configurações (radar_config):
    {"lista": "https://artecon.cnt.br/news", "padrao": "/news/view/[^/?#]+$", "max_noticias": 15,
     "desligado": false}

Uso (no workflow, depois da coleta):  python radar_site.py
Variáveis: SUPABASE_URL e SUPABASE_SERVICE_KEY. Nunca deixa a coleta vermelha: erros vão para o log.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from radar_banco import Banco, ErroBanco
from radar_util import (BRASILIA, ErroDownload, baixar, canonizar_url, extrair_texto, hoje_brasilia, interpretar_data,
                        normalizar_espacos, sem_acentos)

CONFIG_PADRAO = {"lista": "https://artecon.cnt.br/news", "padrao": r"/news/view/[^/?#]+$", "max_noticias": 15}
SELETOR_TEXTO = "article, .news-content, .content, main, body"
OBSERVACAO = "Registrado automaticamente pelo robô (notícia encontrada no site)."

# limites da comparação (0 a 1)
TITULO_IGUAL = 0.8         # títulos praticamente iguais...
TEXTO_COM_TITULO = 0.5     # ...e metade das palavras do texto aprovado na página
TITULO_PARECIDO = 0.5      # título só parecido exige o texto quase todo na página
TEXTO_QUASE_TODO = 0.75
TEXTO_ALTERADO = 0.5       # página com menos da metade das palavras do texto registrado: o texto mudou
PALAVRAS_MINIMAS = 20      # texto aprovado mais curto que isso não é comparado (caberia em qualquer página do tema)
MESES = {"janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"}


# v0.32.0 (17/10/2026): o site da Artecon monta o endereço da notícia com o título ("…/news/view/salario-maternidade-lei-nº-154152026-…")
# e não abre a página quando o endereço tem "º" (responde 404, também com %C2%BA). Decisão do dono: no título que vai ao site,
# "Lei nº 15.415/2026" vira "Lei 15.415/2026" e o "º"/"ª"/"°" depois de número sai ("1ª parcela" → "1 parcela"). No Radar, no
# Instagram e no Facebook o título continua como foi escrito. A mesma regra está na tela (tituloParaOSite, no index.html).
_SINAIS_DO_SITE = re.compile("[ºª°]")
# os espaços, por extenso (o \s e o strip() do Python não são o \s e o trim() do JS: o Python conta o NEL U+0085 e U+001C a U+001F, o JS
# conta o BOM U+FEFF): a soma dos dois, a mesma lista no ESPACOS_DO_SITE da tela, para a regra dar o mesmo resultado nos dois lados
ESPACOS_DO_SITE = "[\t\n\x0b\x0c\r \x1c-\x1f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
_NUMERO_ABREVIADO = re.compile(r"(?<![0-9A-Za-zÀ-ÖØ-öø-ÿ])[nN]\.?[º°][sS]?\.?" + ESPACOS_DO_SITE + r"*(?=[0-9])")   # "nº ", "Nº", "n.º", "N.º", "n°", "nº.", "nºs"
_ORDINAL = re.compile(r"(?<=[0-9])\.?[ºª°]")                                                   # "1ª", "2º", "13º", "1.º", "25°"
_ESPACOS = re.compile(ESPACOS_DO_SITE + "+")


def titulo_para_o_site(titulo: str | None) -> str:
    """O título como vai ao site da Artecon: sem o "nº" antes de número (fica só o número), sem o "º"/"ª"/"°" depois de número e sem
    nenhum "º"/"ª"/"°" que sobrar; os espaços que ficam dobrados viram um (qualquer espaço de ESPACOS_DO_SITE) e os das pontas saem.
    Título sem esses sinais vai exatamente como está."""
    t = str(titulo or "")
    if not _SINAIS_DO_SITE.search(t):
        return t
    t = _SINAIS_DO_SITE.sub("", _ORDINAL.sub("", _NUMERO_ABREVIADO.sub("", t)))
    return _ESPACOS.sub(" ", t).strip(" ")


def palavras(texto: str | None) -> set[str]:
    """Palavras de 3 letras ou mais, sem acento e sem caixa (a marcação do texto não conta)."""
    return {p for p in re.findall(r"[a-z0-9]+", sem_acentos(texto or "").lower()) if len(p) >= 3}


def semelhanca(a: str | None, b: str | None) -> float:
    pa, pb = palavras(a), palavras(b)
    return len(pa & pb) / len(pa | pb) if pa and pb else 0.0


def contido(trecho: str | None, texto: str | None) -> float:
    """Que parte das palavras de `trecho` aparece em `texto`."""
    pt = palavras(trecho)
    return len(pt & palavras(texto)) / len(pt) if pt else 0.0


def chave_url(url: str) -> str:
    """Mesmo endereço com ou sem www e http/https (registro manual × link da lista do site)."""
    u = canonizar_url(url)
    partes = urlsplit(u)
    host = (partes.hostname or "").removeprefix("www.")
    return f"{host}{partes.path}{'?' + partes.query if partes.query else ''}".lower()


def marcas(titulo: str | None) -> set[str]:
    """Números, meses e anos do título: "Agenda de outubro de 2026" × "Agenda de novembro de 2026", ou
    "Portaria nº 45" × "Portaria nº 46", não são a mesma notícia."""
    texto = sem_acentos(titulo or "").lower()
    return set(re.findall(r"\d+", texto)) | {p for p in re.findall(r"[a-z]+", texto) if p in MESES}


def links_da_lista(html: str, base: str, padrao: str, limite: int) -> list[str]:
    """Endereços das notícias na ordem da página (a mais nova primeiro), sem repetição."""
    return [n["url"] for n in noticias_da_lista(html, base, padrao, limite)]


def noticias_da_lista(html: str, base: str, padrao: str, limite: int) -> list[dict]:
    """v0.32.0: as notícias da lista, na ordem da página e sem repetição, cada uma com o endereço e os textos do quadro dela na lista
    (em artecon.cnt.br/news: a categoria, a data, o título e o "LEIA"). O quadro é o maior bloco em volta do link que não tem link de
    outra notícia. Serve para achar a notícia pelo título mesmo quando a página dela não abre."""
    regex, sopa = re.compile(padrao), BeautifulSoup(html or "", "lxml")
    endereco = {}
    for a in sopa.find_all("a", href=True):
        url = canonizar_url(urljoin(base, a["href"]))
        if regex.search(url):
            endereco[id(a)] = url
    achadas: dict[str, dict] = {}
    for a in sopa.find_all("a", href=True):
        url = endereco.get(id(a))
        if url is None:
            continue
        noticia = achadas.setdefault(url, {"url": url, "textos": []})
        quadro = a
        while quadro.parent is not None and quadro.parent.name not in ("body", "html", "[document]") and all(
                endereco.get(id(x), url) == url for x in quadro.parent.find_all("a", href=True)):
            quadro = quadro.parent
        for el in [quadro, *quadro.find_all(True)]:
            for texto in (el.get_text(" "), el.get("title") or ""):
                texto = normalizar_espacos(texto)
                if texto and texto not in noticia["textos"]:
                    noticia["textos"].append(texto)
    return list(achadas.values())[:limite]


def ler_noticia(html: str) -> dict:
    """Título (og:title ou <h1>), data ("Publicada em 30 de Agosto de 2026") e texto da página."""
    sopa = BeautifulSoup(html or "", "lxml")
    meta = sopa.find("meta", attrs={"property": "og:title"})
    h1 = sopa.find("h1")
    titulo = normalizar_espacos((meta.get("content") if meta else "") or (h1.get_text(" ") if h1 else ""))
    texto = extrair_texto(html, SELETOR_TEXTO)
    m = re.search(r"Publicad[ao] em\s+(.{6,40}?\d{4})", texto, re.I)
    return {"titulo": titulo, "data": interpretar_data(m.group(1)) if m else None, "texto": texto}


def dia_brasilia(instante) -> date | None:
    """O dia, em Brasília, de um carimbo do banco (que vem em UTC: 22h30 de Brasília já é o dia seguinte lá)."""
    try:
        return datetime.fromisoformat(str(instante).replace("Z", "+00:00")).astimezone(BRASILIA).date() if instante else None
    except ValueError:
        return None


def escolher(noticia: dict, candidatos: list[dict]) -> dict | None:
    """O conteúdo aprovado que corresponde à notícia, só se houver um, sem dúvida. v0.32.0: o título da notícia no site pode ser o do
    Radar ou o que vai ao site (titulo_para_o_site: sem o "nº" e sem o "º"/"ª" depois de número); vale o que for mais parecido."""
    aceitos = []
    for c in candidatos:
        titulos = [t for t in dict.fromkeys((c["titulo"], titulo_para_o_site(c["titulo"]))) if marcas(t) == marcas(noticia["titulo"])]
        if len(palavras(c.get("corpo"))) < PALAVRAS_MINIMAS or not titulos:
            continue
        aprovado = dia_brasilia(c.get("aprovado_em"))
        if noticia["data"] and aprovado and noticia["data"] < aprovado:
            continue                     # publicada antes de o conteúdo ser aprovado: não é ele
        tit, txt = max(semelhanca(noticia["titulo"], t) for t in titulos), contido(c.get("corpo"), noticia["texto"])
        if (tit >= TITULO_IGUAL and txt >= TEXTO_COM_TITULO) or (tit >= TITULO_PARECIDO and txt >= TEXTO_QUASE_TODO):
            aceitos.append((tit + txt, c))
    if len(aceitos) != 1:
        return None                      # nenhum, ou dois parecidos demais: fica para o registro manual
    return aceitos[0][1]


def texto_alterado(corpo_registrado: str | None, html: str) -> bool:
    """A página publicada deixou de trazer o texto registrado (mais da metade das palavras sumiu)?"""
    if len(palavras(corpo_registrado)) < 20:
        return False                     # texto curto demais para comparar com segurança
    return contido(corpo_registrado, ler_noticia(html)["texto"]) < TEXTO_ALTERADO


def no_site(url: str, cfg: dict) -> bool:
    return (urlsplit(url).hostname or "").removeprefix("www.") == (urlsplit(cfg["lista"]).hostname or "").removeprefix("www.")


def configuracao(banco: Banco) -> dict:
    """Padrão, com o que for válido da chave `site` de Configurações (valor estranho volta ao padrão)."""
    cfg = dict(CONFIG_PADRAO, desligado=False)
    proprio = banco.config("site")
    if not isinstance(proprio, dict):
        return cfg
    if isinstance(proprio.get("lista"), str) and re.match(r"https?://[!-~]+$", proprio["lista"]):
        cfg["lista"] = proprio["lista"]
    if isinstance(proprio.get("padrao"), str) and proprio["padrao"].strip():
        try:
            re.compile(proprio["padrao"])
            cfg["padrao"] = proprio["padrao"]
        except re.error:
            pass
    if isinstance(proprio.get("max_noticias"), int) and not isinstance(proprio["max_noticias"], bool):
        cfg["max_noticias"] = min(max(proprio["max_noticias"], 1), 50)
    cfg["desligado"] = proprio.get("desligado") is True
    return cfg


def executar(banco: Banco, baixar_pagina=lambda url: baixar(url, tentativas=2)[1], hoje: date | None = None) -> list[str]:
    cfg = configuracao(banco)
    if cfg.get("desligado"):
        return ["desligado em Configurações (chave site)"]
    candidatos = banco.conteudos_aprovados_sem_site()
    if not candidatos:
        return []
    registrados = {chave_url(r["url"]) for r in banco.links_publicados() if r.get("url")}
    hoje = hoje or hoje_brasilia()
    feito = []
    for url in links_da_lista(baixar_pagina(cfg["lista"]), cfg["lista"], cfg["padrao"], int(cfg["max_noticias"])):
        if chave_url(url) in registrados or not no_site(url, cfg) or not candidatos:
            continue
        try:
            noticia = ler_noticia(baixar_pagina(url))
        except ErroDownload as e:
            feito.append(f"{url}: não abriu ({e})")
            continue
        conteudo = escolher(noticia, candidatos)
        if conteudo is None:
            continue
        quando = noticia["data"] if noticia["data"] and noticia["data"] <= hoje else hoje
        try:
            banco.registrar_divulgacao(conteudo["id"], url, quando, OBSERVACAO)
        except ErroBanco as e:          # pendência no assunto, conteúdo alterado...: fica para o registro manual
            feito.append(f"{url}: corresponde a \"{conteudo['titulo'][:60]}\", mas o registro foi recusado ({e})")
            continue
        candidatos = [c for c in candidatos if c["id"] != conteudo["id"]]
        feito.append(f"registrado: \"{conteudo['titulo'][:60]}\" → {url} ({quando.strftime('%d/%m/%Y')})")
    return feito


def main() -> int:
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and chave):
        print("Publicações no site: sem as chaves do banco; nada a fazer.")
        return 0
    try:
        feito = executar(Banco(url, chave))
    except Exception as e:      # nunca deixa a coleta vermelha: o registro manual continua valendo
        print(f"! publicações no site não foram conferidas: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    print("Publicações no site: " + ("; ".join(feito) if feito else "nada novo para registrar."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
