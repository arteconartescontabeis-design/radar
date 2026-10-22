"""v0.45.0 — DOM/SC pelos dados abertos da CIGA (robo/radar_ciga.py), sem rede e sem banco.

O combinado com a CIGA (20/10/2026): nenhum robô no diariomunicipal.sc.gov.br (o suporte confirmou que não há exceção) e, no
portal de dados abertos, o robots.txt vale (Crawl-Delay de 10 s; nunca /api/). O coletor lê a página HTML do conjunto do mês,
baixa só os arquivos dos dias da janela e tira TUDO do JSON de dentro do ZIP (o texto completo do ato vem nele). Estes testes
usam um portal de mentira (os pedidos ficam registrados) e conferem, além do filtro e dos campos, que NENHUM pedido sai do
portal de dados abertos — o endereço do diário aparece só como link guardado, para a pessoa abrir no navegador.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from types import SimpleNamespace

import pytest

import radar_ciga
from radar_util import ErroDownload

HOJE = date(2026, 10, 22)
FONTE = {"slug": "domsc-ciga", "tipo_coletor": "ciga_dados", "url": "https://dados.ciga.sc.gov.br/",
         "config": {"janela_dias": 2, "municipios": ["Palhoça", "São José"], "categorias": ["Leis", "Decretos"],
                    "max_zips": 8, "texto_do_feed": True, "texto_minimo": 1}}


def publicacao(codigo=1001, municipio="Palhoça", categoria="Decretos", titulo="DECRETO Nº 3.456/2026",
               texto="<div><p>Dispõe sobre o IPTU de 2027 e dá outras providências.</p></div>",
               data="2026-10-21 10:30:00", entidade="Prefeitura Municipal de Palhoça", **extras):
    p = {"codigo": codigo, "titulo": titulo, "data": data, "cod_registro_info_sfinge": None, "municipio": municipio,
         "entidade": entidade, "categoria": categoria, "link": f"https://diariomunicipal.sc.gov.br/?q=id:{codigo}",
         "texto": texto, "url": f"https://diariomunicipal.sc.gov.br/arquivos/{codigo}.pdf"}
    p.update(extras)
    return p


def zip_do_portal(*publicacoes, nome="publicacoes_de_2026_10_21.json", extra: dict | None = None) -> bytes:
    """Um arquivo como o real: dict com as duas listas (autopublicações e edições), metade em cada."""
    meio = len(publicacoes) // 2
    corpo = {"autopublicacoes": list(publicacoes[:meio]), "edicoes_ordinarias_exclusivas": list(publicacoes[meio:])}
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, json.dumps(corpo, ensure_ascii=False))
        for outro, dados in (extra or {}).items():
            z.writestr(outro, dados)
    return saida.getvalue()


def pagina_do_mes(*arquivos: str) -> str:
    linhas = "\n".join(
        f'<li><a href="https://dados.ciga.sc.gov.br/dataset/abc-123/resource/r-{i}/download/{nome}">Baixar</a></li>'
        for i, nome in enumerate(arquivos))
    return f"<html><body><h1>DOMSC: Publicações</h1><ul>{linhas}</ul></body></html>"


class PortalFalso:
    """O portal de dados abertos de mentira: registra cada pedido (página do mês e arquivos)."""

    def __init__(self, paginas: dict[str, str], zips: dict[str, bytes]):
        self.paginas, self.zips, self.pedidos, self.pausas = paginas, zips, [], 0

    def baixar(self, url, sessao, tentativas=2, limite=60):
        self.pedidos.append(url)
        if url not in self.paginas:
            raise ErroDownload(f"HTTP 404 em {url}", 404)
        return url, self.paginas[url]

    def get(self, url, timeout=None, headers=None):            # o sessao.get dos arquivos
        self.pedidos.append(url)
        assert headers and headers.get("User-Agent", "").startswith("ArteconRadar/"), "o robô se identifica"
        if url in self.zips:
            return SimpleNamespace(status_code=200, content=self.zips[url])
        return SimpleNamespace(status_code=404, content=b"")

    def _pausa(self, segundos=radar_ciga.PAUSA_PORTAL):
        assert segundos == 10.0                                 # o Crawl-Delay do robots.txt, sempre
        self.pausas += 1


@pytest.fixture()
def portal(monkeypatch):
    def montar(paginas, zips):
        p = PortalFalso(paginas, zips)
        monkeypatch.setattr(radar_ciga, "baixar", p.baixar)
        monkeypatch.setattr(radar_ciga, "_pausa", p._pausa)
        return p
    return montar


URL_MES = "https://dados.ciga.sc.gov.br/pt_BR/dataset/domsc-publicacoes-de-10-2026"
URL_ZIP = ("https://dados.ciga.sc.gov.br/dataset/abc-123/resource/r-{i}/download/"
           "cigadados_publicacoes_{dia}_{janela}.zip")


def test_le_a_pagina_do_mes_baixa_so_os_dias_da_janela_e_nunca_visita_o_diario(portal):
    """O caminho feliz: a página do mês (com /pt_BR/) lista as três janelas de cada dia; só as dos dias da janela (ontem e
    anteontem) são baixadas, com a pausa do Crawl-Delay antes de cada arquivo; os itens saem filtrados (município + categoria),
    com o texto completo vindo do próprio arquivo; e NENHUM pedido toca o diariomunicipal.sc.gov.br."""
    zips = {
        URL_ZIP.format(i=1, dia="2026_10_21", janela="0000_1159"): zip_do_portal(
            publicacao(1001),                                                      # Palhoça + Decretos: entra
            publicacao(1002, municipio="São José", categoria="Leis", titulo="LEI Nº 6.789/2026",
                       texto="<p>Institui a planta genérica de valores do ITBI.</p>",
                       entidade="Prefeitura Municipal de São José"),               # entra
            publicacao(1003, municipio="Florianópolis"),                           # outro município: fora
            publicacao(1004, categoria="Portarias")),                              # outra categoria: fora
        URL_ZIP.format(i=2, dia="2026_10_20", janela="1600_2359"): zip_do_portal(
            publicacao(1005, titulo="DECRETO Nº 3.457/2026", texto="<p>Regulamenta a dívida ativa municipal.</p>",
                       data="2026-10-20 18:40:00")),
    }
    paginas = {URL_MES: pagina_do_mes(
        "cigadados_publicacoes_2026_10_22_0000_1159.zip",                          # hoje: fora da janela (padrão: ontem e anteontem)
        "cigadados_publicacoes_2026_10_21_0000_1159.zip",
        "cigadados_publicacoes_2026_10_20_1600_2359.zip",
        "cigadados_publicacoes_2026_10_12_0000_1159.zip")}                         # velho: fora
    p = portal(paginas, zips)
    listagem, http = radar_ciga.listar_paginas(p, FONTE, HOJE)                     # type: ignore[arg-type]
    assert http == 200 and listagem.incompleta is None
    assert listagem.brutos == 5                                                    # tudo o que veio nos arquivos
    assert [i.metadados["ciga_codigo"] for i in listagem.itens] == ["1001", "1002", "1005"]   # o mais novo primeiro
    um = next(i for i in listagem.itens if i.metadados["ciga_codigo"] == "1001")
    assert um.titulo == "DECRETO Nº 3.456/2026 (Palhoça)"
    assert um.url == "https://diariomunicipal.sc.gov.br/?q=id:1001"                # o link HUMANO, nunca visitado
    assert um.data == date(2026, 10, 21)
    assert um.resumo == "Prefeitura Municipal de Palhoça · Decretos"
    assert um.texto_da_listagem == "DECRETO Nº 3.456/2026 Dispõe sobre o IPTU de 2027 e dá outras providências."
    assert um.trecho_do_tema == "Dispõe sobre o IPTU de 2027 e dá outras providências."
    assert um.metadados["url_pdf"].endswith("/1001.pdf")
    # os pedidos: a página do mês + só os dois arquivos da janela, todos no portal de dados abertos
    assert p.pedidos == [URL_MES,
                         URL_ZIP.format(i=2, dia="2026_10_20", janela="1600_2359"),
                         URL_ZIP.format(i=1, dia="2026_10_21", janela="0000_1159")]
    assert all("dados.ciga.sc.gov.br" in u for u in p.pedidos)
    assert not any("diariomunicipal" in u for u in p.pedidos)
    assert p.pausas == 2                                                           # uma pausa de 10 s antes de cada arquivo


def test_filtro_compara_sem_acento_e_sem_caixa_e_categorias_vazia_significa_todas():
    pubs = [publicacao(1, municipio="PALHOCA"), publicacao(2, municipio="são josé", categoria="LEIS"),
            publicacao(3, municipio="Biguaçu"), publicacao(4, categoria="Outras publicações"),
            publicacao(5, titulo=""), publicacao(codigo=None)]
    escolhidas = radar_ciga.filtrar(pubs, FONTE["config"])
    assert [p["codigo"] for p in escolhidas] == [1, 2]                             # sem título ou sem código nunca entram
    todas = radar_ciga.filtrar(pubs, dict(FONTE["config"], categorias=[]))
    assert [p["codigo"] for p in todas] == [1, 2, 4]                               # categorias vazia = todas as categorias


def test_arquivo_estragado_nao_derruba_a_rodada_e_json_de_lista_tambem_vale():
    bom = publicacao(7)
    dados = zip_do_portal(bom, extra={"estragado.json": "{nao-e-json", "leia-me.txt": "nada"})
    assert [p["codigo"] for p in radar_ciga.publicacoes_do_zip(dados)] == [7]
    saida = io.BytesIO()                                                           # um arquivo cujo JSON é lista pura
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("lista.json", json.dumps([publicacao(8), "texto-perdido"]))
    assert [p["codigo"] for p in radar_ciga.publicacoes_do_zip(saida.getvalue())] == [8]


def test_mes_anterior_sem_conjunto_e_tolerado_e_a_falta_do_dia_de_ontem_avisa(portal):
    """Na virada do mês, o conjunto do mês velho pode já ter saído do ar (404): a rodada segue, incompleta. E quando o arquivo de
    ontem ainda não está no portal, a listagem avisa (a próxima rodada o pega)."""
    primeiro = date(2026, 11, 2)                                                   # ontem = 01/11, anteontem = 31/10 (outro mês)
    mes_11 = "https://dados.ciga.sc.gov.br/pt_BR/dataset/domsc-publicacoes-de-11-2026"
    zip_nov = URL_ZIP.format(i=0, dia="2026_11_01", janela="0000_1159")
    p = portal({mes_11: pagina_do_mes("cigadados_publicacoes_2026_11_01_0000_1159.zip")},   # o conjunto de outubro: 404
               {zip_nov: zip_do_portal(publicacao(2001, data="2026-11-01 08:00:00"))})
    listagem, http = radar_ciga.listar_paginas(p, FONTE, primeiro)                 # type: ignore[arg-type]
    assert http == 200 and [i.metadados["ciga_codigo"] for i in listagem.itens] == ["2001"]
    assert "10/2026 ainda não está no portal" in listagem.incompleta
    # o mês atual fora do ar é falha de verdade (não é silêncio)
    p2 = portal({}, {})
    with pytest.raises(ErroDownload):
        radar_ciga.listar_paginas(p2, FONTE, HOJE)                                 # type: ignore[arg-type]
    # a página veio, mas sem o arquivo de ontem: o aviso diz que a próxima rodada pega
    p3 = portal({URL_MES: pagina_do_mes("cigadados_publicacoes_2026_10_12_0000_1159.zip")}, {})
    listagem, _ = radar_ciga.listar_paginas(p3, FONTE, HOJE)                       # type: ignore[arg-type]
    assert "21/10/2026 ainda não estão no portal" in listagem.incompleta


def test_max_zips_limita_os_pedidos_e_avisa(portal):
    nomes = [f"cigadados_publicacoes_2026_10_21_{j}.zip" for j in ("0000_1159", "1200_1559", "1600_2359")] + \
            [f"cigadados_publicacoes_2026_10_20_{j}.zip" for j in ("0000_1159", "1200_1559", "1600_2359")]
    p = portal({URL_MES: pagina_do_mes(*nomes)}, {})
    p.zips = {URL_ZIP.format(i=i, dia="2026_10_21" if i < 3 else "2026_10_20",
                             janela=("0000_1159", "1200_1559", "1600_2359")[i % 3]): zip_do_portal(publicacao(100 + i))
              for i in range(6)}
    fonte = dict(FONTE, config=dict(FONTE["config"], max_zips=2))
    listagem, _ = radar_ciga.listar_paginas(p, fonte, HOJE)                        # type: ignore[arg-type]
    assert "o portal lista 6 arquivos na janela; só os 2 primeiros entraram" in listagem.incompleta
    assert len([u for u in p.pedidos if u.endswith(".zip")]) == 2 and p.pausas == 2


def test_fonte_do_banco_e_do_json_batem_com_o_coletor():
    """A fonte do sql/radar-fontes-novas-v0.45.0.sql: o tipo_coletor é o que radar_coletar despacha, a leitura é 1 vez por dia e
    os filtros batem com os padrões do coletor (mudar lá sem mudar aqui quebra este teste)."""
    import inspect
    from pathlib import Path

    import radar_coletar
    texto = (radar_ciga.__doc__ or "")
    assert "diariomunicipal.sc.gov.br" in texto and "robots.txt" in texto          # o combinado fica escrito no código
    sql = (Path(__file__).resolve().parent.parent / "sql" / "radar-fontes-novas-v0.45.0.sql").read_text(encoding="utf-8")
    assert "'ciga_dados'" in sql and "'santa-catarina', 24)" in sql                # 1 leitura por dia (frequencia_horas: 24)
    assert '"municipios": ["Palhoça", "São José"]' in sql and '"categorias": ["Leis", "Decretos"]' in sql
    assert '"texto_do_feed": true' in sql                                          # o texto vem do arquivo: nenhuma página é aberta
    assert radar_ciga.MUNICIPIOS_PADRAO == ["Palhoça", "São José"] and radar_ciga.CATEGORIAS_PADRAO == ["Leis", "Decretos"]
    fonte_dispatch = inspect.getsource(radar_coletar.coletar_fonte)
    assert 'tipo == "ciga_dados"' in fonte_dispatch and "radar_ciga.listar_paginas" in fonte_dispatch
