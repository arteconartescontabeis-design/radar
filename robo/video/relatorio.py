"""Radar Artecon — corretor de vídeo (v0.22.0): o relatório (radar_videos.relatorio, versão 2; desenho 4.4).

  * parcial(): logo depois do alinhamento e do plano de cortes, antes da montagem, com `parcial: true` — as divergências, o falado
    fora do roteiro, o que do roteiro não foi dito e os avisos: a equipe sabe se precisa regravar sem esperar o vídeo;
  * final(): tudo, depois da montagem e da conferência — entrada, saída (com o volume e o pico medidos na conferência), cortes e
    sugestões, trocas de grafia, divergências, legenda (com a lista dos blocos para o editor do administrador), avisos, texto final,
    o texto extra da cartela que foi gravado,
    áudio, conferência, quadros e a transcrição (o serviço e os segundos de áudio: a cota do F0 é de 5 h por mês, dividida com a
    Agenda — sem nomes);
  * os tempos (em_s) são os do VÍDEO CORRIGIDO (cortes.remapear), como a tela mostra, e `clipe` é o número da parte enviada;
  * situacao(): "regravar" se sobrou divergência que o administrador não marcou "a transcrição errou"; senão "pronto";
  * caber(): o relatório cabe em radar_videos.relatorio (check length(relatorio::text) <= 60000): as listas longas são resumidas,
    com o aviso `relatorio_resumido` (as divergências ficam sempre);
  * resumo_log(): só contagens e códigos, para o log do GitHub.
O relatório tem a fala e o roteiro: vai só para o banco (RLS de admin e editor), nunca para o log.
v0.33.0 (a aba Vídeo): o final grava também
  * `mapa`: a linha original (os clipes em sequência, em quadros de 1/30 s), a faixa de cada clipe, os cortes automáticos no meio da
    fala (a chave e os quadros que tiram), os trechos DESTE vídeo, o pad e as palavras (ms) — a tela converte o tempo do vídeo em
    quadros da linha original (onde os cortes, o começo, o fim e a capa do editor são gravados) e estima a duração depois de montar; o
    banco também;
  * `unidades`: as unidades da legenda que ficaram, no tempo deste vídeo ({u, t, a, b}: a linha do tempo das palavras do editor);
  * `edicao`: o que o editor pediu e o robô fez (sempre presente: é a marca do robô desta versão, que o banco confere —
    radar_video_concluir recusa o vídeo do robô de antes com mudanças do editor, "robo_desatualizado");
  * `capa`: o quadro da capa ({q, em_ms, movida, sha256}: o sha256 do capa.jpg, que vai no nome do arquivo no armazenamento), quando
    o editor escolheu.
Com os cortes do editor, a divergência cuja fala saiu inteira no corte fica `cortada` (não pede regravar: o trecho não vai ao ar),
o falado fora do roteiro, as trocas de grafia e as sugestões do trecho cortado saem, e o texto final é só o das unidades que ficaram.
Toda divergência com fala leva `ate_s` (o fim dela no vídeo), para o "Cortar este trecho" da aba Vídeo.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone

import cortes
import sondar
from sondar import FPS

ROBO = "0.36.0"
VERSAO = 2
LIMITE = 55000                         # folga sobre os 60000 (o jsonb::text do Postgres separa com ", " e ": ", como o json.dumps)
LISTAS = ("fora_do_roteiro", "omitido", "trocas", "sugestoes", "cortes")
SERVICO = re.compile(r"^[a-z0-9_]{3,40}$")


def _agora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _em(plano: dict, t: float) -> float:
    return round(cortes.remapear(plano, float(t))[0], 2)


def _clipe(infos: list[dict], t: float) -> int | None:
    q = float(t) * FPS
    for i in infos:
        if i["inicio_q"] <= q < i["inicio_q"] + i["quadros"]:
            return i["n"]
    return infos[-1]["n"] if infos else None


def _num(v, casas: int = 1) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, casas) if math.isfinite(x) else None


def _transcricao(t: dict | None) -> dict:
    """{servico, segundos_audio, palavras}: o código do serviço (azure_f0, azure_rapido) e quanto áudio foi transcrito."""
    t = t if isinstance(t, dict) else {}
    servico = t.get("servico")
    return {"servico": servico if isinstance(servico, str) and SERVICO.match(servico) else None,
            "segundos_audio": _num(t.get("segundos_audio")), "palavras": int(_num(t.get("palavras"), 0) or 0)}


def _cortado(plano: dict, t0: float, t1: float | None = None) -> bool:
    """O trecho [t0, t1] (linha de fala48k.wav; sem t1, o quadro de t0) saiu inteiro pelo editor (cortes, começo ou fim marcados)?"""
    q0 = cortes._q_ini(float(t0))
    return cortes._tirado_pelo_editor(plano.get("edicao"), q0, max(cortes._q_fim(float(t1)) if t1 is not None else 0, q0 + 1))


def _divergencias(al: dict, plano: dict, infos: list[dict]) -> list[dict]:
    """As divergências no tempo do vídeo corrigido; a que tem fala ganha o fim dela no vídeo (ate_s) ou, se a fala saiu inteira num
    corte do editor, fica `cortada` e não pede regravar. A de omissão (o número do roteiro que não foi dito) não se corta."""
    out = []
    for d in al.get("divergencias") or []:
        x = {**{k: v for k, v in d.items() if k not in ("t", "t_fim")}, "em_s": _em(plano, d["t"]), "clipe": _clipe(infos, d["t"])}
        fim = d.get("t_fim")
        if isinstance(fim, (int, float)) and fim > d["t"]:
            if plano.get("edicao") and _cortado(plano, d["t"], fim):
                x.update(cortada=True, regravar=False)
            else:
                x["ate_s"] = _em(plano, fim)
        out.append(x)
    return out


def _saiu(plano: dict, t0: float, t1: float | None = None) -> bool:
    """O trecho [t0, t1] (linha de fala48k.wav) não está mais no vídeo (saiu por QUALQUER corte: automático ou do editor)?"""
    q0 = cortes._q_ini(float(t0))
    q1 = max(cortes._q_fim(float(t1)) if t1 is not None else 0, q0 + 1)
    return not any(qa < q1 and qb > q0 for qa, qb in plano.get("trechos") or [])


def _no_video(al: dict, plano: dict, infos: list[dict]) -> dict:
    """As listas do alinhamento com os tempos do vídeo corrigido (em_s) e o clipe. v0.33.0: sem o que saiu num corte (a muleta e a
    repetição cortadas por padrão não aparecem mais como "falado fora do roteiro": não vão ao ar); o fora do roteiro que ficou leva
    `ate_s` (o fim no vídeo), para o "Cortar este trecho" da aba Vídeo."""
    def conv(x):
        y = {**{k: v for k, v in x.items() if k not in ("t", "t_fim")}, "em_s": _em(plano, x["t"]), "clipe": _clipe(infos, x["t"])}
        fim = x.get("t_fim")
        if isinstance(fim, (int, float)) and fim > x["t"]:
            y["ate_s"] = _em(plano, fim)
        return y
    fora = lambda x: _saiu(plano, x["t"], x.get("t_fim"))
    return {"trocas": [conv(x) for x in al.get("trocas") or [] if not fora(x)], "divergencias": _divergencias(al, plano, infos),
            "fora_do_roteiro": [conv(x) for x in al.get("fora_do_roteiro") or [] if not fora(x)],
            "omitido": [conv(x) for x in al.get("omitido") or []]}


def _mapa(plano: dict) -> dict:
    """O mapa do vídeo (v0.33.0), para a tela e o banco: a linha original, as faixas, os automáticos, os trechos deste vídeo, o pad e
    as palavras ([ini, fim] em ms da linha original: a estimativa do pad do fim depois de cortar, cortes.estimada_q)."""
    return {"fps": FPS, "linha_q": int(plano.get("linha_q") or 0), "faixas": [list(f) for f in plano.get("faixas") or []],
            "automaticos": [dict(a) for a in plano.get("automaticos") or []], "trechos": [list(t) for t in plano.get("trechos") or []],
            "pad_q": int(plano.get("pad_q") or 0), "palavras": [[int(a), int(b)] for a, b in plano.get("palavras") or []]}


def _edicao(plano: dict, leg: dict, cartela_propria: bool) -> dict:
    """O que o editor pediu e o robô fez (sempre presente no robô desta versão)."""
    ed = plano.get("edicao") or {}
    faixas = plano.get("faixas") or []
    ini, fim = ed.get("inicio_q"), ed.get("fim_q")
    antes = sum(max(0, min(f1, ini) - f0) for f0, f1 in faixas) if ini is not None else 0
    depois = sum(max(0, f1 - max(f0, fim)) for f0, f1 in faixas) if fim is not None else 0
    return {"versao": 1, "cortes": sum(1 for c in plano.get("cortes") or [] if c.get("tipo") == "editor"),
            "inicio_cortado_s": round(antes / FPS, 2), "fim_cortado_s": round(depois / FPS, 2),
            "tamanho": leg.get("tamanho", "M"), "posicao": leg.get("posicao", "baixo"), "cor": leg.get("cor", "marinho"),
            "cartela_extra_propria": bool(cartela_propria)}


def parcial(al: dict, plano: dict, infos: list[dict], transcricao: dict | None = None, modo: str = "completo") -> dict:
    """O relatório parcial (radar_video_parcial), antes da montagem."""
    rel = {"versao": VERSAO, "robo": ROBO, "modo": modo, "parcial": True, "gerado_em": _agora(),
           **{k: v for k, v in _no_video(al, plano, infos).items() if k != "trocas"},
           "avisos": sorted(set(al.get("avisos") or [])), "transcricao": _transcricao(transcricao)}
    return caber(rel)


def final(al: dict, plano: dict, infos: list[dict], montagem: dict, conferencia: dict, legenda_info: dict,
          transcricao: dict | None = None, modo: str = "completo", cfg: dict | None = None, cartela_propria: bool = False) -> dict:
    """O relatório final (radar_video_concluir). montagem: montar.montar (com a capa, se o editor escolheu); conferencia:
    conferir.conferir; legenda_info: legenda.gravar (com a lista dos blocos e a aparência); cfg: as Configurações do pedido, com o
    texto extra da cartela que foi gravado; cartela_propria: o texto extra é o deste vídeo (o editor), e não o das Configurações."""
    cfg = cfg or {}
    saida = dict(montagem.get("saida") or {})
    for k in ("lufs", "pico_dbtp"):                      # medidos na conferência, sobre o arquivo final
        if conferencia.get(k) is not None:
            saida[k] = conferencia[k]
    leg = legenda_info or {}
    avisos = set(al.get("avisos") or []) | set(leg.get("avisos") or [])
    if (saida.get("duracao_s") or 0) > float(cfg.get("duracao_max_s", 90)):
        avisos.add("duracao_acima_do_limite")             # v0.33.0: só aviso (a meta; a aprovação pede confirmação, nada é bloqueado)
    listas = _no_video(al, plano, infos)
    unidades = cortes.no_video(plano, al.get("legenda") or [])
    capa = montagem.get("capa") if isinstance(montagem.get("capa"), dict) else None
    if capa and capa.get("movida"):
        avisos.add("capa_movida")
    # o texto que vai ao ar é só o das unidades que ficaram no vídeo (o banco confere este: boletim pago, termos, nomes) — v0.33.0:
    # sempre (a muleta e a repetição cortadas por padrão também saem dele), e não só com os cortes do editor
    texto_final = " ".join(u["texto"] for u in unidades)
    rel = {"versao": VERSAO, "robo": ROBO, "modo": modo, "parcial": False, "gerado_em": _agora(),
           "entrada": sondar.resumo(infos), "saida": saida, "cortes": plano.get("cortes") or [],
           "sugestoes": plano.get("sugestoes") or [], **listas,
           "legenda": {"blocos": leg.get("blocos", 0), "estilo": leg.get("estilo", "normal"), "gancho": bool(leg.get("gancho")),
                       **(al.get("legenda_ajustes") or {"editados": 0, "recusados": []}), "lista": leg.get("lista") or []},
           "avisos": sorted(avisos), "texto_final": texto_final, "cobertura": al.get("cobertura"),
           # o texto extra da cartela que foi gravado (Configurações → Corretor de vídeo, lido nesta montagem): o banco confere este, e
           # não o das Configurações de hoje, e pede a cartela refeita se ele mudar depois (radar_video_pendencia)
           "cartela_extra": str(cfg.get("cartela_extra") or "")[:120],
           "audio": montagem.get("audio") or {}, "imagem": montagem.get("imagem") or {}, "conferencia": conferencia,
           "quadros_ms": montagem.get("quadros_ms") or [], "transcricao": _transcricao(transcricao),
           # v0.33.0: a aba Vídeo
           "mapa": _mapa(plano), "unidades": [{"u": u.get("u"), "t": u["texto"], "a": round(u["ini"], 2), "b": round(u["fim"], 2)} for u in unidades],
           "edicao": _edicao(plano, leg, cartela_propria),
           **({"capa": {"q": int(capa["q"]), "em_ms": int(capa["em_ms"]), "movida": bool(capa.get("movida")),
                        **({"sha256": str(capa["sha256"])} if capa.get("sha256") else {})}} if capa else {})}
    return caber(rel)


def situacao(rel: dict) -> str:
    """"regravar" se há divergência (número, prazo ou termo) que o administrador não marcou "a transcrição errou"."""
    return "regravar" if any(d.get("regravar") and not d.get("transcricao_errou") for d in rel.get("divergencias") or []) else "pronto"


def _tam(rel: dict) -> int:
    return len(json.dumps(rel, ensure_ascii=False))


def _resumir(rel: dict, passo: int) -> None:
    if passo < 3:                                       # as listas longas: 100, 20 e 5 itens
        for k in LISTAS:
            if isinstance(rel.get(k), list):
                rel[k] = rel[k][:(100, 20, 5)[passo]]
    elif passo == 3:                                    # v0.33.0: as unidades da legenda (sem elas, a aba Vídeo corta pelo tempo)
        rel.pop("unidades", None)
    elif passo == 4 and isinstance(rel.get("legenda"), dict):
        rel["legenda"].pop("lista", None)
    elif passo == 5:                                    # as divergências ficam (são o que pede a regravação), com texto curto
        rel["divergencias"] = [{**d, "falado": str(d.get("falado") or "")[:40], "roteiro": str(d.get("roteiro") or "")[:40]}
                               for d in (rel.get("divergencias") or [])[:50]]
    elif passo == 6:
        rel["texto_final"] = str(rel.get("texto_final") or "")[:20000]


def caber(rel: dict) -> dict:
    """O relatório em tipos do JSON e dentro do limite da coluna: corta as listas longas, depois as unidades da legenda, a lista dos
    blocos, os textos das divergências e, por último, o texto final; o aviso relatorio_resumido diz que algo ficou de fora. O mapa
    nunca sai (é pequeno, e sem ele a aba Vídeo não corta)."""
    rel = json.loads(json.dumps(rel, ensure_ascii=False, default=str))
    passo = 0
    while _tam(rel) > LIMITE and passo < 7:
        _resumir(rel, passo)
        rel["avisos"] = sorted(set(rel.get("avisos") or []) | {"relatorio_resumido"})
        passo += 1
    return rel


def resumo_log(rel: dict) -> dict:
    """Só números e sim/não, para segredo.log (nunca a fala, o roteiro ou um nome)."""
    ds = rel.get("divergencias") or []
    return {"cortes": len(rel.get("cortes") or []), "sugestoes": len(rel.get("sugestoes") or []), "divergencias": len(ds),
            "regravar": situacao(rel) == "regravar", "fora": len(rel.get("fora_do_roteiro") or []),
            "omitido": len(rel.get("omitido") or []), "blocos": int((rel.get("legenda") or {}).get("blocos") or 0),
            "duracao": float((rel.get("saida") or {}).get("duracao_s") or 0.0), "cobertura": float(rel.get("cobertura") or 0.0)}
