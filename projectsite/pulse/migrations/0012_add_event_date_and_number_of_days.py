# Generated migration
from django.db import migrations, models
from django.utils import timezone
from datetime import datetime, time as dt_time


def populate_event_date_from_start_datetime(apps, schema_editor):
    """Populate event_date from start_datetime for existing events."""
    Event = apps.get_model('pulse', 'Event')
    for event in Event.objects.all():
        if event.start_datetime:
            event.event_date = event.start_datetime.date()
        else:
            # Fallback to today if no start_datetime
            event.event_date = timezone.now().date()
        event.save(update_fields=['event_date'])


def populate_start_datetime_from_event_date(apps, schema_editor):
    """Reverse migration: populate start_datetime from event_date."""
    Event = apps.get_model('pulse', 'Event')
    for event in Event.objects.all():
        if event.event_date and not event.start_datetime:
            event.start_datetime = timezone.make_aware(
                datetime.combine(event.event_date, dt_time(0, 0, 0))
            )
            event.end_datetime = timezone.make_aware(
                datetime.combine(event.event_date, dt_time(23, 59, 59))
            )
            event.save(update_fields=['start_datetime', 'end_datetime'])


class Migration(migrations.Migration):

    dependencies = [
        ('pulse', '0011_organization_review_notes_organization_reviewed_at_and_more'),
    ]

    operations = [
        # Step 1: Add event_date as nullable
        migrations.AddField(
            model_name='event',
            name='event_date',
            field=models.DateField(null=True, blank=True, help_text='Date of the event. For multi-day events, create separate events for each day.'),
        ),
        # Step 2: Add number_of_days
        migrations.AddField(
            model_name='event',
            name='number_of_days',
            field=models.PositiveIntegerField(default=1, help_text='Number of days for this event. If > 1, separate events will be created for each day.'),
        ),
        # Step 3: Populate event_date from start_datetime
        migrations.RunPython(populate_event_date_from_start_datetime, populate_start_datetime_from_event_date),
        # Step 4: Make start_datetime and end_datetime nullable
        migrations.AlterField(
            model_name='event',
            name='end_datetime',
            field=models.DateTimeField(blank=True, help_text='Auto-calculated from event_date. Used for QR attendance time windows.', null=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='start_datetime',
            field=models.DateTimeField(blank=True, help_text='Auto-calculated from event_date. Used for QR attendance time windows.', null=True),
        ),
        # Step 5: Change registration_deadline to DateField (Django handles conversion automatically)
        migrations.AlterField(
            model_name='event',
            name='registration_deadline',
            field=models.DateField(blank=True, help_text='Registration deadline must be before the event date', null=True),
        ),
        # Step 6: Make event_date non-nullable (after data is populated)
        migrations.AlterField(
            model_name='event',
            name='event_date',
            field=models.DateField(help_text='Date of the event. For multi-day events, create separate events for each day.'),
        ),
    ]
