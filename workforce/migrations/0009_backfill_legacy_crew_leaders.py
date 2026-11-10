from django.conf import settings
from django.db import migrations


def backfill_crew_leaders(apps, schema_editor):
    Crew = apps.get_model("workforce", "Crew")
    CrewLeaderHistory = apps.get_model("workforce", "CrewLeaderHistory")
    database = schema_editor.connection.alias

    for crew in Crew.objects.using(database).all().iterator():
        if not crew.crew_leader_id:
            continue
        history = CrewLeaderHistory.objects.using(database).create(
            crew_id=crew.pk,
            user_id=crew.crew_leader_id,
            designated_by_id=crew.created_by_id,
            ended_at=None if crew.is_active else crew.dissolved_at,
        )
        CrewLeaderHistory.objects.using(database).filter(pk=history.pk).update(
            designated_at=crew.started_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workforce", "0008_crewleaderhistory"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_crew_leaders, migrations.RunPython.noop),
    ]
