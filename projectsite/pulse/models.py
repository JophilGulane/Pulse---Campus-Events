# events/models.py
from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import F
from django.dispatch import receiver
from django.db.models.signals import post_save
from datetime import datetime, timedelta
import secrets
import hashlib
import uuid
from django.urls import reverse
from django.core.validators import MinValueValidator

User = get_user_model()


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        ORGANIZER = "ORGANIZER", "Organizer"
        USER = "USER", "User"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.USER)
    phone = models.CharField(max_length=20, blank=True)
    course = models.CharField(max_length=100, blank=True)
    year_level = models.PositiveSmallIntegerField(null=True, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)  # optional (install Pillow)
    total_points = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.role})"
    
    def is_admin(self):
        """Check if user is Admin (either through role or Django superuser)."""
        # Django superusers are also considered admins
        if self.user.is_superuser:
            return True
        return self.role == self.Role.ADMIN
    
    def is_user(self):
        """Check if user is User."""
        return self.role == self.Role.USER
    
    def can_manage_events(self):
        """Check if user can create/manage events."""
        return self.is_admin()  # Includes superusers
    
    def can_manage_announcements(self):
        """Check if user can manage announcements."""
        return self.is_admin()  # Includes superusers
    
    def is_organizer(self):
        """Check if user is Organizer."""
        return self.role == self.Role.ORGANIZER
    
    def can_create_events_for_organization(self, organization):
        """Check if user can create events for a specific organization."""
        if self.is_admin():  # Admins can create events for any organization
            return True
        if self.is_organizer():
            # Check if user is an organizer of this organization
            return OrganizationMembership.objects.filter(
                user=self.user,
                organization=organization,
                role=OrganizationMembership.Role.ORGANIZER
            ).exists()
        return False

    def add_points(self, amount, reason="", event=None):
        """Add points and create a transaction record."""
        if amount == 0:
            return
        self.total_points = F("total_points") + amount
        self.save(update_fields=["total_points"])
        # Refresh from DB to get numeric value after F-expression update
        self.refresh_from_db(fields=["total_points"])
        PointsTransaction.objects.create(
            user_profile=self,
            amount=amount,
            reason=reason,
            event=event,
            balance_after=self.total_points,
        )


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


class Organization(models.Model):
    """Organization model - can be created by users, requires super admin approval."""
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_organizations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    join_code = models.CharField(max_length=20, unique=True, help_text="Unique code for users to join this organization")
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, help_text="Organization approval status")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_organizations", help_text="Super admin who reviewed this organization")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, help_text="Notes from the reviewer")
    
    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["join_code"]),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        """Generate join_code if not provided."""
        if not self.join_code:
            self.join_code = self.generate_join_code()
        super().save(*args, **kwargs)
    
    def generate_join_code(self):
        """Generate a unique join code."""
        while True:
            code = secrets.token_urlsafe(12)[:12].upper()
            if not Organization.objects.filter(join_code=code).exists():
                return code
    
    def get_or_create_invite(self, created_by=None):
        """Get or create an invite link for this organization."""
        from django.utils import timezone
        from datetime import timedelta
        
        # Try to get an active invite first
        invite = OrganizationInvite.objects.filter(
            organization=self,
            is_active=True,
        ).first()
        
        if invite and invite.is_valid():
            return invite
        
        # Create a new invite
        invite = OrganizationInvite.objects.create(
            organization=self,
            created_by=created_by,
            expires_at=timezone.now() + timedelta(days=30),
        )
        return invite
    
    def get_invite_link(self, request):
        """Generate invite link for this organization."""
        invite = self.get_or_create_invite()
        return request.build_absolute_uri(
            reverse('join-organization-invite', kwargs={'invite_token': invite.token})
        )
    
    def get_organizers(self):
        """Get all organizers of this organization."""
        return User.objects.filter(
            organization_memberships__organization=self,
            organization_memberships__role=OrganizationMembership.Role.ORGANIZER
        )
    
    def get_admins(self):
        """Get all admins of this organization."""
        return User.objects.filter(
            organization_memberships__organization=self,
            organization_memberships__role=OrganizationMembership.Role.ADMIN
        )
    
    def get_members(self):
        """Get all members (including organizers and admins) of this organization."""
        return User.objects.filter(organization_memberships__organization=self)
    
    def get_member_count(self):
        """Get total member count."""
        return OrganizationMembership.objects.filter(organization=self).count()
    
    def is_approved(self):
        """Check if organization is approved."""
        return self.status == self.Status.APPROVED
    
    def is_pending(self):
        """Check if organization is pending approval."""
        return self.status == self.Status.PENDING


class OrganizationMembership(models.Model):
    """Tracks user membership in organizations."""
    class Role(models.TextChoices):
        MEMBER = "MEMBER", "Member"
        ORGANIZER = "ORGANIZER", "Organizer"
        ADMIN = "ADMIN", "Admin"
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="organization_memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)
    joined_via = models.CharField(max_length=20, choices=[
        ("CODE", "Join Code"),
        ("INVITE", "Invite Link"),
    ], default="CODE")
    
    class Meta:
        unique_together = ("user", "organization")
        ordering = ("-joined_at",)
        indexes = [
            models.Index(fields=["organization", "role"]),
        ]
    
    def __str__(self):
        return f"{self.user.username} in {self.organization.name} ({self.role})"


class OrganizationInvite(models.Model):
    """Tracks invite links for organizations."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invites")
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_organization_invites")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Leave blank for unlimited uses")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["token"]),
        ]
    
    def __str__(self):
        return f"Invite for {self.organization.name} ({self.token[:8]}...)"
    
    def save(self, *args, **kwargs):
        """Generate token if not provided."""
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)
    
    def is_valid(self):
        """Check if invite is still valid."""
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True
    
    def use(self):
        """Mark invite as used."""
        self.used_count += 1
        self.save(update_fields=["used_count"])


class Event(models.Model):
    class EventType(models.TextChoices):
        MANDATORY = "MANDATORY", "Mandatory"
        OPTIONAL = "OPTIONAL", "Optional"
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE, related_name="events", null=True, blank=True, help_text="Organization this event belongs to. Leave blank for global events.")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_events")
    event_type = models.CharField(max_length=12, choices=EventType.choices, default=EventType.OPTIONAL, help_text="Mandatory events auto-register all organization members and count toward attendance metrics.")
    event_date = models.DateField(null=True, blank=True, help_text="Date of the event. For multi-day events, create separate events for each day.")
    number_of_days = models.PositiveIntegerField(default=1, help_text="Number of days for this event. If > 1, separate events will be created for each day.")
    # Keep datetime fields for backward compatibility and QR attendance time windows
    start_datetime = models.DateTimeField(null=True, blank=True, help_text="Auto-calculated from event_date. Used for QR attendance time windows.")
    end_datetime = models.DateTimeField(null=True, blank=True, help_text="Auto-calculated from event_date. Used for QR attendance time windows.")
    venue = models.CharField(max_length=200, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text="Leave blank for unlimited")
    registration_deadline = models.DateField(null=True, blank=True, help_text="Registration deadline must be before the event date")
    points = models.PositiveIntegerField(null=True, blank=True, help_text="Points to award when attending this event. Leave blank to use default (10 points).")
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to="event_images/", null=True, blank=True)  # optional
    pinned = models.BooleanField(default=False)
    
    # QR Code Attendance Settings - 4 Scan System
    enable_morning_in = models.BooleanField(default=True, help_text="Enable morning time-in (check-in) tracking for this event")
    enable_morning_out = models.BooleanField(default=False, help_text="Enable morning time-out (check-out) tracking for this event")
    enable_afternoon_in = models.BooleanField(default=False, help_text="Enable afternoon time-in (check-in) tracking for this event")
    enable_afternoon_out = models.BooleanField(default=False, help_text="Enable afternoon time-out (check-out) tracking for this event")
    
    # Time windows for each attendance type
    morning_in_start = models.TimeField(null=True, blank=True, help_text="Start time for morning check-in (e.g., 7:30 AM). If blank, uses event start time.")
    morning_in_end = models.TimeField(null=True, blank=True, help_text="End time for morning check-in (e.g., 8:30 AM). If blank, uses event start time + 1 hour.")
    morning_out_start = models.TimeField(null=True, blank=True, help_text="Start time for morning check-out (e.g., 11:00 AM). If blank, uses event start time.")
    morning_out_end = models.TimeField(null=True, blank=True, help_text="End time for morning check-out (e.g., 12:00 PM). If blank, uses event start time + 1 hour.")
    afternoon_in_start = models.TimeField(null=True, blank=True, help_text="Start time for afternoon check-in (e.g., 1:00 PM). If blank, uses event start time.")
    afternoon_in_end = models.TimeField(null=True, blank=True, help_text="End time for afternoon check-in (e.g., 2:00 PM). If blank, uses event start time + 1 hour.")
    afternoon_out_start = models.TimeField(null=True, blank=True, help_text="Start time for afternoon check-out (e.g., 5:00 PM). If blank, uses event start time.")
    afternoon_out_end = models.TimeField(null=True, blank=True, help_text="End time for afternoon check-out (e.g., 6:00 PM). If blank, uses event start time + 1 hour.")
    
    attendance_window_start = models.DateTimeField(null=True, blank=True, help_text="Start of overall attendance scanning window. If blank, uses event start time.")
    attendance_window_end = models.DateTimeField(null=True, blank=True, help_text="End of overall attendance scanning window. If blank, uses event end time.")

    class Meta:
        ordering = ("-event_date", "-start_datetime")
        indexes = [
            models.Index(fields=["event_date"]),
            models.Index(fields=["start_datetime"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        """Auto-calculate start_datetime and end_datetime from event_date only if not manually set."""
        from datetime import datetime, time as dt_time
        
        # Only auto-calculate if datetime fields are not set
        # If they are set (manually by user), preserve them completely
        if self.event_date:
            # For start_datetime: only auto-calculate if completely not set
            if not self.start_datetime:
                # No start_datetime set - use event_date at 00:00:00
                self.start_datetime = timezone.make_aware(
                    datetime.combine(self.event_date, dt_time(0, 0, 0))
                )
            # If start_datetime is set, keep it as-is (preserves manually set value)
            
            # For end_datetime: only auto-calculate if completely not set
            if not self.end_datetime:
                # No end_datetime set - use event_date at 23:59:59
                self.end_datetime = timezone.make_aware(
                    datetime.combine(self.event_date, dt_time(23, 59, 59))
                )
            # If end_datetime is set, keep it as-is (preserves manually set value)
        
        super().save(*args, **kwargs)

    def is_past(self):
        """Check if event is in the past based on end_datetime."""
        from django.utils import timezone
        now = timezone.now()
        
        # Primary check: use end_datetime if available
        if self.end_datetime:
            return now > self.end_datetime
        
        # Fallback: if only event_date is available, check if it's before today
        if self.event_date:
            current_date_utc = now.date()
            event_date = self.event_date
            
            # Event is past if event_date is before current date
            if event_date < current_date_utc:
                return True
            
            # If event_date is today but we have no end_datetime, we can't be sure it's past
            # So we'll return False (it might still be ongoing or upcoming)
            return False
        
        return False
    
    @property
    def is_ongoing(self):
        """Check if event is currently ongoing based on start_datetime and end_datetime."""
        from django.utils import timezone
        now = timezone.now()
        
        # If event is past, it's not ongoing
        if self.is_past():
            return False
        
        # Primary check: use start_datetime and end_datetime if available
        if self.start_datetime and self.end_datetime:
            # Event is ongoing if current time is between start and end
            return self.start_datetime <= now <= self.end_datetime
        
        # Fallback: if only event_date is available, check if it's today
        # But this is less accurate since we don't have specific times
        if self.event_date:
            current_date_utc = now.date()
            event_date = self.event_date
            
            # Only consider it ongoing if event_date is today AND we have no datetime info
            # This is a fallback for events without specific times
            if event_date == current_date_utc:
                # If we have end_datetime, check if it hasn't passed
                if self.end_datetime:
                    return now <= self.end_datetime
                # If no end_datetime, assume it's ongoing for the whole day
                return True
            
            return False
        
        return False

    def is_upcoming(self):
        """Check if event is upcoming based on start_datetime."""
        from django.utils import timezone
        now = timezone.now()
        
        # If event is ongoing or past, it's not upcoming
        if self.is_ongoing or self.is_past():
            return False
        
        # Primary check: use start_datetime if available
        if self.start_datetime:
            return now < self.start_datetime
        
        # Fallback: if only event_date is available, check if it's in the future
        if self.event_date:
            current_date_utc = now.date()
            event_date = self.event_date
            
            # Event is upcoming if event_date is in the future
            if event_date > current_date_utc:
                return True
            
            # If event_date is today, it's not upcoming (it's either ongoing or past)
            return False
        
        return False
        return False

    @property
    def registered_count(self):
        return self.registrations.filter(status=Registration.Status.PRE_REGISTERED).count()

    def available_slots(self):
        if self.capacity is None:
            return None  # unlimited
        return max(self.capacity - self.registered_count, 0)

    def is_full(self):
        if self.capacity is None:
            return False
        return self.registered_count >= self.capacity
    
    def get_points(self):
        """Return the points for this event, or default if not set."""
        return self.points if self.points is not None else 10
    
    def is_mandatory(self):
        """Check if this event is mandatory."""
        return self.event_type == self.EventType.MANDATORY
    
    def auto_register_organization_members(self):
        """Auto-register all organization members for mandatory events."""
        if not self.organization or not self.is_mandatory():
            return
        
        from django.utils import timezone
        now = timezone.now()
        
        # Check if registration is still possible
        if self.registration_deadline and self.registration_deadline < now:
            return
        if self.start_datetime < now:
            return
        
        # Get all organization members
        members = self.organization.get_members()
        
        for member in members:
            # Create or update registration
            registration, created = Registration.objects.get_or_create(
                event=self,
                user=member,
                defaults={
                    'status': Registration.Status.PRE_REGISTERED,
                    'is_mandatory': True,
                }
            )
            if not created and registration.status == Registration.Status.CANCELLED:
                # Re-register if previously cancelled
                registration.status = Registration.Status.PRE_REGISTERED
                registration.is_mandatory = True
                registration.save()
    
    def get_attendance_window_start(self):
        """Get the start of the attendance window."""
        if self.attendance_window_start:
            return self.attendance_window_start
        # If no custom window, use event_date at start of day
        if self.event_date:
            from datetime import datetime, time as dt_time
            return timezone.make_aware(datetime.combine(self.event_date, dt_time(0, 0, 0)))
        # Fallback to start_datetime if event_date not set
        return self.start_datetime
    
    def get_attendance_window_end(self):
        """Get the end of the attendance window."""
        if self.attendance_window_end:
            return self.attendance_window_end
        # If no custom window, use event_date at end of day
        if self.event_date:
            from datetime import datetime, time as dt_time
            return timezone.make_aware(datetime.combine(self.event_date, dt_time(23, 59, 59)))
        # Fallback to end_datetime if event_date not set
        return self.end_datetime
    
    def is_within_attendance_window(self):
        """Check if current time is within the attendance scanning window."""
        now = timezone.now()
        window_start = self.get_attendance_window_start()
        window_end = self.get_attendance_window_end()
        
        # If no window is set, allow scanning (fallback to per-type time windows)
        if not window_start or not window_end:
            return True
        
        # If event is ongoing, be more lenient with the window check
        # This handles timezone differences where the event date might be tomorrow in UTC
        # but today in local timezones
        if self.is_ongoing:
            # If we're on the event date (ongoing), allow scanning throughout the day
            # Check if current time is within a reasonable range of the window
            current_date_utc = now.date()
            if self.event_date:
                # If event_date is today or tomorrow (and we're past noon), allow scanning
                from datetime import timedelta
                if (self.event_date == current_date_utc or 
                    (self.event_date == current_date_utc + timedelta(days=1) and now.hour >= 12)):
                    # Allow scanning if we're within 24 hours of the window
                    # This accounts for timezone differences
                    hours_before_start = (window_start - now).total_seconds() / 3600
                    hours_after_end = (now - window_end).total_seconds() / 3600
                    # Allow if we're within 12 hours before start or 12 hours after end
                    if -12 <= hours_before_start <= 24 or -12 <= hours_after_end <= 24:
                        return True
        
        # Check if we're within the window
        return window_start <= now <= window_end
    
    def can_scan_attendance(self):
        """Check if attendance scanning is currently allowed."""
        # Check if any attendance type is enabled
        if not (self.enable_morning_in or self.enable_morning_out or 
                self.enable_afternoon_in or self.enable_afternoon_out):
            return False
        
        # If event is ongoing, allow scanning (even if not exactly within time window)
        # This handles cases where the event is today but time windows might have passed
        # or timezone differences
        if self.is_ongoing:
            return True
        
        # Otherwise, check if we're within the attendance window
        return self.is_within_attendance_window()
    
    def has_any_attendance_enabled(self):
        """Check if any attendance tracking is enabled."""
        return (self.enable_morning_in or self.enable_morning_out or 
                self.enable_afternoon_in or self.enable_afternoon_out)
    
    def can_scan_morning_in(self):
        """Check if morning in can be scanned at current time."""
        if not self.enable_morning_in:
            return False
        
        # Event must be ongoing (between start_datetime and end_datetime)
        if not self.is_ongoing:
            return False
        
        now = timezone.now()
        
        # Get the event date
        if self.event_date:
            event_date = self.event_date
        elif self.start_datetime:
            event_date = self.start_datetime.date()
        else:
            event_date = now.date()
        
        # Check if we're within the specific time window for morning in
        if self.morning_in_start and self.morning_in_end:
            start_datetime = timezone.make_aware(datetime.combine(event_date, self.morning_in_start))
            end_datetime = timezone.make_aware(datetime.combine(event_date, self.morning_in_end))
            # Must be within the time window
            return start_datetime <= now <= end_datetime
        elif self.morning_in_start:
            start_datetime = timezone.make_aware(datetime.combine(event_date, self.morning_in_start))
            end_datetime = start_datetime + timedelta(hours=1)
            return start_datetime <= now <= end_datetime
        else:
            # No specific time, allow if event is ongoing
            return True
    
    def can_scan_morning_out(self):
        """Check if morning out can be scanned at current time."""
        if not self.enable_morning_out:
            return False
        
        # Event must be ongoing (between start_datetime and end_datetime)
        if not self.is_ongoing:
            return False
        
        now = timezone.now()
        
        # Get the event date
        if self.event_date:
            event_date = self.event_date
        elif self.start_datetime:
            event_date = self.start_datetime.date()
        else:
            event_date = now.date()
        
        # Check if we're within the specific time window for morning out
        if self.morning_out_start and self.morning_out_end:
            start_datetime = timezone.make_aware(datetime.combine(event_date, self.morning_out_start))
            end_datetime = timezone.make_aware(datetime.combine(event_date, self.morning_out_end))
            # Must be within the time window
            return start_datetime <= now <= end_datetime
        elif self.morning_out_start:
            start_datetime = timezone.make_aware(datetime.combine(event_date, self.morning_out_start))
            end_datetime = start_datetime + timedelta(hours=1)
            return start_datetime <= now <= end_datetime
        else:
            # No specific time, allow if event is ongoing
            return True
    
    def can_scan_afternoon_in(self):
        """Check if afternoon in can be scanned at current time."""
        if not self.enable_afternoon_in:
            return False
        
        # Event must be ongoing (between start_datetime and end_datetime)
        if not self.is_ongoing:
            return False
        
        now = timezone.now()
        
        # Get the event date
        if self.event_date:
            event_date = self.event_date
        elif self.start_datetime:
            event_date = self.start_datetime.date()
        else:
            event_date = now.date()
        
        # Check if we're within the specific time window for afternoon in
        if self.afternoon_in_start and self.afternoon_in_end:
            start_datetime = timezone.make_aware(datetime.combine(event_date, self.afternoon_in_start))
            end_datetime = timezone.make_aware(datetime.combine(event_date, self.afternoon_in_end))
            # Must be within the time window
            return start_datetime <= now <= end_datetime
        elif self.afternoon_in_start:
            start_datetime = timezone.make_aware(datetime.combine(event_date, self.afternoon_in_start))
            end_datetime = start_datetime + timedelta(hours=1)
            return start_datetime <= now <= end_datetime
        else:
            # No specific time, allow if event is ongoing
            return True
    
    def can_scan_afternoon_out(self):
        """Check if afternoon out can be scanned at current time."""
        if not self.enable_afternoon_out:
            return False
        
        # Event must be ongoing (between start_datetime and end_datetime)
        if not self.is_ongoing:
            return False
        
        now = timezone.now()
        
        # Get the event date
        if self.event_date:
            event_date = self.event_date
        elif self.start_datetime:
            event_date = self.start_datetime.date()
        else:
            event_date = now.date()
        
        # Check if we're within the specific time window for afternoon out
        if self.afternoon_out_start and self.afternoon_out_end:
            start_datetime = timezone.make_aware(datetime.combine(event_date, self.afternoon_out_start))
            end_datetime = timezone.make_aware(datetime.combine(event_date, self.afternoon_out_end))
            # Must be within the time window
            return start_datetime <= now <= end_datetime
        elif self.afternoon_out_start:
            start_datetime = timezone.make_aware(datetime.combine(event_date, self.afternoon_out_start))
            end_datetime = start_datetime + timedelta(hours=1)
            return start_datetime <= now <= end_datetime
        else:
            # No specific time, allow if event is ongoing
            return True
    
    def get_morning_in_time_window(self):
        """Get the time window string for morning in."""
        if not self.enable_morning_in:
            return None
        event_date = self.start_datetime.date() if self.start_datetime else (self.event_date if self.event_date else timezone.now().date())
        
        if self.morning_in_start and self.morning_in_end:
            return f"{self.morning_in_start.strftime('%I:%M %p')} - {self.morning_in_end.strftime('%I:%M %p')}"
        elif self.morning_in_start:
            end_time = (datetime.combine(event_date, self.morning_in_start) + timedelta(hours=1)).time()
            return f"{self.morning_in_start.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
        else:
            return "Event start time + 1 hour"
    
    def get_morning_out_time_window(self):
        """Get the time window string for morning out."""
        if not self.enable_morning_out:
            return None
        event_date = self.start_datetime.date() if self.start_datetime else (self.event_date if self.event_date else timezone.now().date())
        
        if self.morning_out_start and self.morning_out_end:
            return f"{self.morning_out_start.strftime('%I:%M %p')} - {self.morning_out_end.strftime('%I:%M %p')}"
        elif self.morning_out_start:
            end_time = (datetime.combine(event_date, self.morning_out_start) + timedelta(hours=1)).time()
            return f"{self.morning_out_start.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
        else:
            return "Event start time + 1 hour"
    
    def get_afternoon_in_time_window(self):
        """Get the time window string for afternoon in."""
        if not self.enable_afternoon_in:
            return None
        event_date = self.start_datetime.date() if self.start_datetime else (self.event_date if self.event_date else timezone.now().date())
        
        if self.afternoon_in_start and self.afternoon_in_end:
            return f"{self.afternoon_in_start.strftime('%I:%M %p')} - {self.afternoon_in_end.strftime('%I:%M %p')}"
        elif self.afternoon_in_start:
            end_time = (datetime.combine(event_date, self.afternoon_in_start) + timedelta(hours=1)).time()
            return f"{self.afternoon_in_start.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
        else:
            return "Event start time + 1 hour"
    
    def get_afternoon_out_time_window(self):
        """Get the time window string for afternoon out."""
        if not self.enable_afternoon_out:
            return None
        event_date = self.start_datetime.date() if self.start_datetime else (self.event_date if self.event_date else timezone.now().date())
        
        if self.afternoon_out_start and self.afternoon_out_end:
            return f"{self.afternoon_out_start.strftime('%I:%M %p')} - {self.afternoon_out_end.strftime('%I:%M %p')}"
        elif self.afternoon_out_start:
            end_time = (datetime.combine(event_date, self.afternoon_out_start) + timedelta(hours=1)).time()
            return f"{self.afternoon_out_start.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
        else:
            return "Event start time + 1 hour"


class Registration(models.Model):
    class Status(models.TextChoices):
        PRE_REGISTERED = "PRE", "Pre-registered"
        CONFIRMED = "CONFIRMED", "Confirmed"
        ATTENDED = "ATTENDED", "Attended"
        CANCELLED = "CANCELLED", "Cancelled"
        NO_SHOW = "NO_SHOW", "No-show"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="registrations")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PRE_REGISTERED)
    is_mandatory = models.BooleanField(default=False, help_text="True if this registration is for a mandatory event")
    registered_at = models.DateTimeField(auto_now_add=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("event", "user")
        ordering = ("-registered_at",)
        indexes = [
            models.Index(fields=["event", "status"]),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.event.title} ({self.status})"

    def mark_attended(self, award_points=0, reason="Participation"):
        """Mark attendance and optionally award points."""
        self.status = self.Status.ATTENDED
        self.checked_in_at = timezone.now()
        self.save(update_fields=["status", "checked_in_at"])
        if award_points and hasattr(self.user, "profile"):
            self.user.profile.add_points(amount=award_points, reason=reason, event=self.event)


class PointsTransaction(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="points_transactions")
    amount = models.IntegerField()  # positive or negative
    reason = models.CharField(max_length=255, blank=True)
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    balance_after = models.IntegerField()

    class Meta:
        ordering = ("-timestamp",)

    def __str__(self):
        sign = "+" if self.amount >= 0 else ""
        return f"{self.user_profile.user.username}: {sign}{self.amount} ({self.reason})"


class Announcement(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE, related_name="announcements", null=True, blank=True, help_text="Organization this announcement belongs to. Leave blank for global announcements.")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="announcements")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    pinned = models.BooleanField(default=False)
    image = models.ImageField(upload_to="announcement_images/", null=True, blank=True)  # optional

    class Meta:
        ordering = ("-pinned", "-created_at")
        indexes = [
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return self.title

    def is_active(self):
        if self.expires_at:
            return timezone.now() < self.expires_at
        return True


class QRCode(models.Model):
    """Stores unique QR codes for users tied to their organization memberships."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="qr_codes")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="member_qr_codes", null=True, blank=True)
    token = models.CharField(max_length=64, unique=True, db_index=True, help_text="Unique token for QR code scanning")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ("user", "organization")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["user", "organization"]),
        ]
    
    def __str__(self):
        org_name = self.organization.name if self.organization else "Global"
        return f"QR Code for {self.user.username} ({org_name})"
    
    def save(self, *args, **kwargs):
        if not self.token:
            # Generate a unique token based on user ID, organization ID, and a random component
            components = [
                str(self.user.id),
                str(self.organization.id) if self.organization else "global",
                str(uuid.uuid4())
            ]
            token_string = "|".join(components)
            self.token = hashlib.sha256(token_string.encode()).hexdigest()[:32]
        super().save(*args, **kwargs)
    
    def get_qr_data(self):
        """Return the data to encode in the QR code."""
        return self.token
    
    def is_valid_for_organization(self, organization):
        """Check if this QR code is valid for the given organization."""
        if not self.organization:
            return True  # Global QR codes work for all organizations
        return self.organization == organization


class AttendanceRecord(models.Model):
    """Tracks morning and afternoon time-in and time-out for event attendance via QR code scanning."""
    class AttendanceType(models.TextChoices):
        MORNING_IN = "MORNING_IN", "Morning Time In"
        MORNING_OUT = "MORNING_OUT", "Morning Time Out"
        AFTERNOON_IN = "AFTERNOON_IN", "Afternoon Time In"
        AFTERNOON_OUT = "AFTERNOON_OUT", "Afternoon Time Out"
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attendance_records")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attendance_records")
    organizer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="scanned_attendance", help_text="Organizer who scanned the QR code")
    attendance_type = models.CharField(max_length=15, choices=AttendanceType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    points_awarded = models.PositiveIntegerField(default=0, help_text="Points awarded for this attendance record")
    notes = models.TextField(blank=True, help_text="Optional notes from organizer")
    
    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["event", "user"]),
            models.Index(fields=["event", "user", "attendance_type"]),
            models.Index(fields=["timestamp"]),
        ]
        # Prevent duplicate time-in or time-out for same event/user
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user", "attendance_type"],
                name="unique_attendance_type_per_event_user"
            )
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.get_attendance_type_display()} at {self.event.title} ({self.timestamp})"
    
    @classmethod
    def get_morning_in(cls, event, user):
        """Get the morning time-in record for a user at an event."""
        return cls.objects.filter(
            event=event,
            user=user,
            attendance_type=cls.AttendanceType.MORNING_IN
        ).first()
    
    @classmethod
    def get_morning_out(cls, event, user):
        """Get the morning time-out record for a user at an event."""
        return cls.objects.filter(
            event=event,
            user=user,
            attendance_type=cls.AttendanceType.MORNING_OUT
        ).first()
    
    @classmethod
    def get_afternoon_in(cls, event, user):
        """Get the afternoon time-in record for a user at an event."""
        return cls.objects.filter(
            event=event,
            user=user,
            attendance_type=cls.AttendanceType.AFTERNOON_IN
        ).first()
    
    @classmethod
    def get_afternoon_out(cls, event, user):
        """Get the afternoon time-out record for a user at an event."""
        return cls.objects.filter(
            event=event,
            user=user,
            attendance_type=cls.AttendanceType.AFTERNOON_OUT
        ).first()
    
    @classmethod
    def has_morning_in(cls, event, user):
        """Check if user has morning time-in for this event."""
        return cls.get_morning_in(event, user) is not None
    
    @classmethod
    def has_morning_out(cls, event, user):
        """Check if user has morning time-out for this event."""
        return cls.get_morning_out(event, user) is not None
    
    @classmethod
    def has_afternoon_in(cls, event, user):
        """Check if user has afternoon time-in for this event."""
        return cls.get_afternoon_in(event, user) is not None
    
    @classmethod
    def has_afternoon_out(cls, event, user):
        """Check if user has afternoon time-out for this event."""
        return cls.get_afternoon_out(event, user) is not None
    
    @classmethod
    def get_attendance_type(cls, event, user):
        """Determine the next attendance type that should be scanned for a user at an event."""
        # Check what's enabled and what's already recorded
        has_morning_in = cls.has_morning_in(event, user)
        has_morning_out = cls.has_morning_out(event, user)
        has_afternoon_in = cls.has_afternoon_in(event, user)
        has_afternoon_out = cls.has_afternoon_out(event, user)
        
        # Morning In - check if enabled, not already recorded, and within time window
        if event.enable_morning_in and not has_morning_in and event.can_scan_morning_in():
            return cls.AttendanceType.MORNING_IN
        # Morning Out - check time window (no prerequisite required)
        if event.enable_morning_out and not has_morning_out and event.can_scan_morning_out():
            return cls.AttendanceType.MORNING_OUT
        # Afternoon In - check time window
        if event.enable_afternoon_in and not has_afternoon_in and event.can_scan_afternoon_in():
            return cls.AttendanceType.AFTERNOON_IN
        # Afternoon Out - check time window (no prerequisite required)
        if event.enable_afternoon_out and not has_afternoon_out and event.can_scan_afternoon_out():
            return cls.AttendanceType.AFTERNOON_OUT
        
        return None  # All required scans completed or not within time windows
    
    @classmethod
    def is_fully_attended(cls, event, user):
        """Check if user has completed all required attendance scans."""
        # Check each enabled attendance type
        if event.enable_morning_in and not cls.has_morning_in(event, user):
            return False
        if event.enable_morning_out and not cls.has_morning_out(event, user):
            return False
        if event.enable_afternoon_in and not cls.has_afternoon_in(event, user):
            return False
        if event.enable_afternoon_out and not cls.has_afternoon_out(event, user):
            return False
        return True


class Excuse(models.Model):
    """Tracks excuse requests for mandatory event attendance."""
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
    
    class AttendanceType(models.TextChoices):
        MORNING_IN = "MORNING_IN", "Morning Time In"
        MORNING_OUT = "MORNING_OUT", "Morning Time Out"
        AFTERNOON_IN = "AFTERNOON_IN", "Afternoon Time In"
        AFTERNOON_OUT = "AFTERNOON_OUT", "Afternoon Time Out"
        ALL = "ALL", "All Attendance Types"
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="excuses")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="excuses")
    attendance_type = models.CharField(max_length=15, choices=AttendanceType.choices, default=AttendanceType.ALL, help_text="Which attendance type(s) this excuse applies to")
    reason = models.TextField(help_text="Reason for the excuse request")
    proof_link = models.URLField(max_length=500, blank=True, help_text="Google Drive link or URL to proof document (medical certificate, excuse letter signed by dean, etc.)")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_excuses", help_text="Organizer who reviewed this excuse")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, help_text="Notes from the reviewer")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["event", "user"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.event.title} ({self.get_status_display()})"
    
    def is_approved(self):
        """Check if excuse is approved."""
        return self.status == self.Status.APPROVED
    
    def is_pending(self):
        """Check if excuse is pending review."""
        return self.status == self.Status.PENDING
    
    def applies_to_attendance_type(self, attendance_type):
        """Check if this excuse applies to a specific attendance type."""
        if self.attendance_type == self.AttendanceType.ALL[0]:
            return True
        return self.attendance_type == attendance_type
    
    def get_attendance_type_label(self):
        """Get the human-readable label for the attendance type."""
        # Direct mapping from the choices - use the second element (display value) of each tuple
        if self.attendance_type == self.AttendanceType.MORNING_IN[0]:
            return self.AttendanceType.MORNING_IN[1]
        elif self.attendance_type == self.AttendanceType.MORNING_OUT[0]:
            return self.AttendanceType.MORNING_OUT[1]
        elif self.attendance_type == self.AttendanceType.AFTERNOON_IN[0]:
            return self.AttendanceType.AFTERNOON_IN[1]
        elif self.attendance_type == self.AttendanceType.AFTERNOON_OUT[0]:
            return self.AttendanceType.AFTERNOON_OUT[1]
        elif self.attendance_type == self.AttendanceType.ALL[0]:
            return self.AttendanceType.ALL[1]
        else:
            # Fallback to Django's method or return the value itself
            return self.get_attendance_type_display() or self.attendance_type


# Signals for auto-registration of mandatory events
@receiver(post_save, sender=Event)
def auto_register_mandatory_event(sender, instance, created, **kwargs):
    """Auto-register organization members when a mandatory event is created or updated."""
    if instance.is_mandatory() and instance.organization:
        instance.auto_register_organization_members()


@receiver(post_save, sender=OrganizationMembership)
def auto_register_new_member_to_mandatory_events(sender, instance, created, **kwargs):
    """Auto-register new organization members to existing mandatory upcoming events."""
    if created:
        # Get all mandatory upcoming events for this organization
        now = timezone.now()
        mandatory_events = Event.objects.filter(
            organization=instance.organization,
            event_type=Event.EventType.MANDATORY,
            start_datetime__gt=now,
        )
        
        for event in mandatory_events:
            # Check if registration is still possible
            if event.registration_deadline and event.registration_deadline < now:
                continue
            
            # Create registration
            Registration.objects.get_or_create(
                event=event,
                user=instance.user,
                defaults={
                    'status': Registration.Status.PRE_REGISTERED,
                    'is_mandatory': True,
                }
            )
        
        # Auto-generate QR code for the organization
        QRCode.objects.get_or_create(
            user=instance.user,
            organization=instance.organization,
            defaults={'is_active': True}
        )
