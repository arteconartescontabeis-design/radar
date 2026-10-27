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

v0.22.0 (corretor de vídeo): no repositório público entram só vídeos SINTÉTICOS, gerados pelo ffmpeg na hora dos testes, numa pasta
temporária. Nenhum arquivo de vídeo, áudio ou foto (pela extensão ou pelo começo do arquivo, com qualquer nome; a captura de tela é
PNG), nenhum arquivo de trabalho do robô (o pedido, o estado, o resultado, o erro, a transcrição e a luz de cada clipe) e nenhuma
transcrição (a resposta da Azure, as palavras com tempo, o relatório com o texto final, a fala e a cartela do pedido, a legenda ASS,
SRT ou VTT) fora do código do robô (robo/video/) e dos geradores sintéticos dos testes do vídeo; as únicas imagens são as do pacote
(logotipo e timbrado). O .gitignore barra as extensões de vídeo, áudio e foto e os arquivos de trabalho. No radar-repositorio.yml, com
o histórico inteiro, o conferir olha também cada commit do push: o arquivo enviado num commit e apagado no seguinte fica no histórico. E a
versão do pacote é uma só em todos os arquivos que a levam (a tela, os dois scripts, a função nova, o robô do vídeo, o SQL, o LEIAME e
o relatório), e as funções do pacote atendem à versão mínima que a tela pede. v0.23.0: o que não mudou na versão (o banco, a função
radar-video e o robô do vídeo) fica na versão em que mudou por último, nunca à frente da tela.
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess

import pytest

from conftest import RAIZ, REVERSAO, SETUP

# o cabeçalho do calendário em CSV (; , ou tabulação, com ou sem aspas), em tabela de markdown (com ou sem a coluna "semana") e o
# da tabela das pessoas dos .md do plano
CABECALHO = re.compile(r'(?im)^﻿?"?data"?[;,\t]"?dia"?[;,\t]"?semana"?[;,\t]"?tipo"?[;,\t]"?formato"?[;,\t]"?assunto"?[;,\t]"?quem_aparece'
                       r'|^[ \t]*\|[ \t]*data[ \t]*\|[ \t]*dia[ \t]*\|(?:[ \t]*semana[ \t]*\|)?[ \t]*tipo[ \t]*\|[ \t]*formato[ \t]*\|'
                       r'|^[ \t]*\|[ \t]*pessoa[ \t]*\|[ \t]*área[ \t]*\|')
COLUNAS = ["data", "dia", "semana", "tipo", "formato", "assunto", "quem_aparece", "objetivo", "observacao"]
AMOSTRA = "testes/amostras/pauta-ficticia.csv"
NOMES_DA_AMOSTRA = {"Ana Teste", "Bruno Exemplo", "Carla Modelo", "Equipe", "—", "Ana Teste e Bruno Exemplo", "Carla Modelo; Bruno Exemplo"}


# v0.22.0: vídeo, áudio e foto (pela extensão, em qualquer caixa; o .ts do MPEG-TS fica de fora, que é o das funções do Supabase, e o
# começo do arquivo pega o vídeo com outro nome) e os arquivos de trabalho do robô do vídeo (robo/video/corrigir.py)
MIDIA = {".mp4", ".mov", ".m4v", ".m4a", ".3gp", ".3g2", ".mkv", ".webm", ".avi", ".wmv", ".flv", ".m2ts", ".hevc",
         ".h264", ".wav", ".mp3", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".amr", ".aif", ".aiff", ".caf",
         ".jpg", ".jpeg", ".heic", ".heif", ".webp", ".gif", ".tif", ".tiff", ".bmp", ".dng", ".png", ".ass", ".ssa", ".srt", ".vtt"}
IMAGENS_DO_PACOTE = {"radar-logo-artecon.png", "radar-logo-artecon-branco.png", "radar-timbrado-topo.png", "radar-timbrado-rodape.png"}
# (o pedido com a fala e a cartela, o estado com o alinhamento, o resultado com o relatório, o erro, os temporários ".<nome>.json" de
# cada um, a transcrição guardada e a enviada, o pedido da transcrição, o erro dela e a luz de cada clipe)
TRABALHO_DO_ROBO = {"palavras.json", "palavras_envio.json", "pedido_fala.json", "transcricao_erro.txt", "pedido.json", "estado.json",
                    "resultado.json", "erro.json", ".pedido.json", ".estado.json", ".resultado.json", ".erro.json"}
LUZ_DO_ROBO = re.compile(r"luz\d{1,2}\.txt")
# a transcrição: a resposta da Azure (Speech SDK ou fast transcription), as palavras com tempo do robô (palavras.json), a legenda ASS
# e a SRT/VTT. Só no código do robô e nos geradores sintéticos dos testes do vídeo
# e o estado do robô (as palavras do alinhamento com "ini"), o resultado (o relatório com o texto final) e o pedido (a fala para
# conferência e as linhas da cartela, com o nome e o CRC de quem fala)
TRANSCRICAO = re.compile(r'(?m)"(?:NBest|RecognitionStatus|combinedPhrases|offsetMilliseconds|durationMilliseconds|MaskedITN|Lexical|DisplayText)"\s*:'
                         r"""|["']texto["']\s*:\s*["'][^"'\n]*["']\s*,\s*["'](?:inicio|ini)["']\s*:"""
                         r'|"(?:texto_final|fala_roteiro)"\s*:\s*"[^"\n]{3,}|"cartela_linhas"\s*:\s*\[\s*"'
                         r"|^Dialogue:\s*\d+,\d+:\d\d:\d\d\.\d\d,|\d\d:\d\d:\d\d[,.]\d{3}\s*-->\s*\d\d:\d\d:\d\d[,.]\d{3}")
TRANSCRICAO_PODE = re.compile(r"robo/video/[a-z_]+\.py|testes/test_radar_video_[a-z_]+\.py|testes/radar_video_[a-z_]+\.py")


def midia_pelo_conteudo(b: bytes) -> str:
    """O tipo pelo começo do arquivo (o nome não importa): "" quando não é vídeo, áudio nem foto."""
    if b[4:8] == b"ftyp" or b[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip"):
        return "MP4/MOV/HEIC (ISO)"
    if b[:4] == b"RIFF" and b[8:12] in (b"WAVE", b"AVI ", b"WEBP"):
        return "RIFF " + b[8:12].decode().strip()
    for assinatura, tipo in ((b"\x1aE\xdf\xa3", "Matroska/WebM"), (b"ID3", "MP3"), (b"OggS", "Ogg/Opus"), (b"fLaC", "FLAC"),
                             (b"#!AMR", "AMR"), (b"FORM", "AIFF"), (b"caff", "CAF"), (b"FLV", "FLV"), (b"\xff\xd8\xff", "JPEG"),
                             (b"\x89PNG", "PNG"), (b"GIF8", "GIF"), (b"\x30\x26\xb2\x75\x8e\x66\xcf\x11", "ASF/WMA"),
                             (b"\x00\x00\x01\xba", "MPEG-PS"), (b"\x00\x00\x01\xb3", "MPEG")):
        if b.startswith(assinatura):
            return tipo
    if len(b) > 1 and b[0] == 0xFF and b[1] & 0xF6 == 0xF0:
        return "AAC (ADTS)"
    return ""


def problemas_do_arquivo(n: str, b: bytes) -> list[str]:
    """O que o arquivo n (com o conteúdo b) não pode ser no repositório público: "midia (tipo)", "trabalho" ou "transcricao"."""
    base = n.rsplit("/", 1)[-1]
    tipo, achados = midia_pelo_conteudo(b[:64]), []
    if n not in IMAGENS_DO_PACOTE and (("." + base.rsplit(".", 1)[-1].lower() in MIDIA and "." in base) or tipo):
        achados.append(f"midia ({tipo or 'extensão'})")
    if base.lower() in TRABALHO_DO_ROBO or LUZ_DO_ROBO.fullmatch(base):
        achados.append("trabalho")
    if not TRANSCRICAO_PODE.fullmatch(n) and TRANSCRICAO.search(b[:20_000_000].decode("utf-8", "ignore")):
        achados.append("transcricao")
    return achados


def faixa_do_push(antes: str, ramo: str = "", depois: str = "HEAD", raiz=RAIZ) -> list[str]:
    """Os argumentos do rev-list com os commits que o push levou: antes..depois. v0.22.0 (varredura geral): no primeiro push de um ramo
    (o GitHub manda o "antes" só com zeros — o caminho de toda sessão nova), os commits do ramo que nenhum outro ramo do GitHub tem (o
    checkout traz todos, com fetch-depth 0; o do próprio ramo fica de fora) ou, sem o nome do ramo, os que não estão no main."""
    if not set(antes) <= {"0"}:
        return [f"{antes}..{depois}"]
    if ramo:
        return [depois, "--not", f"--exclude=origin/{ramo}", "--remotes=origin"]      # o --exclude do --remotes não leva "refs/remotes/"
    return [depois, "--not", "refs/remotes/origin/main"]


def arquivos_dos_commits(antes: str, depois: str = "HEAD", raiz=RAIZ, faixa: list[str] | None = None) -> list[tuple[str, str, bytes]]:
    """Os arquivos acrescentados ou mudados em cada commit de antes..depois, ou da faixa dada (o que um push levou ao histórico, ainda
    que apagado no commit seguinte): [(commit, caminho, conteúdo)]."""
    rodar = lambda *a: subprocess.run(["git", "-C", str(raiz), *a], capture_output=True, check=True).stdout
    saida = []
    for c in rodar("rev-list", "--reverse", *(faixa or [f"{antes}..{depois}"])).decode().split():
        for n in rodar("diff-tree", "--root", "--no-commit-id", "-r", "-z", "--diff-filter=AM", "--name-only", c).decode("utf-8", "replace").split("\0"):
            if n:
                saida.append((c, n, rodar("cat-file", "blob", f"{c}:{n}")[:20_000_000]))
    return saida


def arquivos_do_repositorio() -> list[str]:
    """Os versionados e os novos que o .gitignore não barra (o que um "git add ." levaria)."""
    return [n for n in git("ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout.decode("utf-8", "replace").split("\0")
            if n and (RAIZ / n).is_file()]


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
                 "radar-pauta.js", "radar-video.js", "radar-setor.js", "radar-respostas.js", "LEIAME-radar.md", "RELATORIO-TESTES-radar.md", "testes/test_radar_agenda.py"):
        assert git("check-ignore", "-q", "--no-index", nome).returncode == 1, nome


def test_workflow_dos_testes_roda_quando_mudam_os_arquivos_da_tela():
    yml = (RAIZ / ".github" / "workflows" / "radar-testes.yml").read_text(encoding="utf-8")
    caminhos = set(re.findall(r'"([^"]+)"', re.search(r"(?m)^\s*paths:\s*\[([^\]]*)\]", yml).group(1)))
    scripts = {src for pagina in ("index.html", "informativo.html")
               for src in re.findall(r'<script src="([^"?#]+)', (RAIZ / pagina).read_text(encoding="utf-8"))}
    assert scripts == {"radar-config.js", "radar-pauta.js", "radar-video.js", "radar-setor.js", "radar-respostas.js"}  # os da própria tela (nenhum de fora; v0.22.0: o corretor de vídeo; v0.34.0: a aba Setor)
    assert scripts | {"index.html", "informativo.html", ".gitignore", "testes/**", "sql/**"} <= caminhos, sorted(caminhos)


def test_workflow_do_repositorio_roda_em_todo_push():
    """O conferir do repositório roda em todo push, sem filtro de caminho nem de branch (o calendário solto na raiz não muda nenhum
    caminho do radar-testes), e roda este arquivo."""
    yml = (RAIZ / ".github" / "workflows" / "radar-repositorio.yml").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in yml.splitlines() if not l.lstrip().startswith("#"))
    assert re.search(r"(?m)^on:\s*\n\s+push:\s*$", codigo), codigo
    assert not re.search(r"(?m)^\s+(paths|paths-ignore|branches|branches-ignore|tags)\s*:", codigo), codigo
    assert "python -m pytest testes/test_radar_repositorio.py" in codigo


# ------------------------------------------------------------- v0.22.0: só vídeo sintético, nada de gravação real nem de transcrição
def test_nenhum_video_audio_foto_nem_transcricao_no_repositorio():
    """O que um "git add ." levaria: nenhum vídeo, áudio ou foto (pela extensão ou pelo começo do arquivo, com qualquer nome; só as
    imagens do pacote), nenhum arquivo de trabalho do robô e nenhuma transcrição fora do código do robô e dos geradores sintéticos."""
    nomes = arquivos_do_repositorio()
    assert "robo/video/transcrever.py" in nomes and "radar-logo-artecon.png" in nomes                      # a lista é a de verdade
    midia, trabalho, transcricao = [], [], []
    for n in nomes:
        for p in problemas_do_arquivo(n, (RAIZ / n).read_bytes()):
            (midia if p.startswith("midia") else trabalho if p == "trabalho" else transcricao).append(n + p.removeprefix("midia"))
    assert midia == [], "vídeo, áudio ou foto no repositório público (só vídeos sintéticos, gerados na hora dos testes): " + ", ".join(midia)
    assert trabalho == [], "arquivo de trabalho do robô do vídeo no repositório: " + ", ".join(trabalho)
    assert transcricao == [], "transcrição (ou legenda com tempo) fora do código do robô e dos testes sintéticos: " + ", ".join(transcricao)
    # as imagens do pacote continuam as de sempre (PNG), e as fontes da cartela não contam como mídia
    assert all(midia_pelo_conteudo((RAIZ / n).read_bytes()[:64]) == "PNG" for n in IMAGENS_DO_PACOTE)
    assert midia_pelo_conteudo((RAIZ / "robo/video/fontes/DMSans-Bold.ttf").read_bytes()[:64]) == ""


def test_commits_do_push_sem_video_audio_foto_nem_transcricao():
    """O que o push levou ao histórico público (radar-repositorio.yml passa o commit de antes do push em RADAR_PUSH_ANTES e o ramo em
    RADAR_PUSH_RAMO, com o histórico inteiro): o arquivo enviado num commit e apagado no seguinte some da árvore, mas fica no histórico.
    v0.22.0 (varredura geral): no primeiro push de um ramo (o "antes" só com zeros), os commits do ramo que nenhum outro ramo tem (antes,
    só a árvore contava, e esse é o caminho de toda sessão nova). Sem o "antes" (o teste local, o "Run workflow"), só a árvore conta."""
    antes, ramo = os.environ.get("RADAR_PUSH_ANTES", "").strip(), os.environ.get("RADAR_PUSH_RAMO", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", antes) or (set(antes) != {"0"} and git("cat-file", "-e", antes + "^{commit}").returncode != 0):
        pytest.skip("sem o commit de antes do push (só no radar-repositorio.yml)")
    faixa = faixa_do_push(antes, ramo)
    achados = [f"{n} no commit {c[:7]} ({', '.join(p)})" for c, n, b in arquivos_dos_commits(antes, faixa=faixa) if (p := problemas_do_arquivo(n, b))]
    assert achados == [], "vídeo, áudio, foto, arquivo de trabalho do robô ou transcrição no histórico do push: " + "; ".join(achados)


def test_arquivo_enviado_e_apagado_no_mesmo_push_e_achado(tmp_path):
    """O conferir dos commits do push (num repositório de mentira): o vídeo enviado num commit e apagado no seguinte, e o estado do robô
    com as palavras transcritas, são achados; o código e as imagens do pacote, não."""
    if shutil.which("git") is None:
        pytest.skip("git não instalado")
    rodar = lambda *a: subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Teste", "-c", "user.email=teste@exemplo.invalid", *a],
                                      capture_output=True, check=True)
    rodar("init", "-q")
    (tmp_path / "LEIA.md").write_text("# teste\n")
    rodar("add", ".")
    rodar("commit", "-q", "-m", "base")
    antes = rodar("rev-parse", "HEAD").stdout.decode().strip()
    (tmp_path / "radar-logo-artecon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "IMG_0001.txt").write_bytes((20).to_bytes(4, "big") + b"ftypqt  " + b"\0" * 8)     # o .mov com outro nome
    (tmp_path / "trabalho").mkdir()
    q = '"'
    (tmp_path / "trabalho" / "notas.json").write_text("{" + q + "palavras" + q + ": [{" + q + "texto" + q + ": " + q + "prazo" + q + ", " + q + "ini" + q + ": 1.2}]}")
    (tmp_path / "codigo.py").write_text("x = 1\n")
    rodar("add", ".")
    rodar("commit", "-q", "-m", "envio")
    rodar("rm", "-q", "IMG_0001.txt", "trabalho/notas.json")
    rodar("commit", "-q", "-m", "apaga")
    achados = {n: problemas_do_arquivo(n, b) for _, n, b in arquivos_dos_commits(antes, raiz=tmp_path)}
    assert achados == {"radar-logo-artecon.png": [], "IMG_0001.txt": ["midia (MP4/MOV/HEIC (ISO))"], "trabalho/notas.json": ["transcricao"],
                       "codigo.py": []}


def test_primeiro_push_de_um_ramo_confere_os_commits_que_so_ele_tem(tmp_path):
    """Varredura geral (v0.22.0): no primeiro push de um ramo novo o GitHub manda o "antes" só com zeros. O vídeo enviado num commit e
    apagado no seguinte desse push é achado (os commits que nenhum outro ramo do GitHub tem); os do main e de outro ramo, não."""
    if shutil.which("git") is None:
        pytest.skip("git não instalado")
    rodar = lambda *a: subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Teste", "-c", "user.email=teste@exemplo.invalid", *a],
                                      capture_output=True, check=True).stdout.decode().strip()
    rodar("init", "-q")
    (tmp_path / "LEIA.md").write_text("# teste\n")
    rodar("add", ".")
    rodar("commit", "-q", "-m", "base")
    rodar("update-ref", "refs/remotes/origin/main", "HEAD")                    # o main do GitHub
    (tmp_path / "outro.MOV").write_bytes((20).to_bytes(4, "big") + b"ftypqt  " + b"\0" * 8)
    rodar("add", ".")
    rodar("commit", "-q", "-m", "outro ramo, já conferido no push dele")
    rodar("update-ref", "refs/remotes/origin/claude/outro", "HEAD")
    rodar("rm", "-q", "outro.MOV")
    rodar("commit", "-q", "-m", "tira")
    (tmp_path / "IMG_0001.txt").write_bytes((20).to_bytes(4, "big") + b"ftypqt  " + b"\0" * 8)
    rodar("add", ".")
    rodar("commit", "-q", "-m", "envio")
    rodar("rm", "-q", "IMG_0001.txt")
    rodar("commit", "-q", "-m", "apaga")
    rodar("update-ref", "refs/remotes/origin/claude/novo", "HEAD")            # o próprio ramo, como o checkout o traz
    zeros = "0" * 40
    achados = lambda faixa: {n for _, n, b in arquivos_dos_commits(zeros, raiz=tmp_path, faixa=faixa) if problemas_do_arquivo(n, b)}
    assert achados(faixa_do_push(zeros, "claude/novo", raiz=tmp_path)) == {"IMG_0001.txt"}
    assert achados(faixa_do_push(zeros, "", raiz=tmp_path)) == {"IMG_0001.txt", "outro.MOV"}      # sem o ramo: tudo o que não está no main
    antes = rodar("rev-parse", "HEAD~1")
    assert faixa_do_push(antes, "claude/novo") == [f"{antes}..HEAD"]


def test_workflow_do_repositorio_confere_os_commits_do_push():
    yml = (RAIZ / ".github" / "workflows" / "radar-repositorio.yml").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in yml.splitlines() if not l.lstrip().startswith("#"))
    assert re.search(r"(?m)^\s+fetch-depth:\s*0\s*$", codigo), codigo
    assert re.search(r"(?m)^\s+RADAR_PUSH_ANTES:\s*\$\{\{\s*github\.event\.before\s*\}\}\s*$", codigo), codigo
    assert re.search(r"(?m)^\s+RADAR_PUSH_RAMO:\s*\$\{\{\s*github\.ref_name\s*\}\}\s*$", codigo), codigo    # v0.22.0


def test_video_audio_foto_e_transcricao_sao_achados_com_qualquer_nome():
    """Os detectores pegam o vídeo do celular com outro nome (o .mp4 renomeado para .txt), o áudio, a foto e as transcrições; e não
    pegam o código, o texto em UTF-16 nem o LEIAME que só cita os nomes. Os exemplos são montados aqui (escritos neste arquivo, ele seria
    achado)."""
    caixa = lambda nome, corpo=b"": (len(corpo) + 8).to_bytes(4, "big") + nome + corpo
    for b, tipo in [(caixa(b"ftyp", b"qt  "), "MP4/MOV/HEIC (ISO)"), (caixa(b"ftyp", b"heic"), "MP4/MOV/HEIC (ISO)"),
                    (caixa(b"wide") + caixa(b"mdat"), "MP4/MOV/HEIC (ISO)"), (b"RIFF\x24\x00\x00\x00WAVEfmt ", "RIFF WAVE"),
                    (b"\x1aE\xdf\xa3\x9fB\x86\x81", "Matroska/WebM"), (b"ID3\x04\x00", "MP3"), (b"OggS\x00\x02", "Ogg/Opus"),
                    (b"\xff\xd8\xff\xe1\x00\x10Exif", "JPEG"), (b"\xff\xf1\x50\x80", "AAC (ADTS)"), (b"\x89PNG\r\n\x1a\n", "PNG")]:
        assert midia_pelo_conteudo(b) == tipo, b
    for b in [b"\xff\xfeo\x00l\x00\xe1\x00", "const x = 1;\n".encode(), b"# Radar\n", b"\x00\x01\x00\x00\x00\x10"]:     # UTF-16, código, texto, fonte
        assert midia_pelo_conteudo(b) == "", b
    q = '"'
    for texto in ["{" + q + "RecognitionStatus" + q + ": " + q + "Success" + q + ", " + q + "NBest" + q + ": []}",
                  # o estado do robô (as palavras do alinhamento), o resultado (o relatório) e o pedido (a fala e a cartela)
                  "[{" + q + "texto" + q + ": " + q + "prazo" + q + ", " + q + "ini" + q + ": 1.25, " + q + "fim" + q + ": 1.6}]",
                  "{" + q + "texto_final" + q + ": " + q + "O prazo vence hoje." + q + "}", "{" + q + "fala_roteiro" + q + ": " + q + "O prazo vence" + q + "}",
                  "{" + q + "cartela_linhas" + q + ": [" + q + "Bruno Exemplo, contador" + q + "]}",
                  '{"phrases": [{' + q + "offset" + "Milliseconds" + q + ': 40, "text": "x"}]}',
                  "[{" + q + "texto" + q + ": " + q + "prazo" + q + ", " + q + "inicio" + q + ": 1.25, " + q + "fim" + q + ": 1.6}]",
                  "[Events]\n" + "Dialogue" + ": 0,0:00:01.20,0:00:03.10,Fala,,0,0,0,,o prazo vence\n",
                  "1\n00:00:01,200 " + "-->" + " 00:00:03,100\no prazo vence\n", "WEBVTT\n\n00:01.200 --> 00:03.100\nx\n00:00:01.200 " + "-->" + " 00:00:03.100\n"]:
        assert TRANSCRICAO.search(texto), texto
    for texto in ["o robô grava palavras.json e transcricao_erro.txt (LEIAME)", "texto = 'inicio'", '{"texto_final_s": 3}',
                  "Dialogue: o diálogo da peça", "00:00:01 a 00:00:03"]:
        assert not TRANSCRICAO.search(texto), texto
    # os arquivos de trabalho do robô, pelo nome (com qualquer conteúdo), em qualquer pasta
    for n in ("trabalho/pedido.json", "estado.json", "x/resultado.json", "erro.json", "trabalho/.estado.json", "fala/palavras_envio.json",
              "palavras.json", "pedido_fala.json", "transcricao_erro.txt", "sai/luz1.txt", "sai/luz12.txt"):
        assert problemas_do_arquivo(n, b"{}") == ["trabalho"], n
    assert problemas_do_arquivo("docs/estado-da-arte.json", b"{}") == [] and problemas_do_arquivo("luzes.txt", b"") == []
    assert TRANSCRICAO_PODE.fullmatch("testes/radar_video_fala_falsa.py") and TRANSCRICAO_PODE.fullmatch("robo/video/transcrever.py")
    assert not TRANSCRICAO_PODE.fullmatch("testes/amostras/fala.json") and not TRANSCRICAO_PODE.fullmatch("robo/video/fala.json")


def test_gitignore_barra_video_audio_foto_e_trabalho_do_robo():
    for nome in ("IMG_0001.MOV", "reel.mp4", "clipe 2.mov", "testes/amostras/gravacao.mp4", "fala16k.wav", "fala48k.wav", "audio.m4a",
                 "VID-20261013.3gp", "voz.mp3", "voz.ogg", "voz.opus", "IMG_0002.HEIC", "q1.jpg", "foto.JPG", "foto.jpeg", "legenda.ass",
                 "legenda.srt", "legenda.vtt", "trabalho/palavras.json", "palavras.json", "pedido_fala.json", "fala/transcricao_erro.txt",
                 # a captura de tela (PNG no iPhone e no Android), a foto do WhatsApp (WEBP) e as outras extensões de imagem e áudio
                 "IMG_1234.PNG", "captura-da-previa.png", "foto-whatsapp.webp", "captura.webp", "anima.gif", "scan.tif", "scan.TIFF", "foto.bmp",
                 "RAW_0001.DNG", "voz.wma", "voz.aiff", "voz.caf", "legenda.ssa", "video.wmv", "video.flv", "docs/radar-logo-artecon.png",
                 # os arquivos de trabalho do robô (pegar, alinhar, montar dentro do clone): o pedido, o estado, o resultado, o erro e os temporários
                 "trabalho/pedido.json", "trabalho/estado.json", "trabalho/resultado.json", "trabalho/erro.json", "trabalho/.estado.json",
                 "trabalho/fala/palavras_envio.json", "trabalho/sai/cartela.png", "trabalho/sai/luz1.txt",
                 # varredura geral (v0.22.0): os clipes brutos do "pegar" (<pasta>/ent/<n>, sem extensão), na raiz do clone ou em subpasta
                 "trabalho/ent/1", "trabalho/ent/12", "corretor/ent/1", "ent/3", "robo/video/tmp/ent/2"):
        assert git("check-ignore", "-q", "--no-index", nome).returncode == 0, nome
    for nome in ("robo/video/transcrever.py", "robo/video/fontes/DMSans-Bold.ttf", "robo/video/requirements.txt", "radar-logo-artecon.png",
                 "radar-timbrado-topo.png", "radar-timbrado-rodape.png", "testes/radar_video_sintetico.py",
                 "testes/amostras/links-reais-2026-10-02.json", "supabase/functions/radar-video/index.ts"):
        assert git("check-ignore", "-q", "--no-index", nome).returncode == 1, nome


def test_workflow_dos_testes_roda_os_testes_do_video():
    """O radar-testes roda a suíte inteira, com os testes do corretor de vídeo: o ffmpeg do apt, o Python do robô com hash (o Speech SDK
    de verdade, contra o servidor local), o Ubuntu do robô (24.04: o ffmpeg 6.1.1 do Dockerfile e o SDK, que só lista até a 24.04) e o
    tempo que cabe (a suíte inteira leva uns 14 minutos aqui, mais a instalação)."""
    yml = (RAIZ / ".github" / "workflows" / "radar-testes.yml").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in yml.splitlines() if not l.lstrip().startswith("#"))
    assert re.search(r"(?m)^\s+runs-on:\s*ubuntu-24\.04\s*$", codigo), codigo
    assert 35 <= int(re.search(r"(?m)^\s+timeout-minutes:\s*(\d+)", codigo).group(1)) <= 60
    assert re.search(r"(?m)apt-get install -y [^\n]*\bffmpeg\b", codigo)
    assert "pip install --require-hashes --no-deps -r robo/video/requirements.txt" in codigo
    assert re.search(r"(?m)^\s+- run: python -m pytest testes -q\s*$", codigo)                       # a pasta inteira: os do vídeo juntos
    assert sorted(p.name for p in (RAIZ / "testes").glob("test_radar_video_*.py")) == [
        "test_radar_video_alinhar.py", "test_radar_video_banco.py", "test_radar_video_corrigir.py", "test_radar_video_robo.py",
        "test_radar_video_transcrever.py"]


def test_versao_igual_em_todos_os_arquivos_da_versao():
    """Uma versão só: a tela (VERSAO e a 1ª entrada de VERSOES), os dois scripts e o ?v= deles, o LEIAME e o relatório. v0.23.0: o que
    não mudou fica na versão em que mudou por último, nunca à frente da tela — o SQL (um setup e uma reversão, os dos testes, da mesma
    versão), a função radar-video e o robô do vídeo (os dois da mesma versão) e as outras funções. v0.26.0: a radar-ia também (a função
    que mudou fica na versão em que mudou por último, nunca à frente da tela; na v0.26.0, só a tela muda). As que a tela exige (radar-ia e
    radar-redes) atendem à versão mínima que ela pede (FUNCAO_MINIMA e REDES_MINIMA)."""
    ler = lambda c: (RAIZ / c).read_text(encoding="utf-8")
    achar = lambda padrao, texto: re.search(padrao, texto).group(1)
    html = ler("index.html")
    v = achar(r'(?m)^const VERSAO = "(\d+\.\d+\.\d+)";', html)
    num = lambda x: tuple(int(p) for p in x.split("."))
    assert achar(r'const VERSOES = \[\s*\["([^"]+)"', html) == v
    assert len(re.findall(r'<script src="radar-(?:pauta|video|setor|respostas)\.js\?v=([^"]+)"', html)) == 4      # v0.35.0: + a aba Respostas (v0.34.0: + a aba Setor)
    assert set(re.findall(r'<script src="radar-(?:pauta|video|setor|respostas)\.js\?v=([^"]+)"', html)) == {v}
    assert achar(r'(?m)^const PAUTA_VERSAO = "([^"]+)"', ler("radar-pauta.js")) == v
    assert achar(r'(?m)^const VIDEO_VERSAO = "([^"]+)"', ler("radar-video.js")) == v
    assert achar(r'(?m)^const SETOR_VERSAO = "([^"]+)"', ler("radar-setor.js")) == v
    assert achar(r'(?m)^const RESPOSTAS_VERSAO = "([^"]+)"', ler("radar-respostas.js")) == v
    assert num(achar(r'(?m)^const VERSAO = "([^"]+)"', ler("supabase/functions/radar-ia/index.ts"))) <= num(v)
    assert ler("LEIAME-radar.md").startswith(f"# Radar Artecon — v{v}\n")
    assert ler("RELATORIO-TESTES-radar.md").startswith(f"# Radar Artecon — Relatório de testes (v{v})\n")
    # o banco: um setup e uma reversão, da mesma versão (a da última mudança no banco), e o setup registra essa versão
    banco = achar(r"^radar-setup-v(\d+\.\d+\.\d+)\.sql$", SETUP.name)
    assert sorted(p.name for p in (RAIZ / "sql").glob("radar-setup-v*.sql")) == [f"radar-setup-v{banco}.sql"] == [SETUP.name]
    assert sorted(p.name for p in (RAIZ / "sql").glob("radar-reversao-v*.sql")) == [f"radar-reversao-v{banco}.sql"] == [REVERSAO.name]
    assert f"('v{banco}', v_antes)" in SETUP.read_text(encoding="utf-8") and num(banco) <= num(v)
    # a tela avisa "precisa do banco da vX: rode o sql/radar-setup-vX.sql" com o banco desta versão
    for script in ("radar-pauta.js", "radar-video.js", "radar-setor.js", "radar-respostas.js"):
        assert set(re.findall(r"sql/radar-setup-v(\d+\.\d+\.\d+)\.sql", ler(script))) == {banco}, script
    # v0.29.0 (revisão): o index.html também (o recado da Conferência das Diretrizes ainda citava o setup da v0.28.0, que não existe
    # mais); fora a aba Versões, que conta a história com o setup de cada versão
    inicio = html.index("const VERSOES = [")
    sem_versoes = html[:inicio] + html[html.index("\n];", inicio):]
    assert set(re.findall(r"sql/radar-setup-v(\d+\.\d+\.\d+)\.sql", sem_versoes)) == {banco}
    # o corretor de vídeo: a função e o robô (no repositório privado) da mesma versão
    video = achar(r'(?m)^const VERSAO = "([^"]+)"', ler("supabase/functions/radar-video/index.ts"))
    assert achar(r'(?m)^ROBO = "([^"]+)"', ler("robo/video/relatorio.py")) == video
    for funcao in sorted(p.parent.name for p in (RAIZ / "supabase" / "functions").glob("*/index.ts")):
        assert num(achar(r'(?m)^const VERSAO = "([^"]+)"', ler(f"supabase/functions/{funcao}/index.ts"))) <= num(v), funcao
    for constante, funcao in (("FUNCAO_MINIMA", "radar-ia"), ("REDES_MINIMA", "radar-redes")):
        minima = achar(rf'(?m)^const {constante} = "([^"]+)"', html)
        assert num(achar(r'(?m)^const VERSAO = "([^"]+)"', ler(f"supabase/functions/{funcao}/index.ts"))) >= num(minima), funcao


def test_tela_sem_a_numeracao_antiga_dos_passos():
    """v0.26.0: o assunto tem 3 passos (1. Preparar, 2. Conferir e aprovar, 3. Publicar). Fora da aba Versões (que conta a história), a
    tela não fala mais dos passos de antes (os 4 da v0.10.0 e os 7 da v0.12.2): nenhum recado, título ou ajuda manda para um passo que
    não existe mais."""
    html = (RAIZ / "index.html").read_text(encoding="utf-8")
    ini = html.index("const VERSOES = [")
    sem_versoes = html[:ini] + html[html.index("\n];", ini) + 3:]
    for antigo in ("passo 4", "passo 5", "passos 6 e 7", "cinco passos", "quatro passos", "2. Escrever", "4. Publicar no site",
                   "aprovado no passo 3", "passos7"):
        assert antigo not in sem_versoes, antigo


def test_leiame_da_v0220_ordem_da_instalacao_termo_teste_parar_e_desfazer():
    """O passo a passo da instalação e os cuidados do corretor dizem o que o código faz: o termo novo antes de tudo (do SQL em diante,
    nenhum reel fica pronto sem ele), o SQL antes da tela (a tela nova com o banco antigo não abre peça nenhuma da Pauta), o teste numa
    peça de teste e não numa real, o limite de 50 MB do Free também no vídeo corrigido, como parar o corretor (tirar o token não para:
    a agenda do workflow pega a fila sem ele, e a reserva vira "robo_nao_pegou") e o que fica fora do banco na reversão."""
    leiame = (RAIZ / "LEIAME-radar.md").read_text(encoding="utf-8")
    inst = leiame[leiame.index("**Da v0.21.0 para a v0.22.0**"):leiame.index("**Da v0.20.0 para a v0.21.0**")]
    antes = inst[inst.index("0. Antes:"):inst.index("\n1. ")]
    assert "**O termo novo**" in antes and "antes da instalação" in antes and "RADAR304" in antes
    assert "nenhum reel do calendário fica pronto nem é aprovado" in inst[:inst.index("0. Antes:")]
    assert re.search(r"(?m)^1\. SQL Editor → execute `sql/radar-setup-v0\.22\.0\.sql`", inst)
    assert re.search(r"(?m)^2\. A tela nova chega pelo repositório", inst)
    assert "o resto funciona como antes" not in inst                      # a tela nova com o banco antigo não abre peça da Pauta
    teste = inst[inst.index("11. **Primeiro reel acompanhado:**"):]
    assert "Nunca numa peça real" in teste and "Importar o calendário (CSV)" in teste and "Cancelar a peça" in teste
    assert "e o vídeo corrigido" in antes and "50 MB" in antes
    cuidados = inst[inst.index("Cuidados nesta versão:"):]
    assert "Disable workflow" in cuidados and "robo_nao_pegou" in cuidados and "o vídeo fica na fila" not in leiame
    assert "Tirar só o `RADAR_VIDEO_GITHUB_TOKEN` **não** para" in cuidados
    for coisa in ("RADAR_VIDEO_ROBO_CHAVE", "AZURE_FALA_CHAVE", "função `radar-video`", "revogue o token fino"):
        assert coisa in cuidados, coisa
    assert "o próprio workflow olha a fila 2 vezes por dia útil, se o token do GitHub vencer" not in leiame
    assert "os clipes e também o vídeo\ncorrigido" in leiame                       # os limites desta versão
    assert "No reel, desmarcar não tira a pessoa do\n   vídeo" in leiame          # a revogação
    # a reversão do banco e o modelo do workflow dizem o mesmo
    rev = REVERSAO.read_text(encoding="utf-8")
    assert "Disable workflow" in rev and "RADAR_VIDEO_GITHUB_TOKEN" in rev and "token fino" in rev and "AZURE_FALA_CHAVE" in rev
    wf = (RAIZ / "robo" / "video" / "workflow" / "radar-video.yml").read_text(encoding="utf-8")
    assert "se o token do GitHub no Supabase vencer, esta agenda de reserva" not in wf and "tirar o token não para" in wf


def test_workflows_publicos_com_acoes_fixas_e_robo_com_hash():
    """Varredura geral (v0.22.0): os jobs do repositório público que recebem a chave interna do banco e a senha do painel do site
    (coleta, resumo, publicar, teste do site, diagnóstico) usavam ações por etiqueta móvel (@v5, @v6) e instalavam o robo/requirements.txt
    sem versão exata nem hash. Agora, como no workflow do corretor de vídeo: cada ação fixada pelo commit (40 caracteres, a versão no
    comentário) e o requirements com versão exata e hash de cada pacote (também das dependências), instalado com --require-hashes."""
    for yml in sorted((RAIZ / ".github" / "workflows").glob("*.yml")):
        codigo = "\n".join(l for l in yml.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
        for acao in re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", codigo):
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", acao), f"{yml.name}: {acao}"
        for pip in re.findall(r"(?m)pip install[^\n]*", codigo):
            if "robo/requirements.txt" in pip:
                assert "--require-hashes" in pip and "--no-deps" in pip and pip.rstrip().endswith("-r robo/requirements.txt"), f"{yml.name}: {pip}"
    req = (RAIZ / "robo" / "requirements.txt").read_text(encoding="utf-8")
    pacotes = re.findall(r"(?m)^([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\$", req)
    assert {p.lower() for p, _ in pacotes} == {"requests", "charset-normalizer", "idna", "urllib3", "certifi", "beautifulsoup4", "soupsieve",
                                               "typing-extensions", "lxml"}
    blocos = re.split(r"(?m)^(?=[A-Za-z])", "\n".join(l for l in req.splitlines() if not l.startswith("#")))
    assert all(re.search(r"--hash=sha256:[0-9a-f]{64}", b) for b in blocos if b.strip()), "pacote sem hash"
    # e o LEIAME não promete mais que a chave do robô "não lê as fotos, as lâminas": ela é service_role e lê os buckets privados
    leiame = " ".join((RAIZ / "LEIAME-radar.md").read_text(encoding="utf-8").split())
    assert "**os arquivos do armazenamento ela lê**" in leiame and "não lê as pessoas, as peças, as fotos, as lâminas" not in leiame


# ------------------------------------------------------------------- v0.29.0: lembretes por e-mail antes do dia
def test_workflow_dos_lembretes_so_issues_e_tres_segredos():
    """O robô dos lembretes roda no repositório público: só abre ou comenta aviso (issues: write, no job; o resto do workflow só lê), usa
    só os segredos da coleta (a URL e a chave do banco) e o GITHUB_TOKEN — nunca a senha do site nem o INLABS —, não mostra comando no
    registro (set -x), roda na hora (workflow_dispatch, pela agenda do banco) e de hora em hora (a reserva, em minuto quebrado), uma
    rodada de cada vez, e pergunta ao banco antes de instalar qualquer coisa."""
    yml = (RAIZ / ".github" / "workflows" / "radar-lembretes.yml").read_text(encoding="utf-8")
    codigo = "\n".join(re.sub(r"\s+#\s.*$", "", l) for l in yml.splitlines() if not l.lstrip().startswith("#"))   # sem os comentários
    assert re.search(r"(?m)^on:\s*\n\s+schedule:\s*\n\s+- cron: \"29 \* \* \* \*\"\s*\n\s+workflow_dispatch:\s*$", codigo), codigo
    assert re.search(r"(?m)^permissions:\s*\n\s+contents: read\s*$", codigo)                       # o padrão do workflow: só ler
    assert len(re.findall(r"(?m)^\s+issues: write\s*$", codigo)) == 1 and "write" not in codigo.replace("issues: write", "")
    assert re.search(r"(?m)^jobs:\s*\n\s+lembrar:\s*\n\s+runs-on: ubuntu-latest\s*\n\s+permissions:\s*\n\s+contents: read\s*\n\s+issues: write", codigo)
    assert re.search(r"(?m)^concurrency:\s*\n\s+group: radar-lembretes\s*\n\s+cancel-in-progress: false\s*$", codigo)
    assert set(re.findall(r"secrets\.(\w+)", codigo)) == {"RADAR_SUPABASE_URL", "RADAR_SUPABASE_SERVICE_KEY", "GITHUB_TOKEN"}
    for proibido in ("ARTECON_SITE", "INLABS", "RADAR_IA_GATEWAY_TOKEN", "set -x", "curl -v", "--verbose", "pull_request"):
        assert proibido not in codigo, proibido
    assert "rpc/radar_lembretes_ha_envio" in codigo and "python radar_lembretes.py" in codigo
    assert codigo.count("if: steps.fila.outputs.ha == 'sim'") == 4                                 # nada instala sem lembrete
    assert re.search(r"sb_secret_\*\) ;;", codigo)                                                  # a chave nova só no apikey
    assert 5 <= int(re.search(r"(?m)^\s+timeout-minutes:\s*(\d+)", codigo).group(1)) <= 10


def test_robos_agendados_da_radar_redes_sao_os_workflows_com_schedule():
    """A radar-redes religa uma vez por dia os workflows agendados que o GitHub desliga no repositório público (manter_robos): a lista
    dela é a dos workflows com "schedule:" (v0.29.0: + o dos lembretes). Workflow agendado fora da lista pararia sem aviso em 60 dias."""
    ts = (RAIZ / "supabase" / "functions" / "radar-redes" / "index.ts").read_text(encoding="utf-8")
    lista = set(re.findall(r'"([\w.-]+\.yml)"', re.search(r"const ROBOS_AGENDADOS = \[([^\]]*)\]", ts).group(1)))
    agendados = {y.name for y in (RAIZ / ".github" / "workflows").glob("*.yml")
                 if re.search(r"(?m)^\s+schedule:\s*$", "\n".join(l for l in y.read_text(encoding="utf-8").splitlines()
                                                                if not l.lstrip().startswith("#")))}
    assert lista == agendados == {"radar-coletar.yml", "radar-site-publicar.yml", "radar-resumo.yml", "radar-lembretes.yml"}
    assert 'const WORKFLOW_LEMBRETES = "radar-lembretes.yml";' in ts                                # fixo: nunca vem do pedido
    assert "pedido?.workflow" not in ts and "pedido.workflow" not in ts


def test_leiame_da_v0290_ordem_desligar_e_desfazer():
    """O passo a passo da v0.29.0 diz o que o código faz: o banco antes da tela (a tela nova com o banco antigo mostra o recado do SQL),
    a função radar-redes antes da agenda (a agenda nova com a função antiga seria recusada: "A agenda só publica"), nenhum segredo novo,
    como desligar sem SQL ("ligado": false), como parar de vez (o workflow e o agendamento) e como desfazer (o SQL que apaga tudo dos
    lembretes tem as mesmas funções do setup)."""
    leiame = (RAIZ / "LEIAME-radar.md").read_text(encoding="utf-8")
    assert leiame.index("**Da v0.28.1 para a v0.29.0**") < leiame.index("**Da v0.28.0 para a v0.28.1**")
    inst = leiame[leiame.index("**Da v0.28.1 para a v0.29.0**"):leiame.index("**Da v0.28.0 para a v0.28.1**")]
    passos = [inst.index(f"\n{n}. ") for n in (1, 2, 3, 4)]
    p1, p2, p3, p4 = (inst[a:b] for a, b in zip(passos, passos[1:] + [inst.index("**O que configurar:**")]))
    assert "`sql/radar-setup-v0.29.0.sql`" in p1 and "antes de publicar a tela" in p1 and "28" in p1 and "v0.29.0" in p1
    assert "`index.html`" in p2 and "`robo/radar_lembretes.py`" in p2 and "`.github/workflows/radar-lembretes.yml`" in p2 and "Ctrl+F5" in p2
    assert "`radar-redes`" in p3 and "Deploy" in p3 and "`RADAR_GITHUB_TOKEN`" in p3 and "já serve" in p3
    assert "`sql/radar-redes-agenda.sql`" in p4 and "radar-redes-agenda-lembretes" in p4 and '"versao":"0.29.0"' in p4
    assert "nenhum segredo novo" in inst.lower() and "sem publicar nada" in inst
    desligar = inst[inst.index("**Como desligar:**"):inst.index("**Para desfazer**")]
    assert '"ligado": false' in desligar and "Disable workflow" in desligar and "cron.unschedule('radar-redes-agenda-lembretes')" in desligar
    desfazer = inst[inst.index("**Para desfazer**"):]
    assert "441bcfe" in desfazer and "Disable workflow" in desfazer and "Radar: lembrete" in desfazer
    setup = {n for n in re.findall(r"create or replace function public\.(radar_lembretes_\w+)\(", SETUP.read_text(encoding="utf-8"))}
    assert len(setup) == 11 and set(re.findall(r"public\.(radar_lembretes_\w+)\(", desfazer)) == setup
    assert "drop table if exists public.radar_lembretes;" in desfazer and "delete from public.radar_config where chave = 'lembretes';" in desfazer
    reversao = REVERSAO.read_text(encoding="utf-8")
    assert set(re.findall(r"drop function if exists public\.(radar_lembretes_\w+)\(", reversao)) == setup
    # o topo do LEIAME conta a versão e o que muda
    topo = leiame[:leiame.index("A v0.28.1 corrige")]
    for trecho in ("**lembretes por e-mail antes do dia**", "um e-mail por dia", "uma vez só", "nunca", "0.22.0 → **0.29.0**",
                   "`robo/radar_lembretes.py`", "**Nenhum segredo novo.**", "Da v0.28.1 para a v0.29.0"):
        assert trecho in topo, trecho


def test_leiame_da_v0310_confere_com_o_cadastro_e_respeita_o_pedido_do_dom_sc():
    """v0.31.0 (revisão): o LEIAME diz o que o cadastro faz. (1) As unidades da Receita que ficam de fora por padrão são as do
    excluir_orgao da rfb-normas (a v0.31.0 tirou o DISIT: as Soluções de Consulta das Disit entram). (2) Quem ainda não foi decidido
    pelo dono não está "desligado por decisão do dono". (3) O robots.txt do DOM/SC pede que robôs não entrem: o LEIAME não manda rodar
    o diagnóstico (que também é um robô) com uma fonte do DOM/SC antes da autorização do site."""
    import json
    leiame = (RAIZ / "LEIAME-radar.md").read_text(encoding="utf-8")
    rfb = next(f for f in json.loads((RAIZ / "robo" / "radar_fontes.json").read_text(encoding="utf-8")) if f["slug"] == "rfb-normas")
    unidades = {u.lower() for u in re.fullmatch(r"\^\(([^)]*)\)", rfb["config"]["excluir_orgao"]).group(1).split("|")}
    citadas = re.search(r"Unidades regionais\s+da Receita \(([^)]*)\)", leiame).group(1)
    assert [u for u in re.split(r",\s*", citadas.replace("…", "")) if u.lower() not in unidades] == []
    assert "disit" not in unidades and re.search(r"desde a v0\.31\.0, as Disit entram", leiame)
    topo = leiame[:leiame.index("A v0.30.0 traz")]
    assert "por decisão do dono" not in topo and "**desligadas até o dono decidir**" in topo and "por escolha desta versão" in topo
    # nenhuma fonte do DOM/SC como exemplo do diagnóstico; o item (d) diz para não rodar nem o diagnóstico sem a autorização
    assert re.findall(r"`(domsc-[a-z]+-[a-z]+)`", leiame) == []
    inst = leiame[leiame.index("**Da v0.30.0 para a v0.31.0**"):leiame.index("**Da v0.29.0 para a v0.30.0**")]
    d = inst[inst.index("- (d) **DOM/SC"):inst.index("**Como desligar uma fonte:**")]
    assert "não rode nem o diagnóstico" in d and "autorização por escrito" in d
    # o item (c): os três casos pelo veredito do diagnóstico, e não só pelo número HTTP
    c = inst[inst.index("- (c) **Atos da Receita"):inst.index("- (d) **DOM/SC")]
    assert c.index('**"OK"**') < c.index('**"REVISAR — lista ok, texto do 1º item recusado"**') < c.index('**"FALHA"** com HTTP 403')


def test_amostras_do_diario_oficial_sem_os_nomes_de_quem_assinou():
    """v0.31.0 (revisão): o LEIA-ME das amostras diz que os nomes de quem assinou os atos foram trocados por um aviso. Nenhum XML do DOU
    das amostras (repositório público) traz o parágrafo de assinatura, como o do Convênio ICMS 115 (o presidente do CONFAZ e o secretário
    de Fazenda de cada estado)."""
    import html
    ufs = ("Acre|Alagoas|Amapá|Amazonas|Bahia|Ceará|Distrito Federal|Espírito Santo|Goiás|Maranhão|Mato Grosso(?: do Sul)?|Minas Gerais|"
           "Pará|Paraíba|Paraná|Pernambuco|Piauí|Rio de Janeiro|Rio Grande do Norte|Rio Grande do Sul|Rondônia|Roraima|Santa Catarina|"
           "São Paulo|Sergipe|Tocantins")
    arquivos = sorted((RAIZ / "testes" / "amostras").glob("dou-*.xml"))
    assert len(arquivos) == 6
    for arq in arquivos:
        texto = html.unescape(arq.read_text(encoding="utf-8"))
        assert "Presidente do CONFAZ -" not in texto, arq.name
        for p in re.findall(r"<p[^>]*>(.*?)</p>", texto, re.S):
            assert len(re.findall(rf"\b(?:{ufs}) - [A-ZÁÉÍÓÚÂÊÔ]", p)) < 3, (arq.name, p[:80])
    assert "[nomes dos signatários retirados da amostra]" in (RAIZ / "testes" / "amostras" / "dou-confaz-entra-despacho-48-convenios.xml").read_text(encoding="utf-8")
    assert "os nomes de quem assinou os atos foram trocados por um aviso" in (RAIZ / "testes" / "amostras" / "LEIA-ME.txt").read_text(encoding="utf-8")
