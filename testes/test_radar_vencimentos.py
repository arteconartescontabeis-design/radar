"""Quadro de vencimentos de chaves e contas e registro da cópia mensal do banco no OneDrive (v0.32.0): o banco (radar_vencimentos,
radar_copias, as funções radar_vencimento*, radar_copia_conferir_agenda e radar_copias_*, e os dois tipos novos de lembrete,
"vencimento" e "copia") e os textos do robô dos lembretes (robo/radar_lembretes.py).

Confere: só o administrador lê e grava o quadro (RLS), e ninguém grava o registro das cópias pela API; o gatilho recusa o valor de uma
chave e o link que não é https; "Acrescentar os vencimentos conhecidos" põe os nove sem data e não duplica; "Renovei" pede uma data
depois de hoje (de Brasília); o lembrete do vencimento sai 30, 7 e 1 dia antes e no dia, cada marco uma vez só, sem acumular o que
passou, num e-mail só por dia, com só o número e a data; o lembrete da cópia só depois das três tentativas da agenda e só para quem já
configurou; a exportação só com a chave da agenda (Vault) ou o administrador, nunca com a chave de serviço sozinha; a lista de tabelas
da função radar-copia é a do banco; nenhuma coluna com nome de segredo; os textos exatos do robô; e o setup duas vezes.

As funções dos lembretes recebem a hora (p_agora) e as datas são fixas (16:00 de Brasília de terça-feira, 03/11/2026). Nomes de mentira
("Ana Teste", "Bruno Exemplo") e domínio .test.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest

from conftest import ADMIN, EDITOR, LEITOR, RAIZ, SETUP, VAULT_SIMULADO, como, conectar, jwt, psql
from test_radar_banco import _sem_transacao, nova_captura, novo_assunto
from test_radar_lembretes import AGORA, LOTE, RODAPE, abertas, configurar, devidos, enviado, grupo, lote_em, mandar, observar

import radar_lembretes

FUSO = ZoneInfo("America/Sao_Paulo")
CODIGOS = ["azure_assinatura", "azure_copia_segredo", "azure_itc_segredo", "dominio_artecon", "github_corretor_video", "github_robo_site",
           "meta_token", "microsoft_365", "supabase_plano"]
PADRAO = {"ligado": True, "hora": "16:00", "de": "08:00", "ate": "20:00", "aprovacao_horas": 24, "parada_horas": 3, "pauta": True,
          "aprovacao": True, "video": True, "noticia": True, "vencimento": True, "copia": True}
FUNCAO = RAIZ / "supabase" / "functions" / "radar-copia" / "index.ts"


@pytest.fixture()
def quadro(limpo):
    """O quadro, o registro das cópias e a chave "lembretes" vazios antes e depois (com data no quadro, os lembretes dos outros testes
    mudariam). No fim, a chave "lembretes" volta ao que era."""
    antes = limpo.execute("select valor from radar_config where chave = 'lembretes'").fetchone()

    def zerar():
        limpo.execute("delete from radar_vencimentos")
        limpo.execute("delete from radar_copias")
        limpo.execute("delete from radar_config where chave = 'lembretes'")
        limpo.execute("truncate radar_lembretes")
    zerar()
    yield limpo
    zerar()
    if antes:
        limpo.execute("insert into radar_config (chave, valor) values ('lembretes', %s)", (json.dumps(antes[0]),))


def item(db, nome="Chave de teste", vence="2026-12-03", **campos) -> int:
    """Um item do quadro gravado direto (como o administrador gravaria pela tela)."""
    campos = {"nome": nome, "vence_em": vence, **campos}
    return db.execute(f"insert into radar_vencimentos ({', '.join(campos)}) values ({', '.join(['%s'] * len(campos))}) returning id",
                      tuple(campos.values())).fetchone()[0]


def copia(db, mes: str, ok: bool | None, iniciado: str | None = None) -> int:
    """Uma linha do registro das cópias (mes = "AAAA-MM-01")."""
    inicio = iniciado or mes + " 07:10+00"
    return db.execute("""insert into radar_copias (mes, origem, iniciado_em, concluido_em, ok, arquivo, erro)
                         values (%s, 'agenda', %s, %s, %s, %s, %s) returning id""",
                      (mes, inicio, None if ok is None else inicio, ok, f"radar-copia-{mes}-0410.zip",
                       "O OneDrive recusou o acesso." if ok is False else None)).fetchone()[0]


def hoje_br():
    return datetime.now(FUSO).date()


# ---------------------------------------------------------------------------------------------------- tabelas, RLS e gatilho
def test_tabelas_novas_com_rls_e_so_o_administrador(quadro):
    with como("authenticated", ADMIN) as c:
        vid = c.execute("insert into radar_vencimentos (nome, tipo, vence_em) values ('Domínio de teste', 'dominio', '2027-01-10') returning id").fetchone()[0]
        assert c.execute("select nome, tipo, ativo from radar_vencimentos where id = %s", (vid,)).fetchone() == ("Domínio de teste", "dominio", True)
        c.execute("update radar_vencimentos set observacao = 'Renovação automática' where id = %s", (vid,))
        assert c.execute("select count(*) from radar_copias").fetchone()[0] == 0                   # o administrador lê o registro
        for sql in ["insert into radar_copias (mes, origem, arquivo) values ('2026-11-01', 'admin', 'radar-copia-2026-11-01-0410.zip')",
                    "update radar_copias set ok = true", "delete from radar_copias"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):                              # …mas não grava: só as funções
                c.execute(sql)
    quadro.execute("insert into radar_copias (mes, origem, arquivo) values ('2026-11-01', 'admin', 'radar-copia-2026-11-01-0410.zip')")
    for uid in (EDITOR, LEITOR):
        with como("authenticated", uid) as c:
            assert c.execute("select count(*) from radar_vencimentos").fetchone()[0] == 0
            assert c.execute("select count(*) from radar_copias").fetchone()[0] == 0
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("insert into radar_vencimentos (nome) values ('Conta de teste')")
            assert c.execute("update radar_vencimentos set nome = 'Outro nome' where id = %s returning id", (vid,)).fetchall() == []
            assert c.execute("delete from radar_vencimentos where id = %s returning id", (vid,)).fetchall() == []
    for papel in ("anon", "service_role"):                         # o visitante e a chave dos robôs (repositório público): nada
        with como(papel) as c:
            for sql in ["select * from radar_vencimentos", "select * from radar_copias", "select id from radar_copias",
                        "insert into radar_vencimentos (nome) values ('Conta de teste')"]:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    c.execute(sql)
    assert quadro.execute("select nome, observacao from radar_vencimentos where id = %s", (vid,)).fetchone() == ("Domínio de teste",
                                                                                                                 "Renovação automática")
    with como("authenticated", ADMIN) as c:
        assert c.execute("delete from radar_vencimentos where id = %s returning id", (vid,)).fetchall() == [(vid,)]
    # as sequências e as colunas: nada para o visitante nem para a equipe
    for tabela in ("radar_vencimentos", "radar_copias"):
        seq = quadro.execute("select pg_get_serial_sequence(%s, 'id')", ("public." + tabela,)).fetchone()[0]
        for papel in ("anon", "authenticated", "service_role"):
            assert quadro.execute("select has_sequence_privilege(%s, %s, 'usage')", (papel, seq)).fetchone()[0] is False
    assert quadro.execute("""select count(*) from information_schema.column_privileges where table_schema = 'public'
                             and table_name in ('radar_vencimentos', 'radar_copias') and grantee in ('anon', 'service_role', 'PUBLIC')""").fetchone()[0] == 0


def _jwt_qualquer():
    return jwt("anon")                               # o formato de um JWT (eyJ….eyJ….…)


SEGREDOS = [("ghp_" + "A1b2" * 9, "token do GitHub"), ("github_pat_" + "11ABCDEFG0" * 3, "token fino do GitHub"),
            ("sb_secret_" + "x1Y2" * 6, "chave interna do Supabase"), ("iagw_radar_" + "k9" * 10, "token da IA Central"),
            ("abc8Q~" + "Ab1.-~_x" * 5, "segredo do Azure"), (None, "JWT"), ("EAA" + "B7c" * 14, "token da Meta"),
            ("-----BEGIN PRIVATE KEY-----", "chave privada"), ("z" * 45, "45 caracteres sem espaço")]


def test_gatilho_recusa_valor_de_chave_e_link_que_nao_e_https(quadro):
    db = quadro
    for valor, _ in SEGREDOS:
        valor = valor or _jwt_qualquer()
        for campo in ("nome", "onde_renovar", "observacao"):
            dados = {"nome": "Chave de teste", campo: ("Chave " + valor)[:120] if campo == "nome" else "Valor: " + valor}
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR360: isto parece o valor de uma chave"):
                item(db, **dados)
    assert db.execute("select count(*) from radar_vencimentos").fetchone()[0] == 0
    # o que não é chave passa: o NOME da chave, um GUID, um endereço https longo, o caminho em palavras
    ok = item(db, nome="  Chave do robô do site (RADAR_GITHUB_TOKEN)  ", observacao="Aplicativo 8b3c1d2e-1111-4a2b-9c3d-0123456789ab",
              onde_renovar="https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade/quickStartType~/null/sourceType/Microsoft_AAD_IAM")
    item(db, nome="Domínio de teste", onde_renovar="registro.br → Domínios → artecon.test → Renovar", observacao="   ")
    assert db.execute("select nome from radar_vencimentos where id = %s", (ok,)).fetchone()[0] == "Chave do robô do site (RADAR_GITHUB_TOKEN)"
    assert db.execute("select observacao from radar_vencimentos where nome = 'Domínio de teste'").fetchone()[0] is None   # vazio vira null
    for link in ("http://exemplo.test/renovar", "javascript:alert(1)", "data:text/html,oi", "HTTP://EXEMPLO.TEST"):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR361: o link de onde renovar precisa começar com https://"):
            item(db, nome="Conta de teste", onde_renovar=link)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR360"):
        db.execute("update radar_vencimentos set observacao = %s where id = %s", ("cole aqui: ghp_" + "Z9" * 18, ok))
    antes = db.execute("select atualizado_em from radar_vencimentos where id = %s", (ok,)).fetchone()[0]
    db.execute("update radar_vencimentos set vence_em = '2027-02-01' where id = %s", (ok,))
    assert db.execute("select atualizado_em from radar_vencimentos where id = %s", (ok,)).fetchone()[0] > antes
    for campo, valor in [("nome", "x"), ("nome", "N " * 61), ("tipo", "senha"), ("vence_em", "1999-12-31"), ("codigo", "Maiúsculo"),
                         ("onde_renovar", "a " * 251), ("observacao", "a " * 501)]:
        with pytest.raises(psycopg.errors.CheckViolation):
            item(db, **{"nome": "Conta de teste", campo: valor})
    # na trilha (Histórico), com quem fez
    marca = db.execute("select coalesce(max(id), 0) from radar_auditoria").fetchone()[0]
    with como("authenticated", ADMIN) as c:
        novo = c.execute("insert into radar_vencimentos (nome, tipo) values ('Conta do Bruno Exemplo', 'conta') returning id").fetchone()[0]
    assert db.execute("select tabela, registro_id, acao, usuario::text from radar_auditoria where id > %s", (marca,)).fetchall() == [
        ("radar_vencimentos", str(novo), "INSERT", ADMIN)]


def test_espaco_rigido_e_outros_espacos_unicode_nao_parecem_chave(quadro):
    """v0.32.0 (revisão): o texto colado do Word, do Outlook ou de uma página traz o espaço rígido (U+00A0). O [[:space:]] do banco não o
    via como espaço (C.UTF-8 e glibc) e recusava o caminho inofensivo com RADAR360, que a tela aceitava. Agora os dois lados trocam a
    mesma lista de espaços (a do \\s do JavaScript) por um espaço comum antes do teste."""
    db = quadro
    nb = "\u00a0"
    inofensivos = [f"admin.microsoft.com{nb}→{nb}Cobrança{nb}→{nb}Seus{nb}produtos{nb}→{nb}Microsoft{nb}365",
                   f"Renovar{nb}no{nb}registro.br{nb}antes{nb}do{nb}vencimento{nb}do{nb}domínio",
                   "Renovar\u2009no\u202fregistro.br\u3000antes\u2007do\u205fvencimento\ufeffdo\u1680domínio\u2028e\u2029conferir\u000bo\u000caviso"]
    parece = lambda t: db.execute("select radar_vencimento_parece_segredo(%s)", (t,)).fetchone()[0]
    assert [parece(t) for t in inofensivos] == [False, False, False]
    with como("authenticated", ADMIN) as c:
        c.execute("insert into radar_vencimentos (nome, tipo, onde_renovar, observacao) values (%s, 'assinatura', %s, %s)",
                  (f"Assinatura{nb}do{nb}Microsoft{nb}365", inofensivos[0], inofensivos[2]))
    assert db.execute("select count(*) from radar_vencimentos").fetchone()[0] == 1
    # o que parece chave continua parecendo, com qualquer espaço em volta
    assert parece(nb + "z" * 40 + nb) is True and parece("\u3000ghp_" + "A1b2" * 9) is True
    assert parece("z" * 20 + nb + "z" * 20) is False and parece(f"https://exemplo.test/{'a' * 50}{nb}fim") is False


def test_conhecidos_sem_data_e_sem_duplicar(quadro):
    db = quadro
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_vencimentos_conhecidos()").fetchone()[0] == 9
        assert c.execute("select radar_vencimentos_conhecidos()").fetchone()[0] == 0              # de novo: nada
    linhas = db.execute("select codigo, vence_em, ativo, tipo, nome, onde_renovar from radar_vencimentos order by codigo").fetchall()
    assert [l[0] for l in linhas] == CODIGOS and all(l[1] is None and l[2] for l in linhas)
    assert {l[0]: l[3] for l in linhas}["dominio_artecon"] == "dominio" and {l[0]: l[3] for l in linhas}["github_robo_site"] == "chave"
    assert all(l[5] for l in linhas)                                                              # todos com onde renovar
    assert db.execute("""select count(*) from radar_vencimentos where radar_vencimento_parece_segredo(nome)
                         or radar_vencimento_parece_segredo(onde_renovar) or radar_vencimento_parece_segredo(observacao)""").fetchone()[0] == 0
    db.execute("delete from radar_vencimentos where codigo = 'github_robo_site'")
    db.execute("update radar_vencimentos set nome = 'Domínio do escritório', vence_em = '2027-03-01' where codigo = 'dominio_artecon'")
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_vencimentos_conhecidos()").fetchone()[0] == 1              # só o apagado volta
    assert db.execute("select count(*) from radar_vencimentos").fetchone()[0] == 9
    assert db.execute("select nome, vence_em::text from radar_vencimentos where codigo = 'dominio_artecon'").fetchone() == (
        "Domínio do escritório", "2027-03-01")                                                    # o que foi editado fica
    for uid in (EDITOR, LEITOR):
        with como("authenticated", uid) as c:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR362: só o administrador mexe no quadro de vencimentos"):
                c.execute("select radar_vencimentos_conhecidos()")


def test_conhecidos_nao_duplica_o_que_foi_incluido_a_mao(quadro):
    """v0.32.0 (revisão): o item que o administrador já incluiu à mão (sem codigo) conta como já no quadro, pelo nome (sem diferença de
    maiúsculas e espaços) ou pelo nome do segredo entre parênteses. Antes, o segredo das cópias, anotado com data logo depois da
    Parte 1 do passo a passo, voltava sem data pelo botão."""
    db = quadro
    with como("authenticated", ADMIN) as c:
        c.execute("""insert into radar_vencimentos (nome, tipo, vence_em)
                     values ('Segredo das cópias no Entra (COPIA_CLIENT_SECRET)', 'chave', '2027-10-17')""")
        c.execute("insert into radar_vencimentos (nome, tipo) values ('  Domínio   ARTECON.cnt.br ', 'dominio')")
        c.execute("insert into radar_vencimentos (nome, tipo) values ('Token do corretor de vídeo (RADAR_VIDEO_GITHUB_TOKEN)', 'chave')")
        assert c.execute("select radar_vencimentos_conhecidos()").fetchone()[0] == 6
        assert c.execute("select radar_vencimentos_conhecidos()").fetchone()[0] == 0
    codigos = [k for (k,) in db.execute("select codigo from radar_vencimentos where codigo is not null order by codigo")]
    assert codigos == [k for k in CODIGOS if k not in ("azure_copia_segredo", "dominio_artecon", "github_corretor_video")]
    assert "github_robo_site" in codigos                                  # RADAR_VIDEO_GITHUB_TOKEN não é o RADAR_GITHUB_TOKEN
    assert db.execute("select count(*) from radar_vencimentos where nome ilike '%COPIA_CLIENT_SECRET%'").fetchone()[0] == 1
    assert db.execute("select vence_em::text from radar_vencimentos where nome ilike '%COPIA_CLIENT_SECRET%'").fetchone()[0] == "2027-10-17"


def test_renovei(quadro):
    db = quadro
    vid = item(db, vence="2026-12-03")
    nova = hoje_br() + timedelta(days=400)
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_vencimentos_renovei(%s, %s)", (vid, nova))
        for data in (hoje_br(), hoje_br() - timedelta(days=1), None):
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR365: a nova data de vencimento precisa ser depois de hoje"):
                c.execute("select radar_vencimentos_renovei(%s, %s)", (vid, data))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR367: item do quadro de vencimentos não encontrado"):
            c.execute("select radar_vencimentos_renovei(%s, %s)", (vid + 100000, nova))
    assert db.execute("select vence_em, renovado_em is not null from radar_vencimentos where id = %s", (vid,)).fetchone() == (nova, True)
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR362"):
            c.execute("select radar_vencimentos_renovei(%s, %s)", (vid, nova + timedelta(days=1)))
    # o servidor noutro fuso (UTC+14): o "hoje" é o de Brasília (amanhã de Brasília vale, mesmo quando já é depois de amanhã lá)
    with conectar() as c:
        c.execute("set timezone = 'Pacific/Kiritimati'")
        c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"role": "authenticated", "sub": ADMIN}),))
        c.execute("set role authenticated")
        c.execute("select radar_vencimentos_renovei(%s, %s)", (vid, hoje_br() + timedelta(days=1)))
    assert db.execute("select vence_em from radar_vencimentos where id = %s", (vid,)).fetchone()[0] == hoje_br() + timedelta(days=1)


# ------------------------------------------------------------------------------------------------------------ "vencimento"
def avisadas(db, tipo):
    return [k for (k,) in db.execute("select chave from radar_lembretes where tipo = %s and avisado_em is not null order by id", (tipo,))]


def test_vencimento_30_7_1_e_no_dia_cada_marco_uma_vez(quadro):
    db = quadro
    v = item(db, vence="2026-12-03")                                                       # 30 dias depois de 03/11
    assert devidos(db, "2026-11-03 10:59+00") == []                                         # 07:59: fora do horário ("de" 08:00)
    assert devidos(db, "2026-11-03 11:00+00") == ["vencimento"]
    g = grupo(db, "vencimento", "2026-11-03 11:00+00")
    assert [(i["n"], i["data"], i["situacao"], i["hora"], i["formato"], i["canal"]) for i in g["itens"]] == [
        (v, "2026-12-03", "30", None, None, None)]
    assert db.execute("select chave, ref from radar_lembretes where tipo = 'vencimento'").fetchall() == [
        (f"vencimento:{v}:2026-12-03:30", {"n": v, "data": "2026-12-03", "situacao": "30"})]
    assert enviado(db, g["lote"], 90, [g["itens"][0]["id"]], "2026-11-03 11:00+00") == 1
    assert devidos(db, "2026-11-03 19:00+00") == []                                         # um e-mail por tipo por dia
    assert devidos(db, "2026-11-04 12:00+00") == []                                         # 29 dias: o marco 30 já foi
    for agora, situacao, marco in [("2026-11-26 12:00+00", "7", 7), ("2026-12-02 12:00+00", "1", 1), ("2026-12-03 12:00+00", "hoje", 0)]:
        assert devidos(db, agora) == ["vencimento"], agora
        assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora=agora)] == [(v, situacao)]
        assert avisadas(db, "vencimento")[-1] == f"vencimento:{v}:2026-12-03:{marco}"
        assert devidos(db, agora.replace("12:00", "15:00")) == []
    assert devidos(db, "2026-12-04 12:00+00") == []                                         # vencido: o marco do dia já foi
    assert devidos(db, "2026-12-20 12:00+00") == []
    assert len(avisadas(db, "vencimento")) == 4
    # "Renovei": a data nova (sem marco ainda); as pendências da data antiga fecham e nada sai
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_vencimentos_renovei(%s, '2027-12-03')", (v,))
    assert devidos(db, "2026-12-21 12:00+00") == []
    assert db.execute("select count(*) from radar_lembretes where tipo = 'vencimento' and resolvido_em is null").fetchone()[0] == 0


def test_marco_perdido_nao_acumula(quadro):
    db = quadro
    configurar(db, vencimento=False)                                                        # desligado do dia 30 ao dia 8
    v1 = item(db, vence="2026-12-03")
    assert devidos(db, "2026-11-03 12:00+00") == []
    assert list(abertas(db)) == [f"vencimento:{v1}:2026-12-03:30"]                          # observado, sem e-mail
    assert devidos(db, "2026-11-25 12:00+00") == []                                         # 8 dias: ainda o marco 30
    configurar(db, vencimento=True)                                                         # religado a 7 dias: só o 7
    assert devidos(db, "2026-11-26 12:00+00") == ["vencimento"]
    assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-11-26 12:00+00")] == [(v1, "7")]
    assert db.execute("select avisado_em is null, resolvido_em is not null from radar_lembretes where chave = %s",
                      (f"vencimento:{v1}:2026-12-03:30",)).fetchone() == (True, True)        # o 30 fechou sem e-mail
    v2 = item(db, nome="Conta de teste", vence="2026-12-02")                                # incluído a 5 dias: vale o marco 7
    assert devidos(db, "2026-11-27 12:00+00") == ["vencimento"]
    assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-11-27 12:00+00")] == [(v2, "5")]
    assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-12-01 12:00+00")] == [(v2, "1")]
    assert sorted((i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-12-02 12:00+00")) == sorted([(v1, "1"), (v2, "hoje")])
    assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-12-03 12:00+00")] == [(v1, "hoje")]
    assert devidos(db, "2026-12-04 12:00+00") == []
    v3 = item(db, nome="Assinatura de teste", vence="2026-12-01")                          # incluída já vencida: um lembrete, "vencido"
    assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-12-05 12:00+00")] == [(v3, "vencido")]
    assert devidos(db, "2026-12-06 12:00+00") == []


def test_marco_avisado_nao_volta_ao_desligar_e_religar_nem_ao_voltar_a_data(quadro):
    """v0.32.0 (revisão): o marco que já foi a um e-mail não volta. Antes, desligar e religar o item ("lembrar deste item"), ou trocar a
    data e voltar à de antes, fechava o episódio avisado, e o mesmo marco ia a outro e-mail."""
    db = quadro
    v = item(db, vence="2026-12-03")
    assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-11-03 12:00+00")] == [(v, "30")]
    db.execute("update radar_vencimentos set ativo = false where id = %s", (v,))             # "lembrar deste item" desmarcado
    observar(db, "2026-11-04 12:00+00")
    db.execute("update radar_vencimentos set ativo = true where id = %s", (v,))              # e marcado de novo
    assert devidos(db, "2026-11-05 12:00+00") == []
    db.execute("update radar_vencimentos set vence_em = '2026-12-05' where id = %s", (v,))   # outra data: o marco 30 dela é novo
    assert [(i["n"], i["data"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-11-06 12:00+00")] == [(v, "2026-12-05", "29")]
    db.execute("update radar_vencimentos set vence_em = '2026-12-03' where id = %s", (v,))   # e a de antes de novo: o 30 já foi
    assert devidos(db, "2026-11-07 12:00+00") == []
    assert avisadas(db, "vencimento") == [f"vencimento:{v}:2026-12-03:30", f"vencimento:{v}:2026-12-05:30"]
    assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-11-26 12:00+00")] == [(v, "7")]   # o próximo marco vale
    # a cópia do mês: também uma vez só (o episódio avisado que fechou não volta no mesmo mês)
    db.execute("delete from radar_vencimentos")
    copia(db, "2026-10-01", True)
    assert [i["data"] for i in mandar(db, "copia", agora="2026-12-02 11:00+00")] == ["2026-12-01"]
    boa = copia(db, "2026-12-01", True, "2026-12-02 13:00+00")
    observar(db, "2026-12-02 14:00+00")
    db.execute("delete from radar_copias where id = %s", (boa,))
    assert devidos(db, "2026-12-03 12:00+00") == [] and "copia:2026-12" not in abertas(db)


def test_sem_enxurrada_um_email_com_todos_os_itens_do_dia(quadro):
    db = quadro
    ids = [item(db, nome=f"Item de teste {k}", vence="2026-12-03") for k in range(9)]
    assert devidos(db) == ["vencimento"]
    g = grupo(db, "vencimento")
    assert sorted(i["n"] for i in g["itens"]) == ids and {i["situacao"] for i in g["itens"]} == {"30"}
    assert enviado(db, g["lote"], 78, [i["id"] for i in g["itens"]]) == 9                  # um e-mail só, com os nove
    dez = item(db, nome="Item de teste 10", vence="2026-12-03")                             # depois do e-mail do dia: espera
    assert devidos(db, "2026-11-03 19:30+00") == [] and f"vencimento:{dez}:2026-12-03:30" in abertas(db)
    assert devidos(db, "2026-11-04 10:59+00") == []                                         # 07:59 do dia seguinte: fora do horário
    assert devidos(db, "2026-11-04 23:01+00") == []                                         # 20:01: idem
    assert [(i["n"], i["situacao"]) for i in mandar(db, "vencimento", agora="2026-11-04 11:00+00")] == [(dez, "29")]
    # sem data ou desligado: nada; desligar, apagar ou tirar a data fecha o que estava aberto
    item(db, nome="Sem data de teste", vence=None)
    onze, doze, treze = (item(db, nome=f"Item de teste {k}", vence="2026-12-05") for k in (11, 12, 13))
    observar(db, "2026-11-05 12:00+00")
    assert set(abertas(db)) == {f"vencimento:{x}:2026-12-05:30" for x in (onze, doze, treze)}
    db.execute("update radar_vencimentos set ativo = false where id = %s", (onze,))
    db.execute("delete from radar_vencimentos where id = %s", (doze,))
    db.execute("update radar_vencimentos set vence_em = null where id = %s", (treze,))
    assert devidos(db, "2026-11-05 12:00+00") == [] and abertas(db) == {}
    assert db.execute("select count(*) from radar_lembretes where resolvido_em is null and avisado_em is null").fetchone()[0] == 0


def test_nada_de_nome_no_ref_nem_no_lote(quadro):
    db = quadro
    v = item(db, nome="Chave da Ana Teste", observacao="Bruno Exemplo renova", onde_renovar="https://exemplo.test/renovar/ana-teste")
    lote = lote_em(db)
    assert [g["tipo"] for g in lote] == ["vencimento"] and lote[0]["itens"][0]["n"] == v
    refs = [r for (r,) in db.execute("select ref from radar_lembretes").fetchall()]
    for texto in [json.dumps(lote, ensure_ascii=False), json.dumps(refs, ensure_ascii=False)] + [radar_lembretes.corpo(g["tipo"], g) for g in lote]:
        for nome in ("Ana", "Teste", "Bruno", "Exemplo", "Chave da", "exemplo.test"):
            assert nome not in texto, (nome, texto)


# ------------------------------------------------------------------------------------------------------------------ "copia"
def test_copia_so_depois_das_tentativas_e_so_quem_configurou(quadro):
    db = quadro
    observar(db, "2026-11-02 12:00+00")
    assert not any(k.startswith("copia:") for k in abertas(db))                            # nunca configurou: nada
    copia(db, "2026-10-01", True)                                                           # a cópia já deu certo em outubro
    for agora in ("2026-11-02 02:59+00", "2026-11-02 08:59+00"):                            # 01/11 23:59 e 02/11 05:59 de Brasília
        observar(db, agora)
        assert "copia:2026-11" not in abertas(db), agora
    observar(db, "2026-11-02 09:00+00")                                                     # 02/11 às 06:00: depois das três tentativas
    assert abertas(db)["copia:2026-11"] == {"data": "2026-11-01"}
    assert devidos(db, "2026-11-02 10:59+00") == []                                         # 07:59: fora do horário
    assert devidos(db, "2026-11-02 11:00+00") == ["copia"]
    assert [i["data"] for i in mandar(db, "copia", agora="2026-11-02 11:00+00")] == ["2026-11-01"]
    assert devidos(db, "2026-11-03 11:00+00") == []                                         # uma vez só no mês
    copia(db, "2026-11-01", True, "2026-11-03 14:00+00")                                    # a cópia boa chega: fecha
    observar(db, "2026-11-03 15:00+00")
    assert db.execute("select resolvido_em is not null from radar_lembretes where chave = 'copia:2026-11'").fetchone()[0] is True
    # sem cópia em novembro: o episódio de novembro fecha na virada do mês, e o de dezembro só no dia 2 às 06:00
    db.execute("truncate radar_lembretes")
    db.execute("delete from radar_copias where mes = '2026-11-01'")
    observar(db, "2026-11-10 12:00+00")
    assert "copia:2026-11" in abertas(db)
    observar(db, "2026-12-01 12:00+00")
    assert not any(k.startswith("copia:") for k in abertas(db))
    observar(db, "2026-12-02 09:00+00")
    assert list(k for k in abertas(db) if k.startswith("copia:")) == ["copia:2026-12"]
    # o primeiro mês: só uma falha registrada (nunca deu certo) também lembra
    db.execute("truncate radar_lembretes")
    db.execute("delete from radar_copias")
    copia(db, "2026-11-01", False, "2026-11-01 07:10+00")
    assert devidos(db, "2026-11-02 11:00+00") == ["copia"]
    configurar(db, copia=False)                                                             # desligado: nada
    assert devidos(db, "2026-11-02 11:30+00") == []


def test_falta_mes_e_em_andamento(quadro):
    db = quadro
    falta = lambda: db.execute("select radar_copias_falta_mes()").fetchone()[0]
    assert falta() is True                                                                  # sem cópia
    mes = db.execute("select date_trunc('month', now() at time zone 'America/Sao_Paulo')::date").fetchone()[0]
    db.execute("""insert into radar_copias (mes, origem, iniciado_em, concluido_em, ok, arquivo)
                  values (%s, 'admin', now() - interval '1 hour', now() - interval '59 minutes', true, 'radar-copia-2026-10-17-1000.zip')""", (mes,))
    assert falta() is False                                                                 # o mês já tem cópia (mesmo a feita à mão)
    db.execute("delete from radar_copias")
    db.execute("""insert into radar_copias (mes, origem, iniciado_em, concluido_em, ok, arquivo)
                  values ((%s - interval '1 month')::date, 'admin', now() - interval '40 days', now() - interval '40 days', true,
                          'radar-copia-2026-09-01-0410.zip')""", (mes,))
    assert falta() is True                                                                  # a do mês passado não vale por este
    antiga = db.execute("""insert into radar_copias (mes, origem, iniciado_em, arquivo)
                           values (%s, 'admin', now() - interval '5 minutes', 'radar-copia-2026-10-17-1001.zip') returning id""", (mes,)).fetchone()[0]
    assert falta() is False                                                                 # em andamento há 5 minutos
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR364: já há uma cópia em andamento"):
            c.execute("select radar_copias_comecar('')")
    db.execute("update radar_copias set iniciado_em = now() - interval '20 minutes' where id = %s", (antiga,))
    assert falta() is True                                                                  # parada há 20 minutos: a agenda tenta de novo
    for uid in (EDITOR, LEITOR):
        with como("authenticated", uid) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR363"):
            c.execute("select radar_copias_comecar('')")
    with como("service_role") as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR363"):
        c.execute("select radar_copias_comecar('')")                                      # a chave dos robôs sozinha: não
    with como("authenticated", ADMIN) as c:
        r = c.execute("select radar_copias_comecar('')").fetchone()[0]
    agora = datetime.now(FUSO)
    assert re.fullmatch(r"radar-copia-\d{4}-\d{2}-\d{2}-\d{4}\.zip", r["arquivo"]) and r["arquivo"].startswith(f"radar-copia-{agora:%Y-%m-%d}-")
    assert (r["origem"], r["banco"]) == ("admin", "v0.50.0") and r["gerado_em"].endswith("-03:00") and r["gerado_em"][:10] == f"{agora:%Y-%m-%d}"
    assert db.execute("select ok, erro from radar_copias where id = %s", (antiga,)).fetchone() == (
        False, "A cópia parou no meio (limite de tempo ou de memória da função no Supabase).")
    assert db.execute("select mes, origem, ok from radar_copias where id = %s", (r["id"],)).fetchone() == (mes, "admin", None)
    with como("authenticated", ADMIN) as c:
        terminar = "select radar_copias_terminar('', %s, %s, 100, 200, 3, 30, %s, %s)"
        assert c.execute(terminar, (antiga, True, "a" * 64, None)).fetchone()[0] is False       # só a que está em andamento
        assert c.execute(terminar, (r["id"], False, "a" * 64, "linha 1\nlinha 2\tcom controle " + "x" * 400)).fetchone()[0] is True
        assert c.execute(terminar, (r["id"], True, "a" * 64, None)).fetchone()[0] is False       # já terminou
    erro, bytes_, sha, ok = db.execute("select erro, bytes, sha256, ok from radar_copias where id = %s", (r["id"],)).fetchone()
    assert ok is False and bytes_ is None and sha is None and len(erro) == 300 and erro.startswith("linha 1 linha 2 com controle x")
    with como("service_role") as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR363"):
        c.execute("select radar_copias_terminar('', %s, true, 1, 1, 1, 1, null, null)", (r["id"],))


EXPORTAR = "select radar_copias_exportar(%s, %s, %s, %s)"


def pagina(c, tabela, depois="", tamanho=10, chave=""):
    """Uma página de radar_copias_exportar: as linhas e o marcador do fim (a chave primária da última linha, em hexadecimal; None na
    página vazia)."""
    r = [x for (x,) in c.execute(EXPORTAR, (chave, tabela, depois, tamanho)).fetchall()]
    if not r:
        return [], None
    assert isinstance(r[-1], str) and re.fullmatch(r"(?:[0-9a-f]{2})+", r[-1]), r[-1]              # o marcador vem sempre no fim
    assert all(isinstance(x, dict) for x in r[:-1])
    return r[:-1], r[-1]


def toda(c, tabela, tamanho, chave="", antes_da_pagina=None):
    """A tabela inteira, página por página pelo marcador (como a função radar-copia faz)."""
    linhas, depois, k = [], "", 0
    while True:
        if antes_da_pagina:
            antes_da_pagina(k)
        r, m = pagina(c, tabela, depois, tamanho, chave)
        linhas += r
        k += 1
        if len(r) < tamanho:
            return linhas
        depois = m


def test_exportar_so_com_a_chave_ou_o_administrador(quadro):
    db = quadro
    db.execute("insert into radar_pessoas (nome, nome_na_peca, area) values ('Ana Teste', 'Ana', 'Fiscal')")
    exportar = EXPORTAR
    with como("service_role") as c:                                                         # a chave dos robôs sozinha: nada
        for chave in ("", "a" * 64, None):
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR363: só a agenda da cópia ou o administrador"):
                c.execute(exportar, (chave, "radar_pessoas", "", 10))
    for uid in (EDITOR, LEITOR):
        with como("authenticated", uid) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR363"):
            c.execute(exportar, ("", "radar_config", "", 10))
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute(exportar, ("", "radar_config", "", 10))
    # o administrador: a página certa, na ordem da chave primária (também a composta), e a seguinte depois do marcador
    c1, c2 = nova_captura(db, url="https://exemplo.test/norma-1"), nova_captura(db, url="https://exemplo.test/norma-2")
    a1, a2 = novo_assunto(db), novo_assunto(db)
    for a, c in ((a2, c1), (a1, c2), (a1, c1)):
        db.execute("insert into radar_assunto_capturas (assunto_id, captura_id) values (%s, %s)", (a, c))
    with como("authenticated", ADMIN) as c:
        linhas, marcador = pagina(c, "radar_assunto_capturas")
        assert [(l["assunto_id"], l["captura_id"]) for l in linhas] == sorted([(a2, c1), (a1, c2), (a1, c1)])
        assert json.loads(bytes.fromhex(marcador)) == {"assunto_id": a2, "captura_id": c1}            # a chave da última linha
        p1, m1 = pagina(c, "radar_assunto_capturas", "", 2)
        assert [(l["assunto_id"], l["captura_id"]) for l in p1] == [(a1, c1), (a1, c2)]
        p2, m2 = pagina(c, "radar_assunto_capturas", m1, 2)                                     # a 2ª página: depois de (a1, c2)
        assert [(l["assunto_id"], l["captura_id"]) for l in p2] == [(a2, c1)]
        assert pagina(c, "radar_assunto_capturas", m2, 2) == ([], None)                         # acabou: só "[]", sem marcador
        categorias = [r["slug"] for r in toda(c, "radar_categorias", 3)]
        assert categorias == sorted(categorias) and len(categorias) == 8
        assert [r["nome"] for r in pagina(c, "radar_pessoas")[0]] == ["Ana Teste"]
        for tabela in ("pg_class", "outra_tabela", "radar_v_painel", "radar_config; drop table radar_config", "Radar_config", None):
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR366: tabela fora da cópia"):
                c.execute(exportar, ("", tabela, "", 10))
        # o tamanho (até 999: o "max rows" do Supabase é 1000, com o marcador) e o marcador que não é o de uma página
        outra = "".join(f"{b:02x}" for b in b'{"slug": "x"}')                                  # chave de outra tabela
        for depois, tamanho in [("", 0), ("", 1000), ("", None), ("zz", 10), ("abc", 10), ("7b", 10), ("5b315d", 10),
                                (outra, 10), ("ab" * 1001, 10)]:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR366: página inválida"):
                c.execute(exportar, ("", "radar_config", depois, tamanho))
        s = c.execute("select radar_copias_situacao()").fetchone()[0]
        assert set(s) == {"agenda", "ultima_ok", "falhas", "em_andamento", "mes_ok", "tamanho_mb"} and s["agenda"] == {"instalada": False}
        for sql in ["select radar_copias_pode('')", "select radar_copias_falta_mes()", "select radar_vencimento_parece_segredo('x')",
                    "select radar_copia_conferir_agenda('x')"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):                      # as internas: só o dono
                c.execute(sql)
    for uid in (EDITOR, LEITOR):
        with como("authenticated", uid) as c:
            assert c.execute("select radar_copias_situacao()").fetchone()[0] == {}
    with como("service_role") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select radar_copias_situacao()")
    # com o Vault (de mentira, só durante o teste) e a chave certa da agenda: exporta pela chave de serviço
    db.execute(VAULT_SIMULADO)
    try:
        db.execute("select vault.create_secret(%s, 'radar_copia_agenda', 'teste')", ("b" * 64,))
        with como("service_role") as c:
            assert c.execute("select radar_copia_conferir_agenda(%s)", ("b" * 64,)).fetchone()[0] is True
            assert [r["nome"] for r in pagina(c, "radar_pessoas", chave="b" * 64)[0]] == ["Ana Teste"]
            for errada in ("b" * 63 + "c", "b" * 31, ""):
                assert c.execute("select radar_copia_conferir_agenda(%s)", (errada,)).fetchone()[0] is False
                with pytest.raises(psycopg.errors.RaiseException, match="RADAR363"):
                    c.execute(exportar, (errada, "radar_pessoas", "", 10))
            r = c.execute("select radar_copias_comecar(%s)", ("b" * 64,)).fetchone()[0]
            assert r["origem"] == "agenda"
            assert c.execute("select radar_copias_terminar(%s, %s, true, 10, 20, 1, 30, %s, null)", ("b" * 64, r["id"], "c" * 64)).fetchone()[0]
        assert db.execute("select ok, bytes, sha256, origem from radar_copias where id = %s", (r["id"],)).fetchone() == (True, 10, "c" * 64, "agenda")
    finally:
        db.execute("drop schema vault cascade")


def test_exportar_pela_chave_nao_pula_linha_apagada_no_meio(quadro):
    """v0.32.0 (revisão): cada página é uma transação. Com OFFSET, uma linha já exportada que fosse apagada entre duas páginas (uma capa
    trocada, a limpeza das imagens, uma exclusão da equipe) fazia a seguinte pular a fronteira da página e ficar fora da cópia, sem
    aviso. Pela chave (o marcador): toda linha que existe do começo ao fim da cópia entra."""
    db = quadro
    ids = [db.execute("insert into radar_imagens (dados, largura, altura) values (%s, 1, 1) returning id",
                      ("data:image/png;base64," + "QUFB" * 12 + f"QQ{k}A",)).fetchone()[0] for k in range(7)]

    def mexer(k):
        if k == 1:
            db.execute("delete from radar_imagens where id = %s", (ids[0],))       # já exportada (1ª página), apagada antes da 2ª
        if k == 2:
            db.execute("delete from radar_imagens where id = %s", (ids[4],))       # ainda não exportada: sai da cópia
    with como("authenticated", ADMIN) as c:
        exportados = [r["id"] for r in toda(c, "radar_imagens", 2, antes_da_pagina=mexer)]
    assert exportados == [ids[0], ids[1], ids[2], ids[3], ids[5], ids[6]]                     # o ids[2] não pula a fronteira
    # a tabela sem chave primária: a cópia recusa (nunca uma tabela pela metade); hoje todas têm (test_tabelas_da_copia_…)
    db.execute("create table public.radar_teste_sem_chave (x int)")
    try:
        with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException,
                                                              match="RADAR366: tabela sem chave primária: radar_teste_sem_chave"):
            c.execute(EXPORTAR, ("", "radar_teste_sem_chave", "", 10))
    finally:
        db.execute("drop table public.radar_teste_sem_chave")


# -------------------------------------------------------------------------------------------------- configuração e catálogo
def test_cfg_dos_lembretes_com_vencimento_e_copia(quadro):
    db = quadro
    ler = lambda: db.execute("select radar_lembretes_cfg()").fetchone()[0]
    assert ler() == PADRAO                                                                  # sem a chave: os 12 padrões
    configurar(db, vencimento="sim", copia=False)
    assert ler() == {**PADRAO, "copia": False}
    configurar(db, vencimento=False, copia=1)
    assert ler() == {**PADRAO, "vencimento": False}
    for tipo in ("pauta", "aprovacao", "video", "noticia", "vencimento", "copia"):
        db.execute("insert into radar_lembretes (tipo, chave) values (%s, %s)", (tipo, f"{tipo}:2026-11"))
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("insert into radar_lembretes (tipo, chave) values ('outro', 'outro:1')")
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("insert into radar_lembretes (tipo, chave) values ('vencimento', 'vencimento:Chave da Ana:2026-12-03:30')")
    db.execute("truncate radar_lembretes")


def test_tabelas_da_copia_sao_todas_as_do_banco(db):
    """A função radar-copia exporta uma lista fixa de tabelas (TABELAS) e diz quais ficam fora de propósito (FORA, com o motivo). Tabela
    nova no banco tem de entrar numa das duas (é preciso decidir se ela vai à cópia)."""
    codigo = FUNCAO.read_text(encoding="utf-8")
    tabelas = re.findall(r'"(radar_[a-z0-9_]+)"', re.search(r"(?m)^const TABELAS = \[(.*?)\] as const;", codigo, re.S).group(1))
    fora = re.findall(r'"?(radar_[a-z0-9_]+)"?\s*:', re.search(r"(?m)^const FORA: Record<string, string> = \{(.*?)\};", codigo, re.S).group(1))
    banco = [t for (t,) in db.execute("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                                         where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\\_%' order by 1""")]
    assert tabelas == sorted(tabelas) and len(tabelas) == len(set(tabelas))
    assert not set(tabelas) & set(fora)
    assert sorted(tabelas + fora) == banco
    assert len(tabelas) == 38 and fora == []                                             # v0.35.0: + as 4 da aba Setor
    # a cópia pagina pela chave primária (v0.32.0, revisão): tabela sem ela não é copiada (RADAR366)
    assert db.execute("""select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
                         where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\\_%'
                           and not exists (select 1 from pg_index i where i.indrelid = c.oid and i.indisprimary)""").fetchone()[0] == 0


def test_nenhuma_coluna_com_nome_de_segredo(db):
    """Nenhuma coluna de tabela do Radar com nome de segredo (a cópia leva todas as colunas): coluna nova com esse nome obriga a decidir
    se ela vai à cópia (FORA, na radar-copia) ou se o nome engana (a lista abaixo)."""
    colunas = {f"{t}.{c}" for t, c in db.execute(
        """select c.table_name, c.column_name from information_schema.columns c
           join information_schema.tables t on t.table_schema = c.table_schema and t.table_name = c.table_name and t.table_type = 'BASE TABLE'
           where c.table_schema = 'public' and c.table_name like 'radar\\_%'
             and c.column_name ~* '(token|secret|segredo|senha|password|api_?key|credencial|chave)'""").fetchall()}
    assert colunas == {"radar_config.chave", "radar_lembretes.chave", "radar_ia_uso.tokens_entrada", "radar_ia_uso.tokens_saida",
                       # v0.35.0: a palavra-chave do gatilho é o "QUERO" do comentário, não uma chave de acesso
                       "radar_respostas_gatilhos.palavra_chave"}


# ----------------------------------------------------------------------------------------------------------- os textos do robô
def test_textos_do_vencimento_e_da_copia():
    corpo = radar_lembretes.corpo
    um = lambda **i: {"lote": LOTE, "itens": [{"id": 1, "n": 3, "data": "2026-12-03", **i}]}
    fazer = ("O que fazer: o administrador abre o Radar → **Configurações** → **Vencimentos de chaves e contas**, renova pelo caminho "
             "anotado no item e clica em **Renovei**, com a nova data. O Radar lembra 30, 7 e 1 dia antes e no dia do vencimento.")
    assert corpo("vencimento", um(situacao="30")) == (                                   # o exemplo do pedido
        "**1 item do quadro de vencimentos vence em 30 dias (03/12/2026): veja Configurações → Vencimentos.**\n\n"
        "- Vence em 30 dias (03/12/2026).\n\n" + fazer + "\n\n" + RODAPE + f"\n\n<!-- radar-lembrete: lote {LOTE} itens 1 -->")
    assert corpo("vencimento", um(situacao="hoje")).startswith(
        "**1 item do quadro de vencimentos vence hoje (03/12/2026): veja Configurações → Vencimentos.**\n\n- Vence hoje (03/12/2026).\n\n")
    assert corpo("vencimento", um(situacao="vencido")).startswith(
        "**1 item do quadro de vencimentos venceu em 03/12/2026: veja Configurações → Vencimentos.**\n\n- Venceu em 03/12/2026.\n\n")
    assert corpo("vencimento", um(situacao="1")).startswith(
        "**1 item do quadro de vencimentos vence amanhã (03/12/2026): veja Configurações → Vencimentos.**\n\n- Vence amanhã (03/12/2026).")
    assert corpo("vencimento", um(situacao="7")).startswith("**1 item do quadro de vencimentos vence em 7 dias (03/12/2026)")
    tres = {"lote": LOTE, "itens": [{"id": 7, "n": 12, "data": "2026-12-20", "situacao": "30"}, {"id": 5, "n": 9, "data": "2026-11-27", "situacao": "7"},
                                    {"id": 6, "n": 4, "data": "2026-12-20", "situacao": "30"}]}
    assert corpo("vencimento", tres) == (
        "**3 itens do quadro de vencimentos pedem atenção: veja Configurações → Vencimentos.**\n\n"
        "- Vence em 7 dias (27/11/2026).\n- Vence em 30 dias (20/12/2026).\n- Vence em 30 dias (20/12/2026).\n\n"
        + fazer + "\n\n" + RODAPE + f"\n\n<!-- radar-lembrete: lote {LOTE} itens 5 6 7 -->")                   # o mais próximo antes
    # v0.32.0 (revisão): nunca o número do item no aviso público (os itens conhecidos entram na ordem do SQL público: o número diria
    # qual chave vence); a marca escondida leva só os números internos dos lembretes ("itens 5 6 7"), não os do quadro
    for g in (um(situacao="30"), um(situacao="vencido"), tres):
        visivel = corpo("vencimento", g).split("<!--")[0]
        assert "nº" not in visivel and "Item" not in visivel
    muitos = {"lote": LOTE, "itens": [{"id": 100 + k, "n": k, "data": f"2026-12-{k + 1:02d}", "situacao": "30"} for k in range(17)]}
    texto = corpo("vencimento", muitos)
    assert texto.count("\n- Vence em 30 dias (") == 15 and "\n- … e mais 2 (a lista inteira está no Radar).\n\n" in texto
    assert texto.endswith("itens " + " ".join(str(100 + k) for k in range(17)) + " -->")
    assert radar_lembretes.MARCA.search(texto).group(1) == LOTE
    assert corpo("copia", {"lote": LOTE, "itens": [{"id": 31, "data": "2026-11-01"}]}) == (
        "**A cópia de segurança do mês 11/2026 ainda não foi feita.**\n\n"
        "- 11/2026: sem cópia concluída depois das tentativas automáticas dos dias 1 e 2.\n\n"
        "O que fazer: o administrador abre o Radar → **Configurações** → **Cópia de segurança no OneDrive**, clica em **Testar a ligação "
        "com o OneDrive** e depois em **Fazer a cópia agora**. O motivo aparece só ali, no Radar.\n\n" + RODAPE +
        f"\n\n<!-- radar-lembrete: lote {LOTE} itens 31 -->")
    assert radar_lembretes.TITULOS["vencimento"] == "Radar: lembrete — vencimento de chave ou conta"
    assert radar_lembretes.TITULOS["copia"] == "Radar: lembrete — cópia de segurança do mês"
    assert sorted(radar_lembretes.TITULOS) == ["aprovacao", "copia", "noticia", "pauta", "vencimento", "video"]


# -------------------------------------------------------------------------------------------------------- o setup duas vezes
def test_setup_duas_vezes_com_as_tabelas_novas(tmp_path):
    """O setup roda duas vezes seguidas (e uma sem a transação do editor) por cima do banco com dados no quadro e nas cópias: nada
    some; as chaves "vencimento" e "copia" entram nos lembretes uma vez só e o ajuste do administrador fica; a restrição do tipo não é
    refeita; as políticas, os gatilhos e os privilégios são os mesmos."""
    banco = "radar_vencimentos_setup"
    with conectar("postgres") as c:
        c.execute(f"drop database if exists {banco} with (force)")
        c.execute(f"create database {banco}")
    estado = lambda c: (
        c.execute("select oid from pg_constraint where conname = 'radar_lembretes_tipo_check'").fetchone()[0],
        c.execute("""select count(*) from pg_policies where tablename in ('radar_vencimentos', 'radar_copias')""").fetchone()[0],
        sorted(t for (t,) in c.execute("""select g.tgname from pg_trigger g join pg_class k on k.oid = g.tgrelid
                                          where k.relname = 'radar_vencimentos' and not g.tgisinternal""")),
        c.execute("""select has_table_privilege('authenticated', 'radar_vencimentos', 'insert'), has_table_privilege('authenticated', 'radar_copias', 'insert'),
                            has_table_privilege('service_role', 'radar_copias', 'select'), has_table_privilege('anon', 'radar_vencimentos', 'select'),
                            has_function_privilege('authenticated', 'radar_copias_exportar(text, text, text, int)', 'execute'),
                            has_function_privilege('anon', 'radar_copias_exportar(text, text, text, int)', 'execute'),
                            has_function_privilege('service_role', 'radar_copia_conferir_agenda(text)', 'execute'),
                            has_function_privilege('authenticated', 'radar_lembretes_situacao()', 'execute'),
                            has_function_privilege('service_role', 'radar_lembretes_observar(timestamptz)', 'execute')""").fetchone(),
        c.execute("select count(*) from radar_vencimentos").fetchone()[0], c.execute("select count(*) from radar_copias").fetchone()[0])
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", banco).returncode == 0
        r = psql(SETUP, banco)
        assert r.returncode == 0, r.stderr
        with conectar(banco) as c:
            assert c.execute("select valor from radar_config where chave = 'lembretes'").fetchone()[0] == PADRAO
            c.execute("""update radar_config set valor = valor || '{"vencimento": false}' where chave = 'lembretes'""")
            c.execute("insert into radar_vencimentos (nome, vence_em) values ('Domínio de teste', '2027-01-10')")
            c.execute("""insert into radar_copias (mes, origem, ok, concluido_em, arquivo) values ('2026-10-01', 'agenda', true, now(),
                         'radar-copia-2026-10-01-0410.zip')""")
            antes = estado(c)
        assert antes[1:] == (2, ["radar_tg_auditar", "radar_tg_vencimento", "radar_tg_vencimentos_atualizado"],
                             (True, False, False, False, True, False, True, True, False), 1, 1)
        for script in (SETUP, _sem_transacao(SETUP, tmp_path / "setup.sql")):
            r = psql(script, banco)
            assert r.returncode == 0, r.stderr
            with conectar(banco) as c:
                assert estado(c) == antes
                assert c.execute("select valor from radar_config where chave = 'lembretes'").fetchone()[0] == {**PADRAO, "vencimento": False}
                assert c.execute("select count(*) from radar_config").fetchone()[0] == 10
        with conectar(banco) as c:
            assert c.execute("""select count(*) from pg_class k join pg_namespace n on n.oid = k.relnamespace
                                where n.nspname = 'public' and k.relkind = 'r' and k.relname like 'radar\\_%' and k.relrowsecurity""").fetchone()[0] == 38
    finally:
        with conectar("postgres") as c:
            c.execute(f"drop database if exists {banco} with (force)")
