from django.db import migrations


TERRITORY_TABLES = (
    "addressing_city",
    "addressing_region",
    "addressing_neighborhood",
)


def reconcile_territory_geometry(apps, schema_editor):
    """Repair databases where an applied migration left geometry as jsonb.

    Migration state already declares these columns as MultiPolygonField, so a
    normal AlterField cannot detect the physical schema drift.
    """

    connection = schema_editor.connection
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        for table in TERRITORY_TABLES:
            cursor.execute(
                """
                SELECT data_type, udt_name
                  FROM information_schema.columns
                 WHERE table_schema = current_schema()
                   AND table_name = %s
                   AND column_name = 'geometry'
                """,
                [table],
            )
            column = cursor.fetchone()
            if column is None:
                raise RuntimeError(f"Missing required column {table}.geometry")

            data_type, udt_name = column
            if udt_name == "jsonb":
                table_name = quote(table)
                cursor.execute(
                    f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN geometry TYPE geometry(MultiPolygon, 4326)
                    USING CASE
                        WHEN geometry IS NULL THEN NULL
                        ELSE ST_Multi(
                            ST_Force2D(
                                ST_SetSRID(ST_GeomFromGeoJSON(geometry::text), 4326)
                            )
                        )::geometry(MultiPolygon, 4326)
                    END
                    """
                )
            elif udt_name != "geometry":
                raise RuntimeError(
                    f"Unsupported type for {table}.geometry: {data_type}/{udt_name}"
                )
            else:
                cursor.execute(
                    """
                    SELECT type, srid
                      FROM geometry_columns
                     WHERE f_table_schema = current_schema()
                       AND f_table_name = %s
                       AND f_geometry_column = 'geometry'
                    """,
                    [table],
                )
                geometry_metadata = cursor.fetchone()
                if geometry_metadata != ("MULTIPOLYGON", 4326):
                    raise RuntimeError(
                        f"Unexpected geometry metadata for {table}.geometry: "
                        f"{geometry_metadata}; expected MULTIPOLYGON/4326"
                    )

            cursor.execute(
                """
                SELECT 1
                  FROM pg_indexes
                 WHERE schemaname = current_schema()
                   AND tablename = %s
                   AND indexdef ILIKE '%%USING gist%%'
                   AND indexdef ILIKE '%%(geometry)%%'
                 LIMIT 1
                """,
                [table],
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE INDEX {quote(table + '_geometry_gist')} "
                    f"ON {quote(table)} USING GIST (geometry)"
                )


class Migration(migrations.Migration):
    atomic = True
    dependencies = [("addressing", "0018_official_catalog_and_cnefe_fields")]

    operations = [
        migrations.RunPython(
            reconcile_territory_geometry,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
