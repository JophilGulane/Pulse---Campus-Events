from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.contrib.auth import get_user_model
from .models import Event, Announcement, Organization, OrganizationMembership, OrganizationInvite, Excuse, UserProfile
from .mixins import user_has_organizer_membership
from django.core.exceptions import ValidationError
from django.utils import timezone

User = get_user_model()


class EventForm(forms.ModelForm):
    """Form for creating and updating Event instances."""
    
    # Separate time fields that will be combined with event_date
    start_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
            'type': 'time',
            'step': '60'
        }),
        help_text='Start time for the event. The date will be automatically set from the event date above.'
    )
    end_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
            'type': 'time',
            'step': '60'
        }),
        help_text='End time for the event. The date will be automatically set from the event date above.'
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # If editing an existing event, populate time fields from datetime fields
        if self.instance and self.instance.pk:
            if self.instance.start_datetime:
                start_local = timezone.localtime(self.instance.start_datetime)
                self.fields['start_time'].initial = start_local.strftime('%H:%M')
            if self.instance.end_datetime:
                end_local = timezone.localtime(self.instance.end_datetime)
                self.fields['end_time'].initial = end_local.strftime('%H:%M')
        
        # Filter organizations based on user permissions
        if user:
            is_admin_user = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())
            is_profile_organizer = hasattr(user, 'profile') and user.profile.is_organizer()
            is_membership_organizer = user_has_organizer_membership(user)

            if is_admin_user:
                # Super admins/admins can select any organization or none (for global events)
                self.fields['organization'].queryset = Organization.objects.filter(is_active=True)
                self.fields['organization'].required = False
                self.fields['organization'].help_text = "Select the organization this event belongs to. Leave blank for global events (only admins and super admins can create global events)."
            elif is_profile_organizer or is_membership_organizer:
                # Organizers (profile role or membership) can only select their organizations
                # Organizers CANNOT create global events - they must select an organization
                organizer_orgs = Organization.objects.filter(
                    is_active=True,
                    memberships__user=user,
                    memberships__role=OrganizationMembership.Role.ORGANIZER
                ).distinct()
                self.fields['organization'].queryset = organizer_orgs

                if organizer_orgs.exists():
                    self.fields['organization'].required = True
                    self.fields['organization'].help_text = "Select the organization this event belongs to. Organizers cannot create global events."
                    if organizer_orgs.count() == 1:
                        self.fields['organization'].initial = organizer_orgs.first()
                else:
                    # No eligible organizations found - hide field but keep form valid
                    self.fields['organization'].widget = forms.HiddenInput()
                    self.fields['organization'].required = False
                    self.fields['organization'].help_text = "No eligible organizations available. Contact an admin."
            else:
                # Regular users cannot create events - hide field
                self.fields['organization'].queryset = Organization.objects.none()
                self.fields['organization'].widget = forms.HiddenInput()
    
    class Meta:
        model = Event
        fields = [
            'title',
            'description',
            'organization',
            'event_type',
            'event_date',
            'start_datetime',
            'end_datetime',
            'start_time',
            'end_time',
            'venue',
            'capacity',
            'registration_deadline',
            'points',
            'is_public',
            'pinned',
            'image',
            'enable_morning_in',
            'enable_morning_out',
            'enable_afternoon_in',
            'enable_afternoon_out',
            'morning_in_start',
            'morning_in_end',
            'morning_out_start',
            'morning_out_end',
            'afternoon_in_start',
            'afternoon_in_end',
            'afternoon_out_start',
            'afternoon_out_end',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'placeholder': 'Enter a compelling event title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white resize-none',
                'rows': 5,
                'placeholder': 'Describe your event in detail...'
            }),
            'organization': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
            }),
            'event_type': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
            }),
            'event_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'type': 'date'
            }),
            # start_datetime and end_datetime are hidden - we use start_time and end_time instead
            'start_datetime': forms.HiddenInput(),
            'end_datetime': forms.HiddenInput(),
            'registration_deadline': forms.DateInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'type': 'date'
            }),
            'venue': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'placeholder': 'Event location or venue'
            }),
            'capacity': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'placeholder': 'Leave blank for unlimited capacity',
                'min': 1
            }),
            'points': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'placeholder': 'Leave blank for default (10 points)',
                'min': 0
            }),
            'is_public': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer'
            }),
            'pinned': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer'
            }),
            'image': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer',
                'accept': 'image/*'
            }),
            'enable_morning_in': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer'
            }),
            'enable_morning_out': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer'
            }),
            'enable_afternoon_in': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer'
            }),
            'enable_afternoon_out': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer'
            }),
            'morning_in_start': forms.TimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all bg-white',
                'type': 'time'
            }),
            'morning_in_end': forms.TimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all bg-white',
                'type': 'time'
            }),
            'morning_out_start': forms.TimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all bg-white',
                'type': 'time'
            }),
            'morning_out_end': forms.TimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all bg-white',
                'type': 'time'
            }),
            'afternoon_in_start': forms.TimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-all bg-white',
                'type': 'time'
            }),
            'afternoon_in_end': forms.TimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-all bg-white',
                'type': 'time'
            }),
            'afternoon_out_start': forms.TimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-all bg-white',
                'type': 'time'
            }),
            'afternoon_out_end': forms.TimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-all bg-white',
                'type': 'time'
            }),
        }
        
        labels = {
            'title': 'Event Title',
            'description': 'Description',
            'organization': 'Organization',
            'event_type': 'Event Type',
            'start_time': 'Start Time',
            'end_time': 'End Time',
            'venue': 'Venue',
            'capacity': 'Capacity',
            'registration_deadline': 'Registration Deadline',
            'points': 'Points Awarded',
            'is_public': 'Make this event public',
            'pinned': 'Pin to top',
            'image': 'Event Image',
            'enable_morning_in': 'Enable Morning Time-In',
            'enable_morning_out': 'Enable Morning Time-Out',
            'enable_afternoon_in': 'Enable Afternoon Time-In',
            'enable_afternoon_out': 'Enable Afternoon Time-Out',
            'morning_in_start': 'Morning In Start Time',
            'morning_in_end': 'Morning In End Time',
            'morning_out_start': 'Morning Out Start Time',
            'morning_out_end': 'Morning Out End Time',
            'afternoon_in_start': 'Afternoon In Start Time',
            'afternoon_in_end': 'Afternoon In End Time',
            'afternoon_out_start': 'Afternoon Out Start Time',
            'afternoon_out_end': 'Afternoon Out End Time',
        }
        
        help_texts = {
            'organization': 'Select the organization this event belongs to. Leave blank for global events (only admins and super admins can create global events).',
            'event_type': 'Mandatory events auto-register all organization members and count toward attendance metrics.',
            'capacity': 'Leave blank for unlimited capacity',
            'registration_deadline': 'Participants cannot register after this date',
            'points': 'Points participants will receive when attending this event. Leave blank for default (10 points).',
            'is_public': 'Public events are visible to all users',
            'pinned': 'Pinned events appear at the top of the list',
            'enable_morning_in': 'Allow organizers to scan QR codes for morning check-in',
            'enable_morning_out': 'Require morning check-out for full morning attendance credit',
            'enable_afternoon_in': 'Allow organizers to scan QR codes for afternoon check-in',
            'enable_afternoon_out': 'Require afternoon check-out for full afternoon attendance credit',
            'morning_in_start': 'Start time for morning check-in (e.g., 7:30 AM). Leave blank to use event start time.',
            'morning_in_end': 'End time for morning check-in (e.g., 8:30 AM). Leave blank for 1 hour after start time.',
            'morning_out_start': 'Start time for morning check-out (e.g., 11:00 AM). Leave blank to use event start time.',
            'morning_out_end': 'End time for morning check-out (e.g., 12:00 PM). Leave blank for 1 hour after start time.',
            'afternoon_in_start': 'Start time for afternoon check-in (e.g., 1:00 PM). Leave blank to use event start time.',
            'afternoon_in_end': 'End time for afternoon check-in (e.g., 2:00 PM). Leave blank for 1 hour after start time.',
            'afternoon_out_start': 'Start time for afternoon check-out (e.g., 5:00 PM). Leave blank to use event start time.',
            'afternoon_out_end': 'End time for afternoon check-out (e.g., 6:00 PM). Leave blank for 1 hour after start time.',
        }
    
    def clean(self):
        cleaned_data = super().clean()
        event_date = cleaned_data.get('event_date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        registration_deadline = cleaned_data.get('registration_deadline')
        
        # Require event_date for event creation
        if not event_date:
            raise forms.ValidationError({
                'event_date': 'Event date is required.'
            })
        
        # Combine event_date with time fields to create datetime fields
        if event_date:
            from datetime import datetime, time as dt_time
            
            # Create start_datetime from event_date and start_time
            if start_time:
                start_datetime = timezone.make_aware(
                    datetime.combine(event_date, start_time)
                )
            else:
                # Default to event_date at 00:00 if no time provided
                start_datetime = timezone.make_aware(
                    datetime.combine(event_date, dt_time(0, 0, 0))
                )
            cleaned_data['start_datetime'] = start_datetime
            
            # Create end_datetime from event_date and end_time
            if end_time:
                end_datetime = timezone.make_aware(
                    datetime.combine(event_date, end_time)
                )
            else:
                # Default to event_date at 23:59 if no time provided
                end_datetime = timezone.make_aware(
                    datetime.combine(event_date, dt_time(23, 59, 59))
                )
            cleaned_data['end_datetime'] = end_datetime
            
            # Validate that end_time is after start_time
            if start_time and end_time:
                if end_time <= start_time:
                    raise forms.ValidationError({
                        'end_time': 'End time must be after start time.'
                    })
        
        if event_date and registration_deadline:
            if registration_deadline >= event_date:
                raise forms.ValidationError(
                    "Registration deadline must be before the event date."
                )
        
        return cleaned_data


class CustomUserCreationForm(UserCreationForm):
    """Extended user registration form with email and name fields."""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email'
        })
    )
    first_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First name (optional)',
            'autocomplete': 'given-name'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last name (optional)',
            'autocomplete': 'family-name'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Choose a username',
                'autocomplete': 'username'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Style password fields
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Create a password',
            'autocomplete': 'new-password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password'
        })
        # Remove password validation help text
        self.fields['password1'].help_text = None
        self.fields['password2'].help_text = None

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise ValidationError("A user with that email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        if commit:
            user.save()
        return user


class AnnouncementForm(forms.ModelForm):
    """Form for creating and updating Announcement instances."""
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter organizations based on user permissions
        if user:
            is_admin_user = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())
            is_profile_organizer = hasattr(user, 'profile') and user.profile.is_organizer()
            is_membership_organizer = user_has_organizer_membership(user)

            if is_admin_user:
                # Super admins/admins can select any organization or none (for global announcements)
                self.fields['organization'].queryset = Organization.objects.filter(is_active=True)
                self.fields['organization'].required = False
                self.fields['organization'].help_text = "Select the organization this announcement belongs to. Leave blank for global announcements (only admins and super admins can create global announcements)."
            elif is_profile_organizer or is_membership_organizer:
                # Organizers (profile role or membership) can only select their organizations
                # Organizers CANNOT create global announcements - they must select an organization
                organizer_orgs = Organization.objects.filter(
                    is_active=True,
                    memberships__user=user,
                    memberships__role=OrganizationMembership.Role.ORGANIZER
                ).distinct()
                self.fields['organization'].queryset = organizer_orgs

                if organizer_orgs.exists():
                    self.fields['organization'].required = True
                    self.fields['organization'].help_text = "Select the organization this announcement belongs to. Organizers cannot create global announcements."
                    if organizer_orgs.count() == 1:
                        self.fields['organization'].initial = organizer_orgs.first()
                else:
                    self.fields['organization'].widget = forms.HiddenInput()
                    self.fields['organization'].required = False
                    self.fields['organization'].help_text = "No eligible organizations available. Contact an admin."
            else:
                self.fields['organization'].queryset = Organization.objects.none()
                self.fields['organization'].widget = forms.HiddenInput()
    
    class Meta:
        model = Announcement
        fields = [
            'title',
            'content',
            'organization',
            'expires_at',
            'pinned',
            'image',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'placeholder': 'Enter announcement title'
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white resize-none',
                'rows': 8,
                'placeholder': 'Write your announcement content here...'
            }),
            'organization': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
            }),
            'expires_at': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'type': 'datetime-local'
            }),
            'pinned': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer'
            }),
            'image': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer',
                'accept': 'image/*'
            }),
        }
        
        labels = {
            'title': 'Announcement Title',
            'content': 'Content',
            'organization': 'Organization',
            'expires_at': 'Expiration Date & Time',
            'pinned': 'Pin to top',
            'image': 'Announcement Image',
        }
        
        help_texts = {
            'organization': 'Select the organization this announcement belongs to. Leave blank for global announcements (only admins and super admins can create global announcements).',
            'expires_at': 'Leave blank if this announcement should never expire',
            'pinned': 'Pinned announcements appear at the top of the list',
        }
    
    def clean(self):
        cleaned_data = super().clean()
        expires_at = cleaned_data.get('expires_at')
        
        if expires_at:
            if expires_at < timezone.now():
                raise forms.ValidationError(
                    "Expiration date cannot be in the past."
                )
        
        return cleaned_data


class OrganizationForm(forms.ModelForm):
    """Form for creating and updating Organization instances."""
    
    class Meta:
        model = Organization
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-pulse-blue/30 rounded-pulse focus:ring-2 focus:ring-pulse-blue focus:border-pulse-blue transition-all bg-pulse-navyLighter text-white placeholder:text-text-muted',
                'placeholder': 'Enter organization name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-pulse-blue/30 rounded-pulse focus:ring-2 focus:ring-pulse-blue focus:border-pulse-blue transition-all bg-pulse-navyLighter text-white placeholder:text-text-muted resize-none',
                'rows': 4,
                'placeholder': 'Describe the organization...'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-pulse-blue border-pulse-blue/30 rounded focus:ring-pulse-blue cursor-pointer bg-pulse-navyLighter'
            }),
        }
        labels = {
            'name': 'Organization Name',
            'description': 'Description',
            'is_active': 'Active',
        }
        help_texts = {
            'is_active': 'Inactive organizations cannot be joined by new members',
        }


class JoinOrganizationByCodeForm(forms.Form):
    """Form for joining an organization using a join code."""
    join_code = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white uppercase',
            'placeholder': 'Enter join code',
            'style': 'text-transform: uppercase;'
        }),
        label='Join Code',
        help_text='Enter the organization join code'
    )
    
    def clean_join_code(self):
        join_code = self.cleaned_data.get('join_code').upper().strip()
        if not Organization.objects.filter(join_code=join_code, is_active=True).exists():
            raise forms.ValidationError('Invalid or inactive join code.')
        return join_code


class ExcuseForm(forms.ModelForm):
    """Form for requesting an excuse for mandatory event attendance."""
    class Meta:
        model = Excuse
        fields = ['attendance_type', 'reason', 'proof_link']
        widgets = {
            'attendance_type': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-all bg-white',
            }),
            'reason': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-all bg-white resize-none',
                'rows': 5,
                'placeholder': 'Please provide a detailed reason for your excuse request...'
            }),
            'proof_link': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-all bg-white',
                'placeholder': 'https://drive.google.com/... or any proof document URL'
            }),
        }
        labels = {
            'attendance_type': 'Attendance Type',
            'reason': 'Reason',
            'proof_link': 'Proof Document Link',
        }
        help_texts = {
            'attendance_type': 'Select which attendance type(s) this excuse applies to',
            'reason': 'Provide a detailed explanation for your absence',
            'proof_link': 'Optional: Google Drive link or URL to proof document (medical certificate, excuse letter signed by dean, etc.)',
        }
    
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)
        
        # Filter attendance types based on what's enabled for the event
        if event:
            choices = [('', '---------')]
            # Use the full choice tuples directly - each choice is already a (value, label) tuple
            if event.enable_morning_in:
                choices.append(('MORNING_IN', 'Morning Time In'))
            if event.enable_morning_out:
                choices.append(('MORNING_OUT', 'Morning Time Out'))
            if event.enable_afternoon_in:
                choices.append(('AFTERNOON_IN', 'Afternoon Time In'))
            if event.enable_afternoon_out:
                choices.append(('AFTERNOON_OUT', 'Afternoon Time Out'))
            choices.append(('ALL', 'All Attendance Types'))
            self.fields['attendance_type'].choices = choices


class ExcuseReviewForm(forms.ModelForm):
    """Form for organizers to review excuse requests."""
    class Meta:
        model = Excuse
        fields = ['status', 'review_notes']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
            }),
            'review_notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white',
                'rows': 4,
                'placeholder': 'Add any notes about your decision...'
            }),
        }
        labels = {
            'status': 'Decision',
            'review_notes': 'Review Notes',
        }


class UsernameChangeForm(forms.ModelForm):
    """Form for changing username."""
    class Meta:
        model = User
        fields = ['username']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-pulse-blue/30 rounded-pulse focus:ring-2 focus:ring-pulse-blue focus:border-pulse-blue transition-all bg-pulse-navyLighter text-white placeholder:text-text-muted',
                'placeholder': 'Enter new username'
            }),
        }
        labels = {
            'username': 'Username',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['username'].initial = self.user.username

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username and self.user:
            # Check if username is already taken by another user
            if User.objects.filter(username=username).exclude(pk=self.user.pk).exists():
                raise ValidationError('This username is already taken. Please choose another one.')
        return username


class ProfileAvatarForm(forms.ModelForm):
    """Form for changing profile avatar."""
    class Meta:
        model = UserProfile
        fields = ['avatar']
        widgets = {
            'avatar': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-pulse-blue/30 rounded-pulse focus:ring-2 focus:ring-pulse-blue focus:border-pulse-blue transition-all bg-pulse-navyLighter text-white file:mr-4 file:py-2 file:px-4 file:rounded-pulse file:border-0 file:text-sm file:font-semibold file:bg-pulse-blue/20 file:text-pulse-blue hover:file:bg-pulse-blue/30 cursor-pointer',
                'accept': 'image/*'
            }),
        }
        labels = {
            'avatar': 'Profile Picture',
        }

