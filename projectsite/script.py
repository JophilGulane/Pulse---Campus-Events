import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'projectsite.settings')
django.setup()

from django.db import connection

# List all tables to rename
tables_to_rename = [
    ('eventease_pointstransaction', 'pulse_pointstransaction'),
    ('eventease_announcement', 'pulse_announcement'),
    ('eventease_userprofile', 'pulse_userprofile'),
    ('eventease_registration', 'pulse_registration'),
    ('eventease_organizationinvite', 'pulse_organizationinvite'),
    ('eventease_organizationmembership', 'pulse_organizationmembership'),
    ('eventease_qrcode', 'pulse_qrcode'),
    ('eventease_attendancerecord', 'pulse_attendancerecord'),
    ('eventease_excuse', 'pulse_excuse'),
    ('eventease_organization', 'pulse_organization'),
    ('eventease_event', 'pulse_event'),
]

print("Starting table rename process...")
print("=" * 50)

with connection.cursor() as cursor:
    for old_name, new_name in tables_to_rename:
        try:
            cursor.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
            print(f"✓ {old_name} → {new_name}")
        except Exception as e:
            print(f"✗ Error renaming {old_name}: {e}")

print("=" * 50)
print("✓ Table rename complete!")
print("\nNext steps:")
print("1. Run: python manage.py makemigrations")
print("2. Run: python manage.py migrate --fake")
print("3. Run: python manage.py runserver")