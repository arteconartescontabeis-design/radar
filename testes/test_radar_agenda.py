"""Agenda do banco que publica a Pauta aprovada (v0.21.0): sql/radar-redes-agenda.sql e sql/radar-redes-agenda-reversao.sql.

O Postgres dos testes não tem pg_cron, pg_net nem Vault: o módulo cria um banco à parte (radar_agenda), com o setup e os três esquemas
de mentira de conftest.py, e roda o arquivo da agenda como está, menos as linhas "create extension" (como o teste da radar-concorrentes
faz com o pg_net). O comando gravado em cron.job é executado como o pg_cron executaria, e cada net.http_post vira uma linha em
net.pedidos. Confere: a chave da agenda nasce no Vault e nunca fica no comando; o comando faz um pedido por envio vencido (a chave anon,
pública, no Authorization e a da agenda no x-radar-agenda) e nenhum quando nada venceu; sem o setup da v0.21.0 o arquivo para com o
recado; a chave service_role, a sb_secret e o que não é JWT são recusados sem agendar nada; a chave anon escrita no arquivo é a de
radar-config.js; e rodar de novo não duplica, e a reversão tira os dois agendamentos (a chave fica no Vault).
"""
from __future__ import annotations

import base64
import json
import re

import pytest

from conftest import CRON_SIMULADO, NET_SIMULADO, RAIZ, SETUP, VAULT_SIMULADO, conectar, jwt, psql

BANCO_AGENDA = "radar_agenda"
AGENDA = RAIZ / "sql" / "radar-redes-agenda.sql"
AGENDA_REVERSAO = RAIZ / "sql" / "radar-redes-agenda-reversao.sql"
URL = "https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-redes"
IMG = "data:image/jpeg;base64," + "A" * 200


def chave_anon_do_config() -> str:
    return re.search(r'SUPABASE_ANON_KEY:\s*"([^"]+)"', (RAIZ / "radar-config.js").read_text()).group(1)


def carga_do_jwt(chave: str) -> dict:
    parte = chave.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))


def sem_extensoes(texto: str, pasta, nome="radar-redes-agenda-teste.sql"):
    """O arquivo da agenda como está, menos as duas linhas "create extension" (o banco de teste não tem pg_cron nem pg_net)."""
    linhas = texto.splitlines()
    assert sum(l.startswith("create extension if not exists") for l in linhas) == 2
    arquivo = pasta / nome
    arquivo.write_text("\n".join("-- (sem a extensão no banco de teste) " + l if l.startswith("create extension") else l for l in linhas))
    return arquivo


def novo_banco(nome: str, com_setup: bool, simulados: bool):
    with conectar("postgres") as c:
        c.execute(f"drop database if exists {nome} with (force)")
        c.execute(f"create database {nome}")
    assert psql(RAIZ / "testes" / "supabase_simulado.sql", nome).returncode == 0
    if com_setup:
        r = psql(SETUP, nome)
        assert r.returncode == 0, r.stderr
    if simulados:
        with conectar(nome) as c:
            c.execute(CRON_SIMULADO)
            c.execute(NET_SIMULADO)
            c.execute(VAULT_SIMULADO)


def apagar_banco(nome: str):
    with conectar("postgres") as c:
        c.execute(f"drop database if exists {nome} with (force)")


@pytest.fixture(scope="module")
def banco_agenda():
    novo_banco(BANCO_AGENDA, com_setup=True, simulados=True)
    yield BANCO_AGENDA
    apagar_banco(BANCO_AGENDA)


@pytest.fixture(scope="module")
def agenda(banco_agenda, tmp_path_factory):
    """sql/radar-redes-agenda.sql rodado no banco do módulo; devolve a chave que ele guardou no Vault."""
    r = psql(sem_extensoes(AGENDA.read_text(), tmp_path_factory.mktemp("agenda")), banco_agenda)
    assert r.returncode == 0, r.stderr
    with conectar(banco_agenda) as c:
        return c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda'").fetchone()[0]


def envio_vencido(c, dias: int, minutos: int = 1) -> int:
    """Peça aprovada para sair pela agenda e o envio dela, vencido, gravados direto no banco (como radar_pauta_aprovar deixaria)."""
    c.execute("select set_config('radar.pauta', '1', false)")
    try:
        pid = c.execute("insert into radar_pauta_pecas (data, tipo, formato) values (radar_pauta_hoje() + %s, 'bastidor', 'imagem') returning id",
                        (dias,)).fetchone()[0]
        versao = c.execute("""update radar_pauta_pecas set situacao = 'aprovada', aprovado_modo = 'agendar', legenda_instagram = 'Legenda da peça de teste.'
                              where id = %s returning versao_publicavel""", (pid,)).fetchone()[0]
    finally:
        c.execute("select set_config('radar.pauta', '', false)")
    return c.execute("""insert into radar_redes_envios (peca_id, canal, legenda, imagem, conteudo_lido_em, agendado_para)
                        values (%s, 'instagram', 'Legenda da peça de teste.', %s, %s, now() - make_interval(mins => %s)) returning id""",
                     (pid, IMG, versao, minutos)).fetchone()[0]


def test_agenda_cria_a_chave_e_agenda_de_5_em_5_min_sem_a_chave_no_comando(banco_agenda, agenda):
    assert re.fullmatch(r"[0-9a-f]{64}", agenda)                                          # 64 caracteres aleatórios, só no Vault
    with conectar(banco_agenda) as c:
        jobs = c.execute("select jobname, schedule, command, active from cron.job order by jobname").fetchall()
    assert [(n, s, a) for n, s, _, a in jobs] == [("radar-redes-agenda", "*/5 * * * *", True), ("radar-redes-agenda-limpeza", "41 6 * * *", True)]
    comando, limpeza = jobs[0][2], jobs[1][2]
    assert agenda not in comando and agenda not in limpeza                                 # a chave é lida do Vault a cada rodada
    for trecho in (URL, "Bearer " + chave_anon_do_config(), "'x-radar-agenda'", "vault.decrypted_secrets", "radar_redes_agenda",
                   "public.radar_agenda_vencidas(2)", "timeout_milliseconds := 150000", "'acao', 'publicar'"):
        assert trecho in comando, trecho
    assert "cron.job_run_details" in limpeza and "interval '7 days'" in limpeza and "like 'radar-%'" in limpeza


def test_agenda_comando_faz_um_pedido_por_envio_vencido_com_anon_e_chave_e_nenhum_quando_nao_ha(banco_agenda, agenda):
    with conectar(banco_agenda) as c:
        comando = c.execute("select command from cron.job where jobname = 'radar-redes-agenda'").fetchone()[0]
        rodar = lambda: (c.execute(comando).fetchall(), [tuple(r) for r in c.execute(
            "select url, body, headers, timeout_milliseconds from net.pedidos order by id").fetchall()])
        c.execute("truncate net.pedidos")
        assert rodar() == ([], [])                                                            # nada vencido: nenhum pedido
        futuro = envio_vencido(c, 3, minutos=-60)                                             # daqui a uma hora: ainda não
        e1, e2, e3 = envio_vencido(c, 4, minutos=30), envio_vencido(c, 5, minutos=20), envio_vencido(c, 6, minutos=10)
        _, pedidos = rodar()
        cab = {"Content-Type": "application/json", "Authorization": "Bearer " + chave_anon_do_config(), "x-radar-agenda": agenda}
        assert pedidos == [(URL, {"acao": "publicar", "envio": e}, cab, 150000) for e in (e1, e2)]   # até 2 por rodada, o mais antigo antes
        c.execute("truncate net.pedidos")
        assert [p[1]["envio"] for p in rodar()[1]] == [e3]                                    # os dois já chamados esperam 10 minutos
        c.execute("truncate net.pedidos")
        assert rodar()[1] == []
        assert c.execute("select disparos from radar_redes_envios where id = %s", (futuro,)).fetchone()[0] == 0
        # pausada em Configurações → Pauta: nenhum pedido
        c.execute("update radar_redes_envios set disparado_em = null")
        c.execute("""update radar_config set valor = valor || '{"agenda_ligada": false}' where chave = 'pauta'""")
        try:
            assert rodar()[1] == []
        finally:
            c.execute("""update radar_config set valor = valor || '{"agenda_ligada": true}' where chave = 'pauta'""")
        c.execute("truncate net.pedidos")
        assert len(rodar()[1]) == 2


def test_agenda_sem_o_setup_v021_para_com_recado(tmp_path):
    novo_banco("radar_agenda_sem", com_setup=False, simulados=False)
    try:
        r = psql(AGENDA_REVERSAO, "radar_agenda_sem")                                        # sem o pg_cron, a reversão só avisa
        assert r.returncode == 0 and "O pg_cron não está instalado" in r.stderr
        with conectar("radar_agenda_sem") as c:
            c.execute(CRON_SIMULADO)
            c.execute(NET_SIMULADO)
            c.execute(VAULT_SIMULADO)
        r = psql(sem_extensoes(AGENDA.read_text(), tmp_path), "radar_agenda_sem")
        assert r.returncode != 0 and "Rode antes o radar-setup-v0.21.0.sql" in r.stderr
        with conectar("radar_agenda_sem") as c:                                               # nada ficou pela metade
            assert c.execute("select (select count(*) from vault.secrets), (select count(*) from cron.job)").fetchone() == (0, 0)
    finally:
        apagar_banco("radar_agenda_sem")


def test_agenda_recusa_jwt_service_role_e_sb_secret(banco_agenda, tmp_path):
    texto, anon = AGENDA.read_text(), chave_anon_do_config()
    assert texto.count(anon) == 1
    with conectar(banco_agenda) as c:
        antes = c.execute("select jobname, command from cron.job order by jobid").fetchall()
    for i, ruim in enumerate([jwt("service_role"), "sb_secret_testeRadar0123456789abcdef", "chave-qualquer", jwt("authenticated")]):
        r = psql(sem_extensoes(texto.replace(anon, ruim), tmp_path, f"ruim{i}.sql"), banco_agenda)
        assert r.returncode != 0 and "não é a chave anon (pública). Nada foi agendado." in r.stderr, ruim
        assert ruim not in r.stderr
    with conectar(banco_agenda) as c:                                                         # a agenda que existia continua igual
        assert c.execute("select jobname, command from cron.job order by jobid").fetchall() == antes


def test_chave_anon_do_sql_e_a_do_radar_config():
    texto, anon = AGENDA.read_text(), chave_anon_do_config()
    escrita = re.search(r"v_anon constant text := '([^']+)';", texto).group(1)
    assert escrita == anon                                                                    # trocou a chave no Supabase: rode o arquivo de novo
    assert carga_do_jwt(anon)["role"] == "anon"
    assert re.findall(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", texto) == [anon]                         # nenhuma outra chave no arquivo
    assert "service_role" not in texto and not re.search(r"sb_secret_\w", texto)



def test_teste_do_fim_do_arquivo_roda_sem_trocar_nada(banco_agenda, agenda):
    """O teste "agenda_teste" do comentário do fim do arquivo (passo 6 da instalação) roda como está, só sem os "--": a chave anon vem
    do próprio agendamento (cron.job), sem marcador para trocar e sem repetir a chave no arquivo, e a da agenda vem do Vault."""
    texto = AGENDA.read_text()
    trecho = texto[texto.index("-- Teste (não publica nada)"):]
    linhas = re.findall(r"(?m)^--   (.*)$", trecho[:trecho.index("-- Depois de alguns segundos")])
    assert len(linhas) == 5 and linhas[0].startswith("select net.http_post(") and not re.search(r"<[^>]*>", "\n".join(linhas))
    with conectar(banco_agenda) as c:
        c.execute("truncate net.pedidos")
        c.execute("\n".join(linhas))
        pedidos = [tuple(r) for r in c.execute("select url, body, headers from net.pedidos order by id").fetchall()]
    assert pedidos == [(URL, {"acao": "agenda_teste"}, {"Content-Type": "application/json", "Authorization": "Bearer " + chave_anon_do_config(),
                                                       "x-radar-agenda": agenda})]


def test_agenda_roda_de_novo_sem_duplicar_e_reversao_tira_tudo(banco_agenda, agenda, tmp_path):
    r = psql(sem_extensoes(AGENDA.read_text(), tmp_path), banco_agenda)
    assert r.returncode == 0, r.stderr
    with conectar(banco_agenda) as c:
        assert [n for (n,) in c.execute("select jobname from cron.job order by jobname").fetchall()] == ["radar-redes-agenda", "radar-redes-agenda-limpeza"]
        assert c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda'").fetchone()[0] == agenda
        for nome in ("radar-itc", "copia-do-projeto"):                                        # as outras agendas ficam
            c.execute("select cron.schedule(%s, '55 5 * * *', 'select 1')", (nome,))
    for _ in range(2):                                                                        # a reversão pode rodar mais de uma vez
        r = psql(AGENDA_REVERSAO, banco_agenda)
        assert r.returncode == 0 and "Agenda da Pauta retirada." in r.stderr, r.stderr
    with conectar(banco_agenda) as c:
        assert sorted(n for (n,) in c.execute("select jobname from cron.job").fetchall()) == ["copia-do-projeto", "radar-itc"]
        assert c.execute("select count(*) from vault.secrets where name = 'radar_redes_agenda'").fetchone()[0] == 1   # a chave fica
