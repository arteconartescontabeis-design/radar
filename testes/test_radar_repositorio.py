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
temporária. Nenhum arquivo de vídeo, áudio ou foto (pela extensão ou pelo começo do arquivo, com qualquer nome), nenhum arquivo de
trabalho do robô (palavras.json, pedido_fala.json, transcricao_erro.txt) e nenhuma transcrição (a resposta da Azure, as palavras com
tempo, a legenda ASS, SRT ou VTT) fora do código do robô (robo/video/) e dos geradores sintéticos dos testes do vídeo; as únicas
imagens são as do pacote (logotipo e timbrado). O .gitignore barra as extensões de vídeo, áudio e foto e os arquivos de trabalho. E a
versão do pacote é uma só em todos os arquivos que a levam (a tela, os dois scripts, a função nova, o robô do vídeo, o SQL, o LEIAME e
o relatório), e as funções do pacote atendem à versão mínima que a tela pede.
"""
from __future__ import annotations

import csv
import io
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
IMAGENS_DO_PACOTE = {"radar-logo-artecon.png", "radar-timbrado-topo.png", "radar-timbrado-rodape.png"}
TRABALHO_DO_ROBO = {"palavras.json", "pedido_fala.json", "transcricao_erro.txt"}
# a transcrição: a resposta da Azure (Speech SDK ou fast transcription), as palavras com tempo do robô (palavras.json), a legenda ASS
# e a SRT/VTT. Só no código do robô e nos geradores sintéticos dos testes do vídeo
TRANSCRICAO = re.compile(r'(?m)"(?:NBest|RecognitionStatus|combinedPhrases|offsetMilliseconds|durationMilliseconds|MaskedITN|Lexical|DisplayText)"\s*:'
                         r"""|["']texto["']\s*:\s*["'][^"'\n]*["']\s*,\s*["']inicio["']\s*:"""
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


# ------------------------------------------------------------- v0.22.0: só vídeo sintético, nada de gravação real nem de transcrição
def test_nenhum_video_audio_foto_nem_transcricao_no_repositorio():
    """O que um "git add ." levaria: nenhum vídeo, áudio ou foto (pela extensão ou pelo começo do arquivo, com qualquer nome; só as
    imagens do pacote), nenhum arquivo de trabalho do robô e nenhuma transcrição fora do código do robô e dos geradores sintéticos."""
    nomes = arquivos_do_repositorio()
    assert "robo/video/transcrever.py" in nomes and "radar-logo-artecon.png" in nomes                      # a lista é a de verdade
    midia, trabalho, transcricao = [], [], []
    for n in nomes:
        b = (RAIZ / n).read_bytes()
        base = n.rsplit("/", 1)[-1]
        tipo = midia_pelo_conteudo(b[:64])
        if n not in IMAGENS_DO_PACOTE and (("." + base.rsplit(".", 1)[-1].lower() in MIDIA and "." in base) or tipo):
            midia.append(f"{n} ({tipo or 'extensão'})")
        if base.lower() in TRABALHO_DO_ROBO:
            trabalho.append(n)
        if not TRANSCRICAO_PODE.fullmatch(n) and TRANSCRICAO.search(b[:20_000_000].decode("utf-8", "ignore")):
            transcricao.append(n)
    assert midia == [], "vídeo, áudio ou foto no repositório público (só vídeos sintéticos, gerados na hora dos testes): " + ", ".join(midia)
    assert trabalho == [], "arquivo de trabalho do robô do vídeo no repositório: " + ", ".join(trabalho)
    assert transcricao == [], "transcrição (ou legenda com tempo) fora do código do robô e dos testes sintéticos: " + ", ".join(transcricao)
    # as imagens do pacote continuam as de sempre (PNG), e as fontes da cartela não contam como mídia
    assert all(midia_pelo_conteudo((RAIZ / n).read_bytes()[:64]) == "PNG" for n in IMAGENS_DO_PACOTE)
    assert midia_pelo_conteudo((RAIZ / "robo/video/fontes/DMSans-Bold.ttf").read_bytes()[:64]) == ""


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
                  '{"phrases": [{' + q + "offset" + "Milliseconds" + q + ': 40, "text": "x"}]}',
                  "[{" + q + "texto" + q + ": " + q + "prazo" + q + ", " + q + "inicio" + q + ": 1.25, " + q + "fim" + q + ": 1.6}]",
                  "[Events]\n" + "Dialogue" + ": 0,0:00:01.20,0:00:03.10,Fala,,0,0,0,,o prazo vence\n",
                  "1\n00:00:01,200 " + "-->" + " 00:00:03,100\no prazo vence\n", "WEBVTT\n\n00:01.200 --> 00:03.100\nx\n00:00:01.200 " + "-->" + " 00:00:03.100\n"]:
        assert TRANSCRICAO.search(texto), texto
    for texto in ["o robô grava palavras.json e transcricao_erro.txt (LEIAME)", "texto = 'inicio'", '{"texto_final_s": 3}',
                  "Dialogue: o diálogo da peça", "00:00:01 a 00:00:03"]:
        assert not TRANSCRICAO.search(texto), texto
    assert TRANSCRICAO_PODE.fullmatch("testes/radar_video_fala_falsa.py") and TRANSCRICAO_PODE.fullmatch("robo/video/transcrever.py")
    assert not TRANSCRICAO_PODE.fullmatch("testes/amostras/fala.json") and not TRANSCRICAO_PODE.fullmatch("robo/video/fala.json")


def test_gitignore_barra_video_audio_foto_e_trabalho_do_robo():
    for nome in ("IMG_0001.MOV", "reel.mp4", "clipe 2.mov", "testes/amostras/gravacao.mp4", "fala16k.wav", "fala48k.wav", "audio.m4a",
                 "VID-20261013.3gp", "voz.mp3", "voz.ogg", "voz.opus", "IMG_0002.HEIC", "q1.jpg", "foto.JPG", "foto.jpeg", "legenda.ass",
                 "legenda.srt", "legenda.vtt", "trabalho/palavras.json", "palavras.json", "pedido_fala.json", "fala/transcricao_erro.txt"):
        assert git("check-ignore", "-q", "--no-index", nome).returncode == 0, nome
    for nome in ("robo/video/transcrever.py", "robo/video/fontes/DMSans-Bold.ttf", "robo/video/requirements.txt", "radar-logo-artecon.png",
                 "testes/radar_video_sintetico.py", "testes/amostras/links-reais-2026-10-02.json", "supabase/functions/radar-video/index.ts"):
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
    """Uma versão só: a tela (VERSAO e a 1ª entrada de VERSOES), os dois scripts e o ?v= deles, a função nova (radar-video), o robô do
    vídeo, o SQL (um setup e uma reversão, os dos testes), o LEIAME e o relatório. As funções que não mudaram (radar-ia e radar-redes)
    atendem à versão mínima que a tela pede (FUNCAO_MINIMA e REDES_MINIMA)."""
    ler = lambda c: (RAIZ / c).read_text(encoding="utf-8")
    achar = lambda padrao, texto: re.search(padrao, texto).group(1)
    html = ler("index.html")
    v = achar(r'(?m)^const VERSAO = "(\d+\.\d+\.\d+)";', html)
    num = lambda x: tuple(int(p) for p in x.split("."))
    assert achar(r'const VERSOES = \[\s*\["([^"]+)"', html) == v
    assert set(re.findall(r'<script src="radar-(?:pauta|video)\.js\?v=([^"]+)"', html)) == {v}
    assert achar(r'(?m)^const PAUTA_VERSAO = "([^"]+)"', ler("radar-pauta.js")) == v
    assert achar(r'(?m)^const VIDEO_VERSAO = "([^"]+)"', ler("radar-video.js")) == v
    assert achar(r'(?m)^const VERSAO = "([^"]+)"', ler("supabase/functions/radar-video/index.ts")) == v
    assert achar(r'(?m)^ROBO = "([^"]+)"', ler("robo/video/relatorio.py")) == v
    assert sorted(p.name for p in (RAIZ / "sql").glob("radar-setup-v*.sql")) == [f"radar-setup-v{v}.sql"] == [SETUP.name]
    assert sorted(p.name for p in (RAIZ / "sql").glob("radar-reversao-v*.sql")) == [f"radar-reversao-v{v}.sql"] == [REVERSAO.name]
    assert f"('v{v}', v_antes)" in SETUP.read_text(encoding="utf-8")
    assert ler("LEIAME-radar.md").startswith(f"# Radar Artecon — v{v}\n")
    assert ler("RELATORIO-TESTES-radar.md").startswith(f"# Radar Artecon — Relatório de testes (v{v})\n")
    for constante, funcao in (("FUNCAO_MINIMA", "radar-ia"), ("REDES_MINIMA", "radar-redes")):
        minima = achar(rf'(?m)^const {constante} = "([^"]+)"', html)
        assert num(achar(r'(?m)^const VERSAO = "([^"]+)"', ler(f"supabase/functions/{funcao}/index.ts"))) >= num(minima), funcao
