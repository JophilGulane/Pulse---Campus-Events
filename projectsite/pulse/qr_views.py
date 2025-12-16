"""
Views for QR Code Attendance System.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import View, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db import transaction, models
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from io import BytesIO
import base64

from PIL import Image, ImageDraw, ImageFont

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

from .models import (
    QRCode, AttendanceRecord, Event, Organization, OrganizationMembership, 
    UserProfile, Registration
)
from .mixins import user_has_organizer_membership


class QRCodeView(LoginRequiredMixin, TemplateView):
    """View for users to see and download their QR code."""
    template_name = 'pulse/qr_code/my_qr_code.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        if not QRCODE_AVAILABLE:
            messages.warning(self.request, 'QR code generation requires the qrcode library. Please install it: pip install qrcode[pil]')
            context['qr_codes'] = []
            context['qr_code_available'] = False
            return context
        
        # Always use a single global QR code per user
        qr_code = self._get_or_create_global_qr_code(user)
        
        if not qr_code:
            context['qr_code_available'] = False
            return context
        
        # Ensure token exists
        if not qr_code.token:
            qr_code.save()
        
        user_display_name = user.get_full_name() or user.username
        image_base64 = self._generate_qr_image_with_label(qr_code, user_display_name, user)
        
        context['qr_code_card'] = {
            'qr_code': qr_code,
            'image_data': image_base64,
            'user_name': user_display_name,
        }
        context['qr_code_available'] = True
        return context
    
    def _get_or_create_global_qr_code(self, user):
        """
        Ensure there is a single QR code per user that works for every organization.
        If legacy organization-specific QR codes exist, reuse the latest one and
        convert it to a global code.
        """
        # Prefer an existing global QR code
        qr_code = QRCode.objects.filter(user=user, organization__isnull=True).first()
        if qr_code:
            # Deactivate any other legacy codes for safety
            QRCode.objects.filter(user=user).exclude(pk=qr_code.pk).update(is_active=False)
            return qr_code
        
        # Fall back to any existing QR code and convert it to global
        legacy_qr = QRCode.objects.filter(user=user).order_by('-created_at').first()
        if legacy_qr:
            legacy_qr.organization = None
            legacy_qr.save(update_fields=['organization'])
            QRCode.objects.filter(user=user).exclude(pk=legacy_qr.pk).update(is_active=False)
            return legacy_qr
        
        # Create a brand new QR code
        return QRCode.objects.create(user=user, organization=None, is_active=True)
    
    def _generate_qr_image_with_label(self, qr_code, user_display_name, user):
        """Generate a QR code PNG with logo in center, profile picture above, and name below."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Higher error correction for logo in center
            box_size=8,  # 30% bigger QR code (15 * 1.3 = 19.5, rounded to 20)
            border=0,
        )
        qr.add_data(qr_code.get_qr_data())
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        
        # Add logo to center of QR code
        qr_img_with_logo = self._add_logo_to_qr_center(qr_img)
        
        # Add profile picture and name
        labeled_img = self._add_profile_and_name_to_qr(qr_img_with_logo, user_display_name, user)
        
        buffer = BytesIO()
        labeled_img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode()
    
    def _add_logo_to_qr_center(self, qr_img):
        """Add Pulse logo to the center of the QR code."""
        try:
            from django.conf import settings
            from django.contrib.staticfiles import finders
            import os
            
            # Try to find logo using staticfiles finder
            logo_path = finders.find('image/pulse-logo.png')
            
            # Fallback to direct path if finder doesn't work
            if not logo_path:
                base_dir = getattr(settings, 'BASE_DIR', None)
                if base_dir:
                    potential_paths = [
                        os.path.join(base_dir, 'static', 'image', 'pulse-logo.png'),
                        os.path.join(base_dir, 'projectsite', 'static', 'image', 'pulse-logo.png'),
                    ]
                    if hasattr(settings, 'STATICFILES_DIRS') and settings.STATICFILES_DIRS:
                        for static_dir in settings.STATICFILES_DIRS:
                            potential_paths.append(os.path.join(static_dir, 'image', 'pulse-logo.png'))
                    
                    for path in potential_paths:
                        if os.path.exists(path):
                            logo_path = path
                            break
            
            if logo_path and os.path.exists(logo_path):
                logo = Image.open(logo_path)
                # Convert to RGBA if needed
                if logo.mode != 'RGBA':
                    logo = logo.convert('RGBA')
                
                # Calculate size for logo (about 20% of QR code size)
                logo_size = int(qr_img.width * 0.2)
                logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                
                # Create white background circle for logo (like Telegram)
                circle_size = int(logo_size * 1.3)
                circle_img = Image.new('RGBA', (circle_size, circle_size), (255, 255, 255, 0))
                circle_draw = ImageDraw.Draw(circle_img)
                circle_draw.ellipse([(0, 0), (circle_size - 1, circle_size - 1)], fill=(255, 255, 255, 255))
                
                # Center logo on white circle
                logo_x = (circle_size - logo_size) // 2
                logo_y = (circle_size - logo_size) // 2
                circle_img.paste(logo, (logo_x, logo_y), logo)
                
                # Paste logo in center of QR code
                qr_center_x = (qr_img.width - circle_size) // 2
                qr_center_y = (qr_img.height - circle_size) // 2
                qr_img.paste(circle_img, (qr_center_x, qr_center_y), circle_img)
        except Exception as e:
            # If logo can't be loaded, continue without it
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not load logo for QR code: {str(e)}")
        
        return qr_img
    
    def _add_profile_and_name_to_qr(self, qr_img, user_display_name, user):
        """Combine the QR image with name below (QR code takes 80% of white box, name is big)."""
        padding = 20
        label_height = 80  # Bigger space for name
        
        # White box dimensions - QR code should be 80% of the box height
        # Calculate box height so QR code is 80% of it
        qr_box_height = int(qr_img.height / 0.8)  # QR is 80%, so total box = QR / 0.8
        qr_box_width = qr_img.width + (padding * 2)
        
        # Total canvas dimensions (white box)
        width = qr_box_width
        height = qr_box_height
        
        # Create white box
        combined = Image.new('RGB', (width, height), color='white')
        
        # Calculate QR code position to take 80% of box height
        qr_available_height = int(qr_box_height * 0.8)
        qr_scale = min(1.0, qr_available_height / qr_img.height)  # Scale if needed
        
        if qr_scale < 1.0:
            # Resize QR code to fit 80% of box
            new_qr_width = int(qr_img.width * qr_scale)
            new_qr_height = int(qr_img.height * qr_scale)
            qr_img = qr_img.resize((new_qr_width, new_qr_height), Image.Resampling.LANCZOS)
        
        # Center QR code horizontally, position at top 80% of box
        qr_x = (width - qr_img.width) // 2
        qr_y = padding
        combined.paste(qr_img, (qr_x, qr_y))
        
        # Draw user name below QR code (big font, in remaining 20% space)
        draw = ImageDraw.Draw(combined)
        font = self._get_label_font(size=36)  # Much bigger font
        text = user_display_name
        
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Position name in the bottom 20% area
        name_area_start = int(qr_box_height * 0.8)
        text_x = (width - text_width) // 2
        text_y = name_area_start + (label_height - text_height) // 2
        
        draw.text((text_x, text_y), text, fill=(31, 41, 55), font=font)
        
        return combined
    
    def _get_label_font(self, size=28):
        """Return a readable font for the QR code label with safe fallbacks."""
        try:
            return ImageFont.truetype("arial.ttf", size)
        except Exception:
            try:
                return ImageFont.truetype("DejaVuSans.ttf", size)
            except Exception:
                return ImageFont.load_default()


class QRCodeScannerView(LoginRequiredMixin, TemplateView):
    """View for organizers to scan QR codes for attendance."""
    template_name = 'pulse/qr_code/scanner.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        is_admin_user = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin())
        is_organizer_user = (
            (hasattr(user, 'profile') and user.profile.is_organizer()) or
            user_has_organizer_membership(user)
        )
        
        # Check if user is organizer or admin
        if not (is_admin_user or is_organizer_user):
            messages.error(self.request, 'Only organizers and admins can scan QR codes.')
            return context
        
        # Get events the organizer can manage (events with any attendance enabled)
        if is_admin_user:
            events = Event.objects.filter(
                models.Q(enable_morning_in=True) |
                models.Q(enable_morning_out=True) |
                models.Q(enable_afternoon_in=True) |
                models.Q(enable_afternoon_out=True)
            ).order_by('-start_datetime')
        else:
            # Get organizer organizations
            organizer_orgs = Organization.objects.filter(
                memberships__user=user,
                memberships__role=OrganizationMembership.Role.ORGANIZER,
                is_active=True
            ).distinct()
            events = Event.objects.filter(
                models.Q(enable_morning_in=True) |
                models.Q(enable_morning_out=True) |
                models.Q(enable_afternoon_in=True) |
                models.Q(enable_afternoon_out=True),
                organization__in=organizer_orgs
            ).order_by('-start_datetime')
        
        # Filter to show only active/live events (currently ongoing)
        # Only show events that are currently happening (between start_datetime and end_datetime)
        now = timezone.now()
        active_events = [e for e in events if e.is_ongoing]
        
        # For each event, get available attendance types
        from .models import AttendanceRecord
        import json
        events_with_types = []
        events_data = {}
        
        for event in active_events:
            available_types = []
            
            # Check each attendance type if it's enabled and currently available
            # Only show attendance types that are currently available (within their time window)
            # Use hardcoded string values to avoid issues with Django TextChoices
            ATTENDANCE_TYPE_LABELS = {
                "MORNING_IN": "Morning Time In",
                "MORNING_OUT": "Morning Time Out",
                "AFTERNOON_IN": "Afternoon Time In",
                "AFTERNOON_OUT": "Afternoon Time Out",
            }
            
            # Helper function to get end datetime for an attendance type
            def get_end_datetime_for_type(event, attendance_type):
                """Get the end datetime for an attendance type scanning window."""
                from datetime import datetime
                event_date = event.event_date if event.event_date else (event.start_datetime.date() if event.start_datetime else timezone.now().date())
                
                # Try to get end time from model field first (most reliable)
                end_time_field = None
                if attendance_type == "MORNING_IN" and event.morning_in_end:
                    end_time_field = event.morning_in_end
                elif attendance_type == "MORNING_OUT" and event.morning_out_end:
                    end_time_field = event.morning_out_end
                elif attendance_type == "AFTERNOON_IN" and event.afternoon_in_end:
                    end_time_field = event.afternoon_in_end
                elif attendance_type == "AFTERNOON_OUT" and event.afternoon_out_end:
                    end_time_field = event.afternoon_out_end
                
                if end_time_field:
                    end_datetime = timezone.make_aware(datetime.combine(event_date, end_time_field))
                    return end_datetime.isoformat()
                
                # Fallback: try to parse from time_window string
                return None
            
            # Helper function to get end time from time window string (fallback)
            def get_end_time_from_window(time_window_str, event_date):
                """Extract end time from time window string like '07:24 AM - 08:24 AM'"""
                if not time_window_str:
                    return None
                try:
                    # Parse "07:24 AM - 08:24 AM" format
                    parts = time_window_str.split(' - ')
                    if len(parts) == 2:
                        end_time_str = parts[1].strip()
                        # Parse time string like "08:24 AM"
                        from datetime import datetime
                        end_time = datetime.strptime(end_time_str, '%I:%M %p').time()
                        # Combine with event date
                        if event_date:
                            from datetime import datetime as dt
                            end_datetime = dt.combine(event_date, end_time)
                            # Make timezone-aware
                            end_datetime_aware = timezone.make_aware(end_datetime)
                            return end_datetime_aware.isoformat()
                except Exception:
                    pass
                return None
            
            # Only add attendance types that are currently available (enabled and within time window)
            if event.enable_morning_in and event.can_scan_morning_in():
                time_window = event.get_morning_in_time_window()
                end_time = get_end_datetime_for_type(event, "MORNING_IN")
                # Fallback to parsing from time_window if model field not set
                if not end_time:
                    end_time = get_end_time_from_window(time_window, event.event_date)
                available_types.append({
                    'value': "MORNING_IN",
                    'label': ATTENDANCE_TYPE_LABELS["MORNING_IN"],
                    'enabled': True,  # Already filtered by can_scan_morning_in()
                    'time_window': time_window,
                    'end_time': end_time
                })
            
            if event.enable_morning_out and event.can_scan_morning_out():
                time_window = event.get_morning_out_time_window()
                end_time = get_end_datetime_for_type(event, "MORNING_OUT")
                if not end_time:
                    end_time = get_end_time_from_window(time_window, event.event_date)
                available_types.append({
                    'value': "MORNING_OUT",
                    'label': ATTENDANCE_TYPE_LABELS["MORNING_OUT"],
                    'enabled': True,  # Already filtered by can_scan_morning_out()
                    'time_window': time_window,
                    'end_time': end_time
                })
            
            if event.enable_afternoon_in and event.can_scan_afternoon_in():
                time_window = event.get_afternoon_in_time_window()
                end_time = get_end_datetime_for_type(event, "AFTERNOON_IN")
                if not end_time:
                    end_time = get_end_time_from_window(time_window, event.event_date)
                available_types.append({
                    'value': "AFTERNOON_IN",
                    'label': ATTENDANCE_TYPE_LABELS["AFTERNOON_IN"],
                    'enabled': True,  # Already filtered by can_scan_afternoon_in()
                    'time_window': time_window,
                    'end_time': end_time
                })
            
            if event.enable_afternoon_out and event.can_scan_afternoon_out():
                time_window = event.get_afternoon_out_time_window()
                end_time = get_end_datetime_for_type(event, "AFTERNOON_OUT")
                if not end_time:
                    end_time = get_end_time_from_window(time_window, event.event_date)
                available_types.append({
                    'value': "AFTERNOON_OUT",
                    'label': ATTENDANCE_TYPE_LABELS["AFTERNOON_OUT"],
                    'enabled': True,  # Already filtered by can_scan_afternoon_out()
                    'time_window': time_window,
                    'end_time': end_time
                })
            
            events_with_types.append({
                'event': event,
                'available_types': available_types
            })
            
            # Store as JSON for JavaScript
            events_data[str(event.id)] = available_types
        
        context['events_with_types'] = events_with_types
        context['events_data_json'] = json.dumps(events_data)
        context['events'] = active_events
        context['now'] = now  # Add 'now' for template comparisons (like event_list.html)
        
        # Add current time for debugging
        context['current_time'] = now
        context['current_date'] = now.date()  # UTC date
        # Also add timezone info
        from django.utils import timezone as tz_utils
        context['timezone_name'] = str(tz_utils.get_current_timezone()) if tz_utils.is_aware(now) else 'UTC'
        return context


@method_decorator(csrf_exempt, name='dispatch')
class ScanQRCodeView(LoginRequiredMixin, View):
    """API endpoint to process QR code scan and record attendance."""
    
    def post(self, request, event_id):
        """Process QR code scan for attendance."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"QR Scan request received - Event ID: {event_id}, User: {request.user.username}")
        
        try:
            event = get_object_or_404(Event, pk=event_id)
            organizer = request.user
            logger.info(f"Event found: {event.title}, Organizer: {organizer.username}")
            
            # Validate organizer permissions
            if not organizer.is_superuser:
                if not hasattr(organizer, 'profile') and not user_has_organizer_membership(organizer):
                    return JsonResponse({'success': False, 'error': 'Invalid user profile.'}, status=403)
                
                is_admin_user = hasattr(organizer, 'profile') and organizer.profile.is_admin()
                is_organizer_user = (
                    hasattr(organizer, 'profile') and organizer.profile.is_organizer()
                ) or user_has_organizer_membership(organizer)
                
                if not (is_admin_user or is_organizer_user):
                    return JsonResponse({'success': False, 'error': 'Only organizers can scan QR codes.'}, status=403)
                
                # Check if organizer can manage this event's organization
                if event.organization:
                    organizer_orgs = Organization.objects.filter(
                        memberships__user=organizer,
                        memberships__role=OrganizationMembership.Role.ORGANIZER,
                        is_active=True
                    ).distinct()
                    if event.organization not in organizer_orgs and not organizer.profile.is_admin():
                        return JsonResponse({'success': False, 'error': 'You can only scan QR codes for your organization events.'}, status=403)
            
            # Validate attendance window
            if not event.can_scan_attendance():
                window_start = event.get_attendance_window_start()
                window_end = event.get_attendance_window_end()
                return JsonResponse({
                    'success': False,
                    'error': f'Scanning is only allowed between {window_start.strftime("%Y-%m-%d %H:%M")} and {window_end.strftime("%Y-%m-%d %H:%M")}.'
                }, status=400)
            
            # Get QR code token from request
            token = request.POST.get('token')
            if not token and request.content_type == 'application/json':
                try:
                    data = json.loads(request.body)
                    token = data.get('token')
                except json.JSONDecodeError:
                    pass
            
            if not token:
                return JsonResponse({'success': False, 'error': 'QR code token is required.'}, status=400)
            
            # Clean token - remove whitespace and newlines
            token = token.strip()
            
            # Debug logging
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"QR Scan attempt - Token: {token[:10]}... (length: {len(token)}), Event: {event_id}, Organizer: {organizer.username}")
            
            # Find QR code - try exact match first
            qr_code = None
            try:
                qr_code = QRCode.objects.select_related('user', 'organization').get(token=token, is_active=True)
                logger.info(f"QR code found: User={qr_code.user.username}, Org={qr_code.organization.name if qr_code.organization else 'Global'}")
            except QRCode.DoesNotExist:
                logger.warning(f"QR code not found for token: {token[:20]}...")
                # Try to find by partial match (in case of encoding issues) - but limit to avoid performance issues
                matching_codes = QRCode.objects.filter(is_active=True).select_related('user')[:100]  # Limit to 100 for performance
                for code in matching_codes:
                    if code.token == token or code.token.strip() == token.strip():
                        qr_code = code
                        logger.info(f"Found QR code by exact match after strip: {code.token[:10]}...")
                        break
                
                if not qr_code:
                    # Log sample of active tokens for debugging
                    active_tokens = list(QRCode.objects.filter(is_active=True).values_list('token', flat=True)[:5])
                    logger.warning(f"QR code not found. Received token: {token[:20]}... (length: {len(token)})")
                    logger.warning(f"Sample active tokens: {[t[:10] + '...' for t in active_tokens]}")
                    return JsonResponse({
                        'success': False, 
                        'error': 'Invalid QR code. Please make sure you are scanning a valid Pulse QR code.'
                    }, status=404)
            
            # Convert any legacy organization-specific QR codes to global so they work everywhere
            if qr_code.organization is not None:
                qr_code.organization = None
                qr_code.save(update_fields=['organization'])
            
            user = qr_code.user
            
            # Check if user is registered for the event
            try:
                registration = Registration.objects.get(event=event, user=user)
                if registration.status == Registration.Status.CANCELLED:
                    return JsonResponse({
                        'success': False,
                        'error': 'User registration is cancelled.'
                    }, status=400)
            except Registration.DoesNotExist:
                # Allow scanning even if not registered (for mandatory events)
                if not event.is_mandatory():
                    return JsonResponse({
                        'success': False,
                        'error': 'User is not registered for this event.'
                    }, status=400)
            
            # Get attendance type from request (organizer selects it)
            attendance_type_str = request.POST.get('attendance_type')
            
            # Also check JSON body if POST didn't have it
            if not attendance_type_str and request.content_type == 'application/json':
                try:
                    data = json.loads(request.body)
                    attendance_type_str = data.get('attendance_type')
                except (json.JSONDecodeError, AttributeError):
                    pass
            
            logger.info(f"📥 Received attendance_type from request: '{attendance_type_str}'")
            
            if not attendance_type_str:
                return JsonResponse({
                    'success': False,
                    'error': 'Attendance type is required.'
                }, status=400)
            
            # Normalize the attendance type (trim whitespace, uppercase)
            attendance_type_str = attendance_type_str.strip().upper()
            
            # Validate attendance type
            # Use the actual string values directly (Django TextChoices stores them as tuples)
            # The tuple is (value, label), so we need the .value attribute or use the string directly
            valid_types = [
                "MORNING_IN",
                "MORNING_OUT", 
                "AFTERNOON_IN",
                "AFTERNOON_OUT",
            ]
            
            # Debug: Log what the TextChoices actually return
            logger.info(f"🔍 AttendanceRecord.AttendanceType.MORNING_IN = {AttendanceRecord.AttendanceType.MORNING_IN}")
            logger.info(f"🔍 AttendanceRecord.AttendanceType.MORNING_IN[0] = {AttendanceRecord.AttendanceType.MORNING_IN[0]}")
            logger.info(f"🔍 AttendanceRecord.AttendanceType.MORNING_IN.value = {getattr(AttendanceRecord.AttendanceType.MORNING_IN, 'value', 'N/A')}")
            logger.info(f"🔍 Using hardcoded valid_types: {valid_types}")
            
            # Log what we're comparing
            logger.info(f"🔍 Validating attendance type: '{attendance_type_str}'")
            logger.info(f"🔍 Valid types are: {valid_types}")
            logger.info(f"🔍 Type of valid_types: {type(valid_types)}")
            logger.info(f"🔍 Type of attendance_type_str: {type(attendance_type_str)}")
            logger.info(f"🔍 MORNING_IN[0] = '{AttendanceRecord.AttendanceType.MORNING_IN[0]}'")
            logger.info(f"🔍 Is in valid_types? {attendance_type_str in valid_types}")
            
            if attendance_type_str not in valid_types:
                logger.error(f"❌ Invalid attendance type received: '{attendance_type_str}'. Valid types: {valid_types}")
                logger.error(f"❌ Received type (repr): {repr(attendance_type_str)}")
                logger.error(f"❌ Valid types (repr): {[repr(v) for v in valid_types]}")
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid attendance type: {attendance_type_str}'
                }, status=400)
            
            attendance_type = attendance_type_str
            logger.info(f"✅ Using attendance_type: '{attendance_type}'")
            
            # Check if this attendance type is enabled for the event
            # Double-check by refreshing the event settings from database
            event.refresh_from_db(fields=['enable_morning_in', 'enable_morning_out', 'enable_afternoon_in', 'enable_afternoon_out'])
            
            # Check if this attendance type is enabled for the event (use string comparison)
            if attendance_type == "MORNING_IN":
                if not event.enable_morning_in:
                    return JsonResponse({
                        'success': False,
                        'error': 'Morning Time In is not enabled for this event. Please check the event settings.'
                    }, status=400)
            elif attendance_type == "MORNING_OUT":
                if not event.enable_morning_out:
                    return JsonResponse({
                        'success': False,
                        'error': 'Morning Time Out is not enabled for this event. Please check the event settings.'
                    }, status=400)
            elif attendance_type == "AFTERNOON_IN":
                if not event.enable_afternoon_in:
                    return JsonResponse({
                        'success': False,
                        'error': 'Afternoon Time In is not enabled for this event. Please check the event settings.'
                    }, status=400)
            elif attendance_type == "AFTERNOON_OUT":
                if not event.enable_afternoon_out:
                    return JsonResponse({
                        'success': False,
                        'error': 'Afternoon Time Out is not enabled for this event. Please check the event settings.'
                    }, status=400)
            
            # Check if within time window for this attendance type (use string comparison)
            if attendance_type == "MORNING_IN" and not event.can_scan_morning_in():
                return JsonResponse({
                    'success': False,
                    'error': 'Morning Time In window is not currently open.'
                }, status=400)
            if attendance_type == "MORNING_OUT" and not event.can_scan_morning_out():
                return JsonResponse({
                    'success': False,
                    'error': 'Morning Time Out window is not currently open.'
                }, status=400)
            if attendance_type == "AFTERNOON_IN" and not event.can_scan_afternoon_in():
                return JsonResponse({
                    'success': False,
                    'error': 'Afternoon Time In window is not currently open.'
                }, status=400)
            if attendance_type == "AFTERNOON_OUT" and not event.can_scan_afternoon_out():
                return JsonResponse({
                    'success': False,
                    'error': 'Afternoon Time Out window is not currently open.'
                }, status=400)
            
            # Check if user already has this attendance type recorded
            existing_record = AttendanceRecord.objects.filter(
                event=event,
                user=user,
                attendance_type=attendance_type
            ).first()
            
            if existing_record:
                # Get label for attendance type - use the model's method
                try:
                    type_label = existing_record.get_attendance_type_label()
                except AttributeError:
                    # Fallback to Django's built-in method
                    type_label = existing_record.get_attendance_type_display()
                return JsonResponse({
                    'success': False,
                    'error': f'User has already been scanned for {type_label}.'
                }, status=400)
            
            # Prerequisites removed - users can scan time out without time in
            
            # Create attendance record
            with transaction.atomic():
                attendance_record = AttendanceRecord.objects.create(
                    event=event,
                    user=user,
                    organizer=organizer,
                    attendance_type=attendance_type,
                    points_awarded=0,  # Will be calculated after
                )
                
                # Calculate and award points based on 4-scan system
                # Count how many attendance types are enabled
                enabled_count = sum([
                    event.enable_morning_in,
                    event.enable_morning_out,
                    event.enable_afternoon_in,
                    event.enable_afternoon_out
                ])
                
                if enabled_count == 0:
                    points_to_award = 0
                else:
                    # Each scan awards a proportional share of total points
                    # If all 4 are enabled, each scan is worth 25% (1/4)
                    # If 2 are enabled, each is worth 50% (1/2), etc.
                    points_per_scan = event.get_points() // enabled_count
                    points_to_award = points_per_scan
                
                # Update attendance record with points
                attendance_record.points_awarded = points_to_award
                attendance_record.save()
                
                # Award points to user
                if points_to_award > 0:
                    user_profile, created = UserProfile.objects.get_or_create(user=user)
                    # Use add_points method which handles balance_after and transaction creation correctly
                    user_profile.add_points(
                        amount=points_to_award,
                        reason=f"Attendance: {event.title} ({attendance_type})",
                        event=event
                    )
                
                # Update QR code last used
                qr_code.last_used_at = timezone.now()
                qr_code.save()
                
                # Update registration status if applicable
                # Mark as attended if this is the first scan (morning in or afternoon in)
                try:
                    registration = Registration.objects.get(event=event, user=user)
                    if (attendance_type == "MORNING_IN" or 
                        attendance_type == "AFTERNOON_IN"):
                        registration.status = Registration.Status.ATTENDED
                        registration.save()
                        logger.info(f"Updated registration status to ATTENDED for user {user.username}")
                except Registration.DoesNotExist:
                    logger.info(f"No registration found for user {user.username} at event {event.title} - this is OK for mandatory events")
                    pass
            
            # Get user's full name or username
            user_display_name = user.get_full_name() or user.username
            # Get user's email for additional identification
            user_email = getattr(user, 'email', '')
            
            # Get the human-readable label for the attendance type
            ATTENDANCE_TYPE_LABELS = {
                AttendanceRecord.AttendanceType.MORNING_IN[0]: "Morning Time In",
                AttendanceRecord.AttendanceType.MORNING_OUT[0]: "Morning Time Out",
                AttendanceRecord.AttendanceType.AFTERNOON_IN[0]: "Afternoon Time In",
                AttendanceRecord.AttendanceType.AFTERNOON_OUT[0]: "Afternoon Time Out",
            }
            attendance_type_label = ATTENDANCE_TYPE_LABELS.get(attendance_type, attendance_type)
            
            logger.info(f"✅ QR Scan successful - User: {user_display_name}, Type: {attendance_type} ({attendance_type_label}), Points: {points_to_award}")
            
            response_data = {
                'success': True,
                'message': f'Successfully recorded {attendance_type_label} for {user_display_name}.',
                'user_name': user_display_name,
                'user_email': user_email,
                'user_username': user.username,
                'attendance_type': attendance_type,  # Keep the value for frontend logic
                'attendance_type_label': attendance_type_label,  # Add the label for display
                'points_awarded': points_to_award,
            }
            
            logger.info(f"Returning success response")
            return JsonResponse(response_data)
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"QR Scan exception: {str(e)}")
            logger.error(f"Traceback: {error_trace}")
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            }, status=500)

