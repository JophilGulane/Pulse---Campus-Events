"""
Management command to create an admin user or promote an existing user to admin.
Usage:
    python manage.py create_admin --username adminuser
    python manage.py create_admin --username adminuser --email admin@example.com
    python manage.py create_admin --username existinguser --promote
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from pulse.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a new admin user or promote an existing user to admin role'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            required=True,
            help='Username for the new user or existing user to promote'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Email address for the new user'
        )
        parser.add_argument(
            '--promote',
            action='store_true',
            help='Promote an existing user to admin instead of creating a new user'
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Password for the new user (if not provided, will prompt)'
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options.get('email')
        promote = options.get('promote', False)
        password = options.get('password')

        try:
            if promote:
                # Promote existing user to admin
                try:
                    user = User.objects.get(username=username)
                    profile, created = UserProfile.objects.get_or_create(user=user)
                    profile.role = UserProfile.Role.ADMIN
                    profile.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully promoted user "{username}" to ADMIN role.')
                    )
                except User.DoesNotExist:
                    raise CommandError(f'User "{username}" does not exist. Use --promote only with existing users.')
            else:
                # Create new admin user
                if User.objects.filter(username=username).exists():
                    raise CommandError(f'User "{username}" already exists. Use --promote to promote them to admin.')

                if not password:
                    from getpass import getpass
                    password = getpass('Password: ')
                    password_confirm = getpass('Password (again): ')
                    if password != password_confirm:
                        raise CommandError('Passwords do not match.')

                # Create user
                user = User.objects.create_user(
                    username=username,
                    email=email or '',
                    password=password
                )

                # Set admin role
                profile, created = UserProfile.objects.get_or_create(user=user)
                profile.role = UserProfile.Role.ADMIN
                profile.save()

                self.stdout.write(
                    self.style.SUCCESS(f'Successfully created admin user "{username}".')
                )

        except Exception as e:
            raise CommandError(f'Error: {str(e)}')

