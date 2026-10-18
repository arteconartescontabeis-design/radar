"""Radar Artecon — corretor de vídeo (v0.22.0): a transcrição de fala16k.wav pela Azure, feita pelo robô (ajustes do dono, item 1).

transcrever(wav) devolve {palavras, frases, transcricao}:
  * palavras [{texto, inicio, fim, confianca}], em segundos na linha do tempo de fala16k.wav (= fala48k.wav = o zero do vídeo), na
    ordem; é o que alinhar.alinhar recebe;
  * frases [{display, inicio, fim}]: a forma de exibição de cada frase (pontuação e algarismos), para o falado fora do roteiro;
  * transcricao {servico, segundos_audio, palavras}: vai para o relatório (sem nomes). A cota do F0 é de 5 h por mês, dividida com
    a Agenda: cada vídeo registra quanto áudio mandou.
Dois modos, escolhidos só pelo ambiente do passo do workflow (segredos do repositório privado radar-video):
  * F0, o padrão (AZURE_FALA_MODO vazio ou "f0"): o recurso artecon-voz (AZURE_FALA_CHAVE, a CHAVE 2, e AZURE_FALA_REGIAO) pelo
    Speech SDK de Python (azure-cognitiveservices-speech): reconhecimento contínuo do WAV, pt-BR, saída detalhada com o tempo e a
    confiança de cada palavra — na forma LÉXICA (minúsculas, sem pontuação, números por extenso: numeros.py casa com o roteiro) —,
    palavrão sem máscara (ProfanityOption.Raw: "***" quebraria o alinhamento e iria para a legenda) e a lista de frases (o glossário
    e os nomes e siglas do roteiro). O F0 atende 1 pedido por vez no recurso inteiro, dividido com o WhatsApp da Agenda: a recusa por
    limite (TooManyRequests, o 429) ou por cota (Forbidden, "the free subscription … ran out of quota", ou o 403 na abertura) espera
    e tenta de novo, com espera crescente de 5 s a 60 s, até ESPERA_MAX (~10 min); depois, ErroVideo("transcricao_ocupada") — a
    tela diz "transcrição ocupada; tente de novo" — ou ErroVideo("azure_cota");
  * rápido (AZURE_FALA_MODO=rapido, com AZURE_FALA_ENDPOINT do recurso S0, ou a região): a fast transcription REST
    (api-version 2025-10-15) do desenho 2.3, síncrona, na forma de exibição (alinhar.py casa com ela também). Mesma interface: a
    troca pelo pago é só cadastrar os segredos.
A chave só existe no ambiente do passo: é lida aqui, na hora, nunca fica no módulo e nunca vai para log, mensagem de erro ou exceção
encadeada (todo erro vira ErroVideo com código fixo, levantado FORA do except: sem __cause__ nem __context__). A resposta da Azure
(a mensagem de erro, o detalhe do cancelamento, que traz o endereço) só é classificada, nunca impressa. O registro de áudio e o
arquivo de log do SDK nunca são ligados. O REST vai direto (sem o proxy do ambiente) e não segue redirecionamento: a chave nunca vai
para outro endereço.
Passo próprio do workflow (main): `python -I robo/video/transcrever.py <pasta do trabalho>`, só com AZURE_FALA_* no ambiente — a
chave da Azure e a do robô (RADAR_VIDEO_ROBO_CHAVE) não precisam estar no mesmo processo. Lê fala16k.wav e pedido_fala.json
({pedido, glossario, fala_roteiro, restante_s}, gravado pelo passo anterior) e grava palavras.json (para_json) ou, na falha,
transcricao_erro.txt com o código fixo (que o passo seguinte manda para radar_video_falhar).
"""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":                              # python -I não põe a pasta do script no sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import importlib
import json
import math
import os
import random
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import wave

import segredo
from segredo import ErroVideo

IDIOMA = "pt-BR"
API_RAPIDO = "2025-10-15"
TAXA = 16000                           # fala16k.wav: 16 kHz, 16 bits, mono (audio.extrair)
DURACAO_MAX = 970.0                    # s: sondar recusa a soma acima de 960 s (longo_demais; v0.33.0)
ESPERA_MAX = 600.0                     # s: ~10 min esperando a vaga (ou a cota) do F0 antes de desistir
ESPERA_INICIAL, ESPERA_TETO = 5.0, 60.0
FALHAS_MAX = 3                         # tentativas em falha de rede ou do serviço (depois, azure_fora)
TEMPO_BASE = 60.0                      # s: tempo-limite de cada tentativa no F0 = TEMPO_BASE + 3 × a duração do áudio
TEMPO_RAPIDO = 120.0                   # s: o POST da fast transcription
RESPOSTA_MAX = 5 * 1024 * 1024
LISTA_MAX, ITEM_MAX = 300, 50          # a lista de frases: até 300 itens de até 50 caracteres
PALAVRAS_MAX, FRASES_MAX = 3000, 500   # os mesmos de alinhar.py
JSON_MAX = 2 * 1024 * 1024             # palavras.json (modo montagem)
SERVICO = {"f0": "azure_f0", "rapido": "azure_rapido"}
_CODIGO = {"ocupada": "transcricao_ocupada", "cota": "azure_cota", "fora": "azure_fora", "chave": "azure_chave",
           "erro": "azure_erro"}
_CHAVE = re.compile(r"^[A-Za-z0-9]{20,128}$")          # 32 (as antigas) ou 84 caracteres; nada que quebre um cabeçalho
_REGIAO = re.compile(r"^[a-z0-9]{3,30}$")
_ENDPOINT = re.compile(r"^https://[a-z0-9][a-z0-9-]{0,62}\.(cognitiveservices\.azure\.com|api\.cognitive\.microsoft\.com)$")
_PONTAS = ".,;:!?…\"'“”‘’«»()[]"
_FIM_FRASE = re.compile(r"[.!?…:][\"'”’»)\]]*$")
_MARCACAO = re.compile(r"[{}\\<>|]")
_PALAVRA = re.compile(r"^[^\W\d_]+(?:[-'’][^\W\d_]+)*$")       # só letras ("PGDAS-D", "d'Ávila"): nada de "R$", "30/10", "{\\b1}"
# palavras comuns que abrem frase com maiúscula: nunca entram na lista como começo de um nome
_ABRE_FRASE = set("com para por sem uma uns umas nos nas dos das pelo pela pelos pelas este esta estes estas esse essa isso isto "
                  "aqui hoje agora quem você vocês nós ele ela eles elas seu sua seus suas meu minha nosso nossa até desde quando "
                  "como mas então também olá bom boa bons boas sou somos fala falo veja olha confira atenção".split())
_dormir, _relogio = time.sleep, time.monotonic          # os testes trocam por um relógio falso


# ------------------------------------------------------------------ entrada
def modo() -> str:
    """'f0' (AZURE_FALA_MODO vazio ou "f0") ou 'rapido'. Outro valor é erro de configuração: nunca troca de serviço (e de cobrança)
    por um erro de digitação."""
    m = (os.environ.get("AZURE_FALA_MODO") or "").strip().lower()
    if m in ("", "f0"):
        return "f0"
    if m in ("rapido", "rápido"):
        return "rapido"
    raise ErroVideo("azure_config", "transcrever")


def duracao(wav: str | Path) -> float:
    """A duração de fala16k.wav, conferido: PCM de 16 bits, mono, 16 kHz, de 0 a 130 s."""
    d = None
    try:
        with wave.open(str(wav), "rb") as w:
            if (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == (1, 2, TAXA, "NONE"):
                d = w.getnframes() / TAXA
    except (OSError, EOFError, wave.Error):
        d = None
    if d is None or not 0 < d <= DURACAO_MAX:
        raise ErroVideo("audio_invalido", "transcrever")
    return d


def lista_de_frases(glossario=(), fala_roteiro: str = "") -> list[str]:
    """A lista de frases (phrase list) que ajuda o reconhecimento: os termos do glossário e, da fala do roteiro, as sequências de
    palavras com maiúscula fora do começo da frase (nomes e siglas: "Ana Teste", "IBS", "eSocial"). A 1ª palavra da frase entra se
    tiver maiúscula no meio ("DCTFWeb") ou se abrir um nome ("Bruno Exemplo explica…"; "Bom dia", "Com a…" não). Sem algarismos (o F0
    devolve a forma léxica, por extenso). Até 300, sem repetir."""
    out: list[str] = []
    vistos: set[str] = set()

    def por(t: str) -> None:
        t = " ".join(str(t or "").split()).strip(_PONTAS)
        if 2 <= len(t) <= ITEM_MAX and t.casefold() not in vistos and not _MARCACAO.search(t) and len(out) < LISTA_MAX:
            vistos.add(t.casefold())
            out.append(t)

    for t in list(glossario or ())[:LISTA_MAX]:
        if isinstance(t, str):
            por(t)
    corrida: list[str] = []
    comeco, pendente = True, None
    for tok in [*str(fala_roteiro or "").split()[:6000], "."]:
        p = tok.strip(_PONTAS)
        titulo = p[:1].isupper() and p[1:].islower() and p.isalpha()
        nome = bool(_PALAVRA.match(p)) and (any(c.isupper() for c in p[1:]) or (p[0].isupper() and not comeco))
        if nome and pendente and titulo and not corrida:
            corrida.append(pendente)                     # "Bruno Exemplo explica…": o nome que abre a frase
        if nome:
            corrida.append(p)
        if corrida and (not nome or tok.rstrip(_PONTAS) != tok):   # a sequência acaba na palavra comum ou na pontuação
            por(" ".join(corrida))
            corrida = []
        pendente = p if comeco and titulo and len(p) >= 3 and p.casefold() not in _ABRE_FRASE and tok.rstrip(_PONTAS) == tok else None
        comeco = bool(_FIM_FRASE.search(tok))
    return out


def _chave() -> str:
    chave = (os.environ.get("AZURE_FALA_CHAVE") or "").strip()
    if not _CHAVE.match(chave):
        raise ErroVideo("azure_sem_chave", "transcrever")
    return chave


# ------------------------------------------------------------------ resultado (dado de fora: conferido)
def _segundos(x, escala: float, teto: float) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    v = float(x) / escala
    if not math.isfinite(v) or v < 0 or v > teto + 1.0:
        return None
    return round(min(v, teto), 3)


def _confianca(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)) or not 0 <= float(x) <= 1:
        return None
    return round(float(x), 3)


def _normalizar(palavras: list[dict], frases: list[dict]) -> tuple[list[dict], list[dict]]:
    """Só as palavras e frases com texto e tempos válidos, na ordem e dentro dos limites de alinhar.py."""
    pw = []
    for w in palavras:
        texto = w.get("texto")
        a, b = w.get("inicio"), w.get("fim")
        if isinstance(texto, str) and " ".join(texto.split()) and a is not None and b is not None and b >= a:
            pw.append({"texto": " ".join(texto.split())[:40], "inicio": a, "fim": b, "confianca": _confianca(w.get("confianca"))})
    fr = []
    for f in frases:
        d = f.get("display")
        a, b = f.get("inicio"), f.get("fim")
        if isinstance(d, str) and " ".join(d.split()) and a is not None and b is not None and b >= a:
            fr.append({"display": " ".join(d.split())[:2000], "inicio": a, "fim": b})
    pw.sort(key=lambda w: (w["inicio"], w["fim"]))
    fr.sort(key=lambda f: (f["inicio"], f["fim"]))
    return pw[:PALAVRAS_MAX], fr[:FRASES_MAX]


def _ler_sdk(jsons: list[str], teto: float) -> tuple[list[dict], list[dict]]:
    """O JSON detalhado de cada frase reconhecida (result.json): Offset e Duration em unidades de 100 ns, NBest[0].Words com a
    palavra na forma léxica e a confiança dela (sem ela, a da frase), DisplayText com a forma de exibição."""
    palavras, frases = [], []
    for js in jsons:
        try:
            d = json.loads(js)
        except (TypeError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("RecognitionStatus", "Success") != "Success":
            continue
        nb = d.get("NBest")
        nb = nb[0] if isinstance(nb, list) and nb and isinstance(nb[0], dict) else {}
        a = _segundos(d.get("Offset"), 1e7, teto)
        du = d.get("Duration")
        b = _segundos(d["Offset"] + du, 1e7, teto) if a is not None and isinstance(du, (int, float)) else None
        frases.append({"display": d.get("DisplayText") or nb.get("Display"), "inicio": a, "fim": b})
        for w in nb.get("Words") or []:
            if not isinstance(w, dict) or isinstance(w.get("Offset"), bool) or not isinstance(w.get("Offset"), (int, float)) \
                    or not isinstance(w.get("Duration"), (int, float)):
                continue
            palavras.append({"texto": w.get("Word"), "inicio": _segundos(w["Offset"], 1e7, teto),
                             "fim": _segundos(w["Offset"] + w["Duration"], 1e7, teto),
                             "confianca": w.get("Confidence", nb.get("Confidence"))})
    return palavras, frases


def _ler_rapido(dados: bytes, teto: float) -> tuple[list[dict], list[dict]] | None:
    """A resposta da fast transcription: phrases[] com offsetMilliseconds, durationMilliseconds, text (exibição), confidence e
    words[] (text, offsetMilliseconds, durationMilliseconds). None se não for esse formato."""
    try:
        d = json.loads(dados)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("phrases", []), list):
        return None
    palavras, frases = [], []
    for ph in d.get("phrases", []):
        if not isinstance(ph, dict) or ph.get("channel") not in (None, 0):
            continue
        off, du = ph.get("offsetMilliseconds"), ph.get("durationMilliseconds")
        a = _segundos(off, 1e3, teto)
        b = _segundos(off + du, 1e3, teto) if a is not None and isinstance(du, (int, float)) else None
        frases.append({"display": ph.get("text"), "inicio": a, "fim": b})
        for w in ph.get("words") or []:
            if not isinstance(w, dict) or isinstance(w.get("offsetMilliseconds"), bool) \
                    or not isinstance(w.get("offsetMilliseconds"), (int, float)) \
                    or not isinstance(w.get("durationMilliseconds"), (int, float)):
                continue
            palavras.append({"texto": w.get("text"), "inicio": _segundos(w["offsetMilliseconds"], 1e3, teto),
                             "fim": _segundos(w["offsetMilliseconds"] + w["durationMilliseconds"], 1e3, teto),
                             "confianca": ph.get("confidence")})
    return palavras, frases


# ------------------------------------------------------------------ F0: Speech SDK
def _sdk():
    sdk = None
    try:
        sdk = importlib.import_module("azure.cognitiveservices.speech")
    except Exception:                                   # noqa: BLE001 — ImportError, ou OSError da biblioteca nativa
        sdk = None
    if sdk is None:
        raise ErroVideo("azure_sem_sdk", "transcrever")
    return sdk


def _classe_sdk(sdk, codigo, detalhe) -> str:
    """O motivo do cancelamento, só pelo código e por palavras fixas do detalhe (que nunca sai daqui)."""
    c = sdk.CancellationErrorCode
    d = str(detalhe or "").lower()
    if codigo == c.TooManyRequests or "(429)" in d or "too many requests" in d:
        return "ocupada"
    if codigo == c.Forbidden or "quota" in d or "(403)" in d:
        return "cota"
    if codigo == c.AuthenticationFailure:
        return "chave"
    if codigo in (c.ConnectionFailure, c.ServiceTimeout, c.ServiceError, c.ServiceUnavailable):
        return "fora"
    return "erro"


def _tentar_f0(sdk, wav: str, chave: str, regiao: str, lista: list[str], dur: float) -> tuple[str, object, float | None]:
    """Uma tentativa: ("ok", (palavras, frases), None) ou (motivo, None, None)."""
    jsons: list[str] = []
    estado = {"motivo": None}
    fim = threading.Event()

    def reconhecido(evt) -> None:                       # roda na linha do SDK: nunca levanta
        try:
            if evt.result.reason == sdk.ResultReason.RecognizedSpeech:
                jsons.append(str(evt.result.json))
        except Exception:                               # noqa: BLE001
            estado["motivo"] = estado["motivo"] or "erro"

    def cancelado(evt) -> None:                         # EndOfStream é o fim do arquivo: session_stopped vem logo depois
        try:
            d = evt.cancellation_details
            if d.reason == sdk.CancellationReason.Error:
                estado["motivo"] = _classe_sdk(sdk, d.code, d.error_details)
                fim.set()
        except Exception:                               # noqa: BLE001
            estado["motivo"] = "erro"
            fim.set()

    terminou, falhou = False, False
    try:
        cfg = sdk.SpeechConfig(subscription=chave, region=regiao)
        cfg.speech_recognition_language = IDIOMA
        cfg.output_format = sdk.OutputFormat.Detailed
        cfg.request_word_level_timestamps()
        cfg.set_profanity(sdk.ProfanityOption.Raw)
        rec = sdk.SpeechRecognizer(speech_config=cfg, audio_config=sdk.audio.AudioConfig(filename=wav))
        if lista:
            grade = sdk.PhraseListGrammar.from_recognizer(rec)
            for item in lista:
                grade.addPhrase(item)
        rec.recognized.connect(reconhecido)
        rec.canceled.connect(cancelado)
        rec.session_stopped.connect(lambda evt: fim.set())
        rec.start_continuous_recognition()
        terminou = fim.wait(TEMPO_BASE + 3 * dur)
        rec.stop_continuous_recognition()
    except Exception:                                   # noqa: BLE001 — a mensagem pode ter o endereço: nunca sai
        falhou = True
    if falhou:
        return "erro", None, None
    if estado["motivo"]:
        return estado["motivo"], None, None
    if not terminou:
        return "fora", None, None
    return "ok", _ler_sdk(jsons, dur), None


# ------------------------------------------------------------------ rápido: fast transcription (REST)
class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):    # noqa: ARG002 — a chave nunca segue para outro endereço
        return None


def _abridor() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _SemRedirecionar())


def _endpoint() -> str:
    base = (os.environ.get("AZURE_FALA_ENDPOINT") or "").strip().rstrip("/")
    if not base:
        regiao = (os.environ.get("AZURE_FALA_REGIAO") or "").strip()
        base = f"https://{regiao}.api.cognitive.microsoft.com" if _REGIAO.match(regiao) else ""
    if not _ENDPOINT.match(base):
        raise ErroVideo("azure_config", "transcrever")
    return base


def _multipart(audio: bytes, definicao: dict) -> tuple[bytes, str]:
    b = "radar" + secrets.token_hex(16)
    corpo = (f"--{b}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"fala16k.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
             .encode() + audio + f"\r\n--{b}\r\nContent-Disposition: form-data; name=\"definition\"\r\n"
             f"Content-Type: application/json\r\n\r\n".encode() + json.dumps(definicao, ensure_ascii=False).encode()
             + f"\r\n--{b}--\r\n".encode())
    return corpo, f"multipart/form-data; boundary={b}"


def _depois(cabecalhos) -> float | None:
    try:
        v = float((cabecalhos or {}).get("Retry-After") or "")
    except (TypeError, ValueError):
        return None
    return min(ESPERA_TETO, max(1.0, v)) if math.isfinite(v) else None


def _tentar_rapido(base: str, chave: str, audio: bytes, lista: list[str], dur: float) -> tuple[str, object, float | None]:
    definicao = {"locales": [IDIOMA], "profanityFilterMode": "None", **({"phraseList": {"phrases": lista}} if lista else {})}
    corpo, tipo = _multipart(audio, definicao)
    pedido = urllib.request.Request(f"{base}/speechtotext/transcriptions:transcribe?api-version={API_RAPIDO}", data=corpo,
                                    method="POST", headers={"Ocp-Apim-Subscription-Key": chave, "Content-Type": tipo,
                                                            "Accept": "application/json"})
    status, depois, dados = 0, None, b""
    try:
        with _abridor().open(pedido, timeout=TEMPO_RAPIDO) as r:
            status, dados = r.status, r.read(RESPOSTA_MAX + 1)
    except urllib.error.HTTPError as e:                 # a resposta de erro da Azure nunca é lida
        status, depois = e.code, _depois(e.headers)
        e.close()
    except Exception:                                   # noqa: BLE001 — sem conexão, tempo esgotado (a mensagem tem o endereço)
        status = 0
    if status == 200 and len(dados) <= RESPOSTA_MAX:
        lido = _ler_rapido(dados, dur)
        return ("ok", lido, None) if lido is not None else ("erro", None, None)
    if status == 429:
        return "ocupada", None, depois
    if status == 401:
        return "chave", None, None
    if status == 403:
        return "cota", None, depois
    if status in (0, 408, 500, 502, 503, 504):
        return "fora", None, None
    return "erro", None, None


# ------------------------------------------------------------------ as tentativas
def _com_novas_tentativas(tentar, servico: str):
    """Recusa por limite ou cota: espera crescente (ou a do Retry-After) até ESPERA_MAX; falha de rede ou do serviço: até FALHAS_MAX
    tentativas; chave recusada ou pedido inválido: na hora. No log, só o motivo, o número da tentativa e a espera."""
    inicio, recusas, falhas = _relogio(), 0, 0
    while True:
        motivo, dados, depois = tentar()
        if motivo == "ok":
            return dados
        if motivo in ("ocupada", "cota"):
            espera = depois or min(ESPERA_TETO, ESPERA_INICIAL * 2 ** recusas) + random.uniform(0, 2)
            recusas += 1
            if _relogio() - inicio + espera > ESPERA_MAX:
                break
        elif motivo == "fora" and falhas + 1 < FALHAS_MAX:
            falhas += 1
            espera = ESPERA_INICIAL * 3 ** (falhas - 1)
        else:
            break
        segredo.log("transcrever", rapido=servico == SERVICO["rapido"], motivo=motivo, tentativa=recusas + falhas,
                    espera=round(espera, 1))
        _dormir(espera)
    raise ErroVideo(_CODIGO.get(motivo, "azure_erro"), "transcrever")


def transcrever(wav: str | Path, glossario=(), fala_roteiro: str = "", restante_s: float | None = None) -> dict:
    """fala16k.wav → {palavras, frases, transcricao}. glossario e fala_roteiro só formam a lista de frases; restante_s é o que falta
    da cota do Radar no mês (Configurações: limite_min_mes), conferido antes de mandar o áudio (cota_radar)."""
    m = modo()
    dur = duracao(wav)
    if restante_s is not None and dur > max(0.0, float(restante_s)):
        raise ErroVideo("cota_radar", "transcrever")
    lista = lista_de_frases(glossario, fala_roteiro)
    chave = _chave()
    if m == "f0":
        regiao = (os.environ.get("AZURE_FALA_REGIAO") or "").strip()
        if not _REGIAO.match(regiao):
            raise ErroVideo("azure_config", "transcrever")
        sdk = _sdk()
        palavras, frases = _com_novas_tentativas(lambda: _tentar_f0(sdk, str(wav), chave, regiao, lista, dur), SERVICO[m])
    else:
        base, audio = _endpoint(), Path(wav).read_bytes()
        palavras, frases = _com_novas_tentativas(lambda: _tentar_rapido(base, chave, audio, lista, dur), SERVICO[m])
    palavras, frases = _normalizar(palavras, frases)
    return {"palavras": palavras, "frases": frases,
            "transcricao": {"servico": SERVICO[m], "segundos_audio": round(dur, 1), "palavras": len(palavras)}}


# ------------------------------------------------------------------ palavras.json (modo montagem: o ajuste não transcreve de novo)
def para_json(r: dict) -> bytes:
    return json.dumps({"versao": 1, "palavras": r["palavras"], "frases": r["frases"], "transcricao": r["transcricao"]},
                      ensure_ascii=False, separators=(",", ":")).encode()


def de_json(dados: bytes) -> dict:
    """O palavras.json de uma tentativa anterior, conferido como a resposta da Azure (palavras_invalidas se não servir)."""
    d = None
    if isinstance(dados, (bytes, bytearray)) and len(dados) <= JSON_MAX:
        try:
            d = json.loads(dados)
        except ValueError:
            d = None
    if not isinstance(d, dict) or d.get("versao") != 1 or not isinstance(d.get("palavras"), list) \
            or not isinstance(d.get("frases"), list) or not isinstance(d.get("transcricao"), dict):
        raise ErroVideo("palavras_invalidas", "transcrever")
    t = d["transcricao"]
    seg = _segundos(t.get("segundos_audio"), 1, DURACAO_MAX)
    teto = seg if seg else DURACAO_MAX
    ler = lambda x: _segundos(x, 1, teto)
    palavras, frases = _normalizar(
        [{"texto": w.get("texto"), "inicio": ler(w.get("inicio")), "fim": ler(w.get("fim")), "confianca": w.get("confianca")}
         for w in d["palavras"][:PALAVRAS_MAX] if isinstance(w, dict)],
        [{"display": f.get("display"), "inicio": ler(f.get("inicio")), "fim": ler(f.get("fim"))}
         for f in d["frases"][:FRASES_MAX] if isinstance(f, dict)])
    servico = t.get("servico") if t.get("servico") in SERVICO.values() else None
    return {"palavras": palavras, "frases": frases,
            "transcricao": {"servico": servico, "segundos_audio": seg, "palavras": len(palavras)}}


# ------------------------------------------------------------------ o passo do workflow
def main(args: list[str]) -> int:
    """<pasta>/fala16k.wav e <pasta>/pedido_fala.json → <pasta>/palavras.json (0) ou <pasta>/transcricao_erro.txt (1). No log, só
    o código, o número de palavras e os segundos de áudio."""
    segredo.instalar_excepthook()
    pasta = Path(args[0]) if len(args) == 1 else None
    if pasta is None or not pasta.is_dir():
        segredo.log("transcrever", erro="pasta_invalida")
        return 2
    erro_txt = pasta / "transcricao_erro.txt"
    erro_txt.unlink(missing_ok=True)
    pedido, codigo = None, None
    try:
        pedido = json.loads((pasta / "pedido_fala.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pedido = None
    restante = pedido.get("restante_s") if isinstance(pedido, dict) else None
    if not isinstance(pedido, dict) or not isinstance(pedido.get("glossario"), list) or not isinstance(pedido.get("fala_roteiro"), str) \
            or not (restante is None or isinstance(restante, (int, float)) and not isinstance(restante, bool)):
        codigo = "pedido_invalido"                      # sem ele, a lista de frases e a cota do Radar ficariam de fora calados
    else:
        segredo.etapa("transcrever", pedido.get("pedido") if isinstance(pedido.get("pedido"), str) else None)
        try:
            r = transcrever(pasta / "fala16k.wav", pedido["glossario"], pedido["fala_roteiro"],
                            None if restante is None else float(restante))
            (pasta / "palavras.json").write_bytes(para_json(r))
        except ErroVideo as e:
            codigo = e.codigo
    if codigo:
        erro_txt.write_text(codigo, encoding="utf-8")
        segredo.log("transcrever", erro=codigo)
        return 1
    segredo.log("transcrever", palavras=r["transcricao"]["palavras"], segundos=float(r["transcricao"]["segundos_audio"]),
                rapido=r["transcricao"]["servico"] == SERVICO["rapido"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
