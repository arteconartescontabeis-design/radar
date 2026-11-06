"""Radar Artecon — DOU pelo site oficial (Leitura do Jornal, v0.65.0).

Enquanto o INLABS (inlabs.in.gov.br) está em manutenção — fora do ar desde 19/10/2026, com a própria
página oficial avisando e apontando a "Base de Dados de Publicações do DOU" no site — o Diário Oficial
é lido pela página pública **Leitura do Jornal** do in.gov.br, que entrega, SEM login, um JSON com
todas as matérias do dia por seção (dentro de ``<script id="params" type="application/json">``):
título, tipo do ato (artType), órgão (hierarchyStr/hierarchyList), página, data e um trecho do texto.

É a MESMA informação oficial do INLABS, por outra porta. Quando o INLABS voltar, as duas fontes
convivem: os atos repetidos caem na detecção de duplicata de sempre (título/conteúdo iguais entre
fontes). O texto completo de cada ato escolhido vem da página dele no in.gov.br
(/web/dou/-/{urlTitle}), pelo caminho comum do robô (config.seletor_texto) — por isso o filtro aqui
precisa ser apertado: só os atos dos órgãos e tipos configurados viram captura.

config da fonte (os mesmos nomes do coletor do INLABS):
    secoes           lista de seções da Leitura do Jornal (padrão ["do1"]; "do1e" é a edição extra)
    orgaos           expressão (ou lista) casada com o ÓRGÃO (hierarchyStr); vazio = todos
    excluir_orgao    expressão que DERRUBA pelo órgão (ex.: unidades regionais)
    tipos            expressão casada com o tipo do ato (artType; reserva: o começo do título)
    janela_dias      dias para trás, contando HOJE (padrão 3: a edição sai de manhã; fim de semana
                     e feriado não têm edição e são pulados sem falha)
    max_itens        teto por rodada (o padrão do _finalizar: 40)
    palavras / excluir_palavras   o filtro de tema de sempre (radar_coletores.filtro_de_tema)
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta

import requests

from radar_coletores import Item, Listagem, _finalizar, expressao_do_tema
from radar_util import AGENTE, ErroDownload, hoje_brasilia, normalizar_espacos, sem_acentos

BASE = "https://www.in.gov.br"
LEITURA = BASE + "/leiturajornal?data={data}&secao={secao}"
MATERIA = BASE + "/web/dou/-/{url_title}"
RE_PARAMS = re.compile(r'<script[^>]*\bid="params"[^>]*>(.*?)</script>', re.S | re.I)
SECOES_PADRAO = ["do1"]
PAUSA_PEDIDOS = 1.0        # educação com o site oficial: um pedido por segundo


def _pausa(segundos: float = PAUSA_PEDIDOS) -> None:
    """Separada para os testes não esperarem de verdade."""
    time.sleep(segundos)


def _expressao(config: dict, campo: str) -> re.Pattern | None:
    """orgaos/excluir_orgao/tipos: expressão (ou lista), sem acento e sem caixa — a régua de expressao_do_tema."""
    return expressao_do_tema(config.get(campo), campo)


def _data_da_materia(valor: str | None) -> date | None:
    try:
        return datetime.strptime(str(valor or "").strip()[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def materias_da_pagina(conteudo: str) -> list[dict]:
    """O JSON de dentro da página (<script id="params">): a lista jsonArray, ou erro claro se o site mudou."""
    m = RE_PARAMS.search(conteudo or "")
    if not m:
        raise ErroDownload("Leitura do Jornal sem o bloco de dados (script id=\"params\"): o site oficial mudou de formato")
    try:
        dados = json.loads(m.group(1))
    except ValueError as e:
        raise ErroDownload(f"Leitura do Jornal com o bloco de dados ilegível: {e}") from e
    lista = dados.get("jsonArray") if isinstance(dados, dict) else None
    if lista is None:
        return []                         # dia sem edição (fim de semana, feriado): a página vem sem a lista
    return [x for x in lista if isinstance(x, dict)]


def filtrar(materias: list[dict], config: dict) -> list[dict]:
    orgaos = _expressao(config, "orgaos")
    excluir = _expressao(config, "excluir_orgao")
    tipos = _expressao(config, "tipos")
    escolhidas = []
    for m in materias:
        orgao = normalizar_espacos(str(m.get("hierarchyStr") or ""))
        tipo = normalizar_espacos(str(m.get("artType") or "")) or normalizar_espacos(str(m.get("title") or ""))[:80]
        if not (m.get("urlTitle") and (m.get("title") or m.get("content"))):
            continue
        if orgaos is not None and orgaos.search(sem_acentos(orgao)) is None:
            continue
        if excluir is not None and excluir.search(sem_acentos(orgao)) is not None:
            continue
        if tipos is not None and tipos.search(sem_acentos(tipo)) is None:
            continue
        escolhidas.append(m)
    return escolhidas


def para_item(m: dict) -> Item:
    titulo = normalizar_espacos(str(m.get("title") or "")) or normalizar_espacos(str(m.get("content") or ""))[:120]
    orgao = normalizar_espacos(str(m.get("hierarchyStr") or ""))
    texto = normalizar_espacos(str(m.get("content") or ""))
    return Item(url=MATERIA.format(url_title=str(m.get("urlTitle")).strip("/")),
                titulo=titulo[:300],
                data=_data_da_materia(m.get("pubDate")),
                resumo=(orgao[:280] or None),
                texto_da_listagem=texto or None,
                metadados={"orgao": orgao, "tipo": normalizar_espacos(str(m.get("artType") or "")),
                           "secao": str(m.get("pubName") or ""), "pagina_dou": str(m.get("numberPage") or "")},
                # título de ato é só número e data: o filtro de tema olha o começo do texto, como no INLABS
                trecho_do_tema=texto[:500] or None)


def _dias(config: dict, hoje: date) -> list[date]:
    janela = max(1, min(int(config.get("janela_dias", 3)), 7))
    return [hoje - timedelta(days=n) for n in range(0, janela)]


def listar_paginas(sessao: requests.Session, fonte: dict, hoje: date | None = None) -> tuple[Listagem, int | None]:
    config = fonte.get("config") or {}
    hoje = hoje or hoje_brasilia()
    secoes = [str(s).strip().lower() for s in (config.get("secoes") or SECOES_PADRAO) if str(s).strip()]
    materias: list[dict] = []
    incompleta: str | None = None
    paginas_lidas = 0
    for dia in _dias(config, hoje):
        for secao in secoes:
            if paginas_lidas:
                _pausa()
            url = LEITURA.format(data=dia.strftime("%d-%m-%Y"), secao=secao)
            try:
                r = sessao.get(url, timeout=60, headers={"User-Agent": AGENTE, "Accept": "text/html"})
            except requests.RequestException as e:
                raise ErroDownload(f"Leitura do Jornal ({url}): {type(e).__name__}: {e}") from e
            paginas_lidas += 1
            if r.status_code == 404:
                continue                   # dia sem edição (fim de semana, feriado)
            if r.status_code != 200:
                # um dia antigo que falhou não derruba a rodada; o DIA MAIS NOVO derruba (é o que importa)
                if dia == hoje:
                    raise ErroDownload(f"Leitura do Jornal respondeu HTTP {r.status_code} em {url}", r.status_code)
                incompleta = incompleta or f"a Leitura do Jornal de {dia.strftime('%d/%m/%Y')} respondeu HTTP {r.status_code}"
                continue
            materias += materias_da_pagina(r.text)
    escolhidas = filtrar(materias, config)
    resultado = _finalizar([para_item(m) for m in escolhidas],
                           dict(config, janela_dias=int(config.get("janela_dias", 3)) + 1), hoje)
    resultado.brutos = len(materias)       # matérias lidas do dia, mesmo fora dos órgãos/tipos: dia vazio ≠ layout mudado
    resultado.incompleta = resultado.incompleta or incompleta
    return resultado, 200
