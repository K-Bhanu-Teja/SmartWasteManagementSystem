from django.conf import settings
from django.db import migrations


def backfill_crew_memberships(apps, schema_editor):
    Crew = apps.get_model("workforce", "Crew")
    CrewMember = apps.get_model("workforce", "CrewMember")
    CrewVehicle = apps.get_model("workforce", "CrewVehicle")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    database = schema_editor.connection.alias

    for crew in Crew.objects.using(database).all().iterator():
        member_ids = set(crew.cleaners.using(database).values_list("pk", flat=True))
        member_ids.update(user_id for user_id in (crew.driver_id, crew.crew_leader_id) if user_id)
        roles = dict(User.objects.using(database).filter(pk__in=member_ids).values_list("pk", "role"))
        for user_id in member_ids:
            member = CrewMember.objects.using(database).create(
                crew_id=crew.pk,
                user_id=user_id,
                member_type=roles.get(user_id, ""),
                is_active=crew.is_active,
                released_at=None if crew.is_active else crew.dissolved_at,
            )
            CrewMember.objects.using(database).filter(pk=member.pk).update(joined_at=crew.started_at)

        if crew.vehicle_id:
            assignment = CrewVehicle.objects.using(database).create(
                crew_id=crew.pk,
                vehicle_id=crew.vehicle_id,
                is_active=crew.is_active,
                released_at=None if crew.is_active else crew.dissolved_at,
            )
            CrewVehicle.objects.using(database).filter(pk=assignment.pk).update(assigned_at=crew.started_at)


class Migration(migrations.Migration):

    dependencies = [
        ("citizen_services", "0009_pickuprequest_updated_at"),
        ("workforce", "0006_workerlocation_availability"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_crew_memberships, migrations.RunPython.noop),
    ]
