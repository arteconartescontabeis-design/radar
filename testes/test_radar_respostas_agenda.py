"""A fila do Módulo Respostas Automáticas (v0.35.0): sql/radar-respostas-agenda.sql e sql/radar-respostas-agenda-reversao.sql.

Como em test_radar_agenda.py: um banco à parte (radar_agenda_respostas), com o setup e o pg_cron, o pg_net e o Vault de mentira de
conftest.py; o arquivo da agenda roda como está, com as extensões contando como já instaladas. Confere: sem o setup desta versão o
arquivo para com o recado e nada é agendado; com tudo, cria a chave 'radar_respostas' no Vault (uma vez só) e a função
radar_respostas_conferir, agenda radar-respostas-fila a cada 5 minutos, e o comando lê a chave do Vault na hora (ela nunca fica em
cron.job); o comando só faz pedido quando há pendente de gatilho ativo com o interruptor geral ligado (radar_respostas_ha_pendentes),
com a chave no x-radar-chave e sem chave anon; rodar de novo não duplica nem troca a chave; e as duas reversões (a da agenda e a do
setup) tiram o agendamento, deixando a chave no Vault.
"""
from __future__ import annotations

import re

import pytest

from conftest import RAIZ, REVERSAO, conectar, psql
from test_radar_agenda import apagar_banco, novo_banco, sem_extensoes

BANCO = "radar_agenda_respostas"
AGENDA = RAIZ / "sql" / "radar-respostas-agenda.sql"
AGENDA_REVERSAO = RAIZ / "sql" / "radar-respostas-agenda-reversao.sql"
URL = "https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-meta-webhook"


def rodar_agenda(pasta, banco=BANCO):
    return psql(sem_extensoes(AGENDA.read_text(), pasta, "radar-respostas-agenda-teste.sql"), banco)


def gatilho_e_pendente(c):
    """Um gatilho ativo com um comentário na fila (o caminho que liga o guarda da agenda)."""
    gid = c.execute("""insert into radar_respostas_gatilhos (rede, midia_id, palavra_chave, resposta_publica, mensagem_privada)
                       values ('instagram', '123', 'quero', 'Mandamos no privado!', 'Aqui está:') returning id""").fetchone()[0]
    c.execute("""insert into radar_respostas_registro (gatilho_id, rede, comentario_id, situacao)
                 values (%s, 'instagram', '111', 'pendente')""", (gid,))
    return gid


@pytest.fixture(scope="module")
def banco():
    novo_banco(BANCO, com_setup=True, simulados=True)
    yield BANCO
    apagar_banco(BANCO)


def test_sem_o_setup_desta_versao_nada_e_agendado(tmp_path):
    nome = "radar_agenda_respostas_vazio"
    novo_banco(nome, com_setup=False, simulados=True)
    try:
        r = rodar_agenda(tmp_path, nome)
        assert r.returncode != 0 and "Rode antes o radar-setup-v0.35.0.sql" in r.stderr, r.stderr
        with conectar(nome) as c:
            assert c.execute("select count(*) from cron.job").fetchone()[0] == 0
            assert c.execute("select count(*) from vault.secrets").fetchone()[0] == 0     # nem a chave entra sem o setup
    finally:
        apagar_banco(nome)


def test_agenda_a_cada_5_minutos_com_a_chave_do_vault(banco, tmp_path):
    r = rodar_agenda(tmp_path)
    assert r.returncode == 0, r.stderr
    with conectar(banco) as c:
        chave = c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_respostas'").fetchone()[0]
        jobs = c.execute("select jobname, schedule, active, command from cron.job order by jobname").fetchall()
        # quem confere a chave é o banco, e só a chave interna executa a conferência
        assert c.execute("select radar_respostas_conferir(%s)", (chave,)).fetchone()[0] is True
        assert c.execute("select radar_respostas_conferir(repeat('x', 64))").fetchone()[0] is False
        assert c.execute("select radar_respostas_conferir(null)").fetchone()[0] is False
        donos = c.execute("""select array_agg(grantee::text order by grantee::text) from information_schema.routine_privileges
                             where routine_name = 'radar_respostas_conferir' and privilege_type = 'EXECUTE'""").fetchone()[0]
        assert "anon" not in donos and "authenticated" not in donos and "service_role" in donos
    assert re.fullmatch(r"[0-9a-f]{64}", chave)
    assert [(n, s, a) for n, s, a, _ in jobs] == [("radar-respostas-fila", "*/5 * * * *", True)]
    comando = jobs[0][3]
    assert chave not in comando                                                     # lida do Vault a cada rodada
    for trecho in (URL, "'x-radar-chave'", "vault.decrypted_secrets", "name = 'radar_respostas'", '{"acao": "pendentes"}',
                   "timeout_milliseconds := 150000", "where public.radar_respostas_ha_pendentes()"):
        assert trecho in comando, trecho
    assert "Authorization" not in comando and "apikey" not in comando and "eyJ" not in comando     # sem chave anon


def test_o_comando_so_pede_quando_ha_pendente_que_pode_sair(banco, tmp_path):
    with conectar(banco) as c:
        if not c.execute("select count(*) from cron.job where jobname = 'radar-respostas-fila'").fetchone()[0]:
            assert rodar_agenda(tmp_path).returncode == 0
        comando = c.execute("select command from cron.job where jobname = 'radar-respostas-fila'").fetchone()[0]
        chave = c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_respostas'").fetchone()[0]
        c.execute("truncate radar_respostas_registro, radar_respostas_gatilhos restart identity cascade")
        c.execute("truncate net.pedidos")
        c.execute(comando)
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 0     # fila vazia: nenhum pedido
        gid = gatilho_e_pendente(c)
        c.execute(comando)
        pedidos = [tuple(r) for r in c.execute("select url, body, headers, timeout_milliseconds from net.pedidos").fetchall()]
        assert pedidos == [(URL, {"acao": "pendentes"}, {"Content-Type": "application/json", "x-radar-chave": chave}, 150000)]
        # com o gatilho desligado, ou com o interruptor geral pausado: nada
        c.execute("truncate net.pedidos")
        c.execute("update radar_respostas_gatilhos set ativo = false where id = %s", (gid,))
        c.execute(comando)
        c.execute("update radar_respostas_gatilhos set ativo = true where id = %s", (gid,))
        c.execute("""insert into radar_config (chave, valor) values ('respostas', '{"ligado": false}')
                     on conflict (chave) do update set valor = excluded.valor""")
        c.execute(comando)
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 0
        c.execute("delete from radar_config where chave = 'respostas'")
        c.execute("truncate radar_respostas_registro, radar_respostas_gatilhos restart identity cascade")


def test_roda_de_novo_sem_duplicar_nem_trocar_a_chave_e_as_reversoes_tiram(banco, tmp_path):
    assert rodar_agenda(tmp_path).returncode == 0
    with conectar(banco) as c:
        chave_antes = c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_respostas'").fetchone()[0]
    r = rodar_agenda(tmp_path)
    assert r.returncode == 0, r.stderr
    with conectar(banco) as c:
        assert c.execute("select count(*) from cron.job where jobname like 'radar-respostas%'").fetchone()[0] == 1
        assert c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_respostas'").fetchone()[0] == chave_antes
        c.execute("select cron.schedule('radar-outra-coisa', '*/5 * * * *', 'select 1')")
    for _ in range(2):                                                              # a reversão da agenda pode rodar mais de uma vez
        r = psql(AGENDA_REVERSAO, banco)
        assert r.returncode == 0 and "Agenda da fila das respostas retirada." in r.stderr, r.stderr
    with conectar(banco) as c:
        assert [n for (n,) in c.execute("select jobname from cron.job order by 1").fetchall()] == ["radar-outra-coisa"]
        assert c.execute("select count(*) from vault.secrets where name = 'radar_respostas'").fetchone()[0] == 1     # a chave fica
    assert rodar_agenda(tmp_path).returncode == 0
    r = psql(REVERSAO, banco)                                                       # a reversão do setup também tira a agenda da fila
    assert r.returncode == 0, r.stderr
    with conectar(banco) as c:
        assert c.execute("select count(*) from cron.job where jobname like 'radar-respostas%'").fetchone()[0] == 0
        assert c.execute("""select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                            where n.nspname = 'public' and p.proname like 'radar\\_respostas\\_%'
                              and p.proname <> 'radar_respostas_conferir'""").fetchone()[0] == 0
        assert c.execute("select to_regclass('public.radar_respostas_gatilhos')").fetchone()[0] is None
    r = psql(AGENDA_REVERSAO, banco)                                                # sem nada para tirar, só avisa
    assert r.returncode == 0


def test_reversao_da_agenda_sem_o_pg_cron_so_avisa(tmp_path):
    nome = "radar_agenda_respostas_semcron"
    novo_banco(nome, com_setup=False, simulados=False)
    try:
        r = psql(AGENDA_REVERSAO, nome)
        assert r.returncode == 0 and "O pg_cron não está instalado" in r.stderr, r.stderr
    finally:
        apagar_banco(nome)
