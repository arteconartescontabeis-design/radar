"""Coletor das APIs de Dados Abertos do Poder Legislativo — proposições (Câmara) e processos/matérias (Senado) recentes,
de tema tributário e trabalhista.

Config da fonte (radar_fontes.config):
  * "casa": "camara" ou "senado" (obrigatório).
  * "janela_dias": período para trás a partir de hoje (padrão 30).
  * CÂMARA — "temas": lista de codTema do endpoint de proposições (padrão [70, 58] = Finanças Públicas/Orçamento e Trabalho e
    Emprego — a Câmara NÃO tem um tema "Tributação"). A própria API filtra por tema no servidor.
  * SENADO — não há tema simples na API /processo: use "palavras" (regex na ementa, do filtro de tema comum, aplicado por
    _finalizar) para ficar só com o que interessa; ancore as siglas curtas com \\b (ex.: "\\biss\\b", "\\bmei\\b") para não
    casar pedaço de palavra (comissão, primeiro). Vale também para a Câmara, além do filtro de tema do servidor.
  * "sem_pagina_de_texto": true — a ementa da API é o texto guardado (a ficha/matéria é uma página SPA, sem texto direto).
  * "paginas_max": teto de páginas por casa/tema (padrão 5; o Senado faz uma requisição só).

A busca é feita aqui (GET com o período na URL); o parse devolve itens para o fluxo comum (_finalizar aplica janela, dedupe e o
filtro de tema). Nada é inventado: cada item leva a URL pública da proposição/matéria, o título (sigla/identificação) e a ementa.
"""
import json
import time
from datetime import date, timedelta

import requests

from radar_coletores import Item, _finalizar
from radar_util import ErroDownload, baixar, hoje_brasilia, normalizar_espacos

CAMARA_PROPOSICOES = "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
CAMARA_FICHA = "https://www.camara.leg.br/propostas-legislativas/{id}"
SENADO_PROCESSO = "https://legis.senado.leg.br/dadosabertos/processo"
SENADO_MATERIA = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{id}"
TEMAS_CAMARA_PADRAO = [70, 58]      # 70 Finanças Públicas e Orçamento; 58 Trabalho e Emprego


def _data_iso(valor) -> date | None:
    s = str(valor or "")[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _json(sessao, url, cabecalhos=None):
    http, texto = baixar(url, sessao, cabecalhos=cabecalhos)
    try:
        # v0.110.0: 200 com HTML (manutenção/erro) em vez de JSON vira ErroDownload com o status, não um JSONDecodeError cru
        return http, json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErroDownload(f"a API respondeu {http} mas não em JSON (o layout pode ter mudado): {e}", http)


def _camara(sessao, config, hoje, maximo):
    ini = (hoje - timedelta(days=int(config.get("janela_dias", 30)))).isoformat()
    temas = config.get("temas") or TEMAS_CAMARA_PADRAO
    itens, http, incompleta, leu_algo = [], None, None, False
    for tema in temas:
        url = (f"{CAMARA_PROPOSICOES}?codTema={int(tema)}&dataApresentacaoInicio={ini}&dataApresentacaoFim={hoje.isoformat()}"
               "&ordem=DESC&ordenarPor=id&itens=100")
        n = 0
        while url and n < maximo:
            n += 1
            if n > 1:
                time.sleep(0.3)
            try:
                http, dados = _json(sessao, url, cabecalhos={"Accept": "application/json"})
            except Exception as e:
                # v0.110.0: só vira falha total se NADA foi lido; um tema vazio seguido de erro em outro é "parcial", não "falha"
                if not leu_algo:
                    raise
                incompleta = f"uma página da Câmara (tema {tema}) não pôde ser lida ({e})"
                break
            leu_algo = True
            for p in (dados.get("dados") if isinstance(dados, dict) else None) or []:
                if not isinstance(p, dict) or not p.get("id"):
                    continue
                sigla = normalizar_espacos(f"{p.get('siglaTipo', '')} {p.get('numero', '')}/{p.get('ano', '')}")
                ementa = normalizar_espacos(str(p.get("ementa") or "")) or None
                titulo = (f"{sigla} — {ementa[:80]}" if sigla and ementa else sigla or ementa or "Proposição")
                itens.append(Item(url=CAMARA_FICHA.format(id=p["id"]), titulo=titulo,
                                  data=_data_iso(p.get("dataApresentacao")), resumo=ementa, texto_da_listagem=ementa,
                                  metadados={"casa": "camara", "sigla_tipo": normalizar_espacos(str(p.get("siglaTipo") or "")) or None}))
            links = dados.get("links") if isinstance(dados, dict) else None
            url = next((l.get("href") for l in (links or []) if isinstance(l, dict) and l.get("rel") == "next"), None)
    return itens, http, incompleta


def _senado(sessao, config, hoje):
    ini = (hoje - timedelta(days=int(config.get("janela_dias", 30)))).isoformat()
    url = f"{SENADO_PROCESSO}?dataInicioApresentacao={ini}&dataFimApresentacao={hoje.isoformat()}&tramitando=S"
    http, dados = _json(sessao, url, cabecalhos={"Accept": "application/json"})
    lista = dados if isinstance(dados, list) else (dados.get("ListaProcessos") or dados.get("Processos") or [])
    itens = []
    for m in lista:
        if not isinstance(m, dict):
            continue
        cod = m.get("codigoMateria") or m.get("id")
        if not cod:
            continue
        titulo = normalizar_espacos(str(m.get("identificacao") or m.get("tipoDocumento") or "Matéria do Senado"))
        ementa = normalizar_espacos(str(m.get("ementa") or "")) or None
        itens.append(Item(url=SENADO_MATERIA.format(id=cod), titulo=titulo,
                          data=_data_iso(m.get("dataApresentacao")), resumo=ementa, texto_da_listagem=ementa,
                          metadados={"casa": "senado", "tipo_documento": normalizar_espacos(str(m.get("tipoDocumento") or "")) or None}))
    return itens, http, None


def listar_paginas(sessao: requests.Session | None, fonte: dict, hoje: date | None = None):
    """Busca e devolve (Listagem, status HTTP). A casa vem de config.casa."""
    config = fonte.get("config") or {}
    hoje = hoje or hoje_brasilia()
    casa = str(config.get("casa") or "").lower()
    maximo = max(1, int(config.get("paginas_max", 5)))
    if casa == "camara":
        itens, http, incompleta = _camara(sessao, config, hoje, maximo)
    elif casa == "senado":
        itens, http, incompleta = _senado(sessao, config, hoje)
    else:
        raise ValueError("fonte api_legislativo sem config.casa (use \"camara\" ou \"senado\")")
    resultado = _finalizar(itens, config, hoje)
    resultado.incompleta = incompleta
    return resultado, http
