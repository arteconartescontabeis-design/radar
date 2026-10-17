"""Radar Artecon — lembretes por e-mail ANTES do dia (v0.29.0).

Hoje o Radar avisa depois que algo falha (a Pauta "não saiu", a fonte parada). Os lembretes avisam antes:

- a peça da Pauta de amanhã (e a de hoje que ainda não saiu) que não está aprovada, na véspera, a partir de um horário;
- a peça pronta que espera a aprovação do administrador há mais de N horas;
- o vídeo do reel que o corretor terminou (pronto para conferir, precisa regravar ou parou);
- a notícia que não saiu: o envio ao site ou às redes com erro, ou a autorização parada há mais de X horas.

Quem decide o que lembrar e quando é o BANCO (radar_lembretes_lote: Configurações → Lembretes por e-mail, o horário, no máximo um
e-mail por tipo por dia e cada pendência uma vez só; a pendência "fecha" sozinha quando é resolvida). Este robô só escreve: como os
outros avisos do Radar, o e-mail é a notificação que o GitHub manda quando o robô (github-actions[bot]) abre um aviso (issue) ou
comenta nele. Um aviso fixo por tipo ("Radar: lembrete — …"): o primeiro lembrete abre o aviso; os seguintes chegam como um comentário
nele (um e-mail). O robô nunca fecha nem edita o aviso (cada mudança mandaria mais um e-mail).

O repositório é público: o texto leva só a data, a hora, o formato, a situação, o canal e os números (da peça ou do envio). Nunca o
assunto, o nome de quem aparece, a legenda, o texto do erro ou do boletim pago — o banco nem entrega isso ao robô. Nada é publicado por
aqui.

Se o robô cair depois de comentar e antes de confirmar, o mesmo lote volta na rodada seguinte ("retomado"): a marca escondida no fim
do comentário (<!-- radar-lembrete: lote … itens … -->) mostra que ele já saiu, e o robô só confirma, sem repetir o e-mail.

Uso (no workflow radar-lembretes.yml, acionado pela agenda do banco ou na rodada de hora em hora):
    python radar_lembretes.py
Variáveis: SUPABASE_URL, SUPABASE_SERVICE_KEY, GITHUB_TOKEN e GITHUB_REPOSITORY (o Actions preenche as duas últimas). Sem elas, não
faz nada. Nunca fica vermelho: o erro vai só para o registro (sem segredo) e a próxima rodada tenta de novo.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime

import requests

from radar_alertas import FUSO, GitHub
from radar_banco import Banco, ErroBanco

PREFIXO_LEMBRETE = "Radar: lembrete — "
TITULOS = {"pauta": PREFIXO_LEMBRETE + "Pauta de amanhã sem aprovação",
           "aprovacao": PREFIXO_LEMBRETE + "peça pronta esperando aprovação",
           "video": PREFIXO_LEMBRETE + "vídeo do reel para conferir",
           "noticia": PREFIXO_LEMBRETE + "notícia que não saiu"}
ABERTURA = ("Este aviso fica aberto: é aqui que o Radar deixa os lembretes deste tipo. Cada lembrete novo chega como um comentário "
            "(um e-mail), no máximo um por dia. Não precisa fechar; se fechar, o próximo lembrete abre outro.")
RODAPE = ("Cada pendência é lembrada uma vez só. Horário e liga/desliga: Radar → Configurações → Lembretes por e-mail (só o "
          "administrador). Nada é publicado por este lembrete.")
MAX_ITENS = 15
MARCA = re.compile(r"<!-- radar-lembrete: lote ([0-9a-f-]{36}) itens ([0-9 ]+) -->")
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
FORMATOS = {"imagem": "Imagem 4:5", "foto": "Foto", "carrossel": "Carrossel", "carrossel_fotos": "Carrossel de fotos", "reel": "Reel",
            "story": "Story"}
CANAIS = {"site": "Site", "instagram": "Instagram", "facebook": "Facebook"}
FALTA_PAUTA = {
    "planejada": "planejada, ainda não começou. Falta preparar, clicar em “Salvar e marcar como pronta” e o administrador aprovar.",
    "em_producao": "em produção. Falta terminar, clicar em “Salvar e marcar como pronta” e o administrador aprovar.",
    "pronta": "pronta. Falta o administrador conferir e aprovar.",
    "aprovada_manual": ("aprovada para publicar à mão e ainda sem o link registrado. Depois de postar no Instagram e no Facebook, use "
                        "“Registrar a publicação” na peça."),
}
VIDEO = {  # os rótulos do quadro do vídeo na tela (radar-video.js), com o que fazer
    "pronto": "Vídeo corrigido pronto. Veja a prévia e o relatório; conferido, o administrador aprova a peça.",
    "regravar": "Precisa regravar. O relatório mostra o bloco a regravar; os outros clipes vão de novo como estão.",
    "erro": "O corretor parou. O motivo e o que fazer estão no quadro do vídeo.",
}


def _dia(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def _quando(valor) -> datetime | None:
    """Data e hora de Brasília de um timestamptz do banco (None se vazio ou ilegível)."""
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).astimezone(FUSO) if valor else None
    except (TypeError, ValueError):
        return None


def _dm(d: date | None) -> str:
    return f"{d:%d/%m}" if d else "—"


def _dia_semana(d: date | None, maiuscula: bool = False) -> str:
    if not d:
        return "—"
    nome = DIAS[d.weekday()]
    return (nome[0].upper() + nome[1:] if maiuscula else nome) + f", {d:%d/%m}"


def _hora(h: datetime | None) -> str:
    return f"{h:%d/%m} às {h:%H:%M}" if h else "—"


def _formato(f) -> str:
    return FORMATOS.get(str(f or ""), str(f or "—"))


def _horas(n) -> str:
    n = int(n or 0)
    return f"{n} hora" if n == 1 else f"{n} horas"


def _cabecalho_pauta(itens: list[dict]) -> str:
    if len(itens) == 1:
        i, d = itens[0], _dia(itens[0].get("data"))
        if i.get("quando") == "amanha":
            return f"**A peça da Pauta de amanhã ({_dia_semana(d)}) ainda não está aprovada.**"
        return f"**A peça da Pauta de hoje ({_dia_semana(d)}) ainda não saiu.**"
    quando = {i.get("quando") for i in itens}
    if quando == {"amanha", "hoje"} and len(itens) == 2:
        return "**A Pauta tem 2 peças pendentes: a de amanhã e a de hoje.**"
    return f"**A Pauta tem {len(itens)} peças pendentes.**"


def _linha(tipo: str, i: dict, horas) -> str:
    n = i.get("n")
    if tipo == "pauta":
        d = _dia(i.get("data"))
        falta = FALTA_PAUTA.get(str(i.get("situacao")), "ainda não está aprovada.")
        return (f"- {'Amanhã' if i.get('quando') == 'amanha' else 'Hoje'}, {_dm(d)} às {i.get('hora') or '—'} — "
                f"{_formato(i.get('formato'))} (peça nº {n}): {falta}")
    if tipo == "aprovacao":
        return (f"- {_dia_semana(_dia(i.get('data')), maiuscula=True)} — {_formato(i.get('formato'))} (peça nº {n}): pronta desde "
                f"{_hora(_quando(i.get('desde')))}.")
    if tipo == "video":
        return (f"- Reel de {_dia_semana(_dia(i.get('data')))} (peça nº {n}): "
                f"{VIDEO.get(str(i.get('situacao')), 'o corretor terminou.')}")
    canal = CANAIS.get(str(i.get("canal")), str(i.get("canal") or "—"))
    if i.get("situacao") == "erro":
        estado = "o envio deu erro"
    elif i.get("canal") == "site":
        estado = f"parada há mais de {_horas(horas)}, esperando o robô do site"
    else:
        estado = f"parada há mais de {_horas(horas)}, sem sair"
    return f"- {canal}, autorizada em {_hora(_quando(i.get('desde')))}: {estado} (envio nº {n})."


def corpo(tipo: str, grupo: dict) -> str:
    """O texto do lembrete de um tipo (o comentário, ou o corpo do aviso depois da ABERTURA). Só datas, horas, formatos, situações,
    canais e números; no fim, o rodapé e a marca escondida com o lote e os números internos das pendências (para retomar sem repetir)."""
    itens, horas = list(grupo.get("itens") or []), grupo.get("horas")
    n = len(itens)
    if tipo == "pauta":
        abre = _cabecalho_pauta(itens)
        fazer = ("O que fazer: abra o Radar → **Pauta**, vá à semana da peça e clique em **Abrir**. A peça só sai depois da aprovação "
                 "do administrador.")
    elif tipo == "aprovacao":
        abre = (f"**1 peça da Pauta está pronta esperando a aprovação do administrador há mais de {_horas(horas)}.**" if n == 1 else
                f"**{n} peças da Pauta estão prontas esperando a aprovação do administrador há mais de {_horas(horas)}.**")
        fazer = ("O que fazer: o administrador abre o Radar → **Pauta**, abre a peça, confere e clica em **Aprovar**. Se precisar mudar "
                 "algo, quem edita a peça a devolve para a produção.")
    elif tipo == "video":
        abre = ("**O corretor de vídeo terminou 1 reel que ainda não foi aprovado.**" if n == 1 else
                f"**O corretor de vídeo terminou {n} reels que ainda não foram aprovados.**")
        fazer = "O que fazer: abra o Radar → **Pauta** → a peça do reel → quadro **Corretor de vídeo**."
    else:
        abre = "**1 publicação de notícia não saiu.**" if n == 1 else f"**{n} publicações de notícia não saíram.**"
        fazer = ("O que fazer: abra o Radar → **Publicações**: a notícia aparece como “Não concluída” ou “Autorizado — aguardando o "
                 "robô”. No site parado, clique em “Acionar o robô agora” (o robô do site depende do GitHub, que às vezes atrasa). No que "
                 "deu erro, abra o assunto (passo **3. Publicar**): o motivo está lá, e só sai de novo com nova autorização do "
                 "administrador.")
    linhas = [_linha(tipo, i, horas) for i in itens[:MAX_ITENS]]
    if n > MAX_ITENS:
        linhas.append(f"- … e mais {n - MAX_ITENS} (a lista inteira está no Radar).")
    marca = f"<!-- radar-lembrete: lote {grupo['lote']} itens {' '.join(str(int(i['id'])) for i in itens)} -->"
    return "\n\n".join([abre, "\n".join(linhas), fazer, RODAPE]) + "\n\n" + marca


def ja_comentado(github: GitHub, numero: int, lote: str) -> list[int] | None:
    """O lote retomado já saiu neste aviso (a marca dele está no corpo ou num comentário do robô)? Devolve os números das pendências
    que foram no e-mail, ou None."""
    for texto in github.textos_do_robo(numero):
        for m in MARCA.finditer(texto or ""):
            if m.group(1) == lote:
                return [int(x) for x in m.group(2).split()]
    return None


def mandar(banco: Banco, github: GitHub, grupo: dict, abertos: dict[str, int]) -> str:
    """Um tipo: comenta no aviso aberto do tipo (ou abre o aviso) e confirma no banco. Devolve a linha do registro (só números)."""
    tipo, lote = grupo["tipo"], str(grupo["lote"])
    titulo, itens = TITULOS[tipo], list(grupo.get("itens") or [])
    numero = abertos.get(titulo)
    if grupo.get("retomado") and numero:
        ids = ja_comentado(github, numero, lote)
        if ids is not None:
            banco.lembretes_enviado(lote, numero, ids)
            return f"{tipo}: {len(ids)} {'item já estava' if len(ids) == 1 else 'itens já estavam'} no aviso #{numero} (só confirmado)"
    texto = corpo(tipo, grupo)
    if numero:
        github.comentar(numero, texto)
        como = "comentário"
    else:
        numero = github.abrir_aviso(titulo, ABERTURA + "\n\n" + texto)
        abertos[titulo] = numero
        como = "aviso novo"
    banco.lembretes_enviado(lote, numero, [int(i["id"]) for i in itens])
    return f"{tipo}: {len(itens)} {'item' if len(itens) == 1 else 'itens'} no aviso #{numero} ({como})"


def executar(banco: Banco, github: GitHub) -> list[str]:
    """Pede o lote ao banco e manda um lembrete por tipo. O GitHub ou o banco falhou num tipo: ele fica para a próxima rodada (o mesmo
    lote volta, "retomado") e os outros tipos seguem."""
    lote = banco.lembretes_lote()
    if lote is None:
        return ["o banco ainda não tem os lembretes (rode o sql/radar-setup-v0.29.0.sql); nada a fazer"]
    grupos = [g for g in lote if g.get("tipo") in TITULOS and g.get("itens")]
    if not grupos:
        return []
    abertos = github.avisos_abertos(PREFIXO_LEMBRETE)
    feito = []
    for grupo in grupos:
        try:
            feito.append(mandar(banco, github, grupo, abertos))
        except (RuntimeError, requests.RequestException, ErroBanco, KeyError, TypeError, ValueError) as e:
            feito.append(f"{grupo['tipo']}: fica para a próxima rodada ({_motivo(e)})")
    return feito


def _motivo(e: Exception) -> str:
    """O tipo do erro e o código HTTP, se houver: nunca a mensagem inteira (pode levar o endereço do projeto)."""
    m = re.search(r"HTTP \d{3}", str(e))
    return type(e).__name__ + (f", {m.group(0)}" if m else "")


def main() -> int:
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (url and chave and token and repo):
        print("Lembretes: sem as variáveis necessárias; nada a fazer.")
        return 0
    try:
        feito = executar(Banco(url, chave), GitHub(repo, token))
    except Exception as e:                       # nunca vermelho: o GitHub mandaria um e-mail de falha a cada rodada
        print(f"! lembretes: nada foi mandado agora ({_motivo(e)}); a próxima rodada tenta de novo.", file=sys.stderr)
        return 0
    print("Lembretes: " + ("; ".join(feito) if feito else "nada a lembrar agora."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
