"""Radar Artecon — atos normativos da Receita pelo sistema Normas (v0.31.0).

Desde 04/10/2026 o endereço antigo (sijut2consulta/consulta.action) devolve uma aplicação montada no navegador, sem a tabela de
atos. A própria página tira os dados de uma pesquisa pública, sem captcha e sem login:

    POST https://normas.receita.fazenda.gov.br/api/indexacao/ato/pesquisar   (corpo JSON: período, página, ordem)

Este módulo faz só esses pedidos, como o radar_inlabs.py faz com o INLABS; a leitura da resposta (e do texto de cada ato) fica em
radar_coletores.py, que não acessa a rede e é testada com respostas reais guardadas em testes/amostras/.

    config.janela_dias        dias para trás, pela data de publicação (padrão 10)
    config.paginas_max        quantas páginas no máximo (padrão 5)
    config.itens_por_pagina   atos por página (padrão 100; a API aceita até 300)
    config.excluir_orgao      expressão sobre as siglas dos órgãos (tira as unidades regionais)
    config.excluir_palavras   expressão (ou lista) sobre o título e a ementa (tira assuntos alheios ao escritório)
    config.url_texto          de onde baixar o texto de cada ato ({id} = número do ato); o padrão é a consulta externa
    config.sem_pagina_de_texto  true: guarda só a ementa (plano B, se a consulta do texto for bloqueada)
    config.tipos_ids / orgaos_siglas  filtros do próprio site (ids dos tipos e siglas dos órgãos, separados por ";")
"""
from __future__ import annotations

import time
from datetime import date

import requests

from radar_coletores import CHAVES_DO_TEMA, Listagem, _finalizar, corpo_pesquisa_normas, json_da_pesquisa_normas, listar_normas_rfb
from radar_util import ErroDownload, hoje_brasilia, postar_json

ENDERECO_PESQUISA = "https://normas.receita.fazenda.gov.br/api/indexacao/ato/pesquisar"
RECUSA = ("o site da Receita recusou o pedido do robô (HTTP 403: bloqueio de acesso automático, que costuma ser pelo endereço "
          "de onde o robô roda, no GitHub); os atos da Receita continuam chegando pelo DOU (dou-inlabs)")


def endereco_antigo(url: str) -> bool:
    """O cadastro de antes da v0.31.0 (a consulta antiga, com {inicio}, {fim} e {p} no endereço), que não existe mais."""
    return "{" in url or "sijut2consulta" in url


def pesquisar(sessao: requests.Session | None, url: str, corpo: dict) -> tuple[int, str]:
    """Um pedido à pesquisa. HTTP 403 vira um erro que diz o que aconteceu (o site recusou o robô) e por onde os atos chegam."""
    try:
        return postar_json(url, corpo, sessao)
    except ErroDownload as e:
        if e.http_status == 403:
            raise ErroDownload(RECUSA, 403) from e
        raise


def listar_paginas(sessao: requests.Session | None, fonte: dict, hoje: date | None = None, pausa: float = 1.0,
                   guardar=None) -> tuple[Listagem, int | None]:
    """Pede a página 1 da pesquisa e, se houver mais, as seguintes (até config.paginas_max), com uma pausa entre elas. Falha na
    1ª página é falha da fonte; numa página seguinte, segue com o que já leu e anota que a leitura ficou incompleta.
    `guardar(n, texto)` recebe cada resposta (o diagnóstico guarda as páginas)."""
    config = fonte.get("config") or {}
    hoje = hoje or hoje_brasilia()
    url = fonte["url"]
    if endereco_antigo(url):
        raise ValueError("o endereço desta fonte ainda é o da consulta antiga do sistema Normas, que não existe mais desde "
                         "04/10/2026: rode o sql/radar-fontes-novas-v0.31.0.sql (ele troca o endereço pela pesquisa nova)")
    maximo = max(1, int(config.get("paginas_max", 5)))
    # o limite de itens e o filtro de tema valem para o conjunto das páginas
    sem_corte = {k: v for k, v in dict(config, max_itens=10 ** 6).items() if k not in CHAVES_DO_TEMA}
    itens, brutos, http, incompleta = [], 0, None, None
    paginas, n = 1, 1
    while n <= min(paginas, maximo):
        if n > 1:
            time.sleep(pausa)                  # gentileza com o site
        try:
            http, texto = pesquisar(sessao, url, corpo_pesquisa_normas(fonte, hoje, n))
            if guardar:
                guardar(n, texto)
            dados = json_da_pesquisa_normas(texto)
            parte = listar_normas_rfb(dados, dict(fonte, config=sem_corte), hoje)
        except Exception as e:
            if n == 1:
                raise
            incompleta = f"a página {n} da pesquisa não pôde ser lida ({e}); os atos das páginas anteriores foram aproveitados"
            break
        brutos += parte.brutos
        itens += parte.itens
        try:
            paginas = int(dados.get("quantidadePaginas") or 1)
        except (TypeError, ValueError):
            paginas = 1
        if not dados["atos"]:
            break
        n += 1
    resultado = _finalizar(itens, config, hoje)
    resultado.brutos = brutos
    resultado.incompleta = incompleta
    return resultado, http
