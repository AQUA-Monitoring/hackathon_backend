<div align="center">

# hackathon_backend

Backend Django/DRF com monitoração de enchentes via câmeras, previsão do tempo, ocorrências, cadastro de pontos de alagamento, upload e gerenciamento de usuários. Orquestrado com Celery + Redis e Postgres. Pronto para rodar com Docker Compose.

</div>

—

Sumário

- Visão geral
- Arquitetura e stack
- Requisitos
- Início rápido (Docker) — recomendado
- Desenvolvimento local (sem Docker) — opcional
- Variáveis de ambiente (.env)
- Banco de dados e migrações
- Tarefas assíncronas (Celery/Beat)
- Endpoints e autenticação
- Estrutura do projeto
- Deploy (produção)
- Solução de problemas (FAQ)
- Licença

## Visão geral

Este projeto fornece uma API para:

- Monitoração de enchentes por câmeras, com processamento de imagens e agendamento de análises.
- Consulta de clima e previsão do tempo.
- Registro e consulta de ocorrências.
- Cadastro de pontos de alagamento.
- Uploads e gestão de mídia.
- Autenticação e gerenciamento de usuários.

Principais apps em `core/`:

- `users`, `weather`, `forecast`, `occurrences`, `flood_camera_monitoring`, `flood_point_registering`, `uploader`, `addressing`, `donation`.

## Arquitetura e stack

- Framework: Django 5.2 + Django REST Framework
- Auth: JWT (djangorestframework-simplejwt) com view customizada por e-mail/senha
- Tarefas: Celery 5 + Redis (broker e result backend) + django-celery-beat (agendador)
- Banco: PostgreSQL
- Mídia/estáticos: `MEDIA_ROOT` em volume Docker; `STATIC_ROOT` = `staticfiles`
- Processamento: OpenCV, Torch (CPU), scikit-learn
- Geoespacial: GeoPandas, Shapely, PROJ, GDAL (dependências via imagem Docker)
- Conteinerização: Docker/Docker Compose

Serviços no Docker Compose (`docker/docker-compose.yml`):

- `web`: Django em modo dev (runserver) ouvindo 0.0.0.0:8000
- `worker`: Celery worker
- `beat`: Celery beat (agendador)
- `redis`: Redis
- `db`: Postgres (exposto na máquina host em 5433)

Volumes nomeados externos (dev): `docker_pgdata` (Postgres) e `docker_media` (arquivos de mídia).

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

3) Suba os serviços (a partir da pasta `docker/` ou informando o arquivo compose explicitamente):

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

- API: http://localhost:8000/
- Admin: http://localhost:8000/admin/

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

Parar tudo:

  ```bash
  docker compose -f docker/docker-compose.yml down
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

Observações:

- Em `config/settings.py`, `DEBUG` está como `True` por padrão. Ajuste para produção.
- CORS/CSRF já permitem origens de desenvolvimento e domínios institucionais conhecidos. Para produção, refine listas conforme necessário.

## Banco de dados e migrações

- Aplique migrações sempre que atualizar o código:

  python manage.py migrate

- Para criar novas migrações:

  python manage.py makemigrations

- No Docker, prefixe os comandos com `docker compose exec web ...` conforme mostrado no Início rápido.

Portas e acesso (Docker):

- Postgres roda no contêiner na 5432 e é exposto no host em 5433. Para clientes locais utilize host `localhost` e porta `5433` (credenciais do seu `.env`).

## Tarefas assíncronas (Celery/Beat)

- Worker: processa tarefas; Beat: agenda tarefas periódicas.
- Agendamento padrão no settings inclui (a cada 300s):

  task: core.flood_camera_monitoring.infra.tasks.analyze_all_cameras_task
  schedule: 300 segundos

- O projeto usa `django-celery-beat` como scheduler (tabelas precisam existir). O código faz fallback para um scheduler persistente se as tabelas ainda não existirem, evitando crash no primeiro start. Ainda assim, aplique migrações.
- Exemplo de tarefa utilitária: `core/flood_camera_monitoring/tasks.py::refresh_all_and_cache_task`, que executa análise unificada e popula cache Redis.

## Endpoints e autenticação

Base de rotas (veja `config/urls.py`):

- Admin: `GET /admin/`
- Auth JWT:
  - `POST /api/auth/token/` — autentica por e-mail/senha e retorna access/refresh
  - `POST /api/auth/token/refresh/`
- Módulos:
  - `GET/POST /api/users/...`
  - `GET/POST /api/weather/...`
  - `GET/POST /api/forecast/...`
  - `GET/POST /api/occurrences/...`
  - `GET/POST /api/flood_monitoring/...`
  - `GET/POST /api/upload/...`
  - `GET/POST /api/addressing/...`
  - `GET/POST /api/donate/...`
  - `GET/POST /api/floods_point/...`

Autenticação:

- Envie o header `Authorization: Bearer <ACCESS_TOKEN>` nas rotas protegidas.
- Duração padrão dos tokens é configurável via `.env` (veja seção JWT).

## Estrutura do projeto

Raiz (principais itens):

- `config/` — settings, urls, wsgi/asgi, celery, paginação
- `core/` — apps de domínio (users, weather, forecast, occurrences, flood_camera_monitoring, etc.)
- `docker/` — Dockerfiles alternativos e `docker-compose.yml`
- `manage.py` — utilitário Django
- `requirements.txt` — dependências pinadas para build
- `pyproject.toml` — metadados do projeto e scripts PDM (opcional para dev)
- `Procfile` — perfil para plataformas tipo Heroku (web/worker/beat)

## Deploy (produção)

Você pode construir com o `Dockerfile` da raiz (multi-stage, com Gunicorn):

- Expõe a aplicação WSGI via `gunicorn config.wsgi:application` (ver `Procfile`).
- Espera a variável `PORT` no ambiente (ou ajuste o comando no `Dockerfile`).
- Executa `collectstatic` durante o build (ignora se não houver estáticos).

Diretrizes rápidas:

- Ajuste `DEBUG=False`, `ALLOWED_HOSTS` e CORS/CSRF para seus domínios.
- Forneça `DJANGO_SECRET_KEY` seguro.
- Aponte `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` para serviços gerenciados.
- Configure armazenamento de mídia (S3, GCS, etc.) para ambientes distribuídos.

Alternativamente, o compose de dev usa `docker/Dockerfile.slim` com `runserver`. Para produção, prefira o `Dockerfile` raiz ou uma imagem própria baseada nele.

## Solução de problemas (FAQ)

- Erro: ImproperlyConfigured: DJANGO_SECRET_KEY environment variable is not set
  - Garanta que seu `.env` na raiz defina `DJANGO_SECRET_KEY` e que o compose referencie `../.env`.

- Tabelas do django_celery_beat ausentes / Beat não agenda
  - Rode migrações. O código tenta fallback para um scheduler persistente, mas o ideal é aplicar as migrações do `django_celery_beat`.

- Erros ao instalar GDAL/GEOS/PROJ localmente
  - Use Docker (recomendado). Se insistir local, instale bibliotecas do sistema correspondentes à sua distro.

- CORS/CSRF bloqueando requisições no front
  - Ajuste origens permitidas em `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` no settings.

- Postgres inacessível do host
  - No compose, use `localhost:5433` (e não 5432). Dentro dos contêineres, o host é `db:5432`.

## Licença

MIT (veja `pyproject.toml`).


