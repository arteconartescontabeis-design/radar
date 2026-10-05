"""Testes dos leitores de listagem e das utilidades (sem rede, sem banco)."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from radar_coletores import listar, listar_html_links, listar_normas_rfb, listar_rss
from radar_util import canonizar_url, extrair_texto, hash_conteudo, hash_titulo, interpretar_data

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
def test_normas_rfb_filtra_unidades_regionais_e_estabiliza_a_url():
    fonte = dict(FONTES["rfb-normas"], config=dict(FONTES["rfb-normas"]["config"], janela_dias=15))
    r = listar_normas_rfb(amostra("rfb-normas.html"), fonte, HOJE)
    assert r.brutos == 5                       # 5 linhas reconhecidas na tabela
    assert [i.titulo for i in r.itens] == [
        "Instrução Normativa RFB nº 2290, de 30/09/2026",
        "Solução de Consulta Cosit nº 198, de 29/09/2026"]     # SRRF fora; portaria de janeiro fora da janela
    it = r.itens[0]
    assert it.url == "https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/153990"   # sem "/vs/..."
    assert it.url_texto is None                # o texto integral não tem endereço direto: fica a ementa
    assert it.texto_da_listagem == ("Instrução Normativa RFB nº 2290, de 30/09/2026. Ementa: Dispõe sobre a apuração da "
                                    "Contribuição Social sobre Bens e Serviços (CBS) no período de transição.")
    assert it.metadados == {"tipo": "Instrução Normativa", "numero": "2290", "orgao": "RFB", "id_ato": "153990"}
    com_molde = dict(fonte, config=dict(fonte["config"], url_texto="http://x/link.action?idAto={id}"))
    assert listar_normas_rfb(amostra("rfb-normas.html"), com_molde, HOJE).itens[0].url_texto == "http://x/link.action?idAto=153990"


def test_normas_rfb_sem_tabela_devolve_zero_reconhecidos():
    assert listar_normas_rfb(amostra("layout-mudou.html"), FONTES["rfb-normas"], HOJE).brutos == 0


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
    bloqueada = radar_diagnostico.diagnosticar(FONTES["rfb-normas"], tmp_path, None)
    assert bloqueada["veredito"] == "FALHA" and bloqueada["http"] == 403
    # fonte paginada e sem página de texto (normas): guarda cada página e mede a ementa
    url1 = "http://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action?tipoData=2&dt_inicio=21/09/2026&dt_fim=01/10/2026&optOrdem=Publicacao_DESC&p=1"
    paginas[url1] = amostra("rfb-normas.html")
    normas = radar_diagnostico.diagnosticar(FONTES["rfb-normas"], tmp_path, None)
    assert normas["veredito"] == "OK" and normas["brutos"] == 5 and normas["na_janela"] == 2
    assert normas["inicio_texto"].startswith("Instrução Normativa RFB nº 2290") and (tmp_path / "rfb-normas-lista.txt").exists()
    texto = radar_diagnostico.relatorio_md([ok, mudou, bloqueada])
    assert "| pgfn-noticias | 200 | 4 |" in texto and "HTTP 403" in texto
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


def test_normas_reais_filtro_por_orgao_e_texto_da_ementa():
    linhas = "".join(f'<tr><td><a href="https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{i}/vs/QUJD">{t}</a></td>'
                     f'<td><a href="https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{i}/vs/QUJD">{n}</a></td>'
                     f"<td>{o}</td><td>{d}</td><td>{e}</td></tr>" for t, n, o, d, e, i in REAIS["rfb-normas"]["linhas"])
    r = listar_normas_rfb(f"<table><tr><th>Tipo do ato</th><th>Nº</th><th>Órgão</th><th>Publicação</th><th>Ementa</th></tr>{linhas}</table>",
                          FONTES["rfb-normas"], DIA)
    assert r.brutos == 7
    assert [i.titulo for i in r.itens] == ["Ato Declaratório Executivo Sutri nº 11, de 02/10/2026",
                                           "Ato Declaratório Executivo Coana nº 132, de 28/09/2026"]
    assert r.itens[0].texto_da_listagem.endswith("Ementa: Altera o Ato Declaratório Executivo Sutri nº 8.")


def test_enderecos_da_listagem_com_janela_de_datas_e_paginas():
    from radar_coletores import enderecos_da_listagem, listar_paginas
    urls = enderecos_da_listagem(FONTES["rfb-normas"], DIA)
    assert len(urls) == 6
    assert urls[0] == ("http://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action?tipoData=2&dt_inicio=22/09/2026"
                       "&dt_fim=02/10/2026&optOrdem=Publicacao_DESC&p=1")
    assert urls[5].endswith("&p=6")
    assert enderecos_da_listagem(FONTES["pgfn-noticias"], DIA) == ["https://www.gov.br/pgfn/pt-br/assuntos/noticias"]

    def linha(n, orgao="RFB", quando="01/10/2026"):
        return (f'<tr><td><a href="https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{n}/vs/A">Portaria</a></td>'
                f"<td>{n}</td><td>{orgao}</td><td>{quando}</td><td>Ementa {n}</td></tr>")
    paginas = {1: "<table>" + "".join(linha(n, "DRF/SOR") for n in range(1000, 1100)) + "</table>",
               2: "<table>" + "".join(linha(n) for n in range(2000, 2100)) + "</table>",
               3: "<table>" + "".join(linha(n) for n in range(3000, 3030)) + "</table>"}
    pedidos = []

    def baixar_falso(url):
        pedidos.append(url)
        return 200, paginas[int(url.rsplit("=", 1)[1])]

    fonte = dict(FONTES["rfb-normas"], config=dict(FONTES["rfb-normas"]["config"], max_itens=500))
    r, http = listar_paginas(baixar_falso, fonte, DIA)
    assert len(pedidos) == 3                      # parou na página incompleta
    assert (r.brutos, len(r.itens), http) == (230, 130, 200)      # a 1ª página inteira era de unidade regional


def test_paginacao_limite_vale_para_o_conjunto_e_pagina_com_erro_nao_perde_as_anteriores():
    from radar_coletores import listar_paginas

    def linha(n):
        return (f'<tr><td><a href="https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{n}/vs/A">Portaria</a></td>'
                f"<td>{n}</td><td>RFB</td><td>01/10/2026</td><td>Ementa {n}</td></tr>")
    paginas = {n: "<table>" + "".join(linha(n * 1000 + i) for i in range(100)) + "</table>" for n in (1, 2, 3)}
    fonte = dict(FONTES["rfb-normas"], config=dict(FONTES["rfb-normas"]["config"], max_itens=250))
    r, _ = listar_paginas(lambda url: (200, paginas.get(int(url.rsplit("=", 1)[1]), "<table></table>")), fonte, DIA)
    ids = sorted(int(i.metadados["id_ato"]) // 1000 for i in r.itens)
    assert len(r.itens) == 250 and set(ids) == {1, 2, 3} and r.incompleta is None      # itens das 3 páginas, não só da 1ª

    def com_falha(url):
        if url.endswith("p=2"):
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
