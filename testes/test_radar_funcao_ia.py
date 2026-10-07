"""Função radar-ia (v0.11.0) rodando de verdade no Deno, com o banco real (PostgREST) e uma IA Central de mentira.

Confere o que a v0.11.0 mudou: o "Gerar" guarda as outras opções de título e pede a escrita natural; a ação nova
"titulos" só sugere (não grava nada) e não repete o que já foi sugerido. Sem o Deno instalado, o arquivo é pulado.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from conftest import API, EDITOR, RAIZ, jwt
from test_radar_banco import cenario_publicavel

PORTA_PONTE, PORTA_FUNCAO = 3994, 3993
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
IA = {"pedidos": [], "respostas": {}, "fila": []}
PAGINA = {"html": "", "status": 200, "tipo": "text/html; charset=utf-8", "bytes": None}


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST; /auth/v1/user → e-mail de quem pede; /gw → IA Central de mentira (formato da Anthropic)."""
    def _responder(self, status, corpo):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _rest(self):
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        cab = {k: v for k, v in self.headers.items() if k.lower() in ("authorization", "content-type", "prefer")}
        r = requests.request(self.command, API + self.path.removeprefix("/rest/v1"), headers=cab, data=corpo, timeout=30)
        self._responder(r.status_code, r.content)

    def do_GET(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        if self.path == "/auth/v1/user":
            return self._responder(200, {"id": EDITOR, "email": "editora@artecon.test"})
        if self.path.startswith("/pagina-oficial/vai-para-fora"):
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.startswith("/pagina-oficial/redireciona"):
            self.send_response(301)
            self.send_header("Location", "/pagina-oficial/final")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.startswith("/pagina-oficial"):                  # "site oficial" de mentira (RADAR_DOMINIOS_EXTRA)
            dados = PAGINA["bytes"] if PAGINA["bytes"] is not None else PAGINA["html"].encode()
            self.send_response(PAGINA["status"])
            self.send_header("Content-Type", PAGINA["tipo"])
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            return self.wfile.write(dados)
        self._responder(404, {"message": "nao encontrado"})

    def do_PATCH(self):
        self._rest()

    def do_POST(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        IA["pedidos"].append(corpo)
        if IA["fila"]:                                                   # respostas completas, em ordem (verificação com busca)
            return self._responder(200, IA["fila"].pop(0))
        nome = corpo["tools"][0]["name"]
        self._responder(200, {"type": "message", "model": corpo["model"], "stop_reason": "tool_use",
                              "usage": {"input_tokens": 1000, "output_tokens": 300},
                              "content": [{"type": "tool_use", "name": nome, "input": IA["respostas"][nome]}]})

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def funcao(api_postgrest):
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), Ponte)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), IA_GATEWAY_TOKEN="iagw_radar_teste",
                    IA_GATEWAY_URL=PONTE + "/gw", RADAR_PORTA_LOCAL=str(PORTA_FUNCAO), NO_COLOR="1", RADAR_DOMINIOS_EXTRA="127.0.0.1")
    proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                             str(RAIZ / "supabase" / "functions" / "radar-ia" / "index.ts")],
                            env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(150):
        try:
            requests.options(f"http://127.0.0.1:{PORTA_FUNCAO}/", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.2)
    yield
    proc.terminate()
    ponte.shutdown()


def pedir(acao, **extra):
    r = requests.post(f"http://127.0.0.1:{PORTA_FUNCAO}/", timeout=60, json={"acao": acao, **extra},
                      headers={"Authorization": "Bearer " + jwt("authenticated", EDITOR)})
    return r.status_code, r.json()


def test_gerar_guarda_as_opcoes_de_titulo_e_pede_escrita_natural(funcao, limpo):
    a, _ = cenario_publicavel(limpo)
    limpo.execute("insert into radar_assunto_capturas select %s, captura_id from radar_evidencias where assunto_id = %s on conflict do nothing", (a, a))
    IA["respostas"]["conteudo"] = {
        "titulo": "CBS terá alíquota de 0,9% na transição",
        "titulos": ["CBS: alíquota de 0,9% na fase de transição.", "CBS terá alíquota de 0,9% na transição", "CBS",
                    "O que muda com a CBS a 0,9%", "CBS: alíquota de 0,9% na fase de transição", "Quarto título que sobra"],
        "corpo": "A CBS será cobrada à alíquota de 0,9% (nove décimos por cento) no período de transição, conforme o texto oficial. " * 2}
    status, r = pedir("gerar", assunto_id=a, formato="flash")
    assert status == 200, r
    pedido = IA["pedidos"][-1]
    assert "ESCRITA NATURAL" in pedido["system"] and "'titulos'" in pedido["system"]
    assert pedido["tools"][0]["input_schema"]["required"] == ["titulo", "titulos", "corpo"]
    esperado = ["CBS: alíquota de 0,9% na fase de transição", "O que muda com a CBS a 0,9%", "Quarto título que sobra"]
    assert r["titulos"] == esperado
    assert limpo.execute("select titulos_sugeridos from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()[0] == esperado
    assert limpo.execute("select acao from radar_ia_uso order by id desc limit 1").fetchone()[0] == "gerar"


def test_titulos_so_sugere_e_nao_repete(funcao, limpo):
    a, c = cenario_publicavel(limpo)
    antes = limpo.execute("select atualizado_em, titulo from radar_conteudos where id = %s", (c,)).fetchone()
    IA["respostas"]["titulos"] = {"titulos": ["Já sugerido antes", "Título novo e bem diferente", antes[1], "Outro título novo aqui"]}
    status, r = pedir("titulos", assunto_id=a, conteudo_id=c, evitar=["Já sugerido antes"])
    assert status == 200, r
    assert r["titulos"] == ["Título novo e bem diferente", "Outro título novo aqui"]
    pedido = IA["pedidos"][-1]
    assert pedido["model"] == "claude-haiku-4-5" and "Já sugerido antes" in pedido["messages"][0]["content"]
    assert limpo.execute("select atualizado_em, titulo from radar_conteudos where id = %s", (c,)).fetchone() == antes   # nada gravado
    assert limpo.execute("select acao from radar_ia_uso order by id desc limit 1").fetchone()[0] == "gerar"       # consumo registrado
    status, r = pedir("titulos", assunto_id=a, conteudo_id=999999)
    assert status == 404 and "não encontrado" in r["message"]
    status, r = pedir("titulos", assunto_id=a, conteudo_id="x")
    assert status == 400


def test_texto_para_analise_so_com_fonte_nao_oficial_e_marcado(funcao, limpo, request):
    limpo.execute("update radar_fontes set oficial = false where slug = 'cgibs-noticias'")
    request.addfinalizer(lambda: limpo.execute("update radar_fontes set oficial = true where slug = 'cgibs-noticias'"))
    cap = limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                           select id, 'https://www.cgibs.gov.br/x', 'Boletim: novidade', 'Chamada do boletim com a novidade sobre o Simples.', md5('b')
                             from radar_fontes where slug = 'cgibs-noticias' returning id""").fetchone()[0]
    a = limpo.execute("insert into radar_assuntos (titulo) values ('Só do boletim') returning id").fetchone()[0]
    limpo.execute("insert into radar_assunto_capturas values (%s, %s)", (a, cap))
    IA["respostas"]["conteudo"] = {"titulo": "Novidade do Simples para análise", "titulos": [],
                                   "corpo": "Segundo o boletim, há novidade sobre o Simples. [VERIFICAR: norma e prazo] " * 3}
    n = len(IA["pedidos"])
    status, r = pedir("gerar", assunto_id=a, formato="flash")                     # sem "analise": recusa, como antes
    assert status == 400 and "fonte oficial" in r["message"] and len(IA["pedidos"]) == n
    status, r = pedir("gerar", assunto_id=a, formato="flash", analise=True)
    assert status == 200, r
    pedido = IA["pedidos"][-1]
    assert "PARA ANÁLISE INTERNA" in pedido["system"] and "<<<TEXTO DE FONTE NÃO OFICIAL" in pedido["messages"][0]["content"]
    assert r["avisos"][0].startswith("TEXTO PARA ANÁLISE, escrito a partir de fonte NÃO oficial (Comitê Gestor do IBS)")
    assert limpo.execute("select avisos_ia->>0 from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()[0].startswith("TEXTO PARA ANÁLISE")



# ------------------------------------------------ v0.14.0: verificação em fontes oficiais e textos sem aviso de origem
def _assunto_do_boletim(db, request):
    db.execute("update radar_fontes set oficial = false where slug = 'cgibs-noticias'")
    request.addfinalizer(lambda: db.execute("update radar_fontes set oficial = true where slug = 'cgibs-noticias'"))
    cap = db.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                        select id, 'https://www.cgibs.gov.br/y', 'Boletim: prazo do Simples', 'O prazo de opção pelo Simples foi prorrogado até 15 de outubro.', md5('c')
                          from radar_fontes where slug = 'cgibs-noticias' returning id""").fetchone()[0]
    a = db.execute("insert into radar_assuntos (titulo) values ('Prazo do Simples prorrogado') returning id").fetchone()[0]
    db.execute("insert into radar_assunto_capturas values (%s, %s)", (a, cap))
    return a


def _resposta(conteudo, parar="tool_use", buscas=0):
    return {"type": "message", "model": "claude-sonnet-4-6", "stop_reason": parar, "content": conteudo,
            "usage": {"input_tokens": 2000, "output_tokens": 400, "server_tool_use": {"web_search_requests": buscas}}}


def test_verificar_procura_so_em_sites_oficiais_e_guarda_so_o_que_a_busca_trouxe(funcao, limpo, request):
    a = _assunto_do_boletim(limpo, request)
    oficial = "https://www.gov.br/receita/pt-br/assuntos/noticias/2026/outubro/prazo-simples"
    IA["fila"][:] = [
        _resposta([{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "prazo opção Simples 2027"}},
                   {"type": "web_search_tool_result", "tool_use_id": "s1", "content": [
                       {"type": "web_search_result", "url": oficial, "title": "Receita prorroga prazo"}]}], parar="pause_turn", buscas=1),
        _resposta([{"type": "tool_use", "id": "t1", "name": "verificacao", "input": {
            "situacao": "confirmada", "resumo": "A Receita Federal confirma a prorrogação até 15 de outubro.",
            "fontes": [{"url": oficial, "titulo": "Receita prorroga prazo", "orgao": "Receita Federal", "data": "05/10/2026", "confirma": "Prazo até 15/10."},
                       {"url": "https://www.gov.br/inventado/nunca-apareceu", "titulo": "x", "orgao": "x", "data": "", "confirma": "x"},
                       {"url": "https://portal-nao-oficial.com.br/noticia", "titulo": "y", "orgao": "y", "data": "", "confirma": "y"}],
            "divergencias": []}}], buscas=1)]
    status, r = pedir("verificar", assunto_id=a)
    assert status == 200, r
    primeiro = IA["pedidos"][-2]
    tipos = {f.get("type", "custom"): f for f in primeiro["tools"]}
    assert tipos["web_search_20260209"]["allowed_domains"] == ["gov.br", "jus.br", "leg.br", "mp.br", "def.br"]
    assert "web_fetch_20260209" in tipos and primeiro["tool_choice"] == {"type": "auto"}
    assert "<<<TEXTO capturado" in primeiro["messages"][0]["content"] and "fonte NÃO oficial" in primeiro["messages"][0]["content"]
    assert IA["pedidos"][-1]["messages"][-1]["role"] == "assistant"            # pause_turn: continua de onde parou
    v = limpo.execute("select verificacao from radar_assuntos where id = %s", (a,)).fetchone()[0]
    assert v["situacao"] == "confirmada" and [f["url"] for f in v["fontes"]] == [oficial] and v["buscas"] == 2
    assert limpo.execute("select acao from radar_ia_uso order by id desc limit 1").fetchone()[0] == "fundamentar"
    # nenhuma página oficial de verdade: não vale como confirmação
    IA["fila"][:] = [_resposta([{"type": "tool_use", "id": "t2", "name": "verificacao", "input": {
        "situacao": "confirmada", "resumo": "Confirmado.", "fontes": [{"url": oficial, "titulo": "a", "orgao": "b", "data": "", "confirma": "c"}],
        "divergencias": []}}])]
    status, r = pedir("verificar", assunto_id=a)
    assert status == 200 and r["verificacao"]["situacao"] == "nao_encontrada" and r["verificacao"]["fontes"] == []


def test_gerar_usa_a_verificacao_e_tira_o_aviso_de_origem_do_texto(funcao, limpo, request):
    a = _assunto_do_boletim(limpo, request)
    limpo.execute("""update radar_assuntos set verificacao = '{"situacao": "confirmada", "resumo": "Receita confirma.", "em": "2026-10-07T10:00:00Z",
                     "fontes": [{"url": "https://www.gov.br/receita/x", "titulo": "Prazo", "orgao": "Receita Federal", "data": "05/10/2026", "confirma": "Prazo até 15/10."}],
                     "divergencias": []}' where id = %s""", (a,))
    IA["respostas"]["conteudo"] = {"titulo": "Prazo do Simples vai até 15 de outubro", "titulos": [],
        "corpo": "*Este informativo é baseado em material de fonte não oficial e precisa ser conferido.*\n\nO prazo de opção foi prorrogado até 15 de outubro, "
                 "segundo a Receita Federal.\n\nA Receita alerta que boletos enviados por fontes não oficiais são golpe.\n\n"
                 "## Análise Artecon\nQuem pretende optar deve organizar os documentos antes do novo prazo."}
    status, r = pedir("gerar", assunto_id=a, formato="informativo", analise=True)
    assert status == 200, r
    pedido = IA["pedidos"][-1]
    assert "<<<VERIFICAÇÃO EM FONTES OFICIAIS" in pedido["messages"][0]["content"] and "Receita Federal — Prazo (05/10/2026)" in pedido["messages"][0]["content"]
    assert "(11) se vier uma VERIFICAÇÃO EM FONTES OFICIAIS" in pedido["system"] and "NÃO escreva no texto avisos sobre a origem" in pedido["system"]
    assert "quem é afetado" in pedido["system"]                                  # Análise Artecon mais útil
    corpo = limpo.execute("select corpo from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()[0]
    assert "baseado em material" not in corpo and corpo.startswith("O prazo de opção")
    assert "boletos enviados por fontes não oficiais são golpe" in corpo          # parágrafo de verdade fica


def test_pagina_traz_o_texto_so_de_site_oficial(funcao, limpo, request):
    a = _assunto_do_boletim(limpo, request)
    PAGINA["html"] = ("<html><head><title>Receita prorroga prazo | Gov.br</title>"
                      "<meta property='article:published_time' content='2026-10-05T10:00:00'></head><body><nav>Menu Início</nav>"
                      "<article><h1>Receita prorroga prazo</h1><p>O prazo de opção pelo Simples Nacional foi prorrogado até 15 de outubro de 2026.</p>"
                      "<p>A medida vale para todas as empresas que &nbsp;pediram a opção &amp; ainda não regularizaram.</p>" + "<p>Detalhe.</p>" * 60 +
                      "</article><footer>Rodapé</footer></body></html>")
    status, r = pedir("pagina", assunto_id=a, url=f"{PONTE}/pagina-oficial/prazo")
    assert status == 200, r
    assert r["titulo"] == "Receita prorroga prazo | Gov.br" and r["data"] == "2026-10-05"
    assert "prorrogado até 15 de outubro de 2026" in r["texto"] and "Menu" not in r["texto"] and "Rodapé" not in r["texto"] and "& ainda" in r["texto"]
    status, r = pedir("pagina", assunto_id=a, url="https://portal-nao-oficial.com.br/x")
    assert status == 400 and "órgão público" in r["message"]
    status, r = pedir("pagina", assunto_id=a, url="http://www.gov.br/x")         # só https
    assert status == 400



def test_pagina_confere_cada_redirecionamento_e_le_latin1_e_entidades(funcao, limpo, request):
    a = _assunto_do_boletim(limpo, request)
    status, r = pedir("pagina", assunto_id=a, url=f"{PONTE}/pagina-oficial/vai-para-fora")
    assert status == 400 and "fora de um órgão público" in r["message"]
    html = ("<html><head><title>Lei de 2026</title></head><body><article><p>Disposições sobre a contribuição e o preço médio; "
            "ação de cobrança &#x110000; &#99999999; &#55296; fim.</p>" + "<p>Parágrafo com acentuação: ação, opção, é.</p>" * 20 + "</article></body></html>")
    PAGINA.update(bytes=html.encode("latin-1"), tipo="text/html; charset=ISO-8859-1")
    request.addfinalizer(lambda: PAGINA.update(bytes=None, tipo="text/html; charset=utf-8"))
    status, r = pedir("pagina", assunto_id=a, url=f"{PONTE}/pagina-oficial/redireciona")
    assert status == 200, r
    assert r["url"].endswith("/pagina-oficial/final") and "contribuição e o preço médio" in r["texto"] and "ação, opção, é" in r["texto"]
