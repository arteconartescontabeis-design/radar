"""v0.22.0 — a Azure SIMULADA para os testes da transcrição (robo/video/transcrever.py). Nenhuma chamada à Azure:
  * sdk_falso(passos): um módulo no lugar do azure.cognitiveservices.speech, com os mesmos nomes que transcrever.py usa (conferidos
    contra o SDK de verdade quando ele está instalado); cada reconhecimento segue o próximo passo;
  * ServidorFala: um servidor local do protocolo de fala do SDK (WebSocket "USP": speech.config, speech.context, áudio; turn.start,
    speech.phrase, turn.end), para rodar o SDK DE VERDADE contra ele, sem rede (SpeechConfig com host=ws://127.0.0.1);
  * ServidorRapido: um servidor HTTP local no lugar da fast transcription (multipart; respostas roteirizadas);
  * wav() e frase_sdk(): o áudio de 16 kHz e o JSON detalhado de uma frase, como o SDK entrega em result.json.
Só textos fictícios ("Ana Teste", "Bruno Exemplo").
"""
from __future__ import annotations

import base64
import enum
import hashlib
import json
import math
import socketserver
import struct
import threading
import types
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

QUEBRADO = object()                    # num passo "ok": um evento com o resultado quebrado (a chamada de volta não pode levantar)
SEM_FALA = None                        # num passo "ok": um evento NoMatch


def wav(caminho: Path, segundos: float, taxa: int = 16000, canais: int = 1, largura: int = 2) -> Path:
    """Um WAV PCM com um tom baixo (o conteúdo não importa: a Azure é simulada)."""
    n = int(round(segundos * taxa))
    um = b"".join(struct.pack("<h", int(800 * math.sin(i / 7))) * canais if largura == 2 else b"\x80" * canais for i in range(taxa))
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(largura)
        w.setframerate(taxa)
        w.writeframes((um * (n // taxa + 1))[:n * canais * largura])
    return caminho


def frase_sdk(display: str, palavras: list[tuple], confianca: float = 0.9, status: str = "Success") -> str:
    """O result.json de uma frase reconhecida na saída detalhada: tempos em unidades de 100 ns; palavras (texto, ini_s, fim_s[, conf])."""
    t = lambda s: int(round(s * 1e7))
    ws = [{"Word": p[0], "Offset": t(p[1]), "Duration": t(p[2]) - t(p[1]), **({"Confidence": p[3]} if len(p) > 3 else {})}
          for p in palavras]
    ini = ws[0]["Offset"] if ws else 0
    fim = ws[-1]["Offset"] + ws[-1]["Duration"] if ws else 0
    return json.dumps({"Id": "x", "RecognitionStatus": status, "Offset": ini, "Duration": fim - ini, "DisplayText": display,
                       "NBest": [{"Confidence": confianca, "Lexical": " ".join(p[0] for p in palavras), "ITN": "", "MaskedITN": "",
                                  "Display": display, "Words": ws}]}, ensure_ascii=False)


# ------------------------------------------------------------------ o SDK falso
def sdk_falso(passos: list[tuple]) -> types.ModuleType:
    """Passos, um por reconhecimento (start_continuous_recognition):
      ("ok", [json | SEM_FALA | QUEBRADO, …]) — os eventos recognized, depois EndOfStream e session_stopped;
      ("erro", "TooManyRequests", "detalhe")    — canceled com CancellationReason.Error, o código e o detalhe, e session_stopped;
      ("trava",)                                 — nunca termina;
      ("excecao", "mensagem")                    — start_continuous_recognition levanta RuntimeError.
    m.feitos guarda cada reconhecimento: a configuração, o áudio e a lista de frases."""
    m = types.ModuleType("azure.cognitiveservices.speech")
    m.passos, m.feitos = list(passos), []

    class ResultReason(enum.Enum):
        NoMatch = 0
        Canceled = 1
        RecognizingSpeech = 2
        RecognizedSpeech = 3

    class CancellationReason(enum.Enum):
        Error = 1
        EndOfStream = 2
        CancelledByUser = 3

    class CancellationErrorCode(enum.Enum):
        NoError = 0
        AuthenticationFailure = 1
        BadRequest = 2
        TooManyRequests = 3
        Forbidden = 4
        ConnectionFailure = 5
        ServiceTimeout = 6
        ServiceError = 7
        ServiceUnavailable = 8
        RuntimeError = 9

    class OutputFormat(enum.Enum):
        Simple = 0
        Detailed = 1

    class ProfanityOption(enum.Enum):
        Masked = 0
        Removed = 1
        Raw = 2

    class SpeechConfig:
        def __init__(self, subscription=None, region=None, endpoint=None, host=None, auth_token=None,
                     speech_recognition_language=None, token_credential=None, key_credential=None):
            self.subscription_key, self.region = subscription, region
            self.speech_recognition_language = speech_recognition_language
            self.output_format = OutputFormat.Simple
            self.tempos_por_palavra, self.palavrao = False, ProfanityOption.Masked

        def request_word_level_timestamps(self):
            self.tempos_por_palavra = True

        def set_profanity(self, opcao):
            self.palavrao = opcao

    class AudioConfig:
        def __init__(self, use_default_microphone=False, filename=None, stream=None, device_name=None):
            self.filename = filename

    class EventSignal:
        def __init__(self):
            self.chamadas = []

        def connect(self, callback):
            self.chamadas.append(callback)

        def signal(self, evt):
            for c in self.chamadas:
                c(evt)

    class CancellationDetails:
        def __init__(self, reason, code, error_details):
            self.reason, self.code, self.error_details = reason, code, error_details

    class SpeechRecognizer:
        def __init__(self, speech_config=None, audio_config=None, language=None, source_language_config=None,
                     auto_detect_source_language_config=None):
            self.recognized, self.canceled = EventSignal(), EventSignal()
            self.session_started, self.session_stopped = EventSignal(), EventSignal()
            self.frases, self.parado = [], False
            m.feitos.append({"config": speech_config, "audio": audio_config, "frases": self.frases})

        def start_continuous_recognition(self):
            passo = m.passos.pop(0) if m.passos else ("ok", [])
            if passo[0] == "excecao":
                raise RuntimeError(passo[1])
            threading.Thread(target=self._correr, args=(passo,), daemon=True).start()

        def _correr(self, passo):
            ns = types.SimpleNamespace
            self.session_started.signal(ns(session_id="s"))
            if passo[0] == "trava":
                return
            if passo[0] == "erro":
                d = CancellationDetails(CancellationReason.Error, getattr(CancellationErrorCode, passo[1]), passo[2])
                self.canceled.signal(ns(cancellation_details=d, result=ns(reason=ResultReason.Canceled)))
            else:
                for js in passo[1]:
                    if js is QUEBRADO:
                        self.recognized.signal(ns(result=None))
                    elif js is SEM_FALA:
                        self.recognized.signal(ns(result=ns(reason=ResultReason.NoMatch, json="{}")))
                    else:
                        self.recognized.signal(ns(result=ns(reason=ResultReason.RecognizedSpeech, json=js)))
                d = CancellationDetails(CancellationReason.EndOfStream, CancellationErrorCode.NoError, "")
                self.canceled.signal(ns(cancellation_details=d, result=ns(reason=ResultReason.Canceled)))
            self.session_stopped.signal(ns(session_id="s"))

        def stop_continuous_recognition(self):
            self.parado = True

    class PhraseListGrammar:
        @classmethod
        def from_recognizer(cls, recognizer):
            g = cls()
            g.rec = recognizer
            return g

        def addPhrase(self, phrase):                    # noqa: N802 — o nome do SDK
            self.rec.frases.append(phrase)

    audio = types.ModuleType("azure.cognitiveservices.speech.audio")
    audio.AudioConfig = AudioConfig
    for nome, v in [("ResultReason", ResultReason), ("CancellationReason", CancellationReason),
                    ("CancellationErrorCode", CancellationErrorCode), ("OutputFormat", OutputFormat),
                    ("ProfanityOption", ProfanityOption), ("SpeechConfig", SpeechConfig), ("SpeechRecognizer", SpeechRecognizer),
                    ("PhraseListGrammar", PhraseListGrammar), ("EventSignal", EventSignal),
                    ("CancellationDetails", CancellationDetails), ("audio", audio)]:
        setattr(m, nome, v)
    return m


# ------------------------------------------------------------------ o protocolo de fala do SDK, local (para o SDK de verdade)
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class ServidorFala:
    """WebSocket local que fala o protocolo do SDK. Enquanto `recusar` tiver um status ("429 Too Many Requests"), toda conexão é
    recusada na abertura com ele (o SDK tenta algumas vezes por conta própria antes de cancelar); senão, aceita, guarda o pedido e,
    no fim do áudio, devolve as `frases` [(display, [(palavra, ini_s, fim_s, conf)])], o fim da fala e o fim do turno."""

    def __init__(self, frases: list[tuple], recusar: str | None = None):
        self.frases, self.recusar = frases, recusar
        self.aberturas: list[str] = []                  # o pedido de abertura (linha e cabeçalhos) de cada conexão aceita
        self.recusadas = 0
        self.contextos: list[dict] = []                 # o speech.context de cada turno (a lista de frases vai nele)
        servidor = self

        class Atende(socketserver.BaseRequestHandler):
            def handle(self):
                servidor._atender(self.request)

        self._srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Atende)
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.porta = self._srv.server_address[1]

    def fechar(self):
        self._srv.shutdown()
        self._srv.server_close()

    @staticmethod
    def _ler(s, n):
        b = b""
        while len(b) < n:
            p = s.recv(n - len(b))
            if not p:
                raise EOFError
            b += p
        return b

    def _quadro(self, s):
        h = self._ler(s, 2)
        op, n = h[0] & 0x0F, h[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._ler(s, 2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._ler(s, 8))[0]
        k = self._ler(s, 4) if h[1] & 0x80 else b"\0\0\0\0"
        d = bytearray(self._ler(s, n))
        for i in range(n):
            d[i] ^= k[i % 4]
        return op, bytes(d)

    @staticmethod
    def _enviar(s, rid, caminho, obj):
        t = (f"X-RequestId: {rid}\r\nPath: {caminho}\r\nContent-Type: application/json; charset=utf-8\r\n\r\n" + json.dumps(obj)).encode()
        n = len(t)
        cab = bytes([0x81, n]) if n < 126 else bytes([0x81, 126]) + struct.pack(">H", n) if n < 65536 else \
            bytes([0x81, 127]) + struct.pack(">Q", n)
        s.sendall(cab + t)

    def _atender(self, s):
        dados = b""
        while b"\r\n\r\n" not in dados:
            p = s.recv(4096)
            if not p:
                return
            dados += p
        abertura = dados.split(b"\r\n\r\n")[0].decode("utf-8", "replace")
        if self.recusar:
            self.recusadas += 1
            s.sendall(f"HTTP/1.1 {self.recusar}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
            return
        self.aberturas.append(abertura)
        chave = next(l.split(":", 1)[1].strip() for l in abertura.splitlines() if l.lower().startswith("sec-websocket-key:"))
        aceite = base64.b64encode(hashlib.sha1((chave + _GUID).encode()).digest()).decode()
        s.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Accept: {aceite}\r\n\r\n").encode())
        rid, audio = None, 0
        while True:
            try:
                op, d = self._quadro(s)
            except (EOFError, OSError):
                return
            if op == 8:
                return
            if op == 1:                                  # texto: cabeçalhos, linha em branco, JSON
                cab, _, corpo = d.decode("utf-8", "replace").partition("\r\n\r\n")
                linhas = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in cab.splitlines() if ":" in l}
                rid = linhas.get("x-requestid", rid)
                if linhas.get("path") == "speech.context":
                    self.contextos.append(json.loads(corpo))
            elif op == 2:                                # áudio: 2 bytes com o tamanho do cabeçalho, o cabeçalho e os bytes
                n = struct.unpack(">H", d[:2])[0]
                for l in d[2:2 + n].decode("utf-8", "replace").splitlines():
                    if l.lower().startswith("x-requestid:"):
                        rid = l.split(":", 1)[1].strip()
                corpo = d[2 + n:]
                if audio == 0:
                    self._enviar(s, rid, "turn.start", {"context": {"serviceTag": "teste"}})
                audio += len(corpo)
                if not corpo:                            # fim do áudio: as frases, o fim da fala e o fim do turno
                    fim = int((audio - 44) / 32000 * 1e7)
                    for display, palavras in self.frases:
                        self._enviar(s, rid, "speech.phrase", json.loads(frase_sdk(display, palavras)))
                    self._enviar(s, rid, "speech.phrase", {"RecognitionStatus": "EndOfDictation", "Offset": fim, "Duration": 0})
                    self._enviar(s, rid, "speech.endDetected", {"Offset": fim})
                    self._enviar(s, rid, "turn.end", {})
                    audio = 0


# ------------------------------------------------------------------ a fast transcription, local
class ServidorRapido:
    """HTTP local no lugar de https://<recurso>.cognitiveservices.azure.com. Cada pedido recebe a próxima resposta de `respostas`
    [(status, cabeçalhos, corpo)] e fica em `pedidos` (caminho, cabeçalhos, corpo)."""

    def __init__(self, respostas: list[tuple]):
        self.respostas, self.pedidos = list(respostas), []
        servidor = self

        class Atende(BaseHTTPRequestHandler):
            def _responder(self):
                n = int(self.headers.get("Content-Length") or 0)
                servidor.pedidos.append((self.path, dict(self.headers), self.rfile.read(n) if n else b""))
                status, cab, corpo = servidor.respostas.pop(0) if servidor.respostas else (500, {}, b"")
                self.send_response(status)
                for k, v in cab.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            do_POST = do_GET = _responder

            def log_message(self, *a):               # nada no stderr
                pass

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), Atende)
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}"

    def fechar(self):
        self._srv.shutdown()
        self._srv.server_close()
