# Radar Artecon — corretor de vídeo (v0.22.0): a imagem do ffmpeg isolado (radar-ffmpeg:local).
#
# Montada no robô do repositório privado radar-video, antes do passo que recebe as chaves:
#   docker build -q -t radar-ffmpeg:local -f robo/video/Dockerfile robo/video
# e usada por isolado.py, a cada ffmpeg/ffprobe, sem rede, sem variáveis de ambiente, com o sistema de arquivos só de leitura e o
# usuário 1001 sem privilégio (docker run --rm --network none --read-only --user 1001:1001 --cap-drop ALL …).
#
# O que é fixado: a imagem do Ubuntu 24.04 pelo digest e o ffmpeg pela versão exata (o mesmo 6.1.1 em que a receita foi medida) —
# a linha de comando E as bibliotecas libav* que fazem o trabalho. O pacote ffmpeg pede as bibliotecas só com ">=" ("libavcodec60
# (>= 7:6.1)"): fixado só ele, uma correção do Ubuntu nas bibliotecas (noble-updates, noble-security) entraria sem nada falhar. Com
# todas na mesma versão, o apt instala sempre a 7:6.1.1-3ubuntu5, que continua no arquivo da 24.04 depois de uma correção (a montagem
# NÃO falha quando sai versão nova: para trocar, confira a nova com apt-cache policy ffmpeg num ubuntu:24.04, rode os testes do robô
# de vídeo e troque FFMPEG_VERSAO). As outras bibliotecas que o ffmpeg usa (libass, libfreetype, libx264, libzimg…) seguem as
# correções de segurança da 24.04. BASE só muda nos testes, para baixar a mesma imagem (o mesmo digest) de um espelho quando o Docker
# Hub recusa por limite.
ARG BASE=ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
FROM ${BASE}
ARG FFMPEG_VERSAO=7:6.1.1-3ubuntu5
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "ffmpeg=${FFMPEG_VERSAO}" \
      "libavcodec60=${FFMPEG_VERSAO}" "libavdevice60=${FFMPEG_VERSAO}" "libavfilter9=${FFMPEG_VERSAO}" "libavformat60=${FFMPEG_VERSAO}" \
      "libavutil58=${FFMPEG_VERSAO}" "libpostproc57=${FFMPEG_VERSAO}" "libswresample4=${FFMPEG_VERSAO}" "libswscale7=${FFMPEG_VERSAO}" \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -u 1001 -U -M -s /usr/sbin/nologin corretor
# o fontconfig (do libass) quer uma pasta gravável para o cache: só o /tmp, que é memória no docker run (--tmpfs)
ENV HOME=/tmp XDG_CACHE_HOME=/tmp
USER 1001:1001
WORKDIR /tmp
