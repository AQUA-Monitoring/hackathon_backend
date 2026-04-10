# Verificar risco na imagem.
FROM python:3.13-slim 

WORKDIR /app

RUN apt-get update && apt-get upgrade -y
COPY pyproject.toml pdm.lock ./
RUN pip install pdm && pdm install

COPY . .

EXPOSE 8090

CMD ["pdm", "run", "dev", "0.0.0.0:8090"]
