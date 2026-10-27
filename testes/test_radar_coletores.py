"""Testes dos leitores de listagem e das utilidades (sem rede, sem banco)."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

import radar_coletores as coletores
from radar_coletores import listar, listar_html_links, listar_normas_rfb, listar_rss
from radar_util import canonizar_url, extrair_texto, hash_conteudo, hash_titulo, interpretar_data, sem_acentos

AMOSTRAS = Path(__file__).resolve().parent / "amostras"
FONTES = {f["slug"]: f for f in json.loads(
    (Path(__file__).resolve().parent.parent / "robo" / "radar_fontes.json").read_text(encoding="utf-8"))}
HOJE = date(2026, 10, 1)
FONTE_RSS = {"slug": "exemplo-rss", "tipo_coletor": "rss", "url": "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/RSS",
             "config": {"janela_dias": 30, "excluir_url": "(/view$|\\.(png|jpe?g|gif|pdf)(/view)?$)"}}


def amostra(nome: str) -> str:
    return (AMOSTRAS / nome).read_text(encoding="utf-8")


# ------------------------------------------------------------------------ RSS
def test_rss_govbr_ignora_imagens_pastas_e_itens_antigos():
    fonte = dict(FONTE_RSS, config=dict(FONTE_RSS["config"], janela_dias=90))
    r = listar_rss(amostra("rfb-noticias.rss"), fonte, HOJE)
    assert [i.titulo for i in r.itens] == [
        "Receita Federal disponibilizará a versão web da DITR 2026",
        "Receita Federal informa parada programada do Sistema de Leilão Eletrônico"]
    assert r.itens[0].data == date(2026, 7, 22)
    assert r.itens[0].url.endswith("/receita-federal-disponibilizara-a-versao-web-da-ditr-2026")
    assert r.itens[0].resumo == "Nova versão permite o preenchimento online da declaração, sem instalar programa."
    assert r.brutos == 4          # a imagem (/view) é descartada antes; pastas antigas caem pela data


def test_rss_tudo_fora_da_janela_e_lista_vazia_mas_nao_suspeita():
    r = listar_rss(amostra("rfb-noticias.rss"), FONTE_RSS, HOJE)   # janela padrão: 30 dias
    assert r.itens == [] and r.brutos > 0


def test_rss_2_0_e_atom_tambem_sao_lidos():
    rss2 = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
      <item><title>Nota A</title><link>https://ex.gov.br/a</link><pubDate>Wed, 30 Sep 2026 10:00:00 -0300</pubDate></item>
      </channel></rss>"""
    atom = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Nota B</title><link href="https://ex.gov.br/b"/><updated>2026-09-29T08:00:00Z</updated></entry></feed>"""
    fonte = {"url": "https://ex.gov.br/rss", "config": {}}
    a = listar_rss(rss2, fonte, HOJE).itens[0]
    b = listar_rss(atom, fonte, HOJE).itens[0]
    assert (a.titulo, a.url, a.data) == ("Nota A", "https://ex.gov.br/a", date(2026, 9, 30))
    assert (b.titulo, b.url, b.data) == ("Nota B", "https://ex.gov.br/b", date(2026, 9, 29))


def test_rss_invalido_levanta_erro_em_vez_de_devolver_vazio():
    with pytest.raises(Exception):
        listar_rss("<html><body>Erro 503</body></html><<<", FONTE_RSS, HOJE)


# ---------------------------------------------------------------- html_links
def test_pgfn_extrai_titulo_data_e_url_absoluta():
    fonte = dict(FONTES["pgfn-noticias"], config=dict(FONTES["pgfn-noticias"]["config"], janela_dias=60))
    r = listar_html_links(amostra("pgfn-noticias.html"), fonte, HOJE)
    assert r.brutos == 4
    assert [(i.titulo, i.data) for i in r.itens] == [
        ("Atraso no débito automático exige atenção de contribuintes nesta quarta (30)", date(2026, 9, 30)),
        ("Novo acesso ao Regularize para representantes de empresas", date(2026, 9, 17)),
        ("Operação Bomba Oculta visa postos de combustíveis clandestinos", date(2026, 8, 28)),
        ("Seleção Nacional de Estagiários", date(2026, 8, 19))]
    assert all(i.url.startswith("https://www.gov.br/pgfn/pt-br/assuntos/noticias/2026/") for i in r.itens)
    assert "Contribuintes com parcelamentos" in r.itens[0].resumo


def test_pgfn_nao_confunde_menu_paginacao_nem_link_dentro_de_script():
    r = listar_html_links(amostra("pgfn-noticias.html"), FONTES["pgfn-noticias"], HOJE)
    urls = [i.url for i in r.itens]
    assert len(urls) == len(set(urls)) == 2            # janela de 30 dias: 30/09 e 17/09
    assert not any("falso" in u or "b_start" in u or u.endswith("/2026") for u in urls)


def test_simples_nacional_links_relativos_com_guid():
    fonte = dict(FONTES["simples-noticias"], config=dict(FONTES["simples-noticias"]["config"], janela_dias=60))
    r = listar_html_links(amostra("simples-noticias.html"), fonte, HOJE)
    assert r.brutos == 3
    assert [(i.titulo, i.data, i.url) for i in r.itens] == [
        ("Publicado Roteiro da Opção pelo Simples Nacional Para o Ano de 2027", date(2026, 8, 21),
         "https://www8.receita.fazenda.gov.br/SimplesNacional/Noticias/NoticiaCompleta.aspx?id=bff8b291-7a89-42fa-94e7-8cacfd617f25"),
        ("CGSN atualiza regras do Simples Nacional para adequação à Reforma Tributária do Consumo", date(2026, 8, 12),
         "https://www8.receita.fazenda.gov.br/SimplesNacional/Noticias/NoticiaCompleta.aspx?id=e595d010-1e04-4c3b-95d9-185fc58594b5")]


def test_sefsc_titulo_vem_do_cartao_quando_o_link_e_generico():
    r = listar_html_links(amostra("sefsc-home.html"), FONTES["sefsc-legislacao"], HOJE)
    assert [(i.titulo, i.data) for i in r.itens] == [
        ("ATO DIAT Nº 058/2026", date(2026, 9, 25)),
        ("ATO DIAT Nº 059/2026", date(2026, 9, 25)),
        ("DECRETO Nº 1.686, DE 8 DE SETEMBRO DE 2026", date(2026, 9, 8))]
    # o link "Legislação Tributária" (índice) e o download .doc de resolução ficam de fora
    assert all("/html/" in i.url for i in r.itens)


def test_pagina_com_layout_trocado_devolve_zero_reconhecidos():
    for slug in ["rfb-noticias", "pgfn-noticias", "simples-noticias", "sefsc-legislacao", "cgibs-noticias"]:
        r = listar(amostra("layout-mudou.html"), FONTES[slug], HOJE)
        assert r.brutos == 0 and r.itens == [], slug


def test_cgibs_padrao_aceita_noticias_e_recusa_secoes():
    padrao = re.compile(FONTES["cgibs-noticias"]["config"]["padrao_url"])
    assert padrao.search("https://www.cgibs.gov.br/dere-cgibs-e-receita-federal-divulgam-endpoints-do-ambiente-de-producao")
    assert padrao.search("https://www.cgibs.gov.br/informe-instabilidade-da-conta-do-cgibs-no-instagram")
    for secao in ["noticias-menu", "legislacoes", "central-de-conteudo", "atos-tecnicos-conjuntos", "leis", ""]:
        assert not padrao.search("https://www.cgibs.gov.br/" + secao), secao


def test_limite_de_itens_por_execucao():
    html = "<html><body>" + "".join(
        f'<div><a href="/pgfn/pt-br/assuntos/noticias/2026/noticia-numero-{n}">Notícia número {n} da lista</a> 30/09/2026</div>'
        for n in range(60)) + "</body></html>"
    assert len(listar_html_links(html, FONTES["pgfn-noticias"], HOJE).itens) == 40


# ---------------------------------------------------------------- normas RFB
# v0.31.0: o sistema Normas virou uma aplicação montada no navegador; os atos vêm da pesquisa pública (JSON) que a própria página usa.
# Amostras REAIS de 17/10/2026, reduzidas (veja testes/amostras/LEIA-ME.txt).
RFB = FONTES["rfb-normas"]
DIA_NORMAS = date(2026, 10, 17)


def test_normas_rfb_le_a_pesquisa_real_filtra_orgao_e_tema_e_usa_o_nome_oficial():
    r = listar_normas_rfb(amostra("normas-pesquisar-2026-10-01a17.json"), RFB, DIA_NORMAS)
    assert r.brutos == 7                       # os 7 atos da resposta, mesmo os filtrados (é o que separa "vazio" de "mudou")
    # o título é o nome oficial (com a data do ATO); a data do item é a da publicação. Coana (aduana) e DRF/SOR (regional) saem pelo
    # órgão; a SC de classificação de mercadoria (NCM) sai pelo tema; a Portaria Conjunta de 05/10 fica fora da janela de 10 dias
    assert [(i.titulo, i.data) for i in r.itens] == [
        ("Solução de Consulta Cosit nº 196, de 08/10/2026", date(2026, 10, 14)),
        ("Solução de Consulta Disit/SRRF03 nº 3056, de 09/10/2026", date(2026, 10, 13)),
        ("Portaria MF nº 3074, de 09/10/2026", date(2026, 10, 9))]
    assert r.fora_do_tema == 1
    it = r.itens[0]
    assert it.url == "https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/154087"         # sem "/vs/...", como antes
    assert it.url_texto == "https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/154087/visao/multivigente"
    assert it.metadados == {"tipo": "Solução de Consulta", "numero": "196", "orgao": "Cosit", "id_ato": "154087", "sigla_tipo": "SC",
                            "data_ato": "2026-10-08",
                            "link_permanente": "https://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=154087"}
    assert it.resumo.startswith("Assunto: Imposto sobre a Renda de Pessoa Jurídica - IRPJ") and "<" not in it.resumo   # a ementa vem em HTML
    assert it.texto_da_listagem.startswith("Solução de Consulta Cosit nº 196, de 08/10/2026. Ementa: Assunto: Imposto sobre a Renda")
    # janela de 5 dias: só as duas Soluções de Consulta
    curta = dict(RFB, config=dict(RFB["config"], janela_dias=5))
    assert [i.titulo for i in listar_normas_rfb(amostra("normas-pesquisar-2026-10-01a17.json"), curta, DIA_NORMAS).itens] == [
        "Solução de Consulta Cosit nº 196, de 08/10/2026", "Solução de Consulta Disit/SRRF03 nº 3056, de 09/10/2026"]
    # o ato conjunto leva os dois órgãos no nome; sem filtros, o NCM e a Coana entram
    solta = dict(RFB, config={"janela_dias": 17})
    titulos = [i.titulo for i in listar_normas_rfb(amostra("normas-pesquisar-2026-10-01a17.json"), solta, DIA_NORMAS).itens]
    assert len(titulos) == 7 and "Portaria Conjunta MF / CGIBS nº 14, de 02/10/2026" in titulos and "Portaria Coana nº 214, de 15/10/2026" in titulos


def test_normas_rfb_pesquisa_vazia_e_zero_reconhecidos():
    r = listar_normas_rfb(amostra("normas-pesquisar-vazia.json"), RFB, DIA_NORMAS)
    assert r.brutos == 0 and r.itens == []              # na coleta, "vazio_suspeito" (nunca "sem novidades")


def test_normas_rfb_formato_novo_diz_o_motivo_e_por_onde_os_atos_chegam():
    """A casca da aplicação (HTML) no lugar do JSON, ou um JSON sem a lista "atos": a fonte diz o que houve, não "nenhum item"."""
    casca = ('<!doctype html><html lang="pt-br"><head><title>Normas</title><base href="/"></head><body><app-root></app-root>'
             '<script src="main-L3RVA65H.js" type="module"></script></body></html>')
    with pytest.raises(coletores.SistemaNormasMudou, match="mudou de formato .veio uma página do site.*continuam chegando pelo DOU .dou-inlabs."):
        listar_normas_rfb(casca, RFB, DIA_NORMAS)
    with pytest.raises(coletores.SistemaNormasMudou, match="não traz a lista de atos"):
        listar_normas_rfb('{"resultado": [], "total": 0}', RFB, DIA_NORMAS)
    with pytest.raises(coletores.SistemaNormasMudou, match="não é JSON"):
        listar_normas_rfb("Erro interno", RFB, DIA_NORMAS)
    with pytest.raises(ValueError):                                                    # pelo listar() também (a coleta registra a falha)
        listar(casca, RFB, DIA_NORMAS)


def test_texto_do_ato_normas_monta_epigrafe_ementa_e_artigos_sem_o_riscado():
    texto = coletores.texto_do_ato_normas(amostra("normas-ato-154126.json"))
    assert texto.startswith("Portaria Coana nº 214, de 15 de outubro de 2026 Altera a Portaria Coana nº 188, de 22 de abril de 2026")
    assert "Art. 2º Esta Portaria entre em vigor" in texto and "<" not in texto and len(texto) > 1000
    sc = coletores.texto_do_ato_normas(amostra("normas-ato-154087.json"))          # Solução de Consulta: a ementa completa basta
    assert sc.startswith("Solução de Consulta Cosit nº 196, de 8 de outubro de 2026 Assunto: Imposto sobre a Renda de Pessoa Jurídica")
    assert 3000 < len(sc) < 4000 and "<span" not in sc and "Anexo" not in sc         # o PDF anexo não entra, e nada é inventado
    # o texto revogado (riscado) e o omitido ficam de fora; a ordem é a do ato, não a da lista
    ato = {"epigrafeCompleta": "Instrução Normativa RFB nº 9, de 1º de outubro de 2026",
           "ementas": [{"ordemSegmentoAto": 0, "textoIntegra": "<p>Dispõe sobre a <b>CBS</b>.</p>"}],
           "outrosSegmentos": [{"ordemSegmentoAto": 3, "textoIntegra": "Art. 2º Vigência."},
                               {"ordemSegmentoAto": 1, "textoIntegra": "Art. 1º Fica revogado.", "tachado": True},
                               {"ordemSegmentoAto": 2, "textoIntegra": "Art. 1º Nova redação."},
                               {"ordemSegmentoAto": 4, "textoIntegra": "nota interna", "omitir": True},
                               {"ordemSegmentoAto": 5, "textoIntegra": "", "arquivoBinario": {"idArquivoBinario": 1}}]}
    assert coletores.texto_do_ato_normas(ato) == ("Instrução Normativa RFB nº 9, de 1º de outubro de 2026 Dispõe sobre a CBS . "
                                                  "Art. 1º Nova redação. Art. 2º Vigência.")
    for ruim in ("<html>erro</html>", "[]", '{"ementas": "x"}'):
        with pytest.raises(ValueError):
            coletores.texto_do_ato_normas(ruim)


def test_corpo_da_pesquisa_normas_igual_ao_da_pagina_com_datas_em_dd_mm_aaaa():
    corpo = coletores.corpo_pesquisa_normas(RFB, DIA_NORMAS, 1)
    esperado = {"tipoData": "dataPublicacao", "tiposAtosSelecionados": "", "orgaosSelecionados": "", "numeroAto": "",
                "dataInicio": "07/10/2026", "dataFim": "17/10/2026", "publicado": True, "internet": True, "apenasAtosVigentes": False,
                "apenasAtosInternos": False, "termo": "", "refino": {}, "paginacaoPaginaAtual": 1, "paginacaoQuantidadePorPagina": 100,
                "tipoPesquisa": "formulario", "ordenacaoColuna": "publicacao", "ordenacaoDirecao": "desc", "skipAggregations": True}
    assert corpo == esperado and list(corpo) == list(esperado)        # o mesmo pedido da tela (no formato ISO a API responde 500)
    filtrada = dict(RFB, config=dict(RFB["config"], tipos_ids=[42, 79], orgaos_siglas="Cosit;Sutri;MF", itens_por_pagina=5000))
    corpo = coletores.corpo_pesquisa_normas(filtrada, DIA_NORMAS, 3)
    assert (corpo["tiposAtosSelecionados"], corpo["orgaosSelecionados"], corpo["paginacaoPaginaAtual"],
            corpo["paginacaoQuantidadePorPagina"]) == ("42;79", "Cosit;Sutri;MF", 3, 300)


def _ato_normas(n, sigla="RFB", publicacao="16/10/2026", ementa="Ementa do ato."):
    return {"idAto": n, "tipoAto": {"nomeTipoAto": "Portaria", "siglaTipoAto": "Port.", "idTipoAto": 57}, "numeroAto": str(n),
            "dataAto": publicacao, "dataPublicacao": publicacao, "orgaos": [{"siglaOrgao": sigla, "idOrgao": 1}], "ementa": ementa,
            "urlVisualizacao": f"https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{n}"}


def test_normas_pela_api_pagina_por_pagina_e_pagina_com_erro_nao_perde_as_anteriores(monkeypatch):
    import radar_normas
    from radar_util import ErroDownload
    paginas = {1: [_ato_normas(1000 + i, "DRF/SOR") for i in range(100)],          # a 1ª página inteira é de unidade regional
               2: [_ato_normas(2000 + i) for i in range(100)], 3: [_ato_normas(3000 + i) for i in range(30)]}
    pedidos = []

    def postar(url, corpo, sessao=None, **_):
        pedidos.append((url, corpo["paginacaoPaginaAtual"], corpo["dataInicio"], corpo["dataFim"]))
        n = corpo["paginacaoPaginaAtual"]
        if n in falhar:
            raise ErroDownload(f"HTTP 500 em {url} (Indexação: Falha ao pesquisar os atos)", 500)
        return 200, json.dumps({"atos": paginas.get(n, []), "refinos": [], "quantidadeTotal": 230, "quantidadePaginas": 3})

    monkeypatch.setattr(radar_normas, "postar_json", postar)
    falhar = set()
    fonte = dict(RFB, config=dict(RFB["config"], max_itens=500))
    r, http = radar_normas.listar_paginas(None, fonte, DIA_NORMAS, pausa=0)
    assert [p[1] for p in pedidos] == [1, 2, 3] and {p[0] for p in pedidos} == {RFB["url"]}
    assert pedidos[0][2:] == ("07/10/2026", "17/10/2026")
    assert (r.brutos, len(r.itens), http, r.incompleta) == (230, 130, 200, None)
    pedidos.clear()
    r, _ = radar_normas.listar_paginas(None, dict(fonte, config=dict(fonte["config"], paginas_max=2)), DIA_NORMAS, pausa=0)
    assert [p[1] for p in pedidos] == [1, 2] and len(r.itens) == 100                 # o limite de páginas da fonte
    falhar = {2}
    r, _ = radar_normas.listar_paginas(None, fonte, DIA_NORMAS, pausa=0)
    assert r.brutos == 100 and r.itens == [] and "a página 2 da pesquisa não pôde ser lida" in r.incompleta
    falhar = {1}
    with pytest.raises(ErroDownload, match="HTTP 500"):                              # a 1ª página: falha de verdade
        radar_normas.listar_paginas(None, fonte, DIA_NORMAS, pausa=0)


def test_normas_recusa_do_site_e_cadastro_antigo_dizem_o_que_fazer(monkeypatch):
    import radar_normas
    from radar_util import ErroDownload

    def recusa(url, corpo, sessao=None, **_):
        raise ErroDownload(f"HTTP 403 em {url}", 403)
    monkeypatch.setattr(radar_normas, "postar_json", recusa)
    with pytest.raises(ErroDownload, match="o site da Receita recusou o pedido do robô .HTTP 403.*dou-inlabs") as e:
        radar_normas.listar_paginas(None, RFB, DIA_NORMAS, pausa=0)
    assert e.value.http_status == 403
    antiga = dict(RFB, url="http://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action?dt_inicio={inicio}&dt_fim={fim}&p={p}")
    with pytest.raises(ValueError, match="consulta antiga.*sql/radar-fontes-novas-v0.31.0.sql"):
        radar_normas.listar_paginas(None, antiga, DIA_NORMAS, pausa=0)


def test_postar_json_tenta_de_novo_no_erro_do_servidor_e_para_na_recusa(monkeypatch):
    import radar_util

    class Resp:
        def __init__(self, status, corpo):
            self.status_code, self.text, self.headers, self.encoding = status, corpo, {"content-type": "application/json"}, None
        def json(self):
            return json.loads(self.text)

    class Sessao:
        def __init__(self, respostas):
            self.respostas, self.pedidos = list(respostas), []
        def post(self, url, data, timeout, headers):
            self.pedidos.append((json.loads(data.decode("utf-8")), headers))
            return self.respostas.pop(0)

    monkeypatch.setattr(radar_util.time, "sleep", lambda s: None)
    s = Sessao([Resp(502, ""), Resp(200, '{"atos": []}')])
    assert radar_util.postar_json("https://x/api", {"termo": "ação"}, s) == (200, '{"atos": []}')
    corpo, cab = s.pedidos[0]
    assert corpo == {"termo": "ação"} and cab["Content-Type"] == "application/json; charset=UTF-8" and cab["User-Agent"].startswith("ArteconRadar/")
    s = Sessao([Resp(500, '{"message": "Indexação: Falha ao pesquisar os atos"}')] * 3)
    with pytest.raises(radar_util.ErroDownload, match=r"HTTP 500 em https://x/api \(Indexação: Falha ao pesquisar os atos\)"):
        radar_util.postar_json("https://x/api", {}, s)
    assert len(s.pedidos) == 3
    s = Sessao([Resp(403, "")])
    with pytest.raises(radar_util.ErroDownload, match="HTTP 403"):
        radar_util.postar_json("https://x/api", {}, s)
    assert len(s.pedidos) == 1                                                       # recusa: não insiste


def test_tipo_de_coletor_desconhecido_e_erro():
    with pytest.raises(ValueError):
        listar("x", {"tipo_coletor": "inexistente", "url": "u"})


# ----------------------------------------------------------------- utilidades
@pytest.mark.parametrize("texto, esperado", [
    ("30/09/2026", date(2026, 9, 30)),
    ("publicado em 1/10/2026 às 9h", date(2026, 10, 1)),
    ("2026-07-22T16:51:56Z", date(2026, 7, 22)),
    ("DECRETO Nº 1.686, DE 8 DE SETEMBRO DE 2026", date(2026, 9, 8)),
    ("1º de março de 2026", date(2026, 3, 1)),
    ("Wed, 30 Sep 2026 10:00:00 -0300", date(2026, 9, 30)),
    ("30.09.2026", date(2026, 9, 30)),
    ("1º/10/2026", date(2026, 10, 1)),
    ("30 set 2026", date(2026, 9, 30)),
    ("30 de set. de 2026", date(2026, 9, 30)),
    ("2026-10-01T02:30:00Z", date(2026, 9, 30)),          # 02:30 UTC ainda é dia 30 em Brasília
    ("2026-10-01T02:30:00-03:00", date(2026, 10, 1)),
    ("Lei 9999-12-31", None),
    ("31/02/2026", None),
    ("sem data", None),
    ("", None),
    (None, None),
])
def test_interpretar_data(texto, esperado):
    assert interpretar_data(texto) == esperado


def test_extrair_texto_pega_o_miolo_e_descarta_menu_rodape_e_script():
    texto = extrair_texto(amostra("pgfn-item.html"), FONTES["pgfn-noticias"]["config"]["seletor_texto"])
    assert texto.startswith("A Procuradoria-Geral da Fazenda Nacional informa")
    assert "emitir o DARF pelo portal Regularize e efetuar o pagamento" in texto    # &nbsp; vira espaço comum
    assert "Menu principal" not in texto and "Creative Commons" not in texto and "track()" not in texto


def test_extrair_texto_sem_seletor_valido_usa_o_corpo_da_pagina():
    texto = extrair_texto(amostra("pgfn-item.html"), "#nao-existe, .tambem-nao")
    assert "Procuradoria-Geral da Fazenda Nacional informa" in texto and "track()" not in texto


def test_extrair_texto_de_pagina_aspnet_dentro_de_form():
    html = "<html><body><form id='f'><div id='conteudo'>" + "Texto da notícia do Simples Nacional. " * 10 + "</div></form></body></html>"
    assert extrair_texto(html, "#conteudo, form, body").startswith("Texto da notícia do Simples Nacional.")


def test_hash_de_conteudo_ignora_formatacao_mas_nao_ignora_mudanca_real():
    a = hash_conteudo("Art. 1º  A alíquota é de 0,9%.\n\nArt. 2º Vigência.")
    assert a == hash_conteudo("Art. 1º A alíquota é de 0,9%. Art. 2º\xa0Vigência.")
    assert a != hash_conteudo("Art. 1º A alíquota é de 1,0%. Art. 2º Vigência.")


def test_hash_de_titulo_tolera_caixa_acento_e_pontuacao():
    assert hash_titulo("CGSN atualiza regras do Simples Nacional!") == hash_titulo("cgsn atualiza regras do simples nacional")
    assert hash_titulo("Prorrogação do prazo") == hash_titulo("PRORROGACAO DO PRAZO.")
    assert hash_titulo("Prorrogação do prazo") != hash_titulo("Prorrogação do prazo da DCTF")


# ------------------------------------------------ casos levantados na revisão independente
PGFN = FONTES["pgfn-noticias"]


def itens_de(html: str, fonte=PGFN, hoje=HOJE):
    return listar_html_links("<html><body>" + html + "</body></html>", fonte, hoje)


def test_titulo_que_comeca_com_mais_veja_saiba_nao_e_descartado():
    r = itens_de("""<ul>
      <li><a href="/pgfn/pt-br/assuntos/noticias/2026/mais-de-2-milhoes">Mais de 2 milhões de contribuintes regularizam débitos</a> <span>30/09/2026</span></li>
      <li><a href="/pgfn/pt-br/assuntos/noticias/2026/veja-como-regularizar">Veja como regularizar débitos inscritos em dívida ativa</a> <span>29/09/2026</span></li>
      <li><a href="/pgfn/pt-br/assuntos/noticias/2026/edital-novo">Novo edital de transação</a> <span>28/09/2026</span></li></ul>""")
    assert [i.titulo for i in r.itens] == ["Mais de 2 milhões de contribuintes regularizam débitos",
                                           "Veja como regularizar débitos inscritos em dívida ativa", "Novo edital de transação"]


def test_titulo_curto_e_mantido():
    r = itens_de("""<li><a href="/pgfn/pt-br/assuntos/noticias/2026/in-2201">IN 2.201</a> <span>30/09/2026</span></li>
                    <li><a href="/pgfn/pt-br/assuntos/noticias/2026/lei-15270">Lei 15.270</a> <span>29/09/2026</span></li>""")
    assert [i.titulo for i in r.itens] == ["IN 2.201", "Lei 15.270"] and r.brutos == 2


def test_link_generico_sem_contexto_aproveitavel_conta_como_reconhecido():
    r = itens_de("""<div><div><a href="/pgfn/pt-br/assuntos/noticias/2026/aaa">Leia mais</a></div>
                    <div><a href="/pgfn/pt-br/assuntos/noticias/2026/bbb">Leia mais</a></div></div>""")
    assert r.brutos == 2 and [i.titulo for i in r.itens] == ["Leia mais", "Leia mais"]


def test_data_dentro_do_titulo_nao_e_a_data_de_publicacao():
    r = itens_de("""<li><a href="/pgfn/pt-br/assuntos/noticias/2026/prazo">Prazo de 31/01/2026 para opção é mantido</a> <span>30/09/2026</span></li>
                    <li><a href="/pgfn/pt-br/assuntos/noticias/2026/vigencia">Nova regra vale a partir de 1º de janeiro de 2027</a>
                        <time datetime="2026-09-29T10:00:00-03:00">ontem</time></li>
                    <li><a href="/pgfn/pt-br/assuntos/noticias/2026/sem-data">Regra vale a partir de 15/03/2027 para todos</a></li>""")
    assert [(i.titulo[:10], i.data) for i in r.itens] == [
        ("Prazo de 3", date(2026, 9, 30)), ("Nova regra", date(2026, 9, 29)), ("Regra vale", None)]


def test_data_futura_nao_vira_data_de_publicacao():
    r = itens_de("""<li><a href="/pgfn/pt-br/assuntos/noticias/2026/evento">Seminário sobre a Reforma</a> <span>30/09/2062</span></li>""")
    assert r.itens[0].data is None


def test_pagina_com_um_unico_link_nao_usa_a_pagina_inteira_como_cartao():
    miolo = "<p>" + "Texto institucional do portal sem relação com a notícia. " * 20 + "</p>"
    r = itens_de(f"""<div id="pagina"><p>Atualizado em 02/03/2019</p>{miolo}
                     <ul><li><a href="/pgfn/pt-br/assuntos/noticias/2026/unica">Única notícia da página inicial</a></li></ul></div>""")
    assert len(r.itens) == 1 and r.itens[0].data is None and r.itens[0].titulo == "Única notícia da página inicial"


def test_cabecalho_de_secao_nao_vira_titulo_do_item():
    r = itens_de("""<section><strong>Notícias</strong>
      <ul><li><a href="/pgfn/pt-br/assuntos/noticias/2026/aaa-bbb">Novo edital de transação publicado</a></li></ul></section>""")
    assert r.itens[0].titulo == "Novo edital de transação publicado"


def test_mesma_noticia_com_barra_final_ou_rastreio_e_um_item_so():
    r = itens_de("""<li><a href="/pgfn/pt-br/assuntos/noticias/2026/edital">Novo edital de transação</a> 30/09/2026</li>
                    <li><a href="/pgfn/pt-br/assuntos/noticias/2026/edital/">Novo edital</a></li>
                    <li><a href="/pgfn/pt-br/assuntos/noticias/2026/edital?utm_source=x&utm_medium=y#topo">edital</a></li>""")
    assert len(r.itens) == 1 and r.itens[0].url == "https://www.gov.br/pgfn/pt-br/assuntos/noticias/2026/edital"


@pytest.mark.parametrize("entrada, saida", [
    ("https://ex.gov.br/n/1/", "https://ex.gov.br/n/1"),
    ("https://ex.gov.br/n/1?utm_source=a&id=7&fbclid=z", "https://ex.gov.br/n/1?id=7"),
    ("https://ex.gov.br/n/1#secao", "https://ex.gov.br/n/1"),
    ("https://ex.gov.br/", "https://ex.gov.br/"),
    ("https://ex.gov.br/N.aspx?id=bff8b291-7a89", "https://ex.gov.br/N.aspx?id=bff8b291-7a89"),
    ("https://ex.gov.br/busca?p=%E1gua&flag&utm_campaign=x", "https://ex.gov.br/busca?p=%E1gua&flag"),
])
def test_canonizar_url(entrada, saida):
    assert canonizar_url(entrada) == saida


def test_rss_com_declaracao_iso_8859_1_nao_vira_texto_quebrado():
    bruto = """<?xml version="1.0" encoding="ISO-8859-1"?><rss version="2.0"><channel>
      <item><title>Instrução Normativa altera prazo de adesão</title><link>https://ex.gov.br/a</link>
      <pubDate>Wed, 30 Sep 2026 10:00:00 -0300</pubDate></item></channel></rss>"""
    # é o que o download entrega: bytes ISO-8859-1 já decodificados para texto
    texto = bruto.encode("iso-8859-1").decode("iso-8859-1")
    assert listar_rss(texto, {"url": "u", "config": {}}, HOJE).itens[0].titulo == "Instrução Normativa altera prazo de adesão"
    assert listar_rss("\ufeff" + texto, {"url": "u", "config": {}}, HOJE).itens[0].titulo == "Instrução Normativa altera prazo de adesão"


def test_atom_usa_o_link_alternate_e_nao_o_self():
    atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Nota técnica</title>
      <link rel="self" href="https://ex.gov.br/feed/1.xml"/><link rel="alternate" href="https://ex.gov.br/nota-1"/>
      <updated>2026-09-29T08:00:00Z</updated></entry></feed>"""
    assert listar_rss(atom, {"url": "u", "config": {}}, HOJE).itens[0].url == "https://ex.gov.br/nota-1"


# ------------------------------------------------------------------ diagnóstico
def test_diagnostico_classifica_cada_situacao(tmp_path, monkeypatch):
    import radar_diagnostico
    from radar_util import ErroDownload

    paginas = {
        PGFN["url"]: amostra("pgfn-noticias.html"),
        "https://www.gov.br/pgfn/pt-br/assuntos/noticias/2026/atraso-no-debito-automatico-exige-atencao-de-contribuintes-nesta-quarta-30": amostra("pgfn-item.html"),
        FONTES["simples-noticias"]["url"]: amostra("layout-mudou.html"),
    }

    def baixar_falso(url, sessao=None, tentativas=3, **_):
        if url not in paginas:
            raise ErroDownload(f"HTTP 403 em {url}", 403)
        return 200, paginas[url]

    monkeypatch.setattr(radar_diagnostico, "baixar", baixar_falso)
    from radar_coletores import listar_paginas
    monkeypatch.setattr(radar_diagnostico, "listar_paginas", lambda b, f: listar_paginas(b, f, HOJE))
    ok = radar_diagnostico.diagnosticar(PGFN, tmp_path, None)
    assert ok["veredito"] == "OK" and ok["brutos"] == 4 and ok["texto_primeiro_item"] > 200
    assert (tmp_path / "pgfn-noticias-lista.txt").exists() and (tmp_path / "pgfn-noticias-item.txt").exists()
    mudou = radar_diagnostico.diagnosticar(FONTES["simples-noticias"], tmp_path, None)
    assert mudou["veredito"].startswith("REVISAR") and mudou["brutos"] == 0
    # v0.31.0: o sistema Normas pela pesquisa nova (POST); a recusa do site (HTTP 403) é falha com o motivo
    import radar_normas
    from radar_util import ErroDownload as Erro
    monkeypatch.setattr(radar_normas, "hoje_brasilia", lambda: DIA_NORMAS)
    monkeypatch.setattr(radar_normas, "postar_json", lambda url, corpo, sessao=None, **_: (_ for _ in ()).throw(Erro(f"HTTP 403 em {url}", 403)))
    bloqueada = radar_diagnostico.diagnosticar(FONTES["rfb-normas"], tmp_path, None)
    assert bloqueada["veredito"] == "FALHA" and bloqueada["http"] == 403 and "recusou o pedido do robô" in bloqueada["erro"]
    # a resposta da pesquisa e o texto do 1º ato (JSON) ficam guardados; o texto é medido como a coleta o monta
    monkeypatch.setattr(radar_normas, "postar_json", lambda url, corpo, sessao=None, **_: (200, amostra("normas-pesquisar-2026-10-01a17.json")))
    # revisão: a pesquisa respondeu e só o texto do 1º ato foi recusado (HTTP 403): o relatório mostra o HTTP da pesquisa (200), não o
    # do texto, e o veredito diz o caso que tem saída ("sem_pagina_de_texto"), diferente da recusa da pesquisa (FALHA, HTTP 403)
    so_texto = radar_diagnostico.diagnosticar(FONTES["rfb-normas"], tmp_path, None)
    assert (so_texto["http"], so_texto["brutos"], so_texto["na_janela"], so_texto["texto_primeiro_item"]) == (200, 7, 3, 0)
    assert so_texto["veredito"].startswith("REVISAR — lista ok, texto do 1º item recusado (HTTP 403)")
    assert '"sem_pagina_de_texto": true' in so_texto["veredito"] and so_texto["erro"].startswith("HTTP 403 em https://normasinternet2.")
    assert "| rfb-normas | 200 | 7 | 3 | 1 | 0 | REVISAR — lista ok, texto do 1º item recusado" in radar_diagnostico.relatorio_md([so_texto])
    paginas["https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/154087/visao/multivigente"] = amostra("normas-ato-154087.json")
    normas = radar_diagnostico.diagnosticar(FONTES["rfb-normas"], tmp_path, None)
    assert (normas["veredito"], normas["http"], normas["brutos"], normas["na_janela"], normas["fora_do_tema"]) == ("OK", 200, 7, 3, 1)
    assert normas["inicio_texto"].startswith("Solução de Consulta Cosit nº 196, de 8 de outubro de 2026 Assunto:") and normas["texto_primeiro_item"] > 3000
    assert (tmp_path / "rfb-normas-lista.txt").read_text(encoding="utf-8").startswith("{") and (tmp_path / "rfb-normas-item.txt").exists()
    texto = radar_diagnostico.relatorio_md([ok, mudou, bloqueada, normas])
    assert "| pgfn-noticias | 200 | 4 |" in texto and "HTTP 403" in texto and "| rfb-normas | 200 | 7 | 3 | 1 |" in texto
    # página não reconhecida: o relatório mostra a estrutura, para ajustar a fonte só pelo log
    assert mudou["estrutura"]["titulo"] == "Portal em manutenção" and mudou["estrutura"]["links"] == 1
    assert "Página não reconhecida — título: _Portal em manutenção_" in texto and "/novo-portal" in texto
    assert "estrutura" not in ok


def test_diagnostico_de_pagina_montada_por_javascript_lista_os_enderecos_dos_scripts():
    import radar_diagnostico
    html = '<html><head><title>Normas</title><base href="/"></head><body><app-root></app-root>' \
           '<script src="main-X.js"></script></body></html>'
    js = 'class S{constructor(){this.apiBaseUrl=globalThis.location.origin+"/api"}' \
         'pesquisar(i){let r=`${this.apiBaseUrl}/indexacao/ato/pesquisar`;return this.http.post(r,i)}}' \
         'const x="http://schemas.openxmlformats.org/x";'
    pedidos = []

    class Resposta:
        def __init__(self, url, text):
            self.url, self.text = url, text

    class Sessao:
        def get(self, url, **_):
            pedidos.append(url)
            return Resposta(url, js if url.endswith(".js") else html)

    e = radar_diagnostico.estrutura_da_pagina(html)
    assert e["scripts_src"] == ["main-X.js"] and e["links"] == 0 and e["tabelas"] == 0
    achados = radar_diagnostico.enderecos_nos_scripts("https://ex.gov.br/consulta/pagina.action?p=1", e["scripts_src"], Sessao())
    assert "https://ex.gov.br/main-X.js" in achados          # <base href="/">: o script é procurado na raiz
    lista = achados["https://ex.gov.br/main-X.js"]
    enderecos = [x for x in lista if not x.startswith("…")]          # endereços soltos; os trechos de código vêm com "…"
    assert "/api" in enderecos and not any("schemas.openxmlformats" in x for x in enderecos)
    assert any(x.startswith("…") and "/indexacao/ato/pesquisar" in x for x in lista)


def test_enderecos_que_nao_sao_http_sao_descartados():
    fonte = {"url": "https://ex.gov.br/lista", "config": {"padrao_url": "noticia"}}
    r = listar_html_links("""<html><body><ul>
        <li><a href="javascript:alert('noticia')">Notícia com endereço malicioso</a> 30/09/2026</li>
        <li><a href="data:text/html,noticia">Notícia em data URI</a> 30/09/2026</li>
        <li><a href="/noticia/1">Notícia verdadeira número um</a> 30/09/2026</li></ul></body></html>""", fonte, HOJE)
    assert [i.url for i in r.itens] == ["https://ex.gov.br/noticia/1"]
    rss = """<rss><channel><item><title>Falsa</title><link>javascript:alert(1)</link></item>
             <item><title>Boa</title><link>https://ex.gov.br/a</link></item></channel></rss>"""
    assert [i.url for i in listar_rss(rss, {"url": "u", "config": {}}, HOJE).itens] == ["https://ex.gov.br/a"]


# ============================================= endereços e datas REAIS lidos em 02/10/2026
REAIS = json.loads((AMOSTRAS / "links-reais-2026-10-02.json").read_text(encoding="utf-8"))
DIA = date(2026, 10, 2)


def pagina_de(slug):
    """Monta uma página neutra (lista simples) com os links reais — notícias e também menus,
    paginação e compartilhamento —, para provar que o padrão da fonte separa uns dos outros."""
    d = REAIS[slug]
    itens = "".join(f'<li><a href="{u.replace("&", "&amp;")}">{t}</a>' + (f" <span>{q}</span>" if q else "") + "</li>" for t, u, q in d["noticias"])
    resto = "".join(f'<a href="{u.replace("&", "&amp;")}">{t}</a> ' for t, u in d["outros"])
    return f"<html><body><nav>{resto}</nav><ul>{itens}</ul><footer>{resto}</footer></body></html>"


@pytest.mark.parametrize("slug", ["rfb-noticias", "pgfn-noticias", "simples-noticias", "sefsc-legislacao", "cgibs-noticias"])
def test_padrao_de_cada_fonte_pega_as_noticias_reais_e_so_elas(slug):
    fonte = dict(FONTES[slug], config=dict(FONTES[slug]["config"], janela_dias=5000, max_itens=500))
    r = listar_html_links(pagina_de(slug), fonte, DIA)
    esperados = {u for _, u, _ in REAIS[slug]["noticias"]}
    assert {i.url for i in r.itens} == esperados
    assert r.brutos == len(esperados)
    por_url = {i.url: i for i in r.itens}
    for titulo, url, quando in REAIS[slug]["noticias"]:
        assert por_url[url].titulo == titulo.rstrip(".")[:300] or por_url[url].titulo == titulo
        if quando:
            assert por_url[url].data == interpretar_data(quando), titulo


def test_janela_de_30_dias_sobre_as_noticias_reais():
    r = listar_html_links(pagina_de("pgfn-noticias"), FONTES["pgfn-noticias"], DIA)
    assert [i.data for i in r.itens] == [date(2026, 9, 30), date(2026, 9, 17)]
    r = listar_html_links(pagina_de("rfb-noticias"), FONTES["rfb-noticias"], DIA)
    assert len(r.itens) == 10 and r.itens[0].data == date(2026, 10, 1)        # "01/10/2026 07h29"
    r = listar_html_links(pagina_de("cgibs-noticias"), FONTES["cgibs-noticias"], DIA)
    assert len(r.itens) == 4 and all(i.data is None for i in r.itens)         # a página inicial do CGIBS não traz datas


def test_normas_reais_de_02_10_filtro_por_orgao_e_texto_da_ementa():
    """Os atos reais lidos em 02/10/2026 (testes/amostras/links-reais-2026-10-02.json), na resposta da pesquisa nova (JSON)."""
    atos = [{"idAto": int(i), "tipoAto": {"nomeTipoAto": t}, "numeroAto": n, "dataPublicacao": d, "orgaos": [{"siglaOrgao": o}],
             "ementa": e, "urlVisualizacao": f"https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{i}"}
            for t, n, o, d, e, i in REAIS["rfb-normas"]["linhas"]]
    r = listar_normas_rfb({"atos": atos, "quantidadePaginas": 1}, RFB, DIA)
    assert r.brutos == 7
    # regionais (SRRF01, Decex/RJO, ALF/STS, DRF/SOR) e Coana fora; a Solução de Consulta da Disit entra (a dou-inlabs não a traz)
    assert [i.titulo for i in r.itens] == ["Ato Declaratório Executivo Sutri nº 11, de 02/10/2026",
                                           "Solução de Consulta Disit/SRRF04 nº 4041, de 02/10/2026"]
    assert r.itens[0].texto_da_listagem.endswith("Ementa: Altera o Ato Declaratório Executivo Sutri nº 8.")
    assert r.itens[1].texto_da_listagem is None and r.itens[1].resumo is None       # sem ementa na lista: o texto vem do ato


def _pagina_de_links(inicio, n, quando="01/10/2026"):
    return "<ul>" + "".join(f'<li><a href="/pgfn/pt-br/assuntos/noticias/2026/noticia-{k}">Notícia número {k} da lista</a> {quando}</li>'
                            for k in range(inicio, inicio + n)) + "</ul>"


def test_enderecos_da_listagem_com_janela_de_datas_e_paginas():
    from radar_coletores import enderecos_da_listagem, listar_paginas
    paginada = dict(PGFN, url="https://www.gov.br/pgfn/busca?de={inicio}&ate={fim}&b={p}",
                    config=dict(PGFN["config"], janela_dias=10, paginas_max=6, itens_por_pagina=100, max_itens=500))
    urls = enderecos_da_listagem(paginada, DIA)
    assert len(urls) == 6
    assert urls[0] == "https://www.gov.br/pgfn/busca?de=22/09/2026&ate=02/10/2026&b=1" and urls[5].endswith("&b=6")
    assert enderecos_da_listagem(FONTES["pgfn-noticias"], DIA) == ["https://www.gov.br/pgfn/pt-br/assuntos/noticias"]
    paginas = {1: _pagina_de_links(1000, 100, "05/01/2026"), 2: _pagina_de_links(2000, 100), 3: _pagina_de_links(3000, 30)}
    pedidos = []

    def baixar_falso(url):
        pedidos.append(url)
        return 200, paginas[int(url.rsplit("=", 1)[1])]

    r, http = listar_paginas(baixar_falso, paginada, DIA)
    assert len(pedidos) == 3                      # parou na página incompleta
    assert (r.brutos, len(r.itens), http) == (230, 130, 200)      # a 1ª página inteira era de notícias antigas


def test_paginacao_limite_vale_para_o_conjunto_e_pagina_com_erro_nao_perde_as_anteriores():
    from radar_coletores import listar_paginas
    paginas = {n: _pagina_de_links(n * 1000, 100) for n in (1, 2, 3)}
    fonte = dict(PGFN, url="https://www.gov.br/pgfn/busca?b={p}", config=dict(PGFN["config"], paginas_max=6, itens_por_pagina=100, max_itens=250))
    r, _ = listar_paginas(lambda url: (200, paginas.get(int(url.rsplit("=", 1)[1]), "<ul></ul>")), fonte, DIA)
    ids = sorted(int(i.url.rsplit("-", 1)[1]) // 1000 for i in r.itens)
    assert len(r.itens) == 250 and set(ids) == {1, 2, 3} and r.incompleta is None      # itens das 3 páginas, não só da 1ª

    def com_falha(url):
        if url.endswith("b=2"):
            raise RuntimeError("HTTP 500")
        return 200, paginas[1]
    r, _ = listar_paginas(com_falha, fonte, DIA)
    assert len(r.itens) == 100 and "página 2" in r.incompleta
    with pytest.raises(RuntimeError):
        listar_paginas(lambda url: (_ for _ in ()).throw(RuntimeError("fora do ar")), fonte, DIA)   # 1ª página: falha de verdade


@pytest.mark.parametrize("texto, esperado", [
    ("As regras valem a partir de 01/01/2027. Publicado em 30/09/2026 às 10h.", (date(2026, 9, 30), True)),
    ("Publicado em: 28/09/2026 às 17h20min. Prazo até 31/10/2026.", (date(2026, 9, 28), True)),
    ("Comunicado de 28/09/2026 sobre o prazo de 15/12/2026.", (date(2026, 9, 28), True)),
    ("Valem a partir de 01/01/2027 e 15/03/2027.", (None, True)),
    ("Publicado em 05/03/2024. Notícia antiga.", (date(2024, 3, 5), False)),
    ("Texto sem data nenhuma.", (None, True)),
])
def test_data_lida_do_texto_prefere_a_de_publicacao_e_recusa_futura(texto, esperado):
    from radar_coletores import data_no_texto
    assert data_no_texto(texto, {"janela_dias": 30}, DIA) == esperado


def test_diagnostico_testa_enderecos_avulsos_antes_de_cadastrar(monkeypatch):
    import radar_diagnostico
    fontes = radar_diagnostico.fontes_avulsas("https://ex.com.br/noticias, https://ex.com.br/rss/ javascript:x  nada", "/noticias/\\d+")
    assert [(f["slug"], f["url"], f["tipo_coletor"]) for f in fontes] == [
        ("teste-1", "https://ex.com.br/noticias", "html_links"), ("teste-2", "https://ex.com.br/rss/", "rss")]
    assert fontes[0]["config"]["padrao_url"] == "/noticias/\\d+" and fontes[0]["avulsa"]
    assert radar_diagnostico.fontes_avulsas("https://a.b/x")[0]["config"]["padrao_url"] == "."      # sem padrão: todos os links
    monkeypatch.setenv("ENDERECOS", "https://ex.com.br/")
    assert radar_diagnostico.carregar_fontes()[1] == "endereços informados para teste"
    # v0.31.0: um endereço do sistema Normas vira a fonte de atos da Receita (a pesquisa nova, com as opções da rfb-normas)
    normas = radar_diagnostico.fontes_avulsas("https://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action")[0]
    assert (normas["tipo_coletor"], normas["url"], normas["config"]) == ("normas_rfb", RFB["url"], RFB["config"])
    # e o identificador de uma fonte confere essa fonte como está cadastrada, ligada ou não (sem chave do banco: o arquivo)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("ENDERECOS", "rfb-normas, nao-existe https://ex.com.br/")
    fontes, origem = radar_diagnostico.carregar_fontes()
    assert [f["slug"] for f in fontes] == ["rfb-normas", "teste-1"] and fontes[0]["url"] == RFB["url"]
    assert origem == "fontes pedidas, do arquivo robo/radar_fontes.json; não encontradas: nao-existe e endereços informados para teste"
    html = '<html><head><title>T</title><link rel="alternate" type="application/rss+xml" title="Notícias" href="/rss/"></head><body></body></html>'
    assert radar_diagnostico.estrutura_da_pagina(html)["feeds"] == ["Notícias -> /rss/"]


# ============================================================ v0.8.0 — DOU pelo INLABS
def _xml_dou(id_, tipo, orgao, titulo, ementa="", texto="<p>Art. 1º Fica alterado.</p>", data="02/10/2026", pagina=True):
    pdf = f' pdfPage="http://pesquisa.in.gov.br/imprensa/jsp/visualiza/index.jsp?data={data}&amp;jornal=515&amp;pagina=19"' if pagina else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?><xml><article id="{id_}" idMateria="{id_}" name="{titulo}" pubName="DO1" '
            f'artType="{tipo}" pubDate="{data}" artCategory="{orgao}"{pdf}><body><Identifica><![CDATA[{titulo}]]></Identifica>'
            f'<Ementa><![CDATA[{ementa}]]></Ementa><Texto><![CDATA[{texto}]]></Texto></body></article></xml>').encode("utf-8")


def _zip_dou(xmls) -> bytes:
    import io
    import zipfile
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w") as z:
        for n, x in enumerate(xmls):
            z.writestr(f"ato-{n}.xml", x)
        z.writestr("quebrado.xml", b"<xml><article")          # arquivo estragado não derruba o dia
        z.writestr("leia-me.txt", b"nada")
    return mem.getvalue()


CONFIG_INLABS = {"janela_dias": 2, "secoes": ["DO1"], "orgaos": "Receita Federal|Procuradoria-Geral da Fazenda Nacional",
                 "tipos": "Instrução Normativa|Portaria", "excluir_orgao": "Superintendência Regional|Delegacia",
                 "texto_do_feed": True, "texto_minimo": 1}


def test_inlabs_le_o_xml_oficial_e_filtra_orgao_tipo_e_regionais():
    import radar_inlabs
    zip_ = _zip_dou([
        _xml_dou("111", "Instrução Normativa", "Ministério da Fazenda/Secretaria Especial da Receita Federal do Brasil",
                 "INSTRUÇÃO NORMATIVA RFB Nº 2.300, DE 1º DE OUTUBRO DE 2026", "Altera a IN RFB nº 2.005.", "<p>Art. 1º A DCTFWeb passa a...</p>"),
        _xml_dou("222", "Portaria", "Ministério da Fazenda/Procuradoria-Geral da Fazenda Nacional", "PORTARIA PGFN Nº 9, DE 1º DE OUTUBRO DE 2026", pagina=False),
        _xml_dou("333", "Portaria", "Ministério da Fazenda/Secretaria Especial da Receita Federal do Brasil/Superintendência Regional da 9ª Região",
                 "PORTARIA SRRF09 Nº 1"),
        _xml_dou("444", "Portaria", "Ministério da Saúde", "PORTARIA MS Nº 5"),
        _xml_dou("555", "Aviso", "Ministério da Fazenda/Secretaria Especial da Receita Federal do Brasil", "AVISO DE LICITAÇÃO")])
    atos = radar_inlabs.atos_do_zip(zip_)
    assert len(atos) == 5
    escolhidos = radar_inlabs.filtrar(atos, CONFIG_INLABS)
    assert [a["id"] for a in escolhidos] == ["111", "222"]
    it = radar_inlabs.para_item(escolhidos[0])
    assert it.titulo == "INSTRUÇÃO NORMATIVA RFB Nº 2.300, DE 1º DE OUTUBRO DE 2026" and it.data == date(2026, 10, 2)
    assert it.url == "http://pesquisa.in.gov.br/imprensa/jsp/visualiza/index.jsp?data=02/10/2026&jornal=515&pagina=19&materia=111"
    assert it.texto_da_listagem.startswith("INSTRUÇÃO NORMATIVA RFB") and "Art. 1º A DCTFWeb" in it.texto_da_listagem and "<p>" not in it.texto_da_listagem
    assert it.resumo == "Altera a IN RFB nº 2.005." and it.metadados["orgao"].endswith("Receita Federal do Brasil")
    assert radar_inlabs.para_item(escolhidos[1]).url == "https://www.in.gov.br/leiturajornal?data=02-10-2026&secao=do1&materia=222"


def test_inlabs_baixa_os_dias_da_janela_e_pede_o_cadastro_quando_falta():
    import radar_inlabs
    from radar_util import ErroDownload

    class Resp:
        def __init__(self, status, content=b""): self.status_code, self.content = status, content

    class Sessao:
        def __init__(self, aceita=True):
            self.pedidos, self.aceita, self.cookies = [], aceita, {}
        def post(self, url, data, timeout):
            assert url.endswith("/logar.php") and data == {"email": "a@b.c", "password": "s"}
            if self.aceita:
                self.cookies["inlabs_session_cookie"] = "x"
            return Resp(200)
        def get(self, url, params, timeout, headers):
            self.pedidos.append(params["dl"])
            if params["dl"] == "2026-10-02-DO1.zip":
                return Resp(200, _zip_dou([_xml_dou("111", "Instrução Normativa", "Secretaria Especial da Receita Federal do Brasil", "IN RFB Nº 2.300")]))
            return Resp(200, b"<html>sem edicao</html>")                # fim de semana: o INLABS devolve uma página, não um zip

    import os
    fonte = {"slug": "dou-inlabs", "tipo_coletor": "inlabs", "config": CONFIG_INLABS}
    os.environ.pop("INLABS_EMAIL", None); os.environ.pop("INLABS_SENHA", None)
    with pytest.raises(ErroDownload, match="INLABS_EMAIL e INLABS_SENHA"):
        radar_inlabs.listar_paginas(Sessao(), fonte, date(2026, 10, 3))
    os.environ.update(INLABS_EMAIL="a@b.c", INLABS_SENHA="s")
    try:
        with pytest.raises(ErroDownload, match="login não foi aceito"):
            radar_inlabs.listar_paginas(Sessao(aceita=False), fonte, date(2026, 10, 3))
        s = Sessao()
        listagem, http = radar_inlabs.listar_paginas(s, fonte, date(2026, 10, 3))
        assert s.pedidos == ["2026-10-03-DO1.zip", "2026-10-02-DO1.zip"] and http == 200
        assert listagem.brutos == 1 and [i.titulo for i in listagem.itens] == ["IN RFB Nº 2.300"]
        # v0.23.0: o espaço e a quebra de linha colados no segredo do GitHub saem (o login falhava em produção); só espaço = sem cadastro
        os.environ.update(INLABS_EMAIL=" a@b.c\n", INLABS_SENHA="\ts \r\n")
        assert radar_inlabs.listar_paginas(Sessao(), fonte, date(2026, 10, 3))[1] == 200
        os.environ.update(INLABS_EMAIL="a@b.c", INLABS_SENHA=" \n")
        with pytest.raises(ErroDownload, match="INLABS_EMAIL e INLABS_SENHA"):
            radar_inlabs.listar_paginas(Sessao(), fonte, date(2026, 10, 3))
    finally:
        os.environ.pop("INLABS_EMAIL", None); os.environ.pop("INLABS_SENHA", None)



def test_inlabs_manutencao_do_governo_nao_culpa_a_senha():
    """v0.54.0: 404/5xx ou a página de manutenção no login do INLABS = serviço do governo fora do ar. A mensagem é honesta
    (“indisponível/manutenção”), não “confira a senha”. Senha errada de verdade (200 sem sessão) continua pedindo para conferir."""
    import os, radar_inlabs
    from radar_util import ErroDownload

    class Resp:
        def __init__(self, status, content=b""): self.status_code, self.content = status, content

    class Sessao:
        def __init__(self, resposta): self.resposta, self.cookies = resposta, {}
        def post(self, url, data, timeout): return self.resposta

    os.environ.update(INLABS_EMAIL="a@b.c", INLABS_SENHA="s")
    try:
        manut = "<html><body>Site em manutenção, acesso temporariamente indisponível.</body></html>".encode()
        for resp in (Resp(404), Resp(503), Resp(200, manut)):
            with pytest.raises(ErroDownload, match="indisponível"):
                radar_inlabs.entrar(Sessao(resp))
        with pytest.raises(ErroDownload, match="login não foi aceito"):      # 200 sem sessão e sem manutenção = senha mesmo
            radar_inlabs.entrar(Sessao(Resp(200, b"<html>entrar</html>")))
    finally:
        os.environ.pop("INLABS_EMAIL", None); os.environ.pop("INLABS_SENHA", None)


def test_inlabs_recupera_os_dias_parados_quando_o_servico_volta():
    """v0.54.0: ao voltar depois de dias fora do ar, a janela alarga para cobrir o período parado (não perde nada), com teto.
    Em operação normal (sem/último sucesso recente) a janela é a da configuração, como antes."""
    import os, radar_inlabs

    class Resp:
        def __init__(self, status, content=b""): self.status_code, self.content = status, content

    class Sessao:
        def __init__(self): self.pedidos, self.cookies = [], {}
        def post(self, url, data, timeout): self.cookies["inlabs_session_cookie"] = "x"; return Resp(200)
        def get(self, url, params, timeout, headers): self.pedidos.append(params["dl"]); return Resp(200, b"<html>sem edicao</html>")

    os.environ.update(INLABS_EMAIL="a@b.c", INLABS_SENHA="s")
    try:
        fonte = {"slug": "dou-inlabs", "tipo_coletor": "inlabs", "config": {"janela_dias": 1, "secoes": ["DO1"]}}
        s = Sessao(); radar_inlabs.listar_paginas(s, fonte, date(2026, 10, 27))
        assert s.pedidos == ["2026-10-27-DO1.zip"]                                   # normal: só o dia da config
        s2 = Sessao(); radar_inlabs.listar_paginas(s2, dict(fonte, ultimo_sucesso_em="2026-10-19T16:29:00+00:00"), date(2026, 10, 27))
        assert len(s2.pedidos) == 9 and s2.pedidos[0] == "2026-10-27-DO1.zip" and "2026-10-19-DO1.zip" in s2.pedidos   # 8 dias parados + hoje
        s3 = Sessao(); radar_inlabs.listar_paginas(s3, dict(fonte, ultimo_sucesso_em="2026-01-01T00:00:00+00:00"), date(2026, 10, 27))
        assert len(s3.pedidos) == radar_inlabs.TETO_JANELA_DIAS                       # queda muito longa: respeita o teto
    finally:
        os.environ.pop("INLABS_EMAIL", None); os.environ.pop("INLABS_SENHA", None)


def test_inlabs_erro_do_servidor_ou_sessao_perdida_nao_vira_dia_sem_edicao():
    import radar_inlabs
    from radar_util import ErroDownload

    class Resp:
        def __init__(self, status, content=b""): self.status_code, self.content = status, content

    class Sessao:
        def __init__(self, resposta): self.resposta = resposta
        def get(self, url, params, timeout, headers): return self.resposta

    assert radar_inlabs.baixar_secao(Sessao(Resp(404)), date(2026, 10, 4), "DO1") is None
    assert radar_inlabs.baixar_secao(Sessao(Resp(200, b"<html>Nao ha edicao</html>")), date(2026, 10, 4), "DO1") is None
    with pytest.raises(ErroDownload, match="HTTP 500"):
        radar_inlabs.baixar_secao(Sessao(Resp(500)), date(2026, 10, 5), "DO1")
    with pytest.raises(ErroDownload, match="pediu login"):
        radar_inlabs.baixar_secao(Sessao(Resp(200, b"<form action='logar.php'><input name='password'>")), date(2026, 10, 5), "DO1")


# ---------------------------------------------------------------- v0.16.0: página cadastrada como fonte RSS
PAGINA_WP = ('<!DOCTYPE html>\n<html lang="pt-BR"><head><meta charset="UTF-8">\n'
             '<link rel="alternate" type="application/rss+xml" title="Portal &raquo; Feed" href="https://portalcontabilsc.com.br/feed/">\n'
             '<link rel="alternate" type="application/rss+xml" title="Comentários" href="https://portalcontabilsc.com.br/comments/feed/">\n'
             '</head><body><p>&nbsp;Portal</p></body></html>')
FEED_COM_ENTIDADES = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Portal</title>'
                      '<item><title>Cr&eacute;ditos presumidos&nbsp;de ICMS &amp; PIS: decis&atilde;o do STF</title>'
                      '<link>https://portalcontabilsc.com.br/stf-exclui/</link><pubDate>Thu, 09 Oct 2026 10:00:00 +0000</pubDate>'
                      '<description>Texto&nbsp;do resumo</description></item></channel></rss>')


def test_fonte_rss_cadastrada_com_a_pagina_segue_o_feed_que_ela_anuncia():
    fonte = {"slug": "pcsc", "url": "https://portalcontabilsc.com.br/", "tipo_coletor": "rss", "config": {"janela_dias": 30}}
    pedidos = []
    def baixar(url):
        pedidos.append(url)
        return 200, {"https://portalcontabilsc.com.br/": PAGINA_WP, "https://portalcontabilsc.com.br/feed/": FEED_COM_ENTIDADES}[url]
    listagem, http = coletores.listar_paginas(baixar, fonte, date(2026, 10, 9))
    assert pedidos == ["https://portalcontabilsc.com.br/", "https://portalcontabilsc.com.br/feed/"] and http == 200
    assert [(i.titulo, i.url, i.resumo) for i in listagem.itens] == [
        ("Créditos presumidos de ICMS & PIS: decisão do STF", "https://portalcontabilsc.com.br/stf-exclui", "Texto do resumo")]


def test_pagina_sem_feed_cadastrada_como_rss_da_erro_que_explica():
    fonte = {"slug": "x", "url": "https://exemplo.com.br/", "tipo_coletor": "rss", "config": {}}
    with pytest.raises(coletores.PaginaNaoEhFeed, match="não um feed RSS; cadastre o endereço do feed"):
        coletores.listar_paginas(lambda url: (200, "<html><body>&nbsp;Início</body></html>"), fonte, date(2026, 10, 9))
    # o feed anunciado que também é página não vira laço: o erro diz qual endereço cadastrar
    with pytest.raises(coletores.PaginaNaoEhFeed, match="o feed que ela anuncia é https://portalcontabilsc.com.br/feed/"):
        coletores.listar_paginas(lambda url: (200, PAGINA_WP), dict(fonte, url="https://portalcontabilsc.com.br/"), date(2026, 10, 9))
    # bytes também são reconhecidos
    with pytest.raises(coletores.PaginaNaoEhFeed):
        coletores.listar_rss(PAGINA_WP.encode(), fonte)


def test_pagina_de_categoria_segue_o_feed_da_categoria_e_paginada_nao_baixa_a_segunda():
    # WordPress: o feed geral e o de comentários vêm antes do feed da categoria
    categoria = ('<!DOCTYPE html><html><head>'
                 '<link rel="alternate" type="application/rss+xml" title="Portal &raquo; Feed" href="https://portalcontabilsc.com.br/feed/">'
                 '<link rel="alternate" type="application/rss+xml" title="Portal &raquo; Feed de comentários" href="https://portalcontabilsc.com.br/comments/feed/">'
                 '<link rel="alternate" type="application/rss+xml" title="Feed da categoria Notícias" href="https://portalcontabilsc.com.br/categoria/noticias/feed/">'
                 '</head><body></body></html>')
    assert coletores.feed_da_pagina(categoria, "https://portalcontabilsc.com.br/categoria/noticias/") == "https://portalcontabilsc.com.br/categoria/noticias/feed/"
    assert coletores.feed_da_pagina(categoria, "https://portalcontabilsc.com.br/") == "https://portalcontabilsc.com.br/feed/"
    um_nivel = ('<html><head><link rel="alternate" type="application/rss+xml" href="https://s.com.br/feed/">'
                '<link rel="alternate" type="application/rss+xml" href="https://s.com.br/noticias/feed/"></head></html>')
    assert coletores.feed_da_pagina(um_nivel, "https://s.com.br/noticias/page/1/") == "https://s.com.br/noticias/feed/"   # sem /categoria/
    assert coletores.feed_da_pagina(um_nivel, "https://s.com.br/page/2/") == "https://s.com.br/feed/"
    so_comentarios = '<html><head><link rel="alternate" type="application/rss+xml" title="Comentários" href="/comments/feed/"></head></html>'
    assert coletores.feed_da_pagina(so_comentarios, "https://x.com.br/") == "https://x.com.br/comments/feed/"
    pedidos = []
    def baixar(url):
        pedidos.append(url)
        return 200, (FEED_COM_ENTIDADES if url.endswith("/categoria/noticias/feed/") else categoria)
    fonte = {"slug": "pcsc", "url": "https://portalcontabilsc.com.br/categoria/noticias/page/{p}/", "tipo_coletor": "rss",
             "config": {"janela_dias": 30, "paginas_max": 3, "itens_por_pagina": 1}}
    listagem, _ = coletores.listar_paginas(baixar, fonte, date(2026, 10, 9))
    assert pedidos == ["https://portalcontabilsc.com.br/categoria/noticias/page/1/", "https://portalcontabilsc.com.br/categoria/noticias/feed/"]
    assert [i.url for i in listagem.itens] == ["https://portalcontabilsc.com.br/stf-exclui"]


# ============================================================ v0.31.0 — fontes oficiais que faltavam
# As fontes novas são lidas do próprio sql/radar-fontes-novas-v0.31.0.sql: o que se testa aqui é o cadastro que vai para o banco.
RAIZ_REPO = Path(__file__).resolve().parent.parent
SQL_V031 = (RAIZ_REPO / "sql" / "radar-fontes-novas-v0.31.0.sql").read_text(encoding="utf-8")
_LIT = r"'((?:[^']|'')*)'"
_LINHA = re.compile(r"\(\s*" + r",\s*".join([_LIT] * 4) + r",\s*(true|false),\s*(true|false),\s*" + _LIT + r",\s*" + _LIT +
                    r",\s*" + _LIT + r"::jsonb,\s*(?:" + _LIT + r"|null),\s*(\d+)\)")


def _fontes_do_sql(texto: str) -> dict:
    tira = lambda x: x.replace("''", "'") if x is not None else None
    fontes = {}
    for m in _LINHA.finditer(texto):
        slug, nome, orgao, abrangencia, oficial, ativo, tipo, url, config, categoria, freq = m.groups()
        fontes[tira(slug)] = {"slug": tira(slug), "nome": tira(nome), "orgao": tira(orgao), "abrangencia": tira(abrangencia),
                              "oficial": oficial == "true", "ativo": ativo == "true", "tipo_coletor": tira(tipo), "url": tira(url),
                              "config": json.loads(tira(config)), "categoria_padrao": tira(categoria), "frequencia_horas": int(freq)}
    return fontes


NOVAS = _fontes_do_sql(SQL_V031)


def test_fontes_novas_ligadas_so_as_conferidas_e_rfb_normas_igual_nos_tres_lugares():
    assert {s: f["ativo"] for s, f in NOVAS.items()} == {
        "dou-presidencia": True, "dou-confaz": True, "dou-trabalho-previdencia": True, "dou-fazenda-ministro": False,
        "esocial-noticias": True, "fgts-digital-comunicados": True, "previdencia-noticias": True, "inss-noticias": False,
        "domsc-palhoca-leis": False, "domsc-palhoca-decretos": False, "domsc-saojose-leis": False, "domsc-saojose-decretos": False}
    assert all(f["oficial"] for f in NOVAS.values())
    assert {f["tipo_coletor"] for s, f in NOVAS.items() if s.startswith("dou-")} == {"inlabs"}
    for f in NOVAS.values():                           # o filtro de tema de cada uma é uma expressão que o robô aceita
        coletores.filtro_de_tema(f["config"])
        assert len(f["nome"]) <= 200 and re.fullmatch(r"https?://[!-~]+", f["url"]) and len(json.dumps(f["config"])) < 20000
    # a rfb-normas: o mesmo endereço e as mesmas opções no SQL desta versão, no setup (carga inicial) e em robo/radar_fontes.json
    m = re.search(r"set url = '([^']+)',\s*config = '([^']+)'::jsonb\s*where slug = 'rfb-normas'", SQL_V031)
    assert (m.group(1), json.loads(m.group(2))) == (RFB["url"], RFB["config"])
    assert "sem_pagina_de_texto" not in RFB["config"] and "{" not in RFB["url"] and "ativo = true" not in SQL_V031


def test_textos_para_o_dono_dizem_quais_fontes_novas_ficam_sem_filtro_de_tema():
    """Revisão: a aba Versões, o topo do LEIAME e o cabeçalho do SQL diziam que TODA fonte nova tinha filtro de tema, e o DOM/SC "já
    filtrado por tributos". Ficam sem filtro só o eSocial e o FGTS Digital (tudo o que publicam é do departamento pessoal), e os
    textos dizem isso."""
    assert {s for s, f in NOVAS.items() if coletores.filtro_de_tema(f["config"]) is None} == {"esocial-noticias", "fgts-digital-comunicados"}
    html = (RAIZ_REPO / "index.html").read_text(encoding="utf-8")
    versao = html[html.index('["0.31.0", "17/10/2026", ['):html.index('["0.30.0", "17/10/2026", [')]
    leiame = (RAIZ_REPO / "LEIAME-radar.md").read_text(encoding="utf-8")
    textos = {"Versões": versao, "LEIAME (topo)": leiame[:leiame.index("A v0.30.0 traz")], "SQL (cabeçalho)": SQL_V031[:SQL_V031.index("do $$")],
              "LEIAME (fontes da v0.31.0)": leiame[leiame.index("### Fontes oficiais da v0.31.0"):leiame.index("### Instagram e Facebook")]}
    for onde, texto in textos.items():
        assert not re.search(r"todas (?:oficiais e )?com (?:\*\*)?filtro de tema|cada fonte nova tem as palavras|já filtrad", texto), onde
    for onde in ("Versões", "LEIAME (topo)", "SQL (cabeçalho)"):
        assert re.search(r"(?:o|do) eSocial e (?:o|do) FGTS Digital", textos[onde], re.I), onde


def test_cadastro_do_dom_sc_filtro_do_proprio_site_e_sem_abrir_a_pagina_do_ato():
    from urllib.parse import parse_qs, unquote, urlsplit
    domsc = {s: f for s, f in NOVAS.items() if s.startswith("domsc-")}
    assert len(domsc) == 4
    for slug, f in domsc.items():
        partes = urlsplit(f["url"])
        assert partes.netloc == "diariomunicipal.sc.gov.br" and partes.query.endswith("&view=rss")
        args = parse_qs(partes.query)
        assert args["codigoEntidade"][0] in {"185", "251"} and args["categoria"][0] in {"Leis", "Decretos"}
        q = unquote(re.search(r"[?&]q=([^&]+)", f["url"]).group(1))
        assert len(q) <= 200 and q.startswith("(") and q.endswith(")") and "-" not in q and "tribut*" in q     # limites do site
        assert re.fullmatch(r"[a-z%0-9*]+", re.search(r"excluiTermos=([^&]+)", f["url"]).group(1))         # sem acento (estraga)
        assert (f["abrangencia"], f["categoria_padrao"], f["config"]["sem_pagina_de_texto"]) == ("municipal", "santa-catarina", True)
    assert {(s.split("-")[1], s.split("-")[2]) for s in domsc} == {("palhoca", "leis"), ("palhoca", "decretos"), ("saojose", "leis"),
                                                                   ("saojose", "decretos")}


# ------------------------------------------------------------ filtro de tema
CONTEUDO = '<content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/"><![CDATA[{}]]></content:encoded>'


def _feed(*itens):
    return ("<rss><channel>" + "".join(
        f"<item><title>{t}</title><link>https://ex.gov.br/n{n}</link><pubDate>{d}</pubDate><description>{r}</description>"
        + (CONTEUDO.format(c) if c else "") + "</item>"
        for n, (t, r, d, c) in enumerate(itens)) + "</channel></rss>")


QUINTA = "Thu, 15 Oct 2026 10:00:00 -0300"
FEED_TEMA = _feed(("Novo leiaute do eSocial", "Versão S-1.3 dos eventos", QUINTA, ""),
                  ("Campanha do FGTS na televisão", "Publicidade institucional do fundo", QUINTA, ""),
                  ("CONTRIBUIÇÃO PREVIDENCIÁRIA: novo prazo", "Recolhimento até o dia 20", QUINTA, ""),
                  ("Dia nacional do ribeirinho", "Homenagem", QUINTA, "<p>O MINISTRO DO TRABALHO E EMPREGO, no uso...</p>"),
                  ("Notícia antiga de janeiro", "Sem tema", "Thu, 15 Jan 2026 10:00:00 -0300", ""))


def test_filtro_de_tema_entra_fica_fora_e_e_contado_sem_virar_vazio_suspeito():
    fonte = {"url": "u", "config": {"janela_dias": 30, "palavras": ["esocial", "FGTS", "contribuiç"], "excluir_palavras": "campanha"}}
    r = listar_rss(FEED_TEMA, fonte, DIA_NORMAS)
    assert [i.titulo for i in r.itens] == ["Novo leiaute do eSocial", "CONTRIBUIÇÃO PREVIDENCIÁRIA: novo prazo"]
    # a campanha (excluir_palavras) e o dia do ribeirinho (fora das palavras) contam; a notícia de janeiro, fora da janela, não
    assert (r.brutos, r.fora_do_tema) == (5, 2)
    # a mesma coisa como uma expressão só, sem acento e em maiúsculas: casa do mesmo jeito (sem diferença de acento e maiúscula)
    outra = {"url": "u", "config": {"janela_dias": 30, "palavras": "ESOCIAL|fgts|CONTRIBUIC", "excluir_palavras": ["Campanha"]}}
    assert [i.titulo for i in listar_rss(FEED_TEMA, outra, DIA_NORMAS).itens] == [i.titulo for i in r.itens]
    # nada do tema: a página foi lida (brutos > 0), então não é "nenhum item reconhecido"
    nada = {"url": "u", "config": {"janela_dias": 30, "palavras": "imposto de renda"}}
    r = listar_rss(FEED_TEMA, nada, DIA_NORMAS)
    assert (r.itens, r.brutos, r.fora_do_tema) == ([], 5, 4)
    # vazio = sem filtro
    for vazio in ("", [], ["  "], None):
        assert len(listar_rss(FEED_TEMA, {"url": "u", "config": {"janela_dias": 30, "palavras": vazio}}, DIA_NORMAS).itens) == 4


def test_filtro_de_tema_nao_procura_no_texto_inteiro_a_nao_ser_que_a_fonte_peca():
    fonte = {"url": "u", "config": {"janela_dias": 30, "palavras": "trabalho"}}
    assert listar_rss(FEED_TEMA, fonte, DIA_NORMAS).itens == []          # "TRABALHO" só no preâmbulo do texto do feed
    com_texto = {"url": "u", "config": {"janela_dias": 30, "palavras": "trabalho", "palavras_no_texto": True}}
    assert [i.titulo for i in listar_rss(FEED_TEMA, com_texto, DIA_NORMAS).itens] == ["Dia nacional do ribeirinho"]


@pytest.mark.parametrize("palavras, trecho", [
    ("(FAP", 'as palavras do tema (palavras) não são uma expressão válida: "(FAP"'),
    (["FGTS", "[eSocial"], 'não são uma expressão válida: o item 2 ("[eSocial")'),
    (5, "precisam ser um texto ou uma lista de textos"),
    ({"a": 1}, "precisam ser um texto ou uma lista de textos"),
])
def test_palavras_invalidas_viram_erro_claro(palavras, trecho):
    with pytest.raises(ValueError) as e:
        listar_rss(FEED_TEMA, {"url": "u", "config": {"palavras": palavras}}, DIA_NORMAS)
    assert trecho in str(e.value)
    with pytest.raises(ValueError, match=r"excluir_palavras"):
        listar_html_links("<a href='/x/1'>Notícia</a>", {"url": "https://ex.gov.br/", "config": {"padrao_url": "/x/", "excluir_palavras": ["a)"]}}, DIA_NORMAS)


def test_filtro_de_tema_na_listagem_paginada_conta_uma_vez_no_conjunto():
    from radar_coletores import listar_paginas
    paginas = {1: _feed(*[(f"Tema FGTS {n}", "x", QUINTA, "") for n in range(3)] + [("Outro assunto", "x", QUINTA, "")]),
               2: _feed(("Outro assunto 2", "y", QUINTA, ""))}
    paginas[2] = paginas[2].replace("https://ex.gov.br/n0", "https://ex.gov.br/p2")
    fonte = {"slug": "x", "tipo_coletor": "rss", "url": "https://ex.gov.br/feed?p={p}",
             "config": {"janela_dias": 30, "paginas_max": 2, "itens_por_pagina": 4, "palavras": "FGTS"}}
    r, _ = listar_paginas(lambda url: (200, paginas[int(url[-1])]), fonte, DIA_NORMAS)
    assert (len(r.itens), r.brutos, r.fora_do_tema) == (3, 5, 2)


# ------------------------------------------------------------ gov.br: eSocial, FGTS Digital, Previdência (e INSS, desligada)
def _govbr(slug, arquivo, **mudancas):
    fonte = dict(NOVAS[slug], config=dict(NOVAS[slug]["config"], **mudancas))
    return listar(amostra(arquivo), fonte, DIA_NORMAS)


def test_govbr_data_e_a_de_publicacao_e_nao_a_do_resumo():
    datas = {i.url.rsplit("/", 1)[-1]: i.data for i in _govbr("esocial-noticias", "govbr-esocial-noticias.html", janela_dias=3650).itens}
    # o resumo cita prazos (24/06/2026, 25/04/2026, 31/07/2026); vale a linha "publicado dd/mm/aaaa"
    assert datas["atualizacao-de-certificado-do-esocial-para-um-novo-padrao-de-seguranca"] == date(2025, 12, 11)
    assert datas["indisponibilidade-do-sistema-dctfweb"] == date(2026, 4, 17)
    assert datas["parada-do-esocial-em-31-07-2026-19h-manutencao-programada-para-implantacao-do-cnpj-alfanumerico"] == date(2026, 7, 30)
    assert datas["parada-do-esocial-em-21-01-2026-manutencao-programada"] == date(2026, 1, 16)
    r = itens_de('<li><a href="/pgfn/pt-br/assuntos/noticias/2026/prazo">Prazo novo</a> <span>Vence em 31/12/2026 e 01/12/2026.</span>'
                 ' <span>publicado 28/09/2026 10h00</span></li>')
    assert r.itens[0].data == date(2026, 9, 28)
    # revisão: o resumo, que vem ANTES da linha "publicado", pode dizer "a portaria publicada em 10/03/2026": vale a última data
    # marcada como de publicação (a da linha), e não a primeira (a citada no resumo)
    original = "Sistema ficará indisponível no dia 25/04/2026, entre 0h e 12h, com reflexos no eSocial."
    pagina = amostra("govbr-esocial-noticias.html")
    assert pagina.count(original) == 1
    citada = pagina.replace(original, "A Portaria Conjunta publicada em 10/03/2026 previa a parada; o sistema ficará indisponível no dia 25/04/2026.")
    fonte = dict(NOVAS["esocial-noticias"], config=dict(NOVAS["esocial-noticias"]["config"], janela_dias=3650))
    datas = {i.url.rsplit("/", 1)[-1]: i.data for i in listar(citada, fonte, DIA_NORMAS).itens}
    assert datas["indisponibilidade-do-sistema-dctfweb"] == date(2026, 4, 17)
    r = itens_de('<li><a href="/pgfn/pt-br/assuntos/noticias/2026/prazo">Prazo novo</a> <span>A IN publicada em 10/03/2026 vence em '
                 '31/12/2026.</span> <span>publicado 28/09/2026 10h00</span></li>')
    assert r.itens[0].data == date(2026, 9, 28)


def test_esocial_ignora_menu_termos_mais_buscados_colecoes_e_paginacao():
    r = _govbr("esocial-noticias", "govbr-esocial-noticias.html", janela_dias=3650)
    urls = [i.url for i in r.itens]
    assert r.brutos == 10 and len(urls) == 10
    assert not any("colecao-" in u or "search" in u or "b_start" in u for u in urls)
    assert any("/noticias/receita-federal/antecipacao-de-atividades" in u for u in urls)   # a subpasta entra
    r = _govbr("esocial-noticias", "govbr-esocial-noticias.html")
    assert r.brutos == 10 and r.itens == []        # nada novo desde 27/08: a página foi reconhecida (não é "layout mudou")


def test_fgts_digital_comunicados_em_ordem_de_publicacao():
    r = _govbr("fgts-digital-comunicados", "govbr-fgts-comunicados.html", janela_dias=3650)
    assert r.brutos == 7 and r.itens[0].titulo == "A emissão antecipada da guia não antecipa a obrigação de pagamento"
    assert r.itens[0].data == date(2026, 9, 23)
    assert all("summary_view" not in i.url and "b_start" not in i.url for i in r.itens)
    datas = {i.url.rsplit("/", 1)[-1]: i.data for i in r.itens}
    assert datas["recolhimentos-de-fgts-em-processos-trabalhistas-serao-efetuados-via-fgts-digital-a-partir-de-maio-2026"] == date(2026, 4, 2)
    assert [i.data for i in _govbr("fgts-digital-comunicados", "govbr-fgts-comunicados.html").itens] == [date(2026, 9, 23)]


def test_previdencia_e_inss_so_entra_o_que_e_do_escritorio():
    sem_filtro = _govbr("previdencia-noticias", "govbr-previdencia-noticias.html", palavras="")
    com_filtro = _govbr("previdencia-noticias", "govbr-previdencia-noticias.html")
    assert len(sem_filtro.itens) == 9                 # fraude, mutirão, Lei Maria da Penha, FAP...
    assert [i.titulo[:39] for i in com_filtro.itens] == ["Fator Acidentário de Prevenção (FAP) co"]
    assert (com_filtro.brutos, com_filtro.fora_do_tema) == (9, 8)
    inss = _govbr("inss-noticias", "govbr-inss-noticias.html", palavras="")
    assert inss.brutos == 9 and len(inss.itens) == 6 and all(i.data for i in inss.itens)    # as 3 páginas do menu, sem data, saem
    assert [i.url.rsplit("/", 1)[-1][:40] for i in _govbr("inss-noticias", "govbr-inss-noticias.html").itens] == [
        "fez-alguma-contribuicao-com-base-em-valo"]
    assert "/inss/pt-br/noticias" not in NOVAS["inss-noticias"]["url"]          # esse endereço leva à página de login


@pytest.mark.parametrize("slug, arquivo, comeco", [
    ("esocial-noticias", "govbr-esocial-item.html", "Com fundamento na Lei Complementar nº 224/2025"),
    ("fgts-digital-comunicados", "govbr-fgts-item.html", "Considerando que o vencimento do FGTS mensal"),
    ("previdencia-noticias", "govbr-previdencia-item.html", "As informações referentes ao Fator Acidentário de Prevenção (FAP) 2026"),
    ("inss-noticias", "govbr-inss-item.html", "Você sabia que nenhum benefício do Instituto Nacional do Seguro Social"),
])
def test_texto_da_noticia_do_govbr_sem_o_menu(slug, arquivo, comeco):
    texto = extrair_texto(amostra(arquivo), NOVAS[slug]["config"]["seletor_texto"])
    assert texto.startswith(comeco) and len(texto) > 1000
    assert "Termos mais buscados" not in texto and "Desenrola" not in texto and "Compartilhe" not in texto


# ------------------------------------------------------------ DOM/SC (Palhoça e São José), desligadas
def test_dom_sc_le_o_feed_real_com_data_resumo_e_texto_parcial_sem_abrir_o_ato():
    fonte = NOVAS["domsc-palhoca-decretos"]
    # revisão: a pesquisa do site olha o ato inteiro e até o nome do arquivo. O único decreto dos últimos 30 dias, o 4.033 ("QUALIFICAÇÃO.
    # OS. Dispõe sobre a qualificação de entidade"), só veio porque o PDF se chama "..._instituto_de_saude_social._iss_extrato.pdf":
    # é lido e fica fora do tema (excluir_palavras), sem virar captura
    r = listar(amostra("domsc-rss-palhoca-decretos.xml"), fonte, DIA_NORMAS)
    assert (r.brutos, r.itens, r.fora_do_tema) == (10, [], 1)
    r = listar(amostra("domsc-rss-palhoca-decretos.xml"), dict(fonte, config=dict(fonte["config"], janela_dias=60)), DIA_NORMAS)
    assert [(i.url, i.data, i.titulo) for i in r.itens] == [
        ("https://diariomunicipal.sc.gov.br/?q=id:8706903", date(2026, 9, 14), "DECRETO Nº 4.002, DE 09 DE SETEMBRO DE 2026")]
    assert r.fora_do_tema == 2                                     # o 4.033 (qualificação de entidade) e o 3.996 (Temporada de Verão)
    assert r.itens[0].texto_da_listagem == r.itens[0].resumo and r.itens[0].resumo.startswith(
        "DECRETO Nº 4.002, DE 09 DE SETEMBRO DE 2026. NOTA FISCAL ELETRÔNICA.")
    r = listar(amostra("domsc-rss-palhoca-decretos.xml"), dict(fonte, config=dict(fonte["config"], janela_dias=400)), DIA_NORMAS)
    assert (len(r.itens), r.fora_do_tema) == (6, 4)                # fora: OS, Temporada de Verão e os dois do Conselho de Habitação
    assert not any(p in i.resumo for i in r.itens for p in ("QUALIFICAÇÃO", "TEMPORADA", "HABITAÇÃO"))
    sj = NOVAS["domsc-saojose-leis"]
    r = listar(amostra("domsc-rss-saojose-leis.xml"), dict(sj, config=dict(sj["config"], janela_dias=400)), DIA_NORMAS)
    lc183 = next(i for i in r.itens if "COMPLEMENTAR N.º 183" in i.titulo)
    assert (len(r.itens), r.fora_do_tema) == (7, 3) and lc183.data == date(2025, 12, 10) and "NOTA PREMIADA" in lc183.resumo
    fora = {"LEI N.º 6.611 DE 14 DE JULHO DE 2026", "LEI COMPLEMENTAR N.º 192 DE 12 DE MAIO DE 2026", "LEI N.º 6.547 DE 18 DE DEZEMBRO DE 2025"}
    assert not fora & {i.titulo for i in r.itens}                  # utilidade pública, serviços funerários e operação de crédito
    assert listar(amostra("domsc-rss-saojose-leis.xml"), sj, DIA_NORMAS).itens == []      # nada nos últimos 30 dias
    # as quatro fontes do DOM/SC tiram os mesmos assuntos
    assert len({json.dumps(f["config"]["excluir_palavras"]) for s, f in NOVAS.items() if s.startswith("domsc-")}) == 1


# ------------------------------------------------------------ Diário Oficial (INLABS): leis e decretos, CONFAZ, trabalho
def _xml_amostra(nome):
    import radar_inlabs
    return radar_inlabs.ler_xml((AMOSTRAS / nome).read_bytes())


def _destino(ato, hoje=DIA_NORMAS):
    """As fontes do INLABS (desta versão e a dou-inlabs) que gravariam o ato: órgão, tipo e regionais; depois o tema."""
    import radar_inlabs
    destino = []
    for slug, f in NOVAS.items():
        if f["tipo_coletor"] == "inlabs" and radar_inlabs.filtrar([ato], f["config"]):
            r = coletores._finalizar([radar_inlabs.para_item(ato)], dict(f["config"], janela_dias=4000), hoje)
            destino.append((slug, len(r.itens)))
    return destino


@pytest.mark.parametrize("arquivo, esperado", [
    ("dou-presidencia-entra-decreto-13134-pis-cofins.xml", [("dou-presidencia", 1)]),
    ("dou-presidencia-entra-ec-141-jornada.xml", [("dou-presidencia", 1)]),
    ("dou-presidencia-fora-tema-mp-1396-orgao-trocado.xml", [("dou-presidencia", 0)]),     # órgão trocado (STF): passa pelo tipo; tema não
    ("dou-confaz-entra-despacho-48-convenios.xml", [("dou-confaz", 1)]),
    ("dou-confaz-fora-excluir-pmpf-28.xml", [("dou-confaz", 0)]),                           # PMPF: excluir_palavras
    ("dou-trabalho-entra-portaria-conjunta-49-salario-maternidade.xml", [("dou-trabalho-previdencia", 1)]),
])
def test_atos_reais_do_dou_vao_para_a_fonte_certa(arquivo, esperado):
    assert _destino(_xml_amostra(arquivo)) == esperado


@pytest.mark.parametrize("titulo, ementa", [
    # reais (DOU): a portaria do trabalho em feriados no comércio e a prorrogação dela; a ementa só cita a norma que alteram
    ("PORTARIA MTE Nº 3.665, DE 13 DE NOVEMBRO DE 2023",
     "Altera a Portaria/MTP nº 671, de 8 de novembro de 2021. (Processo nº 19964.203605/2023-95)."),
    ("PORTARIA MTE Nº 1.066, DE 17 DE JUNHO DE 2025", "Prorroga o início da vigência da Portaria MTE nº 3.665, de 13 de novembro de 2023."),
    # montadas: o termo da própria Portaria/MTP 671 e a Instrução Normativa consolidada da inspeção do trabalho
    ("PORTARIA MTE Nº 1, DE 2 DE JANEIRO DE 2026", "Dispõe sobre o registro eletrônico de ponto."),
    ("INSTRUÇÃO NORMATIVA MTE Nº 1, DE 2 DE JANEIRO DE 2026", "Altera a Instrução Normativa/MTP nº 2, de 8 de novembro de 2021."),
    ("PORTARIA MTE Nº 2, DE 2 DE JANEIRO DE 2026", "Dispõe sobre o trabalho aos domingos e feriados autorizado em convenção coletiva."),
])
def test_dou_trabalho_ato_que_so_cita_a_norma_consolidada_que_altera_entra(titulo, ementa):
    """Revisão: o ato do MTE com ementa (o filtro não olha o texto) que só cita a portaria consolidada que altera (Portaria/MTP 671, IN/MTP
    2) ou só prorroga outra portaria ficava "fora do tema", embora passe pelo órgão e pelo tipo."""
    tipo = "Instrução Normativa" if titulo.startswith("INSTRUÇÃO") else "Portaria"
    ato = {"id": "1", "tipo": tipo, "orgao": "Ministério do Trabalho e Emprego/Gabinete do Ministro", "titulo": titulo, "ementa": ementa,
           "texto": "", "data": None, "secao": "DO1", "pagina": ""}
    assert _destino(ato) == [("dou-trabalho-previdencia", 1)]
    # outra portaria do MTE, de outro assunto, continua fora
    assert _destino(dict(ato, ementa="Altera a Portaria MTE nº 9, que dispõe sobre o Regimento Interno da Mesa Nacional.")) == [
        ("dou-trabalho-previdencia", 0)]


def test_ato_do_dou_sem_ementa_no_xml_usa_o_paragrafo_da_ementa_do_texto():
    import radar_inlabs
    ato = _xml_amostra("dou-trabalho-entra-portaria-conjunta-49-salario-maternidade.xml")
    assert ato["ementa"].startswith("Dispõe sobre a concessão automática e provisória do salário-maternidade")
    it = radar_inlabs.para_item(ato)
    assert it.resumo == ato["ementa"] and it.trecho_do_tema is None
    # sem ementa nenhuma, o tema olha só o começo do texto (500 caracteres), nunca o texto inteiro
    sem = dict(ato, ementa="", texto="O MINISTRO resolve: " + "x " * 400 + "salário-maternidade")
    it = radar_inlabs.para_item(sem)
    assert len(it.trecho_do_tema) == 500 and "salário-maternidade" not in it.trecho_do_tema
    assert _destino(sem) == [("dou-trabalho-previdencia", 0)]


def test_112_atos_reais_do_dou_cada_fonte_decide_como_na_medicao():
    """Os 112 atos de 17 dias reais do DOU (2025 e 2026) da medição da pesquisa: para cada fonte do INLABS, se o ato fica de fora
    pelo órgão ou tipo (vazio), entra (ENTRA), sai pelas palavras do tema (fora-tema) ou pelas palavras excluídas (fora-excluir)."""
    import csv
    import radar_inlabs
    linhas = list(csv.DictReader((AMOSTRAS / "dou-atos-reais-2025-2026.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert len(linhas) == 112
    contagem = {}
    for l in linhas:
        ato = {"id": "1", "tipo": l["tipo"], "orgao": l["orgao"], "titulo": l["titulo"], "ementa": l["ementa"], "texto": "",
               "data": None, "secao": l["edicao"], "pagina": ""}
        for slug in ("dou-presidencia", "dou-confaz", "dou-trabalho-previdencia", "dou-fazenda-ministro"):
            config = NOVAS[slug]["config"]
            if not radar_inlabs.filtrar([ato], config):
                obtido = ""
            elif coletores.filtro_de_tema(config)(radar_inlabs.para_item(ato)):
                obtido = "ENTRA"
            else:
                alvo = sem_acentos(f"{ato['titulo']} {ato['ementa']}")
                palavras = coletores.expressao_do_tema(config.get("palavras"))
                obtido = "fora-tema" if palavras is not None and not palavras.search(alvo) else "fora-excluir"
            assert obtido == l[slug], (slug, l["titulo"])
            contagem[(slug, obtido)] = contagem.get((slug, obtido), 0) + 1
    assert {s: contagem.get((s, "ENTRA"), 0) for s in ("dou-presidencia", "dou-confaz", "dou-trabalho-previdencia", "dou-fazenda-ministro")} == \
        {"dou-presidencia": 10, "dou-confaz": 9, "dou-trabalho-previdencia": 6, "dou-fazenda-ministro": 3}


def test_varias_fontes_do_inlabs_na_mesma_rodada_baixam_cada_dia_uma_vez(monkeypatch):
    import radar_coletar
    import radar_inlabs

    class Resp:
        def __init__(self, status, content=b""): self.status_code, self.content = status, content

    class Sessao:
        def __init__(self):
            self.pedidos, self.logins, self.cookies = [], 0, {}
        def post(self, url, data, timeout):
            self.logins += 1
            self.cookies["inlabs_session_cookie"] = "x"
            return Resp(200)
        def get(self, url, params, timeout, headers):
            self.pedidos.append(params["dl"])
            xmls = [(AMOSTRAS / n).read_bytes() for n in ("dou-presidencia-entra-decreto-13134-pis-cofins.xml",
                                                          "dou-confaz-entra-despacho-48-convenios.xml",
                                                          "dou-confaz-fora-excluir-pmpf-28.xml")]
            return Resp(200, _zip_dou(xmls)) if params["dl"] == "2026-10-14-DO1.zip" else Resp(404)

    monkeypatch.setenv("INLABS_EMAIL", "a@b.c")
    monkeypatch.setenv("INLABS_SENHA", "s")
    presidencia = {"slug": "dou-presidencia", "tipo_coletor": "inlabs", "config": dict(NOVAS["dou-presidencia"]["config"], janela_dias=7)}
    confaz = {"slug": "dou-confaz", "tipo_coletor": "inlabs", "config": dict(NOVAS["dou-confaz"]["config"], janela_dias=7)}
    s = Sessao()
    assert radar_coletar.tempo_da_fonte(presidencia, s, DIA_NORMAS) == 600
    r1, _ = radar_inlabs.listar_paginas(s, presidencia, DIA_NORMAS)
    assert len(s.pedidos) == 14 and s.logins == 1                      # 7 dias × (DO1 e DO1E), com um login
    assert radar_inlabs.janela_em_memoria(s, confaz, DIA_NORMAS)
    assert radar_coletar.tempo_da_fonte(confaz, s, DIA_NORMAS) == radar_coletar.TEMPO_INLABS_EM_MEMORIA     # só filtra: cabe na rodada
    r2, _ = radar_inlabs.listar_paginas(s, confaz, DIA_NORMAS)
    assert len(s.pedidos) == 14 and s.logins == 1                      # nada baixado de novo
    assert [i.titulo for i in r1.itens] == ["DECRETO Nº 13.134, DE 9 DE OUTUBRO DE 2026"]
    assert [i.titulo for i in r2.itens] == ["DESPACHO Nº 48, DE 13 DE OUTUBRO DE 2026"] and r2.fora_do_tema == 1 and r2.brutos == 3
    # uma janela maior baixa só os dias que faltam; a rodada seguinte (outra sessão) baixa tudo de novo
    radar_inlabs.listar_paginas(s, dict(confaz, config=dict(confaz["config"], janela_dias=8)), DIA_NORMAS)
    assert s.pedidos[14:] == ["2026-10-10-DO1.zip", "2026-10-10-DO1E.zip"] and s.logins == 1
    nova = Sessao()
    assert not radar_inlabs.janela_em_memoria(nova, confaz, DIA_NORMAS)
    radar_inlabs.listar_paginas(nova, confaz, DIA_NORMAS)
    assert len(nova.pedidos) == 14 and nova.logins == 1


def test_resumo_da_rodada_conta_o_que_ficou_fora_do_tema():
    import radar_coletar
    texto = radar_coletar.resumo_markdown([
        {"fonte": "dou-presidencia", "status": "ok", "encontrados": 1, "fora_do_tema": 4, "novos": 1, "atualizados": 0, "sem_texto": 0,
         "com_erro": 0, "erro": None},
        {"fonte": "rfb-noticias", "status": "ok", "encontrados": 2, "novos": 0, "atualizados": 0, "sem_texto": 0, "com_erro": 0, "erro": None}], [])
    assert "| Fonte | Situação | Na janela | Fora do tema | Novos |" in texto
    assert "| dou-presidencia | ok | 1 | 4 | 1 |" in texto and "| rfb-noticias | ok | 2 | 0 | 0 |" in texto
    assert "Fora do tema (não viraram captura): 4 item(ns)" in texto
