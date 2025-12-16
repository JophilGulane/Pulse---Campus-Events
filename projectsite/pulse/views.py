from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, FormView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as AuthLoginView, LogoutView as AuthLogoutView
from django.contrib.auth import login, get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, F, Case, When, IntegerField, Sum, Count
from datetime import datetime
from .models import Event, Announcement, UserProfile, Registration, Organization, OrganizationMembership, AttendanceRecord, Excuse
from .forms import EventForm, CustomUserCreationForm, ExcuseForm, ExcuseReviewForm, UsernameChangeForm, ProfileAvatarForm

User = get_user_model()
from .mixins import AdminRequiredMixin, SuperAdminRequiredMixin, AdminOrOrganizerRequiredMixin


def get_user_organizations(user):
    """Helper function to get all organizations a user belongs to."""
    if not user.is_authenticated:
        return []
    return Organization.objects.filter(
        memberships__user=user,
        is_active=True
    ).distinct()


def get_user_organizer_organizations(user):
    """Helper function to get organizations a user organizes."""
    if not user.is_authenticated:
        return []
    return Organization.objects.filter(
        memberships__user=user,
        memberships__role=OrganizationMembership.Role.ORGANIZER,
        is_active=True
    ).distinct()


def can_user_view_event(user, event):
    """Check if user can view a specific event."""
    # Super admins can see everything
    if user.is_superuser:
        return True
    
    # Global events (no organization) - all authenticated users can see if public
    if not event.organization:
        return event.is_public or (hasattr(user, 'profile') and user.profile.is_admin())
    
    # Organization events - user must be member of that organization
    user_orgs = get_user_organizations(user)
    if event.organization in user_orgs:
        return True
    
    # Admins can see all organization events
    if hasattr(user, 'profile') and user.profile.is_admin():
        return True
    
    return False


def can_user_view_announcement(user, announcement):
    """Check if user can view a specific announcement."""
    # Super admins can see everything
    if user.is_superuser:
        return True
    
    # Global announcements (no organization) - all authenticated users can see
    if not announcement.organization:
        return True
    
    # Organization announcements - user must be member of that organization
    user_orgs = get_user_organizations(user)
    if announcement.organization in user_orgs:
        return True
    
    # Admins can see all organization announcements
    if hasattr(user, 'profile') and user.profile.is_admin():
        return True
    
    return False

# Create your views here.

class OrganizerDashboardView(AdminOrOrganizerRequiredMixin, TemplateView):
    """Dashboard for organizers to manage their organization's events and announcements."""
    template_name = 'pulse/organizer_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Check if user is super admin
        is_superuser = user.is_superuser
        
        # Get organizations the user organizes
        organizer_orgs = get_user_organizer_organizations(user)
        
        # For super admins, get all active organizations
        if is_superuser:
            all_orgs = Organization.objects.filter(is_active=True)
            organizer_orgs = all_orgs
        
        # Get events for these organizations
        events = Event.objects.select_related('organization', 'created_by').filter(
            Q(organization__in=organizer_orgs) |
            Q(created_by=user)
        ).order_by('-start_datetime')
        
        # Get announcements for these organizations
        announcements = Announcement.objects.select_related('organization', 'created_by').filter(
            Q(organization__in=organizer_orgs) |
            Q(created_by=user)
        ).order_by('-pinned', '-created_at')
        
        # Calculate stats
        now = timezone.now()
        upcoming_events = events.filter(start_datetime__gte=now)
        ongoing_events = events.filter(start_datetime__lte=now, end_datetime__gte=now)
        past_events = events.filter(end_datetime__lt=now)
        active_announcements = announcements.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gte=now)
        )
        
        # Get total registrations for upcoming events
        total_registrations = Registration.objects.filter(
            event__in=upcoming_events,
            status__in=[Registration.Status.PRE_REGISTERED, Registration.Status.CONFIRMED, Registration.Status.ATTENDED]
        ).count()
        
        # Organizer member management filters
        member_search = self.request.GET.get('member_search', '').strip()
        member_org_filter = self.request.GET.get('member_org', 'all')
        member_role_filter = self.request.GET.get('member_role', '')

        member_results = []
        memberships_qs = OrganizationMembership.objects.none()
        total_scans_per_org = {}
        attendance_map = {}

        if organizer_orgs.exists():
            memberships_qs = OrganizationMembership.objects.filter(
                organization__in=organizer_orgs
            ).select_related('user', 'organization').order_by('organization__name', 'user__username')

            if member_org_filter and member_org_filter != 'all':
                try:
                    org_id = int(member_org_filter)
                    memberships_qs = memberships_qs.filter(organization_id=org_id)
                except ValueError:
                    pass

            if member_role_filter in dict(OrganizationMembership.Role.choices):
                memberships_qs = memberships_qs.filter(role=member_role_filter)

            if member_search:
                memberships_qs = memberships_qs.filter(
                    Q(user__first_name__icontains=member_search) |
                    Q(user__last_name__icontains=member_search) |
                    Q(user__username__icontains=member_search) |
                    Q(user__email__icontains=member_search)
                )

            membership_list = list(memberships_qs)

            if membership_list:
                org_ids = {membership.organization_id for membership in membership_list}
                user_ids = {membership.user_id for membership in membership_list}

                mandatory_events = Event.objects.filter(
                    organization_id__in=org_ids,
                    event_type=Event.EventType.MANDATORY
                ).values(
                    'id',
                    'organization_id',
                    'enable_morning_in',
                    'enable_morning_out',
                    'enable_afternoon_in',
                    'enable_afternoon_out',
                )

                for event in mandatory_events:
                    scans_for_event = sum([
                        1 if event['enable_morning_in'] else 0,
                        1 if event['enable_morning_out'] else 0,
                        1 if event['enable_afternoon_in'] else 0,
                        1 if event['enable_afternoon_out'] else 0,
                    ])
                    total_scans_per_org[event['organization_id']] = total_scans_per_org.get(event['organization_id'], 0) + scans_for_event

                attendance = AttendanceRecord.objects.filter(
                    event__organization_id__in=org_ids,
                    event__event_type=Event.EventType.MANDATORY,
                    user_id__in=user_ids
                ).values('user_id', 'event__organization_id').annotate(
                    scans=Count('id'),
                    points=Sum('points_awarded')
                )

                attendance_map = {
                    (item['user_id'], item['event__organization_id']): item for item in attendance
                }

                for membership in membership_list:
                    stats = attendance_map.get((membership.user_id, membership.organization_id), {})
                    total_scans = total_scans_per_org.get(membership.organization_id, 0)
                    scans = stats.get('scans', 0)
                    points = stats.get('points', 0) or 0
                    score_percent = round((scans / total_scans) * 100, 1) if total_scans else 0

                    member_results.append({
                        'membership': membership,
                        'organization': membership.organization,
                        'user': membership.user,
                        'role': membership.role,
                        'joined_at': membership.joined_at,
                        'scans': scans,
                        'max_scans': total_scans,
                        'points': points,
                        'score_percent': score_percent,
                    })

        context.update({
            'organizations': organizer_orgs,
            'events': events[:10],  # Show latest 10 events
            'announcements': announcements[:10],  # Show latest 10 announcements
            'upcoming_events_count': upcoming_events.count(),
            'ongoing_events_count': ongoing_events.count(),
            'past_events_count': past_events.count(),
            'active_announcements_count': active_announcements.count(),
            'total_registrations': total_registrations,
            'is_organizer': hasattr(user, 'profile') and user.profile.is_organizer(),
            'is_admin': user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()),
            'member_results': member_results,
            'member_results_count': len(member_results),
            'member_search': member_search,
            'member_org_filter': member_org_filter,
            'member_role_filter': member_role_filter,
            'member_org_options': organizer_orgs,
            'role_choices': OrganizationMembership.Role.choices,
        })

        return context


class LandingPageView(ListView):
    """Display landing page with featured events."""
    model = Event
    template_name = 'landing.html'
    context_object_name = 'landing'
    allow_empty = True
    
    def get_queryset(self):
        """Return top 3 upcoming and ongoing events, prioritized by points."""
        now = timezone.now()
        user = self.request.user if hasattr(self.request, 'user') and self.request.user.is_authenticated else None
        
        # Base filter: events that haven't ended yet
        events = Event.objects.filter(
            end_datetime__gte=now
        )
        
        # Filter by organization membership if user is authenticated
        if user and user.is_authenticated:
            user_orgs = get_user_organizations(user)
            # Show global public events OR events from user's organizations
            # For non-authenticated users, only show global public events
            events = events.filter(
                Q(organization__isnull=True, is_public=True) |
                Q(organization__in=user_orgs)
            )
        else:
            # Non-authenticated users only see global public events
            events = events.filter(
                organization__isnull=True,
                is_public=True
            )
        
        # Annotate with points value (use 10 as default if null)
        events = events.annotate(
            points_value=Case(
                When(points__isnull=False, then=F('points')),
                default=10,
                output_field=IntegerField()
            )
        ).order_by(
            '-pinned',  # Pinned events first
            '-points_value',  # Then by points (highest first)
            'start_datetime'  # Finally by start date
        )[:3]  # Limit to 3 events
        
        return events


# Event CRUD Views
class EventListView(LoginRequiredMixin, ListView):
    """List all public events. Requires login."""
    model = Event
    template_name = 'pulse/event_list.html'
    context_object_name = 'events'
    paginate_by = 12
    
    def get_queryset(self):
        """Return events based on user role and organization membership."""
        user = self.request.user
        user_orgs = get_user_organizations(user)
        
        # Super admins and admins can see all events
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            queryset = Event.objects.select_related('organization', 'created_by').all()
        else:
            # Regular users see:
            # 1. Global events (organization=None) that are public
            # 2. Events from their organizations
            queryset = Event.objects.select_related('organization', 'created_by').filter(
                Q(organization__isnull=True, is_public=True) |
                Q(organization__in=user_orgs)
            )
        
        # Filter by upcoming/past/ongoing if requested
        filter_type = self.request.GET.get('filter', 'all')
        now = timezone.now()
        
        if filter_type == 'upcoming':
            queryset = queryset.filter(start_datetime__gte=now)
        elif filter_type == 'past':
            queryset = queryset.filter(end_datetime__lt=now)
        elif filter_type == 'ongoing':
            queryset = queryset.filter(start_datetime__lte=now, end_datetime__gte=now)
        
        # Filter by organization
        org_filter = self.request.GET.get('organization', '')
        if org_filter:
            if org_filter == 'global':
                queryset = queryset.filter(organization__isnull=True)
            else:
                try:
                    queryset = queryset.filter(organization_id=org_filter)
                except ValueError:
                    pass
        
        # Filter by event type
        event_type_filter = self.request.GET.get('event_type', '')
        if event_type_filter in ['MANDATORY', 'OPTIONAL']:
            queryset = queryset.filter(event_type=event_type_filter)
        
        # Search filter
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(venue__icontains=search)
            )
        
        return queryset.order_by('-pinned', '-start_datetime')
    
    def get_context_data(self, **kwargs):
        """Add current time and filter options to context for template comparisons."""
        context = super().get_context_data(**kwargs)
        context['now'] = timezone.localtime(timezone.now())
        
        # Get user organizations for filter dropdown
        user = self.request.user
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            context['organizations'] = Organization.objects.filter(is_active=True).order_by('name')
        else:
            context['organizations'] = get_user_organizations(user)
        
        # Add current filter values to context
        context['current_filter'] = self.request.GET.get('filter', 'all')
        context['current_org'] = self.request.GET.get('organization', '')
        context['current_event_type'] = self.request.GET.get('event_type', '')
        context['current_search'] = self.request.GET.get('search', '')
        
        return context


class EventDetailView(LoginRequiredMixin, DetailView):
    """Display detailed view of a single event. Requires login."""
    model = Event
    template_name = 'pulse/event_detail.html'
    context_object_name = 'event'
    
    def get_queryset(self):
        """Allow viewing events based on organization membership and permissions."""
        user = self.request.user
        
        # Super admins and admins can see all events
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            return Event.objects.all()
        
        # Regular users can see:
        # 1. Global public events
        # 2. Events from their organizations
        # 3. Events they created
        user_orgs = get_user_organizations(user)
        return Event.objects.filter(
            Q(organization__isnull=True, is_public=True) |
            Q(organization__in=user_orgs) |
            Q(created_by=user)
        )
    
    def get_context_data(self, **kwargs):
        """Add registration status for the logged-in user."""
        context = super().get_context_data(**kwargs)
        event = context['event']
        
        # Check for excuse submission success
        excuse_submitted = self.request.session.pop('excuse_submitted', None)
        if excuse_submitted:
            context['excuse_submitted'] = True
        
        # User is always authenticated (LoginRequiredMixin ensures this)
        try:
            registration = Registration.objects.get(
                event=event,
                user=self.request.user
            )
            context['user_registration'] = registration
            context['is_registered'] = True
            # Get status display, ensure it's not empty
            status_display = registration.get_status_display()
            context['registration_status'] = status_display if status_display else "Pre-registered"
        except Registration.DoesNotExist:
            context['is_registered'] = False
            context['registration_status'] = None
        
        # Check if registration is still possible
        now = timezone.now()
        is_registered = context.get('is_registered', False)
        
        # Check registration deadline (compare dates)
        registration_deadline_passed = False
        if event.registration_deadline:
            if isinstance(event.registration_deadline, datetime):
                deadline_date = event.registration_deadline.date()
            else:
                deadline_date = event.registration_deadline
            registration_deadline_passed = deadline_date < now.date()
        
        # Check if event date has passed
        event_passed = False
        if event.event_date:
            event_passed = event.event_date < now.date()
        elif event.start_datetime:
            event_passed = event.start_datetime < now
        
        # For optional events, allow registration if user can see the event (already checked in queryset)
        # For mandatory events, they're auto-registered, so this mainly applies to optional events
        can_register = (
            not is_registered and  # User is not already registered
            not event.is_mandatory() and  # Only optional events can be manually registered
            not registration_deadline_passed and  # Registration deadline hasn't passed
            not event_passed and  # Event hasn't passed
            not event.is_full()  # Event isn't full
        )
        
        context['can_register'] = can_register
        
        # Provide specific reason why registration isn't available (for debugging/UI)
        if not can_register and not is_registered:
            if event.is_mandatory():
                context['registration_unavailable_reason'] = "This is a mandatory event. You are automatically registered."
            elif registration_deadline_passed:
                context['registration_unavailable_reason'] = "Registration deadline has passed."
            elif event_passed:
                context['registration_unavailable_reason'] = "This event has already passed."
            elif event.is_full():
                context['registration_unavailable_reason'] = "This event is full."
            else:
                context['registration_unavailable_reason'] = "Registration is currently unavailable."
        else:
            context['registration_unavailable_reason'] = None
        
        # Add current time for debugging
        try:
            from django.utils.timezone import localdate
            context['current_date'] = localdate()
        except ImportError:
            context['current_date'] = now.date()
        context['current_time'] = now
        context['event_date'] = event.event_date
        
        return context


class EventCreateView(AdminOrOrganizerRequiredMixin, CreateView):
    """Create a new event. Admin and Organizers can create events."""
    model = Event
    form_class = EventForm
    template_name = 'pulse/event_form.html'
    success_url = reverse_lazy('event-list')
    
    def get_form_kwargs(self):
        """Pass user to form for organization filtering."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        
        # Pre-select organization if organizer only organizes one organization
        if hasattr(self.request.user, 'profile') and self.request.user.profile.is_organizer():
            organizer_orgs = get_user_organizer_organizations(self.request.user)
            if organizer_orgs.count() == 1:
                kwargs['initial'] = {'organization': organizer_orgs.first()}
        
        return kwargs
    
    def form_valid(self, form):
        """Set the created_by field, validate organization access."""
        user = self.request.user
        organization = form.cleaned_data.get('organization')
        
        # Validate that only super admins and admins can create global events
        is_admin_user = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())
        if not organization and not is_admin_user:
            form.add_error('organization', 'Only super admins and admins can create global events. Please select an organization.')
            return self.form_invalid(form)
        
        # Validate that organizers can only create events for their organizations
        if organization and not user.is_superuser:
            if hasattr(user, 'profile') and user.profile.is_organizer() and not user.profile.is_admin():
                organizer_orgs = get_user_organizer_organizations(user)
                if organization not in organizer_orgs:
                    form.add_error('organization', 'You can only create events for organizations you organize.')
                    return self.form_invalid(form)
        
        # If organizer and no organization selected, ensure they have at least one org
        if not organization and hasattr(user, 'profile') and user.profile.is_organizer() and not user.profile.is_admin():
            organizer_orgs = get_user_organizer_organizations(user)
            if organizer_orgs.exists():
                # Auto-assign first organization if organizer has only one
                if organizer_orgs.count() == 1:
                    organization = organizer_orgs.first()
                else:
                    form.add_error('organization', 'Please select an organization for this event.')
                    return self.form_invalid(form)
        
        # Create event instance
        event = form.save(commit=False)
        event.created_by = user
        event.organization = organization
        
        # Save the event (this will auto-calculate start_datetime/end_datetime only if not manually set)
        event.save()
        form.save_m2m()
        
        messages.success(self.request, 'Event created successfully!')
        
        # Redirect to the created event
        return redirect('event-detail', pk=event.pk)


class EventUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing event."""
    model = Event
    form_class = EventForm
    template_name = 'pulse/event_form.html'
    success_url = reverse_lazy('event-list')
    
    def get_queryset(self):
        """Allow Admin/Organizer to edit events, or users to edit their own."""
        user = self.request.user
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            return Event.objects.all()
        elif hasattr(user, 'profile') and user.profile.is_organizer():
            # Organizers can edit events for their organizations
            organizer_orgs = get_user_organizer_organizations(user)
            return Event.objects.filter(
                Q(organization__in=organizer_orgs) |
                Q(created_by=user)
            )
        return Event.objects.filter(created_by=self.request.user)
    
    def get_form_kwargs(self):
        """Pass user to form for organization filtering."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        """Validate organization access for organizers and handle event_date updates."""
        user = self.request.user
        organization = form.cleaned_data.get('organization')
        
        # Validate that organizers can only update events for their organizations
        if organization and not user.is_superuser:
            if hasattr(user, 'profile') and user.profile.is_organizer() and not user.profile.is_admin():
                organizer_orgs = get_user_organizer_organizations(user)
                if organization not in organizer_orgs:
                    form.add_error('organization', 'You can only update events for organizations you organize.')
                    return self.form_invalid(form)
        
        # Get the event instance
        event = form.save(commit=False)
        
        # If event_date changed, we need to recalculate start_datetime and end_datetime
        # The save() method will handle this, but we need to ensure it's triggered
        if 'event_date' in form.changed_data:
            # Force recalculation by clearing the datetime fields
            # The save() method will recalculate them from event_date
            event.start_datetime = None
            event.end_datetime = None
        
        # Save the event (this will trigger the save() method which recalculates datetimes)
        event.save()
        form.save_m2m()
        
        messages.success(self.request, 'Event updated successfully!')
        return redirect('event-detail', pk=event.pk)


class EventDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an event."""
    model = Event
    template_name = 'pulse/event_confirm_delete.html'
    success_url = reverse_lazy('event-list')
    
    def get_queryset(self):
        """Allow Admin to delete any event, or users to delete their own."""
        if hasattr(self.request.user, 'profile') and self.request.user.profile.is_admin():
            return Event.objects.all()
        return Event.objects.filter(created_by=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Event deleted successfully!')
        return super().delete(request, *args, **kwargs)


# ============================================================================
# ANNOUNCEMENTS/NEWSFEED VIEW
# ============================================================================

class AnnouncementsNewsfeedView(LoginRequiredMixin, ListView):
    """Display page showing only announcements. Requires login."""
    model = Announcement
    template_name = 'pulse/announcements_newsfeed.html'
    context_object_name = 'announcements'
    paginate_by = 20
    
    def get_queryset(self):
        """Return active announcements based on organization membership."""
        user = self.request.user
        user_orgs = get_user_organizations(user)
        now = timezone.now()
        
        # Super admins and admins can see all announcements
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            queryset = Announcement.objects.select_related('organization', 'created_by').all()
        else:
            # Regular users see:
            # 1. Global announcements (organization=None)
            # 2. Announcements from their organizations
            queryset = Announcement.objects.select_related('organization', 'created_by').filter(
                Q(organization__isnull=True) |
                Q(organization__in=user_orgs)
            )
        
        # Filter by active/expired
        filter_type = self.request.GET.get('filter', 'active')
        if filter_type == 'active':
            queryset = queryset.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
        elif filter_type == 'expired':
            queryset = queryset.filter(expires_at__lte=now)
        elif filter_type == 'all':
            pass  # Show all
        
        # Filter by organization
        org_filter = self.request.GET.get('organization', '')
        if org_filter:
            if org_filter == 'global':
                queryset = queryset.filter(organization__isnull=True)
            else:
                try:
                    queryset = queryset.filter(organization_id=org_filter)
                except ValueError:
                    pass
        
        # Filter by pinned
        pinned_filter = self.request.GET.get('pinned', '')
        if pinned_filter == 'yes':
            queryset = queryset.filter(pinned=True)
        elif pinned_filter == 'no':
            queryset = queryset.filter(pinned=False)
        
        # Search filter
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search)
            )
        
        return queryset.order_by('-pinned', '-created_at')
    
    def get_context_data(self, **kwargs):
        """Add filter options to context."""
        context = super().get_context_data(**kwargs)
        context['now'] = timezone.now()
        
        # Get user organizations for filter dropdown
        user = self.request.user
        if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin()):
            context['organizations'] = Organization.objects.filter(is_active=True).order_by('name')
        else:
            context['organizations'] = get_user_organizations(user)
        
        # Add current filter values to context
        context['current_filter'] = self.request.GET.get('filter', 'active')
        context['current_org'] = self.request.GET.get('organization', '')
        context['current_pinned'] = self.request.GET.get('pinned', '')
        context['current_search'] = self.request.GET.get('search', '')
        
        return context


# ============================================================================
# LEADERBOARD VIEW
# ============================================================================

class LeaderboardView(ListView):
    """Display leaderboard of users ranked by points, optionally scoped to an organization."""
    model = UserProfile
    template_name = 'pulse/leaderboard.html'
    context_object_name = 'profiles'
    paginate_by = 25
    
    def get_queryset(self):
        """
        Return user profiles ordered by points for the selected organization
        (or global total_points when no organization is selected).
        """
        from .models import OrganizationMembership, AttendanceRecord, Event, Organization

        queryset = UserProfile.objects.select_related('user').filter(
            user__is_active=True
        )

        org_id = self.request.GET.get('organization')
        self.selected_org = None

        if org_id:
            try:
                self.selected_org = Organization.objects.get(pk=int(org_id), is_active=True)
            except (Organization.DoesNotExist, ValueError):
                self.selected_org = None

        if self.selected_org:
            # Rank based on points earned from events in this organization only
            # First, filter to only include users who are members of this organization
            from .models import OrganizationMembership
            from django.db.models import Sum
            
            # Get user IDs who are members of this organization
            org_member_ids = list(OrganizationMembership.objects.filter(
                organization=self.selected_org,
                user__is_active=True
            ).values_list('user_id', flat=True))
            
            if not org_member_ids:
                # No members in this organization, return empty queryset
                return UserProfile.objects.none()
            
            # Filter queryset to only include organization members
            queryset = queryset.filter(user_id__in=org_member_ids)

            attendance = AttendanceRecord.objects.filter(
                event__organization=self.selected_org,
                user_id__in=org_member_ids,
                user__is_active=True,
            ).values('user_id').annotate(org_points=Sum('points_awarded'))

            points_map = {row['user_id']: row['org_points'] or 0 for row in attendance}

            # Attach org_points attribute for ranking; default 0 for users without records
            profiles = list(queryset)
            for profile in profiles:
                profile.org_points = points_map.get(profile.user_id, 0)

            # Sort by org_points then username
            profiles.sort(key=lambda p: (-getattr(p, 'org_points', 0), p.user.username))
            return profiles

        # Global leaderboard by total_points
        return queryset.order_by('-total_points', 'user__username')
    
    def get_context_data(self, **kwargs):
        """Add current user's rank, position, and organization filter options."""
        from .models import Organization, OrganizationMembership

        context = super().get_context_data(**kwargs)
        
        # Calculate ranks for displayed users
        queryset = self.get_queryset()
        page_obj = context['page_obj']
        
        # Calculate ranks for all profiles (handling ties correctly)
        all_profiles = list(queryset)
        rank_map = {}  # Maps profile ID to rank
        current_rank = 1
        
        for idx, profile in enumerate(all_profiles):
            # If this profile has different points than the previous one, update rank
            prev_points = getattr(all_profiles[idx-1], 'org_points', all_profiles[idx-1].total_points) if idx > 0 else None
            this_points = getattr(profile, 'org_points', profile.total_points)
            if idx > 0 and prev_points != this_points:
                current_rank = idx + 1
            rank_map[profile.id] = current_rank
        
        # Build list for current page only
        profiles_with_rank = []
        for profile in page_obj:
            profiles_with_rank.append({
                'profile': profile,
                'rank': rank_map.get(profile.id, 1),
                'is_current_user': self.request.user.is_authenticated and 
                                  hasattr(self.request.user, 'profile') and
                                  profile.user == self.request.user,
            })
        
        context['profiles_with_rank'] = profiles_with_rank
        
        # Get current user's rank if authenticated
        if self.request.user.is_authenticated and hasattr(self.request.user, 'profile'):
            user_profile = self.request.user.profile
            if user_profile.id in rank_map:
                context['user_rank'] = rank_map[user_profile.id]
                # Attach org_points for header display when scoped to an organization
                if getattr(self, 'selected_org', None):
                    matched = next((p for p in all_profiles if p.id == user_profile.id), None)
                    if matched is not None and hasattr(matched, 'org_points'):
                        user_profile.org_points = matched.org_points
                context['user_profile'] = user_profile
        
        # Get top 3 for podium display - pass as separate variables for easier template access
        top_3_list = all_profiles[:3] if len(all_profiles) >= 3 else all_profiles
        context['top_3_list'] = top_3_list
        # Also pass as individual variables for direct access
        if len(top_3_list) > 0:
            context['top_1'] = top_3_list[0]
        if len(top_3_list) > 1:
            context['top_2'] = top_3_list[1]
        if len(top_3_list) > 2:
            context['top_3'] = top_3_list[2]

        # Organization filter options
        user = self.request.user
        selected_org_id = None
        if getattr(self, 'selected_org', None):
            selected_org_id = self.selected_org.id

        if user.is_authenticated and (user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())):
            org_options = Organization.objects.filter(is_active=True).order_by('name')
        elif user.is_authenticated:
            org_options = Organization.objects.filter(
                memberships__user=user,
                memberships__role=OrganizationMembership.Role.ORGANIZER,
                is_active=True,
            ).distinct().order_by('name')
        else:
            org_options = Organization.objects.none()

        context['organizations'] = org_options
        context['selected_org'] = self.selected_org
        # Ensure selected_org_id is an integer (or None) for template comparison
        context['selected_org_id'] = selected_org_id
        
        return context


# ============================================================================
# AUTHENTICATION VIEWS
# ============================================================================

class SignUpView(CreateView):
    """
    User registration view with email verification.
    Creates inactive users and sends verification email.
    """
    form_class = CustomUserCreationForm
    template_name = 'account/signup.html'
    success_url = reverse_lazy('verification-sent')
    
    def dispatch(self, request, *args, **kwargs):
        """Redirect authenticated users."""
        if request.user.is_authenticated:
            return redirect('landing')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        """
        After successful signup:
        1. Create user as inactive (is_active=False)
        2. Send verification email
        3. Redirect to verification sent page
        """
        # Save the user but don't commit yet so we can modify it
        user = form.save(commit=False)
        # Set user as inactive - they need to verify email first
        user.is_active = False
        user.save()
        
        # UserProfile is created automatically via signal
        
        # Import here to avoid circular imports
        from pulse.email_utils import send_verification_email
        
        # Send verification email
        email_sent = send_verification_email(user, self.request)
        
        if email_sent:
            messages.success(
                self.request,
                f'Account created! Please check your email ({user.email}) to verify your account.'
            )
        else:
            messages.warning(
                self.request,
                'Account created, but we couldn\'t send the verification email. '
                'Please contact support or try logging in to resend.'
            )
        
        # Don't log the user in - they need to verify first
        return redirect('verification-sent')


class VerificationSentView(TemplateView):
    """
    Display a message that verification email has been sent.
    Shown after successful signup.
    """
    template_name = 'account/verification_sent.html'


class VerifyEmailView(View):
    """
    Email verification view.
    Activates user account when they click the verification link.
    
    URL pattern: /accounts/verify-email/<user_id>/<token>/
    """
    def get(self, request, user_id, token):
        """
        Handle GET request from verification email link.
        
        Args:
            user_id: Primary key of the user to verify
            token: Verification token generated by default_token_generator
        """
        from django.contrib.auth import get_user_model
        from django.contrib.auth.tokens import default_token_generator
        
        User = get_user_model()
        
        try:
            # Get the user by ID
            user = get_object_or_404(User, pk=user_id)
            
            # Check if user is already verified
            if user.is_active:
                messages.info(
                    request,
                    'Your email is already verified. You can log in now.'
                )
                return redirect('login')
            
            # Verify the token
            # default_token_generator.check_token() validates:
            # - Token matches the user
            # - Token hasn't expired (tokens are invalidated when password changes)
            if default_token_generator.check_token(user, token):
                # Token is valid - activate the user
                user.is_active = True
                user.save()
                
                messages.success(
                    request,
                    f'Email verified successfully! Welcome to Pulse, {user.username}! You can now log in.'
                )
                return redirect('login')
            else:
                # Token is invalid or expired
                messages.error(
                    request,
                    'Invalid or expired verification link. Please request a new verification email.'
                )
                return render(request, 'account/verification_error.html', {
                    'error': 'invalid_token'
                })
                
        except Exception as e:
            # Handle any unexpected errors
            messages.error(
                request,
                'An error occurred during verification. Please try again or contact support.'
            )
            return render(request, 'account/verification_error.html', {
                'error': 'server_error'
            })


class ResendVerificationView(View):
    """
    View to resend verification email.
    Useful if user didn't receive the initial email or link expired.
    """
    def post(self, request):
        """Handle POST request to resend verification email."""
        from django.contrib.auth import get_user_model
        from pulse.email_utils import send_verification_email
        
        User = get_user_model()
        email = request.POST.get('email', '').strip()
        
        if not email:
            messages.error(request, 'Please provide your email address.')
            return redirect('resend-verification')
        
        try:
            user = User.objects.get(email=email)
            
            # Check if already verified
            if user.is_active:
                messages.info(
                    request,
                    'This email is already verified. You can log in now.'
                )
                return redirect('login')
            
            # Resend verification email
            email_sent = send_verification_email(user, request)
            
            if email_sent:
                messages.success(
                    request,
                    f'Verification email sent to {user.email}. Please check your inbox.'
                )
            else:
                messages.error(
                    request,
                    'Failed to send verification email. Please try again later or contact support.'
                )
            
            return redirect('verification-sent')
            
        except User.DoesNotExist:
            # Don't reveal if email exists or not (security best practice)
            messages.success(
                request,
                'If an account with that email exists and is unverified, a verification email has been sent.'
            )
            return redirect('verification-sent')
        except Exception as e:
            messages.error(
                request,
                'An error occurred. Please try again later.'
            )
            return redirect('resend-verification')
    
    def get(self, request):
        """Display form to resend verification email."""
        return render(request, 'account/resend_verification.html')


class LoginView(AuthLoginView):
    """
    Custom login view with redirect to landing page.
    Also checks if user account is active (verified).
    """
    template_name = 'account/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        """Redirect to landing page after login."""
        return reverse_lazy('landing')
    
    def form_valid(self, form):
        """
        Override to check if user account is active before logging in.
        """
        # Get the user from the form
        user = form.get_user()
        
        # Check if user account is active (email verified)
        if not user.is_active:
            # User exists but email is not verified
            messages.warning(
                self.request,
                'Your account is not yet activated. Please check your email and click the verification link. '
                'If you didn\'t receive the email, you can request a new one.'
            )
            # Redirect to resend verification page
            return redirect('resend-verification')
        
        # User is active - proceed with normal login
        return super().form_valid(form)
    
    def form_invalid(self, form):
        """Add error message for invalid login."""
        messages.error(self.request, 'Invalid username or password. Please try again.')
        return super().form_invalid(form)


class ForgotPasswordView(View):
    """
    View to handle forgot password requests.
    Users enter their email and receive a password reset link.
    """
    def post(self, request):
        """Handle POST request to send password reset email."""
        from django.contrib.auth import get_user_model
        from pulse.email_utils import send_password_reset_email
        
        User = get_user_model()
        email = request.POST.get('email', '').strip()
        
        if not email:
            messages.error(request, 'Please provide your email address.')
            return redirect('forgot-password')
        
        try:
            # Find user by email (case-insensitive)
            user = User.objects.get(email__iexact=email)
            
            # Only allow password reset for active users
            if not user.is_active:
                # Don't reveal if account exists or is inactive (security best practice)
                messages.success(
                    request,
                    'If an account with that email exists, a password reset email has been sent.'
                )
                return redirect('password-reset-sent')
            
            # Check if user has a usable password
            if not user.has_usable_password():
                messages.error(
                    request,
                    'This account does not have a password set. Please contact support.'
                )
                return redirect('forgot-password')
            
            # Send password reset email
            email_sent = send_password_reset_email(user, request)
            
            if email_sent:
                messages.success(
                    request,
                    f'Password reset email sent to {user.email}. Please check your inbox.'
                )
            else:
                messages.error(
                    request,
                    'Failed to send password reset email. Please try again later or contact support.'
                )
            
            return redirect('password-reset-sent')
            
        except User.DoesNotExist:
            # Don't reveal if email exists or not (security best practice)
            messages.success(
                request,
                'If an account with that email exists, a password reset email has been sent.'
            )
            return redirect('password-reset-sent')
        except Exception as e:
            messages.error(
                request,
                'An error occurred. Please try again later.'
            )
            return redirect('forgot-password')
    
    def get(self, request):
        """Display form to request password reset."""
        return render(request, 'account/forgot_password.html')


class PasswordResetSentView(TemplateView):
    """
    Display a message that password reset email has been sent.
    Shown after successful password reset request.
    """
    template_name = 'account/password_reset_sent.html'


class ResetPasswordView(View):
    """
    Password reset confirmation view.
    Allows user to set a new password when they click the reset link.
    
    URL pattern: /accounts/reset-password/<uid>/<token>/
    """
    def get(self, request, uid, token):
        """
        Handle GET request from password reset email link.
        Display form to enter new password.
        
        Args:
            uid: Base64-encoded user ID
            token: Password reset token generated by default_token_generator
        """
        from django.contrib.auth import get_user_model
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode
        from django.utils.encoding import force_str
        
        User = get_user_model()
        
        try:
            # Decode the user ID from base64
            user_id = force_str(urlsafe_base64_decode(uid))
            user = get_object_or_404(User, pk=user_id)
            
            # Verify the token
            if default_token_generator.check_token(user, token):
                # Token is valid - show password reset form
                return render(request, 'account/reset_password.html', {
                    'uid': uid,
                    'token': token,
                    'valid_token': True
                })
            else:
                # Token is invalid or expired
                messages.error(
                    request,
                    'Invalid or expired password reset link. Please request a new one.'
                )
                return render(request, 'account/reset_password.html', {
                    'valid_token': False
                })
                
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            # Invalid user ID or user doesn't exist
            messages.error(
                request,
                'Invalid password reset link. Please request a new one.'
            )
            return render(request, 'account/reset_password.html', {
                'valid_token': False
            })
        except Exception as e:
            # Handle any unexpected errors
            messages.error(
                request,
                'An error occurred during password reset. Please try again or contact support.'
            )
            return render(request, 'account/reset_password.html', {
                'valid_token': False
            })
    
    def post(self, request, uid, token):
        """
        Handle POST request to set new password.
        
        Args:
            uid: Base64-encoded user ID
            token: Password reset token generated by default_token_generator
        """
        from django.contrib.auth import get_user_model
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode
        from django.utils.encoding import force_str
        from django.contrib.auth import login
        
        User = get_user_model()
        password1 = request.POST.get('password1', '').strip()
        password2 = request.POST.get('password2', '').strip()
        
        # Validate passwords
        if not password1 or not password2:
            messages.error(request, 'Please fill in both password fields.')
            return render(request, 'account/reset_password.html', {
                'uid': uid,
                'token': token,
                'valid_token': True
            })
        
        if password1 != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'account/reset_password.html', {
                'uid': uid,
                'token': token,
                'valid_token': True
            })
        
        # Check password strength (Django's validators will be used)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        
        try:
            validate_password(password1)
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
            return render(request, 'account/reset_password.html', {
                'uid': uid,
                'token': token,
                'valid_token': True
            })
        
        try:
            # Decode the user ID from base64
            user_id = force_str(urlsafe_base64_decode(uid))
            user = get_object_or_404(User, pk=user_id)
            
            # Verify the token again (security check)
            if not default_token_generator.check_token(user, token):
                messages.error(
                    request,
                    'Invalid or expired password reset link. Please request a new one.'
                )
                return redirect('forgot-password')
            
            # Set the new password
            user.set_password(password1)
            user.save()
            
            # Log the user in automatically after password reset
            login(request, user)
            
            messages.success(
                request,
                'Password reset successfully! You have been logged in.'
            )
            return redirect('landing')
            
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            messages.error(
                request,
                'Invalid password reset link. Please request a new one.'
            )
            return redirect('forgot-password')
        except Exception as e:
            messages.error(
                request,
                'An error occurred during password reset. Please try again or contact support.'
            )
            return redirect('forgot-password')


class LogoutView(AuthLogoutView):
    """Custom logout view."""
    next_page = reverse_lazy('landing')
    
    def dispatch(self, request, *args, **kwargs):
        """Show logout message."""
        if request.user.is_authenticated:
            messages.success(request, 'You have been logged out successfully.')
        return super().dispatch(request, *args, **kwargs)


# ============================================================================
# USER REGISTRATION & PROFILE VIEWS
# ============================================================================

class RegisterForEventView(LoginRequiredMixin, View):
    """Register user for an event."""
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        
        # Check if user can view this event
        if not can_user_view_event(request.user, event):
            messages.error(request, 'You do not have permission to register for this event.')
            return redirect('event-list')
        
        # Mandatory events: users are automatically registered, they can't manually register
        if event.is_mandatory():
            messages.info(request, 'This is a mandatory event. You are automatically registered.')
            return redirect('event-detail', pk=event_id)
        
        # Check if registration is still possible
        now = timezone.now()
        if event.registration_deadline and event.registration_deadline < now:
            messages.error(request, 'Registration deadline has passed.')
            return redirect('event-detail', pk=event_id)
        
        if event.start_datetime < now:
            messages.error(request, 'This event has already started.')
            return redirect('event-detail', pk=event_id)
        
        if event.is_full():
            messages.error(request, 'This event is full.')
            return redirect('event-detail', pk=event_id)
        
        # Check if already registered
        registration, created = Registration.objects.get_or_create(
            event=event,
            user=request.user,
            defaults={'status': Registration.Status.PRE_REGISTERED, 'is_mandatory': False}
        )
        
        if created:
            messages.success(request, f'Successfully pre-registered for "{event.title}"!')
        else:
            if registration.status == Registration.Status.CANCELLED:
                registration.status = Registration.Status.PRE_REGISTERED
                registration.is_mandatory = False
                registration.registered_at = timezone.now()
                registration.save()
                messages.success(request, f'Successfully re-registered for "{event.title}"!')
            else:
                messages.info(request, 'You are already registered for this event.')
        
        return redirect('event-detail', pk=event_id)


class UnregisterFromEventView(LoginRequiredMixin, View):
    """Cancel user registration for an event."""
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        
        try:
            registration = Registration.objects.get(
                event=event,
                user=request.user
            )
            registration.status = Registration.Status.CANCELLED
            registration.save()
            messages.success(request, f'Registration cancelled for "{event.title}".')
        except Registration.DoesNotExist:
            messages.error(request, 'You are not registered for this event.')
        
        return redirect('event-detail', pk=event_id)


class UserProfileView(LoginRequiredMixin, TemplateView):
    """Display user profile with points and registration history."""
    template_name = 'pulse/user_profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Check for organization creation success
        org_created_name = self.request.session.pop('org_created_name', None)
        if org_created_name:
            context['org_created_name'] = org_created_name
        
        # Check organization roles
        from .models import OrganizationMembership
        is_org_admin = OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.Role.ADMIN,
            organization__is_active=True,
            organization__status='APPROVED',
        ).exists()
        is_org_organizer = OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.Role.ORGANIZER,
            organization__is_active=True,
        ).exists()
        
        context['is_org_admin'] = is_org_admin
        context['is_org_organizer'] = is_org_organizer
        
        if hasattr(user, 'profile'):
            profile = user.profile
            context['profile'] = profile
            
            # Get points transactions
            context['points_transactions'] = profile.points_transactions.all()[:20]
            context['total_transactions'] = profile.points_transactions.count()
            
            # Get user registrations
            registrations = Registration.objects.filter(user=user).select_related('event').order_by('-registered_at')[:20]
            context['registrations'] = registrations
            context['total_registrations'] = Registration.objects.filter(user=user).count()
            
            # Get upcoming registrations
            now = timezone.now()
            upcoming_registrations = [
                reg for reg in registrations
                if reg.event.start_datetime > now and reg.status != Registration.Status.CANCELLED
            ]
            context['upcoming_registrations'] = upcoming_registrations
            
            # Stats
            attended_count = Registration.objects.filter(
                user=user,
                status=Registration.Status.ATTENDED
            ).count()
            context['attended_count'] = attended_count
            
            # Get organization memberships
            from .models import OrganizationMembership
            organization_memberships = OrganizationMembership.objects.filter(
                user=user
            ).select_related('organization').order_by('-joined_at')
            context['organization_memberships'] = organization_memberships

            if organization_memberships:
                org_ids = [membership.organization_id for membership in organization_memberships]
                mandatory_points = AttendanceRecord.objects.filter(
                    user=user,
                    event__organization_id__in=org_ids,
                    event__event_type=Event.EventType.MANDATORY
                ).values('event__organization_id').annotate(
                    total_points=Sum('points_awarded'),
                    scans=Count('id')
                )
                mandatory_events_counts = Event.objects.filter(
                    organization_id__in=org_ids,
                    event_type=Event.EventType.MANDATORY
                ).values('organization_id').annotate(total=Count('id'))

                points_map = {item['event__organization_id']: item for item in mandatory_points}
                events_map = {item['organization_id']: item['total'] for item in mandatory_events_counts}

                mandatory_points_by_org = []
                for membership in organization_memberships:
                    org_id = membership.organization_id
                    stats = points_map.get(org_id, {})
                    mandatory_points_by_org.append({
                        'organization': membership.organization,
                        'points': stats.get('total_points', 0) or 0,
                        'scans': stats.get('scans', 0),
                        'total_mandatory_events': events_map.get(org_id, 0),
                    })

                context['mandatory_points_by_org'] = mandatory_points_by_org
        
        return context


class ChangeUsernameView(LoginRequiredMixin, UpdateView):
    """View for changing username."""
    model = User
    form_class = UsernameChangeForm
    template_name = 'pulse/profile_settings.html'
    
    def get_object(self):
        return self.request.user
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, 'Username updated successfully!')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('profile')


class ChangePasswordView(LoginRequiredMixin, FormView):
    """View for changing password."""
    form_class = PasswordChangeForm
    template_name = 'pulse/profile_settings.html'
    success_url = reverse_lazy('profile')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Style password fields with Pulse theme
        for field_name, field in form.fields.items():
            field.widget.attrs.update({
                'class': 'w-full px-4 py-3 border border-pulse-blue/30 rounded-pulse focus:ring-2 focus:ring-pulse-blue focus:border-pulse-blue transition-all bg-pulse-navyLighter text-white placeholder:text-text-muted',
            })
        return form
    
    def form_valid(self, form):
        form.save()
        # Update session to prevent logout
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, 'Password changed successfully!')
        return super().form_valid(form)


class ChangeAvatarView(LoginRequiredMixin, UpdateView):
    """View for changing profile avatar."""
    model = UserProfile
    form_class = ProfileAvatarForm
    template_name = 'pulse/profile_settings.html'
    
    def get_object(self):
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile
    
    def form_valid(self, form):
        messages.success(self.request, 'Profile picture updated successfully!')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('profile')


class OrganizationMandatorySummaryView(LoginRequiredMixin, TemplateView):
    """Show detailed mandatory attendance summary for a user's organization.
    
    If ?user=<id> is provided and the requester is an organizer/admin for the org,
    show the summary for that member instead of the current user.
    """
    template_name = 'pulse/organization_mandatory_summary.html'

    def get_context_data(self, **kwargs):
        from django.contrib.auth import get_user_model

        context = super().get_context_data(**kwargs)
        request_user = self.request.user
        org_id = self.kwargs.get('org_pk')

        organization = get_object_or_404(Organization, pk=org_id, is_active=True)

        # Determine target user (member whose attendance we're viewing)
        target_user = request_user
        target_user_id = self.request.GET.get('user')
        if target_user_id and target_user_id.isdigit():
            UserModel = get_user_model()
            target_user = get_object_or_404(UserModel, pk=int(target_user_id))

            # Only allow viewing another user if requester is organizer/admin for this org
            is_admin = (
                request_user.is_superuser or 
                (hasattr(request_user, 'profile') and request_user.profile.is_admin())
            )
            is_organizer_for_org = OrganizationMembership.objects.filter(
                user=request_user,
                organization=organization,
                role=OrganizationMembership.Role.ORGANIZER
            ).exists()

            if not (is_admin or is_organizer_for_org):
                messages.error(self.request, "You do not have permission to view member attendance for this organization.")
                target_user = request_user

        # Ensure target user is a member of this organization
        membership_qs = OrganizationMembership.objects.filter(user=target_user, organization=organization)
        if not membership_qs.exists():
            messages.error(self.request, "Selected user is not a member of this organization.")
            return context

        # Mandatory events for this organization
        mandatory_events = Event.objects.filter(
            organization=organization,
            event_type=Event.EventType.MANDATORY
        ).order_by('start_datetime')

        # Attendance records for this user and these events
        records = AttendanceRecord.objects.filter(
            user=target_user,
            event__in=mandatory_events
        ).select_related('event')

        records_by_event = {}
        for rec in records:
            records_by_event.setdefault(rec.event_id, []).append(rec)
        
        # Get all excuses for all events (including approved ones)
        from .models import Excuse
        excuses_by_event = {}
        all_excuses = Excuse.objects.filter(
            event__in=mandatory_events,
            user=target_user,
            status__in=[Excuse.Status.PENDING, Excuse.Status.APPROVED]
        ).select_related('event', 'user', 'reviewed_by')
        
        for excuse in all_excuses:
            excuses_by_event.setdefault(excuse.event_id, []).append(excuse)

        # Build table rows
        event_rows = []
        total_possible_scans = 0
        total_completed_scans = 0

        for event in mandatory_events:
            flags = {
                'MORNING_IN': event.enable_morning_in,
                'MORNING_OUT': event.enable_morning_out,
                'AFTERNOON_IN': event.enable_afternoon_in,
                'AFTERNOON_OUT': event.enable_afternoon_out,
            }
            event_possible = sum(1 for v in flags.values() if v)
            total_possible_scans += event_possible

            recs = records_by_event.get(event.id, [])
            # Create a set of attendance type values (strings like "MORNING_IN", "MORNING_OUT", etc.)
            # Each type is checked independently - scanning "MORNING_OUT" does NOT add "MORNING_IN" to this set
            # Explicitly convert to string and ensure we're getting the exact value
            present_types = set()
            for r in recs:
                if r.attendance_type:
                    # Get the exact string value of the attendance type
                    present_types.add(str(r.attendance_type))
            
            # Get excuses for this event
            event_excuses = excuses_by_event.get(event.id, [])
            
            # Helper function to check if there's an approved or pending excuse for an attendance type
            # IMPORTANT: Only check for excuses that specifically apply to this attendance type
            # An excuse with attendance_type="ALL" applies to all types, but we check each type separately
            def get_excuse_status(attendance_type_str):
                for excuse in event_excuses:
                    if excuse.applies_to_attendance_type(attendance_type_str):
                        # Compare with the actual status value
                        if excuse.status == Excuse.Status.APPROVED:
                            return 'approved'
                        elif excuse.status == Excuse.Status.PENDING:
                            return 'pending'
                return None

            # Check if user has any pending/approved excuse for this event
            # Each attendance type is checked independently
            # Use hardcoded string values to avoid issues with Django TextChoices enum access
            morning_in_status = get_excuse_status("MORNING_IN")
            morning_out_status = get_excuse_status("MORNING_OUT")
            afternoon_in_status = get_excuse_status("AFTERNOON_IN")
            afternoon_out_status = get_excuse_status("AFTERNOON_OUT")
            
            # Count completed scans by checking if attendance type exists OR if there's an approved excuse
            # We need to count each enabled attendance type only once (either scan OR approved excuse)
            completed_count = 0
            if flags['MORNING_IN']:
                if ("MORNING_IN" in present_types or 
                    morning_in_status == 'approved'):
                    completed_count += 1
            if flags['MORNING_OUT']:
                if ("MORNING_OUT" in present_types or 
                    morning_out_status == 'approved'):
                    completed_count += 1
            if flags['AFTERNOON_IN']:
                if ("AFTERNOON_IN" in present_types or 
                    afternoon_in_status == 'approved'):
                    completed_count += 1
            if flags['AFTERNOON_OUT']:
                if ("AFTERNOON_OUT" in present_types or 
                    afternoon_out_status == 'approved'):
                    completed_count += 1
            
            total_completed_scans += completed_count
            
            has_any_excuse = (
                morning_in_status in ['approved', 'pending'] or
                morning_out_status in ['approved', 'pending'] or
                afternoon_in_status in ['approved', 'pending'] or
                afternoon_out_status in ['approved', 'pending']
            )
            
            # Check if user has completed each attendance type (either scanned or has approved excuse)
            # Each attendance type is checked independently - scanning "Morning Out" does NOT mark "Morning In" as complete
            # Use hardcoded string values to ensure accuracy
            has_morning_in_completed = (
                "MORNING_IN" in present_types or
                morning_in_status == 'approved'
            )
            has_morning_out_completed = (
                "MORNING_OUT" in present_types or
                morning_out_status == 'approved'
            )
            has_afternoon_in_completed = (
                "AFTERNOON_IN" in present_types or
                afternoon_in_status == 'approved'
            )
            has_afternoon_out_completed = (
                "AFTERNOON_OUT" in present_types or
                afternoon_out_status == 'approved'
            )
            
            row = {
                'event': event,
                'morning_in': flags['MORNING_IN'],
                'morning_out': flags['MORNING_OUT'],
                'afternoon_in': flags['AFTERNOON_IN'],
                'afternoon_out': flags['AFTERNOON_OUT'],
                'has_morning_in': has_morning_in_completed,
                'has_morning_out': has_morning_out_completed,
                'has_afternoon_in': has_afternoon_in_completed,
                'has_afternoon_out': has_afternoon_out_completed,
                'morning_in_excuse': morning_in_status,
                'morning_out_excuse': morning_out_status,
                'afternoon_in_excuse': afternoon_in_status,
                'afternoon_out_excuse': afternoon_out_status,
                'has_any_excuse': has_any_excuse,
            }
            event_rows.append(row)

        # Score based on completed scans
        if total_possible_scans > 0:
            completion_ratio = total_completed_scans / total_possible_scans
        else:
            completion_ratio = 0

        score_percent = round(completion_ratio * 100, 2)

        # Points: earned vs maximum possible for mandatory events
        mandatory_attendance = records
        earned_points = mandatory_attendance.aggregate(total=Sum('points_awarded'))['total'] or 0
        max_points = sum(e.get_points() for e in mandatory_events)
        points_ratio = (earned_points / max_points * 100) if max_points > 0 else 0

        context.update({
            'organization': organization,
            'target_user': target_user,
            'event_rows': event_rows,
            'score_percent': score_percent,
            'earned_points': earned_points,
            'max_points': max_points,
            'points_ratio': round(points_ratio, 2),
            'total_mandatory_events': mandatory_events.count(),
            'total_completed_scans': total_completed_scans,
            'total_possible_scans': total_possible_scans,
        })

        return context

class MyRegistrationsView(LoginRequiredMixin, ListView):
    """Display all user registrations."""
    model = Registration
    template_name = 'pulse/my_registrations.html'
    context_object_name = 'registrations'
    paginate_by = 20
    
    def get_queryset(self):
        """Get all registrations for the current user, optionally filtered by status."""
        queryset = Registration.objects.filter(
            user=self.request.user
        ).select_related('event').order_by('-registered_at')
        
        # Filter by status if requested
        status_filter = self.request.GET.get('status', 'all')
        if status_filter != 'all':
            queryset = queryset.filter(status=status_filter)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        
        status_filter = self.request.GET.get('status', 'all')
        context['current_filter'] = status_filter
        
        # Calculate stats from all registrations (not filtered)
        all_registrations = Registration.objects.filter(user=self.request.user).select_related('event')
        context['total_registrations'] = all_registrations.count()
        
        upcoming = [
            r for r in all_registrations
            if r.event.start_datetime > now and r.status != Registration.Status.CANCELLED
        ]
        context['upcoming_count'] = upcoming
        context['attended_count'] = all_registrations.filter(status=Registration.Status.ATTENDED).count()
        
        return context


class RequestExcuseView(LoginRequiredMixin, CreateView):
    """View for students to request an excuse for mandatory event attendance."""
    model = Excuse
    form_class = ExcuseForm
    template_name = 'pulse/request_excuse.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        event_id = self.kwargs.get('event_id')
        event = get_object_or_404(Event, pk=event_id)
        kwargs['event'] = event
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event_id = self.kwargs.get('event_id')
        context['event'] = get_object_or_404(Event, pk=event_id)
        return context
    
    def form_valid(self, form):
        event_id = self.kwargs.get('event_id')
        event = get_object_or_404(Event, pk=event_id)
        
        # Check if event is mandatory
        if not event.is_mandatory():
            messages.error(self.request, "Excuses can only be requested for mandatory events.")
            return redirect('event-detail', pk=event_id)
        
        # Check if user is registered for this event
        registration = Registration.objects.filter(
            event=event,
            user=self.request.user
        ).first()
        
        if not registration:
            messages.error(self.request, "You must be registered for this event to request an excuse.")
            return redirect('event-detail', pk=event_id)
        
        # Check if excuse already exists for this event/user/attendance_type
        existing_excuse = Excuse.objects.filter(
            event=event,
            user=self.request.user,
            attendance_type=form.cleaned_data['attendance_type'],
            status__in=[Excuse.Status.PENDING, Excuse.Status.APPROVED]
        ).first()
        
        if existing_excuse:
            messages.warning(self.request, "You already have a pending or approved excuse for this attendance type.")
            return redirect('event-detail', pk=event_id)
        
        form.instance.event = event
        form.instance.user = self.request.user
        form.instance.status = Excuse.Status.PENDING
        
        # Store success flag in session for popup display
        self.request.session['excuse_submitted'] = True
        self.request.session.modified = True
        
        messages.success(self.request, "Your excuse request has been submitted and is pending review.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('event-detail', kwargs={'pk': self.kwargs.get('event_id')})


class ReviewExcusesView(AdminOrOrganizerRequiredMixin, ListView):
    """View for organizers to review excuse requests."""
    model = Excuse
    template_name = 'pulse/review_excuses.html'
    context_object_name = 'excuses'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Excuse.objects.filter(
            status=Excuse.Status.PENDING
        ).select_related('event', 'user', 'reviewed_by', 'event__organization').order_by('-created_at')
        
        # Filter by organization if user is organizer (not super admin)
        if not self.request.user.is_superuser:
            user_orgs = Organization.objects.filter(
                memberships__user=self.request.user,
                memberships__role=OrganizationMembership.Role.ORGANIZER
            )
            queryset = queryset.filter(event__organization__in=user_orgs)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_pending'] = self.get_queryset().count()
        return context


class ReviewExcuseDetailView(AdminOrOrganizerRequiredMixin, UpdateView):
    """View for organizers to review and approve/reject a specific excuse."""
    model = Excuse
    form_class = ExcuseReviewForm
    template_name = 'pulse/review_excuse_detail.html'
    context_object_name = 'excuse'
    
    def get_queryset(self):
        queryset = Excuse.objects.filter(
            status=Excuse.Status.PENDING
        ).select_related('event', 'user', 'event__organization')
        
        # Filter by organization if user is organizer (not super admin)
        if not self.request.user.is_superuser:
            user_orgs = Organization.objects.filter(
                memberships__user=self.request.user,
                memberships__role=OrganizationMembership.Role.ORGANIZER
            )
            queryset = queryset.filter(event__organization__in=user_orgs)
        
        return queryset
    
    def form_valid(self, form):
        excuse = form.instance
        was_approved = excuse.status == Excuse.Status.APPROVED
        old_status = None
        
        # Get old status before saving
        if excuse.pk:
            try:
                old_excuse = Excuse.objects.get(pk=excuse.pk)
                old_status = old_excuse.status
            except Excuse.DoesNotExist:
                pass
        
        excuse.reviewed_by = self.request.user
        excuse.reviewed_at = timezone.now()
        
        response = super().form_valid(form)
        
        # If excuse was just approved, create attendance records and award points
        if excuse.status == Excuse.Status.APPROVED and old_status != Excuse.Status.APPROVED:
            from .models import AttendanceRecord, UserProfile
            
            event = excuse.event
            user = excuse.user
            
            # Determine which attendance types this excuse applies to
            attendance_types_to_create = []
            if excuse.attendance_type == Excuse.AttendanceType.ALL[0]:
                # Apply to all enabled attendance types
                if event.enable_morning_in:
                    attendance_types_to_create.append("MORNING_IN")
                if event.enable_morning_out:
                    attendance_types_to_create.append("MORNING_OUT")
                if event.enable_afternoon_in:
                    attendance_types_to_create.append("AFTERNOON_IN")
                if event.enable_afternoon_out:
                    attendance_types_to_create.append("AFTERNOON_OUT")
            else:
                # Apply to specific attendance type
                attendance_types_to_create.append(excuse.attendance_type)
            
            # Create attendance records for each applicable type
            # Calculate points proportionally (same logic as QR scanning)
            enabled_count = sum([
                event.enable_morning_in,
                event.enable_morning_out,
                event.enable_afternoon_in,
                event.enable_afternoon_out
            ])
            
            if enabled_count == 0:
                points_per_scan = 0
            else:
                # Each scan awards a proportional share of total points
                # If all 4 are enabled, each scan is worth 25% (1/4)
                # If 2 are enabled, each is worth 50% (1/2), etc.
                total_points = event.get_points() if hasattr(event, 'get_points') else 10
                points_per_scan = total_points // enabled_count
            
            points_awarded_total = 0
            for attendance_type in attendance_types_to_create:
                # Check if attendance record already exists
                existing_record = AttendanceRecord.objects.filter(
                    event=event,
                    user=user,
                    attendance_type=attendance_type
                ).first()
                
                if not existing_record:
                    # Create attendance record
                    attendance_record = AttendanceRecord.objects.create(
                        event=event,
                        user=user,
                        organizer=self.request.user,  # The reviewer who approved
                        attendance_type=attendance_type,
                        points_awarded=points_per_scan,
                        notes=f"Approved excuse: {excuse.reason[:100]}"
                    )
                    
                    # Award points to user
                    if points_per_scan > 0 and hasattr(user, 'profile'):
                        user.profile.add_points(
                            amount=points_per_scan,
                            reason=f"Approved Excuse: {event.title} ({attendance_type})",
                            event=event
                        )
                        points_awarded_total += points_per_scan
            
            if points_awarded_total > 0:
                messages.success(self.request, f"Excuse has been approved. {points_awarded_total} point(s) awarded.")
            else:
                messages.success(self.request, "Excuse has been approved.")
        elif excuse.status == Excuse.Status.REJECTED:
            messages.success(self.request, "Excuse has been rejected.")
        
        return response
    
    def get_success_url(self):
        return reverse_lazy('review-excuses')