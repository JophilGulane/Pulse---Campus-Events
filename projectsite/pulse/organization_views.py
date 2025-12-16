"""
Views for organization management and joining.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.http import JsonResponse
from .models import Organization, OrganizationMembership, OrganizationInvite, AttendanceRecord, Event
from .forms import OrganizationForm, JoinOrganizationByCodeForm
from .mixins import SuperAdminRequiredMixin, OrganizerRequiredMixin


# ============================================================================
# SUPER ADMIN VIEWS - Organization Management
# ============================================================================

class OrganizationListView(SuperAdminRequiredMixin, ListView):
    """Super Admin view to list all organizations."""
    model = Organization
    template_name = 'pulse/organization/organization_list.html'
    context_object_name = 'organizations'
    paginate_by = 20
    
    def get_queryset(self):
        """Filter organizations based on search and status."""
        queryset = Organization.objects.all()
        search = self.request.GET.get('search', '')
        status_filter = self.request.GET.get('status', 'all')
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(join_code__icontains=search)
            )
        
        if status_filter != 'all':
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pending_count'] = Organization.objects.filter(status=Organization.Status.PENDING).count()
        context['current_status'] = self.request.GET.get('status', 'all')
        return context


class OrganizationCreateView(LoginRequiredMixin, CreateView):
    """View for users to request organization creation (requires super admin approval)."""
    model = Organization
    form_class = OrganizationForm
    template_name = 'pulse/organization/organization_form.html'
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.status = Organization.Status.PENDING
        form.instance.is_active = False  # Inactive until approved
        organization_name = form.instance.name
        response = super().form_valid(form)
        
        # Create membership for the creator so they can see it in their profile
        organization = form.instance
        OrganizationMembership.objects.get_or_create(
            user=self.request.user,
            organization=organization,
            defaults={'role': OrganizationMembership.Role.ADMIN}
        )
        
        # Store organization name in session for popup display
        self.request.session['org_created_name'] = organization_name
        self.request.session.modified = True
        return response
    
    def get_success_url(self):
        return reverse_lazy('profile')


class OrganizationCreateAdminView(SuperAdminRequiredMixin, CreateView):
    """Super Admin view to create organizations directly (auto-approved)."""
    model = Organization
    form_class = OrganizationForm
    template_name = 'pulse/organization/organization_form.html'
    success_url = reverse_lazy('organization-list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.status = Organization.Status.APPROVED
        form.instance.is_active = True
        messages.success(self.request, f'Organization "{form.instance.name}" created successfully!')
        return super().form_valid(form)


class OrganizationDetailView(SuperAdminRequiredMixin, DetailView):
    """Super Admin view to view organization details."""
    model = Organization
    template_name = 'pulse/organization/organization_detail.html'
    context_object_name = 'organization'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = context['organization']
        
        # Get members
        context['members'] = OrganizationMembership.objects.filter(
            organization=organization
        ).select_related('user').order_by('-role', 'joined_at')
        
        # Get organizers (get_organizers already filters by ORGANIZER role, so it won't include admins)
        context['organizers'] = organization.get_organizers()
        
        # Get admins
        context['admins'] = organization.get_admins()
        
        # Check if current user is admin of this organization
        context['is_org_admin'] = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization=organization,
            role=OrganizationMembership.Role.ADMIN
        ).exists()
        
        # Get events count
        context['events_count'] = organization.events.count()
        
        # Get announcements count
        context['announcements_count'] = organization.announcements.count()
        
        return context


class OrganizationDetailForOrganizerView(LoginRequiredMixin, DetailView):
    """View for organizers and admins to view their organization details."""
    model = Organization
    template_name = 'pulse/organization/organization_detail.html'
    context_object_name = 'organization'
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user is organizer or admin of this organization."""
        organization = self.get_object()
        user = request.user
        
        # Super admins can always view
        if user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        
        # Check if user is admin or organizer of this organization
        membership = OrganizationMembership.objects.filter(
            user=user,
            organization=organization,
            role__in=[OrganizationMembership.Role.ADMIN, OrganizationMembership.Role.ORGANIZER]
        ).first()
        
        if not membership:
            messages.error(request, "You don't have permission to view this organization.")
            return redirect('profile')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = context['organization']
        
        # Get members
        context['members'] = OrganizationMembership.objects.filter(
            organization=organization
        ).select_related('user').order_by('-role', 'joined_at')
        
        # Get organizers (get_organizers already filters by ORGANIZER role, so it won't include admins)
        context['organizers'] = organization.get_organizers()
        
        # Get admins
        context['admins'] = organization.get_admins()
        
        # Check if current user is admin of this organization
        context['is_org_admin'] = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization=organization,
            role=OrganizationMembership.Role.ADMIN
        ).exists()
        
        # Get events count
        context['events_count'] = organization.events.count()
        
        # Get announcements count
        context['announcements_count'] = organization.announcements.count()
        
        return context


class OrganizationUpdateView(SuperAdminRequiredMixin, UpdateView):
    """Super Admin view to update organizations."""
    model = Organization
    form_class = OrganizationForm
    template_name = 'pulse/organization/organization_form.html'
    success_url = reverse_lazy('organization-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Organization "{form.instance.name}" updated successfully!')
        return super().form_valid(form)


class OrganizationMembersView(LoginRequiredMixin, ListView):
    """View for super admins and organization admins to manage organization members."""
    template_name = 'pulse/organization/organization_members.html'
    context_object_name = 'memberships'
    paginate_by = 30
    
    def dispatch(self, request, *args, **kwargs):
        organization = get_object_or_404(Organization, pk=kwargs['pk'])
        # Check permissions: super admin OR organization admin
        is_super_admin = request.user.is_superuser
        is_org_admin = OrganizationMembership.objects.filter(
            user=request.user,
            organization=organization,
            role=OrganizationMembership.Role.ADMIN
        ).exists()
        
        if not (is_super_admin or is_org_admin):
            messages.error(request, 'You do not have permission to view this page.')
            return redirect('profile')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        organization = get_object_or_404(Organization, pk=self.kwargs['pk'])
        queryset = OrganizationMembership.objects.filter(
            organization=organization
        ).select_related('user').order_by('-role', 'joined_at')
        
        role_filter = self.request.GET.get('role', '')
        if role_filter:
            queryset = queryset.filter(role=role_filter)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = get_object_or_404(Organization, pk=self.kwargs['pk'])
        context['organization'] = organization
        
        # Check if current user is admin of this organization
        context['is_org_admin'] = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization=organization,
            role=OrganizationMembership.Role.ADMIN
        ).exists()
        
        return context


class OrganizationAttendanceDashboardView(OrganizerRequiredMixin, TemplateView):
    """Dashboard for organizers to view member attendance scores."""
    template_name = 'pulse/organization/attendance_dashboard.html'

    def get_context_data(self, **kwargs):
        from django.contrib.auth import get_user_model
        context = super().get_context_data(**kwargs)
        organization = get_object_or_404(Organization, pk=self.kwargs['pk'])
        context['organization'] = organization

        membership = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization=organization
        )
        is_admin = (
            self.request.user.is_superuser or 
            (hasattr(self.request.user, 'profile') and self.request.user.profile.is_admin())
        )
        if not membership.exists() and not is_admin:
            context['members'] = []
            context['summary'] = {}
            return context

        UserModel = get_user_model()
        members = OrganizationMembership.objects.filter(
            organization=organization
        ).select_related('user').order_by('-role', 'user__username')

        mandatory_events = Event.objects.filter(
            organization=organization,
            event_type=Event.EventType.MANDATORY
        )
        total_scans_possible_per_event = {}
        for event in mandatory_events:
            count = sum([
                event.enable_morning_in,
                event.enable_morning_out,
                event.enable_afternoon_in,
                event.enable_afternoon_out,
            ])
            total_scans_possible_per_event[event.id] = count
        total_scans_possible = sum(total_scans_possible_per_event.values())

        # Attendance records grouped by user
        attendance = AttendanceRecord.objects.filter(
            event__in=mandatory_events
        ).values('user_id').annotate(
            scans=Count('id'),
            points=Sum('points_awarded')
        )
        attendance_map = {item['user_id']: item for item in attendance}

        member_rows = []
        for membership in members:
            user = membership.user
            stats = attendance_map.get(user.id, {})
            scans = stats.get('scans', 0)
            points = stats.get('points', 0) or 0
            score_percent = round((scans / total_scans_possible) * 100, 2) if total_scans_possible else 0
            member_rows.append({
                'user': user,
                'role': membership.role,
                'joined_at': membership.joined_at,
                'scans': scans,
                'points': points,
                'score_percent': score_percent,
            })

        context['members'] = member_rows
        context['total_mandatory_events'] = mandatory_events.count()
        context['total_scans_per_member'] = total_scans_possible
        context['summary'] = {
            'average_score': round(
                sum(row['score_percent'] for row in member_rows) / len(member_rows), 2
            ) if member_rows else 0,
            'top_member': max(member_rows, key=lambda x: x['score_percent'], default=None),
        }
        return context

class AssignOrganizerView(LoginRequiredMixin, View):
    """View for organization admins and super admins to assign a user as an organizer."""
    def post(self, request, org_pk, user_pk):
        organization = get_object_or_404(Organization, pk=org_pk)
        user = get_object_or_404(request.user.__class__, pk=user_pk)
        
        # Check permissions: super admin OR organization admin
        is_super_admin = request.user.is_superuser
        is_org_admin = OrganizationMembership.objects.filter(
            user=request.user,
            organization=organization,
            role=OrganizationMembership.Role.ADMIN
        ).exists()
        
        if not (is_super_admin or is_org_admin):
            messages.error(request, 'You do not have permission to assign organizers.')
            return redirect('organization-members', pk=org_pk)
        
        # Check if user is already a member
        membership = OrganizationMembership.objects.filter(
            user=user,
            organization=organization
        ).first()
        
        if not membership:
            messages.error(request, f'{user.username} is not a member of this organization.')
            return redirect('organization-members', pk=org_pk)
        
        # Update role to organizer
        membership.role = OrganizationMembership.Role.ORGANIZER
        membership.save()
        
        messages.success(request, f'{user.username} has been assigned as an organizer.')
        return redirect('organization-members', pk=org_pk)


class ReviewOrganizationView(SuperAdminRequiredMixin, View):
    """Super Admin view to approve or reject organization requests."""
    def post(self, request, pk):
        organization = get_object_or_404(Organization, pk=pk)
        action = request.POST.get('action')  # 'approve' or 'reject'
        review_notes = request.POST.get('review_notes', '')
        
        if action == 'approve':
            organization.status = Organization.Status.APPROVED
            organization.is_active = True
            organization.reviewed_by = request.user
            organization.reviewed_at = timezone.now()
            organization.review_notes = review_notes
            organization.save()
            
            # Automatically make the creator an admin of the organization
            if organization.created_by:
                membership, created = OrganizationMembership.objects.get_or_create(
                    user=organization.created_by,
                    organization=organization,
                    defaults={'role': OrganizationMembership.Role.ADMIN}
                )
                if not created:
                    membership.role = OrganizationMembership.Role.ADMIN
                    membership.save()
            
            messages.success(request, f'Organization "{organization.name}" has been approved. The creator is now an admin.')
        
        elif action == 'reject':
            organization.status = Organization.Status.REJECTED
            organization.is_active = False
            organization.reviewed_by = request.user
            organization.reviewed_at = timezone.now()
            organization.review_notes = review_notes
            organization.save()
            
            messages.success(request, f'Organization "{organization.name}" has been rejected.')
        
        return redirect('organization-list')


# ============================================================================
# USER VIEWS - Join/Leave Organizations
# ============================================================================

class JoinOrganizationByCodeView(LoginRequiredMixin, View):
    """View for users to join an organization using a join code."""
    template_name = 'pulse/organization/join_by_code.html'
    
    def get(self, request):
        form = JoinOrganizationByCodeForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = JoinOrganizationByCodeForm(request.POST)
        
        if form.is_valid():
            join_code = form.cleaned_data['join_code']
            organization = Organization.objects.get(join_code=join_code)
            
            # Check if organization is approved
            if not organization.is_approved():
                messages.error(request, 'This organization is not yet approved. Please wait for approval before joining.')
                return redirect('profile')
            
            # Check if already a member
            if OrganizationMembership.objects.filter(
                user=request.user,
                organization=organization
            ).exists():
                messages.info(request, f'You are already a member of {organization.name}.')
                return redirect('profile')
            
            # Join organization
            OrganizationMembership.objects.create(
                user=request.user,
                organization=organization,
                role=OrganizationMembership.Role.MEMBER,
                joined_via='CODE'
            )
            
            # Store organization name in session for popup display
            request.session['org_joined_name'] = organization.name
            request.session.modified = True
            
            messages.success(request, f'Successfully joined {organization.name}!')
            return redirect('profile')
        
        return render(request, self.template_name, {'form': form})


class JoinOrganizationByInviteView(LoginRequiredMixin, View):
    """View for users to join an organization using an invite link."""
    template_name = 'pulse/organization/join_by_invite.html'
    
    def get(self, request, invite_token):
        invite = get_object_or_404(OrganizationInvite, token=invite_token)
        
        if not invite.is_valid():
            messages.error(request, 'This invite link is invalid or has expired.')
            return redirect('landing')
        
        # Check if already a member
        if OrganizationMembership.objects.filter(
            user=request.user,
            organization=invite.organization
        ).exists():
            messages.info(request, f'You are already a member of {invite.organization.name}.')
            return redirect('profile')
        
        context = {
            'invite': invite,
            'organization': invite.organization,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, invite_token):
        invite = get_object_or_404(OrganizationInvite, token=invite_token)
        
        if not invite.is_valid():
            messages.error(request, 'This invite link is invalid or has expired.')
            return redirect('landing')
        
        # Check if already a member
        if OrganizationMembership.objects.filter(
            user=request.user,
            organization=invite.organization
        ).exists():
            messages.info(request, f'You are already a member of {invite.organization.name}.')
            return redirect('profile')
        
        # Join organization
        OrganizationMembership.objects.create(
            user=request.user,
            organization=invite.organization,
            role=OrganizationMembership.Role.MEMBER,
            joined_via='INVITE'
        )
        
        # Mark invite as used
        invite.use()
        
        # Store organization name in session for popup display
        request.session['org_joined_name'] = invite.organization.name
        request.session.modified = True
        
        messages.success(request, f'Successfully joined {invite.organization.name}!')
        return redirect('profile')


class ClearOrgJoinedSessionView(LoginRequiredMixin, View):
    """View to clear the organization joined session variable after popup is shown."""
    
    def post(self, request):
        if 'org_joined_name' in request.session:
            del request.session['org_joined_name']
            request.session.modified = True
        return JsonResponse({'success': True})


class LeaveOrganizationView(LoginRequiredMixin, View):
    """View for users to leave an organization."""
    def post(self, request, org_pk):
        organization = get_object_or_404(Organization, pk=org_pk)
        
        try:
            membership = OrganizationMembership.objects.get(
                user=request.user,
                organization=organization
            )
            
            # Don't allow organizers to leave via this view (they should be removed by super admin)
            if membership.role == OrganizationMembership.Role.ORGANIZER:
                messages.error(request, 'Organizers cannot leave organizations. Contact a super admin to be removed.')
                return redirect('profile')
            
            membership.delete()
            messages.success(request, f'You have left {organization.name}.')
        except OrganizationMembership.DoesNotExist:
            messages.error(request, 'You are not a member of this organization.')
        
        return redirect('profile')

