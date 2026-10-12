"""Repositório público (v0.21.0): o calendário da Pauta, que tem os nomes da equipe, nunca vai para o GitHub.

Confere os arquivos versionados e os novos que o .gitignore não barra (git ls-files --cached --others --exclude-standard): nenhum
pode ter uma linha que comece com o cabeçalho do calendário (data;dia;semana;tipo;formato;assunto;quem_aparece). A única exceção é
a amostra inventada, testes/amostras/pauta-ficticia.csv, só com nomes de mentira. Um calendário de teste montado dentro de outro
arquivo (num teste de tela, por exemplo) também é barrado: use a amostra ou grave o arquivo numa pasta temporária. O cabeçalho
citado no meio de uma linha (a tela confere o cabeçalho do CSV) não conta. E o .gitignore barra o CSV do plano onde quer que ele
seja copiado. Sem o git (pacote baixado em .zip), os testes são pulados.

E o workflow dos testes roda quando muda o que eles leem: a tela passou a ter dois scripts (radar-config.js e radar-pauta.js, que
antes não estava na lista: mudar só ele não rodava os testes), e o SQL da agenda leva a chave anon de radar-config.js.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess

import pytest

from conftest import RAIZ

CABECALHO = re.compile(r'(?im)^﻿?"?data"?;"?dia"?;"?semana"?;"?tipo"?;"?formato"?;"?assunto"?;"?quem_aparece')
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
    assert linhas[0] == ["data", "dia", "semana", "tipo", "formato", "assunto", "quem_aparece", "objetivo", "observacao"]
    assert len(linhas) > 7 and all(len(l) == 9 for l in linhas)
    assert {l[6] for l in linhas[1:]} <= NOMES_DA_AMOSTRA


def test_gitignore_barra_o_calendario_da_pauta():
    for nome in ("2b-calendario.csv", "plano-publicacoes-artecon-2026-10-12/2b-calendario.csv", "plano-publicacoes/README.md",
                 "testes/amostras/pauta-real.csv", "sql/pauta-novembro.csv", "calendario-2027.csv"):
        assert git("check-ignore", "-q", "--no-index", nome).returncode == 0, nome
    assert git("check-ignore", "-q", "--no-index", AMOSTRA).returncode == 1          # a amostra inventada vai para o repositório


def test_workflow_dos_testes_roda_quando_mudam_os_arquivos_da_tela():
    yml = (RAIZ / ".github" / "workflows" / "radar-testes.yml").read_text(encoding="utf-8")
    caminhos = set(re.findall(r'"([^"]+)"', re.search(r"(?m)^\s*paths:\s*\[([^\]]*)\]", yml).group(1)))
    scripts = {src for pagina in ("index.html", "informativo.html")
               for src in re.findall(r'<script src="([^"?#]+)', (RAIZ / pagina).read_text(encoding="utf-8"))}
    assert scripts == {"radar-config.js", "radar-pauta.js"}                   # os da própria tela (nenhum de fora)
    assert scripts | {"index.html", "informativo.html", ".gitignore", "testes/**", "sql/**"} <= caminhos, sorted(caminhos)
