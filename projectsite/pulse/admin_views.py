"""
Views for Super Admin and Admin management features.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, UpdateView, CreateView, DeleteView
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q
from .models import UserProfile, Event, Registration, Announcement
from .forms import AnnouncementForm
from .mixins import (
    SuperAdminRequiredMixin,
    AdminRequiredMixin,
    AdminOrOrganizerRequiredMixin,
    user_has_organizer_membership,
)

User = get_user_model()


# ============================================================================
# SUPER ADMIN VIEWS - Manage Admins
# ============================================================================

class UserManagementView(SuperAdminRequiredMixin, ListView):
    """Super Admin view to manage users and assign roles."""
    model = User
    template_name = 'pulse/admin/user_management.html'
    context_object_name = 'users'
    paginate_by = 20
    
    def get_queryset(self):
        """Filter users based on search query."""
        queryset = User.objects.select_related('profile').all()
        search = self.request.GET.get('search', '')
        role_filter = self.request.GET.get('role', '')
        
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        if role_filter:
            queryset = queryset.filter(profile__role=role_filter)
        
        return queryset.order_by('-date_joined')


class UpdateUserRoleView(SuperAdminRequiredMixin, UpdateView):
    """Super Admin view to update user roles."""
    model = UserProfile
    fields = ['role']
    template_name = 'pulse/admin/update_user_role.html'
    success_url = reverse_lazy('user-management')
    
    def get_object(self):
        """Get UserProfile from User pk."""
        user = User.objects.get(pk=self.kwargs['pk'])
        return user.profile
    
    def form_valid(self, form):
        messages.success(self.request, f'User role updated successfully!')
        return super().form_valid(form)


# ============================================================================
# ADMIN VIEWS - Manage Events and Participants
# ============================================================================

class ManageEventsView(AdminOrOrganizerRequiredMixin, ListView):
    """Admin and Organizer view to manage events."""
    model = Event
    template_name = 'pulse/admin/manage_events.html'
    context_object_name = 'events'
    paginate_by = 20
    
    def get_queryset(self):
        """Show events based on user role."""
        from .views import get_user_organizer_organizations
        user = self.request.user
        
        is_admin_user = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())
        is_organizer_user = (
            (hasattr(user, 'profile') and user.profile.is_organizer()) or
            user_has_organizer_membership(user)
        )
        
        # Super admins and admins see all events
        if is_admin_user:
            queryset = Event.objects.select_related('created_by', 'organization').all()
        elif is_organizer_user:
            # Organizers see events for their organizations only
            organizer_orgs = get_user_organizer_organizations(user)
            queryset = Event.objects.select_related('created_by', 'organization').filter(
                Q(organization__in=organizer_orgs) |
                Q(created_by=user)
            )
        else:
            queryset = Event.objects.none()
        
        search = self.request.GET.get('search', '')
        status_filter = self.request.GET.get('status', '')
        
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(venue__icontains=search)
            )
        
        if status_filter == 'upcoming':
            from django.utils import timezone
            queryset = queryset.filter(start_datetime__gte=timezone.now())
        elif status_filter == 'ongoing':
            from django.utils import timezone
            now = timezone.now()
            queryset = queryset.filter(start_datetime__lte=now, end_datetime__gte=now)
        elif status_filter == 'past':
            from django.utils import timezone
            queryset = queryset.filter(end_datetime__lt=timezone.now())
        
        return queryset.order_by('-pinned', '-start_datetime')


class ManageParticipantsView(AdminOrOrganizerRequiredMixin, ListView):
    """Admin and Organizer view to manage event participants."""
    model = Registration
    template_name = 'pulse/admin/manage_participants.html'
    context_object_name = 'registrations'
    paginate_by = 30
    
    def get_queryset(self):
        """Filter registrations based on user role, event, and status."""
        from .views import get_user_organizer_organizations
        user = self.request.user
        
        is_admin_user = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())
        is_organizer_user = (
            (hasattr(user, 'profile') and user.profile.is_organizer()) or
            user_has_organizer_membership(user)
        )
        
        # Super admins and admins see all registrations
        if is_admin_user:
            queryset = Registration.objects.select_related('event', 'user', 'event__organization').all()
        elif is_organizer_user:
            # Organizers see registrations for their organization's events only
            organizer_orgs = get_user_organizer_organizations(user)
            queryset = Registration.objects.select_related('event', 'user', 'event__organization').filter(
                Q(event__organization__in=organizer_orgs) |
                Q(event__created_by=user)
            )
        else:
            queryset = Registration.objects.none()
        
        event_id = self.request.GET.get('event', '')
        status_filter = self.request.GET.get('status', '')
        self.selected_event = event_id
        self.selected_status = status_filter
        
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-registered_at')
    
    def get_context_data(self, **kwargs):
        """Add events list for filtering."""
        from .views import get_user_organizer_organizations
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_admin_user = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())
        is_organizer_user = (
            (hasattr(user, 'profile') and user.profile.is_organizer()) or
            user_has_organizer_membership(user)
        )
        
        # Filter events based on user role
        if is_admin_user:
            context['events'] = Event.objects.all().order_by('-start_datetime')
        elif is_organizer_user:
            organizer_orgs = get_user_organizer_organizations(user)
            context['events'] = Event.objects.filter(
                Q(organization__in=organizer_orgs) |
                Q(created_by=user)
            ).order_by('-start_datetime')
        else:
            context['events'] = Event.objects.none()

        context['selected_event'] = getattr(self, 'selected_event', '')
        context['selected_status'] = getattr(self, 'selected_status', '')
        context['status_choices'] = [
            ('', 'All Statuses'),
            (Registration.Status.PRE_REGISTERED, 'Pre-Registered'),
            (Registration.Status.CONFIRMED, 'Confirmed'),
            (Registration.Status.ATTENDED, 'Attended'),
            (Registration.Status.CANCELLED, 'Cancelled'),
        ]
        
        return context


class UpdateRegistrationStatusView(AdminRequiredMixin, UpdateView):
    """Admin view to update registration status (confirm, mark attended, etc.)."""
    model = Registration
    fields = ['status', 'notes']
    template_name = 'pulse/admin/update_registration.html'
    
    def get_success_url(self):
        return reverse_lazy('manage-participants')
    
    def form_valid(self, form):
        # Award points if marking as attended
        if form.cleaned_data['status'] == Registration.Status.ATTENDED:
            registration = form.instance
            if registration.status != Registration.Status.ATTENDED:
                # Award points based on event's points setting
                if hasattr(registration.user, 'profile'):
                    points_to_award = registration.event.get_points()
                    registration.mark_attended(award_points=points_to_award, reason="Event Attendance")
        
        messages.success(self.request, 'Registration status updated successfully!')
        return super().form_valid(form)


# ============================================================================
# ANNOUNCEMENT MANAGEMENT
# ============================================================================

class AnnouncementListView(AdminOrOrganizerRequiredMixin, ListView):
    """Admin and Organizer view to manage announcements."""
    model = Announcement
    template_name = 'pulse/admin/announcement_list.html'
    context_object_name = 'announcements'
    paginate_by = 20
    
    def get_queryset(self):
        """Show announcements based on user role."""
        from .views import get_user_organizer_organizations
        user = self.request.user
        
        # Super admins and admins see all announcements
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            queryset = Announcement.objects.select_related('created_by', 'organization').all()
        elif hasattr(user, 'profile') and user.profile.is_organizer():
            # Organizers see announcements for their organizations only
            organizer_orgs = get_user_organizer_organizations(user)
            queryset = Announcement.objects.select_related('created_by', 'organization').filter(
                Q(organization__in=organizer_orgs) |
                Q(created_by=user)
            )
        else:
            queryset = Announcement.objects.none()
        
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search)
            )
        
        return queryset.order_by('-pinned', '-created_at')


class AnnouncementCreateView(AdminOrOrganizerRequiredMixin, CreateView):
    """Admin and Organizer view to create announcements."""
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'pulse/admin/announcement_form.html'
    success_url = reverse_lazy('announcement-list')
    
    def get_form_kwargs(self):
        """Pass user to form for organization filtering."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        
        # Pre-select organization if organizer only organizes one organization
        from .views import get_user_organizer_organizations
        if hasattr(self.request.user, 'profile') and self.request.user.profile.is_organizer():
            organizer_orgs = get_user_organizer_organizations(self.request.user)
            if organizer_orgs.count() == 1:
                kwargs['initial'] = {'organization': organizer_orgs.first()}
        
        return kwargs
    
    def form_valid(self, form):
        """Set the created_by field and validate organization access."""
        from .views import get_user_organizer_organizations
        user = self.request.user
        organization = form.cleaned_data.get('organization')
        
        # Validate that only super admins and admins can create global announcements
        is_admin_user = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())
        if not organization and not is_admin_user:
            form.add_error('organization', 'Only super admins and admins can create global announcements. Please select an organization.')
            return self.form_invalid(form)
        
        # Validate that organizers can only create announcements for their organizations
        if organization and not user.is_superuser:
            if hasattr(user, 'profile') and user.profile.is_organizer() and not user.profile.is_admin():
                organizer_orgs = get_user_organizer_organizations(user)
                if organization not in organizer_orgs:
                    form.add_error('organization', 'You can only create announcements for organizations you organize.')
                    return self.form_invalid(form)
        
        form.instance.created_by = user
        
        # If organizer and no organization selected, ensure they have at least one org
        if not organization and hasattr(user, 'profile') and user.profile.is_organizer() and not user.profile.is_admin():
            organizer_orgs = get_user_organizer_organizations(user)
            if organizer_orgs.exists():
                # Auto-assign first organization if organizer has only one
                if organizer_orgs.count() == 1:
                    form.instance.organization = organizer_orgs.first()
                else:
                    form.add_error('organization', 'Please select an organization for this announcement.')
                    return self.form_invalid(form)
        
        messages.success(self.request, 'Announcement created successfully!')
        return super().form_valid(form)


class AnnouncementUpdateView(AdminOrOrganizerRequiredMixin, UpdateView):
    """Admin and Organizer view to update announcements."""
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'pulse/admin/announcement_form.html'
    success_url = reverse_lazy('announcement-list')
    
    def get_queryset(self):
        """Allow organizers to edit announcements for their organizations."""
        from .views import get_user_organizer_organizations
        user = self.request.user
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            return Announcement.objects.all()
        elif hasattr(user, 'profile') and user.profile.is_organizer():
            organizer_orgs = get_user_organizer_organizations(user)
            return Announcement.objects.filter(
                Q(organization__in=organizer_orgs) |
                Q(created_by=user)
            )
        return Announcement.objects.none()
    
    def get_form_kwargs(self):
        """Pass user to form for organization filtering."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        """Validate organization access for organizers."""
        from .views import get_user_organizer_organizations
        user = self.request.user
        organization = form.cleaned_data.get('organization')
        
        # Validate that organizers can only update announcements for their organizations
        if organization and not user.is_superuser:
            if hasattr(user, 'profile') and user.profile.is_organizer() and not user.profile.is_admin():
                organizer_orgs = get_user_organizer_organizations(user)
                if organization not in organizer_orgs:
                    form.add_error('organization', 'You can only update announcements for organizations you organize.')
                    return self.form_invalid(form)
        
        messages.success(self.request, 'Announcement updated successfully!')
        return super().form_valid(form)


class AnnouncementDeleteView(AdminOrOrganizerRequiredMixin, DeleteView):
    """Admin and Organizer view to delete announcements."""
    model = Announcement
    template_name = 'pulse/admin/announcement_confirm_delete.html'
    success_url = reverse_lazy('announcement-list')
    
    def get_queryset(self):
        """Allow organizers to delete announcements for their organizations."""
        from .views import get_user_organizer_organizations
        user = self.request.user
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            return Announcement.objects.all()
        elif hasattr(user, 'profile') and user.profile.is_organizer():
            organizer_orgs = get_user_organizer_organizations(user)
            return Announcement.objects.filter(
                Q(organization__in=organizer_orgs) |
                Q(created_by=user)
            )
        return Announcement.objects.none()
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Announcement deleted successfully!')
        return super().delete(request, *args, **kwargs)

