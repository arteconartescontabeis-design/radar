# Radar Artecon — corretor de vídeo (v0.22.0): a imagem do ffmpeg isolado (radar-ffmpeg:local).
#
# Montada no robô do repositório privado radar-video, antes do passo que recebe as chaves:
#   docker build -q -t radar-ffmpeg:local -f robo/video/Dockerfile robo/video
# e usada por isolado.py, a cada ffmpeg/ffprobe, sem rede, sem variáveis de ambiente, com o sistema de arquivos só de leitura e o
# usuário 1001 sem privilégio (docker run --rm --network none --read-only --user 1001:1001 --cap-drop ALL …).
#
# Tudo fixado: a imagem do Ubuntu 24.04 pelo digest e o pacote do ffmpeg pela versão exata (o mesmo 6.1.1 em que a receita foi
# medida; já traz libass, libfreetype, libx264 e libzimg). Quando o Ubuntu publicar uma correção do ffmpeg, a montagem falha aqui
# de propósito: confira a versão nova (apt-cache policy ffmpeg num ubuntu:24.04), rode os testes do robô de vídeo e troque as duas.
# BASE só muda nos testes, para baixar a mesma imagem (o mesmo digest) de um espelho quando o Docker Hub recusa por limite.
ARG BASE=ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
FROM ${BASE}
ARG FFMPEG_VERSAO=7:6.1.1-3ubuntu5
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "ffmpeg=${FFMPEG_VERSAO}" \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -u 1001 -U -M -s /usr/sbin/nologin corretor
# o fontconfig (do libass) quer uma pasta gravável para o cache: só o /tmp, que é memória no docker run (--tmpfs)
ENV HOME=/tmp XDG_CACHE_HOME=/tmp
USER 1001:1001
WORKDIR /tmp
