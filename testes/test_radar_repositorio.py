"""Repositório público (v0.21.0): o calendário da Pauta, que tem os nomes da equipe, nunca vai para o GitHub.

Confere os arquivos versionados e os novos que o .gitignore não barra (git ls-files --cached --others --exclude-standard): nenhum
pode ter uma linha que comece com o cabeçalho do calendário — separado por ponto e vírgula, vírgula (o "Baixar como CSV" do Google
Sheets e o padrão do LibreOffice) ou tabulação, com ou sem aspas, ou em tabela de markdown (o .md do calendário) — nem com o
cabeçalho da tabela das pessoas dos .md do plano ("| Pessoa | Área |"). A única exceção é a amostra inventada,
testes/amostras/pauta-ficticia.csv, só com nomes de mentira. Um calendário de teste montado dentro de outro arquivo (num teste de
tela, por exemplo) também é barrado: use a amostra ou grave o arquivo numa pasta temporária. O cabeçalho citado no meio de uma linha
(a tela confere o cabeçalho do CSV) não conta. E o .gitignore barra qualquer CSV novo e os .md do plano, com acento, maiúscula ou
em outra pasta. Sem o git (pacote baixado em .zip), os testes são pulados.

O workflow dos testes roda quando muda o que eles leem: a tela passou a ter dois scripts (radar-config.js e radar-pauta.js, que
antes não estava na lista: mudar só ele não rodava os testes), e o SQL da agenda leva a chave anon de radar-config.js. E este
arquivo roda em TODO push (radar-repositorio.yml, sem filtro de caminho): o calendário solto na raiz, ou enviado pelo site do
GitHub (que não passa pelo .gitignore), não muda nenhum caminho do radar-testes.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess

import pytest

from conftest import RAIZ

# o cabeçalho do calendário em CSV (; , ou tabulação, com ou sem aspas), em tabela de markdown (com ou sem a coluna "semana") e o
# da tabela das pessoas dos .md do plano
CABECALHO = re.compile(r'(?im)^﻿?"?data"?[;,\t]"?dia"?[;,\t]"?semana"?[;,\t]"?tipo"?[;,\t]"?formato"?[;,\t]"?assunto"?[;,\t]"?quem_aparece'
                       r'|^[ \t]*\|[ \t]*data[ \t]*\|[ \t]*dia[ \t]*\|(?:[ \t]*semana[ \t]*\|)?[ \t]*tipo[ \t]*\|[ \t]*formato[ \t]*\|'
                       r'|^[ \t]*\|[ \t]*pessoa[ \t]*\|[ \t]*área[ \t]*\|')
COLUNAS = ["data", "dia", "semana", "tipo", "formato", "assunto", "quem_aparece", "objetivo", "observacao"]
AMOSTRA = "testes/amostras/pauta-ficticia.csv"
NOMES_DA_AMOSTRA = {"Ana Teste", "Bruno Exemplo", "Carla Modelo", "Equipe", "—", "Ana Teste e Bruno Exemplo", "Carla Modelo; Bruno Exemplo"}


def git(*args) -> subprocess.CompletedProcess:
    if shutil.which("git") is None:
        pytest.skip("git não instalado")
    r = subprocess.run(["git", "-C", str(RAIZ), *args], capture_output=True)
    if r.returncode not in (0, 1) or not (RAIZ / ".git").exists():
        pytest.skip("fora de um repositório git (pacote .zip)")
    return r


def test_nenhum_csv_da_pauta_versionado():
    nomes = [n for n in git("ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout.decode("utf-8", "replace").split("\0") if n]
    assert AMOSTRA in nomes
    achados = [n for n in nomes if n != AMOSTRA and (RAIZ / n).is_file()
               and CABECALHO.search((RAIZ / n).read_bytes()[:20_000_000].decode("utf-8", "ignore"))]
    assert achados == [], "calendário da Pauta (com nomes da equipe?) no repositório: " + ", ".join(achados)
    # a amostra é o calendário no formato do plano, só com nomes inventados
    linhas = list(csv.reader(io.StringIO((RAIZ / AMOSTRA).read_text(encoding="utf-8-sig")), delimiter=";"))
    assert linhas[0] == COLUNAS
    assert len(linhas) > 7 and all(len(l) == 9 for l in linhas)
    assert {l[6] for l in linhas[1:]} <= NOMES_DA_AMOSTRA


def test_cabecalho_do_calendario_em_outros_formatos_tambem_e_achado():
    """O cabeçalho é achado com vírgula, tabulação, aspas e maiúsculas, no .md do calendário e na tabela das pessoas; citado no meio da
    linha (como no LEIAME e na tela), não. Os exemplos são montados aqui (escritos no começo de uma linha, este arquivo seria achado)."""
    tabela = lambda colunas: "| " + " | ".join(colunas) + " |"
    for texto in [";".join(COLUNAS), ",".join(COLUNAS), "\t".join(COLUNAS), ",".join(f'"{c}"' for c in COLUNAS), ";".join(COLUNAS).upper(),
                  "\ufeff" + ",".join(COLUNAS), "Intro\n\n" + tabela(["Data", "Dia", "Tipo", "Formato", "Assunto", "Quem aparece"]),
                  tabela(["Data", "Dia", "Semana", "Tipo", "Formato"]), "  " + tabela(["Pessoa", "Área", "Como aparece"])]:
        assert CABECALHO.search(texto), texto
    for texto in ["as colunas " + ";".join(COLUNAS), "const x = [" + ", ".join(f'"{c}"' for c in COLUNAS) + "]", tabela(["Dia", "Tipo de peça"]),
                  tabela(["Pessoa", "Função"])]:
        assert not CABECALHO.search(texto), texto


def test_gitignore_barra_o_calendario_da_pauta():
    for nome in ("2b-calendario.csv", "plano-publicacoes-artecon-2026-10-12/2b-calendario.csv", "plano-publicacoes/README.md",
                 "testes/amostras/pauta-real.csv", "sql/pauta-novembro.csv", "calendario-2027.csv",
                 # com acento, maiúscula ou outro nome (o .gitignore do Linux do GitHub diferencia maiúsculas)
                 "Calendário de publicações.csv", "calendário.csv", "Calendario.csv", "CALENDARIO.CSV", "Pauta-novembro.csv", "redes.csv",
                 # os .md do plano, soltos em qualquer pasta
                 "1-PLANO-resumo.md", "2-calendario-26-10-a-31-01.md", "3-roteiros-dos-reels.md", "4-serie-pessoas.md", "docs/4-serie-pessoas.md",
                 "4b-captacao-mensal.md", "5-guia-de-producao.md", "6-regras-legais-e-termo.md"):
        assert git("check-ignore", "-q", "--no-index", nome).returncode == 0, nome
    for nome in (AMOSTRA, "testes/ia_central/producao-2026-10-03.csv",                                           # vão para o repositório
                 "radar-pauta.js", "radar-video.js", "LEIAME-radar.md", "RELATORIO-TESTES-radar.md", "testes/test_radar_agenda.py"):
        assert git("check-ignore", "-q", "--no-index", nome).returncode == 1, nome


def test_workflow_dos_testes_roda_quando_mudam_os_arquivos_da_tela():
    yml = (RAIZ / ".github" / "workflows" / "radar-testes.yml").read_text(encoding="utf-8")
    caminhos = set(re.findall(r'"([^"]+)"', re.search(r"(?m)^\s*paths:\s*\[([^\]]*)\]", yml).group(1)))
    scripts = {src for pagina in ("index.html", "informativo.html")
               for src in re.findall(r'<script src="([^"?#]+)', (RAIZ / pagina).read_text(encoding="utf-8"))}
    assert scripts == {"radar-config.js", "radar-pauta.js", "radar-video.js"}  # os da própria tela (nenhum de fora; v0.22.0: o corretor de vídeo)
    assert scripts | {"index.html", "informativo.html", ".gitignore", "testes/**", "sql/**"} <= caminhos, sorted(caminhos)


def test_workflow_do_repositorio_roda_em_todo_push():
    """O conferir do repositório roda em todo push, sem filtro de caminho nem de branch (o calendário solto na raiz não muda nenhum
    caminho do radar-testes), e roda este arquivo."""
    yml = (RAIZ / ".github" / "workflows" / "radar-repositorio.yml").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in yml.splitlines() if not l.lstrip().startswith("#"))
    assert re.search(r"(?m)^on:\s*\n\s+push:\s*$", codigo), codigo
    assert not re.search(r"(?m)^\s+(paths|paths-ignore|branches|branches-ignore|tags)\s*:", codigo), codigo
    assert "python -m pytest testes/test_radar_repositorio.py" in codigo
