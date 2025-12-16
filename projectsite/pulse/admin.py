# events/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.http import HttpResponse
import csv
from .models import Event, Registration, UserProfile, PointsTransaction, Announcement, Organization, OrganizationMembership, OrganizationInvite, QRCode, AttendanceRecord

User = get_user_model()

# Default points to award when using admin action
DEFAULT_AWARD_POINTS = 10


class RegistrationInline(admin.TabularInline):
    model = Registration
    extra = 0
    readonly_fields = ("registered_at", "checked_in_at")
    fields = ("user", "status", "is_mandatory", "registered_at", "checked_in_at", "notes")
    show_change_link = True
    ordering = ("-registered_at",)


class PointsTransactionInline(admin.TabularInline):
    model = PointsTransaction
    extra = 0
    readonly_fields = ("timestamp", "balance_after")
    fields = ("amount", "reason", "event", "timestamp", "balance_after")
    show_change_link = False
    ordering = ("-timestamp",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "event_type", "start_datetime", "end_datetime", "venue", "capacity", "pinned", "created_by")
    list_filter = ("pinned", "is_public", "event_type", "organization", "start_datetime", "created_at")
    search_fields = ("title", "description", "venue", "created_by__username", "created_by__email", "organization__name")
    date_hierarchy = "start_datetime"
    readonly_fields = ("created_at", "updated_at")
    inlines = [RegistrationInline]
    ordering = ("-start_datetime",)
    fieldsets = (
        (None, {"fields": ("title", "description", "organization", "event_type", "created_by", "image", "pinned")}),
        ("Schedule & Capacity", {"fields": ("start_datetime", "end_datetime", "venue", "capacity", "registration_deadline", "points")}),
        ("QR Code Attendance", {"fields": ("enable_time_in", "enable_time_out", "attendance_window_start", "attendance_window_end")}),
        ("Visibility", {"fields": ("is_public",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "status", "is_mandatory", "registered_at", "checked_in_at")
    list_filter = ("status", "is_mandatory", "event")
    search_fields = ("user__username", "user__email", "event__title", "notes")
    readonly_fields = ("registered_at", "checked_in_at")
    actions = ("admin_mark_attended", "admin_award_points", "export_selected_registrations_csv")

    def admin_mark_attended(self, request, queryset):
        """
        Mark selected registrations as attended and award event-specific points to the user profile (if exists).
        """
        updated = 0
        total_points_awarded = 0
        for reg in queryset:
            if reg.status != Registration.Status.ATTENDED:
                points_to_award = reg.event.get_points()
                reg.mark_attended(award_points=points_to_award, reason="Admin-marked attendance")
                updated += 1
                total_points_awarded += points_to_award
        avg_points = total_points_awarded // updated if updated > 0 else 0
        self.message_user(request, f"{updated} registrations marked as attended. Average points awarded: {avg_points} per registration.")
    admin_mark_attended.short_description = "Mark selected registrations as attended (award event-specific points)"

    def admin_award_points(self, request, queryset):
        """
        Award event-specific points to each registration's user profile without changing status.
        """
        awarded = 0
        total_points_awarded = 0
        for reg in queryset:
            profile = getattr(reg.user, "profile", None)
            if profile:
                points_to_award = reg.event.get_points()
                profile.add_points(amount=points_to_award, reason="Admin-awarded points", event=reg.event)
                awarded += 1
                total_points_awarded += points_to_award
        avg_points = total_points_awarded // awarded if awarded > 0 else 0
        self.message_user(request, f"Awarded points to {awarded} users. Average points: {avg_points} per user.")
    admin_award_points.short_description = "Award event-specific points to selected registration users"

    def export_selected_registrations_csv(self, request, queryset):
        """
        Export selected registrations as CSV (user, email, event, status, registered_at, checked_in_at).
        """
        meta = self.model._meta
        fieldnames = ["username", "email", "event_title", "status", "registered_at", "checked_in_at", "notes"]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename=registrations_export.csv'
        writer = csv.writer(response)
        writer.writerow(fieldnames)

        for reg in queryset.select_related("user", "event"):
            writer.writerow([
                reg.user.username,
                reg.user.email,
                reg.event.title,
                reg.status,
                reg.registered_at.isoformat() if reg.registered_at else "",
                reg.checked_in_at.isoformat() if reg.checked_in_at else "",
                reg.notes or "",
            ])

        return response
    export_selected_registrations_csv.short_description = "Export selected registrations as CSV"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "course", "year_level", "total_points", "phone")
    list_filter = ("role", "year_level")
    search_fields = ("user__username", "user__email", "course", "phone")
    readonly_fields = ("total_points",)
    inlines = [PointsTransactionInline]
    ordering = ("-total_points",)


@admin.register(PointsTransaction)
class PointsTransactionAdmin(admin.ModelAdmin):
    list_display = ("user_profile", "amount", "reason", "event", "timestamp", "balance_after")
    list_filter = ("timestamp",)
    search_fields = ("user_profile__user__username", "reason")
    readonly_fields = ("timestamp",)
    ordering = ("-timestamp",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "created_by", "created_at", "expires_at", "pinned")
    list_filter = ("pinned", "organization")
    search_fields = ("title", "content", "created_by__username", "organization__name")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "join_code", "is_active", "created_by", "created_at", "member_count")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "description", "join_code", "created_by__username")
    readonly_fields = ("join_code", "created_at", "updated_at")
    date_hierarchy = "created_at"
    
    def member_count(self, obj):
        return obj.get_member_count()
    member_count.short_description = "Members"
    
    fieldsets = (
        (None, {"fields": ("name", "description", "is_active", "created_by")}),
        ("Join Settings", {"fields": ("join_code",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


class OrganizationMembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0
    readonly_fields = ("joined_at",)
    fields = ("user", "role", "joined_at", "joined_via")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "joined_at", "joined_via")
    list_filter = ("role", "joined_via", "organization")
    search_fields = ("user__username", "user__email", "organization__name")
    readonly_fields = ("joined_at",)
    date_hierarchy = "joined_at"


@admin.register(OrganizationInvite)
class OrganizationInviteAdmin(admin.ModelAdmin):
    list_display = ("organization", "token", "created_by", "created_at", "expires_at", "used_count", "max_uses", "is_active")
    list_filter = ("is_active", "created_at")
    search_fields = ("organization__name", "token", "created_by__username")
    readonly_fields = ("token", "created_at", "used_count")
    date_hierarchy = "created_at"


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "token", "created_at", "last_used_at", "is_active")
    list_filter = ("is_active", "organization", "created_at")
    search_fields = ("user__username", "user__email", "organization__name", "token")
    readonly_fields = ("token", "created_at", "last_used_at")
    date_hierarchy = "created_at"


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "organizer", "attendance_type", "timestamp", "points_awarded")
    list_filter = ("attendance_type", "event", "timestamp")
    search_fields = ("user__username", "user__email", "event__title", "organizer__username")
    readonly_fields = ("timestamp",)
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)


# Attach Profile inline to the default User admin for convenience
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User as DjangoUser  # used only to compare

class ProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "profile"
    fk_name = "user"
    readonly_fields = ("total_points",)


# Only attempt to customize the auth User admin if the project's user model is the default Django User.
try:
    # If the project's user model is the default auth.User, replace its admin to show profile inline
    if User.__name__ == "User" and User._meta.app_label == "auth":
        # Unregister default User admin and re-register with profile inline
        try:
            admin.site.unregister(User)
        except Exception:
            pass

        @admin.register(User)
        class UserAdmin(BaseUserAdmin):
            inlines = (ProfileInline,)
            list_display = ("username", "email", "first_name", "last_name", "is_staff")
            # Keep other behavior from BaseUserAdmin
except Exception:
    # If anything goes wrong, don't break the admin - fallback to default behavior.
    pass
