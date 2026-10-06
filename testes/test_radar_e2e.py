"""Teste de ponta a ponta: robô real → PostgREST real → PostgreSQL com o setup real.

As "fontes" são páginas servidas por um servidor HTTP local, para poder simular
site fora do ar, mudança de layout e alteração de texto. Requer o binário
`postgrest` no PATH (o mesmo motor de API usado pelo Supabase); sem ele, o
arquivo é pulado.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import subprocess
import threading
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

import radar_coletar
from conftest import API, jwt
from radar_banco import Banco, ErroBanco

PORTA_SITE = 3998
SITE = f"http://127.0.0.1:{PORTA_SITE}"
HOJE = date(2026, 10, 1)
PAGINAS: dict[str, tuple[int, str]] = {}
IA = {"pedidos": [], "status": 200, "mensagem": "", "responder": None}


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        status, corpo = PAGINAS.get(self.path, (404, "nao encontrado"))
        dados = corpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_POST(self):
        """IA Central de mentira (o robô chama o ia-gateway no formato da Anthropic)."""
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        IA["pedidos"].append({"corpo": corpo, "cab": {k.lower(): v for k, v in self.headers.items()}})
        if IA.get("bruto") is not None:
            dados = IA["bruto"].encode()
        elif IA["status"] != 200:
            dados = json.dumps({"type": "error", "error": {"type": "artecon_ia_central", "message": IA["mensagem"]}}).encode()
        elif corpo.get("tools", [{}])[0].get("name") == "conteudo":        # v0.9.0: rascunho automático
            dados = json.dumps({"type": "message", "model": corpo["model"], "stop_reason": "tool_use", "usage": {"input_tokens": 5000, "output_tokens": 900},
                                "content": [{"type": "tool_use", "name": "conteudo",
                                             "input": IA["conteudo"](corpo) if callable(IA["conteudo"]) else IA["conteudo"]}]}).encode()
        else:
            ids = [json.loads(l)["id"] for l in corpo["messages"][0]["content"].split("NOVOS (avalie cada um):\n")[1].splitlines()]
            itens = IA["responder"](ids) if IA["responder"] else [{"id": i, "nota": 7, "motivo": "m", "tema": "t", "igual_a": None} for i in ids]
            dados = json.dumps({"type": "message", "model": corpo["model"], "stop_reason": "tool_use", "usage": {"input_tokens": 900, "output_tokens": 200},
                                "content": [{"type": "tool_use", "name": "avaliacao", "input": {"itens": itens}}]}).encode()
        self.send_response(IA["status"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def servicos(api_postgrest):
    site = ThreadingHTTPServer(("127.0.0.1", PORTA_SITE), Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    yield
    site.shutdown()


def artigo(texto: str) -> str:
    return (f"<html><body><nav>Menu do portal</nav><div id='content-core'><p>{texto}</p>"
            f"<p>{'Parágrafo complementar com orientações ao contribuinte. ' * 5}</p></div>"
            f"<footer>Rodapé do portal</footer></body></html>")


def lista(itens: list[tuple[str, str, str]]) -> str:
    return "<html><body><ul>" + "".join(
        f"<li><h2><a href='{u}'>{t}</a></h2><span>{d}</span></li>" for u, t, d in itens) + "</ul></body></html>"


@pytest.fixture()
def cenario(servicos, limpo):
    """Duas fontes de teste ativas (as reais ficam inativas durante o teste)."""
    PAGINAS.clear()
    PAGINAS.update({
        "/a/lista": (200, lista([("/a/noticias/2026/prazo-do-simples-prorrogado", "Prazo do Simples Nacional é prorrogado", "30/09/2026"),
                                 ("/a/noticias/2026/nova-transacao-tributaria", "PGFN abre nova transação tributária", "28/09/2026"),
                                 ("/a/noticias/2026/noticia-antiga-de-janeiro", "Notícia antiga de janeiro", "05/01/2026")])),
        "/a/noticias/2026/prazo-do-simples-prorrogado": (200, artigo("O prazo de opção foi prorrogado até 31 de janeiro de 2027.")),
        "/a/noticias/2026/nova-transacao-tributaria": (200, artigo("O edital prevê descontos de até 65% sobre multas e juros.")),
        "/b/lista": (200, lista([("/b/atos/2026/decreto-numero-1700-icms", "Decreto nº 1.700 altera o RICMS/SC", "29/09/2026")])),
        "/b/atos/2026/decreto-numero-1700-icms": (200, artigo("Fica alterado o art. 15 do Anexo 2 do RICMS/SC.")),
    })
    limpo.execute("update radar_fontes set ativo = false")
    for slug, caminho, padrao in [("teste-a", "/a/lista", "/a/noticias/\\d{4}/"), ("teste-b", "/b/lista", "/b/atos/\\d{4}/")]:
        limpo.execute("""insert into radar_fontes (slug, nome, orgao, tipo_coletor, url, config)
                         values (%s, %s, 'Órgão de teste', 'html_links', %s, %s::jsonb)""",
                      (slug, slug, SITE + caminho, json.dumps({"padrao_url": padrao, "janela_dias": 30,
                                                               "seletor_texto": "#content-core"})))
    yield limpo
    limpo.execute("truncate radar_capturas_versoes, radar_capturas, radar_execucoes restart identity cascade")
    limpo.execute("delete from radar_fontes where slug like 'teste-%'")
    limpo.execute("update radar_fontes set ativo = true")


def robo(slug=None, forcar=True):
    banco = Banco(API, jwt("service_role"), prefixo="")
    resultados, pulados = radar_coletar.executar(banco, slug, forcar, hoje=HOJE, pausa=0)
    return {r["fonte"]: r for r in resultados}, pulados


def test_primeira_coleta_grava_itens_da_janela_com_texto_e_hash(cenario):
    r, _ = robo()
    assert (r["teste-a"]["status"], r["teste-a"]["novos"]) == ("ok", 2)       # a de janeiro fica fora da janela
    assert (r["teste-b"]["status"], r["teste-b"]["novos"]) == ("ok", 1)
    linhas = cenario.execute("""select titulo, data_publicacao, texto, length(hash_conteudo), versao
                                from radar_capturas order by id""").fetchall()
    assert len(linhas) == 3
    assert linhas[0][0] == "Prazo do Simples Nacional é prorrogado" and linhas[0][1] == date(2026, 9, 30)
    assert linhas[0][2].startswith("O prazo de opção foi prorrogado até 31 de janeiro de 2027.")
    assert "Menu do portal" not in linhas[0][2] and "Rodapé" not in linhas[0][2]
    assert all(l[3] == 64 and l[4] == 1 for l in linhas)
    ex = cenario.execute("select status, itens_novos, http_status, versao_robo, finalizado_em is not null "
                         "from radar_execucoes order by id").fetchall()
    assert ex == [("ok", 2, 200, "0.10.0", True), ("ok", 1, 200, "0.10.0", True)]
    assert cenario.execute("select count(*) from radar_fontes where slug like 'teste-%' and ultimo_sucesso_em is not null").fetchone()[0] == 2


def test_segunda_coleta_nao_duplica(cenario):
    robo()
    r, _ = robo()
    assert r["teste-a"]["novos"] == 0 and r["teste-a"]["atualizados"] == 0 and r["teste-a"]["encontrados"] == 2
    assert cenario.execute("select count(*) from radar_capturas").fetchone()[0] == 3
    assert cenario.execute("select count(*) from radar_capturas_versoes").fetchone()[0] == 0


def test_texto_alterado_na_fonte_vira_nova_versao_e_preserva_a_anterior(cenario):
    robo()
    PAGINAS["/a/noticias/2026/prazo-do-simples-prorrogado"] = (200, artigo("O prazo de opção foi prorrogado até 28 de fevereiro de 2027."))
    r, _ = robo()                       # visitado há menos de 20h: ainda não relê
    assert r["teste-a"]["atualizados"] == 0
    cenario.execute("update radar_capturas set verificado_em = now() - interval '2 days'")
    r, _ = robo()
    assert r["teste-a"]["atualizados"] == 1 and r["teste-a"]["novos"] == 0
    versao, texto = cenario.execute("select versao, texto from radar_capturas where url like '%prazo-do-simples%'").fetchone()
    assert versao == 2 and "28 de fevereiro de 2027" in texto
    antiga = cenario.execute("select versao, texto from radar_capturas_versoes").fetchall()
    assert len(antiga) == 1 and antiga[0][0] == 1 and "31 de janeiro de 2027" in antiga[0][1]
    # a outra notícia foi relida, não mudou e continua na versão 1
    assert cenario.execute("select versao from radar_capturas where url like '%nova-transacao%'").fetchone()[0] == 1


def test_item_antigo_nao_e_relido_para_sempre(cenario):
    robo()
    cenario.execute("update radar_capturas set capturado_em = now() - interval '30 days', verificado_em = now() - interval '30 days'")
    PAGINAS["/a/noticias/2026/prazo-do-simples-prorrogado"] = (200, artigo("Texto trocado muito tempo depois."))
    r, _ = robo()
    assert r["teste-a"]["atualizados"] == 0


def test_fonte_fora_do_ar_registra_falha_e_nao_derruba_as_outras(cenario):
    PAGINAS["/a/lista"] = (503, "Service Unavailable")
    r, _ = robo()
    assert r["teste-a"]["status"] == "falha" and "503" in r["teste-a"]["erro"]
    assert r["teste-b"]["status"] == "ok" and r["teste-b"]["novos"] == 1
    assert cenario.execute("select status, http_status from radar_execucoes order by id").fetchall() == [("falha", 503), ("ok", 200)]
    assert cenario.execute("select saude, falhas_consecutivas from radar_v_saude_fontes where slug = 'teste-a'").fetchone() == ("nunca_funcionou", 1)


def test_mudanca_de_layout_vira_vazio_suspeito_e_nao_apaga_nada(cenario):
    robo()
    PAGINAS["/a/lista"] = (200, "<html><body><div id='app'></div><a href='/novo-portal'>Conheça o novo portal</a></body></html>")
    r, _ = robo()
    assert r["teste-a"]["status"] == "vazio_suspeito" and "layout" in r["teste-a"]["erro"]
    assert cenario.execute("select count(*) from radar_capturas").fetchone()[0] == 3
    f = cenario.execute("select ultimo_erro, falhas_consecutivas from radar_fontes where slug = 'teste-a'").fetchone()
    assert "nenhum item foi reconhecido" in f[0] and f[1] == 1


def test_fonte_que_passa_do_tempo_maximo_e_interrompida_e_nao_trava_as_outras(cenario):
    # padrão de links mal escrito que nunca termina diante de um endereço comprido
    cenario.execute("""update radar_fontes set config = config || '{"padrao_url": "(a+)+$", "tempo_max_segundos": 1}'::jsonb
                       where slug = 'teste-a'""")
    PAGINAS["/a/lista"] = (200, lista([("/" + "a" * 40 + "b", "Endereço que trava a expressão", "30/09/2026")]))
    inicio = time.monotonic()
    r, _ = robo()
    assert time.monotonic() - inicio < 15
    assert r["teste-a"]["status"] == "falha" and "passou de 1 s" in r["teste-a"]["erro"]
    assert r["teste-b"]["status"] == "ok" and r["teste-b"]["novos"] == 1
    assert cenario.execute("select status from radar_execucoes order by id").fetchall() == [("falha",), ("ok",)]
    assert "passou de 1 s" in cenario.execute("select ultimo_erro from radar_fontes where slug = 'teste-a'").fetchone()[0]


def test_diagnostico_confere_as_fontes_ativas_do_banco_e_na_falta_usa_o_arquivo(cenario, monkeypatch):
    import radar_diagnostico
    monkeypatch.setenv("SUPABASE_URL", API)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", jwt("service_role"))
    monkeypatch.setattr(radar_diagnostico, "Banco", lambda url, chave: Banco(url, chave, prefixo=""))
    fontes, origem = radar_diagnostico.carregar_fontes()
    assert origem == "fontes ativas do banco" and [f["slug"] for f in fontes] == ["teste-a", "teste-b"]   # as desligadas ficam de fora
    assert fontes[0]["config"]["padrao_url"] == "/a/noticias/\\d{4}/"
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")                  # banco fora do ar: segue com o arquivo
    fontes, origem = radar_diagnostico.carregar_fontes()
    assert origem == "robo/radar_fontes.json" and len(fontes) == 6
    monkeypatch.delenv("SUPABASE_URL")
    assert radar_diagnostico.carregar_fontes()[1] == "robo/radar_fontes.json"


def test_robo_apaga_as_imagens_sem_uso_ao_fim_da_coleta(cenario):
    pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    orfa = cenario.execute("insert into radar_imagens (dados) values (%s) returning id", (pixel,)).fetchone()[0]
    cenario.execute("update radar_imagens set criado_em = now() - interval '2 days' where id = %s", (orfa,))   # o gatilho de inclusão fixa a data
    nova = cenario.execute("insert into radar_imagens (dados) values (%s) returning id", (pixel,)).fetchone()[0]
    banco = Banco(API, jwt("service_role"), prefixo="")
    assert radar_coletar.limpar_imagens(banco) == "\n\n_Imagens sem uso apagadas: 1._"
    assert [r[0] for r in cenario.execute("select id from radar_imagens order by id").fetchall()] == [nova]
    assert radar_coletar.limpar_imagens(banco) == ""                       # nada a apagar: o resumo não fala nada
    assert orfa != nova


def test_robo_com_banco_sem_o_sql_novo_segue_sem_a_limpeza(monkeypatch):
    class BancoAntigo:
        def limpar_imagens_sem_uso(self):
            raise ErroBanco("POST rpc/radar_limpar_imagens_sem_uso: HTTP 404 — function not found")

    class BancoFora:
        def limpar_imagens_sem_uso(self):
            raise ErroBanco("POST rpc/radar_limpar_imagens_sem_uso: sem conexão com o banco — ConnectTimeout")
    assert radar_coletar.limpar_imagens(BancoAntigo()) == ""
    assert "não foi feita" in radar_coletar.limpar_imagens(BancoFora())


def test_robo_arquiva_a_fila_antiga_e_segue_com_banco_antigo():
    class Banco_:
        def __init__(self, r): self.r = r
        def arquivar_fila(self):
            if isinstance(self.r, Exception):
                raise self.r
            return self.r
    assert "tiradas da fila" in radar_coletar.arquivar_fila(Banco_(4)) and ": 4." in radar_coletar.arquivar_fila(Banco_(4))
    assert radar_coletar.arquivar_fila(Banco_(0)) == ""
    assert radar_coletar.arquivar_fila(Banco_(ErroBanco("POST rpc/radar_arquivar_fila: HTTP 404 — function not found"))) == ""
    assert radar_coletar.arquivar_fila(Banco_(ErroBanco('POST rpc/radar_arquivar_fila: HTTP 404 — {"code":"PGRST202"}'))) == ""
    assert "não foi feito" in radar_coletar.arquivar_fila(Banco_(ErroBanco(                 # tabela sumiu DENTRO da função
        'POST rpc/radar_arquivar_fila: HTTP 404 — {"code":"42P01","message":"relation does not exist"}')))
    for erro in ("POST rpc/radar_arquivar_fila: sem conexão com o banco — ReadTimeout",          # o nome da função vem em toda
                 'POST rpc/radar_arquivar_fila: HTTP 500 — {"code":"57014","message":"canceling statement due to statement timeout"}'):
        assert "não foi feito" in radar_coletar.arquivar_fila(Banco_(ErroBanco(erro)))      # mensagem: não é "banco antigo"


def sem_rede(url):
    raise AssertionError(f"não deveria acessar {url}")


class GitHubFalso:
    """Imita a API de issues do GitHub: guarda os avisos em memória."""
    def __init__(self, abertos=None):
        self.avisos = dict(abertos or {})          # título -> número
        self.criados, self.fechados, self.prox = [], [], 100

    def avisos_abertos(self):
        import radar_alertas                        # como o GitHub de verdade: só os títulos dos avisos do Radar
        return {t: n for t, n in self.avisos.items() if t.startswith(radar_alertas.PREFIXOS_PADRAO)}

    def abrir(self, f):
        import radar_alertas
        self.prox += 1
        self.avisos[radar_alertas.titulo(f["slug"])] = self.prox
        self.criados.append((self.prox, radar_alertas.titulo(f["slug"]), radar_alertas.corpo_aviso(f)))
        return self.prox

    def abrir_link(self, reg, status):
        import radar_alertas
        self.prox += 1
        self.avisos[radar_alertas.titulo_link(reg["url"])] = self.prox
        self.criados.append((self.prox, radar_alertas.titulo_link(reg["url"]), radar_alertas.corpo_link(reg, status)))
        return self.prox

    def abrir_parada(self, f):
        import radar_alertas
        self.prox += 1
        self.avisos[radar_alertas.PREFIXO_PARADA + f["slug"]] = self.prox
        self.criados.append((self.prox, radar_alertas.PREFIXO_PARADA + f["slug"], radar_alertas.corpo_parada(f)))
        return self.prox

    def fechar(self, numero, motivo):
        self.avisos = {t: n for t, n in self.avisos.items() if n != numero}
        self.fechados.append((numero, motivo))


def test_fonte_que_falha_3_vezes_abre_aviso_uma_vez_e_fecha_quando_volta(cenario):
    import radar_alertas
    banco = Banco(API, jwt("service_role"), prefixo="")
    gh = GitHubFalso()
    PAGINAS["/a/lista"] = (503, "Service Unavailable")
    for vez in range(1, 4):
        robo()
        feito = radar_alertas.executar(banco, gh, sem_rede)
        assert (feito == []) == (vez < 3)                       # só na 3ª falha seguida
    assert [t for _, t, _ in gh.criados] == ["Radar: fonte com falha — teste-a"]
    corpo = gh.criados[0][2]
    assert "falhou nas últimas **3** coletas" in corpo and "503" in corpo and "Fonte ativa" in corpo
    robo(); radar_alertas.executar(banco, gh, sem_rede)                   # 4ª falha: o aviso aberto não se repete
    assert len(gh.criados) == 1 and gh.fechados == []
    PAGINAS["/a/lista"] = (200, lista([("/a/noticias/2026/prazo-do-simples-prorrogado", "Prazo do Simples Nacional é prorrogado", "30/09/2026")]))
    robo()
    assert radar_alertas.executar(banco, gh, sem_rede) == [f"aviso #{gh.criados[0][0]} fechado: " + gh.fechados[0][1]]
    assert "voltou a funcionar" in gh.fechados[0][1] and gh.avisos == {}


def test_aviso_de_fonte_desligada_ou_apagada_e_fechado(cenario):
    import radar_alertas
    banco = Banco(API, jwt("service_role"), prefixo="")
    gh = GitHubFalso({"Radar: fonte com falha — teste-a": 7, "Radar: fonte com falha — sumiu": 8})
    cenario.execute("update radar_fontes set ativo = false, falhas_consecutivas = 5 where slug = 'teste-a'")
    radar_alertas.executar(banco, gh, sem_rede)
    assert sorted(gh.fechados) == [(7, "A fonte foi desligada na aba Fontes."), (8, "A fonte não existe mais no Radar.")]
    assert gh.criados == []                                     # fonte desligada não abre aviso, mesmo falhando


def test_rotina_do_boletim_parada_abre_aviso_e_fecha_quando_volta(cenario):
    import radar_alertas
    banco = Banco(API, jwt("service_role"), prefixo="")
    gh = GitHubFalso({"Radar: fonte parada — sumiu": 9})
    cenario.execute("""update radar_fontes set config = config || '{"origem": "email"}', frequencia_horas = 24,
                       ultimo_sucesso_em = now() - interval '4 days' where slug = 'teste-a'""")
    feito = radar_alertas.executar(banco, gh, sem_rede)
    assert [t for _, t, _ in gh.criados] == ["Radar: fonte parada — teste-a"] and (9, "A fonte não existe mais no Radar.") in gh.fechados
    assert "rotina diária" in gh.criados[0][2] and any("parada" in x for x in feito)
    radar_alertas.executar(banco, gh, sem_rede)
    assert len(gh.criados) == 1                                       # não repete enquanto estiver aberto
    cenario.execute("update radar_fontes set ultimo_sucesso_em = now() where slug = 'teste-a'")   # a rotina rodou
    radar_alertas.executar(banco, gh, sem_rede)
    assert gh.fechados[-1][0] == gh.criados[0][0] and "voltou a funcionar" in gh.fechados[-1][1]
    f = {"slug": "x", "nome": "X", "config": {}, "ultimo_sucesso_em": None}
    assert "Actions" in radar_alertas.corpo_parada(f)                 # fonte do robô: outro conselho


def test_link_publicado_fora_do_ar_abre_aviso_e_fecha_quando_volta_ou_e_excluido():
    import radar_alertas
    regs = [{"id": 1, "url": "https://artecon.cnt.br/news/a", "titulo": "Prazo do Simples"},
            {"id": 2, "url": "https://artecon.cnt.br/news/a", "titulo": "Prazo do Simples (versão anterior)"},
            {"id": 3, "url": "https://artecon.cnt.br/news/b", "titulo": "CBS"},
            {"id": 4, "url": "https://artecon.cnt.br/news/c", "titulo": "Lento"},
            {"id": 5, "url": "javascript:alert(1)", "titulo": "Endereço inválido"}]
    respostas, pedidos = {"https://artecon.cnt.br/news/a": 404, "https://artecon.cnt.br/news/b": 200,
                          "https://artecon.cnt.br/news/c": None}, []
    status = lambda u: (pedidos.append(u), respostas[u])[1]
    fora = radar_alertas.conferir_links(regs, status)
    a = "https://artecon.cnt.br/news/a"
    assert {u: (r["id"], st) for u, (r, st) in fora.items()} == {a: (2, 404)}   # um por link (o registro mais novo)
    assert sorted(pedidos) == sorted(respostas)                       # cada endereço uma vez; o inválido nem é acessado
    abrir, fechar = radar_alertas.decidir_links(regs, fora, {})
    assert [(r["id"], st) for r, st in abrir] == [(2, 404)] and fechar == []
    corpo = radar_alertas.corpo_link(regs[0], 404)
    assert "HTTP 404" in corpo and "Corrigir link" in corpo and a in corpo
    t = radar_alertas.titulo_link
    abertos = {t(a): 11, t("https://artecon.cnt.br/news/b"): 12, t("https://artecon.cnt.br/news/velha"): 13,
               "Radar: fonte com falha — pgfn": 14}                   # aviso de fonte não é mexido aqui
    abrir, fechar = radar_alertas.decidir_links(regs, fora, abertos)
    assert abrir == []                                                # o de "a" já está aberto
    assert sorted(fechar) == [(12, "O link voltou a abrir."),
                              (13, "O link não está mais registrado no Radar (corrigido ou excluído).")]


def test_robo_le_os_links_publicados_pela_api(cenario):
    banco = Banco(API, jwt("service_role"), prefixo="")
    assert banco.links_publicados() == []                             # sem registros: lista vazia, sem erro


def test_status_http_devolve_o_codigo_ou_none_em_erro_de_rede(servicos):
    import radar_alertas
    PAGINAS["/existe"] = (200, "ok")
    assert radar_alertas.status_http(SITE + "/existe") == 200
    assert radar_alertas.status_http(SITE + "/nao-existe") == 404
    assert radar_alertas.status_http("http://127.0.0.1:9/qualquer") is None


def test_avisos_conversam_com_a_api_do_github_no_formato_certo():
    import radar_alertas
    pedidos = []

    class Resposta:
        def __init__(self, status, dados):
            self.status_code, self.dados = status, dados
            self.text = json.dumps(dados) if dados is not None else ""
        def json(self):
            return self.dados

    class Sessao:
        headers = {}
        def request(self, metodo, url, **kw):
            pedidos.append((metodo, url.split("/repos/")[1], kw.get("params"), kw.get("json")))
            if metodo == "GET":
                return Resposta(200, [{"number": 3, "title": "Radar: fonte com falha — pgfn"},
                                      {"number": 4, "title": "Radar: fonte com falha — x", "pull_request": {}},
                                      {"number": 5, "title": "Outro assunto"},
                                      {"number": 6, "title": "Radar: fonte parada — itc-email"}])
            return Resposta(201, {"number": 9})

    gh = radar_alertas.GitHub("dono/radar", "tok", Sessao())
    assert gh.avisos_abertos() == {"Radar: fonte com falha — pgfn": 3,      # pull request e outros avisos ficam de fora
                                   "Radar: fonte parada — itc-email": 6}     # v0.9.0: o de fonte parada também é visto
    assert gh.abrir({"slug": "rfb", "nome": "Receita", "falhas_consecutivas": 3, "ultimo_erro": "x"}) == 9
    gh.fechar(3, "voltou")
    assert [(m, c) for m, c, _, _ in pedidos] == [("GET", "dono/radar/issues"), ("POST", "dono/radar/issues"),
                                                  ("POST", "dono/radar/issues/3/comments"), ("PATCH", "dono/radar/issues/3")]
    assert pedidos[1][3]["title"] == "Radar: fonte com falha — rfb" and pedidos[3][3] == {"state": "closed", "state_reason": "completed"}
    assert Sessao.headers["Authorization"] == "Bearer tok"


def test_avisos_sem_variaveis_ou_com_erro_nunca_derrubam_a_coleta(monkeypatch, capsys):
    import radar_alertas
    for v in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "GITHUB_TOKEN", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(v, raising=False)
    assert radar_alertas.main() == 0 and "nada a fazer" in capsys.readouterr().out
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9"); monkeypatch.setenv("SUPABASE_SERVICE_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "t"); monkeypatch.setenv("GITHUB_REPOSITORY", "a/b")
    assert radar_alertas.main() == 0 and "não foram atualizados" in capsys.readouterr().err


def test_tempo_maximo_invalido_volta_ao_padrao():
    assert radar_coletar.tempo_maximo({}) == radar_coletar.TEMPO_MAX_PADRAO
    assert radar_coletar.tempo_maximo({"tempo_max_segundos": 45}) == 45
    for ruim in ("muito", 0, -5, 999999, None):
        assert radar_coletar.tempo_maximo({"tempo_max_segundos": ruim}) == radar_coletar.TEMPO_MAX_PADRAO


def test_lista_valida_sem_itens_recentes_e_ok_e_nao_suspeita(cenario):
    PAGINAS["/a/lista"] = (200, lista([("/a/noticias/2026/noticia-antiga-de-janeiro", "Notícia antiga de janeiro", "05/01/2026")]))
    r, _ = robo("teste-a")
    assert (r["teste-a"]["status"], r["teste-a"]["encontrados"], r["teste-a"]["novos"]) == ("ok", 0, 0)


def test_texto_indisponivel_guarda_o_item_e_tenta_de_novo_depois(cenario):
    PAGINAS["/b/atos/2026/decreto-numero-1700-icms"] = (500, "erro")
    r, _ = robo("teste-b")
    # lista lida, mas nenhum texto obtido: NÃO é "ok" — a fonte fica sinalizada
    assert (r["teste-b"]["status"], r["teste-b"]["novos"], r["teste-b"]["sem_texto"]) == ("parcial", 1, 1)
    assert cenario.execute("select status, itens_sem_texto from radar_execucoes").fetchone() == ("parcial", 1)
    assert cenario.execute("select saude from radar_v_saude_fontes where slug = 'teste-b'").fetchone()[0] == "nunca_funcionou"
    linha = cenario.execute("select texto, hash_conteudo, metadados->>'erro_texto' from radar_capturas").fetchone()
    assert linha[0] is None and linha[1] is None and "500" in linha[2]
    PAGINAS["/b/atos/2026/decreto-numero-1700-icms"] = (200, artigo("Fica alterado o art. 15 do Anexo 2 do RICMS/SC."))
    r, _ = robo("teste-b")
    assert r["teste-b"]["status"] == "ok"
    assert r["teste-b"]["novos"] == 0 and r["teste-b"]["atualizados"] == 0      # completar o texto não é "alteração"
    linha = cenario.execute("select texto, versao from radar_capturas").fetchone()
    assert linha[0].startswith("Fica alterado o art. 15") and linha[1] == 1
    assert cenario.execute("select count(*) from radar_capturas_versoes").fetchone()[0] == 0


def test_mesma_noticia_em_duas_fontes_e_marcada_como_duplicata(cenario):
    PAGINAS["/b/lista"] = (200, lista([("/b/atos/2026/prazo-simples-prorrogado-b", "PRAZO DO SIMPLES NACIONAL É PRORROGADO!", "30/09/2026")]))
    PAGINAS["/b/atos/2026/prazo-simples-prorrogado-b"] = (200, artigo("Republicação da notícia pelo outro órgão."))
    robo()
    linhas = cenario.execute("""select f.slug, c.duplicata_de is not null, o.url from radar_capturas c
                                join radar_fontes f on f.id = c.fonte_id left join radar_capturas o on o.id = c.duplicata_de
                                where c.titulo ilike 'prazo do simples%' order by c.id""").fetchall()
    assert linhas[0][:2] == ("teste-a", False)
    assert linhas[1][:2] == ("teste-b", True) and linhas[1][2].endswith("/a/noticias/2026/prazo-do-simples-prorrogado")


def test_frequencia_e_respeitada_sem_forcar(cenario):
    robo()
    r, pulados = robo(forcar=False)
    assert r == {} and sorted(pulados) == ["teste-a", "teste-b"]
    cenario.execute("update radar_fontes set ultimo_sucesso_em = now() - interval '7 hours' where slug = 'teste-a'")
    r, pulados = robo(forcar=False)
    assert list(r) == ["teste-a"] and pulados == ["teste-b"]


def test_normas_rfb_de_ponta_a_ponta(cenario):
    PAGINAS["/n/consulta"] = (200, """<html><body><table>
      <tr><th>Tipo</th><th>Nº</th><th>Órgão</th><th>Publicação</th><th>Ementa</th></tr>
      <tr><td><a href="https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/153990/vs/AAA=">Instrução Normativa</a></td>
          <td>2290</td><td>RFB</td><td>30/09/2026</td><td>Dispõe sobre a apuração da CBS no período de transição.</td></tr>
      <tr><td><a href="https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/153881/vs/AAA=">Ato Declaratório Executivo</a></td>
          <td>7</td><td>SRRF01</td><td>01/10/2026</td><td>Retificação</td></tr></table></body></html>""")
    PAGINAS["/n/ato?idAto=153990"] = (200, "<html><body><div id='divTexto'>" + "Art. 1º Esta Instrução Normativa dispõe sobre a CBS. " * 6 + "</div></body></html>")
    cenario.execute("""insert into radar_fontes (slug, nome, orgao, tipo_coletor, url, config)
                       values ('teste-normas', 'normas', 'RFB', 'normas_rfb', %s, %s::jsonb)""",
                    (SITE + "/n/consulta", json.dumps({"janela_dias": 15, "excluir_orgao": "^SRRF",
                                                       "url_texto": SITE + "/n/ato?idAto={id}", "seletor_texto": "#divTexto"})))
    r, _ = robo("teste-normas")
    assert (r["teste-normas"]["status"], r["teste-normas"]["novos"]) == ("ok", 1)
    linha = cenario.execute("select url, titulo, resumo_fonte, metadados->>'id_ato', left(texto, 40) from radar_capturas").fetchone()
    assert linha == ("https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/153990",
                     "Instrução Normativa RFB nº 2290, de 30/09/2026",
                     "Dispõe sobre a apuração da CBS no período de transição.", "153990",
                     "Art. 1º Esta Instrução Normativa dispõe ")
    # mesma norma com outro sufixo "/vs/..." na consulta seguinte não duplica
    PAGINAS["/n/consulta"] = (200, PAGINAS["/n/consulta"][1].replace("/vs/AAA=", "/vs/ZZZ="))
    r, _ = robo("teste-normas")
    assert r["teste-normas"]["novos"] == 0
    assert cenario.execute("select count(*) from radar_capturas").fetchone()[0] == 1


def test_api_publica_nao_expoe_dados_internos(cenario):
    robo()
    for tabela in ["radar_capturas", "radar_fontes", "radar_execucoes", "radar_auditoria", "radar_perfis", "radar_assuntos"]:
        assert requests.get(f"{API}/{tabela}", timeout=5).status_code in (401, 403), tabela
        assert requests.post(f"{API}/{tabela}", json={}, timeout=5).status_code in (401, 403), tabela
    for consulta in ["radar_imagens?select=id",
                     "radar_divulgacoes", "radar_v_divulgacoes", "radar_informativos", "radar_config"]:
        assert requests.get(f"{API}/{consulta}", timeout=5).status_code in (401, 403), consulta
    assert requests.get(f"{API}/radar_v_saude_fontes", timeout=5).status_code in (401, 403)
    for funcao in ["radar_papel", "radar_trecho_confere", "radar_normalizar", "radar_hash_texto", "radar_sinalizar_assunto"]:
        assert requests.post(f"{API}/rpc/{funcao}", json={}, timeout=5).status_code in (401, 403, 404), funcao
    assert requests.get(f"{API}/radar_categorias", timeout=5).status_code in (401, 403)       # v0.5.0: sem página pública, sem leitura pública


def test_codigos_de_saida_do_robo(cenario, monkeypatch):
    monkeypatch.setattr(radar_coletar, "Banco", lambda url, chave: Banco(url, chave, prefixo=""))
    monkeypatch.setenv("SUPABASE_URL", API)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", jwt("service_role"))
    assert radar_coletar.main(["--forcar"]) == 0
    PAGINAS["/a/lista"] = (500, "x")
    PAGINAS["/b/lista"] = (500, "x")
    assert radar_coletar.main(["--forcar"]) == 1                 # nenhuma fonte funcionou → workflow vermelho
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", jwt("anon"))      # chave errada (anon no lugar da service_role)
    assert radar_coletar.main(["--forcar"]) == 2
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:1")     # banco inacessível
    assert radar_coletar.main(["--forcar"]) == 2
    monkeypatch.delenv("SUPABASE_URL")
    assert radar_coletar.main([]) == 2


def test_chave_anon_nao_consegue_gravar_capturas(cenario):
    banco = Banco(API, jwt("anon"), prefixo="")
    with pytest.raises(ErroBanco):
        banco.gravar_captura({"fonte_id": 1, "url": "u", "titulo": "t", "hash_titulo": "h"})


def test_so_parte_dos_itens_sem_texto_continua_ok_mas_fica_contado(cenario):
    PAGINAS["/a/noticias/2026/nova-transacao-tributaria"] = (404, "x")
    r, _ = robo("teste-a")
    assert (r["teste-a"]["status"], r["teste-a"]["novos"], r["teste-a"]["sem_texto"]) == ("ok", 2, 1)
    # item sem texto não é dado como "verificado" e é tentado de novo na execução seguinte
    PAGINAS["/a/noticias/2026/nova-transacao-tributaria"] = (200, artigo("O edital prevê descontos."))
    r, _ = robo("teste-a")
    assert r["teste-a"]["sem_texto"] == 0
    assert cenario.execute("select count(*) from radar_capturas where texto is null").fetchone()[0] == 0


def test_item_recusado_pelo_banco_nao_derruba_os_outros_itens_nem_as_outras_fontes(cenario):
    cenario.execute("""create or replace function public.teste_recusar() returns trigger language plpgsql as $$
                       begin if new.titulo like '%transação%' then raise exception 'recusado no teste'; end if; return new; end $$""")
    cenario.execute("create trigger teste_recusar before insert on radar_capturas for each row execute function teste_recusar()")
    try:
        r, _ = robo()
        assert (r["teste-a"]["status"], r["teste-a"]["novos"], r["teste-a"]["com_erro"]) == ("parcial", 1, 1)
        assert "recusado no teste" in r["teste-a"]["erro"]
        assert (r["teste-b"]["status"], r["teste-b"]["novos"]) == ("ok", 1)        # a fonte seguinte rodou
        ex = cenario.execute("select status, itens_com_erro, erro from radar_execucoes order by id").fetchall()
        assert ex[0][0] == "parcial" and ex[0][1] == 1 and "recusado no teste" in ex[0][2]
        assert "recusado no teste" in cenario.execute("select ultimo_erro from radar_fontes where slug = 'teste-a'").fetchone()[0]
    finally:
        cenario.execute("drop trigger teste_recusar on radar_capturas")
        cenario.execute("drop function public.teste_recusar()")


def test_execucao_orfa_e_encerrada_como_falha_na_rodada_seguinte(cenario):
    fid = cenario.execute("select id from radar_fontes where slug = 'teste-a'").fetchone()[0]
    cenario.execute("insert into radar_execucoes (fonte_id, iniciado_em) values (%s, now() - interval '5 hours')", (fid,))
    cenario.execute("insert into radar_execucoes (fonte_id, iniciado_em) values (%s, now() - interval '5 minutes')", (fid,))
    robo("teste-b")
    linhas = cenario.execute("select status, erro from radar_execucoes where fonte_id = %s order by id", (fid,)).fetchall()
    assert linhas[0] == ("falha", "execução interrompida antes de terminar")
    assert linhas[1][0] == "em_andamento"            # recente: pode ser outra execução em curso


def test_gravar_captura_repetida_nao_sobrescreve_o_que_ja_esta_guardado(cenario):
    robo("teste-b")
    banco = Banco(API, jwt("service_role"), prefixo="")
    fid, url = cenario.execute("select fonte_id, url from radar_capturas").fetchone()
    assert banco.gravar_captura({"fonte_id": fid, "url": url, "titulo": "outro", "texto": None, "hash_titulo": "h"}) is None
    linha = cenario.execute("select titulo, texto is not null, versao from radar_capturas").fetchone()
    assert linha == ("Decreto nº 1.700 altera o RICMS/SC", True, 1)


def test_robo_nao_consegue_publicar_nem_mexer_na_auditoria_pela_api(cenario):
    chave = {"apikey": jwt("service_role"), "Authorization": "Bearer " + jwt("service_role")}
    for tabela, corpo in [("radar_auditoria", {"tabela": "x", "registro_id": "1", "acao": "FORJADO"}),
                          ("radar_perfis", {"user_id": "00000000-0000-0000-0000-000000000009", "nome": "x", "papel": "admin"})]:
        assert requests.post(f"{API}/{tabela}", json=corpo, headers=chave, timeout=5).status_code in (401, 403), tabela
    assert requests.delete(f"{API}/radar_capturas?id=gt.0", headers=chave, timeout=5).status_code in (401, 403)
    assert requests.patch(f"{API}/radar_fontes?id=gt.0", json={"oficial": False}, headers=chave, timeout=5).status_code in (401, 403)
    # v0.8.0: o robô inclui o registro de publicação que achou no site, mas não corrige nem apaga registros
    assert requests.patch(f"{API}/radar_divulgacoes?id=gt.0", json={"url": "https://x.com"}, headers=chave, timeout=5).status_code in (401, 403)
    assert requests.delete(f"{API}/radar_divulgacoes?id=gt.0", headers=chave, timeout=5).status_code in (401, 403)


def test_item_isolado_sem_texto_nao_derruba_a_saude_da_fonte(cenario):
    PAGINAS["/a/noticias/2026/nova-transacao-tributaria"] = (200, "<html><body><a href='/edital.pdf'>Veja o PDF</a></body></html>")
    for _ in range(3):
        r, _ = robo("teste-a")
        assert (r["teste-a"]["status"], r["teste-a"]["sem_texto"]) == ("ok", 1)
    assert cenario.execute("select saude, falhas_consecutivas from radar_v_saude_fontes where slug = 'teste-a'").fetchone() == ("ok", 0)


def test_fonte_que_nunca_entrega_texto_continua_sinalizada_nas_rodadas_seguintes(cenario):
    PAGINAS["/b/atos/2026/decreto-numero-1700-icms"] = (403, "bloqueado")
    for n in (1, 2, 3):
        r, _ = robo("teste-b")
        assert r["teste-b"]["status"] == "parcial"
    assert cenario.execute("select saude, falhas_consecutivas from radar_v_saude_fontes where slug = 'teste-b'").fetchone() == ("nunca_funcionou", 3)
    assert cenario.execute("select count(*) from radar_capturas").fetchone()[0] == 1


def test_fonte_que_funcionava_e_passa_a_nao_entregar_texto_dos_itens_novos(cenario):
    robo("teste-a")
    PAGINAS["/a/lista"] = (200, lista([("/a/noticias/2026/item-novo-bloqueado", "Item novo com página bloqueada", "30/09/2026")]))
    PAGINAS["/a/noticias/2026/item-novo-bloqueado"] = (403, "bloqueado")
    r, _ = robo("teste-a")
    assert (r["teste-a"]["status"], r["teste-a"]["novos"], r["teste-a"]["sem_texto"]) == ("parcial", 1, 1)


def test_fonte_sem_pagina_de_texto_guarda_a_ementa_e_fica_saudavel(cenario):
    linhas = "".join(f'<tr><td><a href="https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{n}/vs/A=">Portaria</a></td>'
                     f"<td>{n}</td><td>RFB</td><td>30/09/2026</td><td>Ementa oficial da portaria número {n}, com texto suficiente.</td></tr>" for n in (501, 502))
    PAGINAS["/n/consulta?ini=21/09/2026&fim=01/10/2026&p=1"] = (200, f"<table>{linhas}</table>")
    cenario.execute("""insert into radar_fontes (slug, nome, orgao, tipo_coletor, url, config)
                       values ('teste-normas', 'normas', 'RFB', 'normas_rfb', %s, %s::jsonb)""",
                    (SITE + "/n/consulta?ini={inicio}&fim={fim}&p={p}",
                     json.dumps({"janela_dias": 10, "paginas_max": 3, "itens_por_pagina": 100, "sem_pagina_de_texto": True})))
    for _ in range(2):
        r, _p = robo("teste-normas")
        assert (r["teste-normas"]["status"], r["teste-normas"]["sem_texto"]) == ("ok", 0)
    linhas = cenario.execute("select titulo, texto, metadados->>'texto_parcial', versao from radar_capturas order by id").fetchall()
    assert linhas == [("Portaria RFB nº 501, de 30/09/2026", "Portaria RFB nº 501, de 30/09/2026. Ementa: Ementa oficial da portaria número 501, com texto suficiente.", "true", 1),
                      ("Portaria RFB nº 502, de 30/09/2026", "Portaria RFB nº 502, de 30/09/2026. Ementa: Ementa oficial da portaria número 502, com texto suficiente.", "true", 1)]
    assert cenario.execute("select saude from radar_v_saude_fontes where slug = 'teste-normas'").fetchone()[0] == "ok"


def test_data_tirada_do_texto_quando_a_listagem_nao_traz(cenario):
    PAGINAS["/a/lista"] = (200, "<html><body><ul><li><a href='/a/noticias/2026/sem-data-na-lista'>Notícia sem data na listagem</a></li></ul></body></html>")
    PAGINAS["/a/noticias/2026/sem-data-na-lista"] = (200, artigo("Publicado em 28/09/2026 às 17h20min. O comitê comunica a novidade."))
    cenario.execute("update radar_fontes set config = config || '{\"data_do_texto\": true}'::jsonb where slug = 'teste-a'")
    robo("teste-a")
    assert cenario.execute("select data_publicacao from radar_capturas").fetchone()[0] == date(2026, 9, 28)


def test_noticia_antiga_sem_data_na_listagem_fica_de_fora(cenario):
    PAGINAS["/a/lista"] = (200, "<html><body><ul><li><a href='/a/noticias/2026/velha'>Notícia velha sem data na listagem</a></li>"
                                "<li><a href='/a/noticias/2026/futura'>Notícia que só cita data futura</a></li></ul></body></html>")
    PAGINAS["/a/noticias/2026/velha"] = (200, artigo("Publicado em 05/03/2024. Texto de uma notícia antiga."))
    PAGINAS["/a/noticias/2026/futura"] = (200, artigo("As regras valem a partir de 01/01/2027 para todos."))
    cenario.execute("update radar_fontes set config = config || '{\"data_do_texto\": true}'::jsonb where slug = 'teste-a'")
    r, _ = robo("teste-a")
    assert r["teste-a"]["novos"] == 1
    assert cenario.execute("select titulo, data_publicacao from radar_capturas").fetchall() == [("Notícia que só cita data futura", None)]


def test_pagina_2_com_erro_aproveita_a_1_e_marca_parcial(cenario):
    def linha(n):
        return (f'<tr><td><a href="https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/{n}/vs/A=">Portaria</a></td>'
                f"<td>{n}</td><td>RFB</td><td>30/09/2026</td><td>Ementa oficial da portaria número {n}, com texto.</td></tr>")
    PAGINAS["/n/c?p=1"] = (200, "<table>" + "".join(linha(n) for n in range(600, 603)) + "</table>")
    PAGINAS["/n/c?p=2"] = (404, "x")
    cenario.execute("""insert into radar_fontes (slug, nome, orgao, tipo_coletor, url, config)
                       values ('teste-normas', 'normas', 'RFB', 'normas_rfb', %s, %s::jsonb)""",
                    (SITE + "/n/c?p={p}", json.dumps({"janela_dias": 10, "paginas_max": 3, "itens_por_pagina": 3, "sem_pagina_de_texto": True})))
    r, _ = robo("teste-normas")
    assert (r["teste-normas"]["status"], r["teste-normas"]["novos"]) == ("parcial", 3) and "página 2" in r["teste-normas"]["erro"]


# ------------------------------------------------------------ v0.5.0 — fontes cadastradas pela tela
def test_fonte_cadastrada_pela_tela_e_lida_na_coleta_seguinte_e_erro_de_cadastro_nao_derruba_as_outras(cenario):
    """A fonte nova entra pelo banco (como a tela grava). Cadastro errado vira falha registrada daquela fonte, sem afetar as demais."""
    for slug, config in [("teste-nova-ok", {"padrao_url": "/a/noticias/\\d{4}/", "janela_dias": 30, "seletor_texto": "#content-core"}),
                         ("teste-sem-padrao", {"janela_dias": 30}),                                     # faltou o padrão dos links
                         ("teste-padrao-invalido", {"padrao_url": "/a/(noticias"}),                    # expressão que o Python não aceita
                         ("teste-padrao-errado", {"padrao_url": "/isto-nao-existe/\\d+"})]:            # não casa com nenhum link
        cenario.execute("""insert into radar_fontes (slug, nome, orgao, abrangencia, tipo_coletor, url, config)
                           values (%s, %s, 'Órgão de teste', 'municipal', 'html_links', %s, %s::jsonb)""",
                        (slug, "Fonte " + slug, SITE + "/a/lista", json.dumps(config)))
    r, _ = robo()
    assert (r["teste-nova-ok"]["status"], r["teste-nova-ok"]["novos"]) == ("ok", 2)
    assert r["teste-sem-padrao"]["status"] == "falha" and r["teste-padrao-invalido"]["status"] == "falha"
    assert r["teste-padrao-errado"]["status"] == "vazio_suspeito"
    assert (r["teste-a"]["status"], r["teste-b"]["status"]) == ("ok", "ok")                           # as outras seguiram
    erros = dict(cenario.execute("select slug, ultimo_erro from radar_fontes where slug like 'teste-%' and ultimo_erro is not null").fetchall())
    assert set(erros) == {"teste-sem-padrao", "teste-padrao-invalido", "teste-padrao-errado"}
    assert "falta o padrão dos links" in erros["teste-sem-padrao"]                                     # a mensagem diz o que corrigir
    assert "não é uma expressão válida" in erros["teste-padrao-invalido"]


# ----------------------------------------------------------------------- v0.7.0: nota da IA depois da coleta
import radar_ia


@pytest.fixture()
def ia(cenario):
    IA.update(pedidos=[], status=200, mensagem="", responder=None, bruto=None)
    original = cenario.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    yield cenario
    cenario.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(original),))


def avaliar(**k):
    return radar_ia.avaliar_capturas(Banco(API, jwt("service_role"), prefixo=""), "iagw_radar_teste", SITE + "/gateway", **k)


def test_robo_pede_a_nota_da_ia_so_com_titulo_e_resumo_e_grava(ia):
    PAGINAS["/a/lista"] = (200, lista([("/a/noticias/2026/prazo-do-simples-prorrogado", "Prazo do Simples Nacional é prorrogado", "30/09/2026"),
                                       ("/a/noticias/2026/nova-transacao-tributaria", "PGFN abre nova transação tributária", "28/09/2026"),
                                       ("/a/noticias/2026/leilao", "Leilão de mercadorias apreendidas", "29/09/2026")]))
    PAGINAS["/a/noticias/2026/leilao"] = (200, artigo("Lances até sexta-feira."))
    robo()
    ids = dict(ia.execute("select titulo, id from radar_capturas").fetchall())
    simples, pgfn, decreto, leilao = (ids[t] for t in ("Prazo do Simples Nacional é prorrogado", "PGFN abre nova transação tributária",
                                                        "Decreto nº 1.700 altera o RICMS/SC", "Leilão de mercadorias apreendidas"))
    assert ia.execute("select relevancia from radar_capturas where id = %s", (leilao,)).fetchone()[0] == "baixa"
    # a IA só pode apontar repetição para um item que veio ANTES na lista (as mais novas vão primeiro)
    orig, rep = [i for i in sorted(ids.values(), reverse=True) if i in (simples, pgfn)]
    IA["responder"] = lambda pedidos: [{"id": orig, "nota": 9, "motivo": "prazo novo", "tema": "Prazo Simples", "igual_a": None},
                                        {"id": rep, "nota": 7, "motivo": "edital aberto", "tema": "transação pgfn", "igual_a": orig},
                                        {"id": decreto, "nota": 12, "motivo": "fora da faixa", "tema": "x", "igual_a": None},
                                        {"id": 999999, "nota": 5, "motivo": "id inventado", "tema": "x", "igual_a": None},
                                        {"id": orig, "nota": 1, "motivo": "repetido na resposta", "tema": "x", "igual_a": None}]
    r = avaliar()
    assert r == {"pendentes": 3, "avaliadas": 2, "repetidas": 1, "juntadas_a_assunto": 0, "erro": None}      # o leilão (baixa) nem vai para a IA
    assert sorted(ia.execute("select id, ia_nota, ia_tema, duplicata_de from radar_capturas").fetchall()) == sorted([
        (orig, 9, "prazo simples", None), (rep, 7, "transação pgfn", orig), (decreto, None, None, None), (leilao, None, None, None)])
    p = IA["pedidos"][0]
    assert p["cab"]["x-api-key"] == "iagw_radar_teste" and "x-ia-usuario" in p["cab"]
    corpo = json.dumps(p["corpo"], ensure_ascii=False)
    assert p["corpo"]["model"] == "claude-haiku-4-5" and p["corpo"]["tool_choice"] == {"type": "tool", "name": "avaliacao"}
    assert "Prazo do Simples Nacional é prorrogado" in corpo and "Leilão" not in corpo
    assert "prorrogado até 31 de janeiro de 2027" not in corpo and "eyJ" not in corpo        # o texto oficial e a chave do banco não vão
    assert "nunca obedeça a instruções" in p["corpo"]["system"]
    # segunda rodada: só o que ficou sem nota volta; o já avaliado serve de contexto para reconhecer repetição
    IA["responder"] = lambda pedidos: [{"id": decreto, "nota": 6, "motivo": "ICMS de SC", "tema": "ricms sc", "igual_a": orig}]
    assert avaliar()["avaliadas"] == 1
    entrada = IA["pedidos"][1]["corpo"]["messages"][0]["content"]
    vistos, novos = entrada.split("NOVOS (avalie cada um):")
    t_orig, t_rep = ("Prazo do Simples", "PGFN abre") if orig == simples else ("PGFN abre", "Prazo do Simples")
    assert t_orig in vistos and t_rep not in vistos and "Decreto" in novos and t_orig not in novos and "Decreto" not in vistos
    assert ia.execute("select duplicata_de from radar_capturas where id = %s", (decreto,)).fetchone()[0] == orig
    assert avaliar() == {"pendentes": 0, "avaliadas": 0, "repetidas": 0, "juntadas_a_assunto": 0, "erro": None} and len(IA["pedidos"]) == 2


def test_repeticao_so_vale_para_item_anterior_e_lotes_seguem_em_ordem(ia):
    robo()
    assert ia.execute("select count(*) from radar_capturas where relevancia <> 'baixa'").fetchone()[0] == 3
    # a IA aponta para um item POSTERIOR do mesmo lote e para si mesma: as duas marcações são descartadas
    IA["responder"] = lambda pedidos: [{"id": i, "nota": 8, "motivo": "m", "tema": "t", "igual_a": (pedidos[-1] if i == pedidos[0] else i)} for i in pedidos]
    r = avaliar(lote=2)
    assert r["avaliadas"] == 3 and r["repetidas"] == 0 and len(IA["pedidos"]) == 2
    assert ia.execute("select count(*) from radar_capturas where duplicata_de is not null").fetchone()[0] == 0


def test_ia_indisponivel_nao_derruba_a_coleta(ia, monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", API)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", jwt("service_role"))
    monkeypatch.setattr(radar_coletar, "Banco", lambda url, chave: Banco(url, chave, prefixo=""))
    resumo = tmp_path / "resumo.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(resumo))
    monkeypatch.setenv("IA_GATEWAY_URL", SITE + "/gateway")
    # sem o segredo: a coleta roda e o resumo diz o que falta
    monkeypatch.delenv("RADAR_IA_GATEWAY_TOKEN", raising=False)
    assert radar_coletar.main(["--forcar"]) == 0
    assert "RADAR_IA_GATEWAY_TOKEN" in resumo.read_text(encoding="utf-8") and IA["pedidos"] == []
    # limite do dia atingido na IA Central: coleta ok, capturas sem nota, motivo no resumo
    monkeypatch.setenv("RADAR_IA_GATEWAY_TOKEN", "iagw_radar_teste")
    IA.update(status=429, mensagem='Limite diário de IA de "Radar" atingido (US$ 2.00 de US$ 2.00).')
    assert radar_coletar.main(["--forcar"]) == 0
    assert "Limite diário de IA" in resumo.read_text(encoding="utf-8")
    assert ia.execute("select count(*), count(ia_nota) from radar_capturas").fetchone() == (3, 0)
    # IA de volta: a coleta seguinte avalia o que ficou para trás
    IA.update(status=200, mensagem="")
    assert radar_coletar.main(["--forcar"]) == 0
    assert ia.execute("select count(ia_nota) from radar_capturas").fetchone()[0] == 3
    assert "3 de 3 captura(s) avaliada(s)" in resumo.read_text(encoding="utf-8")
    assert radar_coletar.main(["--forcar", "--sem-ia"]) == 0
    # endereço errado da IA Central: também não derruba
    ia.execute("update radar_capturas set ia_avaliado_em = null, ia_nota = null")
    monkeypatch.setenv("IA_GATEWAY_URL", "http://127.0.0.1:1/nada")
    assert radar_coletar.main(["--forcar"]) == 0
    assert "sem conexão com a IA Central" in resumo.read_text(encoding="utf-8")


def test_muitos_itens_apontando_para_a_mesma_origem_sao_tratados_como_erro_da_ia():
    novos = [{"id": i} for i in range(1, 10)]
    tudo_igual = [{"id": 1, "nota": 9, "igual_a": None}] + [{"id": i, "nota": 8, "igual_a": 1} for i in range(2, 10)]
    assert [b["igual_a"] for b in radar_ia.conferir(tudo_igual, novos, [])] == [None] * 9        # 8 repetições da mesma: ninguém é escondido
    poucos = [{"id": 1, "nota": 9, "igual_a": None}] + [{"id": i, "nota": 8, "igual_a": (1 if i <= 4 else None)} for i in range(2, 10)]
    assert [b["igual_a"] for b in radar_ia.conferir(poucos, novos, [])] == [None, 1, 1, 1] + [None] * 5
    # em cadeia (2 igual a 1, 3 igual a 2…) é a mesma coisa: todos acabariam recolhidos atrás do primeiro
    cadeia = [{"id": 1, "nota": 9, "igual_a": None}] + [{"id": i, "nota": 8, "igual_a": i - 1} for i in range(2, 10)]
    assert [b["igual_a"] for b in radar_ia.conferir(cadeia, novos, [])] == [None] * 9
    # tipos estranhos não passam: id como texto ou verdadeiro/falso, nota como texto, item que não é objeto
    assert radar_ia.conferir([{"id": "1", "nota": 5}, {"id": True, "nota": 5}, {"id": 2, "nota": "9"}, "x", None, {"id": 3, "nota": 7, "igual_a": "1"}], novos, []) == \
        [{"id": 3, "nota": 7, "motivo": "", "tema": "", "igual_a": None}]


@pytest.mark.parametrize("bruto,esperado", [
    ('[1, 2, 3]', "fora do formato"),
    ('{"content": [{"type": "tool_use", "input": "texto"}]}', "fora do formato"),
    ('{"content": [{"type": "tool_use", "input": {"itens": [{"id": "abc", "nota": 5}]}}]}', "nenhuma avaliação deste lote"),
    ('isto não é json', "fora do formato"),
])
def test_resposta_estranha_da_ia_para_a_avaliacao_com_aviso_e_sem_derrubar(ia, bruto, esperado):
    robo()
    IA["bruto"] = bruto
    r = avaliar(lote=2)
    assert r["avaliadas"] == 0 and esperado in r["erro"] and len(IA["pedidos"]) == 1               # parou no primeiro lote
    assert "Interrompida" in radar_ia.resumo_markdown(r)


def test_token_da_ia_nunca_aparece_no_resumo(ia):
    robo()
    IA.update(status=401, mensagem="Token iagw_radar_teste inválido para iagw_radar_outroTOKEN-123")
    r = avaliar()
    assert "iagw_radar" not in r["erro"] and "iagw_***" in r["erro"]
    # resposta parcial sem erro: o resumo avisa que ficou captura sem nota
    IA.update(status=200, mensagem="", responder=lambda ids: [{"id": ids[0], "nota": 8, "motivo": "m", "tema": "t", "igual_a": None}])
    r = avaliar()
    assert r["avaliadas"] == 1 and r["pendentes"] == 3 and "2 ficaram sem nota" in radar_ia.resumo_markdown(r)


def test_as_capturas_mais_novas_sao_avaliadas_primeiro_e_as_sem_nota_servem_de_contexto(ia):
    robo()
    ids = [x[0] for x in ia.execute("select id from radar_capturas where relevancia <> 'baixa' order by capturado_em desc, id desc").fetchall()]
    r = avaliar(maximo=2)
    assert r["avaliadas"] == 2
    entrada = IA["pedidos"][0]["corpo"]["messages"][0]["content"]
    vistos, novos = entrada.split("NOVOS (avalie cada um):")
    assert [json.loads(l)["id"] for l in novos.strip().splitlines()] == ids[:2]
    assert f'"id": {ids[2]},' in vistos                    # a que ficou fora do lote entra como "já vista", mesmo sem nota


def test_feed_com_texto_completo_dispensa_a_pagina_e_fonte_de_email_nao_e_visitada(cenario):
    corpo = "A Receita Federal prorrogou o prazo de entrega da declaração para 30 de novembro. " * 3
    PAGINAS["/c/feed"] = (200, f"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
      <channel><item><title>Prazo da declaração é prorrogado</title><link>{SITE}/c/noticia-lenta</link>
      <pubDate>Wed, 30 Sep 2026 10:00:00 -0300</pubDate><description>Resumo curto</description>
      <content:encoded><![CDATA[<p>{corpo}</p>]]></content:encoded></item></channel></rss>""")
    PAGINAS["/c/noticia-lenta"] = (500, "erro do site")              # a página da notícia falha; o feed basta
    cenario.execute("update radar_fontes set ativo = false where slug like 'teste-%'")
    cenario.execute("""insert into radar_fontes (slug, nome, orgao, tipo_coletor, url, config, oficial) values
        ('teste-feed', 'Portal de teste', 'Portal', 'rss', %s, '{"janela_dias": 30, "texto_do_feed": true}'::jsonb, false),
        ('teste-email', 'Boletim por e-mail', 'Consultoria', 'rss', %s, '{"origem": "email"}'::jsonb, false)""",
                    (SITE + "/c/feed", SITE + "/nao-existe"))
    r, pulados = robo()
    assert set(r) == {"teste-feed"} and "teste-email" not in pulados
    assert (r["teste-feed"]["status"], r["teste-feed"]["novos"], r["teste-feed"]["sem_texto"]) == ("ok", 1, 0)
    texto, = cenario.execute("select texto from radar_capturas").fetchone()
    assert texto.startswith("A Receita Federal prorrogou o prazo") and "Resumo curto" not in texto
    assert cenario.execute("""select count(*) from radar_execucoes e join radar_fontes f on f.id = e.fonte_id
                              where f.slug = 'teste-email'""").fetchone()[0] == 0


# ============================================================ v0.8.0 — publicações no site registradas pelo robô
CORPO_APROVADO = ("A Receita Federal prorrogou para 30 de novembro o prazo de entrega da declaração das empresas do "
                  "Simples Nacional. Quem já entregou não precisa fazer nada. A multa por atraso continua a mesma, "
                  "mas só passa a contar depois do novo prazo. Confira o calendário completo com o seu contador.")


def pagina_site(titulo: str, corpo: str, data: str = "02 de Outubro de 2026") -> str:
    return (f"<html><head><meta property='og:title' content='{titulo}'></head><body><nav>Escritório Serviços Notícias</nav>"
            f"<div>Categorias IRRF Economia Tributário</div><p>Publicada em {data}</p><p>{corpo}</p>"
            f"<footer>(48) 3242-0530</footer></body></html>")


def lista_site(slugs: list[str]) -> str:
    return "<html><body>" + "".join(f"<div><h3>Notícia</h3><a href='/news/view/{s}'>LEIA</a></div>" for s in slugs) + \
        "<a href='/news/category/irrf'>IRRF</a></body></html>"


class BancoSite:
    """O que o radar_site usa do banco, em memória."""
    def __init__(self, candidatos, registrados=(), config=None, recusar=False):
        self.candidatos, self.registrados, self.cfg, self.recusar, self.gravados = list(candidatos), list(registrados), config, recusar, []

    def config(self, chave):
        return self.cfg

    def conteudos_aprovados_sem_site(self):
        return list(self.candidatos)

    def links_publicados(self):
        return [{"id": i, "url": u, "titulo": "", "corpo": ""} for i, u in enumerate(self.registrados, 1)]

    def registrar_divulgacao(self, conteudo_id, url, quando, obs):
        if self.recusar:
            raise ErroBanco("RADAR074: assunto com pendência")
        self.gravados.append((conteudo_id, url, quando, obs))
        return {}


def test_robo_registra_a_noticia_do_site_que_corresponde_ao_conteudo_aprovado():
    import radar_site
    base = "https://artecon.cnt.br"
    paginas = {base + "/news": lista_site(["prazo-do-simples", "antiga", "ja-registrada"]),
               base + "/news/view/prazo-do-simples": pagina_site("PRAZO DO SIMPLES NACIONAL É PRORROGADO", CORPO_APROVADO),
               base + "/news/view/antiga": pagina_site("Contabilidade 4.0", "Texto que não tem nada a ver com o aprovado, sobre dados.")}
    pedidos = []
    baixar = lambda u: (pedidos.append(u), paginas[u])[1]
    candidatos = [{"id": 7, "titulo": "Prazo do Simples Nacional é prorrogado", "corpo": "**Prazo novo.** " + CORPO_APROVADO},
                  {"id": 8, "titulo": "CBS: o que muda", "corpo": "Texto sobre a CBS na transição, sem relação."}]
    banco = BancoSite(candidatos, registrados=[base + "/news/view/ja-registrada"])
    feito = radar_site.executar(banco, baixar, hoje=date(2026, 10, 5))
    assert banco.gravados == [(7, base + "/news/view/prazo-do-simples", date(2026, 10, 2), radar_site.OBSERVACAO)]
    assert feito == [f"registrado: \"Prazo do Simples Nacional é prorrogado\" → {base}/news/view/prazo-do-simples (02/10/2026)"]
    assert base + "/news/view/ja-registrada" not in pedidos           # link já registrado nem é aberto
    assert all("/category/" not in u for u in pedidos)


def test_robo_nao_registra_quando_ha_duvida_ou_o_banco_recusa():
    import radar_site
    base = "https://artecon.cnt.br"
    paginas = {base + "/news": lista_site(["prazo"]),
               base + "/news/view/prazo": pagina_site("Prazo do Simples Nacional é prorrogado", CORPO_APROVADO)}
    dois = [{"id": 1, "titulo": "Prazo do Simples Nacional é prorrogado", "corpo": CORPO_APROVADO},
            {"id": 2, "titulo": "Prazo do Simples Nacional prorrogado", "corpo": CORPO_APROVADO}]
    banco = BancoSite(dois)
    assert radar_site.executar(banco, paginas.get) == [] and banco.gravados == []      # dois candidatos: dúvida
    so_titulo = [{"id": 3, "titulo": "Prazo do Simples Nacional é prorrogado", "corpo": "Outro texto, escrito de outro jeito, " * 5}]
    banco = BancoSite(so_titulo)
    assert radar_site.executar(banco, paginas.get) == [] and banco.gravados == []      # título igual, texto diferente
    banco = BancoSite([dois[0]], recusar=True)
    feito = radar_site.executar(banco, paginas.get)
    assert banco.gravados == [] and "registro foi recusado" in feito[0] and "RADAR074" in feito[0]
    banco = BancoSite([dois[0]], config={"desligado": True})
    assert radar_site.executar(banco, lambda u: 1 / 0) == ["desligado em Configurações (chave site)"]
    banco = BancoSite([])                                                             # nada aprovado: nem abre o site
    assert radar_site.executar(banco, lambda u: 1 / 0) == []


def test_data_futura_ou_ausente_na_pagina_vira_a_data_de_hoje():
    import radar_site
    base = "https://artecon.cnt.br"
    for data in ("31 de Dezembro de 2030", "sem data"):
        paginas = {base + "/news": lista_site(["p"]), base + "/news/view/p": pagina_site("Prazo do Simples", CORPO_APROVADO, data)}
        banco = BancoSite([{"id": 1, "titulo": "Prazo do Simples", "corpo": CORPO_APROVADO}])
        radar_site.executar(banco, paginas.get, hoje=date(2026, 10, 5))
        assert banco.gravados[0][2] == date(2026, 10, 5), data


def test_texto_do_site_diferente_do_aprovado_abre_aviso_e_fecha_quando_volta():
    import radar_alertas
    cfg = {"lista": "https://artecon.cnt.br/news"}
    a, b, c = (f"https://artecon.cnt.br/news/view/{s}" for s in ("a", "b", "c"))
    regs = [{"id": 1, "url": a, "titulo": "Prazo", "corpo": CORPO_APROVADO},
            {"id": 2, "url": b, "titulo": "Igual", "corpo": CORPO_APROVADO},
            {"id": 3, "url": c, "titulo": "Fora", "corpo": CORPO_APROVADO},
            {"id": 4, "url": "https://outro.site.br/x", "titulo": "Outro site", "corpo": CORPO_APROVADO}]
    paginas = {a: pagina_site("Prazo", "O texto foi trocado por um aviso curto, sem nenhuma informação sobre o assunto."),
               b: pagina_site("Igual", CORPO_APROVADO), c: None}
    pedidos = []
    alterados, sem = radar_alertas.conferir_textos(regs, cfg, lambda u: (pedidos.append(u), paginas[u])[1])
    assert list(alterados) == [a] and sem == {c} and "https://outro.site.br/x" not in pedidos
    t = radar_alertas.titulo_texto
    abrir, fechar = radar_alertas.decidir_textos(regs, alterados, {t(c): 20, t(b): 21, t("https://artecon.cnt.br/news/view/velha"): 22,
                                                                    "Radar: fonte com falha — pgfn": 23}, sem)
    assert [r["id"] for r in abrir] == [1]
    assert sorted(fechar) == [(21, "O texto do site voltou a corresponder ao registrado."),
                              (22, "O link não está mais registrado no Radar (corrigido ou excluído).")]   # c não abriu: fica
    assert "não traz mais a maior parte do texto" in radar_alertas.corpo_texto(regs[0])


def test_banco_le_aprovados_sem_registro_e_registra_publicacao_pela_api(limpo, api_postgrest):
    from test_radar_banco import aprovar, fundamentado
    banco = Banco(API, jwt("service_role"), prefixo="")
    a1, c1 = fundamentado(limpo)
    a2, c2 = fundamentado(limpo)
    aprovar(c1); aprovar(c2)
    assert {c["id"] for c in banco.conteudos_aprovados_sem_site()} == {c1, c2}
    assert set(banco.conteudos_aprovados_sem_site()[0]) == {"id", "titulo", "corpo", "aprovado_em"}
    limpo.execute("update radar_conteudos set fora_do_site = true where id = %s", (c2,))       # só do informativo: o robô não registra
    assert [c["id"] for c in banco.conteudos_aprovados_sem_site()] == [c1]
    limpo.execute("update radar_conteudos set fora_do_site = false where id = %s", (c2,))
    banco.registrar_divulgacao(c1, "https://artecon.cnt.br/news/view/cbs", date(2026, 10, 2), "pelo robô")
    assert [c["id"] for c in banco.conteudos_aprovados_sem_site()] == [c2]
    linha = limpo.execute("select url, publicado_em::text, observacao, registrado_por, titulo from radar_divulgacoes").fetchone()
    assert linha == ("https://artecon.cnt.br/news/view/cbs", "2026-10-02", "pelo robô", None, "CBS: o que muda")
    assert limpo.execute("select status from radar_assuntos where id = %s", (a1,)).fetchone()[0] == "publicado"
    assert banco.links_publicados()[0]["corpo"] == "Texto do informativo."
    assert banco.config("chave-que-nao-existe") is None
    limpo.execute("insert into radar_config (chave, valor) values ('site', '{\"desligado\": true}') on conflict (chave) do update set valor = excluded.valor")
    try:
        assert banco.config("site") == {"desligado": True}
    finally:
        limpo.execute("delete from radar_config where chave = 'site'")


# ============================================================ v0.8.0 — resumo semanal
def test_resumo_semanal_agrupa_por_tema_esconde_o_boletim_e_fecha_o_anterior():
    import radar_resumo
    from datetime import datetime, timezone
    site = {"nome": "Receita Federal — Notícias", "oficial": True, "config": {}}
    portal = {"nome": "Econet — Blog", "oficial": False, "config": {}}
    itc = {"nome": "ITC", "oficial": False, "config": {"origem": "email"}}
    caps = [{"titulo": "Prazo do Simples prorrogado", "url": "https://gov.br/a", "relevancia": "alta", "ia_nota": 9, "ia_tema": "Simples Nacional", "radar_fontes": site},
            {"titulo": "Repetição do prazo", "url": "https://gov.br/b", "relevancia": "alta", "ia_nota": 9, "ia_tema": "Simples Nacional", "duplicata_de": 1, "radar_fontes": site},
            {"titulo": "Nota alta sem palavras", "url": "https://blog/c", "relevancia": "media", "ia_nota": 8, "ia_tema": "", "radar_fontes": portal},
            {"titulo": "Pouco relevante", "url": "https://gov.br/d", "relevancia": "media", "ia_nota": 3, "radar_fontes": site},
            {"titulo": "MATÉRIA PAGA DA ITC", "url": "https://www.itcnet.com.br/?radar=1", "relevancia": "alta", "ia_nota": 9, "radar_fontes": itc}]
    itens, do_email = radar_resumo.selecionar(caps)
    assert [c["titulo"] for c in itens] == ["Prazo do Simples prorrogado", "Nota alta sem palavras"] and do_email == 1

    class BancoResumo:
        def capturas_entre(self, i, f): self.periodo = (i, f); return caps
        def numeros_da_semana(self, i, f): return {"aprovados": 2, "publicados": 1}
        def fontes_sem_novidade(self, desde):
            self.desde = desde
            return [{"slug": "econet-blog", "nome": "Econet — Blog", "ultima_captura_em": "2026-09-25T10:00:00+00:00"},
                    {"slug": "nova", "nome": "Fonte nova", "ultima_captura_em": None}]

    class GH:
        def __init__(self, abertos): self.abertos, self.abertos_novos, self.fechados = abertos, [], []
        def avisos_abertos(self, *prefixos): assert prefixos == (radar_resumo.PREFIXO_RESUMO,); return dict(self.abertos)
        def abrir_aviso(self, t, corpo): self.abertos_novos.append((t, corpo)); return 50
        def fechar(self, n, motivo): self.fechados.append(n)

    banco, gh = BancoResumo(), GH({"Radar: resumo da semana — 21/09 a 27/09/2026": 40})
    agora = datetime(2026, 10, 5, 11, 47, tzinfo=timezone.utc)                     # segunda, 08:47 em Brasília
    feito = radar_resumo.executar(banco, gh, agora)
    titulo, corpo = gh.abertos_novos[0]
    assert titulo == "Radar: resumo da semana — 28/09 a 04/10/2026" and gh.fechados == [40]
    assert banco.periodo[0].isoformat() == "2026-09-28T00:00:00-03:00" and banco.periodo[1].isoformat() == "2026-10-05T00:00:00-03:00"
    assert "### Simples Nacional" in corpo and "### Outros" in corpo and "[Prazo do Simples prorrogado](https://gov.br/a)" in corpo
    assert "(não oficial)" in corpo and "Capturas novas na semana: **5**" in corpo and "aprovados: **2**" in corpo
    assert "MATÉRIA PAGA" not in corpo and "itcnet" not in corpo and "Mais **1** matéria" in corpo   # repositório público
    assert "Repetição" not in corpo and "Pouco relevante" not in corpo
    assert banco.desde.isoformat() == "2026-09-30T00:00:00-03:00"                      # v0.9.0: fontes sem novidade
    assert "Fontes sem notícia nova há mais de 5 dias" in corpo and "Econet — Blog — última em 25/09/2026" in corpo
    assert "Fonte nova — nunca trouxe nada" in corpo
    assert feito[0].startswith("resumo #50 aberto") and feito[1] == "resumo anterior #40 fechado"
    gh2 = GH({titulo: 50})
    assert radar_resumo.executar(banco, gh2, agora) == ["resumo já aberto (#50)"] and gh2.abertos_novos == []   # rodou duas vezes


def test_banco_le_capturas_e_numeros_da_semana_pela_api(cenario):
    from datetime import datetime, timezone
    r, _ = robo()
    banco = Banco(API, jwt("service_role"), prefixo="")
    agora = datetime.now(timezone.utc)
    caps = banco.capturas_entre(agora - timedelta(days=1), agora + timedelta(minutes=1))
    assert len(caps) == 3 and caps[0]["radar_fontes"]["nome"].startswith("teste-")
    assert banco.capturas_entre(agora - timedelta(days=30), agora - timedelta(days=20)) == []
    assert banco.numeros_da_semana(agora - timedelta(days=7), agora) == {"aprovados": 0, "publicados": 0}
    assert banco.fontes_sem_novidade(agora - timedelta(days=5)) == []                    # v0.9.0: as duas trouxeram hoje
    assert banco.fontes_sem_novidade(agora + timedelta(minutes=1))                       # nada depois de "agora"


def test_fonte_do_inlabs_grava_os_atos_com_o_texto_do_xml(cenario, monkeypatch):
    import radar_inlabs
    from radar_coletores import Item, Listagem
    texto = "INSTRUÇÃO NORMATIVA RFB Nº 2.300 Altera a IN RFB nº 2.005. Art. 1º A DCTFWeb passa a ter novo prazo de entrega."
    vistos = []

    def falso(sessao, fonte, hoje=None):
        vistos.append(fonte["slug"])
        return Listagem(brutos=40, itens=[Item(url="http://pesquisa.in.gov.br/imprensa/jsp/visualiza/index.jsp?data=30/09/2026&pagina=19&materia=111",
                                               titulo="INSTRUÇÃO NORMATIVA RFB Nº 2.300", data=date(2026, 9, 30),
                                               resumo="Altera a IN RFB nº 2.005.", texto_da_listagem=texto)]), 200
    monkeypatch.setattr(radar_inlabs, "listar_paginas", falso)
    cenario.execute("update radar_fontes set ativo = false where slug like 'teste-%'")
    cenario.execute("""insert into radar_fontes (slug, nome, orgao, tipo_coletor, url, config) values
        ('teste-inlabs', 'DOU pelo INLABS', 'Imprensa Nacional', 'inlabs', 'https://inlabs.in.gov.br/',
         '{"texto_do_feed": true, "texto_minimo": 1}'::jsonb)""")
    r, _ = robo()
    assert vistos == ["teste-inlabs"] and (r["teste-inlabs"]["status"], r["teste-inlabs"]["novos"]) == ("ok", 1)
    assert cenario.execute("select texto from radar_capturas").fetchone()[0] == texto



def test_robo_nao_confunde_www_mes_diferente_texto_curto_nem_noticia_anterior_a_aprovacao():
    import radar_site
    base = "https://artecon.cnt.br"
    agenda = ("Confira as obrigações do mês: DCTFWeb, EFD-Reinf, FGTS Digital, eSocial, GPS, DARF do IRRF e o DAS do Simples "
              "Nacional. Os prazos mudam quando o dia cai em fim de semana ou feriado, então confira com a equipe.")
    paginas = {base + "/news": lista_site(["agenda-novembro", "ja-registrada", "curta"]),
               base + "/news/view/agenda-novembro": pagina_site("Agenda tributária de novembro de 2026", agenda),
               base + "/news/view/curta": pagina_site("Prazo do Simples", "Prazo do Simples prorrogado. " + CORPO_APROVADO)}
    pedidos = []
    baixar = lambda u: (pedidos.append(u), paginas[u])[1]
    candidatos = [{"id": 1, "titulo": "Agenda tributária de outubro de 2026", "corpo": agenda},       # outro mês: não é ela
                  {"id": 2, "titulo": "Prazo do Simples", "corpo": "Prazo do Simples prorrogado."}]  # curto demais para comparar
    banco = BancoSite(candidatos, registrados=["https://www.artecon.cnt.br/news/view/ja-registrada/"])
    assert radar_site.executar(banco, baixar, hoje=date(2026, 10, 5)) == [] and banco.gravados == []
    assert base + "/news/view/ja-registrada" not in pedidos                       # com www e barra no fim: é o mesmo endereço
    antes = [{"id": 3, "titulo": "Prazo do Simples Nacional é prorrogado", "corpo": CORPO_APROVADO, "aprovado_em": "2026-10-04T10:00:00Z"}]
    paginas[base + "/news"] = lista_site(["antiga"])
    paginas[base + "/news/view/antiga"] = pagina_site("Prazo do Simples Nacional é prorrogado", CORPO_APROVADO, "02 de Outubro de 2026")
    banco = BancoSite(antes)
    assert radar_site.executar(banco, baixar, hoje=date(2026, 10, 5)) == [] and banco.gravados == []   # publicada antes de aprovar
    assert radar_site.chave_url("http://www.artecon.cnt.br/news/view/x/") == radar_site.chave_url("https://artecon.cnt.br/news/view/x")


def test_configuracao_do_site_com_valor_estranho_volta_ao_padrao():
    import radar_site
    for ruim in ({"max_noticias": "15a"}, {"padrao": None}, {"padrao": "(["}, {"lista": "javascript:alert(1)"}, {"desligado": "sim"}, [1, 2]):
        cfg = radar_site.configuracao(BancoSite([], config=ruim))
        assert (cfg["lista"], cfg["padrao"], cfg["max_noticias"], cfg["desligado"]) == (
            radar_site.CONFIG_PADRAO["lista"], radar_site.CONFIG_PADRAO["padrao"], 15, False), ruim
    assert radar_site.configuracao(BancoSite([], config={"max_noticias": 500}))["max_noticias"] == 50


def test_numero_curto_no_titulo_e_aprovacao_a_noite_em_brasilia():
    import radar_site
    base = "https://artecon.cnt.br"
    corpo = ("A Secretaria da Fazenda prorrogou o prazo de recolhimento do ICMS das empresas do comércio varejista para o dia "
             "vinte do mês seguinte. A medida vale para os fatos geradores de outubro e não altera as obrigações acessórias.")
    paginas = {base + "/news": lista_site(["portaria-45"]),
               base + "/news/view/portaria-45": pagina_site("Portaria SEF nº 45 prorroga prazo do ICMS", corpo, "05 de Outubro de 2026")}
    banco = BancoSite([{"id": 1, "titulo": "Portaria SEF nº 46 prorroga prazo do ICMS", "corpo": corpo}])
    assert radar_site.executar(banco, paginas.get, hoje=date(2026, 10, 5)) == [] and banco.gravados == []    # nº 45 ≠ nº 46
    noite = [{"id": 2, "titulo": "Portaria SEF nº 45 prorroga prazo do ICMS", "corpo": corpo, "aprovado_em": "2026-10-06T01:30:00+00:00"}]
    banco = BancoSite(noite)                                              # aprovada às 22h30 de 05/10 em Brasília
    radar_site.executar(banco, paginas.get, hoje=date(2026, 10, 6))
    assert banco.gravados and banco.gravados[0][:3] == (2, base + "/news/view/portaria-45", date(2026, 10, 5))


# ============================================================ v0.9.0 — rascunhos automáticos
def test_robo_prepara_o_rascunho_da_noticia_de_topo_e_respeita_o_limite_do_dia(ia):
    import radar_rascunhos
    from datetime import datetime, timezone
    robo()
    simples = ia.execute("select id from radar_capturas where titulo = 'Prazo do Simples Nacional é prorrogado'").fetchone()[0]
    pgfn = ia.execute("select id from radar_capturas where titulo = 'PGFN abre nova transação tributária'").fetchone()[0]
    ia.execute("update radar_fontes set oficial = true where slug like 'teste-%'")
    ia.execute("update radar_capturas set ia_nota = 9 where id = %s", (simples,))
    ia.execute("update radar_capturas set ia_nota = 6 where id = %s", (pgfn,))                    # abaixo da nota mínima
    assert ia.execute("select relevancia from radar_capturas where id = %s", (simples,)).fetchone()[0] == "alta"
    IA["conteudo"] = {"titulo": "Prazo de opção pelo Simples vai até 31 de janeiro de 2027",
                      "titulos": ["Simples Nacional: opção para 2027 ganha mais prazo.", "Prazo de opção pelo Simples vai até 31 de janeiro de 2027",
                                  "Curto", "Simples Nacional: opção para 2027 ganha mais prazo", "Empresas têm até 31/01/2027 para optar pelo Simples"],
                      "corpo": "## O que muda\nO prazo de opção foi estendido até **31 de janeiro de 2027**, com multa de 20% para quem perder. "
                               "<b>Confira</b> as condições com a equipe. [VERIFICAR: quem pode optar]"}
    banco = Banco(API, jwt("service_role"), prefixo="")
    agora = datetime.now(timezone.utc)
    ia.execute("update radar_config set valor = '{\"por_dia\": 1}' where chave = 'rascunhos'")
    try:
        r = radar_rascunhos.executar(banco, "iagw_radar_teste", SITE + "/gateway", agora=agora)
        assert r["erro"] is None and len(r["feitos"]) == 1
        pedido = IA["pedidos"][-1]
        assert pedido["corpo"]["model"] == "claude-sonnet-4-6" and "TEXTO ORIGINAL, NUNCA CÓPIA" in pedido["corpo"]["system"]
        assert "prorrogado até 31 de janeiro de 2027" in pedido["corpo"]["messages"][0]["content"]       # foi o texto oficial
        assert pedido["cab"]["x-ia-usuario"] == "robô de rascunhos"
        assert "ESCRITA NATURAL" in pedido["corpo"]["system"] and "'titulos'" in pedido["corpo"]["system"]   # v0.10.0
        assert ia.execute("select titulos_sugeridos from radar_conteudos").fetchone()[0] == [
            "Simples Nacional: opção para 2027 ganha mais prazo", "Empresas têm até 31/01/2027 para optar pelo Simples"]
        cont = ia.execute("""select c.titulo, c.corpo, c.status, c.gerado_por, c.modelo_ia, c.avisos_ia, a.status
                             from radar_conteudos c join radar_assuntos a on a.id = c.assunto_id""").fetchall()
        assert len(cont) == 1
        titulo, corpo, status, gerado, modelo, avisos, st_assunto = cont[0]
        assert (status, gerado, modelo, st_assunto) == ("rascunho", "ia", "claude-sonnet-4-6 (robô)", "conteudo_gerado")
        assert "<b>" not in corpo and avisos[0] == radar_rascunhos.AVISO_ROBO
        assert any("20%" in a for a in avisos) and any("[VERIFICAR]" in a for a in avisos)
        assert not any("31 de janeiro de 2027" in a for a in avisos)
        assert simples not in {x[0] for x in ia.execute("select id from radar_v_fila").fetchall()}   # saiu da triagem
        assert ia.execute("select rascunhos_robo from radar_v_painel").fetchone()[0] == 1
        ia.execute("update radar_capturas set ia_nota = 10 where id = %s", (pgfn,))
        n = len(IA["pedidos"])
        assert radar_rascunhos.executar(banco, "iagw_radar_teste", SITE + "/gateway", agora=agora)["feitos"] == []   # 1 por dia
        assert len(IA["pedidos"]) == n
        ia.execute("update radar_config set valor = '{\"por_dia\": 3}' where chave = 'rascunhos'")
        IA.update(status=429, mensagem="limite do mês")
        r = radar_rascunhos.executar(banco, "iagw_radar_teste", SITE + "/gateway", agora=agora)
        assert "limite do mês" in r["erro"] and r["feitos"] == []
        assert pgfn in {x[0] for x in ia.execute("select id from radar_v_fila").fetchall()}       # IA fora: nada foi aberto
        ia.execute("update radar_config set valor = '{\"ligado\": false}' where chave = 'rascunhos'")
        assert radar_rascunhos.executar(banco, "iagw_radar_teste", SITE + "/gateway", agora=agora)["pulado"]
    finally:
        ia.execute("""update radar_config set valor = '{"ligado": true, "nota_minima": 9, "por_dia": 2, "dias": 3, "formato": "informativo"}'
                      where chave = 'rascunhos'""")
        ia.execute("delete from radar_assuntos")


def test_texto_ruim_da_ia_numa_captura_nao_trava_as_outras(ia):
    import radar_rascunhos
    robo()
    ia.execute("update radar_fontes set oficial = true where slug like 'teste-%'")
    ia.execute("update radar_capturas set ia_nota = 10 where titulo = 'PGFN abre nova transação tributária'")
    ia.execute("update radar_capturas set ia_nota = 9 where titulo = 'Prazo do Simples Nacional é prorrogado'")
    bom = {"titulo": "Prazo do Simples prorrogado", "corpo": "O prazo de opção foi estendido. " * 5}
    IA["conteudo"] = lambda corpo: {"titulo": "x", "corpo": "curto"} if "PGFN" in corpo["messages"][0]["content"] else bom
    try:
        r = radar_rascunhos.executar(Banco(API, jwt("service_role"), prefixo=""), "iagw_radar_teste", SITE + "/gateway")
        assert len(r["feitos"]) == 1 and r["erro"] is None and "PGFN" in r["puladas"][0] and "curto demais" in r["puladas"][0]
        assert "sem rascunho desta vez" in radar_rascunhos.resumo_markdown(r)
        assert [t for (t,) in ia.execute("select titulo from radar_conteudos").fetchall()] == ["Prazo do Simples prorrogado"]
        assert ia.execute("select count(*) from radar_v_fila where titulo like 'PGFN%%'").fetchone()[0] == 1   # continua na fila
    finally:
        ia.execute("delete from radar_assuntos")
