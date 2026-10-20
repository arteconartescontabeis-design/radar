"""Aba Respostas (v0.35.0) no navegador de verdade (Chromium via Playwright), com o PostgREST e o banco reais. A função
radar-meta-webhook é imitada na própria página (route): a tela só a chama no "Testar conexão", no "Tentar de novo" e nos pendentes.

Confere: a aba (entre a Setor e as Fontes) para todos os perfis, com o aviso "aguardando a Meta"; o leitor vê a situação, os
gatilhos e o registro SEM os controles; o administrador cria o gatilho pelo formulário (inclusive escolhendo uma publicação feita
pelo próprio Radar), edita, desliga, exclui, pausa tudo e retoma; o "Testar conexão" mostra as contas; o filtro do registro; o
"Tentar de novo" de um erro; o texto hostil de um comentário aparece escapado (nunca roda); e o celular a 375 px sem rolagem lateral.

Dados de mentira: comentários de "Ana Teste" e "Bruno Exemplo" em mídias "123"/"456"; nada real.
"""
from __future__ import annotations

import json
import re

import pytest

from conftest import RAIZ
from test_radar_telas import BASE, entrar, navegador, pagina, sem_rolagem_lateral  # noqa: F401  (fixtures)

LEITOR_EMAIL, ADMIN_EMAIL = "leitor@artecon.test", "admin@artecon.test"
VERSAO_TELA = re.search(r'(?m)^const VERSAO = "([^"]+)"', (RAIZ / "index.html").read_text(encoding="utf-8")).group(1)


def limpar(db):
    db.execute("truncate radar_respostas_registro, radar_respostas_gatilhos, radar_respostas_contas restart identity cascade")
    db.execute("delete from radar_config where chave = 'respostas'")


@pytest.fixture()
def tela(pagina, limpo):
    limpar(limpo)
    pagina.db = limpo
    yield pagina
    limpar(limpo)


def cenario(db, hostil=False):
    """Um gatilho com registro variado (respondido, na fila, erro e descartado) e as contas conectadas."""
    gid = db.execute("""insert into radar_respostas_gatilhos (rede, midia_id, titulo, palavra_chave, resposta_publica,
                                                              mensagem_privada, link_material, limite_hora)
                        values ('instagram', '123', 'Material da CBS', 'QUERO', 'Mandamos no privado!', 'Aqui está o material:',
                                'https://exemplo.test/m', 20) returning id""").fetchone()[0]
    db.execute("""insert into radar_respostas_contas (rede, conta_id, nome)
                  values ('facebook', '101', 'Artecon Página Teste'), ('instagram', '777', 'artecon.teste')""")
    texto_erro = "<script>window.__xss=1</script> QUERO <b>já</b>" if hostil else "QUERO, pode mandar"
    db.execute("""insert into radar_respostas_registro
                      (gatilho_id, rede, comentario_id, autor_nome, texto_comentario, situacao, motivo, erro, privada_ok, enviado_em)
                  values (%s, 'instagram', '111', 'Ana Teste', 'Oi, QUERO o material!', 'enviado', '', '', true, now()),
                         (%s, 'instagram', '112', 'Bruno Exemplo', 'quero tambem', 'pendente', 'limite por hora: sai na hora seguinte', '', false, null),
                         (%s, 'instagram', '113', 'Carla Fictícia', %s, 'erro', '', 'Meta 368: bloqueio temporário', false, null),
                         (%s, 'instagram', '114', 'Davi Imaginário', 'bom dia', 'descartado', 'sem a palavra-chave', '', false, null)""",
               (gid, gid, gid, texto_erro, gid))
    return gid


def abrir(pg, email=LEITOR_EMAIL, esperar="#resp-situacao"):
    entrar(pg, email)
    pg.wait_for_selector("nav.abas")
    pg.click("nav.abas button[data-aba=respostas]")
    pg.wait_for_selector(esperar)


def funcao_imitada(pg, respostas, pedidos):
    """A função radar-meta-webhook imitada: cada pedido recebe a próxima resposta (status, corpo) e fica guardado."""
    fila = list(respostas)

    def tratar(rota):
        pedidos.append(json.loads(rota.request.post_data or "{}"))
        status, corpo = fila.pop(0) if fila else (200, {"ok": True, "versao": VERSAO_TELA})
        rota.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))
    pg.route("**/functions/v1/radar-meta-webhook", tratar)


# ------------------------------------------------------------------------------------- quem só lê
def test_leitor_ve_tudo_sem_os_controles_e_o_hostil_nao_roda(tela):
    cenario(tela.db, hostil=True)
    abrir(tela)
    abas = tela.locator("nav.abas button").all_inner_texts()
    assert abas.index("Setor") < abas.index("Respostas") and abas.index("Fontes") == abas.index("Respostas") + 1
    assert "Meta aprovar o acesso avançado" in tela.inner_text("#resp-meta")
    assert "ligadas" in tela.inner_text("#resp-situacao") and "Artecon Página Teste" in tela.inner_text("#resp-contas")
    linha = tela.locator("#resp-gatilhos tr[data-gatilho]")
    assert linha.count() == 1 and "Material da CBS" in linha.inner_text() and "1 de 20" in linha.inner_text()
    # o registro inteiro, com as quatro situações; o comentário hostil aparece como texto e nunca roda
    tabela = tela.inner_text("#resp-tabela")
    for trecho in ("Ana Teste", "respondido", "na fila", "Meta 368", "descartado", "sem a palavra-chave", "<script>"):
        assert trecho in tabela, trecho
    assert tela.evaluate("() => window.__xss === undefined")
    # nada de controle: nem testar, nem pausar, nem novo, nem editar, nem reenviar
    for texto in ("Testar conexão", "Pausar todas", "+ Novo gatilho", "Editar", "Excluir", "Tentar de novo"):
        assert tela.locator(f"button:has-text(\"{texto}\")").count() == 0, texto


def test_celular_375px_sem_rolagem_lateral(navegador, limpo):
    limpar(limpo)
    cenario(limpo)
    contexto = navegador.new_context(viewport={"width": 375, "height": 740}, locale="pt-BR")
    contexto.route(re.compile(r"fonts\.(googleapis|gstatic)\.com"), lambda rota: rota.abort())
    pg = contexto.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    try:
        abrir(pg, ADMIN_EMAIL)
        assert sem_rolagem_lateral(pg), "a aba Respostas"
        pg.click("[data-acao=resp-novo]")
        pg.wait_for_selector("#resp-form")
        assert sem_rolagem_lateral(pg), "o formulário"
        assert erros == [], erros
    finally:
        contexto.close()
        limpar(limpo)


# ------------------------------------------------------------------------------------- o administrador
def test_admin_cria_edita_desliga_e_exclui_o_gatilho(tela):
    # uma publicação feita pelo próprio Radar, para escolher no formulário
    a = tela.db.execute("insert into radar_assuntos (titulo, situacao_confirmacao, categoria) values ('CBS', 'confirmado_oficialmente', 'federal') returning id").fetchone()[0]
    c = tela.db.execute("insert into radar_conteudos (assunto_id, formato, titulo, corpo, status, gerado_por) values "
                        "(%s, 'informativo', 'CBS na transição', 'Texto da publicação de teste.', 'em_revisao', 'humano') returning id", (a,)).fetchone()[0]
    tela.db.execute("""insert into radar_redes_envios (conteudo_id, canal, legenda, conteudo_lido_em, situacao, post_id, url, publicado_em)
                       values (%s, 'instagram', 'Legenda de teste da publicação.', now(), 'publicado', '18000000001',
                               'https://www.instagram.com/p/x1/', now())""", (c,))
    abrir(tela, ADMIN_EMAIL)
    tela.click("[data-acao=resp-novo]")
    tela.wait_for_selector("#resp-form")
    tela.select_option("#resp-publicada", "instagram|18000000001")                    # escolher preenche a rede e o número
    assert tela.input_value("#resp-midia") == "18000000001" and tela.input_value("#resp-rede") == "instagram"
    tela.fill("#resp-titulo", "Material da CBS")
    tela.fill("#resp-chave", "QUERO")
    tela.fill("#resp-publica", "Mandamos no privado!")
    tela.fill("#resp-privada", "Aqui está o material:")
    tela.fill("#resp-link", "https://exemplo.test/m")
    assert "7 dias" in tela.inner_text("#resp-previa")                                # a prévia explica a regra da Meta
    tela.click("#resp-form button:has-text(\"Criar o gatilho\")")
    tela.wait_for_selector("#recado >> text=Gatilho criado")
    assert tela.db.execute("select rede, midia_id, palavra_chave from radar_respostas_gatilhos").fetchone() == \
        ("instagram", "18000000001", "QUERO")
    # editar
    tela.click("[data-acao=resp-editar]")
    tela.wait_for_selector("#resp-form[data-id]")
    tela.fill("#resp-titulo", "Material da CBS (novo)")
    tela.click("#resp-form button:has-text(\"Salvar o gatilho\")")
    tela.wait_for_selector("#recado >> text=Gatilho salvo.")
    # desligar e excluir (os confirm() são aceitos pela fixture)
    tela.click("[data-acao=resp-mudar]")
    tela.wait_for_selector("#recado >> text=Gatilho desligado")
    tela.click("[data-acao=resp-apagar]")
    tela.wait_for_selector("#recado >> text=Gatilho excluído.")
    assert tela.db.execute("select count(*) from radar_respostas_gatilhos").fetchone()[0] == 0
    tela.wait_for_selector("#resp-vazio")


def test_publicacao_fora_do_formato_tem_recado_claro(tela):
    abrir(tela, ADMIN_EMAIL)
    tela.click("[data-acao=resp-novo]")
    tela.wait_for_selector("#resp-form")
    tela.fill("#resp-midia", "https://www.instagram.com/p/abc123/")                   # link do Instagram não vira número
    tela.fill("#resp-chave", "QUERO")
    tela.fill("#resp-publica", "x")
    tela.fill("#resp-privada", "y")
    tela.click("#resp-form button:has-text(\"Criar o gatilho\")")
    tela.wait_for_selector("#recado .erro >> text=Não reconheci a publicação")
    assert tela.db.execute("select count(*) from radar_respostas_gatilhos").fetchone()[0] == 0


def test_pausar_todas_e_retomar(tela):
    cenario(tela.db)
    abrir(tela, ADMIN_EMAIL)
    tela.click("[data-acao=resp-pausar]")                                             # o confirm() é aceito
    tela.wait_for_selector("#recado >> text=Respostas automáticas pausadas.")
    tela.wait_for_selector("#resp-situacao >> text=PAUSADAS")
    assert tela.db.execute("select valor from radar_config where chave = 'respostas'").fetchone()[0] == {"ligado": False}
    tela.click("[data-acao=resp-pausar]")
    tela.wait_for_selector("#recado >> text=Respostas automáticas retomadas.")


def test_testar_conexao_mostra_as_contas(tela):
    pedidos = []
    funcao_imitada(tela, [(200, {"ok": True, "versao": VERSAO_TELA,
                                 "contas": [{"rede": "facebook", "conta_id": "101", "nome": "Artecon Página Teste"},
                                            {"rede": "instagram", "conta_id": "777", "nome": "artecon.teste"}], "avisos": []})], pedidos)
    abrir(tela, ADMIN_EMAIL)
    tela.click("[data-acao=resp-testar]")
    tela.wait_for_selector("#recado >> text=Conexão ok")
    assert pedidos == [{"acao": "diagnostico"}]


def test_filtro_do_registro_e_tentar_de_novo(tela):
    gid = cenario(tela.db)
    pedidos = []
    funcao_imitada(tela, [(200, {"ok": True, "versao": VERSAO_TELA, "pendentes": 2, "enviados": 2, "erros": 0})], pedidos)
    abrir(tela, ADMIN_EMAIL)
    tela.select_option("#resp-f-situacao", "erro")
    tela.click("#resp-registro button:has-text(\"Filtrar\")")
    tela.wait_for_selector("#resp-tabela")
    tabela = tela.inner_text("#resp-tabela")
    assert "Meta 368" in tabela and "Ana Teste" not in tabela
    tela.click("[data-acao=resp-reenviar]")
    tela.wait_for_selector("#recado >> text=Reenviado para a fila")
    assert pedidos == [{"acao": "pendentes"}]
    assert tela.db.execute("select situacao from radar_respostas_registro where comentario_id = '113'").fetchone()[0] in ("pendente", "enviado")
    # a função antiga: o recado em português
    tela.unroute("**/functions/v1/radar-meta-webhook")
    funcao_imitada(tela, [(400, {"message": "Ação desconhecida."})], pedidos)
    tela.db.execute("update radar_respostas_registro set situacao = 'erro', erro = 'Meta 1' where comentario_id = '112'")
    tela.select_option("#resp-f-situacao", "")
    tela.click("#resp-registro button:has-text(\"Filtrar\")")
    tela.wait_for_selector("[data-acao=resp-reenviar]")
    tela.click("[data-acao=resp-reenviar]")
    tela.wait_for_selector("#recado >> text=Reenviado para a fila")                   # o erro da função não trava o reenviar


def test_sem_o_banco_desta_versao_tem_recado(tela):
    tela.db.execute("alter function radar_respostas_situacao() rename to radar_respostas_situacao_x")
    try:
        tela.db.execute("notify pgrst, 'reload schema'")
        abrir(tela, LEITOR_EMAIL, "#resp-sem-banco")
        assert "sql/radar-setup-v0.42.0.sql" in tela.inner_text("#resp-sem-banco")
    finally:
        tela.db.execute("alter function radar_respostas_situacao_x() rename to radar_respostas_situacao")
        tela.db.execute("notify pgrst, 'reload schema'")
