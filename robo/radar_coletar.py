"""Radar Artecon — robô de coleta das fontes oficiais.

Uso:
    python radar_coletar.py                 # todas as fontes ativas, respeitando a frequência
    python radar_coletar.py --fonte pgfn-noticias --forcar

Variáveis de ambiente: SUPABASE_URL e SUPABASE_SERVICE_KEY (chave service_role).

Regras:
  * cada fonte roda isolada — a falha de uma não interrompe as outras;
  * falha de download ou página sem nenhum item reconhecido NUNCA vira
    "sem novidades": fica registrada como 'falha' ou 'vazio_suspeito';
  * o texto de cada item é guardado com hash; se o texto mudar numa nova
    visita, o banco preserva a versão anterior.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
import traceback
from datetime import date, datetime, timedelta, timezone

import requests

from radar_banco import Banco, ErroBanco
import radar_ia
from radar_coletores import Item, data_no_texto, listar_paginas
from radar_util import (VERSAO, ErroDownload, agora_iso, baixar, extrair_texto,
                        hash_conteudo, hash_titulo)


def _instante(valor: str | None) -> datetime | None:
    if not valor:
        return None
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def fonte_esta_na_hora(fonte: dict, agora: datetime) -> bool:
    ultimo = _instante(fonte.get("ultimo_sucesso_em"))
    if ultimo is None:
        return True
    # tolerância de 1h para o atraso natural do agendador
    return agora - ultimo >= timedelta(hours=int(fonte["frequencia_horas"]) - 1)


def deve_revisitar(existente: dict, config: dict, agora: datetime) -> bool:
    """Itens recentes são relidos (no máximo 1x por dia) para detectar alteração.
    Item cujo texto ainda não foi obtido é tentado a cada execução — mas só
    enquanto for recente (um link para PDF não fica sendo relido para sempre)."""
    capturado = _instante(existente.get("capturado_em")) or agora
    verificado = _instante(existente.get("verificado_em")) or capturado
    dentro = agora - capturado <= timedelta(days=int(config.get("revisitar_dias", 7)))
    if not existente.get("hash_conteudo"):
        return dentro
    return dentro and agora - verificado >= timedelta(hours=20)


def obter_texto(item: Item, config: dict, sessao: requests.Session) -> tuple[str | None, str | None]:
    if config.get("sem_pagina_de_texto"):
        # a fonte não oferece o texto integral por endereço direto: guarda-se o que a
        # listagem oficial traz (ementa) e isso fica anotado na captura
        return (item.texto_da_listagem, None) if item.texto_da_listagem else (None, "a listagem não trouxe ementa")
    try:
        _, html = baixar(item.url_texto or item.url, sessao, tentativas=2)
    except ErroDownload as e:
        return None, str(e)
    texto = extrair_texto(html, config.get("seletor_texto"))
    if len(texto) < int(config.get("texto_minimo", 80)):
        return None, f"texto curto demais ({len(texto)} caracteres)"
    return texto, None


TEMPO_MAX_PADRAO = 300     # segundos por fonte; ajustável em config.tempo_max_segundos


class TempoEsgotado(BaseException):
    """A fonte passou do tempo máximo (padrão de links mal escrito, site lento demais...).
    BaseException: nenhum "except Exception" pelo caminho (requests, leitura das páginas) a engole."""


class limite_de_tempo:
    """Interrompe o bloco depois de `segundos` (só no Linux/macOS e na thread principal;
    fora disso, roda sem limite). Interrompe até uma expressão regular que não termina."""

    def __init__(self, segundos: float):
        self.segundos = segundos
        self.ativo = (segundos > 0 and hasattr(signal, "SIGALRM")
                      and threading.current_thread() is threading.main_thread())

    def _estourou(self, *_):
        raise TempoEsgotado(f"a fonte passou de {self.segundos:g} s e foi interrompida")

    def __enter__(self):
        if self.ativo:
            self.anterior = signal.signal(signal.SIGALRM, self._estourou)
            signal.setitimer(signal.ITIMER_REAL, self.segundos)
        return self

    def __exit__(self, *_):
        if self.ativo:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self.anterior)
        return False


def tempo_maximo(config: dict) -> float:
    try:
        valor = float(config.get("tempo_max_segundos", TEMPO_MAX_PADRAO))
    except (TypeError, ValueError):
        return TEMPO_MAX_PADRAO
    return valor if 0 < valor <= 3600 else TEMPO_MAX_PADRAO


def coletar_fonte(banco: Banco, fonte: dict, sessao: requests.Session,
                  hoje: date | None = None, pausa: float = 1.0) -> dict:
    config = fonte.get("config") or {}
    agora = datetime.now(timezone.utc)
    resultado = {"fonte": fonte["slug"], "status": "falha", "encontrados": 0, "novos": 0,
                 "atualizados": 0, "sem_texto": 0, "com_erro": 0, "erro": None}
    execucao = banco.abrir_execucao(fonte["id"])      # se nem isto funcionar, o banco está fora: aborta
    http = None
    try:
        with limite_de_tempo(tempo_maximo(config)):
            listagem, http = listar_paginas(lambda url: baixar(url, sessao), fonte, hoje)
            resultado["encontrados"] = len(listagem.itens)

            if listagem.brutos == 0:
                resultado["status"] = "vazio_suspeito"
                resultado["erro"] = ("a página respondeu, mas nenhum item foi reconhecido — "
                                     "possível mudança de layout; revisar a configuração da fonte")
            else:
                existentes = banco.capturas_da_fonte(fonte["id"])
                ja_rendeu_texto = any(e.get("hash_conteudo") for e in existentes.values())
                novos_tentados = novos_sem_texto = textos_obtidos = 0
                for item in listagem.itens:
                    existente = existentes.get(item.url)
                    if existente and not deve_revisitar(existente, config, agora):
                        continue
                    texto, erro_texto = obter_texto(item, config, sessao)
                    if not config.get("sem_pagina_de_texto"):
                        time.sleep(pausa)                          # gentileza com o site (só quando houve pedido)
                    if item.data is None and texto and config.get("data_do_texto"):
                        item.data, na_janela = data_no_texto(texto, config, hoje)    # a listagem não traz data
                        if not na_janela and existente is None:
                            continue                               # notícia antiga: fica fora, como as demais
                    if existente is None:
                        novos_tentados += 1
                        novos_sem_texto += 0 if texto else 1
                    textos_obtidos += 1 if texto else 0
                    h_conteudo = hash_conteudo(texto) if texto else None
                    metadados = dict(item.metadados)
                    if config.get("sem_pagina_de_texto") and texto:
                        metadados["texto_parcial"] = True          # só a ementa; o texto integral está na fonte
                    if erro_texto:
                        metadados["erro_texto"] = erro_texto
                        resultado["sem_texto"] += 1
                    try:
                        if existente is None:
                            h_titulo = hash_titulo(item.titulo)
                            gravada = banco.gravar_captura({
                                "fonte_id": fonte["id"], "url": item.url, "titulo": item.titulo,
                                "data_publicacao": item.data.isoformat() if item.data else None,
                                "resumo_fonte": item.resumo, "texto": texto, "hash_titulo": h_titulo,
                                "duplicata_de": banco.buscar_duplicata(fonte["id"], h_titulo, h_conteudo),
                                "metadados": metadados, "verificado_em": agora_iso(),
                            })
                            if gravada is not None:
                                resultado["novos"] += 1
                        elif texto and h_conteudo != existente.get("hash_conteudo"):
                            eh_alteracao = bool(existente.get("hash_conteudo"))
                            banco.atualizar_captura(existente["id"], {
                                "titulo": item.titulo, "texto": texto,
                                "metadados": metadados, "verificado_em": agora_iso()})
                            if eh_alteracao:
                                resultado["atualizados"] += 1
                        elif texto:
                            banco.atualizar_captura(existente["id"], {"verificado_em": agora_iso()})
                        # sem texto: não marca como verificado — a conferência não aconteceu
                    except ErroBanco as e:
                        # um item recusado pelo banco não derruba os demais nem as outras fontes
                        resultado["com_erro"] += 1
                        resultado["erro"] = resultado["erro"] or f"item '{item.titulo[:60]}': {e}"

                if listagem.incompleta:
                    resultado["status"] = "parcial"
                    resultado["erro"] = resultado["erro"] or listagem.incompleta
                elif resultado["com_erro"]:
                    resultado["status"] = "parcial"
                elif resultado["sem_texto"] and textos_obtidos == 0 and (
                        (novos_tentados and novos_sem_texto == novos_tentados) or not ja_rendeu_texto):
                    # nenhum item NOVO veio com texto, ou a fonte nunca entregou texto algum.
                    # (Um item isolado sem texto — ex.: link para PDF — não derruba a fonte.)
                    resultado["status"] = "parcial"
                    resultado["erro"] = ("a lista foi lida, mas nenhum item trouxe ementa" if config.get("sem_pagina_de_texto") else
                                         "a lista foi lida, mas o texto de nenhum item pôde ser obtido — "
                                         "revisar 'seletor_texto'/'url_texto' da fonte ou bloqueio do site")
                else:
                    resultado["status"] = "ok"
    except TempoEsgotado as e:
        # o que já foi gravado fica; a fonte é marcada para revisão
        resultado["status"] = "parcial" if resultado["novos"] or resultado["atualizados"] else "falha"
        resultado["erro"] = f"{e} — revisar o padrão de links da fonte ou a lentidão do site"
    except ErroDownload as e:
        http = e.http_status or http
        resultado["erro"] = str(e)
    except ErroBanco as e:
        resultado["erro"] = str(e)
    except Exception as e:  # erro de leitura da página: registra e segue para a próxima fonte
        resultado["erro"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        try:
            banco.fechar_execucao(execucao, status=resultado["status"], http_status=http,
                                  itens_encontrados=resultado["encontrados"],
                                  itens_novos=resultado["novos"],
                                  itens_atualizados=resultado["atualizados"],
                                  itens_sem_texto=resultado["sem_texto"],
                                  itens_com_erro=resultado["com_erro"],
                                  erro=resultado["erro"])
        except ErroBanco as e:
            print(f"  ! não foi possível fechar a execução {execucao}: {e}", file=sys.stderr)
    return resultado


def resumo_markdown(resultados: list[dict], pulados: list[str]) -> str:
    linhas = [f"## Radar Artecon — coleta v{VERSAO}", "",
              "| Fonte | Situação | Na janela | Novos | Alterados | Sem texto | Com erro | Observação |",
              "|---|---|---:|---:|---:|---:|---:|---|"]
    for r in resultados:
        linhas.append(f"| {r['fonte']} | {r['status']} | {r['encontrados']} | {r['novos']} | "
                      f"{r['atualizados']} | {r['sem_texto']} | {r['com_erro']} | {(r['erro'] or '')[:160]} |")
    if pulados:
        linhas += ["", "Fora do horário (frequência ainda não venceu): " + ", ".join(pulados)]
    return "\n".join(linhas)


def executar(banco: Banco, slug: str | None = None, forcar: bool = False,
             hoje: date | None = None, pausa: float = 1.0) -> tuple[list[dict], list[str]]:
    orfas = banco.encerrar_execucoes_orfas()
    if orfas:
        print(f"! {orfas} execução(ões) anterior(es) ficou(aram) sem terminar e foi(ram) marcada(s) como falha")
    fontes = banco.fontes_ativas(slug)
    if slug and not fontes:
        raise SystemExit(f"fonte '{slug}' não existe ou está inativa")
    agora = datetime.now(timezone.utc)
    sessao = requests.Session()
    resultados, pulados = [], []
    for fonte in fontes:
        if not forcar and not fonte_esta_na_hora(fonte, agora):
            pulados.append(fonte["slug"])
            continue
        print(f"→ {fonte['slug']}")
        r = coletar_fonte(banco, fonte, sessao, hoje, pausa)
        print(f"  {r['status']}: {r['encontrados']} na janela, {r['novos']} novos, "
              f"{r['atualizados']} alterados" + (f" — {r['erro']}" if r["erro"] else ""))
        resultados.append(r)
    return resultados, pulados


def avaliar_com_ia(banco: Banco, sem_ia: bool = False) -> dict:
    """Nota da IA para as capturas novas. Nunca derruba a coleta: qualquer problema vira aviso no resumo."""
    token = os.environ.get("RADAR_IA_GATEWAY_TOKEN", "").strip()
    if sem_ia:
        return {"pulado": "opção --sem-ia."}
    if not token:
        return {"pulado": "falta o segredo RADAR_IA_GATEWAY_TOKEN no GitHub (token do Radar na IA Central)."}
    try:
        r = radar_ia.avaliar_capturas(banco, token, os.environ.get("IA_GATEWAY_URL") or radar_ia.GATEWAY_PADRAO,
                                      os.environ.get("RADAR_IA_MODELO_RAPIDO") or radar_ia.MODELO_PADRAO)
    except Exception as e:                      # noqa: BLE001 — a avaliação é um extra da coleta
        return {"pulado": radar_ia._sem_segredo(f"erro inesperado ({type(e).__name__}: {str(e)[:200]}).", token)}
    print(f"IA: {r['avaliadas']} de {r['pendentes']} avaliada(s), {r['repetidas']} repetição(ões)" + (f" — {r['erro']}" if r["erro"] else ""))
    return r


def limpar_imagens(banco: Banco) -> str:
    """Faxina das imagens sem uso; é um extra da coleta: banco antigo ou erro não derrubam nada."""
    try:
        n = banco.limpar_imagens_sem_uso()
    except ErroBanco as e:
        if "radar_limpar_imagens_sem_uso" in str(e):
            return ""                                   # banco ainda sem o SQL da v0.7.1
        return f"\n\n_Limpeza de imagens sem uso não foi feita: {str(e)[:200]}_"
    return f"\n\n_Imagens sem uso apagadas: {n}._" if n else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Radar Artecon — coleta das fontes oficiais")
    ap.add_argument("--fonte", help="slug de uma única fonte")
    ap.add_argument("--forcar", action="store_true", help="ignora a frequência configurada")
    ap.add_argument("--sem-ia", action="store_true", help="não pede à IA a nota das capturas novas")
    args = ap.parse_args(argv)

    print(f"Radar Artecon — robô de coleta v{VERSAO}")
    try:
        banco = Banco(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", ""))
        resultados, pulados = executar(banco, args.fonte, args.forcar)
    except ErroBanco as e:
        print(f"ERRO DE BANCO: {e}", file=sys.stderr)
        return 2

    texto = resumo_markdown(resultados, pulados)
    texto += radar_ia.resumo_markdown(avaliar_com_ia(banco, args.sem_ia))
    texto += limpar_imagens(banco)
    print("\n" + texto)
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(texto + "\n")

    if resultados and all(r["status"] != "ok" for r in resultados):
        return 1   # nenhuma fonte funcionou: o workflow fica vermelho
    return 0


if __name__ == "__main__":
    sys.exit(main())
