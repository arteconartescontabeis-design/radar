"""Radar Artecon — corretor de vídeo (v0.22.0): o robô de ponta a ponta, em fases — cada uma é um passo do workflow.

O workflow do repositório PRIVADO radar-video (o modelo está em robo/video/workflow/radar-video.yml) baixa este código do repositório
público num commit fixo e trata UM pedido por execução, numa pasta de trabalho só dele (<trabalho>, em $RUNNER_TEMP):
  pegar     [chave do robô]       o próximo pedido na radar-video (conversa.py) e os clipes, pelos links de 600 s → ent/<n>; no modo
                                  montagem (ajuste, reconferir, tentar de novo), a transcrição guardada (palavras.json) → fala/;
  preparar  [sem segredo]         sondar e recusar (entrada não confiável), o áudio de trabalho e as pausas (sondar.py, audio.py); no
                                  modo completo, fala/fala16k.wav e fala/pedido_fala.json para o passo seguinte;
  (transcrever.py) [só a Azure]   fala/palavras.json ou fala/transcricao_erro.txt (o F0 pelo Speech SDK; a chave do robô não está ali);
  alinhar   [chave do robô]       guarda a transcrição (trabalho/<id>/<t>/palavras.json) e registra os segundos na cota do mês (audio;
                                  o banco soma uma vez por rodada), alinha com o roteiro (alinhar.py), planeja os cortes (cortes.py)
                                  e manda o relatório parcial: a equipe sabe se precisa regravar sem esperar o vídeo;
  montar    [sem segredo]         legenda, gancho, cartela, montagem, conferência e o relatório final (legenda.py, cartela.py,
                                  montar.py, conferir.py, relatorio.py);
  entregar  [chave do robô]       sobe o vídeo em corrigido/<id>/<sha256>.mp4 (nunca se sobrescreve) e os 4 quadros, e conclui; se
                                  algo parou antes, manda o código fixo (falhar). Roda sempre que houve pedido (if: always()).
Assim a chave do robô só existe nos passos que falam com a radar-video, e esses só carregam a biblioteca padrão e o código daqui (nada
do Pillow nem do SDK da Azure); a da Azure só no passo da transcrição; e o ffmpeg roda sempre no contêiner sem rede, sem ambiente e só
leitura (isolado.py), escrevendo só em sai/ — fala/ e os arquivos do estado ficam fora do alcance dele.

Estado entre as fases, na pasta de trabalho: pedido.json (o pedido, sem os links), estado.json (a sondagem, as pausas, o alinhamento
e o plano), resultado.json (o relatório final e o vídeo) e erro.json ({codigo, etapa, detalhe}: a fase seguinte pula e o entregar
manda o código). Nada disso vai para log: no log, só a fase, o uuid do pedido, números e códigos (segredo.log).

Saída de cada fase: 0 (fez, ou recusou com código e registrou), 1 (erro de configuração ou inesperado: o job fica vermelho), 2 (uso).
O pegar escreve em $GITHUB_OUTPUT pedido=sim|nao e seguir=sim|nao; o preparar, transcrever=sim|nao.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":                              # python -I não põe a pasta do script no sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import hashlib
import json
import os
import re

import segredo
from conversa import Conversa
from segredo import ErroVideo

FONTES = Path(__file__).resolve().parent / "fontes"
PRESET = "medium"                      # x264 (os testes trocam por um mais rápido)
JSON_MAX = 2 * 1024 * 1024             # o palavras.json guardado (transcrever.JSON_MAX)
_ARQUIVO = re.compile(r"/[A-Za-z0-9_./-]+")             # fullmatch (o "$" aceitaria a quebra de linha no fim)


class Trabalho:
    """A pasta de trabalho de um pedido: ent/ (os clipes; só leitura no contêiner), sai/ (o que o ffmpeg grava), fala/ (a transcrição,
    fora do contêiner) e os arquivos do estado."""

    def __init__(self, pasta: Path):
        self.pasta = Path(os.path.abspath(pasta))
        if not _ARQUIVO.fullmatch(str(self.pasta)) or ".." in self.pasta.parts:
            raise ErroVideo("pasta_invalida", "corrigir")
        self.ent, self.sai, self.fala = self.pasta / "ent", self.pasta / "sai", self.pasta / "fala"

    def pastas(self):
        import isolado
        return isolado.Pastas(self.ent, self.sai, FONTES)

    def ler(self, nome: str) -> dict | None:
        try:
            dados = json.loads((self.pasta / f"{nome}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return dados if isinstance(dados, dict) else None

    def gravar(self, nome: str, dados: dict) -> None:
        tmp = self.pasta / f".{nome}.json"
        tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.pasta / f"{nome}.json")

    def erro(self) -> dict | None:
        e = self.ler("erro")
        return e if e and isinstance(e.get("codigo"), str) and segredo.CODIGO.match(e["codigo"]) else None

    def falhou(self, e: ErroVideo, fase: str) -> None:
        """Guarda o código para o entregar (a fase seguinte pula) e registra no log só o código, a etapa e os itens fixos."""
        self.gravar("erro", {"codigo": e.codigo, "etapa": e.etapa or fase, "detalhe": list(e.detalhe)})
        pedido = (self.ler("pedido") or {}).get("id")
        segredo.log(fase, pedido=pedido, erro=e.codigo, em=e.etapa or fase,
                    **{f"item_{'abcdefgh'[k]}": d for k, d in enumerate(e.detalhe[:8])})


def _saida(**valores: str) -> None:
    """$GITHUB_OUTPUT do passo (só valores fixos: sim/nao, o modo)."""
    destino = os.environ.get("GITHUB_OUTPUT")
    if not destino:
        return
    with open(destino, "a", encoding="utf-8") as f:
        for k, v in valores.items():
            if re.fullmatch(r"[a-z_]{2,20}", k) and re.fullmatch(r"[a-z_]{2,20}", v):
                f.write(f"{k}={v}\n")


def _sha256(arquivo: Path) -> str:
    h = hashlib.sha256()
    with arquivo.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _baixar(conversa: Conversa, pedido: dict, caminho: str, url: str, destino: Path, maximo: int) -> int:
    """Baixa pelo link; se o link falhar (venceu, rede), pede outro (links) e tenta de novo, até 3 vezes."""
    for k in range(3):
        try:
            return conversa.baixar(url, destino, maximo)
        except ErroVideo as e:
            erro = e
        if erro.codigo == "arquivo_grande" or k == 2:
            break
        url = conversa.links(pedido["id"], pedido["tentativa"], ler=[caminho])["ler"][caminho]
    raise erro


# ------------------------------------------------------------------ fases
def pegar(trab: Trabalho) -> int:
    """[chave do robô] O próximo pedido e os clipes. Sem pedido: pedido=nao (os outros passos não rodam)."""
    segredo.etapa("pegar")
    try:
        if trab.pasta.exists() and any(trab.pasta.iterdir()):
            raise ErroVideo("pasta_invalida", "pegar")      # a pasta é só deste pedido: nada de sobra de outra execução
        conversa = Conversa.do_ambiente()
        r = conversa.pegar()
    except ErroVideo as e:
        _saida(pedido="nao", seguir="nao")
        segredo.log("pegar", erro=e.codigo)
        return 1
    if r is None:
        _saida(pedido="nao", seguir="nao")
        segredo.log("pegar", fila="vazia")
        return 0
    pedido = r["pedido"]
    segredo.etapa("pegar", pedido["id"])
    for p in (trab.ent, trab.sai, trab.fala):
        p.mkdir(parents=True, exist_ok=True)
    trab.gravar("pedido", pedido)
    _saida(pedido="sim")                                    # daqui em diante o entregar roda (e manda o código, se falhar)
    try:
        total = 0
        for parte in r["partes"]:
            total += _baixar(conversa, pedido, f"bruto/{pedido['id']}/{parte['n']}", parte["url"], trab.ent / str(parte["n"]),
                             parte["bytes"])
        if pedido["modo"] == "montagem":
            if not r["palavras"]:
                raise ErroVideo("palavras_invalidas", "pegar")
            g = pedido["palavras_tentativa"]
            _baixar(conversa, pedido, f"trabalho/{pedido['id']}/{g}/palavras.json", r["palavras"], trab.fala / "palavras.json", JSON_MAX)
    except ErroVideo as e:
        _saida(seguir="nao")
        trab.falhou(e, "pegar")
        return 0
    _saida(seguir="sim", modo=pedido["modo"])
    segredo.log("pegar", pedido=pedido["id"], modo=pedido["modo"], rodada=pedido["tentativa"], clipes=len(r["partes"]),
                mb=round(total / 1024 / 1024, 1))
    return 0


def preparar(trab: Trabalho) -> int:
    """[sem segredo] Sondagem, áudio de trabalho e pausas; no modo completo, o que o passo da transcrição lê."""
    import audio
    import isolado
    import sondar
    pedido = trab.ler("pedido")
    if pedido is None or trab.erro():
        _saida(transcrever="nao")
        segredo.log("preparar", pulado=True)
        return 0
    segredo.etapa("preparar", pedido["id"])
    try:
        pastas = trab.pastas()
        isolado.preparar(pastas)
        infos = sondar.sondar_todas(pedido["partes"], pastas)
        duracao = audio.extrair(infos, pastas)
        piso = audio.piso_ruido(audio.amostras("/sai/fala48k.wav", pastas))
        silencios = audio.silencios("/sai/fala48k.wav", pastas, audio.limiar_silencio(piso))
    except ErroVideo as e:
        _saida(transcrever="nao")
        trab.falhou(e, "preparar")
        return 0
    # a transcrição lê fora do sai/ (que o ffmpeg alcança): o WAV vai para fala/, com o pedido da transcrição
    os.replace(trab.sai / "fala16k.wav", trab.fala / "fala16k.wav")
    trab.gravar("estado", {"infos": infos, "silencios": silencios, "duracao": duracao, "piso_db": round(piso, 1)})
    if pedido["modo"] == "completo":
        cfg = pedido["config"]
        (trab.fala / "pedido_fala.json").write_text(json.dumps(
            {"pedido": pedido["id"], "glossario": [g for g in cfg.get("glossario") or [] if isinstance(g, str)],
             "fala_roteiro": pedido["fala_roteiro"], "restante_s": pedido["restante_s"]}, ensure_ascii=False), encoding="utf-8")
    _saida(transcrever="sim" if pedido["modo"] == "completo" else "nao")
    resumo = sondar.resumo(infos)
    segredo.log("preparar", pedido=pedido["id"], clipes=resumo["clipes"], duracao=round(duracao, 1), hdr=resumo["hdr"] is not None,
                girado=resumo["girado"], pausas=len(silencios))
    return 0


def _transcricao(trab: Trabalho) -> tuple[dict, bytes]:
    """A transcrição desta rodada (fala/palavras.json, do passo da transcrição ou guardada) ou o código do erro dela."""
    import transcrever
    try:
        dados = (trab.fala / "palavras.json").read_bytes()
    except OSError:
        dados = None
    if dados is None:
        try:
            codigo = (trab.fala / "transcricao_erro.txt").read_text(encoding="utf-8").strip()
        except OSError:
            codigo = ""
        # sem nenhum dos dois, o passo da transcrição não terminou (ou não rodou)
        raise ErroVideo(codigo if segredo.CODIGO.match(codigo) else "erro_interno", "transcrever")
    return transcrever.de_json(dados), dados


def alinhar(trab: Trabalho) -> int:
    """[chave do robô] Guarda a transcrição e conta os segundos (modo completo), alinha, planeja os cortes e manda o parcial."""
    import alinhar as alinhamento
    import cortes
    import relatorio
    pedido, estado = trab.ler("pedido"), trab.ler("estado")
    if pedido is None or trab.erro():
        segredo.log("alinhar", pulado=True)
        return 0
    segredo.etapa("alinhar", pedido["id"])
    vid, t = pedido["id"], pedido["tentativa"]
    try:
        if estado is None:
            raise ErroVideo("erro_interno", "alinhar")
        conversa = Conversa.do_ambiente()
        r, dados = _transcricao(trab)
        guardada = registrada = False
        if pedido["modo"] == "completo":
            # sem guardar, o vídeo segue (o ajuste é que transcreveria de novo); o pedido perdido e a chave recusada param tudo
            caminho, parar = f"trabalho/{vid}/{t}/palavras.json", None
            (trab.fala / "palavras_envio.json").write_bytes(dados)
            try:
                url = conversa.links(vid, t, gravar=[caminho])["gravar"][caminho]
                conversa.subir(url, trab.fala / "palavras_envio.json", "application/json")      # False: já estava lá (a mesma)
                guardada = True
            except ErroVideo as e:
                parar = e if e.codigo in ("pedido_perdido", "robo_chave") else None
            if parar:
                raise parar
            # soma os segundos na cota do mês (o banco, uma vez por rodada: a conversa repete a chamada que falhou no caminho); o áudio
            # já foi para a Azure, conta mesmo sem guardar
            try:
                registrada = conversa.audio(vid, t, r["transcricao"]["segundos_audio"] or 0).get("palavras_guardadas") is True
            except ErroVideo as e:
                parar = e if e.codigo in ("pedido_perdido", "robo_chave") else None
            if parar:
                raise parar
        cfg, ajustes = pedido["config"], pedido["ajustes"]
        al = alinhamento.alinhar(pedido["fala_roteiro"], r["palavras"], r["frases"], cfg, ajustes)
        infos, silencios = estado["infos"], [tuple(s) for s in estado["silencios"]]
        # sem nenhuma palavra (a Azure não ouviu nada), os cortes vêm só dos silêncios (a reserva), e não o erro sem_fala
        plano = cortes.planejar(infos, silencios, cfg, al["palavras"] if r["palavras"] else None, al["remover"],
                                ajustes.get("manter") or [])
        parcial = relatorio.parcial(al, plano, infos, r["transcricao"], pedido["modo"])
        conversa.parcial(vid, t, parcial)
    except ErroVideo as e:
        trab.falhou(e, "alinhar")
        return 0
    trab.gravar("estado", {**estado, "al": al, "plano": plano, "transcricao": r["transcricao"]})
    segredo.log("alinhar", pedido=vid, palavras=len(r["palavras"]), guardada=guardada, registrada=registrada,
                divergencias=len(parcial.get("divergencias") or []), fora=len(parcial.get("fora_do_roteiro") or []),
                cortes=len(plano["cortes"]), sugestoes=len(plano["sugestoes"]), fala_s=round(plano["fala_q"] / 30, 1))
    return 0


def montar(trab: Trabalho) -> int:
    """[sem segredo] Legenda, cartela, montagem, conferência e o relatório final."""
    import cartela
    import conferir
    import cortes
    import legenda
    import montar as montagem
    import relatorio
    pedido, estado = trab.ler("pedido"), trab.ler("estado")
    if pedido is None or trab.erro():
        segredo.log("montar", pulado=True)
        return 0
    segredo.etapa("montar", pedido["id"])
    try:
        if estado is None or "plano" not in estado:
            raise ErroVideo("erro_interno", "montar")
        cfg, ajustes, pastas = pedido["config"], pedido["ajustes"], trab.pastas()
        al, plano, infos = estado["al"], estado["plano"], estado["infos"]
        estilo = ajustes.get("estilo") if ajustes.get("estilo") in legenda.ESTILOS else "normal"
        gancho = None if ajustes.get("sem_gancho") is True else pedido.get("gancho")
        leg = legenda.gravar(trab.sai / "legenda.ass", cortes.no_video(plano, al["legenda"]),
                             [g for g in cfg.get("glossario") or [] if isinstance(g, str)], estilo, gancho or None)
        cartela.desenhar(trab.sai / "cartela.png", pedido["cartela_linhas"], str(cfg.get("cartela_extra") or ""))
        m = montagem.montar(infos, plano, pastas, cfg, preset=PRESET)
        conf = conferir.conferir(pastas, cfg)
        rel = relatorio.final(al, plano, infos, m, conf, leg, estado.get("transcricao"), pedido["modo"], cfg)
        for k in range(1, 5):
            if not (trab.sai / f"q{k}.jpg").is_file():
                raise ErroVideo("conferencia_falhou", "montar", ["quadros"])
    except ErroVideo as e:
        trab.falhou(e, "montar")
        return 0
    video = trab.sai / "reel.mp4"
    trab.gravar("resultado", {"situacao": relatorio.situacao(rel), "relatorio": rel, "sha256": _sha256(video),
                              "bytes": video.stat().st_size, "duracao": conf["duracao_s"]})
    segredo.log("montar", pedido=pedido["id"], **relatorio.resumo_log(rel))
    return 0


def entregar(trab: Trabalho) -> int:
    """[chave do robô] Sobe o vídeo e os quadros e conclui; ou manda o código do que parou antes (falhar)."""
    pedido = trab.ler("pedido")
    if pedido is None:
        segredo.log("entregar", pulado=True)
        return 0
    segredo.etapa("entregar", pedido["id"])
    vid, t = pedido["id"], pedido["tentativa"]
    erro, resultado = trab.erro(), trab.ler("resultado")
    try:
        conversa = Conversa.do_ambiente()
    except ErroVideo as e:
        segredo.log("entregar", pedido=vid, erro=e.codigo)
        return 1
    codigo = None
    if erro:
        codigo = erro["codigo"]
    elif resultado is None:
        # um passo parou sem deixar código: o job foi cancelado (tempo esgotado) ou o runner falhou fora do robô (o Python, a imagem do
        # ffmpeg): "github" volta à fila (até 3 tentativas)
        codigo = "tempo_esgotado" if os.environ.get("RADAR_VIDEO_JOB") == "cancelled" else "github"
    else:
        try:
            r = _entregar(conversa, trab, pedido, resultado)
        except ErroVideo as e:
            codigo = e.codigo
        else:
            segredo.log("entregar", pedido=vid, situacao=r.get("situacao") if isinstance(r.get("situacao"), str) else "?")
            return 0
    if codigo in ("pedido_perdido", "robo_chave"):
        # o pedido já não é deste robô (ou a chave não vale): não há o que registrar; o banco recupera o parado em 20 minutos
        segredo.log("entregar", pedido=vid, erro=codigo)
        return 1 if codigo == "robo_chave" else 0
    try:
        r = conversa.falhar(vid, t, codigo)
    except ErroVideo as e:
        segredo.log("entregar", pedido=vid, erro=codigo, falhar=e.codigo)
        return 0 if e.codigo == "pedido_perdido" else 1
    segredo.log("entregar", pedido=vid, erro=codigo, situacao=r.get("situacao") if isinstance(r.get("situacao"), str) else "?")
    return 0


def _entregar(conversa: Conversa, trab: Trabalho, pedido: dict, resultado: dict) -> dict:
    vid, t = pedido["id"], pedido["tentativa"]
    video, sha = trab.sai / "reel.mp4", str(resultado.get("sha256") or "")
    if not video.is_file() or _sha256(video) != sha or video.stat().st_size != resultado.get("bytes"):
        raise ErroVideo("erro_interno", "entregar")         # o vídeo mudou depois da conferência
    caminho = f"corrigido/{vid}/{sha}.mp4"
    quadros = {f"quadros/{vid}/{sha}/q{k}.jpg": trab.sai / f"q{k}.jpg" for k in range(1, 5)}
    links, recusa = None, None
    try:
        links = conversa.links(vid, t, gravar=[caminho, *quadros])["gravar"]
    except ErroVideo as e:
        recusa = e
    if recusa is not None:
        if recusa.codigo != "ja_existe":
            raise recusa
        # o mesmo vídeo (o mesmo sha256) já subiu numa rodada que parou antes de concluir: sobem só os quadros (o que já estiver lá
        # fica) e o concluir confere o vídeo no armazenamento (tamanho e tipo)
        links = conversa.links(vid, t, gravar=list(quadros))["gravar"]
    if caminho in links:
        conversa.subir(links[caminho], video, "video/mp4")
    for q, arquivo in quadros.items():
        conversa.subir(links[q], arquivo, "image/jpeg")
    return conversa.concluir(vid, t, resultado["situacao"], resultado["relatorio"], sha, resultado["bytes"], resultado["duracao"])


FASES = {"pegar": pegar, "preparar": preparar, "alinhar": alinhar, "montar": montar, "entregar": entregar}


def main(args: list[str]) -> int:
    """python -I robo/video/corrigir.py <fase> <pasta de trabalho>"""
    segredo.instalar_excepthook()
    if len(args) != 2 or args[0] not in FASES:
        segredo.log("corrigir", erro="uso")
        return 2
    try:
        trab = Trabalho(Path(args[1]))
    except ErroVideo as e:
        segredo.log(args[0], erro=e.codigo)
        return 2
    try:
        return FASES[args[0]](trab)
    except Exception:
        # o inesperado: o entregar manda erro_interno; o excepthook imprime só a etapa, o uuid e o nome do tipo
        if args[0] != "entregar" and trab.ler("pedido") is not None and not trab.erro():
            trab.gravar("erro", {"codigo": "erro_interno", "etapa": args[0], "detalhe": []})
        raise


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
