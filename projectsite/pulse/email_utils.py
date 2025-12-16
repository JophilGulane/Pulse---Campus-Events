"""
Email utility functions for Pulse.
Handles sending verification and reset emails to users.
"""
import logging

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse


logger = logging.getLogger(__name__)


def send_verification_email(user, request=None):
    """
    Send email verification link to a newly registered user.
    
    Args:
        user: The User instance to send verification email to
        request: Optional HttpRequest object to build absolute URLs
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Generate a unique token for this user
        # Django's default_token_generator creates a secure token based on:
        # - User's primary key
        # - User's last login timestamp (or password hash)
        # - SECRET_KEY from settings
        token = default_token_generator.make_token(user)
        
        # Build the verification URL
        # We'll create a view that handles: /accounts/verify-email/<user_id>/<token>/
        verification_path = reverse('verify-email', kwargs={
            'user_id': user.pk,
            'token': token
        })
        
        # Get the site URL from settings (prioritize SITE_URL setting for production)
        # Only use request.build_absolute_uri() as fallback if SITE_URL is not configured
        site_url = getattr(settings, 'SITE_URL', None)
        if not site_url:
            # Fallback to request host if SITE_URL is not set
            if request:
                site_url = request.build_absolute_uri('/')[:-1]  # Remove trailing slash
            else:
                site_url = 'http://localhost:8000'  # Final fallback
        
        # Ensure site_url doesn't have trailing slash
        site_url = site_url.rstrip('/')
        
        verification_url = f"{site_url}{verification_path}"
        
        # Prepare email context
        context = {
            'user': user,
            'verification_url': verification_url,
            'site_name': 'Pulse',
        }
        
        # Render email templates
        # HTML version
        html_message = render_to_string('account/verification_email.html', context)
        # Plain text version (for email clients that don't support HTML)
        plain_message = strip_tags(html_message)
        
        # Send the email
        send_mail(
            subject='Verify your Pulse account',
            message=plain_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'Pulse <noreply@pulse.com>'),
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,  # Raise exception if email fails to send
        )
        
        return True
        
    except Exception as e:
        # Log the error
        logger.error("Error sending verification email to %s: %s", user.email, e)
        return False


def send_password_reset_email(user, request=None):
    """
    Send password reset link to a user who forgot their password.
    
    Args:
        user: The User instance to send password reset email to
        request: Optional HttpRequest object to build absolute URLs
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Generate a unique token for this user
        # Django's default_token_generator creates a secure token based on:
        # - User's primary key
        # - User's last login timestamp (or password hash)
        # - SECRET_KEY from settings
        token = default_token_generator.make_token(user)
        
        # Encode user ID in base64 for URL safety
        from django.utils.http import urlsafe_base64_encode
        from django.contrib.auth import get_user_model
        from django.utils.encoding import force_bytes
        
        User = get_user_model()
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Build the password reset URL
        # Pattern: /accounts/reset-password/<uid>/<token>/
        reset_path = reverse('reset-password', kwargs={
            'uid': uid,
            'token': token
        })
        
        # Get the site URL from settings (prioritize SITE_URL setting for production)
        # Only use request.build_absolute_uri() as fallback if SITE_URL is not configured
        site_url = getattr(settings, 'SITE_URL', None)
        if not site_url:
            # Fallback to request host if SITE_URL is not set
            if request:
                site_url = request.build_absolute_uri('/')[:-1]  # Remove trailing slash
            else:
                site_url = 'http://localhost:8000'  # Final fallback
        
        # Ensure site_url doesn't have trailing slash
        site_url = site_url.rstrip('/')
        
        reset_url = f"{site_url}{reset_path}"
        
        # Prepare email context
        context = {
            'user': user,
            'reset_url': reset_url,
            'site_name': 'Pulse',
            'uid': uid,
            'token': token,
        }
        
        # Render email templates
        # HTML version
        html_message = render_to_string('account/password_reset_email.html', context)
        # Plain text version (for email clients that don't support HTML)
        plain_message = strip_tags(html_message)
        
        # Send the email
        send_mail(
            subject='Reset your Pulse password',
            message=plain_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'Pulse <noreply@pulse.com>'),
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,  # Raise exception if email fails to send
        )
        
        return True
        
    except Exception as e:
        # Log the error
        logger.error("Error sending password reset email to %s: %s", user.email, e)
        return False

