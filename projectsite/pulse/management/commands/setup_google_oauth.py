"""
Management command to automatically set up Google OAuth SocialApplication.
Run: python manage.py setup_google_oauth
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
import os


class Command(BaseCommand):
    help = 'Set up Google OAuth SocialApplication in the database'

    def handle(self, *args, **options):
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("Google OAuth Setup"))
        self.stdout.write("="*60 + "\n")
        
        # Get credentials from environment
        client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '').strip()
        client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
        
        if not client_id or not client_secret:
            self.stdout.write(self.style.ERROR("❌ Missing Google OAuth credentials!"))
            self.stdout.write("\nPlease set these environment variables:")
            self.stdout.write("  GOOGLE_OAUTH_CLIENT_ID=your-client-id")
            self.stdout.write("  GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret")
            self.stdout.write("\nOr add them to your .env file.\n")
            return
        
        # Get or create the default site
        site, created = Site.objects.get_or_create(
            id=settings.SITE_ID,
            defaults={
                'domain': 'localhost:8000',
                'name': 'Pulse'
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f"✓ Created site: {site.domain}"))
        else:
            self.stdout.write(f"✓ Using existing site: {site.domain}")
        
        # Check if SocialApp already exists
        social_app = SocialApp.objects.filter(provider='google').first()
        
        if social_app:
            # Update existing app
            self.stdout.write("\nFound existing Google SocialApplication. Updating...")
            social_app.client_id = client_id
            social_app.secret = client_secret
            social_app.name = 'Google'
            social_app.save()
            
            # Ensure site is associated
            if site not in social_app.sites.all():
                social_app.sites.add(site)
            
            self.stdout.write(self.style.SUCCESS("✓ Updated Google SocialApplication"))
        else:
            # Create new app
            self.stdout.write("\nCreating Google SocialApplication...")
            social_app = SocialApp.objects.create(
                provider='google',
                name='Google',
                client_id=client_id,
                secret=client_secret,
            )
            social_app.sites.add(site)
            self.stdout.write(self.style.SUCCESS("✓ Created Google SocialApplication"))
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("✓ Google OAuth is now configured!"))
        self.stdout.write("="*60)
        self.stdout.write("\nThe Google OAuth button should now appear on your login page.")
        self.stdout.write("Make sure to restart your Django server if it's running.\n")
