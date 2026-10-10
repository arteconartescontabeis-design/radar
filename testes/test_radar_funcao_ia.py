"""Função radar-ia (v0.11.0) rodando de verdade no Deno, com o banco real (PostgREST) e uma IA Central de mentira.

Confere o que a v0.11.0 mudou: o "Gerar" guarda as outras opções de título e pede a escrita natural; a ação nova
"titulos" só sugere (não grava nada) e não repete o que já foi sugerido. Sem o Deno instalado, o arquivo é pulado.
"""
from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from conftest import API, EDITOR, RAIZ, carregar_fontes_novas, como, jwt
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
    ponte.server_close()          # libera a porta na hora: outro módulo de teste usa a mesma


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
    assert pedido["tools"][0]["input_schema"]["required"] == ["titulo", "titulos", "corpo", "pendencias"]
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
    # v0.16.0: o texto veio com marca [VERIFICAR]: a segunda passada tira a marca e o ponto vai para os pontos a conferir
    IA["respostas"]["revisao"] = {"titulo": "Novidade do Simples para análise", "pendencias": ["[VERIFICAR: norma e prazo]"],
                                  "corpo": "Segundo o boletim, há novidade sobre o Simples, ainda sem a norma publicada. " * 3}
    status, r = pedir("gerar", assunto_id=a, formato="flash", analise=True)
    assert status == 200, r
    pedido, revisao = IA["pedidos"][-2:]
    assert "PARA ANÁLISE INTERNA" in pedido["system"] and "<<<TEXTO DE FONTE NÃO OFICIAL" in pedido["messages"][0]["content"]
    assert "'segundo o Portal Contábil SC'" in pedido["system"] and "marque com [VERIFICAR" not in pedido["system"]
    assert revisao["tools"][0]["name"] == "revisao" and "[VERIFICAR: norma e prazo]" in revisao["messages"][0]["content"]
    assert r["avisos"][0].startswith("TEXTO PARA ANÁLISE, escrito a partir de fonte NÃO oficial (Comitê Gestor do IBS)")
    corpo, avisos = limpo.execute("select corpo, avisos_ia from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()
    assert avisos[0].startswith("TEXTO PARA ANÁLISE") and "[VERIFICAR" not in corpo
    # no texto para análise o dado fica no texto, atribuído à fonte não oficial: o aviso diz isso (e não "ficou fora do texto")
    assert "Pontos a conferir na fonte oficial antes de publicar (no texto, atribuídos à fonte não oficial): norma e prazo." in avisos
    assert not any("marcados com [VERIFICAR]" in x for x in avisos)


# ------------------------------------------------ v0.16.0: o texto não leva marca nem cópia
COPIADO = ("A norma dispõe sobre a apuração da Contribuição Social sobre Bens e Serviços (CBS) no período de transição. "
           "Art. 2º O contribuinte deverá destacar a CBS no documento fiscal à alíquota de 0,9%. ")
REVISADO = ("Segundo a Receita Federal, a regra nova explica como calcular a CBS durante a transição, e a empresa precisa "
            "mostrar o tributo na nota fiscal com alíquota de 0,9%. ")


def _assunto_com_texto(db):
    a, c = cenario_publicavel(db)
    db.execute("insert into radar_assunto_capturas select %s, captura_id from radar_evidencias where assunto_id = %s on conflict do nothing", (a, a))
    return a, c


def test_gerar_sem_marca_nem_copia_faz_uma_chamada_so_e_guarda_as_pendencias(funcao, limpo):
    a, _ = _assunto_com_texto(limpo)
    IA["respostas"]["conteudo"] = {"titulo": "CBS de 0,9% na transição", "titulos": [],
                                   "corpo": "Segundo a Receita Federal, a CBS entra com alíquota de 0,9% e precisa aparecer na nota fiscal. " * 2,
                                   "pendencias": ["[VERIFICAR: data da sessão presencial]", "data da sessão presencial", "x"]}
    n = len(IA["pedidos"])
    status, r = pedir("gerar", assunto_id=a, formato="flash")
    assert status == 200, r
    assert len(IA["pedidos"]) == n + 1                                         # nada a revisar: uma chamada só
    sistema = IA["pedidos"][-1]["system"]
    assert "NUNCA escreva nele marcas" in sistema and "'pendencias'" in sistema and "'ADI 5.161' e 'ADI nº 5.161/DF'" in sistema
    assert "FONTE SEMPRE CITADA" in sistema and "BOLETIM PAGO" in sistema and "[VERIFICAR: o que falta]" not in sistema
    assert "Ficou fora do texto por falta de confirmação (confira na fonte oficial antes de publicar): data da sessão presencial." in r["avisos"]


def test_gerar_com_marca_ou_copia_pede_a_revisao_e_grava_o_texto_revisado(funcao, limpo):
    a, _ = _assunto_com_texto(limpo)
    IA["respostas"]["conteudo"] = {"titulo": "CBS de 0,9% na transição", "titulos": [], "pendencias": [],
                                   "corpo": COPIADO + "A sessão será em 30 de setembro [VERIFICAR: a fonte indica 30/9, mas não especifica o ano]. "
                                            + "Texto próprio sobre a CBS. " * 4}
    IA["respostas"]["revisao"] = {"titulo": "CBS de 0,9% na transição", "pendencias": ["ano da sessão presencial"],
                                  "corpo": REVISADO + "A sessão está marcada para 30 de setembro. " + "Texto próprio sobre a CBS. " * 4}
    n = len(IA["pedidos"])
    status, r = pedir("gerar", assunto_id=a, formato="flash")
    assert status == 200, r
    assert len(IA["pedidos"]) == n + 2
    rev = IA["pedidos"][-1]
    assert rev["tools"][0]["name"] == "revisao" and "Você revisa" in rev["system"] and "passa a dizer de onde veio" in rev["system"]
    msg = rev["messages"][0]["content"]
    assert "Marcas e comentários de dúvida a resolver" in msg and "a fonte indica 30/9" in msg
    assert "Trechos iguais ao da fonte sem a fonte citada no parágrafo" in msg and "contribuinte deverá destacar a CBS no documento fiscal" in msg
    assert "(fonte: Receita Federal do Brasil)" in msg                         # v0.18.0: a IA cita a fonte pelo nome do órgão
    assert "<<<TEXTO OFICIAL" in msg                                           # o material para confirmar o que puder
    corpo, avisos = limpo.execute("select corpo, avisos_ia from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()
    assert corpo.startswith(REVISADO.strip()) and "[VERIFICAR" not in corpo
    assert "Ficou fora do texto por falta de confirmação (confira na fonte oficial antes de publicar): ano da sessão presencial." in avisos
    assert not any("marcados com [VERIFICAR]" in x or "revisão automática" in x for x in avisos)
    assert limpo.execute("select acao, tokens_entrada, tokens_saida from radar_ia_uso order by id desc limit 1").fetchone() == ("gerar", 2000, 600)


def test_trecho_igual_com_a_fonte_citada_no_paragrafo_nao_pede_revisao(funcao, limpo):
    """v0.18.0: o texto pode ficar igual ao da fonte quando o mesmo parágrafo diz de onde veio; sem isso, a segunda passada
    acrescenta a fonte (e no trecho tirado do boletim pago, reescreve)."""
    a, _ = _assunto_com_texto(limpo)
    citado = "Segundo a Receita Federal do Brasil, a " + COPIADO[2:]
    IA["respostas"]["conteudo"] = {"titulo": "CBS de 0,9% na transição", "titulos": [], "pendencias": [],
                                   "corpo": citado + "\n\n" + "Texto próprio sobre a CBS. " * 4}
    n = len(IA["pedidos"])
    status, r = pedir("gerar", assunto_id=a, formato="flash")
    assert status == 200, r
    assert len(IA["pedidos"]) == n + 1                                         # citada: nada a revisar
    corpo, avisos = limpo.execute("select corpo, avisos_ia from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()
    assert corpo.startswith(citado.strip()) and not any("revisão automática" in x for x in avisos)
    # a fonte citada noutro parágrafo não vale: o trecho igual pede a segunda passada
    IA["respostas"]["conteudo"] = {"titulo": "CBS de 0,9% na transição", "titulos": [], "pendencias": [],
                                   "corpo": "A Receita Federal do Brasil publicou a norma.\n\n" + COPIADO + "Texto próprio sobre a CBS. " * 4}
    IA["respostas"]["revisao"] = {"titulo": "CBS de 0,9% na transição", "pendencias": [], "corpo": citado + "Texto próprio sobre a CBS. " * 4}
    status, r = pedir("gerar", assunto_id=a, formato="flash")
    assert status == 200, r
    assert len(IA["pedidos"]) == n + 3 and "(fonte: Receita Federal do Brasil)" in IA["pedidos"][-1]["messages"][0]["content"]


def test_frase_do_boletim_pago_nao_fica_nem_citando_e_a_revisao_reescreve(funcao, limpo, request):
    """v0.18.0: do boletim pago (ITC), as frases nunca são reproduzidas: citar a ITC não basta; o material da revisão marca o boletim."""
    carregar_fontes_novas(limpo, request)
    a, c = _assunto_com_texto(limpo)
    boletim = ("Na nossa avaliação a mudança exige atenção redobrada dos departamentos fiscais que ainda não revisaram os cadastros "
               "de produtos antes da virada do ano.")
    itc = limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                           select id, 'https://www.itcnet.com.br/?radar=t1', 'CBS na nota', %s, md5('cbs na nota') from radar_fontes
                           where slug = 'itc-email' returning id""", (boletim,)).fetchone()[0]
    limpo.execute("insert into radar_assunto_capturas values (%s, %s)", (a, itc))
    limpo.execute("update radar_conteudos set corpo = %s where id = %s",
                  ("Segundo a ITC Consultoria, " + boletim[0].lower() + boletim[1:] + "\n\n" + "Texto próprio sobre a CBS. " * 4, c))
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0].isoformat()
    IA["respostas"]["revisao"] = {"titulo": "CBS: o que muda", "pendencias": [],
                                  "corpo": "Segundo o boletim da ITC, vale revisar os cadastros antes do fim do ano.\n\n" + "Texto próprio sobre a CBS. " * 4}
    status, r = pedir("revisar", assunto_id=a, conteudo_id=c, lido=lido)
    assert status == 200, r
    msg = IA["pedidos"][-1]["messages"][0]["content"]
    assert "(BOLETIM PAGO: reescreva com palavras próprias)" in msg and "| BOLETIM PAGO: use só a informação, nunca as frases" in msg
    assert r["copias"] == 1 and r["restam"] == {"marcas": 0, "copias": 0}


def test_revisao_que_volta_cortada_deixa_o_texto_original_com_aviso(funcao, limpo):
    a, _ = _assunto_com_texto(limpo)
    original = "A sessão será em 30 de setembro [VERIFICAR: ano]. " + "Texto próprio sobre a CBS. " * 6
    IA["respostas"]["conteudo"] = {"titulo": "CBS de 0,9% na transição", "titulos": [], "pendencias": [], "corpo": original}
    IA["respostas"]["revisao"] = {"titulo": "CBS", "pendencias": [], "corpo": "Texto próprio sobre a CBS. " * 4}   # bem menor: cortado
    status, r = pedir("gerar", assunto_id=a, formato="flash")
    assert status == 200, r
    corpo, avisos = limpo.execute("select corpo, avisos_ia from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()
    assert corpo == original.strip()
    assert any("marcados com [VERIFICAR]" in x for x in avisos)
    assert any(x.startswith("A revisão automática (marcas e trechos iguais ao da fonte) não pôde ser feita agora (a IA devolveu um texto incompleto)")
               and "Revisar com IA" in x for x in avisos)


def test_revisar_reescreve_um_conteudo_ja_gravado(funcao, limpo):
    a, c = _assunto_com_texto(limpo)
    limpo.execute("update radar_conteudos set corpo = %s, avisos_ia = '[\"aviso antigo\"]' where id = %s",
                  (COPIADO + "O prazo de adesão [VERIFICAR: prazo de adesão] ainda será definido. " + "Texto próprio sobre a CBS. " * 4, c))
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0].isoformat()
    IA["respostas"]["revisao"] = {"titulo": "CBS: o que muda", "pendencias": ["prazo de adesão"],
                                  "corpo": REVISADO + "O prazo de adesão ainda será definido. " + "Texto próprio sobre a CBS. " * 4}
    n = len(IA["pedidos"])
    status, r = pedir("revisar", assunto_id=a, conteudo_id=c, lido="2020-01-01T00:00:00+00:00")     # tela velha: não mexe
    assert status == 409 and len(IA["pedidos"]) == n
    status, r = pedir("revisar", assunto_id=a + 1000, conteudo_id=c, lido=lido)
    assert status == 404
    status, r = pedir("revisar", assunto_id=a, conteudo_id=c, lido=lido)
    assert status == 200, r
    assert r["pendencias"] == ["prazo de adesão"] and r["restam"] == {"marcas": 0, "copias": 0} and r["marcas"] == 1 and r["copias"] == 1
    corpo, avisos, status_c = limpo.execute("select corpo, avisos_ia, status from radar_conteudos where id = %s", (c,)).fetchone()
    assert corpo.startswith(REVISADO.strip()) and status_c == "em_revisao"
    assert avisos[0] == "aviso antigo" and re.fullmatch(r"Revisado com IA em \d\d/\d\d/\d{4}: 1 marca\(s\) ou comentário\(s\) de dúvida e 1 "
                                                         r"trecho\(s\) igual\(is\) ao da fonte sem a fonte citada corrigidos\.", avisos[1])
    assert avisos[2:] == ["Ficou fora do texto por falta de confirmação (confira na fonte oficial antes de publicar): prazo de adesão."]
    assert r["avisos_gravados"] is True and r["titulo_mudou"] is False and r["autorizacao_caiu"] is False
    assert limpo.execute("select acao from radar_ia_uso order by id desc limit 1").fetchone()[0] == "gerar"
    n = len(IA["pedidos"])
    status, r = pedir("revisar", assunto_id=a, conteudo_id=c)                  # nada mais a revisar: nem chama a IA
    assert status == 400 and "não há o que revisar" in r["message"] and len(IA["pedidos"]) == n


def test_revisar_fontes_nao_oficiais_copia_autorizada_titulo_e_pendencias_longas(funcao, limpo, request):
    a, c = _assunto_com_texto(limpo)
    limpo.execute("update radar_fontes set oficial = false, orgao = 'Portal Contábil SC' where slug = 'cgibs-noticias'")
    request.addfinalizer(lambda: limpo.execute("update radar_fontes set oficial = true, orgao = 'Comitê Gestor do IBS' where slug = 'cgibs-noticias'"))
    portal = limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                              select id, 'https://www.cgibs.gov.br/portal', 'Portal: CBS na transição', 'O portal diz que o prazo de adesão vai até 30 de novembro.', md5('portal')
                                from radar_fontes where slug = 'cgibs-noticias' returning id""").fetchone()[0]
    limpo.execute("insert into radar_assunto_capturas values (%s, %s)", (a, portal))
    limpo.execute("update radar_conteudos set titulo = 'CBS [VERIFICAR: alíquota] na transição', corpo = %s where id = %s",
                  (COPIADO + "O prazo de adesão [VERIFICAR: prazo] ainda será definido. " + "Texto próprio sobre a CBS. " * 4, c))
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0]
    with como("authenticated", EDITOR) as x:                                 # a equipe autorizou o trecho igual ao da fonte
        x.execute("select radar_autorizar_copia(%s, 'transcrição do art. 2º da IN', %s)", (c, lido))
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0].isoformat()
    longas = [f"ponto {i:02d} " + "x" * 190 for i in range(30)]
    IA["respostas"]["revisao"] = {"titulo": "CBS de 0,9% na transição", "pendencias": longas,
                                  "corpo": COPIADO + "O prazo de adesão ainda será definido. " + "Texto próprio sobre a CBS. " * 4}
    status, r = pedir("revisar", assunto_id=a, conteudo_id=c, lido=lido)
    assert status == 200, r
    msg = IA["pedidos"][-1]["messages"][0]["content"]
    assert "<<<TEXTO OFICIAL id=" in msg and "<<<TEXTO DE FONTE NÃO OFICIAL id=" in msg and "órgão: Portal Contábil SC" in msg.split("<<<TEXTO DE FONTE NÃO OFICIAL")[1]
    assert "Trechos iguais ao da fonte" not in msg                           # a cópia autorizada não é reescrita: só as marcas
    assert "só no TEXTO DE FONTE NÃO OFICIAL não está confirmado" in IA["pedidos"][-1]["system"]
    assert r["titulo_mudou"] is True and r["autorizacao_caiu"] is True and r["avisos_gravados"] is True
    avisos = limpo.execute("select avisos_ia from radar_conteudos where id = %s", (c,)).fetchone()[0]
    pend = [x for x in avisos if x.startswith("Ficou fora do texto")]
    assert len(pend) == 1 and len(pend[0]) <= 2000 and re.search(r"\(e mais \d+\)\.$", pend[0])   # 30 pontos longos: cabe no limite do banco
    assert limpo.execute("select copia_autorizada_em from radar_conteudos where id = %s", (c,)).fetchone()[0] is None


def test_comentario_de_duvida_sem_colchetes_tambem_pede_a_revisao(funcao, limpo):
    a, _ = _assunto_com_texto(limpo)
    IA["respostas"]["conteudo"] = {"titulo": "CBS de 0,9% na transição", "titulos": [], "pendencias": [],
                                   "corpo": "A sessão será em 30 de setembro (a fonte não especifica o ano). A fonte cita tanto ADI 5.161 quanto ADI nº 5.161/DF. "
                                            + "Texto próprio sobre a CBS. " * 4}
    IA["respostas"]["revisao"] = {"titulo": "CBS de 0,9% na transição", "pendencias": ["ano da sessão"],
                                  "corpo": "A sessão está marcada para 30 de setembro, segundo a ADI nº 5.161/DF. " + "Texto próprio sobre a CBS. " * 4}
    n = len(IA["pedidos"])
    status, r = pedir("gerar", assunto_id=a, formato="flash")
    assert status == 200, r
    assert len(IA["pedidos"]) == n + 2
    msg = IA["pedidos"][-1]["messages"][0]["content"]
    assert "a fonte não especifica o ano" in msg and "A fonte cita tanto ADI 5" in msg
    corpo = limpo.execute("select corpo from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()[0]
    assert "a fonte não especifica" not in corpo and not any("comentário(s) sobre dúvida" in x for x in r["avisos"])



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
