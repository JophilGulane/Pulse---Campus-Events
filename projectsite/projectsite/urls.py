"""
URL configuration for projectsite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from pulse.views import (
    LandingPageView,
    LeaderboardView,
    SignUpView,
    LoginView,
    LogoutView,
    UserProfileView,
    ChangeUsernameView,
    ChangePasswordView,
    ChangeAvatarView,
    MyRegistrationsView,
    EventListView,
    EventDetailView,
    EventCreateView,
    EventUpdateView,
    EventDeleteView,
    AnnouncementsNewsfeedView,
    RegisterForEventView,
    UnregisterFromEventView,
    VerificationSentView,
    VerifyEmailView,
    ResendVerificationView,
    ForgotPasswordView,
    PasswordResetSentView,
    ResetPasswordView,
    OrganizerDashboardView,
    OrganizationMandatorySummaryView,
    RequestExcuseView,
    ReviewExcusesView,
    ReviewExcuseDetailView,
)
from pulse.admin_views import (
    UserManagementView,
    UpdateUserRoleView,
    ManageParticipantsView,
    UpdateRegistrationStatusView,
    AnnouncementListView,
    AnnouncementCreateView,
    AnnouncementUpdateView,
    AnnouncementDeleteView,
)
from pulse.organization_views import (
    OrganizationListView,
    OrganizationCreateView,
    OrganizationCreateAdminView,
    OrganizationDetailView,
    OrganizationDetailForOrganizerView,
    OrganizationUpdateView,
    OrganizationMembersView,
    OrganizationAttendanceDashboardView,
    AssignOrganizerView,
    ReviewOrganizationView,
    JoinOrganizationByCodeView,
    JoinOrganizationByInviteView,
    ClearOrgJoinedSessionView,
    LeaveOrganizationView,
)
from pulse.qr_views import (
    QRCodeView,
    QRCodeScannerView,
    ScanQRCodeView,
)

urlpatterns = [
    # Admin Management - Super Admin (must come before Django admin)
    path('admin/users/', UserManagementView.as_view(), name='user-management'),
    path('admin/users/<int:pk>/role/', UpdateUserRoleView.as_view(), name='update-user-role'),
    
    # Dashboard for Organizers and Admins
    path('dashboard/', OrganizerDashboardView.as_view(), name='organizer-dashboard'),
    
    # Admin Management - Participants
    path('admin/participants/', ManageParticipantsView.as_view(), name='manage-participants'),
    path('admin/registrations/<int:pk>/update/', UpdateRegistrationStatusView.as_view(), name='update-registration'),
    
    # Admin Management - Announcements
    path('admin/announcements/', AnnouncementListView.as_view(), name='announcement-list'),
    path('admin/announcements/add/', AnnouncementCreateView.as_view(), name='announcement-create'),
    path('admin/announcements/<int:pk>/update/', AnnouncementUpdateView.as_view(), name='announcement-update'),
    path('admin/announcements/<int:pk>/delete/', AnnouncementDeleteView.as_view(), name='announcement-delete'),
    
    # Organization Management
    path('organizations/create/', OrganizationCreateView.as_view(), name='organization-create'),
    path('organizations/<int:pk>/', OrganizationDetailForOrganizerView.as_view(), name='organization-detail-organizer'),
    path('admin/organizations/', OrganizationListView.as_view(), name='organization-list'),
    path('admin/organizations/add/', OrganizationCreateAdminView.as_view(), name='organization-create-admin'),
    path('admin/organizations/<int:pk>/', OrganizationDetailView.as_view(), name='organization-detail'),
    path('admin/organizations/<int:pk>/update/', OrganizationUpdateView.as_view(), name='organization-update'),
    path('admin/organizations/<int:pk>/members/', OrganizationMembersView.as_view(), name='organization-members'),
    path('admin/organizations/<int:pk>/attendance/', OrganizationAttendanceDashboardView.as_view(), name='organization-attendance'),
    path('admin/organizations/<int:pk>/review/', ReviewOrganizationView.as_view(), name='review-organization'),
    path('admin/organizations/<int:org_pk>/assign-organizer/<int:user_pk>/', AssignOrganizerView.as_view(), name='assign-organizer'),
    
    # Excuse Review - Admin
    path('admin/excuses/', ReviewExcusesView.as_view(), name='review-excuses'),
    path('admin/excuses/<int:pk>/review/', ReviewExcuseDetailView.as_view(), name='review-excuse-detail'),
    
    # Django Admin (must come after custom admin paths)
    path('admin/', admin.site.urls),
    
    # Authentication - Custom views (keep for backward compatibility)
    path('accounts/login/', LoginView.as_view(), name='login'),
    path('accounts/signup/', SignUpView.as_view(), name='signup'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    
    # Django Allauth URLs (for Google OAuth and other social accounts)
    path('accounts/', include('allauth.urls')),
    
    # Email Verification
    path('accounts/verification-sent/', VerificationSentView.as_view(), name='verification-sent'),
    path('accounts/verify-email/<int:user_id>/<str:token>/', VerifyEmailView.as_view(), name='verify-email'),
    path('accounts/resend-verification/', ResendVerificationView.as_view(), name='resend-verification'),
    
    # Password Reset
    path('accounts/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('accounts/password-reset-sent/', PasswordResetSentView.as_view(), name='password-reset-sent'),
    path('accounts/reset-password/<str:uid>/<str:token>/', ResetPasswordView.as_view(), name='reset-password'),
    
    # Landing Page
    path('', LandingPageView.as_view(), name='landing'),
    
    # Events
    path('events/', EventListView.as_view(), name='event-list'),
    path('events/add/', EventCreateView.as_view(), name='event-create'),
    path('events/<int:pk>/', EventDetailView.as_view(), name='event-detail'),
    path('events/<int:pk>/update/', EventUpdateView.as_view(), name='event-update'),
    path('events/<int:pk>/delete/', EventDeleteView.as_view(), name='event-delete'),
    path('events/<int:event_id>/register/', RegisterForEventView.as_view(), name='register-event'),
    path('events/<int:event_id>/unregister/', UnregisterFromEventView.as_view(), name='unregister-event'),
    
    # Announcements/Newsfeed
    path('announcements/', AnnouncementsNewsfeedView.as_view(), name='announcements-newsfeed'),
    
    # User Profile & Registrations
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('profile/change-username/', ChangeUsernameView.as_view(), name='change-username'),
    path('profile/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('profile/change-avatar/', ChangeAvatarView.as_view(), name='change-avatar'),
    path('my-registrations/', MyRegistrationsView.as_view(), name='my-registrations'),
    path('organizations/<int:org_pk>/mandatory-summary/', OrganizationMandatorySummaryView.as_view(), name='organization-mandatory-summary'),
    
    # Organizations - Join/Leave
    path('organizations/join/', JoinOrganizationByCodeView.as_view(), name='join-organization-code'),
    path('organizations/join/<str:invite_token>/', JoinOrganizationByInviteView.as_view(), name='join-organization-invite'),
    path('organizations/clear-joined-session/', ClearOrgJoinedSessionView.as_view(), name='clear-org-joined-session'),
    path('organizations/<int:org_pk>/leave/', LeaveOrganizationView.as_view(), name='leave-organization'),
    
    # Leaderboard
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    
    # QR Code Attendance
    path('qr-code/', QRCodeView.as_view(), name='my-qr-code'),
    path('qr-code/scanner/', QRCodeScannerView.as_view(), name='qr-scanner'),
    path('events/<int:event_id>/scan-qr/', ScanQRCodeView.as_view(), name='scan-qr-code'),
    
    # Excuse Requests
    path('events/<int:event_id>/request-excuse/', RequestExcuseView.as_view(), name='request-excuse'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
