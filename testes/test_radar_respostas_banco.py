"""Módulo Respostas Automáticas (v0.35.0): o banco. As três tabelas novas (gatilhos, registro e contas) com RLS, as funções
radar_respostas_* (quem executa cada uma, o que recusam e com que código), a decisão do comentário (radar_respostas_receber: gatilho
ativo, palavra-chave sem maiúsculas/acentos/pontuação, a própria conta, o repetido, o interruptor geral, o limite por hora), a fila
(pendentes dentro da folga e a janela de 7 dias da Meta), o resultado do envio, o reenviar, a situação e o registro da aba.

Dados de mentira: comentários de "Ana Teste" e "Bruno Exemplo", mídias "123"/"456", links exemplo.test; nada real. Cada teste limpa
as tabelas radar_respostas_* e a linha "respostas" de radar_config, antes e depois (o conftest não mexe nelas).
"""
from __future__ import annotations

import json

import psycopg
import pytest

from conftest import ADMIN, EDITOR, LEITOR, como

TABELAS = ("radar_respostas_gatilhos", "radar_respostas_registro", "radar_respostas_contas")
DA_TELA = {"radar_respostas_gatilho_salvar", "radar_respostas_gatilho_mudar", "radar_respostas_gatilho_apagar",
           "radar_respostas_configurar", "radar_respostas_situacao", "radar_respostas_listar", "radar_respostas_reenviar",
           "radar_respostas_publicadas"}
DA_FUNCAO = {"radar_respostas_receber", "radar_respostas_resultado", "radar_respostas_pendentes", "radar_respostas_ha_pendentes",
             "radar_respostas_conta_salvar", "radar_respostas_pagina"}

GATILHO = {"rede": "instagram", "midia_id": "123", "titulo": "Material da CBS", "palavra_chave": "QUERO",
           "resposta_publica": "Mandamos no privado!", "mensagem_privada": "Aqui está o material:",
           "link_material": "https://exemplo.test/material", "limite_hora": 2, "ativo": True}


def limpar(db):
    db.execute("truncate radar_respostas_registro, radar_respostas_gatilhos, radar_respostas_contas restart identity cascade")
    db.execute("delete from radar_config where chave = 'respostas'")


@pytest.fixture()
def resp(limpo):
    limpar(limpo)
    yield limpo
    limpar(limpo)


def chamar(uid, sql, args=()):
    with como("authenticated", uid) as c:
        return c.execute(sql, args).fetchone()[0]


def servico(sql, args=()):
    with como("service_role") as c:
        return c.execute(sql, args).fetchone()[0]


def novo_gatilho(uid=ADMIN, **troca):
    return chamar(uid, "select radar_respostas_gatilho_salvar(null, %s)", (json.dumps({**GATILHO, **troca}),))


def receber(midia="123", comentario="111", autor="555", nome="Ana Teste", texto="Oi, QUERO o material!", rede="instagram"):
    return servico("select radar_respostas_receber(%s, %s, %s, %s, %s, %s)", (rede, midia, comentario, autor, nome, texto))


def recusa(uid, sql, args, codigo):
    with pytest.raises(psycopg.errors.RaiseException) as e, como("authenticated", uid) as c:
        c.execute(sql, args)
    assert codigo in str(e.value), e.value


# ------------------------------------------------------------------------------------- tabelas, RLS e privilégios
def test_tres_tabelas_com_rls_e_ninguem_grava_direto(resp):
    for t in TABELAS:
        rls, forcada = resp.execute("select relrowsecurity, relforcerowsecurity from pg_class where oid = %s::regclass", (t,)).fetchone()
        assert rls, t
    # a equipe lê os gatilhos e as contas; o registro só sai pela função (a regra de reserva é só do administrador)
    novo_gatilho()
    resp.execute("insert into radar_respostas_contas (rede, conta_id, nome) values ('instagram', '777', 'artecon.teste')")
    receber()
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_respostas_gatilhos").fetchone()[0] == 1
        assert c.execute("select count(*) from radar_respostas_contas").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):                  # o registro só sai pela função (sem grant)
            c.execute("select count(*) from radar_respostas_registro")
        c.connection.rollback()
        for t in TABELAS:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"insert into {t} default values")
            c.connection.rollback()


def test_quem_executa_cada_funcao(resp):
    linhas = resp.execute("""select p.proname, coalesce(array_agg(distinct r.grantee::text) filter (where r.privilege_type = 'EXECUTE'), '{}')
                             from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                             left join information_schema.routine_privileges r on r.routine_name = p.proname
                             where n.nspname = 'public' and p.proname like 'radar\\_respostas\\_%'
                             group by p.proname""").fetchall()
    por_nome = {nome: set(donos) for nome, donos in linhas}
    for nome in DA_TELA:
        assert "authenticated" in por_nome[nome] and "anon" not in por_nome[nome], nome
    for nome in DA_FUNCAO:
        assert "service_role" in por_nome[nome] and "authenticated" not in por_nome[nome] and "anon" not in por_nome[nome], nome


# ------------------------------------------------------------------------------------- gatilhos (a tela)
def test_gatilho_so_o_administrador_e_cada_recusa_tem_codigo(resp):
    recusa(EDITOR, "select radar_respostas_gatilho_salvar(null, %s)", (json.dumps(GATILHO),), "RADAR420")
    recusa(LEITOR, "select radar_respostas_configurar(%s)", (json.dumps({"ligado": False}),), "RADAR420")
    gid = novo_gatilho()
    recusa(EDITOR, "select radar_respostas_gatilho_mudar(%s, false)", (gid,), "RADAR420")
    recusa(EDITOR, "select radar_respostas_gatilho_apagar(%s)", (gid,), "RADAR420")
    for troca, codigo in [({"rede": "tiktok"}, "RADAR421"), ({"midia_id": "abc"}, "RADAR422"), ({"midia_id": "_123"}, "RADAR422"),
                          ({"palavra_chave": "a"}, "RADAR423"), ({"palavra_chave": "x" * 41}, "RADAR423"),
                          ({"resposta_publica": " "}, "RADAR424"), ({"resposta_publica": "x" * 501}, "RADAR424"),
                          ({"mensagem_privada": ""}, "RADAR425"), ({"link_material": "http://sem-s.test/x"}, "RADAR426"),
                          ({"link_material": "https://" + "x" * 300}, "RADAR426"), ({"limite_hora": 0}, "RADAR427"),
                          ({"limite_hora": 201}, "RADAR427"), ({"limite_hora": "muitos"}, "RADAR427")]:
        recusa(ADMIN, "select radar_respostas_gatilho_salvar(null, %s)", (json.dumps({**GATILHO, "midia_id": "456", **troca}),), codigo)
    # a mesma publicação não ganha dois gatilhos; editar o que existe pode
    recusa(ADMIN, "select radar_respostas_gatilho_salvar(null, %s)", (json.dumps(GATILHO),), "RADAR422")
    assert chamar(ADMIN, "select radar_respostas_gatilho_salvar(%s, %s)", (gid, json.dumps({**GATILHO, "titulo": "Novo título"}))) == gid
    recusa(ADMIN, "select radar_respostas_gatilho_salvar(%s, %s)", (gid + 99, json.dumps(GATILHO)), "RADAR428")
    recusa(ADMIN, "select radar_respostas_gatilho_mudar(%s, false)", (gid + 99,), "RADAR428")
    recusa(ADMIN, "select radar_respostas_gatilho_apagar(%s)", (gid + 99,), "RADAR428")
    quem, titulo = resp.execute("select criado_por::text, titulo from radar_respostas_gatilhos where id = %s", (gid,)).fetchone()
    assert quem == ADMIN and titulo == "Novo título"
    # o Histórico guarda o gatilho (nunca os comentários dos clientes)
    assert resp.execute("select count(*) from radar_auditoria where tabela = 'radar_respostas_gatilhos'").fetchone()[0] >= 2


def test_configuracao_sempre_completa_e_o_interruptor(resp):
    assert resp.execute("select radar_respostas_cfg()").fetchone()[0] == {"ligado": True}
    assert chamar(ADMIN, "select radar_respostas_configurar(%s)", (json.dumps({"ligado": False}),)) == {"ligado": False}
    recusa(ADMIN, "select radar_respostas_configurar(%s)", (json.dumps({"ligado": "sim"}),), "RADAR427")
    resp.execute("""update radar_config set valor = '"quebrada"' where chave = 'respostas'""")
    assert resp.execute("select radar_respostas_cfg()").fetchone()[0] == {"ligado": True}  # fora do formato: volta ao padrão


# ------------------------------------------------------------------------------------- a decisão do comentário
def test_receber_responde_descarta_e_nunca_em_dobro(resp):
    novo_gatilho()
    resp.execute("insert into radar_respostas_contas (rede, conta_id, nome) values ('instagram', '777', 'artecon.teste')")
    r = receber()
    assert r["acao"] == "responder" and r["resposta_publica"] == "Mandamos no privado!" and r["link"] == "https://exemplo.test/material"
    assert receber() == {"acao": "ignorado", "motivo": "comentário já tratado"}            # o mesmo comentário: uma vez só
    assert receber(comentario="112", texto="parabéns pelo post")["motivo"] == "sem a palavra-chave"
    assert receber(comentario="113", texto="eu ❤ QUERO!!!")["acao"] == "responder"          # pontuação e símbolos não atrapalham
    assert receber(comentario="114", texto="QuÉrO")["acao"] == "responder"                  # maiúsculas e acento
    assert receber(midia="999", comentario="115") == {"acao": "ignorado", "motivo": "sem gatilho ativo para a publicação"}
    assert receber(comentario="116", autor="777", nome="artecon.teste")["motivo"] == "comentário da própria conta"
    assert receber(comentario="x1") == {"acao": "ignorado", "motivo": "pedido fora do formato"}
    # sem gatilho nada é registrado; os descartes com gatilho ficam, com o motivo
    assert resp.execute("select count(*) from radar_respostas_registro where comentario_id = '115'").fetchone()[0] == 0
    assert resp.execute("select situacao, motivo from radar_respostas_registro where comentario_id = '116'").fetchone() == \
        ("descartado", "comentário da própria conta")
    # o texto e o autor entram cortados
    r = receber(comentario="117", texto="QUERO " + "x" * 600, nome="N" * 200)
    assert r["acao"] == "responder"
    tam = resp.execute("select char_length(texto_comentario), char_length(autor_nome) from radar_respostas_registro where comentario_id = '117'").fetchone()
    assert tam == (500, 120)


def test_limite_por_hora_fila_e_resultado(resp):
    gid = novo_gatilho()                                                                    # limite_hora = 2
    r1, r2 = receber(comentario="201"), receber(comentario="202", texto="quero tambem")
    assert r1["acao"] == r2["acao"] == "responder"
    servico("select radar_respostas_resultado(%s, true, '888', true, '')", (r1["registro"],))
    servico("select radar_respostas_resultado(%s, true, '889', false, 'A resposta pública saiu; a mensagem privada não: Meta 10903')",
            (r2["registro"],))
    assert resp.execute("select situacao, privada_ok from radar_respostas_registro where id = %s", (r1["registro"],)).fetchone() == ("enviado", True)
    assert resp.execute("select situacao, privada_ok, erro ~ 'privada' from radar_respostas_registro where id = %s", (r2["registro"],)).fetchone() == \
        ("enviado", False, True)
    r3 = receber(comentario="203", texto="eu QUERO")
    assert r3 == {"acao": "pendente", "registro": r3["registro"], "motivo": "limite por hora: sai na hora seguinte"}
    assert servico("select radar_respostas_ha_pendentes()") is True
    assert servico("select radar_respostas_pendentes(10)") == []                            # sem folga na hora
    resp.execute("update radar_respostas_registro set enviado_em = now() - interval '61 minutes' where situacao = 'enviado'")
    fila = servico("select radar_respostas_pendentes(10)")
    assert [f["comentario_id"] for f in fila] == ["203"] and fila[0]["resposta_publica"] == "Mandamos no privado!"
    # o envio que falhou de vez: erro com a mensagem limpa
    servico("select radar_respostas_resultado(%s, false, '', false, 'Meta 190: token vencido')", (r3["registro"],))
    assert resp.execute("select situacao, erro from radar_respostas_registro where id = %s", (r3["registro"],)).fetchone() == \
        ("erro", "Meta 190: token vencido")
    with pytest.raises(psycopg.errors.RaiseException) as e, como("service_role") as c:
        c.execute("select radar_respostas_resultado(99999, true, '', false, '')")
    assert "RADAR429" in str(e.value)
    # o gatilho desligado segura a fila (e o guarda da agenda não dispara)
    resp.execute("update radar_respostas_registro set situacao = 'pendente', erro = '' where id = %s", (r3["registro"],))
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_respostas_gatilho_mudar(%s, false)", (gid,))
    assert servico("select radar_respostas_ha_pendentes()") is False
    assert servico("select radar_respostas_pendentes(10)") == []


def test_fila_respeita_a_janela_de_7_dias_e_o_interruptor(resp):
    novo_gatilho(**{"limite_hora": 5})
    r = receber(comentario="301")
    resp.execute("update radar_respostas_registro set situacao = 'pendente' where id = %s", (r["registro"],))
    resp.execute("update radar_respostas_registro set criado_em = now() - interval '8 days' where id = %s", (r["registro"],))
    assert servico("select radar_respostas_pendentes(10)") == []
    situacao, erro = resp.execute("select situacao, erro from radar_respostas_registro where id = %s", (r["registro"],)).fetchone()
    assert situacao == "erro" and "7 dias" in erro
    r2 = receber(comentario="302")
    resp.execute("update radar_respostas_registro set situacao = 'pendente' where id = %s", (r2["registro"],))
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_respostas_configurar(%s)", (json.dumps({"ligado": False}),))
    assert servico("select radar_respostas_pendentes(10)") == [] and servico("select radar_respostas_ha_pendentes()") is False


def test_reenviar_so_o_administrador_so_erro_e_dentro_dos_7_dias(resp):
    novo_gatilho()
    r = receber(comentario="401")
    recusa(ADMIN, "select radar_respostas_reenviar(%s)", (r["registro"],), "RADAR429")      # ainda não é erro
    servico("select radar_respostas_resultado(%s, false, '', false, 'Meta 1: erro desconhecido')", (r["registro"],))
    recusa(EDITOR, "select radar_respostas_reenviar(%s)", (r["registro"],), "RADAR420")
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_respostas_reenviar(%s)", (r["registro"],))
    assert resp.execute("select situacao, erro from radar_respostas_registro where id = %s", (r["registro"],)).fetchone() == ("pendente", "")
    resp.execute("update radar_respostas_registro set situacao = 'erro', criado_em = now() - interval '8 days' where id = %s", (r["registro"],))
    recusa(ADMIN, "select radar_respostas_reenviar(%s)", (r["registro"],), "RADAR429")


# ------------------------------------------------------------------------------------- a aba (situação e registro)
def test_situacao_e_registro_para_a_equipe_toda(resp):
    gid = novo_gatilho()
    resp.execute("insert into radar_respostas_contas (rede, conta_id, nome) values ('facebook', '888', 'Artecon Página')")
    r1 = receber(comentario="501")
    servico("select radar_respostas_resultado(%s, true, '900', true, '')", (r1["registro"],))
    receber(comentario="502", texto="só passando")
    s = chamar(LEITOR, "select radar_respostas_situacao()")
    assert s["cfg"] == {"ligado": True} and s["contas"][0]["rede"] == "facebook"
    g = s["gatilhos"][0]
    assert (g["id"], g["ultima_hora"], g["pendentes"], g["enviados"]) == (gid, 1, 0, 1)
    todos = chamar(LEITOR, "select radar_respostas_listar(null, null, 100)")
    assert [x["comentario_id"] for x in todos] == ["502", "501"]
    assert chamar(LEITOR, "select radar_respostas_listar(%s, 'descartado', 100)", (gid,))[0]["motivo"] == "sem a palavra-chave"
    recusa(ADMIN, "select radar_respostas_listar(null, 'qualquer', 100)", (), "RADAR429")
    with pytest.raises(psycopg.errors.RaiseException) as e, como("authenticated", "00000000-0000-0000-0000-000000000009") as c:
        c.execute("select radar_respostas_situacao()")
    assert "RADAR420" in str(e.value)


def test_publicadas_lista_o_que_o_radar_publicou(resp):
    a = resp.execute("insert into radar_assuntos (titulo, situacao_confirmacao, categoria) values ('CBS na transição', 'confirmado_oficialmente', 'federal') returning id").fetchone()[0]
    c1, c2 = [resp.execute("insert into radar_conteudos (assunto_id, formato, titulo, corpo, status, gerado_por) values "
                           "(%s, 'informativo', %s, 'Texto da publicação com tamanho bom.', 'em_revisao', 'humano') returning id",
                           (a, t)).fetchone()[0] for t in ("CBS na transição", "Outra publicação")]
    resp.execute("""insert into radar_redes_envios (conteudo_id, canal, legenda, conteudo_lido_em, situacao, post_id, url, publicado_em)
                    values (%s, 'instagram', 'Legenda de teste da publicação.', now(), 'publicado', '18000000001', 'https://www.instagram.com/p/x1/', now()),
                           (%s, 'facebook', 'Legenda de teste da publicação.', now(), 'publicado', '101_202', 'https://www.facebook.com/x', now() - interval '1 hour'),
                           (%s, 'instagram', 'Legenda de teste da publicação.', now(), 'erro', '18000000002', null, null)""", (c1, c1, c2))
    lista = chamar(LEITOR, "select radar_respostas_publicadas()")
    assert [(x["rede"], x["midia_id"]) for x in lista] == [("instagram", "18000000001"), ("facebook", "101_202")]
    assert lista[0]["titulo"] == "CBS na transição"


def test_conta_salvar_e_pagina(resp):
    servico("select radar_respostas_conta_salvar('facebook', '101', 'Artecon Página')")
    servico("select radar_respostas_conta_salvar('instagram', '777', 'artecon.teste')")
    servico("select radar_respostas_conta_salvar('facebook', '102', 'Artecon Página Nova')")      # troca, sem duplicar
    assert resp.execute("select count(*) from radar_respostas_contas").fetchone()[0] == 2
    assert servico("select radar_respostas_pagina()") == "102"
    with pytest.raises(psycopg.errors.RaiseException) as e, como("service_role") as c:
        c.execute("select radar_respostas_conta_salvar('tiktok', '1', 'x')")
    assert "RADAR421" in str(e.value)
