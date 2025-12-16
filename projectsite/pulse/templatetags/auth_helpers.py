"""
Template tags for authentication and role checks.
"""
from django import template

from pulse.models import OrganizationMembership

register = template.Library()


@register.simple_tag(takes_context=True)
def is_admin(context):
    """Safely check if the current user is an admin."""
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False
    
    user = request.user
    if not hasattr(user, 'profile'):
        return False
    
    try:
        return user.profile.is_admin()
    except AttributeError:
        return False


@register.simple_tag(takes_context=True)
def is_super_admin(context):
    """Safely check if the current user is a super admin (Django superuser)."""
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False
    
    return request.user.is_superuser


@register.simple_tag(takes_context=True)
def can_create_event(context):
    """Safely check if the current user can create events (admin or organizer)."""
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False
    
    user = request.user
    if user.is_superuser:
        return True
    
    if not hasattr(user, 'profile'):
        return False
    
    # Admin or Organizer can create events
    if user.profile.is_admin() or user.profile.is_organizer():
        return True
    
    return _user_has_organizer_membership(user)


@register.simple_tag(takes_context=True)
def can_manage_announcements(context):
    """Safely check if the current user can manage announcements (admin or organizer)."""
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False
    
    user = request.user
    if user.is_superuser:
        return True
    
    if not hasattr(user, 'profile'):
        return False
    
    # Admin or Organizer can manage announcements
    if user.profile.is_admin() or user.profile.is_organizer():
        return True
    
    return _user_has_organizer_membership(user)


@register.simple_tag(takes_context=True)
def is_organizer(context):
    """Safely check if the current user is an organizer."""
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False
    
    user = request.user
    if not hasattr(user, 'profile'):
        return False
    
    try:
        if user.profile.is_organizer():
            return True
    except AttributeError:
        return False
    
    return _user_has_organizer_membership(user)


@register.filter
def user_is_admin(user):
    """Filter to check if a user object is an admin."""
    if not user or not user.is_authenticated:
        return False
    
    if not hasattr(user, 'profile'):
        return False
    
    try:
        return user.profile.is_admin()
    except AttributeError:
        return False


def _user_has_organizer_membership(user):
    """Helper to detect organizer access via organization membership."""
    if not user or not user.is_authenticated:
        return False
    
    return OrganizationMembership.objects.filter(
        user=user,
        role=OrganizationMembership.Role.ORGANIZER,
        organization__is_active=True,
    ).exists()


@register.simple_tag(takes_context=True)
def is_org_admin(context):
    """Check if the current user is an organization admin (has ADMIN role in any organization)."""
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False
    
    user = request.user
    return OrganizationMembership.objects.filter(
        user=user,
        role=OrganizationMembership.Role.ADMIN,
        organization__is_active=True,
        organization__status='APPROVED',
    ).exists()


@register.filter
def equals(value, arg):
    """Filter to check if value equals arg."""
    return value == arg


@register.filter
def get_item(list_or_dict, index):
    """Get an item from a list by index or from a dict by key."""
    try:
        if isinstance(list_or_dict, dict):
            return list_or_dict.get(str(index))
        elif isinstance(list_or_dict, (list, tuple)):
            idx = int(index)
            if 0 <= idx < len(list_or_dict):
                return list_or_dict[idx]
    except (ValueError, TypeError, IndexError):
        pass
    return None


@register.filter
def first_char(value):
    """Get the first character of a string, or empty string if None/empty."""
    if value:
        return str(value)[0] if len(str(value)) > 0 else ''
    return ''


@register.filter
def get_initials(user):
    """Get the first character of first_name, or username if first_name is empty."""
    if not user:
        return ''
    if user.first_name:
        return str(user.first_name)[0].upper() if len(str(user.first_name)) > 0 else ''
    if user.username:
        return str(user.username)[0].upper() if len(str(user.username)) > 0 else ''
    return ''


@register.filter
def get_display_name(user):
    """Get the full name of a user, or username if full name is not available."""
    if not user:
        return ''
    full_name = user.get_full_name()
    if full_name and full_name.strip():
        return full_name
    return user.username if user.username else ''

