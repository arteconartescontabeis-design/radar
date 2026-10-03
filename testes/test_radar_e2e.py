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
from datetime import date
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


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        status, corpo = PAGINAS.get(self.path, (404, "nao encontrado"))
        dados = corpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
    assert ex == [("ok", 2, 200, "0.5.0", True), ("ok", 1, 200, "0.5.0", True)]
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
    for consulta in ["radar_publicacoes?select=slug,titulo,corpo", "radar_publicacoes?select=criado_por", "radar_imagens?select=id",
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
    for tabela, corpo in [("radar_publicacoes", {"conteudo_id": 1, "slug": "x", "status": "publicado"}),
                          ("radar_auditoria", {"tabela": "x", "registro_id": "1", "acao": "FORJADO"}),
                          ("radar_perfis", {"user_id": "00000000-0000-0000-0000-000000000009", "nome": "x", "papel": "admin"})]:
        assert requests.post(f"{API}/{tabela}", json=corpo, headers=chave, timeout=5).status_code in (401, 403), tabela
    assert requests.delete(f"{API}/radar_capturas?id=gt.0", headers=chave, timeout=5).status_code in (401, 403)
    assert requests.patch(f"{API}/radar_fontes?id=gt.0", json={"oficial": False}, headers=chave, timeout=5).status_code in (401, 403)


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
