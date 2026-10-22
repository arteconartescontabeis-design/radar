"""Agenda do banco que publica a Pauta aprovada (v0.21.0): sql/radar-redes-agenda.sql e sql/radar-redes-agenda-reversao.sql.

O Postgres dos testes não tem pg_cron, pg_net nem Vault: o módulo cria um banco à parte (radar_agenda), com o setup e os três esquemas
de mentira de conftest.py, e roda o arquivo da agenda como está, com as duas extensões contando como já instaladas (v0.23.0; antes, sem
as linhas "create extension", como o teste da radar-concorrentes faz com o pg_net). O comando gravado em cron.job é executado como o pg_cron executaria, e cada net.http_post vira uma linha em
net.pedidos. Confere: a chave da agenda nasce no Vault e nunca fica no comando; o comando faz um pedido por envio vencido (a chave anon,
pública, no Authorization e a da agenda no x-radar-agenda) e nenhum quando nada venceu; sem o setup da v0.21.0 o arquivo para com o
recado; a chave service_role, a sb_secret e o que não é JWT são recusados sem agendar nada; a chave anon escrita no arquivo é a de
radar-config.js; e rodar de novo não duplica, e a reversão tira os dois agendamentos (a chave fica no Vault).

v0.23.0 (a pendência da v0.22.1): as três agendas (ITC, Pauta e corretor de vídeo) rodam de novo no Supabase sem o "dependent privileges
exist": com as extensões instaladas, o arquivo não roda "create extension" nem grant (o que disparava o gatilho da Supabase).
"""
from __future__ import annotations

import base64
import json
import re

import pytest

from conftest import CRON_SIMULADO, NET_SIMULADO, RAIZ, REVERSAO, SETUP, VAULT_SIMULADO, conectar, jwt, psql

BANCO_AGENDA = "radar_agenda"
EXTENSOES = ("pg_cron", "pg_net")
AGENDA = RAIZ / "sql" / "radar-redes-agenda.sql"
AGENDA_ITC = RAIZ / "sql" / "radar-itc-agenda.sql"                                    # v0.23.0
AGENDA_VIDEO = RAIZ / "sql" / "radar-video-agenda.sql"
AGENDA_REVERSAO = RAIZ / "sql" / "radar-redes-agenda-reversao.sql"
URL = "https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-redes"
IMG = "data:image/jpeg;base64," + "A" * 200


def chave_anon_do_config() -> str:
    return re.search(r'SUPABASE_ANON_KEY:\s*"([^"]+)"', (RAIZ / "radar-config.js").read_text()).group(1)


def carga_do_jwt(chave: str) -> dict:
    parte = chave.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))


def sem_extensoes(texto: str, pasta, nome="radar-redes-agenda-teste.sql"):
    """O arquivo da agenda como está, com o pg_cron e o pg_net contando como já instalados (o banco de teste não tem as extensões; o
    cron e o net são os de mentira). v0.23.0: o bloco do começo confere o pg_extension e pula o "create extension" e os grants, como
    na 2ª rodada no Supabase; aqui ele confere uma extensão que todo banco tem (plpgsql). Fora do bloco, nenhum "create extension"."""
    assert not re.search(r"(?mi)^\s*(create extension|grant )", texto)
    for extensao in EXTENSOES:
        assert texto.count(f"from pg_extension where extname = '{extensao}'") == 1, extensao
        texto = texto.replace(f"where extname = '{extensao}'", "where extname = 'plpgsql'")
    arquivo = pasta / nome
    arquivo.write_text(texto)
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
    assert [(n, s, a) for n, s, _, a in jobs] == [("radar-redes-agenda", "*/5 * * * *", True), ("radar-redes-agenda-lembretes", "*/15 * * * *", True),
                                                  ("radar-redes-agenda-limpeza", "41 6 * * *", True), ("radar-redes-agenda-robos", "13 8 * * *", True),
                                                  ("radar-redes-agenda-site", "*/5 * * * *", True)]   # v0.45.0: + a hora marcada do site
    comando, lembretes, limpeza, robos, site = (j[2] for j in jobs)                         # v0.29.0: + os lembretes por e-mail
    assert all(agenda not in c for c in (comando, lembretes, limpeza, robos, site))         # a chave é lida do Vault a cada rodada
    for trecho in (URL, "Bearer " + chave_anon_do_config(), "'x-radar-agenda'", "vault.decrypted_secrets", "radar_redes_agenda",
                   "public.radar_agenda_vencidas(2)", "timeout_milliseconds := 150000", "'acao', 'publicar'"):
        assert trecho in comando, trecho
    assert "cron.job_run_details" in limpeza and "interval '7 days'" in limpeza and "like 'radar-%'" in limpeza
    # v0.45.0: o job da hora marcada do site só chama quando o banco diz que uma hora venceu
    for trecho in (URL, '{"acao": "acionar_site"}', "where public.radar_site_agendada_devida()", "timeout_milliseconds := 60000"):
        assert trecho in site, trecho


def test_agenda_pede_uma_vez_por_dia_que_a_funcao_religue_os_robos_do_github(banco_agenda, agenda):
    """Rodada 2 da varredura geral: no repositório público, o GitHub desliga sozinho os workflows agendados depois de 60 dias sem
    atividade (a coleta, o robô do site e o resumo param sem aviso). O pg_cron, que o GitHub não desliga, pede uma vez por dia à
    radar-redes ("manter_robos", com a chave da agenda) que os religue."""
    with conectar(banco_agenda) as c:
        comando = c.execute("select command from cron.job where jobname = 'radar-redes-agenda-robos'").fetchone()[0]
        c.execute("truncate net.pedidos")
        c.execute(comando)
        pedidos = [tuple(r) for r in c.execute("select url, body, headers, timeout_milliseconds from net.pedidos order by id").fetchall()]
    assert pedidos == [(URL, {"acao": "manter_robos"}, {"Content-Type": "application/json", "Authorization": "Bearer " + chave_anon_do_config(),
                                                        "x-radar-agenda": agenda}, 60000)]


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


def test_agenda_site_so_pede_quando_uma_hora_marcada_do_site_vence(banco_agenda, agenda):
    """v0.45.0: o job radar-redes-agenda-site pergunta ao banco (radar_site_agendada_devida) e, sem publicação no site com hora
    marcada vencida, não faz pedido nenhum. O disparo com a hora vencida (até 3 vezes, de 10 em 10 minutos) é testado no banco,
    em test_radar_banco.py (test_hora_marcada_no_site_...)."""
    with conectar(banco_agenda) as c:
        comando = c.execute("select command from cron.job where jobname = 'radar-redes-agenda-site'").fetchone()[0]
        c.execute("truncate net.pedidos")
        c.execute(comando)
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 0


def test_agenda_sem_o_setup_para_com_recado(tmp_path):
    novo_banco("radar_agenda_sem", com_setup=False, simulados=False)
    try:
        r = psql(AGENDA_REVERSAO, "radar_agenda_sem")                                        # sem o pg_cron, a reversão só avisa
        assert r.returncode == 0 and "O pg_cron não está instalado" in r.stderr
        with conectar("radar_agenda_sem") as c:
            c.execute(CRON_SIMULADO)
            c.execute(NET_SIMULADO)
            c.execute(VAULT_SIMULADO)
        r = psql(sem_extensoes(AGENDA.read_text(), tmp_path), "radar_agenda_sem")
        assert r.returncode != 0 and "Rode antes o radar-setup-v0.45.0.sql" in r.stderr          # v0.29.0: o setup desta versão
        with conectar("radar_agenda_sem") as c:                                               # nada ficou pela metade
            assert c.execute("select (select count(*) from vault.secrets), (select count(*) from cron.job)").fetchone() == (0, 0)
    finally:
        apagar_banco("radar_agenda_sem")


# ------------------------------------------------------------------- v0.29.0: os lembretes por e-mail
LEMBRETES_ABERTOS = json.dumps({"ligado": True, "hora": "00:00", "de": "00:00", "ate": "23:59"})   # a qualquer hora do dia


def test_agenda_lembretes_so_pede_quando_ha_e_no_maximo_a_cada_30_min(banco_agenda, agenda):
    """De 15 em 15 minutos, o comando pergunta ao banco (radar_lembretes_acionar) e só com lembrete para mandar pede à radar-redes
    ("acionar_lembretes", com a chave da agenda) que acione o robô dos lembretes. A mesma pendência é pedida no máximo uma vez a cada 30
    minutos (o token falhou ou o GitHub não rodou: o pedido volta 30 minutos depois); mandada hoje, o tipo espera o dia seguinte;
    desligado, nada é pedido."""
    with conectar(banco_agenda) as c:
        comando = c.execute("select command from cron.job where jobname = 'radar-redes-agenda-lembretes'").fetchone()[0]
        assert "where public.radar_lembretes_acionar()" in comando and "timeout_milliseconds := 60000" in comando
        pedidos = lambda: (c.execute("truncate net.pedidos"), c.execute(comando),
                           [tuple(r) for r in c.execute("select url, body, headers from net.pedidos order by id").fetchall()])[2]
        c.execute("""insert into radar_config (chave, valor) values ('lembretes', %s)
                     on conflict (chave) do update set valor = excluded.valor""", (LEMBRETES_ABERTOS,))
        minhas = []
        try:
            assert pedidos() == []                                                          # nada a lembrar: nenhum pedido
            peca = c.execute("""insert into radar_pauta_pecas (data, tipo, formato) values (radar_pauta_hoje() + 1, 'bastidor', 'foto')
                                returning id""").fetchone()[0]                              # a peça de amanhã, planejada
            minhas.append(peca)
            cab = {"Content-Type": "application/json", "Authorization": "Bearer " + chave_anon_do_config(), "x-radar-agenda": agenda}
            assert pedidos() == [(URL, {"acao": "acionar_lembretes"}, cab)]
            assert pedidos() == []                                                          # pedida há pouco: espera 30 minutos
            c.execute("update radar_lembretes set acionado_em = now() - interval '29 minutes'")
            assert pedidos() == []
            c.execute("update radar_lembretes set acionado_em = now() - interval '31 minutes'")
            assert len(pedidos()) == 1                                                      # o robô não veio: pede de novo
            minhas.append(c.execute("""insert into radar_pauta_pecas (data, tipo, formato) values (radar_pauta_hoje(), 'bastidor', 'foto')
                                       returning id""").fetchone()[0])
            assert len(pedidos()) == 1                                                      # pendência nova: pede (uma vez)
            assert pedidos() == []
            c.execute("""update radar_config set valor = valor || '{"ligado": false}' where chave = 'lembretes'""")
            c.execute("update radar_lembretes set acionado_em = null")
            assert pedidos() == []                                                          # desligado: nada
            c.execute("""update radar_config set valor = valor || '{"ligado": true}' where chave = 'lembretes'""")
            lote = c.execute("select radar_lembretes_lote_em(now())").fetchone()[0]       # o robô mandou o e-mail do dia
            for g in lote:
                c.execute("select radar_lembretes_enviado_em(%s::uuid, 9, %s::bigint[], now())", (g["lote"], [i["id"] for i in g["itens"]]))
            assert pedidos() == []                                                          # um e-mail por tipo por dia
        finally:
            c.execute("delete from radar_config where chave = 'lembretes'")
            c.execute("truncate radar_lembretes")
            c.execute("delete from radar_pauta_pecas where id = any(%s)", (minhas,))


def test_agenda_sem_o_setup_v029_para_com_recado(tmp_path):
    """O banco da v0.28.1 (sem as funções dos lembretes): o arquivo da agenda para com o recado, sem mexer no que estava agendado."""
    banco = "radar_agenda_v028"
    novo_banco(banco, com_setup=True, simulados=True)
    try:
        with conectar(banco) as c:
            c.execute("drop function public.radar_lembretes_acionar()")
            c.execute("select cron.schedule('radar-redes-agenda', '*/5 * * * *', 'select 1')")
        r = psql(sem_extensoes(AGENDA.read_text(), tmp_path), banco)
        assert r.returncode != 0 and "Rode antes o radar-setup-v0.45.0.sql" in r.stderr
        with conectar(banco) as c:
            assert c.execute("select jobname, command from cron.job").fetchall() == [("radar-redes-agenda", "select 1")]
            assert c.execute("select count(*) from vault.secrets").fetchone()[0] == 0
    finally:
        apagar_banco(banco)


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


def test_agendas_aceitam_a_chave_publica_nova_so_no_apikey(tmp_path):
    """Rodada 2 da varredura geral: o Supabase desliga a chave anon antiga (JWT) até o fim de 2026, e os dois arquivos das agendas só
    aceitavam um JWT com role anon. A chave pública nova (sb_publishable_…) agora vale e vai só no apikey (no Authorization o Supabase
    a recusa); o teste do fim de cada arquivo também. A chave interna continua recusada (test_agenda_recusa_jwt_service_role_e_sb_secret)."""
    nova = "sb_publishable_" + "Ab9_-x" * 6
    video = RAIZ / "sql" / "radar-video-agenda.sql"
    novo_banco("radar_agenda_nova", com_setup=True, simulados=True)
    try:
        for arquivo in (AGENDA, video):
            texto = arquivo.read_text()
            assert texto.count(chave_anon_do_config()) == 1
            r = psql(sem_extensoes(texto.replace(chave_anon_do_config(), nova), tmp_path, "nova-" + arquivo.name), "radar_agenda_nova")
            assert r.returncode == 0, r.stderr
        with conectar("radar_agenda_nova") as c:
            segredos = dict(c.execute("select name, decrypted_secret from vault.decrypted_secrets").fetchall())
            comandos = dict(c.execute("select jobname, command from cron.job").fetchall())
            assert {"radar-redes-agenda", "radar-redes-agenda-robos", "radar-video-reserva", "radar-video-limpeza"} <= set(comandos)
            for nome, comando in comandos.items():
                if "net.http_post" in comando:
                    assert "Authorization" not in comando and "Bearer" not in comando and f"'apikey', '{nova}'" in comando, nome
            c.execute("truncate net.pedidos")
            c.execute(comandos["radar-redes-agenda-robos"])
            for arquivo, segredo in ((AGENDA, "radar_redes_agenda"), (video, "radar_video_agenda")):     # o teste do fim do arquivo
                trecho = arquivo.read_text()[arquivo.read_text().index("-- Teste (n"):]
                c.execute("\n".join(re.findall(r"(?m)^--   (.*)$", trecho[:trecho.index("-- Depois de alguns segundos")])))
            cabecalhos = [r[0] for r in c.execute("select headers from net.pedidos order by id").fetchall()]
        assert cabecalhos == [{"Content-Type": "application/json", "apikey": nova, "x-radar-agenda": segredos["radar_redes_agenda"]}] * 2 + \
                            [{"Content-Type": "application/json", "apikey": nova, "x-radar-agenda": segredos["radar_video_agenda"]}]
    finally:
        apagar_banco("radar_agenda_nova")


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
        assert [n for (n,) in c.execute("select jobname from cron.job order by jobname").fetchall()] == [
            "radar-redes-agenda", "radar-redes-agenda-lembretes", "radar-redes-agenda-limpeza", "radar-redes-agenda-robos", "radar-redes-agenda-site"]
        assert c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda'").fetchone()[0] == agenda
        for nome in ("radar-itc", "copia-do-projeto"):                                        # as outras agendas ficam
            c.execute("select cron.schedule(%s, '55 5 * * *', 'select 1')", (nome,))
    for _ in range(2):                                                                        # a reversão pode rodar mais de uma vez
        r = psql(AGENDA_REVERSAO, banco_agenda)
        assert r.returncode == 0 and "Agenda da Pauta retirada." in r.stderr, r.stderr
    with conectar(banco_agenda) as c:
        assert sorted(n for (n,) in c.execute("select jobname from cron.job").fetchall()) == ["copia-do-projeto", "radar-itc"]
        assert c.execute("select count(*) from vault.secrets where name = 'radar_redes_agenda'").fetchone()[0] == 1   # a chave fica


# v0.23.0: o gatilho da Supabase que parava a 2ª rodada (grant_pg_cron_access, no "create extension" e nos grants do pg_cron), de
# mentira: falha em qualquer "create extension" e em qualquer grant
GATILHO_DA_SUPABASE = """
create function public.gatilho_da_supabase_simulado() returns event_trigger language plpgsql as $$
begin
  raise exception 'dependent privileges exist';
end $$;
create event trigger gatilho_da_supabase_simulado on ddl_command_end when tag in ('CREATE EXTENSION', 'GRANT')
  execute function public.gatilho_da_supabase_simulado();
"""


def test_as_tres_agendas_rodam_de_novo_sem_tocar_nas_extensoes(tmp_path):
    """v0.23.0 (a pendência da v0.22.1): rodar de novo no Supabase o radar-itc-agenda.sql, o radar-redes-agenda.sql ou o
    radar-video-agenda.sql parava em "ERROR: dependent privileges exist": com o pg_cron instalado, o "create extension" e os grants do
    cabeçalho disparavam o gatilho da Supabase. Com as extensões instaladas, nenhum dos dois roda: com um gatilho de mentira que falha
    em qualquer um, cada agenda roda duas vezes seguidas sem erro, sem duplicar agendamento e sem trocar a chave do Vault. Sem a
    extensão, o bloco ainda a cria (no banco de teste ela não existe: o erro mostra a tentativa, e nada mais roda)."""
    banco = "radar_agenda_de_novo"
    novo_banco(banco, com_setup=True, simulados=True)
    try:
        with conectar(banco) as c:
            c.execute(GATILHO_DA_SUPABASE)
        for arquivo in (AGENDA_ITC, AGENDA, AGENDA_VIDEO):
            for vez in (1, 2):
                r = psql(sem_extensoes(arquivo.read_text(), tmp_path, f"{vez}-{arquivo.name}"), banco)
                assert r.returncode == 0, (arquivo.name, vez, r.stderr)
                with conectar(banco) as c:
                    estado = (c.execute("select jobname, schedule, command from cron.job order by jobname").fetchall(),
                              c.execute("select name, decrypted_secret from vault.decrypted_secrets order by name").fetchall())
                if vez == 2:
                    assert estado == antes, arquivo.name                                   # a 2ª rodada refaz igual
                antes = estado
        jobs, segredos = dict((n, (s, cmd)) for n, s, cmd in antes[0]), dict(antes[1])
        assert sorted(jobs) == ["radar-itc", "radar-itc-completa", "radar-redes-agenda", "radar-redes-agenda-lembretes", "radar-redes-agenda-limpeza",
                                "radar-redes-agenda-robos", "radar-redes-agenda-site", "radar-video-limpeza", "radar-video-reserva"]
        assert sorted(segredos) == ["radar_itc_agenda", "radar_redes_agenda", "radar_video_agenda", "radar_video_robo"]
        # a agenda da ITC (sem teste antes): 02h55 de Brasília, o complemento só com boletim para depois, a chave lida do Vault na hora
        assert jobs["radar-itc"][0] == "55 5 * * *" and jobs["radar-itc-completa"][0] == "10,25 6 * * *"
        assert all(segredos["radar_itc_agenda"] not in cmd for _, cmd in jobs.values())
        with conectar(banco) as c:
            c.execute("truncate net.pedidos")
            c.execute(jobs["radar-itc"][1])
            c.execute(jobs["radar-itc-completa"][1])                                   # nada ficou para depois: não chama
            pedidos = [tuple(p) for p in c.execute("select url, body, headers from net.pedidos order by id").fetchall()]
        assert pedidos == [("https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-itc", {"acao": "ler"},
                            {"Content-Type": "application/json", "x-radar-agenda": segredos["radar_itc_agenda"]})]
        # com boletim para depois, o complemento chama. O gatilho de mentira barra qualquer GRANT (o da Supabase, só os do pg_cron):
        # sai antes do SQL das fontes (que cadastra a itc-email)
        with conectar(banco) as c:
            c.execute("alter event trigger gatilho_da_supabase_simulado disable")
        assert psql(RAIZ / "sql" / "radar-fontes-novas-2026-10.sql", banco).returncode == 0
        with conectar(banco) as c:
            c.execute("update radar_fontes set ultimo_erro = 'Leitura do boletim: 2 boletim(ns) ficaram para a próxima leitura' "
                      "where slug = 'itc-email'")
            c.execute("truncate net.pedidos")
            c.execute(jobs["radar-itc-completa"][1])
            assert [u for (u,) in c.execute("select url from net.pedidos").fetchall()] == [pedidos[0][0]]
        # sem a extensão instalada, o bloco tenta criá-la (e para ali, com o ON_ERROR_STOP do SQL Editor)
        for arquivo in (AGENDA_ITC, AGENDA, AGENDA_VIDEO):
            r = psql(arquivo, banco)
            assert r.returncode != 0 and 'extension "pg_cron" is not available' in r.stderr, (arquivo.name, r.stderr)
        r = psql(RAIZ / "sql" / "radar-concorrentes.sql", banco)
        assert r.returncode != 0 and 'extension "pg_net" is not available' in r.stderr, r.stderr
        with conectar(banco) as c:
            assert c.execute("select jobname, schedule, command from cron.job order by jobname").fetchall() == antes[0]
    finally:
        apagar_banco(banco)


# ------------------------------------------------------------------- v0.32.0: a cópia mensal do banco no OneDrive
AGENDA_COPIA = RAIZ / "sql" / "radar-copia-agenda.sql"
AGENDA_COPIA_REVERSAO = RAIZ / "sql" / "radar-copia-agenda-reversao.sql"
URL_COPIA = "https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-copia"


def test_agenda_da_copia_mensal_e_reversao(tmp_path):
    """sql/radar-copia-agenda.sql: roda duas vezes sem erro (com o gatilho da Supabase de mentira, sem tocar nas extensões) e igual; três
    agendamentos (dia 1 às 04h10 e às 05h10, dia 2 às 04h10 de Brasília); a chave 'radar_copia_agenda' (64 caracteres) só no Vault, fora
    dos comandos; o comando só pede a cópia quando o mês ainda não tem cópia OK nem uma em andamento, com só o x-radar-agenda (a
    radar-copia fica com o "Verify JWT" desligado: sem Authorization nem apikey) e 150 s de espera; o teste do fim do arquivo roda como
    está; sem o setup, para com o recado; a reversão tira os três (a chave fica), e a reversão do setup também."""
    banco = "radar_agenda_copia"
    novo_banco(banco, com_setup=True, simulados=True)
    try:
        with conectar(banco) as c:
            c.execute(GATILHO_DA_SUPABASE)
        antes = None
        for vez in (1, 2):
            r = psql(sem_extensoes(AGENDA_COPIA.read_text(), tmp_path, f"copia-{vez}.sql"), banco)
            assert r.returncode == 0, (vez, r.stderr)
            with conectar(banco) as c:
                estado = (c.execute("select jobname, schedule, command, active from cron.job order by jobname").fetchall(),
                          c.execute("select name, decrypted_secret from vault.decrypted_secrets order by name").fetchall())
            assert antes is None or estado == antes, "a 2ª rodada refaz igual"
            antes = estado
        jobs, segredos = {n: (s, cmd, a) for n, s, cmd, a in antes[0]}, dict(antes[1])
        assert {n: (s, a) for n, (s, _, a) in jobs.items()} == {"radar-copia": ("10 7 1 * *", True), "radar-copia-de-novo": ("10 8 1 * *", True),
                                                               "radar-copia-dia-2": ("10 7 2 * *", True)}
        assert list(segredos) == ["radar_copia_agenda"] and re.fullmatch(r"[0-9a-f]{64}", segredos["radar_copia_agenda"])
        assert all(segredos["radar_copia_agenda"] not in cmd for _, cmd, _ in jobs.values())
        assert len({cmd for _, cmd, _ in jobs.values()}) == 1                                    # o mesmo pedido nos três horários
        comando = jobs["radar-copia"][1]
        for trecho in (URL_COPIA, "'x-radar-agenda'", "vault.decrypted_secrets", "radar_copia_agenda", "where public.radar_copias_falta_mes()",
                       "timeout_milliseconds := 150000", '{"acao": "copiar"}'):
            assert trecho in comando, trecho
        assert "Authorization" not in comando and "apikey" not in comando and "Bearer" not in comando
        with conectar(banco) as c:
            pedidos = lambda: (c.execute("truncate net.pedidos"), c.execute(comando),
                               [tuple(r) for r in c.execute("select url, body, headers, timeout_milliseconds from net.pedidos order by id")])[2]
            cab = {"Content-Type": "application/json", "x-radar-agenda": segredos["radar_copia_agenda"]}
            assert pedidos() == [(URL_COPIA, {"acao": "copiar"}, cab, 150000)]                 # sem cópia no mês: pede
            c.execute("""insert into radar_copias (mes, origem, iniciado_em, arquivo)
                         values (date_trunc('month', now() at time zone 'America/Sao_Paulo')::date, 'agenda', now() - interval '3 minutes',
                                 'radar-copia-2026-11-01-0410.zip')""")
            assert pedidos() == []                                                              # uma em andamento: espera
            c.execute("update radar_copias set iniciado_em = now() - interval '30 minutes'")
            assert len(pedidos()) == 1                                                          # parada há 30 minutos: pede de novo
            c.execute("update radar_copias set ok = true, concluido_em = now()")
            assert pedidos() == []                                                              # o mês já tem cópia: nenhum pedido
            # o teste do fim do arquivo (sem os "--"): um pedido "agenda_teste", com a chave do Vault
            texto = AGENDA_COPIA.read_text()
            trecho = texto[texto.index("-- Teste (não copia nada)"):]
            linhas = re.findall(r"(?m)^--   (.*)$", trecho[:trecho.index("-- Depois de alguns segundos")])
            assert len(linhas) == 3 and not re.search(r"<[^>]*>", "\n".join(linhas))
            c.execute("truncate net.pedidos")
            c.execute("\n".join(linhas))
            assert [tuple(r) for r in c.execute("select url, body, headers from net.pedidos")] == [(URL_COPIA, {"acao": "agenda_teste"}, cab)]
            for nome in ("radar-itc", "radar-video-reserva"):                                  # as outras agendas ficam
                c.execute("select cron.schedule(%s, '55 5 * * *', 'select 1')", (nome,))
        for _ in range(2):                                                                      # a reversão pode rodar mais de uma vez
            r = psql(AGENDA_COPIA_REVERSAO, banco)
            assert r.returncode == 0 and "Agenda da cópia retirada." in r.stderr, r.stderr
        with conectar(banco) as c:
            assert sorted(n for (n,) in c.execute("select jobname from cron.job")) == ["radar-itc", "radar-video-reserva"]
            assert c.execute("select count(*) from vault.secrets where name = 'radar_copia_agenda'").fetchone()[0] == 1   # a chave fica
        assert psql(sem_extensoes(AGENDA_COPIA.read_text(), tmp_path, "copia-3.sql"), banco).returncode == 0
        with conectar(banco) as c:                                                              # de volta, com a mesma chave
            assert c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_copia_agenda'").fetchone()[0] == \
                segredos["radar_copia_agenda"]
            c.execute("alter event trigger gatilho_da_supabase_simulado disable")
        r = psql(REVERSAO, banco)                                                               # a reversão do setup tira a agenda também
        assert r.returncode == 0, r.stderr
        with conectar(banco) as c:
            assert c.execute("select count(*) from cron.job where jobname like 'radar-copia%'").fetchone()[0] == 0
    finally:
        apagar_banco(banco)
    novo_banco("radar_agenda_copia_sem", com_setup=False, simulados=True)                     # sem o setup: o recado, e nada fica pela metade
    try:
        r = psql(sem_extensoes(AGENDA_COPIA.read_text(), tmp_path, "copia-sem.sql"), "radar_agenda_copia_sem")
        assert r.returncode != 0 and "Rode antes o radar-setup-v0.32.0.sql" in r.stderr
        with conectar("radar_agenda_copia_sem") as c:
            assert c.execute("select (select count(*) from vault.secrets), (select count(*) from cron.job)").fetchone() == (0, 0)
    finally:
        apagar_banco("radar_agenda_copia_sem")
