# Base geográfica de Joinville e Araquari

Este documento registra a carga local de desenvolvimento realizada em
2026-07-19. Os arquivos brutos e processados ficam em `data/geodata/`, são
ignorados pelo Git e não devem ser confundidos com dados implantados em
produção. A fonte de verdade da ativação é `GeodataDataset`.

## Fontes ativadas localmente

| Cidade | Camada | Autoridade e edição | Fonte | SHA-256 do arquivo importado | Resultado |
|---|---|---|---|---|---|
| Joinville | Município | IBGE 2024 | [Malhas municipais de Santa Catarina](https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2024/UFs/SC/SC_Municipios_2024.zip) | `9449313433c5dcc0829aa107aa26b0b7c85a5bd14ba3e869f6477cbfe1ce98b9` | 1 limite |
| Araquari | Município | IBGE 2024 | [Malhas municipais de Santa Catarina](https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2024/UFs/SC/SC_Municipios_2024.zip) | `176e9e6894a4be8dd2c5bfa2c2595e89663d44832dad2bed31c4e772b8e60af6` | 1 limite |
| Joinville | Bairros | Prefeitura de Joinville, SIMGeo 2023-10-16 | [FeatureServer BAIRROS](https://geo.joinville.sc.gov.br/server/rest/services/Hosted/BAIRROS/FeatureServer/3) | `16063b150c4a0cf3fb59fe83667bfdbec92fe5550a89fdbd305606b3acf9cca5` | 43 bairros |
| Araquari | Bairros | IBGE, Censo 2022 | [Malha de bairros de Santa Catarina](https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/malha_com_atributos/bairros/shp/UF/SC/SC_bairros_CD2022.zip) | `147a7c118cb51037ef47786ac5fe672f99a0da383408f4a085d46007bf93d08b` | 10 bairros |
| Joinville | Eixos viários | Prefeitura de Joinville, SIMGeo obtido em 2026-07-19 | [FeatureServer LOGRADOUROS](https://geo.joinville.sc.gov.br/server/rest/services/Hosted/LOGRADOUROS/FeatureServer/0) | `16f86fdec104478cf02f2bc654c3183e9ed90a8337430c65ed86a33d476a5dff` | 16.708 segmentos |
| Joinville | Endereços | IBGE, CNEFE 2022 | [CSV municipal](https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/42_SC/4209102_JOINVILLE.zip) | `0e17ecc85ef80c707edcad321d85f6cdc3aa1394168165a8c46a62da3250f3d8` | 280.855 aceitos; 11 externos rejeitados |
| Araquari | Endereços | IBGE, CNEFE 2022 | [CSV municipal](https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/42_SC/4201307_ARAQUARI.zip) | `f194ccfe02ca2f9d14a53d62c69337afb2f5f571d02d06eefc5145aab8944d7c` | 23.301 aceitos; 3 externos rejeitados |

Os metadados da Prefeitura de Joinville declaram os dados para consulta sem
restrição de uso e pedem citação da fonte original. A autorização deve ser
reconfirmada antes de uma carga em produção. A base viária de Araquari não foi
ativada: nenhuma fonte municipal reutilizável foi confirmada nesta edição.

## Regra específica do CNEFE

O arquivo usa `;` como delimitador. `COD_UNICO_ENDERECO` pode aparecer mais de
uma vez quando espécies distintas ocupam a mesma coordenada; por isso o ID da
fonte é composto por `COD_UNICO_ENDERECO,COD_ESPECIE`. Pontos fora do limite
municipal são rejeitados somente quando `--skip-outside-city` é informado e
ficam contabilizados em `report.conflicts` e `report.skipped`. Endereços que
não caem em um bairro permanecem com `neighborhood=NULL`.

Exemplo reproduzível, sempre precedido por `--dry-run`:

```bash
python manage.py import_addressing_dataset ARQUIVO.csv \
  --kind address_point --city-code CODIGO_IBGE --authority IBGE \
  --title "CNEFE MUNICIPIO" --source-url URL_DO_CSV \
  --license-name "IBGE - dados públicos" --license-url URL_DA_PUBLICACAO \
  --source-version "Censo 2022" --published-at 2024-05-21 --crs EPSG:4326 \
  --csv-delimiter ';' --id-props COD_UNICO_ENDERECO,COD_ESPECIE \
  --street-props NOM_TITULO_SEGLOGR,NOM_SEGLOGR \
  --number-prop NUM_ENDERECO --zipcode-prop CEP \
  --modifier-prop DSC_MODIFICADOR --address-type-prop NOM_TIPO_SEGLOGR \
  --species-prop COD_ESPECIE --complement-prop VAL_COMP_ELEM1 \
  --longitude-prop LONGITUDE --latitude-prop LATITUDE \
  --chunk-size 2000 --skip-outside-city --dry-run
```

Remova `--dry-run` apenas depois de revisar checksum, licença, contagens e
conflitos. Repetir o mesmo arquivo e autoridade retorna `idempotent=true`.

## Estado da carga local

- Joinville: 43 bairros, 16.708 eixos e 280.855 endereços ativos; 269.527
  endereços resolvidos para bairro.
- Araquari: 10 bairros e 23.301 endereços ativos; 20.642 endereços resolvidos
  para bairro.
- Regiões não foram inferidas.
- Nenhum endereço operacional de câmera foi sobrescrito pela carga.
- Produção não foi alterada.
