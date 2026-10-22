"""Radar Artecon — DOM/SC pelos dados abertos da CIGA (v0.45.0).

A CIGA não permite robôs no site do diário (diariomunicipal.sc.gov.br) — pedido avaliado e negado
pelo suporte em 20/10/2026 — e o portal de dados abertos (dados.ciga.sc.gov.br) proíbe a API no
robots.txt (Disallow: /api/; Crawl-Delay: 10). Por isso este coletor:

  * roda UMA rodada por dia (frequencia_horas: 24 na fonte);
  * lê a página HTML do conjunto do mês (/pt_BR/dataset/domsc-publicacoes-de-MM-AAAA; o caminho
    sem /pt_BR respondia Gateway Timeout em 21/10/2026) — é dela que saem os endereços diretos
    dos arquivos (cigadados_publicacoes_AAAA_MM_DD_HHMM_HHMM.zip, três janelas por dia);
  * baixa só os arquivos dos dias da janela (padrão 2: ontem e anteontem — o arquivo da última
    janela do dia sai pouco depois da meia-noite, e o dia visto duas vezes não perde nada),
    com pausa de 10 segundos entre um pedido e outro (o Crawl-Delay do robots.txt);
  * NUNCA visita diariomunicipal.sc.gov.br: o texto completo do ato já vem no JSON de dentro do
    ZIP; o endereço da captura aponta ao diário oficial só para a PESSOA abrir no navegador.

config da fonte:
    municipios       lista de municípios (padrão ["Palhoça", "São José"]); sem diferença de
                     acento e de maiúsculas
    categorias       lista de categorias do DOM/SC (padrão ["Leis", "Decretos"]; vazia = todas)
    janela_dias      dias para trás, sem contar hoje (padrão 2)
    max_zips         teto de arquivos por rodada (padrão 8: um dia extraordinário com mais
                     janelas não vira enxurrada de pedidos)
    palavras / excluir_palavras   o filtro de tema de sempre (radar_coletores.filtro_de_tema)
O texto vem da própria listagem (texto_do_feed: true na fonte): o robô não abre página nenhuma
além do portal de dados abertos.
"""
from __future__ import annotations

import io
import json
import re
import time
import zipfile
from datetime import date, datetime, timedelta

import requests

from radar_coletores import Item, Listagem, _finalizar
from radar_util import AGENTE, ErroDownload, baixar, extrair_texto, hoje_brasilia, normalizar_espacos

BASE = "https://dados.ciga.sc.gov.br"
CONJUNTO = BASE + "/pt_BR/dataset/domsc-publicacoes-de-{mes:02d}-{ano}"
# o endereço direto do arquivo, como aparece na página do conjunto
ARQUIVO_RX = re.compile(r'href="(https://dados\.ciga\.sc\.gov\.br/dataset/[^"]+/download/'
                        r'cigadados_publicacoes_(\d{4})_(\d{2})_(\d{2})_\d{4}_\d{4}\.zip)"')
PAUSA_PORTAL = 10.0        # o Crawl-Delay do robots.txt do portal
MUNICIPIOS_PADRAO = ["Palhoça", "São José"]
CATEGORIAS_PADRAO = ["Leis", "Decretos"]
MAX_ZIPS_PADRAO = 8


def _pausa(segundos: float = PAUSA_PORTAL) -> None:
    """Separada para os testes não esperarem de verdade."""
    time.sleep(segundos)


def _chave(texto: str) -> str:
    """Comparação sem acento e sem caixa (Palhoça == PALHOCA)."""
    trocas = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
    return normalizar_espacos(str(texto or "")).lower().translate(trocas)


def _baixar_bytes(sessao: requests.Session, url: str, tentativas: int = 2, limite: int = 120) -> bytes:
    ultimo: ErroDownload | None = None
    for n in range(1, tentativas + 1):
        try:
            r = sessao.get(url, timeout=limite, headers={"User-Agent": AGENTE, "Accept": "*/*"})
            if r.status_code == 200:
                return r.content
            ultimo = ErroDownload(f"HTTP {r.status_code} em {url}", r.status_code)
            if r.status_code in (400, 401, 403, 404, 410):
                break
        except requests.RequestException as e:
            ultimo = ErroDownload(f"{type(e).__name__}: {e}")
        if n < tentativas:
            _pausa()                       # a nova tentativa também respeita o Crawl-Delay
    raise ultimo or ErroDownload(f"falha ao baixar {url}")


def _data_da_publicacao(valor: str | None) -> date | None:
    try:
        return datetime.fromisoformat(str(valor or "").strip().replace(" ", "T")[:19]).date()
    except ValueError:
        return None


def publicacoes_do_zip(dados: bytes) -> list[dict]:
    """As publicações de um arquivo do portal (todas as listas do JSON: autopublicações e edições)."""
    publicacoes: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for nome in z.namelist():
            if not nome.lower().endswith(".json"):
                continue
            try:
                lido = json.loads(z.read(nome).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue                   # um arquivo estragado não derruba a rodada
            listas = [lido] if isinstance(lido, list) else \
                     [v for v in lido.values() if isinstance(v, list)] if isinstance(lido, dict) else []
            for lista in listas:
                publicacoes += [p for p in lista if isinstance(p, dict)]
    return publicacoes


def filtrar(publicacoes: list[dict], config: dict) -> list[dict]:
    municipios = {_chave(m) for m in (config.get("municipios") or MUNICIPIOS_PADRAO)}
    categorias = {_chave(c) for c in (config.get("categorias") if config.get("categorias") is not None
                                      else CATEGORIAS_PADRAO) if str(c).strip()}
    escolhidas = []
    for p in publicacoes:
        if not (p.get("codigo") and p.get("titulo")):
            continue
        if _chave(p.get("municipio")) not in municipios:
            continue
        if categorias and _chave(p.get("categoria")) not in categorias:
            continue
        escolhidas.append(p)
    return escolhidas


def para_item(p: dict) -> Item:
    municipio = normalizar_espacos(str(p.get("municipio") or ""))
    entidade = normalizar_espacos(str(p.get("entidade") or ""))
    categoria = normalizar_espacos(str(p.get("categoria") or ""))
    titulo = normalizar_espacos(str(p.get("titulo") or ""))
    texto = extrair_texto(str(p.get("texto") or ""))
    resumo = " · ".join(x for x in (entidade or municipio, categoria) if x) or None
    # o endereço oficial da publicação, para a PESSOA abrir no navegador (o robô nunca o visita)
    url = normalizar_espacos(str(p.get("link") or "")) or \
        f"https://diariomunicipal.sc.gov.br/?q=id:{p.get('codigo')}"
    return Item(url=url, titulo=f"{titulo} ({municipio})"[:300] if municipio else titulo[:300],
                data=_data_da_publicacao(p.get("data")),
                resumo=resumo, texto_da_listagem=" ".join(x for x in (titulo, texto) if x) or None,
                metadados={"municipio": municipio, "entidade": entidade, "categoria": categoria,
                           "ciga_codigo": str(p.get("codigo")), "url_pdf": p.get("url") or ""},
                # título de lei é só o número: o filtro de tema olha o começo do texto do ato
                trecho_do_tema=texto[:500] or None)


def _dias(config: dict, hoje: date) -> list[date]:
    janela = max(1, min(int(config.get("janela_dias", 2)), 7))
    return [hoje - timedelta(days=n) for n in range(1, janela + 1)]


def _meses(dias: list[date]) -> list[tuple[int, int]]:
    vistos: list[tuple[int, int]] = []
    for d in dias:
        if (d.year, d.month) not in vistos:
            vistos.append((d.year, d.month))
    return vistos


def listar_paginas(sessao: requests.Session, fonte: dict, hoje: date | None = None) -> tuple[Listagem, int | None]:
    config = fonte.get("config") or {}
    hoje = hoje or hoje_brasilia()
    dias = _dias(config, hoje)
    # 1. a página do conjunto de cada mês da janela (quase sempre um só)
    arquivos: dict[str, date] = {}
    incompleta: str | None = None
    for ano, mes in _meses(dias):
        try:
            _, pagina = baixar(CONJUNTO.format(ano=ano, mes=mes), sessao, tentativas=2, limite=60)
        except ErroDownload as e:
            # o conjunto do mês que virou ontem pode ainda não existir no dia 1º: não é falha da rodada
            if e.http_status == 404 and (ano, mes) != (dias[0].year, dias[0].month):
                incompleta = f"o conjunto de {mes:02d}/{ano} ainda não está no portal"
                continue
            raise
        for url, a, m, d in ARQUIVO_RX.findall(pagina):
            try:
                dia = date(int(a), int(m), int(d))
            except ValueError:
                continue
            if dia in dias and url not in arquivos:
                arquivos[url] = dia
    # 2. os arquivos dos dias da janela, com o Crawl-Delay entre um pedido e outro
    max_zips = max(1, min(int(config.get("max_zips", MAX_ZIPS_PADRAO)), 24))
    pendentes = sorted(arquivos.items(), key=lambda x: (x[1], x[0]))
    if len(pendentes) > max_zips:
        incompleta = incompleta or f"o portal lista {len(pendentes)} arquivos na janela; só os {max_zips} primeiros entraram"
        pendentes = pendentes[:max_zips]
    publicacoes: list[dict] = []
    for url, _dia in pendentes:
        _pausa()
        publicacoes += publicacoes_do_zip(_baixar_bytes(sessao, url))
    if not pendentes and dias[0] not in set(arquivos.values()):
        incompleta = incompleta or (f"os arquivos de {dias[0].strftime('%d/%m/%Y')} ainda não estão no portal; "
                                    "a próxima rodada os pega")
    escolhidas = filtrar(publicacoes, config)
    resultado = _finalizar([para_item(p) for p in escolhidas],
                           dict(config, janela_dias=int(config.get("janela_dias", 2)) + 1), hoje)
    resultado.brutos = len(publicacoes)
    resultado.incompleta = resultado.incompleta or incompleta
    return resultado, 200
