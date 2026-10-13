"""Radar Artecon — corretor de vídeo (v0.22.0): a conversa do robô com a função radar-video, o único lugar com que ele fala.

O robô não tem chave do Supabase nem acesso ao banco (desenho 2.3, com os ajustes do dono): só o token estreito do Vault
'radar_video_robo' (RADAR_VIDEO_ROBO_CHAVE, segredo do repositório privado radar-video), no cabeçalho x-radar-video-robo, e a chave
anon PÚBLICA de radar-config.js no Authorization (o "Verify JWT" da função exige). Os arquivos vão e vêm pelos links que a função
assina, um caminho do pedido de cada vez (600 s para ler; o token de envio vale 2 h e serve a um caminho só, sem upsert):
  * endereço: só https://<projeto>.supabase.co/functions/v1/radar-video, do MESMO projeto da chave anon (o "ref" do JWT e o de
    radar-config.js), ou http://127.0.0.1 (os testes). Um link só é usado se for desse mesmo projeto e do caminho pedido
    (…/storage/v1/object/sign/radar-videos/<caminho> para ler, …/object/upload/sign/radar-videos/<caminho> para gravar): uma resposta
    adulterada não leva o robô, a chave nem um arquivo a outro lugar;
  * urllib sem o proxy do ambiente e sem seguir redirecionamento;
  * a chave é lida do ambiente na hora, conferida (^[A-Za-z0-9]{32,200}$: nada que quebre um cabeçalho) e nunca vai para log, erro
    ou exceção encadeada (todo ErroVideo é levantado FORA do except);
  * a resposta da função e do armazenamento nunca é impressa: só vira um código fixo — 401 robo_chave; o pedido que não está mais com
    o robô (RADAR316: substituído, descartado, ajustado ou vencido) pedido_perdido; o corrigido que já existe (409 nos links)
    ja_existe; 5xx, 409 e 404 do armazenamento storage; sem conexão ou tempo esgotado rede; o resto robo_recusado;
  * o pegar nunca se repete sozinho (o pegar repetido tomaria outro pedido); links, audio (o banco soma os segundos uma vez por rodada:
    radar_video_registrar_audio), parcial, concluir e falhar tentam de novo na falha de rede ou do servidor (o concluir repetido que já
    valeu volta pedido_perdido);
  * baixar: em blocos, até o tamanho declarado (arquivo_grande); subir: PUT com o tipo, cache-control de 60 s e x-upsert false, como o
    uploadToSignedUrl do supabase-js ("já existe" volta False: quem chama decide; o concluir confere tamanho e tipo no armazenamento).
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from segredo import ErroVideo

RAIZ = Path(__file__).resolve().parent.parent.parent
CONFIG_JS = RAIZ / "radar-config.js"
BUCKET = "radar-videos"
TEMPO_FUNCAO = 90                      # s: o pegar assina até 13 links (cada um uma ida ao armazenamento)
TEMPO_ARQUIVO = 120                    # s sem receber ou mandar nada (o arquivo em si pode levar mais)
RESPOSTA_MAX = 2 * 1024 * 1024         # a resposta da função (o pedido traz a fala e as Configurações)
ERRO_MAX = 4096                        # do corpo de uma resposta de erro só se lê isto (para classificar; nunca sai daqui)
BLOCO = 1024 * 1024
TENTATIVAS = 3
ESPERAS = (5.0, 15.0)
CACHE = "max-age=60"                   # cacheControl de 60 s: a validade efetiva do link é o prazo + 60 s (desenho 3.3)
TIPOS_CLIPE = ("video/mp4", "video/quicktime")
# (sempre fullmatch: o "$" do re aceitaria uma quebra de linha no fim, que no cabeçalho viraria outro cabeçalho)
_CHAVE = re.compile(r"[A-Za-z0-9]{32,200}")
_FUNCAO = re.compile(r"https://([a-z0-9]{20})\.supabase\.co/functions/v1/radar-video")
_LOCAL = re.compile(r"http://127\.0\.0\.1:\d{2,5}(?:/[A-Za-z0-9_./-]*)?")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_CAMINHO = re.compile(r"(bruto|trabalho|corrigido|quadros)/[0-9a-f-]{36}/[A-Za-z0-9_./-]{1,90}")
_PERDIDO = "este pedido não está mais com o robô"           # RADAR316 de radar_video_do_robo (a função tira o código)
_dormir = time.sleep                                        # os testes trocam


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):    # noqa: ARG002 — a chave nunca segue para outro endereço
        return None


def _abridor() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _SemRedirecionar())


def _jwt(token: str) -> dict:
    try:
        meio = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(meio + "=" * (-len(meio) % 4)))
    except (IndexError, ValueError):
        return {}


def anon_do_config(caminho: Path = CONFIG_JS) -> tuple[str, str]:
    """A chave anon (pública) e o ref do projeto, de radar-config.js (a mesma que a tela usa). Precisa ser um JWT com role anon."""
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError:
        texto = ""
    chave = re.search(r'SUPABASE_ANON_KEY:\s*"([A-Za-z0-9_.-]+)"', texto)
    url = re.search(r'SUPABASE_URL:\s*"https://([a-z0-9]{20})\.supabase\.co"', texto)
    dados = _jwt(chave.group(1)) if chave else {}
    if not chave or not url or dados.get("role") != "anon" or dados.get("ref") != url.group(1):
        raise ErroVideo("robo_config", "conversa")
    return chave.group(1), url.group(1)


class Conversa:
    """A radar-video, do jeito que o robô a vê. Do ambiente (do_ambiente): RADAR_VIDEO_URL e RADAR_VIDEO_ROBO_CHAVE."""

    def __init__(self, url: str, chave: str, anon: str, ref: str | None = None):
        url = (url or "").strip()
        m = _FUNCAO.fullmatch(url)
        if m:
            if ref is not None and m.group(1) != ref:      # a chave do robô só vai para o projeto da chave anon do repositório
                raise ErroVideo("robo_config", "conversa")
            self._origem = ("https", f"{m.group(1)}.supabase.co")
        elif _LOCAL.fullmatch(url):
            self._origem = ("http", "127.0.0.1")           # os testes (a porta do armazenamento pode ser outra)
        else:
            raise ErroVideo("robo_config", "conversa")
        if not _CHAVE.fullmatch(chave or ""):
            raise ErroVideo("robo_sem_chave", "conversa")
        if not isinstance(anon, str) or _jwt(anon).get("role") != "anon":
            raise ErroVideo("robo_config", "conversa")
        self._url, self._chave, self._anon = url, chave, anon

    @classmethod
    def do_ambiente(cls) -> "Conversa":
        anon, ref = anon_do_config()
        return cls(os.environ.get("RADAR_VIDEO_URL", ""), (os.environ.get("RADAR_VIDEO_ROBO_CHAVE") or "").strip(), anon, ref)

    def __repr__(self) -> str:                             # nunca a chave
        return "Conversa(radar-video)"

    # ------------------------------------------------------------------ a função
    def _uma(self, corpo: bytes) -> tuple[int, bytes]:
        pedido = urllib.request.Request(self._url, data=corpo, method="POST", headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + self._anon, "x-radar-video-robo": self._chave})
        status, dados = 0, b""
        try:
            with _abridor().open(pedido, timeout=TEMPO_FUNCAO) as r:
                status, dados = r.status, r.read(RESPOSTA_MAX + 1)
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                dados = e.read(ERRO_MAX)
            except Exception:                              # noqa: BLE001 — o corpo do erro é só para classificar
                dados = b""
            e.close()
        except Exception:                                  # noqa: BLE001 — sem conexão, tempo esgotado (a mensagem tem o endereço)
            status = 0
        return status, dados

    def chamar(self, acao: str, repetir: bool = True, **campos) -> dict:
        """Uma ação do robô ({acao, …}); devolve o JSON da resposta ou levanta ErroVideo com o código fixo."""
        corpo = json.dumps({"acao": acao, **campos}, ensure_ascii=False, separators=(",", ":")).encode()
        for k in range(TENTATIVAS if repetir else 1):
            status, dados = self._uma(corpo)
            codigo = _codigo(status, dados)
            if codigo is None:
                break
            if codigo not in ("rede", "storage") or k + 1 >= (TENTATIVAS if repetir else 1):
                raise ErroVideo(codigo, acao if re.fullmatch(r"[a-z_]{3,40}", acao) else "")
            _dormir(ESPERAS[min(k, len(ESPERAS) - 1)])
        resposta = None
        if len(dados) <= RESPOSTA_MAX:
            try:
                resposta = json.loads(dados)
            except ValueError:
                resposta = None
        if not isinstance(resposta, (dict, bool)):
            raise ErroVideo("resposta_invalida", acao)
        return resposta if isinstance(resposta, dict) else {"ok": resposta}

    def pegar(self) -> dict | None:
        """O próximo pedido, conferido: {pedido, partes: [{n, tipo, bytes, url}], palavras: url|None}; None sem pedido."""
        r = self.chamar("pegar", repetir=False)
        p = r.get("pedido")
        if p is None:
            return None
        if not isinstance(p, dict):
            raise ErroVideo("resposta_invalida", "pegar")
        pedido = _pedido(p)
        links = r.get("links") if isinstance(r.get("links"), dict) else {}
        urls = {x.get("n"): x.get("url") for x in links.get("partes") or [] if isinstance(x, dict)}
        partes = []
        for parte in pedido["partes"]:
            partes.append({**parte, "url": self._link(urls.get(parte["n"]), f"bruto/{pedido['id']}/{parte['n']}")})
        palavras = None
        if pedido["modo"] == "montagem":
            g = pedido["palavras_tentativa"]
            palavras = self._link(links.get("palavras"), f"trabalho/{pedido['id']}/{g}/palavras.json") if g else None
        return {"pedido": pedido, "partes": partes, "palavras": palavras}

    def links(self, vid: str, t: int, ler=(), gravar=()) -> dict:
        """{ler: {caminho: url}, gravar: {caminho: url}}, só dos caminhos pedidos e conferidos."""
        r = self.chamar("links", id=vid, tentativa=t, ler=list(ler), gravar=list(gravar))
        out = {"ler": {}, "gravar": {}}
        for tipo in ("ler", "gravar"):
            dados = r.get(tipo) if isinstance(r.get(tipo), dict) else {}
            for caminho in (ler if tipo == "ler" else gravar):
                v = dados.get(caminho)
                url = v.get("url") if tipo == "gravar" and isinstance(v, dict) else v
                out[tipo][caminho] = self._link(url, caminho, gravar=tipo == "gravar")
        return out

    def audio(self, vid: str, t: int, segundos: float) -> dict:
        """Os segundos transcritos na cota do mês. Repete na falha (o banco soma uma vez por rodada): o áudio já foi para a Azure, e a
        chamada perdida deixaria a cota do F0, dividida com a Agenda, abaixo do real."""
        return self.chamar("audio", id=vid, tentativa=t, segundos=round(float(segundos), 1))

    def parcial(self, vid: str, t: int, relatorio: dict) -> dict:
        return self.chamar("parcial", id=vid, tentativa=t, relatorio=relatorio)

    def concluir(self, vid: str, t: int, situacao: str, relatorio: dict, sha256: str, tamanho: int, duracao: float) -> dict:
        return self.chamar("concluir", id=vid, tentativa=t, situacao=situacao, relatorio=relatorio, sha256=sha256, bytes=tamanho,
                           duracao=duracao)

    def falhar(self, vid: str, t: int, codigo: str) -> dict:
        return self.chamar("falhar", id=vid, tentativa=t, codigo=codigo if re.fullmatch(r"[a-z_]{3,40}", codigo) else "erro_interno")

    # ------------------------------------------------------------------ os links do armazenamento
    def _link(self, url, caminho: str, gravar: bool = False) -> str:
        """O link só vale se for do mesmo projeto, do caminho pedido, com o token: senão resposta_invalida (e nada é aberto)."""
        if not isinstance(url, str) or not _CAMINHO.fullmatch(caminho) or ".." in caminho.split("/"):
            raise ErroVideo("resposta_invalida", "links")
        u = urllib.parse.urlsplit(url)
        rota = f"/storage/v1/object/{'upload/sign' if gravar else 'sign'}/{BUCKET}/{caminho}"
        consulta = urllib.parse.parse_qs(u.query, keep_blank_values=True)
        if (u.scheme, u.hostname) != self._origem or u.username or u.password or u.fragment or u.path != rota \
                or len(consulta.get("token", [])) != 1 or not consulta["token"][0] or set(consulta) - {"token", "download"} \
                or (self._origem[0] == "https" and u.port not in (None, 443)):
            raise ErroVideo("resposta_invalida", "links")
        return url

    def baixar(self, url: str, destino: Path, maximo: int) -> int:
        """Baixa o link para `destino`, em blocos, até `maximo` bytes (passando disso: arquivo_grande). Devolve o tamanho."""
        tamanho, codigo = 0, None
        try:
            with _abridor().open(urllib.request.Request(url, method="GET"), timeout=TEMPO_ARQUIVO) as r, destino.open("wb") as f:
                if r.status != 200:
                    codigo = "storage"
                while codigo is None:
                    bloco = r.read(BLOCO)
                    if not bloco:
                        break
                    tamanho += len(bloco)
                    if tamanho > maximo:
                        codigo = "arquivo_grande"
                        break
                    f.write(bloco)
        except urllib.error.HTTPError as e:
            e.close()
            codigo = "storage"
        except Exception:                                  # noqa: BLE001 — sem conexão, tempo esgotado, disco
            codigo = "rede"
        if codigo:
            destino.unlink(missing_ok=True)
            raise ErroVideo(codigo, "baixar")
        return tamanho

    def subir(self, url: str, arquivo: Path, tipo: str) -> bool:
        """PUT do arquivo no token de envio. True: subiu; False: o caminho já existia (sem upsert, nunca se sobrescreve)."""
        tamanho = arquivo.stat().st_size
        for k in range(TENTATIVAS):
            status, dados = 0, b""
            try:
                with arquivo.open("rb") as f:
                    pedido = urllib.request.Request(url, data=f, method="PUT", headers={
                        "Content-Type": tipo, "Content-Length": str(tamanho), "cache-control": CACHE, "x-upsert": "false",
                        "apikey": self._anon, "Authorization": "Bearer " + self._anon})
                    with _abridor().open(pedido, timeout=TEMPO_ARQUIVO) as r:
                        status = r.status
                        r.read(ERRO_MAX)
            except urllib.error.HTTPError as e:
                status = e.code
                try:
                    dados = e.read(ERRO_MAX)
                except Exception:                          # noqa: BLE001
                    dados = b""
                e.close()
            except Exception:                              # noqa: BLE001 — sem conexão, tempo esgotado
                status = 0
            if 200 <= status < 300:
                return True
            if _ja_existe(status, dados):
                return False
            if status not in (0, 408, 429, 500, 502, 503, 504) or k + 1 >= TENTATIVAS:
                break
            _dormir(ESPERAS[min(k, len(ESPERAS) - 1)])
        raise ErroVideo("rede" if status == 0 else "storage", "subir")


def _ja_existe(status: int, dados: bytes) -> bool:
    """O armazenamento responde 400 (ou 409) com {"statusCode": "409", "error": "Duplicate"} ao caminho que já existe."""
    if status == 409:
        return True
    if status != 400:
        return False
    try:
        d = json.loads(dados[:ERRO_MAX])
    except ValueError:
        return False
    return isinstance(d, dict) and (str(d.get("statusCode")) == "409" or d.get("error") == "Duplicate")


def _codigo(status: int, dados: bytes) -> str | None:
    """None se deu certo; senão o código fixo (a mensagem da função só é olhada para achar o RADAR316, nunca sai)."""
    if status == 200:
        return None
    if status == 0:
        return "rede"
    if status == 401:
        return "robo_chave"
    mensagem = ""
    try:
        d = json.loads(dados[:ERRO_MAX])
        mensagem = str(d.get("message") or "") if isinstance(d, dict) else ""
    except ValueError:
        mensagem = ""
    if status == 400 and mensagem.startswith(_PERDIDO):
        return "pedido_perdido"
    if status == 409 and "nunca se sobrescreve" in mensagem:
        return "ja_existe"
    if status in (404, 409, 429) or status >= 500:
        return "storage"
    return "robo_recusado"


def _inteiro(x, minimo: int, maximo: int) -> int:
    if isinstance(x, bool) or not isinstance(x, int) or not minimo <= x <= maximo:
        raise ErroVideo("resposta_invalida", "pegar")
    return x


def _pedido(p: dict) -> dict:
    """O pedido de radar_video_pegar, conferido (dado de fora: só o que tem a forma certa segue)."""
    vid = p.get("id")
    if not isinstance(vid, str) or not _UUID.fullmatch(vid) or p.get("modo") not in ("completo", "montagem"):
        raise ErroVideo("resposta_invalida", "pegar")
    partes = p.get("partes")
    if not isinstance(partes, list) or not 1 <= len(partes) <= 12:
        raise ErroVideo("resposta_invalida", "pegar")
    limpas = []
    for k, x in enumerate(partes, 1):
        if not isinstance(x, dict) or x.get("tipo") not in TIPOS_CLIPE:
            raise ErroVideo("resposta_invalida", "pegar")
        limpas.append({"n": _inteiro(x.get("n"), k, k), "tipo": x["tipo"], "bytes": _inteiro(x.get("bytes"), 1, 500 * 1024 * 1024)})
    linhas = p.get("cartela_linhas")
    if not isinstance(linhas, list) or not 1 <= len(linhas) <= 4 or not all(isinstance(x, str) for x in linhas):
        raise ErroVideo("resposta_invalida", "pegar")
    fala, gancho = p.get("fala_roteiro"), p.get("gancho")
    if not isinstance(fala, str) or len(fala) > 6000 or not (gancho is None or isinstance(gancho, str) and len(gancho) <= 120):
        raise ErroVideo("resposta_invalida", "pegar")
    ajustes, config = p.get("ajustes"), p.get("config")
    if not isinstance(ajustes, dict) or not isinstance(config, dict):
        raise ErroVideo("resposta_invalida", "pegar")
    restante = p.get("restante_s")
    if isinstance(restante, bool) or not isinstance(restante, (int, float)):
        raise ErroVideo("resposta_invalida", "pegar")
    g = p.get("palavras_tentativa")
    return {"id": vid, "tentativa": _inteiro(p.get("tentativa"), 1, 200), "modo": p["modo"], "partes": limpas, "fala_roteiro": fala,
            "cartela_linhas": linhas, "gancho": gancho, "ajustes": ajustes, "config": config, "restante_s": max(0.0, float(restante)),
            "palavras_tentativa": None if g is None else _inteiro(g, 1, 200)}
