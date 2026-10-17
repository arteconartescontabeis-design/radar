"""Aba Setor (v0.34.0): a função radar-concorrentes de verdade no Deno, com o banco real (PostgREST) e uma Meta (Graph API) de mentira.
Sem o Deno instalado, o arquivo é pulado.

Confere: só o administrador ou a chave do Vault chamam as ações do setor (e só o administrador lê a conta da Artecon); o banco escolhe
quem ler (até 12 por chamada) e a função grava cada conta; os campos pedidos à Meta são EXATAMENTE os oficiais da aba (nada de imagem,
nome, biografia ou site); todo pedido à Meta é GET, só nos caminhos de leitura (nunca publicar, comentar, curtir ou seguir); a mesma @ em
dois setores é lida uma vez; há pausa entre as chamadas; a recusa de limite (4, 17, 32, 613, 80002) e o uso alto informado nos
cabeçalhos param a rodada e gravam a pausa (a chamada seguinte nem chega à Meta); token vencido pausa só a agenda; a Meta ou a rede fora
do ar param a rodada sem falha para as contas (continuam devidas); a conta privada ou que não é comercial volta com erro em português
sem derrubar as outras; curtidas ocultas viram null, a legenda é cortada e as hashtags
vêm da legenda inteira; a agenda lê só as devidas; a hashtag desligada nunca é pedida e, ligada, é buscada uma vez só; o registro (log)
nunca tem token, nome de conta, hashtag, legenda ou link; e a ação "ler" de antes continua igual.

Dados de mentira ("ana.teste", "bruno.exemplo", "artecon.teste"...). A chave fica num Vault simulado (como no teste da radar-concorrentes).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

import test_radar_setor_banco as sb
from conftest import ADMIN, API, EDITOR, LEITOR, RAIZ, SECRETA, conectar, gateway, jwt
from test_radar_funcao_concorrentes import VAULT_SIMULADO, aplicar_sql, recarregar_api

PORTA_PONTE, PORTA_FUNCAO, PORTA_SEM_TOKEN, PORTA_TEMPO, PORTA_SEM_REDE = 3964, 3963, 3962, 3961, 3960
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
IG = "17841400000000001"                        # META_IG_USER_ID da Artecon (de mentira): a conta "artecon.teste"
TOKEN_IG = "EAAsetorSecreto789"
TOKEN_PAGINA = "EAApaginaSetor012"
HID = "17843853986012965"                       # o número da hashtag #contabilidade (de mentira)
CAMPOS_SETOR = ("id,username,followers_count,media_count,"
                "media.limit(50){id,timestamp,media_type,media_product_type,like_count,comments_count,caption,permalink}")
CAMPOS_HASHTAG = "id,media_type,comments_count,like_count,caption,permalink,timestamp"
PROIBIDOS = ("media_url", "thumbnail_url", "view_count", "biography", "website", "follows_count", "{name,", ",name,")
ESTADO: dict = {}
TODOS: list = []                                # todo pedido que chegou à Meta de mentira, de todos os testes (o último confere)


def _posts(u, quantos, base=0):
    agora = datetime.now(timezone.utc)
    lista = []
    for i in range(quantos):
        tipo = ("IMAGE", "VIDEO", "CAROUSEL_ALBUM")[i % 3]
        legenda = f"Dica {i} de {u}: o prazo do Simples Nacional."
        if i == 1:                                   # legenda longa: o segredo e as hashtags depois do 300º caractere
            legenda = "Declaração do Imposto de Renda: " + "texto " * 60 + "LEGENDA_SECRETA #ImpostoDeRenda #MEI #ImpostoDeRenda"
        p = {"id": str(17900000000000000 + base + i), "caption": legenda, "media_type": tipo,
             "media_product_type": "REELS" if tipo == "VIDEO" else "FEED",
             "timestamp": (agora - timedelta(days=1 + i, hours=3)).strftime("%Y-%m-%dT%H:%M:%S+0000"),
             "comments_count": i, "permalink": f"https://www.instagram.com/p/Teste{base + i}/",
             "media_url": f"https://cdn.teste/{u}/{i}.jpg", "thumbnail_url": f"https://cdn.teste/{u}/{i}-capa.jpg", "view_count": 999}
        if i % 4 != 2:
            p["like_count"] = 10 + i                 # sem o campo: curtidas ocultas pelo dono
        lista.append(p)
    return lista


def _conta(u, cid, seguidores, posts, base):
    return {"id": cid, "username": u, "name": "Nome " + u, "biography": "Bio de " + u, "website": "https://site.teste",
            "followers_count": seguidores, "follows_count": 10, "media_count": posts, "posts": _posts(u, posts, base)}


CONTAS = {c["username"]: c for c in [
    _conta("ana.teste", "17841400000000002", 1000, 12, 0), _conta("bruno.exemplo", "17841400000000003", 2000, 5, 100),
    _conta("artecon.teste", IG, 1500, 4, 200), _conta("lenta.teste", "17841400000000004", 500, 3, 300)]
    + [_conta(f"conta{i:02d}", str(17841400000000010 + i), 300, 3, 1000 + 10 * i) for i in range(13)]}
HASHTAG_POSTS = {"top_media": _posts("hashtag", 6, 5000), "recent_media": _posts("recentes", 4, 6000)}


class PonteSetor(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST (pelo gateway do Supabase); /meta → Graph API (Business Discovery e hashtag)."""
    def _responder(self, status, corpo, meta=False):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            if meta:
                for k, v in ESTADO["cabecalhos"].items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(dados)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _rest(self):
        auth = gateway(self.headers)
        if auth is None:
            return self._responder(401, {"message": "Invalid Compact JWS"})
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        cab = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "prefer")} | ({"Authorization": auth} if auth else {})
        r = requests.request(self.command, API + self.path.removeprefix("/rest/v1"), headers=cab, data=corpo, timeout=30)
        self._responder(r.status_code, r.content)

    def _erro(self, status, **e):
        return self._responder(status, {"error": {"type": "OAuthException", "fbtrace_id": "AbC", **e}}, meta=True)

    def _meta(self):
        url = urlparse(self.path)
        caminho = url.path.removeprefix("/meta/")
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        ESTADO["meta"].append({"metodo": self.command, "caminho": caminho, "campos": q.get("fields", ""), "q": q, "hora": time.monotonic()})
        TODOS.append(ESTADO["meta"][-1])
        if self.command != "GET":
            return self._erro(405, code=100, message="só leitura nesta Meta de mentira")
        if q.get("access_token") != TOKEN_IG or ESTADO["token_recusado"]:
            return self._erro(400, code=190, message=f"Invalid OAuth access token - Cannot parse access token {q.get('access_token')}")
        if ESTADO["erro_depois"] is not None:
            ESTADO["erro_depois"] -= 1
            if ESTADO["erro_depois"] < 0:
                codigo, msg = ESTADO["erro"]
                return self._erro(400, code=codigo, message=f"{msg} {TOKEN_IG}")
        if caminho in ESTADO["erro_caminho"]:
            codigo, msg = ESTADO["erro_caminho"][caminho]
            return self._erro(400, code=codigo, message=msg)
        if caminho == "ig_hashtag_search":
            if ESTADO["hashtag_erro"]:
                codigo, msg = ESTADO["hashtag_erro"]
                return self._erro(400, code=codigo, message=msg)
            return self._responder(200, {"data": [{"id": HID}] if q.get("q") == "contabilidade" and q.get("user_id") == IG else []}, meta=True)
        m = re.fullmatch(rf"{HID}/(top_media|recent_media)", caminho)
        if m:
            cmp = q.get("fields", "").split(",")
            return self._responder(200, {"data": [{k: v for k, v in p.items() if k in cmp} for p in HASHTAG_POSTS[m.group(1)]]}, meta=True)
        if caminho != IG:
            return self._erro(400, code=100, error_subcode=33, message="Unsupported get request")
        campos = q.get("fields", "")
        if campos == "username":
            return self._responder(200, {"username": "artecon.teste", "id": IG}, meta=True)
        mm = re.fullmatch(r"business_discovery\.username\(([^)]*)\)\{(.*)\}", campos)
        mi = mm and re.search(r"media(?:\.after\(([^)]*)\))?\.limit\((\d+)\)\{([^}]*)\}", mm.group(2))
        if not mi:
            return self._erro(400, code=100, message="(#100) Syntax error")
        u = mm.group(1)
        conta_campos = [c for c in mm.group(2)[:mi.start()].split(",") if c]
        cursor, limite, cmp = mi.group(1), int(mi.group(2)), mi.group(3).split(",")
        if u in ESTADO["atraso"]:
            time.sleep(ESTADO["atraso"][u])
        if u in ESTADO["erro_de"]:
            codigo, msg = ESTADO["erro_de"][u]
            return self._erro(500, code=codigo, message=msg)
        conta = CONTAS.get(u)
        if conta is None:
            return self._erro(400, code=110, error_subcode=2207013, message="Invalid user id", error_user_msg=f"The user with username: {u} cannot be found.")
        inicio = int(cursor) if cursor else 0
        fatia = min(limite, ESTADO["max_pagina"] or limite)
        media = {"data": [{k: v for k, v in p.items() if k in cmp} for p in conta["posts"][inicio:inicio + fatia]]}
        if inicio + fatia < len(conta["posts"]):
            media["paging"] = {"cursors": {"after": str(inicio + fatia)}}
        bd = {"media": media} | {k: conta[k] for k in conta_campos if k in conta}
        self._responder(200, {"business_discovery": bd, "id": IG}, meta=True)

    def do_GET(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        if self.path.startswith("/meta/"):
            return self._meta()
        self._responder(404, {})

    def do_POST(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        if self.path.startswith("/meta/"):
            return self._meta()
        self._responder(404, {})

    do_DELETE = do_PUT = do_POST

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def chave(banco_pronto, tmp_path_factory):
    """Vault simulado + sql/radar-concorrentes.sql (a chave que a agenda do setor usa); tudo sai no fim do módulo."""
    with conectar() as c:
        tinha_vault = c.execute("select count(*) from pg_namespace where nspname = 'vault'").fetchone()[0] == 1
        if not tinha_vault:
            c.execute(VAULT_SIMULADO)
    try:
        aplicar_sql(tmp_path_factory.mktemp("setor-chave"))
        with conectar() as c:
            yield c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_concorrentes'").fetchone()[0]
    finally:
        with conectar() as c:
            c.execute("drop function if exists public.radar_concorrentes_conferir(text)")
            if tinha_vault:
                c.execute("delete from vault.secrets where name = 'radar_concorrentes'")
            else:
                c.execute("drop schema vault cascade")
            c.execute("notify pgrst, 'reload schema'")


def _subir(porta, extra, registro):
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), META_GRAPH_URL=PONTE + "/meta",
                    RADAR_PORTA_LOCAL=str(porta), NO_COLOR="1")
    for nome in ("SUPABASE_SECRET_KEYS", "SUPABASE_SERVICE_ROLE_KEY", "META_IG_TOKEN", "META_PAGE_TOKEN", "META_IG_USER_ID",
                 "RADAR_CONCORRENTES_ORCAMENTO_MS", "RADAR_CONCORRENTES_PRAZO_MS", "RADAR_SETOR_PAUSA_MS"):
        ambiente.pop(nome, None)
    ambiente.update(extra)
    proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                             str(RAIZ / "supabase" / "functions" / "radar-concorrentes" / "index.ts")],
                            env=ambiente, stdout=registro, stderr=subprocess.STDOUT)
    for _ in range(150):
        try:
            requests.options(f"http://127.0.0.1:{porta}/", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.2)
    return proc


@pytest.fixture(scope="module")
def funcao(api_postgrest, chave, tmp_path_factory):
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    recarregar_api()
    pasta = tmp_path_factory.mktemp("registros-setor")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), PonteSetor)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    meta_ok = {"META_IG_USER_ID": IG, "META_IG_TOKEN": TOKEN_IG, "META_PAGE_TOKEN": TOKEN_PAGINA, "RADAR_SETOR_PAUSA_MS": "200",
               "SUPABASE_SERVICE_ROLE_KEY": SECRETA, "SUPABASE_SECRET_KEYS": json.dumps({"default": SECRETA})}
    processos, arquivos = [], []
    try:
        for porta, extra in ((PORTA_FUNCAO, meta_ok),
                             (PORTA_SEM_TOKEN, {"META_IG_USER_ID": IG, "SUPABASE_SERVICE_ROLE_KEY": jwt("service_role")}),
                             (PORTA_TEMPO, {**meta_ok, "RADAR_CONCORRENTES_ORCAMENTO_MS": "4000", "RADAR_CONCORRENTES_PRAZO_MS": "3900"}),
                             (PORTA_SEM_REDE, {**meta_ok, "META_GRAPH_URL": "http://127.0.0.1:9/meta"})):     # porta fechada: a Meta fora do ar
            arquivos.append(open(pasta / f"{porta}.log", "wb"))
            processos.append(_subir(porta, extra, arquivos[-1]))
        yield pasta
    finally:
        for p in processos:
            p.terminate()
        for p in processos:
            p.wait(timeout=10)
        for a in arquivos:
            a.close()
        ponte.shutdown()
        ponte.server_close()


@pytest.fixture()
def meta(funcao, limpo):
    ESTADO.update(meta=[], cabecalhos={}, token_recusado=False, erro=None, erro_depois=None, hashtag_erro=None, atraso={}, max_pagina=None,
                  erro_de={}, erro_caminho={})
    sb.limpar(limpo)
    yield limpo
    sb.limpar(limpo)


def pedir(corpo, uid=ADMIN, porta=PORTA_FUNCAO, cab=None, timeout=90):
    cab = cab if cab is not None else {"Authorization": "Bearer " + jwt("authenticated", uid)}
    r = requests.post(f"http://127.0.0.1:{porta}/", timeout=timeout, json=corpo, headers=cab)
    return r.status_code, r.json()


def coletar(**k):
    return pedir({"acao": "setor_coletar"}, **k)


def bd(usuario=None):
    """Os pedidos de Business Discovery (os campos), de uma conta ou de todas."""
    return [m["campos"] for m in ESTADO["meta"] if m["campos"].startswith("business_discovery") and (usuario is None or f"username({usuario})" in m["campos"])]


def setor_com(db, texto, nome="Contabilidade"):
    sid = sb.novo_setor(nome)
    sb.incluir(sid, texto)
    return sid


# ------------------------------------------------------------------------------------- quem chama
def test_so_o_administrador_ou_a_chave(meta, chave):
    setor_com(meta, "@ana.teste")
    for uid in (EDITOR, LEITOR):
        assert coletar(uid=uid)[0] == 403
    assert coletar(cab={})[0] == 401
    assert coletar(cab={"x-radar-chave": "0" * 64})[0] == 401
    assert pedir({"acao": "setor_propria"}, cab={"x-radar-chave": chave})[0] == 403          # a conta da Artecon, só o administrador
    assert pedir({"acao": "setor_teste"}, cab={"x-radar-chave": chave}) == (200, {"ok": True, "versao": sb_versao()})
    assert pedir({"acao": "setor_teste"}) == (200, {"ok": True, "versao": sb_versao()})
    assert ESTADO["meta"] == []                                                             # nada disso chegou à Meta
    assert meta.execute("select count(*) from radar_setor_coletas").fetchone()[0] == 0


def sb_versao():
    return re.search(r'(?m)^const VERSAO = "([^"]+)"', (RAIZ / "supabase" / "functions" / "radar-concorrentes" / "index.ts").read_text()).group(1)


# ------------------------------------------------------------------------------------- a leitura
def test_administrador_le_e_grava_com_os_campos_oficiais_e_so_get(meta):
    setor_com(meta, "@ana.teste @bruno.exemplo @artecon.teste")
    status, r = coletar()
    assert status == 200 and (r["lidas"], r["com_erro"], r["faltam"], r["chamadas"]) == (3, 0, 0, 3), r
    assert r["versao"] == sb_versao() and [c["nome"] for c in r["contas"]] == ["ana.teste", "bruno.exemplo", "artecon.teste"]
    assert bd() == [f"business_discovery.username({u}){{{CAMPOS_SETOR}}}" for u in ("ana.teste", "bruno.exemplo", "artecon.teste")]
    assert all(not any(p in m["campos"] for p in PROIBIDOS) for m in ESTADO["meta"])
    assert all(m["metodo"] == "GET" and m["caminho"] == IG and m["q"]["access_token"] == TOKEN_IG for m in ESTADO["meta"])
    contas = {n: (s, t, mid, p, pe, e) for n, s, t, mid, p, pe, e in meta.execute(
        "select nome, seguidores, posts_total, meta_id, propria, pedida_em, erro from radar_setor_contas").fetchall()}
    assert contas == {"ana.teste": (1000, 12, "17841400000000002", False, None, None), "bruno.exemplo": (2000, 5, "17841400000000003", False, None, None),
                      "artecon.teste": (1500, 4, IG, True, None, None)}
    assert meta.execute("select count(*) from radar_setor_posts").fetchone()[0] == 12 + 5 + 4
    k = meta.execute("select origem, contas, lidas, com_erro, posts, chamadas, terminada_em is not null, pausa_ate from radar_setor_coletas").fetchone()
    assert k == ("admin", 3, 3, 0, 21, 3, True, None)
    # nada mais a ler: a chamada seguinte não chega à Meta
    ESTADO["meta"] = []
    assert coletar() == (200, {"versao": sb_versao(), "motivo": "nada"}) and ESTADO["meta"] == []


def test_curtidas_ocultas_legenda_cortada_e_hashtags_da_legenda_inteira(meta):
    setor_com(meta, "@ana.teste")
    assert coletar()[1]["lidas"] == 1
    posts = {m: (c, n, h, t, f) for m, c, n, h, t, f in meta.execute(
        "select midia_id, curtidas, char_length(legenda), hashtags, temas, formato from radar_setor_posts").fetchall()}
    assert posts["17900000000000002"][0] is None                                         # sem like_count: curtidas ocultas
    longa = posts["17900000000000001"]
    assert longa[1] == 300 and longa[2] == ["impostoderenda", "mei"]                      # depois do corte, mas na legenda inteira
    assert "Imposto de Renda" in longa[3] and "MEI" in longa[3] and longa[4] == "reel"
    assert meta.execute("select count(*) from radar_setor_posts where legenda like '%LEGENDA_SECRETA%'").fetchone()[0] == 0


def test_a_mesma_conta_em_dois_setores_e_lida_uma_vez(meta):
    a = setor_com(meta, "@ana.teste", "Setor A")
    b = setor_com(meta, "@ana.teste", "Setor B")
    status, r = coletar()
    assert status == 200 and r["lidas"] == 1 and len(bd()) == 1, r
    assert meta.execute("""select c.setor_id, count(*) from radar_setor_posts p join radar_setor_contas c on c.id = p.conta_id
                           group by 1 order by 1""").fetchall() == [(a, 12), (b, 12)]


def test_pausa_entre_as_chamadas_e_doze_contas_por_vez(meta):
    setor_com(meta, " ".join(f"@conta{i:02d}" for i in range(13)))
    status, r = coletar()
    assert status == 200 and (r["lidas"], r["faltam"], r["chamadas"]) == (12, 1, 12), r
    horas = [m["hora"] for m in ESTADO["meta"]]
    assert min(b - a for a, b in zip(horas, horas[1:])) >= 0.19                         # RADAR_SETOR_PAUSA_MS=200 nesta instância
    status, r = coletar()
    assert (r["lidas"], r["faltam"]) == (1, 0) and len(bd()) == 13


@pytest.mark.parametrize("codigo", [4, 17, 32, 613, 80002])
def test_limite_da_meta_para_na_hora_e_pausa(meta, codigo):
    setor_com(meta, "@ana.teste @bruno.exemplo @artecon.teste")
    ESTADO.update(erro=(codigo, "Application request limit reached"), erro_depois=1)
    status, r = coletar()
    assert status == 200 and r["lidas"] == 1 and r["com_erro"] == 1 and len(ESTADO["meta"]) == 2, r
    assert "limite de chamadas da Meta" in r["geral"] and TOKEN_IG not in json.dumps(r)
    pausa = meta.execute("select extract(epoch from pausa_ate - now()) / 60, pausa_motivo from radar_setor_coletas").fetchone()
    assert 58 <= pausa[0] <= 60.5 and pausa[1] == "limite"
    # ninguém leva falha; a que recebeu a recusa e a que nem foi pedida continuam pedidas
    assert meta.execute("select max(falhas_consecutivas), count(*) filter (where pedida_em is not null) from radar_setor_contas").fetchone() == (0, 2)
    ESTADO.update(meta=[], erro_depois=None)
    status, r = coletar()
    assert status == 200 and r["motivo"] == "pausa" and r["pausa_ate"] and ESTADO["meta"] == []
    assert meta.execute("select radar_setor_ha_devidas()").fetchone()[0] is False


def test_uso_alto_informado_pela_meta_para_depois_daquela_conta(meta):
    setor_com(meta, "@ana.teste @bruno.exemplo")
    ESTADO["cabecalhos"] = {"x-app-usage": json.dumps({"call_count": 85, "total_cputime": 10, "total_time": 12})}
    status, r = coletar()
    assert status == 200 and r["lidas"] == 1 and len(ESTADO["meta"]) == 1 and "85%" in r.get("geral", ""), r
    assert meta.execute("select round(extract(epoch from pausa_ate - now()) / 60), uso_max from radar_setor_coletas").fetchone() == (60, 85)
    sb.limpar(meta)
    setor_com(meta, "@ana.teste @bruno.exemplo")
    ESTADO.update(meta=[], cabecalhos={"x-business-use-case-usage": json.dumps({"1234": [{"type": "instagram", "call_count": 81,
                                                                                          "estimated_time_to_regain_access": 90}]})})
    assert coletar()[1]["lidas"] == 1
    assert meta.execute("select round(extract(epoch from pausa_ate - now()) / 60) from radar_setor_coletas").fetchone()[0] == 90
    sb.limpar(meta)
    setor_com(meta, "@ana.teste @bruno.exemplo")
    ESTADO.update(meta=[], cabecalhos={"x-app-usage": "isto não é JSON"})                  # ilegível: ignora
    assert coletar()[1]["lidas"] == 2


def test_token_vencido_pausa_so_a_agenda(meta, chave):
    setor_com(meta, "@ana.teste @bruno.exemplo")
    ESTADO["token_recusado"] = True
    status, r = coletar()
    assert status == 200 and r["lidas"] == 0 and len(ESTADO["meta"]) == 1, r
    assert "META_IG_TOKEN" in r["geral"] and "190" in r["geral"] and TOKEN_IG not in json.dumps(r)
    assert meta.execute("select erro from radar_setor_contas where nome = 'ana.teste'").fetchone()[0].startswith("o token da Meta venceu")
    assert meta.execute("select pausa_motivo, round(extract(epoch from pausa_ate - now()) / 3600) from radar_setor_coletas").fetchone() == ("configuracao", 6)
    ESTADO["meta"] = []
    assert coletar(cab={"x-radar-chave": chave})[1]["motivo"] == "pausa" and ESTADO["meta"] == []      # a agenda espera
    ESTADO["token_recusado"] = False                                                      # o administrador trocou o token e testa
    status, r = coletar()
    assert r["lidas"] == 2 and "geral" not in r
    assert meta.execute("select count(*) from radar_setor_pausa_em(now())").fetchone()[0] == 0          # a pausa de configuração caiu


def test_meta_fora_do_ar_para_a_rodada_e_ninguem_leva_falha(meta, chave):
    """Revisão da v0.34.0: sem conseguir falar com a Meta (rede), a rodada para na 1ª conta, nenhuma conta leva falha nem fica "tentada"
    na semana (a agenda tenta de novo na hora seguinte, sem pausa) e, de volta a Meta, todas são lidas."""
    setor_com(meta, "@ana.teste @bruno.exemplo @artecon.teste")
    meta.execute("update radar_setor_contas set pedida_em = null")                       # a agenda: nunca lidas, devidas na semana
    status, r = coletar(porta=PORTA_SEM_REDE, cab={"x-radar-chave": chave})
    assert status == 200 and (r["lidas"], r["com_erro"], r["chamadas"]) == (0, 1, 1), r
    assert "não foi possível falar com a Meta" in r["geral"] and "pausa_ate" not in r
    assert meta.execute("""select max(falhas_consecutivas), count(*) filter (where tentada_em is not null),
                                  count(*) filter (where erro_codigo = 'rede') from radar_setor_contas""").fetchone() == (0, 0, 1)
    assert meta.execute("select pausa_ate, codigos from radar_setor_coletas").fetchone() == (None, "rede")
    assert meta.execute("select radar_setor_ha_devidas()").fetchone()[0] is True                 # a agenda tenta de novo
    status, r = coletar(cab={"x-radar-chave": chave})                                    # a Meta voltou
    assert (r["lidas"], r["com_erro"]) == (3, 0) and "geral" not in r, r
    assert meta.execute("select max(erro), max(falhas_consecutivas) from radar_setor_contas").fetchone() == (None, 0)


def test_meta_instavel_em_duas_contas_seguidas_para_sem_falha_e_numa_so_a_falha_e_dela(meta):
    setor_com(meta, "@ana.teste @bruno.exemplo @artecon.teste")
    ESTADO.update(erro=(2, "Service temporarily unavailable"), erro_depois=0)            # a Meta responde "indisponível" a tudo
    status, r = coletar()
    assert status == 200 and (r["lidas"], r["com_erro"], r["chamadas"]) == (0, 2, 2) and "pausa_ate" not in r, r
    assert "Meta 2" in r["geral"] and TOKEN_IG not in json.dumps(r)
    assert meta.execute("""select max(falhas_consecutivas), count(*) filter (where tentada_em is null), count(*) filter (where pedida_em is not null)
                             from radar_setor_contas""").fetchone() == (0, 3, 3)                 # ninguém leva falha; todas continuam pedidas
    # só uma conta com o código 2 (a seguinte leu): a falha é só dela, como antes
    sb.limpar(meta)
    setor_com(meta, "@ana.teste @bruno.exemplo @artecon.teste")
    ESTADO.update(meta=[], erro=None, erro_depois=None, erro_de={"bruno.exemplo": (2, "Service temporarily unavailable")})
    status, r = coletar()
    assert (r["lidas"], r["com_erro"]) == (2, 1) and "geral" not in r, r
    assert meta.execute("select nome, falhas_consecutivas, tentada_em is not null from radar_setor_contas where falhas_consecutivas > 0").fetchall() == [
        ("bruno.exemplo", 1, True)]


def test_conta_privada_ou_que_nao_e_comercial_so_ela_tem_erro(meta):
    setor_com(meta, "@ana.teste @pessoal.privada @bruno.exemplo")
    status, r = coletar()
    assert status == 200 and (r["lidas"], r["com_erro"]) == (2, 1), r
    erro, codigo, falhas, pedida = meta.execute("select erro, erro_codigo, falhas_consecutivas, pedida_em from radar_setor_contas where nome = 'pessoal.privada'").fetchone()
    assert "privada ou que não é comercial/criador" in erro and codigo == "110/2207013" and falhas == 1 and pedida is None


def test_sem_tempo_o_resto_continua_devido_sem_falha(meta):
    setor_com(meta, "@lenta.teste @ana.teste @bruno.exemplo @artecon.teste")
    ESTADO["atraso"] = {"lenta.teste": 1.2, "ana.teste": 1.2}
    status, r = coletar(porta=PORTA_TEMPO, timeout=30)
    assert status == 200 and 1 <= r["lidas"] < 4 and r["com_erro"] == 0 and r["faltam"] >= 1, r
    assert meta.execute("select max(falhas_consecutivas), max(erro) from radar_setor_contas").fetchone() == (0, None)


def test_sem_o_meta_ig_token_explica_e_nao_chama_a_meta(meta):
    setor_com(meta, "@ana.teste")
    status, r = coletar(porta=PORTA_SEM_TOKEN)
    assert status == 503 and "META_IG_TOKEN" in r["message"] and ESTADO["meta"] == []


# ------------------------------------------------------------------------------------- a agenda e a hashtag
def test_agenda_le_so_as_devidas_e_respeita_a_leitura_desligada(meta, chave):
    setor_com(meta, "@ana.teste @bruno.exemplo")
    meta.execute("update radar_setor_contas set pedida_em = null")
    meta.execute("update radar_setor_contas set coletada_em = now() where nome = 'ana.teste'")          # lida nesta semana
    status, r = coletar(cab={"x-radar-chave": chave})
    assert status == 200 and r["lidas"] == 1 and bd() == [f"business_discovery.username(bruno.exemplo){{{CAMPOS_SETOR}}}"], r
    assert meta.execute("select origem from radar_setor_coletas").fetchone()[0] == "agenda"
    meta.execute("update radar_setor_contas set coletada_em = null, tentada_em = null")
    meta.execute("""insert into radar_config (chave, valor) values ('setor', '{"coleta_ligada": false}')""")
    ESTADO["meta"] = []
    assert coletar(cab={"x-radar-chave": chave}) == (200, {"versao": sb_versao(), "motivo": "desligada"}) and ESTADO["meta"] == []


def test_hashtag_desligada_nunca_e_pedida_e_ligada_e_buscada_uma_vez(meta):
    setor_com(meta, "#contabilidade @ana.teste")
    status, r = coletar()
    assert r["lidas"] == 1 and all(m["caminho"] == IG for m in ESTADO["meta"]), r              # desligada: só a conta
    meta.execute("""insert into radar_config (chave, valor) values ('setor', '{"hashtag_ligada": true}')""")
    ESTADO["meta"] = []
    status, r = coletar()
    assert r["lidas"] == 1 and [m["caminho"] for m in ESTADO["meta"]] == ["ig_hashtag_search", f"{HID}/top_media"], r
    busca, top = ESTADO["meta"]
    assert busca["q"]["user_id"] == IG and busca["q"]["q"] == "contabilidade"
    assert top["campos"] == CAMPOS_HASHTAG and top["q"]["limit"] == "50" and top["q"]["user_id"] == IG
    assert meta.execute("select meta_id, buscada_em is not null, seguidores from radar_setor_contas where tipo = 'hashtag'").fetchone() == (HID, True, None)
    assert meta.execute("""select count(*) from radar_setor_posts p join radar_setor_contas c on c.id = p.conta_id where c.tipo = 'hashtag'""").fetchone()[0] == 6
    # a rodada seguinte não busca o número de novo; no modo "ambos", também as recentes
    meta.execute("update radar_config set valor = valor || '{\"hashtag_modo\": \"ambos\"}' where chave = 'setor'")
    meta.execute("update radar_setor_contas set pedida_em = now() where tipo = 'hashtag'")
    ESTADO["meta"] = []
    assert coletar()[1]["lidas"] == 1
    assert [m["caminho"] for m in ESTADO["meta"]] == [f"{HID}/top_media", f"{HID}/recent_media"]
    painel = sb.chamar(LEITOR, "select radar_setor_painel(%s, 90)", (meta.execute("select id from radar_setor_setores").fetchone()[0],))
    assert painel["hashtags"][0]["nome"] == "contabilidade" and painel["hashtags"][0]["n"] == 10


def test_hashtag_buscada_conta_para_as_30_mesmo_com_a_leitura_falhando_depois(meta):
    """Revisão da v0.34.0: a busca do número (ig_hashtag_search) deu certo e a leitura das publicações falhou: a busca fica registrada
    na rodada (a Meta conta) e o número fica guardado (a próxima rodada não busca de novo)."""
    setor_com(meta, "#contabilidade")
    meta.execute("""insert into radar_config (chave, valor) values ('setor', '{"hashtag_ligada": true}')""")
    ESTADO["erro_caminho"] = {f"{HID}/top_media": (100, "Unsupported get request")}
    status, r = coletar()
    assert status == 200 and (r["lidas"], r["com_erro"]) == (0, 1), r
    assert meta.execute("select meta_id, buscada_em is not null, falhas_consecutivas from radar_setor_contas").fetchone() == (HID, True, 1)
    assert meta.execute("select radar_setor_buscadas_em(now())").fetchone()[0] == 1
    ESTADO.update(meta=[], erro_caminho={})
    meta.execute("update radar_setor_contas set pedida_em = now()")
    assert coletar()[1]["lidas"] == 1 and [m["caminho"] for m in ESTADO["meta"]] == [f"{HID}/top_media"]


def test_recusa_da_hashtag_em_portugues_e_as_contas_seguem(meta):
    setor_com(meta, "#contabilidade #mei @ana.teste")
    meta.execute("""insert into radar_config (chave, valor) values ('setor', '{"hashtag_ligada": true}')""")
    ESTADO["hashtag_erro"] = (10, "(#10) To use 'Instagram Public Content Access', your use of this endpoint must be reviewed and approved by Facebook.")
    status, r = coletar()
    assert status == 200 and (r["lidas"], r["com_erro"]) == (1, 2) and "geral" not in r, r
    assert [m["caminho"] for m in ESTADO["meta"]].count("ig_hashtag_search") == 1                # a 2ª hashtag nem é pedida
    erros = [e for (e,) in meta.execute("select erro from radar_setor_contas where tipo = 'hashtag'").fetchall()]
    assert all(e.startswith("a Meta ainda não liberou a busca por hashtag") for e in erros)
    assert meta.execute("select count(*) from radar_setor_pausa_em(now())").fetchone()[0] == 0           # a recusa da hashtag não pausa
    sb.limpar(meta)
    setor_com(meta, "#contabilidade")
    meta.execute("""insert into radar_config (chave, valor) values ('setor', '{"hashtag_ligada": true}')""")
    ESTADO.update(meta=[], hashtag_erro=(24, "You have reached the limit of 30 unique hashtags in 7 days"))
    coletar()
    assert meta.execute("select erro from radar_setor_contas").fetchone()[0].startswith("limite da Meta: 30 hashtags diferentes a cada 7 dias")


# ------------------------------------------------------------------------------------- a conta da Artecon, o teste e o que não muda
def test_conta_da_artecon_e_o_teste_da_agenda(meta):
    status, r = pedir({"acao": "setor_propria"})
    assert status == 200 and r == {"versao": sb_versao(), "usuario": "artecon.teste"}
    assert [(m["caminho"], m["campos"]) for m in ESTADO["meta"]] == [(IG, "username")]
    ESTADO["meta"] = []
    assert pedir({"acao": "setor_teste"})[1]["ok"] is True and ESTADO["meta"] == []
    assert pedir({"acao": "setor_apagar_tudo"}) == (400, {"message": "Ação desconhecida."})


def test_a_acao_ler_continua_igual(meta):
    status, r = pedir({"perfis": ["ana.teste"], "posts": 3})
    assert status == 200 and set(r["perfis"][0]) == {"usuario", "ok", "conta", "posts"}, r          # o número da conta não sai
    assert set(r["perfis"][0]["conta"]) == {"username", "name", "biografia", "site", "seguidores", "seguindo", "posts_total"}
    assert "media_url" in ESTADO["meta"][0]["campos"]                                    # a ação de antes pede os mesmos campos de antes
    assert meta.execute("select count(*) from radar_setor_coletas").fetchone()[0] == 0     # e não grava nada


def test_cabecalho_da_funcao_diz_o_que_ela_grava():
    """Revisão da v0.34.0: o começo do arquivo público não pode dizer que a função "não grava nada no banco": desde a aba Setor, a
    setor_coletar grava as métricas (radar_setor_*). Na Meta, continua só GET."""
    fonte = (RAIZ / "supabase" / "functions" / "radar-concorrentes" / "index.ts").read_text(encoding="utf-8")
    comeco = fonte[:fonte.index("// Quem pode chamar")]
    assert "não grava nada no banco" not in comeco and "SOMENTE LEITURA" not in comeco
    assert "Na Meta, só lê (GET)" in comeco and "setor_coletar\" grava no banco" in comeco and "300 caracteres" in comeco


def test_so_leitura_e_registro_sem_nomes(meta, chave, funcao):
    """Roda no fim: nenhum pedido à Meta (de nenhum teste deste arquivo) foi além de ler; e o registro (log) das 4 instâncias."""
    setor_com(meta, "@ana.teste @pessoal.privada")
    assert coletar()[0] == 200
    assert coletar(porta=PORTA_SEM_TOKEN)[0] == 503
    assert all(m["metodo"] == "GET" for m in TODOS)
    for porta in (PORTA_FUNCAO, PORTA_SEM_TOKEN, PORTA_TEMPO, PORTA_SEM_REDE):
        registro = (funcao / f"{porta}.log").read_text()
        for proibido in (TOKEN_IG, TOKEN_PAGINA, "ana.teste", "bruno", "artecon.teste", "pessoal", "conta0", "lenta", "contabilidade", "LEGENDA_SECRETA",
                         "instagram.com", "access_token", "Dica "):
            assert proibido not in registro, (porta, proibido)
    registro = (funcao / f"{PORTA_FUNCAO}.log").read_text()
    assert re.search(r"radar-concorrentes \(admin\): setor, 2 conta\(s\), 1 lida\(s\), 1 com erro, 12 post\(s\), 2 chamada\(s\), códigos da Meta: 110/2207013\n", registro)
    assert "radar-concorrentes (chave): setor, " in registro




def test_todo_pedido_a_meta_foi_so_de_leitura():
    """Todos os pedidos que chegaram à Meta de mentira neste arquivo: só GET e só nos caminhos de leitura (nada de /media,
    /media_publish, /comments, /likes, seguir, POST ou DELETE)."""
    assert len(TODOS) > 50
    for m in TODOS:
        assert m["metodo"] == "GET" and (m["caminho"] in (IG, "ig_hashtag_search") or re.fullmatch(rf"{HID}/(top|recent)_media", m["caminho"])), m
