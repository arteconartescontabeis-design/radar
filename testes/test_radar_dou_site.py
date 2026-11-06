"""v0.65.0 — DOU pela Leitura do Jornal do site oficial (robo/radar_dou_site.py), sem rede e sem banco.

Enquanto o INLABS está em manutenção (fora do ar desde 19/10/2026, com aviso na própria página oficial), o DOU é
lido pela página pública Leitura do Jornal do in.gov.br: um JSON por dia e seção (script id="params"), com título,
tipo (artType), órgão (hierarchyStr), página e um trecho do texto — sem login. Estes testes usam um site de mentira
(os pedidos ficam registrados) e conferem o filtro por órgão e tipo, os campos do item, o fim de semana sem edição
(404 não é falha), o dia antigo com erro (a rodada segue, incompleta) e o aviso claro quando o site muda de formato.
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

import radar_dou_site
from radar_util import ErroDownload

HOJE = date(2026, 11, 6)
FONTE = {"slug": "dou-site", "tipo_coletor": "dou_site", "url": "https://www.in.gov.br/leiturajornal",
         "config": {"secoes": ["do1"], "janela_dias": 3, "max_itens": 60,
                    "orgaos": "Receita Federal|Procuradoria-Geral da Fazenda Nacional|Comitê Gestor do Simples Nacional",
                    "excluir_orgao": "Superintendência Regional|Delegacia",
                    "tipos": "Instrução Normativa|Ato Declaratório|Portaria|Solução de Consulta|Lei|Decreto|Medida Provisória"}}


def materia(url_title="instrucao-normativa-rfb-n-2300-de-5-de-novembro-de-2026-742000001",
            title="INSTRUÇÃO NORMATIVA RFB Nº 2.300, DE 5 DE NOVEMBRO DE 2026",
            art_type="Instrução Normativa",
            orgao="Ministério da Fazenda/Secretaria Especial da Receita Federal do Brasil",
            content="Dispõe sobre a entrega da DCTFWeb e dá outras providências.",
            data="06/11/2026", **extras):
    m = {"urlTitle": url_title, "title": title, "artType": art_type, "hierarchyStr": orgao, "content": content,
         "pubDate": data, "pubName": "DO1", "numberPage": "33", "hierarchyList": orgao.split("/"),
         "hierarchyLevelSize": 2, "editionNumber": "211", "pubOrder": "1", "subTitulo": "", "titulo": ""}
    m.update(extras)
    return m


def pagina(*materias) -> str:
    corpo = json.dumps({"jsonArray": list(materias)}, ensure_ascii=False)
    return f'<html><head><script id="params" type="application/json">{corpo}</script></head><body>Leitura</body></html>'


class SiteFalso:
    """O in.gov.br de mentira: cada data-seção com a sua resposta; os pedidos ficam registrados."""

    def __init__(self, paginas: dict[str, str | int]):
        self.paginas = paginas            # "06-11-2026/do1" -> html (ou um int: o HTTP de erro)
        self.pedidos: list[str] = []

    def get(self, url, timeout=None, headers=None):
        self.pedidos.append(url)
        chave = url.split("data=")[1].replace("&secao=", "/")
        resposta = self.paginas.get(chave)
        if resposta is None:
            return SimpleNamespace(status_code=404, text="")
        if isinstance(resposta, int):
            return SimpleNamespace(status_code=resposta, text="")
        return SimpleNamespace(status_code=200, text=resposta)


@pytest.fixture(autouse=True)
def sem_pausa(monkeypatch):
    monkeypatch.setattr(radar_dou_site, "_pausa", lambda *a, **k: None)


def test_filtra_por_orgao_e_tipo_e_monta_o_item_completo():
    site = SiteFalso({
        "06-11-2026/do1": pagina(
            materia(),                                                            # entra (Receita, IN)
            materia(url_title="despacho-anvisa-742000002", title="DESPACHO Nº 135, DE 5 DE NOVEMBRO DE 2026",
                    art_type="Despacho", orgao="Ministério da Saúde/Agência Nacional de Vigilância Sanitária"),
            materia(url_title="portaria-srrf-742000003", title="PORTARIA SRRF08 Nº 9, DE 5 DE NOVEMBRO DE 2026",
                    art_type="Portaria", orgao="Ministério da Fazenda/Superintendência Regional da Receita Federal"),
            materia(url_title="ato-declaratorio-pgfn-742000004", title="ATO DECLARATÓRIO PGFN Nº 7, DE 5 DE NOVEMBRO DE 2026",
                    art_type="Ato Declaratório", orgao="Ministério da Fazenda/Procuradoria-Geral da Fazenda Nacional",
                    content="Declara a dispensa de contestação sobre o tema X.")),
        # fim de semana sem edição: a chave nem existe (404) — não é falha
    })
    listagem, http = radar_dou_site.listar_paginas(site, FONTE, HOJE)
    assert http == 200
    assert listagem.brutos == 4                                                   # tudo o que foi lido, mesmo fora do filtro
    assert [i.titulo for i in listagem.itens] == ["INSTRUÇÃO NORMATIVA RFB Nº 2.300, DE 5 DE NOVEMBRO DE 2026",
                                                  "ATO DECLARATÓRIO PGFN Nº 7, DE 5 DE NOVEMBRO DE 2026"]
    item = listagem.itens[0]
    assert item.url == "https://www.in.gov.br/web/dou/-/instrucao-normativa-rfb-n-2300-de-5-de-novembro-de-2026-742000001"
    assert item.data == date(2026, 11, 6)
    assert item.resumo == "Ministério da Fazenda/Secretaria Especial da Receita Federal do Brasil"
    assert item.texto_da_listagem.startswith("Dispõe sobre a entrega da DCTFWeb")
    assert item.trecho_do_tema.startswith("Dispõe sobre")
    assert item.metadados["orgao"].endswith("Receita Federal do Brasil")
    assert item.metadados["tipo"] == "Instrução Normativa"
    assert item.metadados["secao"] == "DO1" and item.metadados["pagina_dou"] == "33"
    # a janela de 3 dias com uma seção = 3 pedidos, todos na Leitura do Jornal
    assert len(site.pedidos) == 3 and all(p.startswith("https://www.in.gov.br/leiturajornal?data=") for p in site.pedidos)


def test_dia_sem_edicao_e_dia_antigo_com_erro_nao_derrubam_mas_o_dia_de_hoje_derruba():
    # ontem com erro 500: a rodada segue, marcada incompleta; anteontem sem edição (404): nada a dizer
    site = SiteFalso({"06-11-2026/do1": pagina(materia()), "05-11-2026/do1": 500})
    listagem, _ = radar_dou_site.listar_paginas(site, FONTE, HOJE)
    assert len(listagem.itens) == 1
    assert "05/11/2026" in (listagem.incompleta or "") and "HTTP 500" in listagem.incompleta
    # o dia de HOJE com erro derruba a rodada (é a edição que importa)
    site = SiteFalso({"06-11-2026/do1": 503})
    with pytest.raises(ErroDownload, match="HTTP 503"):
        radar_dou_site.listar_paginas(site, FONTE, HOJE)


def test_site_sem_o_bloco_de_dados_avisa_mudanca_de_formato():
    site = SiteFalso({"06-11-2026/do1": "<html><body>Novo portal sem o JSON</body></html>"})
    with pytest.raises(ErroDownload, match='script id="params"'):
        radar_dou_site.listar_paginas(site, FONTE, HOJE)


def test_pagina_sem_a_lista_e_dia_vazio_nao_viram_alarme_de_layout():
    # a página veio com o bloco, mas sem jsonArray (dia sem edição): zero matérias, sem erro
    sem_lista = '<html><script id="params" type="application/json">{"outra": 1}</script></html>'
    site = SiteFalso({"06-11-2026/do1": sem_lista})
    listagem, _ = radar_dou_site.listar_paginas(site, FONTE, HOJE)
    assert listagem.brutos == 0 and listagem.itens == []


def test_filtro_de_tema_das_configuracoes_vale_sobre_o_trecho_do_texto():
    fonte = dict(FONTE, config=dict(FONTE["config"], palavras=["DCTFWeb"], janela_dias=1))
    site = SiteFalso({"06-11-2026/do1": pagina(
        materia(),                                                                # fala de DCTFWeb: entra
        materia(url_title="in-rfb-aduana-742000009", title="INSTRUÇÃO NORMATIVA RFB Nº 2.301, DE 5 DE NOVEMBRO DE 2026",
                content="Dispõe sobre o despacho aduaneiro de importação."))})    # fora do tema
    listagem, _ = radar_dou_site.listar_paginas(site, fonte, HOJE)
    assert [i.url.rsplit("-", 1)[-1] for i in listagem.itens] == ["742000001"]
    assert listagem.fora_do_tema == 1


def test_secoes_e_janela_configuraveis_e_edicao_extra():
    fonte = dict(FONTE, config=dict(FONTE["config"], secoes=["do1", "do1e"], janela_dias=2))
    extra = materia(url_title="mp-do-apoio-742000010", title="MEDIDA PROVISÓRIA Nº 1.400, DE 6 DE NOVEMBRO DE 2026",
                    art_type="Medida Provisória", orgao="Atos do Poder Executivo", data="06/11/2026")
    fonte["config"]["orgaos"] = ""                                               # sem filtro de órgão: entra pelo tipo
    site = SiteFalso({"06-11-2026/do1": pagina(materia()), "06-11-2026/do1e": pagina(extra),
                      "05-11-2026/do1": pagina(), "05-11-2026/do1e": pagina()})
    listagem, _ = radar_dou_site.listar_paginas(site, fonte, HOJE)
    assert len(site.pedidos) == 4                                                # 2 dias × 2 seções
    assert {i.metadados["tipo"] for i in listagem.itens} == {"Instrução Normativa", "Medida Provisória"}
