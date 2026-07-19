# Fluxo territorial e histórico de alagamentos

Este documento descreve como o Aqua relaciona câmeras e evidências de
alagamento ao território. A API Django e os dados versionados no PostGIS são a
fonte canônica. Mapbox e o GeoJSON estático do frontend são apenas recursos de
busca e apresentação.

## Visão geral

```text
coordenada ou mancha
        |
        v
serviço de resolução territorial
        |
        +--> município e bairro por cobertura/interseção
        +--> região oficial, quando existir
        +--> rua e segmento viário por proximidade/interseção
        +--> dataset, qualidade e motivos da resolução
        |
        +--> câmera (localização operacional)
        `--> evento -> revisão -> trechos atingidos -> histórico
```

O código segue o fluxo convencional do Django:

```text
urls -> views/viewsets -> serializers -> services -> models/PostGIS
```

Services são usados somente para operações que combinam regras, transações ou
consultas espaciais. Não devem ser criadas entidades ou interfaces de
repositório que apenas dupliquem o ORM.

## Catálogo territorial

- `City`, `Region` e `Neighborhood` guardam limites oficiais.
- `Street` identifica o logradouro pelo nome e pela cidade.
- `RoadAxisSegment` guarda a geometria física analisável de um trecho.
- `AddressReference` guarda pontos de fontes como o CNEFE.
- `GeodataDataset` registra autoridade, versão, licença, CRS e checksum.

Região é opcional e nunca deve ser inferida por centróide. CEP também é
opcional: serve para pesquisa e conferência, não para determinar o território.
Uma importação não altera os textos já salvos no endereço operacional de uma
câmera.

## Resolução de um ponto

O resolvedor rejeita coordenadas ausentes, inválidas e `[0, 0]`. Município e
bairro são obtidos com cobertura espacial. Rua, segmento e endereço são
avaliados por proximidade e podem ficar vazios quando não houver uma
correspondência segura.

Os estados possíveis são:

- `VERIFIED`: correspondência canônica sem conflito relevante;
- `APPROXIMATE`: candidato próximo que exige atenção;
- `MANUAL`: escolha confirmada manualmente por operador autorizado;
- `INCONSISTENT`: dados submetidos contradizem a geometria;
- `UNRESOLVED`: a base disponível não permite determinar o vínculo.

O cadastro de câmera sempre repete a validação no servidor. O frontend pode
sugerir um endereço com Mapbox, mas essa sugestão não substitui a resolução no
PostGIS.

## Resolução de uma mancha

Uma mancha deve ser `Polygon` ou `MultiPolygon` em EPSG:4326. Para ativar um
evento, ela precisa estar contida em um único município. Todos os bairros
intersectados são retornados; o bairro do ponto representativo não substitui
essa lista.

Os segmentos candidatos são recortados com `ST_Intersection`. Apenas as partes
lineares são persistidas e medidas em EPSG:31982. Tangência pontual aparece no
relatório, mas não conta como extensão alagada. A rua principal é a que possui
maior comprimento atingido, sem marcar a rua inteira como alagada.

```text
FloodSpatialEvent
  `-- FloodFootprintRevision
        |-- resolução territorial da revisão
        `-- RoadFloodImpactRun
              `-- RoadFloodImpact (recorte, metros e fração)
```

Nova revisão ou nova malha viária produz outro snapshot. Resultados anteriores
permanecem auditáveis.

## Natureza da evidência

Previsão, observação de câmera, relato e ocorrência confirmada são naturezas
distintas. Um relato não vira confirmação por atualização silenciosa. A
confirmação humana cria um evento confirmado relacionado à evidência original.
Registros antigos cuja natureza não possa ser comprovada devem usar
`LEGACY_UNCLASSIFIED`.

## Compatibilidade do cadastro antigo

O endpoint de `flood_point_registering` é temporário. Ele preserva o payload
histórico para o frontend e o sync, mas deve delegar a resolução ao mesmo
serviço territorial usado pelos eventos. A fachada só poderá ser removida
depois que frontend, fila offline e sincronização usarem o contrato canônico e
uma versão publicada da API registrar a depreciação.

## Diagnóstico de inconsistências

Ao investigar uma localização:

1. confira longitude/latitude e a ordem dos eixos;
2. confirme que não é `[0, 0]`;
3. confira a versão ativa dos datasets de limite e vias;
4. verifique o estado e os códigos de motivo retornados pelo resolvedor;
5. compare cidade e bairro informados com `covers` no PostGIS;
6. inspecione a distância até rua/endereço candidato;
7. em bordas, mantenha a ambiguidade explícita para revisão humana;
8. não corrija o histórico sobrescrevendo snapshots anteriores.

Araquari possui limites e referências de endereço, mas ainda não possui eixo
viário municipal autorizado nesta base. Nesse caso, cidade e bairro podem ser
verificados enquanto rua e segmento permanecem não resolvidos.

## Operação e migrações

- Nunca edite migração já aplicada; crie uma migração corretiva.
- Novas referências territoriais começam opcionais e recebem backfill
  idempotente.
- Não invente coordenadas para dados antigos.
- Rode importações primeiro com `--dry-run` e confira licença, checksum,
  contagens, conflitos e reparos.
- Não ative nova fonte em produção sem autorização de reutilização.
- O rollback lógico reativa a versão anterior do dataset; registros e
  snapshots históricos não são apagados.

Consulte `docs/GEODATA_JOINVILLE_ARAQUARI.md` para fontes, checksums, contagens
locais e exemplo reproduzível de importação.
