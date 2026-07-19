# Importação geoespacial

O comando `import_addressing_dataset` aceita GeoJSON e CSV CNEFE com longitude e
latitude. `--city-code` e `--crs` são os argumentos canônicos; `--city` e
`--source-crs` permanecem como aliases compatíveis. O modo padrão rejeita
geometrias inválidas; `--repair-geometries` usa `make_valid` e registra cada
reparo no relatório do dataset.

A API administrativa não recebe uploads. Ela só processa caminhos relativos já
disponíveis em `GEODATA_IMPORT_ROOT`, limita o arquivo por
`GEODATA_IMPORT_MAX_BYTES` e executa a carga de forma síncrona.

O banco precisa ser PostGIS. A conta que aplica a migração `0015` necessita do
privilégio `CREATE EXTENSION` para criar `postgis`; em ambientes gerenciados, a
extensão deve ser habilitada previamente por um administrador do banco.
