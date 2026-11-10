from django.db import migrations, models


def normalize_public_dustbins(apps, schema_editor):
    Dustbin = apps.get_model("citizen_services", "Dustbin")
    for dustbin in Dustbin.objects.only("pk").iterator():
        Dustbin.objects.filter(pk=dustbin.pk).update(
            name=f"DBno{dustbin.pk}",
            category="public_dustbin",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("citizen_services", "0006_delete_mapdisplaysettings"),
    ]

    operations = [
        migrations.RunPython(normalize_public_dustbins, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="dustbin",
            name="name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="dustbin",
            name="category",
            field=models.CharField(
                choices=[("public_dustbin", "Public dustbin")],
                default="public_dustbin",
                max_length=40,
            ),
        ),
    ]
