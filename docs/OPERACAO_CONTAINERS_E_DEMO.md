# Operação de containers, Flood Monitoring e demo
O projeto possui quatro modos de desenvolvimento e uma composição de produção
isolada. O banco, Redis e os modelos Django de câmeras permanecem no core; o
que é opcional no desenvolvimento são captura de vídeo, inferência, agenda
flood e stream da demo.

## Modos de execução

| Modo | Comando | Serviços adicionais |
|---|---|---|
| Dev base | docker compose -p aqua-dev up --build | Nenhum: web, worker, db e redis |
| Dev API de câmeras | docker compose -p aqua-dev --profile flood up -d --build web worker flood-api | flood-api, sem agenda nem captura automática |
| Dev câmeras | docker compose -p aqua-dev --profile flood up --build | flood-api, flood-worker e beat |
| Dev demo | docker compose -p aqua-dev --profile demo up --build | demo-stream |
| Dev câmeras + demo | docker compose -p aqua-dev --profile flood --profile demo up --build | Todos os opcionais |
| Produção | docker compose -p aqua-prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build | beat e demo-stream são padrão |

No dev base, web e worker usam a imagem base, sem Torch, Torchvision, OpenCV,
FFmpeg ou download de modelo. As rotas de Flood Monitoring respondem 503
estável enquanto flood-api estiver desligado.

O modo **Dev API de câmeras** é o mais indicado para trabalhar em cadastro,
admin, listagem, snapshots já persistidos e integração frontend. Ele mantém a
API especializada disponível, mas não inicia `beat` nem `flood-worker`; assim,
nenhuma câmera é consultada automaticamente. Ative o perfil flood completo
somente quando a captura e a análise assíncrona fizerem parte do teste.

## Topologia

~~~text
dev base:
  web(base) + worker(base) + db + redis

profile flood:
  web(base) -> flood-api(flood)
  flood-worker(flood_camera, concorrência 1) + beat(base)

profile demo:
  demo-stream(demo, HLS 8088, controle interno 8089)
  web(base) -> demo-stream para status e troca de cenário

produção:
  web(full, Gunicorn) + worker(full) + beat(full)
  + demo-stream(demo) + db + redis
~~~

## Portas e saúde

| Serviço | Host dev | Host produção | Healthcheck |
|---|---:|---:|---|
| web | 8001 | 8000 | /health/ verifica somente DB e Redis |
| db | 5434 | 5433 | pg_isready |
| redis | não publicada | não publicada | redis-cli ping |
| demo-stream HLS | 8188 em produção (8088 internamente) | 8188 em produção | /health na porta interna 8089 |
| flood-api | interna | incorporada ao web full | /health interno |

Os healthchecks do override de desenvolvimento executam uma verificação inicial
com intervalo de 20 segundos e, depois de saudável, repetem somente a cada 24
horas para não poluir os logs. Produção mantém a frequência mais curta.

## Configuração

Crie o ambiente de desenvolvimento:

~~~bash
cp .env.sample.dev .env
python -c "import secrets; print(secrets.token_urlsafe(64))"
~~~

Variáveis principais:

| Variável | Uso |
|---|---|
| POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD | Banco usado pelo Django e PostgreSQL |
| FLOOD_CAMERA_API_MODE | proxy no web leve; direct em flood-api e produção |
| FLOOD_CAMERA_SERVICE_URL | Endereço interno do flood-api, padrão http://flood-api:8091 |
| FLOOD_CAMERA_DEDICATED_QUEUE | 1 no dev para usar a fila flood_camera; 0 em produção |
| DEMO_CONTROL_TOKEN | Obrigatório para iniciar e controlar demo-stream |
| DEMO_VIDEO_ATTACHMENT_KEY | Chave retornada por POST /api/upload/videos/ para o vídeo da demo |
| DEMO_STREAM_PUBLIC_URL | URL HLS consumida pelo navegador |
| DEMO_STREAM_INTERNAL_URL | Controle interno da demo, http://demo-stream:8089 |
| DEMO_STREAM_MEDIA_INTERNAL_BASE_URL | Segmentos internos, http://demo-stream:8088 |

Em produção, DEMO_ENABLED é forçado para 1 pela composição e demo-stream sobe
como serviço normal. Defina um DEMO_CONTROL_TOKEN forte e uma URL pública real
em .env.sample.prod antes de publicar.

## Uploader e demo

O uploader aceita PNG, JPEG e SVG seguro em /api/upload/images/, PDF em
/api/upload/documents/ e MP4, WebM ou MOV em /api/upload/videos/. Os limites
padrão são 10 MiB para imagens e 500 MiB para vídeos; podem ser alterados com
UPLOADER_IMAGE_MAX_BYTES e UPLOADER_VIDEO_MAX_BYTES.

O arquivo demo_assets/scenario.json mantém apenas a estrutura do cenário. O
MP4 não faz parte da imagem Docker nem do repositório: demo-stream resolve
DEMO_VIDEO_ATTACHMENT_KEY no banco e materializa o arquivo a partir do storage
do Django. O volume media é compartilhado entre web e demo-stream, e o mesmo
fluxo também funciona com outro backend de storage.

Antes da primeira execução em cada ambiente, envie o vídeo e copie o
attachment_key da resposta para o arquivo .env:

~~~bash
curl -f -X POST http://localhost:8001/api/upload/videos/ \
  -H 'Authorization: Bearer <JWT_DE_ADMIN>' \
  -F 'description=Demo de alagamento' \
  -F 'file=@/caminho/para/demo.mp4'

# .env
DEMO_VIDEO_ATTACHMENT_KEY=<attachment_key_da_resposta>
~~~

Depois de alterar a chave, recrie demo-stream para que ele carregue o vídeo do
uploader. O banco e o volume media precisam ser preservados juntos entre
deploys.

~~~bash
# Stream e API base de controle
docker compose -p aqua-dev --profile demo up --build

# Testar mídia
curl -f http://localhost:8088/health
curl -f http://localhost:8088/hls/playlist.m3u8

# Status e controle pela API
curl -i http://localhost:8001/api/flood_monitoring/demo
curl -i -X POST http://localhost:8001/api/flood_monitoring/demo/state \
  -H 'Authorization: Bearer <JWT_DE_ADMIN>' \
  -H 'Content-Type: application/json' \
  --data '{"state":"flooded"}'
~~~

GET /api/flood_monitoring/demo/predict precisa do perfil flood, pois executa
inferência no último segmento HLS. Sem flood, retorna 503 sem carregar
bibliotecas de ML.

## Câmeras e filas

No perfil flood, o gateway web mantém a mesma URL pública
/api/flood_monitoring/* e encaminha chamadas de inferência para flood-api. O
worker geral consome somente celery; flood-worker consome somente flood_camera.
O beat de desenvolvimento só sobe nesse perfil e mantém a análise periódica de
300 segundos.

~~~bash
docker compose -p aqua-dev --profile flood up --build
docker compose -p aqua-dev --profile flood logs -f flood-api flood-worker beat
~~~

## Rotina operacional

~~~bash
docker compose -p aqua-dev ps
docker compose -p aqua-dev logs -f web
docker compose -p aqua-dev exec web python manage.py migrate
docker compose -p aqua-dev exec web python manage.py check
docker compose -p aqua-dev down

docker compose -p aqua-prod \
  -f docker-compose.yml -f docker-compose.prod.yml ps
~~~

Use down -v apenas quando a intenção for remover banco e mídia locais. Os
volumes produtivos são externos e não devem ser apagados sem backup aprovado.

## Diagnóstico

| Sintoma | Ação |
|---|---|
| Flood retorna 503 no dev base | Ative --profile flood |
| Demo retorna 503 | Ative --profile demo e confira DEMO_CONTROL_TOKEN |
| demo/predict retorna 503 | Ative flood e aguarde um segmento HLS completo |
| Worker geral executa tarefa flood | Confirme FLOOD_CAMERA_DEDICATED_QUEUE=1 e o argumento -Q celery |
| web não saudável | Consulte /health/; ele informa DB e Redis sem depender do modelo |
