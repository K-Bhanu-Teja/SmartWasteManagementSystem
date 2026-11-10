from django.core.management.base import BaseCommand

from workforce.services import process_confirmation_deadlines


class Command(BaseCommand):
    help = "Send task completion reminders and move expired confirmations to administrator review."

    def handle(self, *args, **options):
        counts = process_confirmation_deadlines()
        self.stdout.write(
            self.style.SUCCESS(
                f"Reminders sent: {counts['reminders_sent']}; tasks sent for review: {counts['reviews_created']}."
            )
        )
