from django.db import migrations


def relax_legacy_account_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    Account = apps.get_model("account", "Account")
    table_name = Account._meta.db_table
    model_columns = {field.column for field in Account._meta.local_fields}
    quoted_table = schema_editor.connection.ops.quote_name(table_name)

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND is_nullable = 'NO'
              AND column_default IS NULL
            """,
            [table_name],
        )
        legacy_columns = [
            column_name
            for (column_name,) in cursor.fetchall()
            if column_name not in model_columns
        ]

        for column_name in legacy_columns:
            quoted_column = schema_editor.connection.ops.quote_name(column_name)
            cursor.execute(f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} DROP NOT NULL")


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0059_private_project_models"),
    ]

    operations = [
        migrations.RunPython(relax_legacy_account_columns, migrations.RunPython.noop),
    ]
