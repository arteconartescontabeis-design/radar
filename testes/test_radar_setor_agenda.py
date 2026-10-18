"""Leitura automática da aba Setor (v0.34.0): sql/radar-setor-agenda.sql e sql/radar-setor-agenda-reversao.sql.

Como em test_radar_agenda.py: um banco à parte (radar_agenda_setor), com o setup e o pg_cron, o pg_net e o Vault de mentira de
conftest.py; o arquivo da agenda roda como está, com as extensões contando como já instaladas. Confere: sem o setup desta versão ou sem
a chave da radar-concorrentes (sql/radar-concorrentes.sql) o arquivo para com o recado e nada é agendado; com tudo, agenda
radar-setor-coleta aos 17 minutos de cada hora, e o comando lê a chave do Vault na hora (ela nunca fica em cron.job); o comando só faz
pedido quando há conta devida (radar_setor_ha_devidas), com a chave no x-radar-chave e sem chave anon; a guarda diária dos 400 dias
(radar-setor-guarda) apaga as publicações velhas de todas as contas sem chamar a função; rodar de novo não duplica; e as duas reversões
(a da agenda e a do setup) tiram os agendamentos, deixando a chave no Vault.
"""
from __future__ import annotations

import re

import pytest

from conftest import RAIZ, REVERSAO, conectar, psql
from test_radar_agenda import apagar_banco, novo_banco, sem_extensoes

BANCO = "radar_agenda_setor"
AGENDA = RAIZ / "sql" / "radar-setor-agenda.sql"
AGENDA_REVERSAO = RAIZ / "sql" / "radar-setor-agenda-reversao.sql"
CONCORRENTES = RAIZ / "sql" / "radar-concorrentes.sql"
URL = "https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-concorrentes"


def rodar_agenda(pasta, banco=BANCO):
    return psql(sem_extensoes(AGENDA.read_text(), pasta, "radar-setor-agenda-teste.sql"), banco)


def aplicar_concorrentes(pasta, banco=BANCO):
    """sql/radar-concorrentes.sql como está, com o pg_net contando como já instalado."""
    arquivo = pasta / "radar-concorrentes-teste.sql"
    arquivo.write_text(CONCORRENTES.read_text().replace("where extname = 'pg_net'", "where extname = 'plpgsql'"))
    r = psql(arquivo, banco)
    assert r.returncode == 0, r.stderr


@pytest.fixture(scope="module")
def banco():
    novo_banco(BANCO, com_setup=True, simulados=True)
    yield BANCO
    apagar_banco(BANCO)


def test_sem_o_setup_desta_versao_nada_e_agendado(tmp_path):
    nome = "radar_agenda_setor_vazio"
    novo_banco(nome, com_setup=False, simulados=True)
    try:
        r = rodar_agenda(tmp_path, nome)
        assert r.returncode != 0 and "Rode antes o radar-setup-v0.34.0.sql" in r.stderr, r.stderr
        with conectar(nome) as c:
            assert c.execute("select count(*) from cron.job").fetchone()[0] == 0
    finally:
        apagar_banco(nome)


def test_agenda_de_hora_em_hora_so_com_a_chave_da_radar_concorrentes(banco, tmp_path):
    r = rodar_agenda(tmp_path)                                                      # ainda sem o sql/radar-concorrentes.sql
    assert r.returncode != 0 and "Rode antes o sql/radar-concorrentes.sql" in r.stderr, r.stderr
    with conectar(banco) as c:
        assert c.execute("select count(*) from cron.job").fetchone()[0] == 0
    aplicar_concorrentes(tmp_path)
    r = rodar_agenda(tmp_path)
    assert r.returncode == 0, r.stderr
    with conectar(banco) as c:
        chave = c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_concorrentes'").fetchone()[0]
        jobs = c.execute("select jobname, schedule, active, command from cron.job order by jobname").fetchall()
    assert re.fullmatch(r"[0-9a-f]{64}", chave)
    assert [(n, s, a) for n, s, a, _ in jobs] == [("radar-setor-coleta", "17 * * * *", True), ("radar-setor-guarda", "43 6 * * *", True)]
    assert jobs[1][3] == "select public.radar_setor_guardar_em(now())"                # a guarda: só no banco, sem chave nem pedido
    comando = jobs[0][3]
    assert chave not in comando                                                     # lida do Vault a cada rodada
    for trecho in (URL, "'x-radar-chave'", "vault.decrypted_secrets", "name = 'radar_concorrentes'", '{"acao": "setor_coletar"}',
                   "timeout_milliseconds := 150000", "where public.radar_setor_ha_devidas()"):
        assert trecho in comando, trecho
    assert "Authorization" not in comando and "apikey" not in comando and "eyJ" not in comando     # sem chave anon


def test_o_comando_so_pede_quando_ha_conta_devida(banco, tmp_path):
    with conectar(banco) as c:
        if not c.execute("select count(*) from cron.job where jobname = 'radar-setor-coleta'").fetchone()[0]:
            aplicar_concorrentes(tmp_path)
            assert rodar_agenda(tmp_path).returncode == 0
        comando = c.execute("select command from cron.job where jobname = 'radar-setor-coleta'").fetchone()[0]
        chave = c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_concorrentes'").fetchone()[0]
        c.execute("truncate radar_setor_setores, radar_setor_coletas restart identity cascade")
        c.execute("truncate net.pedidos")
        c.execute(comando)
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 0     # nenhuma conta: nenhum pedido
        sid = c.execute("insert into radar_setor_setores (nome) values ('Contabilidade') returning id").fetchone()[0]
        c.execute("insert into radar_setor_contas (setor_id, nome) values (%s, 'ana.teste')", (sid,))
        c.execute(comando)
        pedidos = [tuple(r) for r in c.execute("select url, body, headers, timeout_milliseconds from net.pedidos").fetchall()]
        assert pedidos == [(URL, {"acao": "setor_coletar"}, {"Content-Type": "application/json", "x-radar-chave": chave}, 150000)]
        # lida nesta semana, ou com a leitura automática desligada: nada
        c.execute("truncate net.pedidos")
        c.execute("update radar_setor_contas set coletada_em = now()")
        c.execute(comando)
        c.execute("update radar_setor_contas set coletada_em = null")
        c.execute("""insert into radar_config (chave, valor) values ('setor', '{"coleta_ligada": false}')""")
        c.execute(comando)
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 0
        c.execute("delete from radar_config where chave = 'setor'")
        c.execute("truncate radar_setor_setores, radar_setor_coletas restart identity cascade")


def test_a_guarda_diaria_apaga_as_publicacoes_velhas_de_todas_as_contas(banco, tmp_path):
    with conectar(banco) as c:
        if not c.execute("select count(*) from cron.job where jobname = 'radar-setor-guarda'").fetchone()[0]:
            aplicar_concorrentes(tmp_path)
            assert rodar_agenda(tmp_path).returncode == 0
        comando = c.execute("select command from cron.job where jobname = 'radar-setor-guarda'").fetchone()[0]
        c.execute("truncate radar_setor_setores, radar_setor_coletas restart identity cascade")
        c.execute("truncate net.pedidos")
        sid = c.execute("insert into radar_setor_setores (nome, ativo) values ('Contabilidade', false) returning id").fetchone()[0]
        cid = c.execute("insert into radar_setor_contas (setor_id, nome, ativa) values (%s, 'ana.teste', false) returning id", (sid,)).fetchone()[0]
        c.execute("""insert into radar_setor_posts (conta_id, midia_id, publicado_em, tipo)
                     values (%s, 'velha', now() - interval '401 days', 'IMAGE'), (%s, 'nova', now() - interval '399 days', 'IMAGE')""", (cid, cid))
        c.execute(comando)                                                           # setor inativo e conta pausada: sai igual
        assert [m for (m,) in c.execute("select midia_id from radar_setor_posts").fetchall()] == ["nova"]
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 0     # nada de chamar a função
        c.execute("truncate radar_setor_setores, radar_setor_coletas restart identity cascade")


def test_roda_de_novo_e_as_reversoes_tiram_o_agendamento(banco, tmp_path):
    aplicar_concorrentes(tmp_path)
    for _ in range(2):
        r = rodar_agenda(tmp_path)
        assert r.returncode == 0, r.stderr
    with conectar(banco) as c:
        c.execute("select cron.schedule('radar-outra-coisa', '*/5 * * * *', 'select 1')")
        assert c.execute("select count(*) from cron.job where jobname like 'radar-setor%'").fetchone()[0] == 2
    for _ in range(2):                                                              # a reversão da agenda pode rodar mais de uma vez
        r = psql(AGENDA_REVERSAO, banco)
        assert r.returncode == 0 and "Leitura automática do setor retirada." in r.stderr, r.stderr
    with conectar(banco) as c:
        assert [n for (n,) in c.execute("select jobname from cron.job order by 1").fetchall()] == ["radar-outra-coisa"]
        assert c.execute("select count(*) from vault.secrets where name = 'radar_concorrentes'").fetchone()[0] == 1     # a chave fica
    assert rodar_agenda(tmp_path).returncode == 0
    r = psql(REVERSAO, banco)                                                       # a reversão do setup também tira a agenda do setor
    assert r.returncode == 0, r.stderr
    with conectar(banco) as c:
        assert c.execute("select count(*) from cron.job where jobname like 'radar-setor%'").fetchone()[0] == 0
        assert c.execute("""select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                            where n.nspname = 'public' and p.proname like 'radar\\_setor\\_%'""").fetchone()[0] == 0
        assert c.execute("select to_regclass('public.radar_setor_contas')").fetchone()[0] is None
    r = psql(AGENDA_REVERSAO, banco)                                                # sem nada para tirar, só avisa
    assert r.returncode == 0


def test_reversao_da_agenda_sem_o_pg_cron_so_avisa(tmp_path):
    nome = "radar_agenda_setor_semcron"
    novo_banco(nome, com_setup=False, simulados=False)
    try:
        r = psql(AGENDA_REVERSAO, nome)
        assert r.returncode == 0 and "O pg_cron não está instalado" in r.stderr, r.stderr
    finally:
        apagar_banco(nome)
