<div align="center">

# Aqua - Backend

Backend Django/DRF com monitoração de enchentes via câmeras, previsão do tempo, ocorrências, cadastro de pontos de alagamento, upload e gerenciamento de usuários. Orquestrado com Celery + Redis e Postgres via Docker Compose.

</div>

> Consulte o [guia de operação de containers e demo](docs/OPERACAO_CONTAINERS_E_DEMO.md)
> para comandos, variáveis, portas, saúde dos serviços e o plano de isolamento
> opcional de Flood Monitoring.

---

## Arquitetura Dual-Instance (Dev + Prod)

O projeto suporta duas instâncias independentes rodando no mesmo computador sem conflitos:

| Aspecto | Desenvolvimento | Produção |
|---|---|---|
| **Diretório** | `~/apps/aqua-dev/` | `~/apps/aqua-prod/` |
| **Projeto Docker** | `aqua-dev` | `aqua-prod` |
| **Porta Web** | `8001` | `8000` |
| **Porta DB** | `5434` | `5433` |
| **Volumes** | `aqua-dev_pgdata`, `aqua-dev_media` | `aqua-prod_pgdata`, `aqua-prod_media` |
| **Rede** | `aqua-dev_default` | `aqua-prod_default` |
| **Banco** | `aqua_dev` | `aqua_prod` |
| **Compose** | `docker compose up` | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` |

Cada instância é um clone independente do repositório, com seu próprio `.env`, volumes e containers.

---

## Início Rápido

### 1. Clonar o repositório (duas cópias)

```bash
# Produção
git clone <repo-url> ~/apps/aqua-prod
cd ~/apps/aqua-prod
git checkout main

Serviços no compose hospedado (`docker/docker-compose.yml`):

- `web`: Django em modo dev (runserver) ouvindo 0.0.0.0:8090
- `worker`: Celery worker
- `beat`: Celery beat (agendador)
- `redis`: Redis
- `db`: Postgres (exposto na máquina host em 5433)

Volumes nomeados externos (dev): `docker_pgdata` (Postgres) e `docker_media` (arquivos de mídia).
Rede compartilhada entre composes: `docker_shared_backend`.
No `web` hospedado, o código roda imutável (sem bind mount) e com filesystem em modo somente leitura.

## Requisitos

Recomendado:

- Docker e Docker Compose

Opcional (para rodar localmente sem Docker):

- Python 3.13
- Postgres 16+
- Redis 7+
- Bibliotecas do sistema para GDAL/GEOS/PROJ, OpenCV e ffmpeg (o Docker já provê isso)

## Início rápido (Docker) — recomendado

1) Crie os volumes externos uma única vez:

   docker volume create docker_pgdata
   docker volume create docker_media

2) Copie o arquivo de exemplo e ajuste as variáveis:

  ```bash
  cp .env.sample .env
  ```

3) Suba os serviços hospedados (imutáveis, sem bind mount de código):

  # opção A: executar de dentro da pasta docker/
  ```bash
  cd docker
  docker compose up -d --build
  ```

  # opção B: de qualquer lugar, informando o compose
  ```bash
  docker compose -f docker/docker-compose.yml up -d --build
  ```

4) Aplique migrações e crie um superusuário:

  ```bash
  docker compose -f docker/docker-compose.yml exec web python manage.py migrate
  docker compose -f docker/docker-compose.yml exec web python manage.py createsuperuser
  ```

5) Acesse:

- API: http://localhost:8090/
- Admin: http://localhost:8090/admin/

6) Opcional: suba um segundo container `web` local (editável), consumindo o mesmo banco e a mesma mídia:

  ```bash
  docker compose -f docker/docker-compose.local.yml up -d --build
  ```

- API local paralela: http://localhost:8091/
- Esse `web` local usa bind mount do código (`..:/app`) para desenvolvimento e usa a rede `docker_shared_backend` para acessar `db:5432` e `redis:6379` do compose hospedado.
- No compose local, `docker_media` está montado como somente leitura (`:ro`) para evitar escrita acidental de uploads.
- Se precisar testar upload via local, altere `docker/docker-compose.local.yml` para `media:/app/media` (sem `:ro`).

Logs úteis:

- Web:
  ```bash
  docker compose -f docker/docker-compose.yml logs -f web
  ```
- Worker:
  ```bash
  docker compose -f docker/docker-compose.yml logs -f worker
  ```
- Beat:
  ```bash
  docker compose -f docker/docker-compose.yml logs -f beat
  ```
- Web local (compose local):
  ```bash
  docker compose -f docker/docker-compose.local.yml logs -f web
  ```

Parar tudo:

  ```bash
  docker compose -f docker/docker-compose.yml down
  docker compose -f docker/docker-compose.local.yml down
  ```

## Desenvolvimento local 

1) Crie e ative um ambiente virtual Python 3.13:

  ```bash
  python3.13 -m venv .venv
  source .venv/bin/activate
  ```

2) Instale dependências Python (pode exigir libs de sistema avançadas; prefira Docker se encontrar erros):

  ```bash
  pip install --upgrade pip
  pip install -r requirements.txt
  ```

3) Configure e suba Postgres e Redis locais, ou use `DATABASE_URL`, `CELERY_BROKER_URL` e `CELERY_RESULT_BACKEND` apontando para serviços disponíveis.

4) Crie o arquivo `.env` (veja abaixo), execute migrações e rode o servidor:

  ```bash
  python manage.py migrate
  python manage.py runserver 0.0.0.0:8000
  ```

Worker/Beat localmente (outros terminais):

  ```bash
  celery -A config worker -l info
  celery -A config beat -l info
  ```

## Variáveis de ambiente (.env)

Exemplo seguro de `.env` (use `cp .env.sample .env` e ajuste os valores):

```dotenv
# Django
DJANGO_SETTINGS_MODULE=config.settings
DEBUG=1
DJANGO_SECRET_KEY=<defina-uma-chave-forte>

# Banco de Dados (use APENAS UMA das opções)
# Opção A: DATABASE_URL tem precedência quando definido
# Formato: postgresql://<usuario>:<senha>@<host>:<porta>/<nome_db>
DATABASE_URL=postgresql://<db_user>:<db_password>@db:5432/<db_name>

# Opção B: Variáveis individuais do Postgres (se DATABASE_URL estiver vazio)
POSTGRES_USER=<db_user>
POSTGRES_PASSWORD=<db_password>
POSTGRES_DB=<db_name>
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Celery / Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
REDIS_CACHE_URL=redis://redis:6379/2

# JWT (opcional)
JWT_ACCESS_MINUTES=60
JWT_REFRESH_DAYS=7
JWT_ALGORITHM=HS256

# API
API_PAGE_SIZE=20

# Outros
CAMERA_INSTALL_URL=
TZ=America/Sao_Paulo
```

### 2. Configurar ambiente

```bash
cd ~/apps/aqua-dev
cp .env.sample.dev .env
# Editar .env com suas credenciais de dev

cd ~/apps/aqua-prod
cp .env.sample.prod .env
# Editar .env com credenciais reais de produção
```

### 3. Subir os serviços

```bash
# Desenvolvimento (override carregado automaticamente)
cd ~/apps/aqua-dev

# Base: API e worker geral, sem câmeras e sem demo
docker compose -p aqua-dev up --build

# Apenas câmeras
docker compose -p aqua-dev --profile flood up --build

<<<<<<< HEAD
# Apenas demo
docker compose -p aqua-dev --profile demo up --build
=======
- No Docker, prefixe os comandos com `docker compose -f docker/docker-compose.yml exec web ...` para o compose hospedado.
- Para executar algo no `web` local paralelo, use `docker compose -f docker/docker-compose.local.yml exec web ...`.
>>>>>>> 14877fa (feat: add local Docker Compose configuration for development with bind mount and shared network)

# Câmeras e demo
docker compose -p aqua-dev --profile flood --profile demo up --build

# Produção (sempre rodando)
cd ~/apps/aqua-prod
docker compose -p aqua-prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Na produção, Flood Monitoring, beat e demo-stream sobem por padrão. Em
desenvolvimento, os perfis tornam câmeras e demo opcionais.

### 4. Migrações e superusuário

```bash
docker compose -p aqua-dev exec web python manage.py migrate
docker compose -p aqua-dev exec web python manage.py createsuperuser
```

---

## Mapeamento de Portas

| Serviço | Container | Dev | Prod |
|---|---|---|---|
| **Django API** | `8090` | `8001` | `8000` |
| **PostgreSQL** | `5432` | `5434` | `5433` |
| **Redis** | `6379` | _(não exposta)_ | _(não exposta)_ |
| **Worker/Beat** | — | _(sem porta)_ | _(sem porta)_ |

---

## Arquivos de Composição

| Arquivo | Função |
|---|---|
| `docker-compose.yml` | Base compartilhada (build, depends_on, volumes nomeados) |
| `docker-compose.override.yml` | Override dev (portas interpoladas, bind mount para hot reload) — **auto-load** |
| `docker-compose.prod.yml` | Override prod (portas fixas, restart policies, volumes nomeados) |

### Uso

```bash
# Dev (override auto-load)
docker compose -p aqua-dev up

# Prod (override explícito)
docker compose -p aqua-prod -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Comandos Comuns

```bash
# Ver logs
docker compose -p aqua-dev logs -f web
docker compose -p aqua-dev logs -f worker

# Executar comandos no container
docker compose -p aqua-dev exec web python manage.py migrate
docker compose -p aqua-dev exec web python manage.py createsuperuser

# Parar
docker compose -p aqua-dev down

# Reconstruir imagem
docker compose -p aqua-dev up --build

# Ver volumes
docker volume ls | grep aqua
```

---

## Variáveis de Ambiente

Cada clone tem seu próprio `.env`. Use os samples como template:

| Sample | Ambiente | Portas |
|---|---|---|
| `.env.sample.dev` | Desenvolvimento | `WEB_PORT=8001`, `DB_PORT=5434` |
| `.env.sample.prod` | Produção | `WEB_PORT=8000`, `DB_PORT=5433` |

Principais variáveis:

| Variável | Descrição |
|---|---|
| `DEBUG` | `1` para dev, `0` para produção |
| `DJANGO_SECRET_KEY` | Chave secreta (gerar com `python -c "import secrets; print(secrets.token_urlsafe(64))"`) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Credenciais do banco |
| `CELERY_BROKER_URL` | Redis (default: `redis://redis:6379/0`) |
| `WEB_PORT` | Porta host para o Django |
| `DB_PORT` | Porta host para o PostgreSQL |
| `ACCESS_TOKEN` | Token Mercado Pago |
| `FLOOD_MODEL_DRIVE_ID` | ID do modelo ML no Google Drive |
| `API_URL` | URL da API para sync remoto |

<<<<<<< HEAD
---

## Estrutura do Projeto

```
├── docker-compose.yml              # Docker Compose base
├── docker-compose.override.yml     # Dev overrides (auto-load)
├── docker-compose.prod.yml         # Prod overrides
├── Dockerfile               # Multi-stage production (Gunicorn — usado pelo Dokku)
├── Dockerfile.slim          # Slim image (usada pelo Docker Compose local)
├── requirements.runtime.txt # Dependências para a slim image
├── .dockerignore            # Regras de exclusão do build Docker
├── requirements.txt         # Dependências pinadas
├── pyproject.toml           # Metadados e scripts PDM
├── Procfile                 # Perfil Heroku/Dokku
├── config/                  # Django settings, urls, wsgi, celery
├── core/                    # Apps: users, weather, forecast, occurrences, etc.
├── .env.sample.dev          # Template para dev
└── .env.sample.prod         # Template para produção
```

---

## Deploy (Dokku)

O deploy real de produção é feito via GitHub Actions para Dokku:

```yaml
# .github/workflows/deploy.yml
# Push na branch main → ssh para dokku@app2.fabricadesoftware.ifc.edu.br
```

O `Dockerfile` da raiz (multi-stage com Gunicorn) é usado pelo Dokku, não pelo Compose local.

---

## Solução de Problemas

- **Porta ocupada**: Ajuste `WEB_PORT` e `DB_PORT` no `.env`
- **Conflito de volumes**: Use `-p aqua-prod` / `-p aqua-dev` para isolar nomes
- **Healthcheck DB falhando**: Verifique se `POSTGRES_USER` no `.env` corresponde ao usuário do healthcheck
- **Migrações pendentes**: `docker compose exec web python manage.py migrate`
=======
MIT (veja `pyproject.toml`).
>>>>>>> 14877fa (feat: add local Docker Compose configuration for development with bind mount and shared network)
