"""
Management command to check Google OAuth configuration.
Run: python manage.py check_google_oauth
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import os
from pathlib import Path


class Command(BaseCommand):
    help = 'Check Google OAuth configuration'

    def handle(self, *args, **options):
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("Google OAuth Configuration Check"))
        self.stdout.write("="*60 + "\n")
        
        # Check .env file locations
        base_dir = Path(settings.BASE_DIR)
        env_paths = [
            base_dir / '.env',
            base_dir.parent / '.env',
            Path.cwd() / '.env',
        ]
        
        self.stdout.write("Checking for .env file:")
        env_found = False
        for env_path in env_paths:
            if env_path.exists():
                self.stdout.write(self.style.SUCCESS(f"  ✓ Found: {env_path}"))
                env_found = True
                break
            else:
                self.stdout.write(self.style.WARNING(f"  ✗ Not found: {env_path}"))
        
        if not env_found:
            self.stdout.write(self.style.ERROR("\n❌ No .env file found!"))
            self.stdout.write("   Create a .env file in one of these locations:")
            for env_path in env_paths:
                self.stdout.write(f"   - {env_path}")
            self.stdout.write("\n   With the following content:")
            self.stdout.write("   GOOGLE_OAUTH_CLIENT_ID=your-client-id-here")
            self.stdout.write("   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret-here\n")
            return
        
        # Check environment variables
        self.stdout.write("\nChecking environment variables:")
        client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '').strip()
        client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
        
        if client_id:
            self.stdout.write(self.style.SUCCESS(f"  ✓ GOOGLE_OAUTH_CLIENT_ID: {client_id[:30]}..."))
        else:
            self.stdout.write(self.style.ERROR("  ✗ GOOGLE_OAUTH_CLIENT_ID: NOT SET"))
        
        if client_secret:
            self.stdout.write(self.style.SUCCESS(f"  ✓ GOOGLE_OAUTH_CLIENT_SECRET: {len(client_secret)} characters"))
        else:
            self.stdout.write(self.style.ERROR("  ✗ GOOGLE_OAUTH_CLIENT_SECRET: NOT SET"))
        
        # Check settings
        self.stdout.write("\nChecking Django settings:")
        if hasattr(settings, 'SOCIALACCOUNT_PROVIDERS'):
            google_config = settings.SOCIALACCOUNT_PROVIDERS.get('google', {})
            app_config = google_config.get('APP', {})
            settings_client_id = app_config.get('client_id', '')
            settings_secret = app_config.get('secret', '')
            
            if settings_client_id:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Settings client_id: {settings_client_id[:30]}..."))
            else:
                self.stdout.write(self.style.ERROR("  ✗ Settings client_id: EMPTY"))
            
            if settings_secret:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Settings secret: {len(settings_secret)} characters"))
            else:
                self.stdout.write(self.style.ERROR("  ✗ Settings secret: EMPTY"))
        
        # Check redirect URIs
        self.stdout.write("\n" + "="*60)
        self.stdout.write("Required Redirect URIs in Google Cloud Console:")
        self.stdout.write("="*60)
        self.stdout.write("Add these EXACT URLs to your Google OAuth Client:")
        self.stdout.write("\n  For local development:")
        self.stdout.write("    http://localhost:8000/accounts/google/login/callback/")
        self.stdout.write("    http://127.0.0.1:8000/accounts/google/login/callback/")
        self.stdout.write("\n  For your domains:")
        for host in settings.ALLOWED_HOSTS:
            if host not in ['localhost', '127.0.0.1', '[::1]']:
                protocol = 'https' if 'ngrok' in host or 'cloudflare' in host else 'http'
                self.stdout.write(f"    {protocol}://{host}/accounts/google/login/callback/")
        
        self.stdout.write("\n" + "="*60)
        if client_id and client_secret:
            self.stdout.write(self.style.SUCCESS("✓ Configuration looks good!"))
            self.stdout.write("\nIf you're still getting 'invalid_client' error:")
            self.stdout.write("  1. Double-check the Client ID and Secret in Google Cloud Console")
            self.stdout.write("  2. Make sure the redirect URIs above are added EXACTLY as shown")
            self.stdout.write("  3. Restart your Django server after updating .env file")
        else:
            self.stdout.write(self.style.ERROR("❌ Configuration incomplete!"))
            self.stdout.write("  Fix the issues above and try again.")
        self.stdout.write("="*60 + "\n")

