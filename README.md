# Pulse - Campus Events Platform

A modern Django-based platform for discovering, managing, and experiencing campus events. Connect. Engage. Thrive.

## Features

### 🎯 Core Functionality
- **Event Management**: Create, update, and manage campus events with detailed information
- **Event Registration**: Users can register for events with capacity management
- **QR Code Attendance**: 4-scan attendance system (Morning In/Out, Afternoon In/Out) with time windows
- **Points & Rewards**: Gamified system with points awarded for event attendance
- **Leaderboard**: Track and display top participants by points
- **Organizations**: Create and manage organizations with member management
- **Mandatory Events**: Auto-registration for organization members with excuse request system
- **Announcements**: Newsfeed-style announcements with image support

### 👥 User Roles
- **Admin**: Full system access, can manage users, events, organizations, and announcements
- **Organizer**: Can create events for their organizations and manage attendance
- **User**: Can register for events, view announcements, and track their points

### 🔐 Authentication
- Email/Username login
- Google OAuth integration via Django Allauth
- Email verification (optional)
- Password reset functionality

### 📱 QR Code System
- Unique QR codes per user per organization
- 4-scan attendance tracking:
  - Morning Time In
  - Morning Time Out
  - Afternoon Time In
  - Afternoon Time Out
- Time window validation for each scan type
- Real-time attendance tracking

## Technology Stack

- **Backend**: Django 5.2.7
- **Database**: SQLite (development), PostgreSQL (production-ready)
- **Authentication**: Django Allauth
- **Frontend**: Tailwind CSS (via CDN)
- **Image Processing**: Pillow
- **QR Code Generation**: qrcode
- **API**: Django REST Framework
- **Deployment**: Gunicorn + WhiteNoise

## Prerequisites

- Python 3.11+
- pip
- Virtual environment (recommended)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Pulse
   ```

2. **Create and activate a virtual environment**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   cd Pulse
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Create a `.env` file in the `projectsite` directory (or root) with the following variables:
   ```env
   DJANGO_SECRET_KEY=your-secret-key-here
   DJANGO_DEBUG=True
   
   # Google OAuth (optional)
   GOOGLE_OAUTH_CLIENT_ID=your-google-client-id
   GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret
   
   # Email Configuration (optional)
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-app-password
   DEFAULT_FROM_EMAIL=Pulse <noreply@pulse.com>
   ```

5. **Run migrations**
   ```bash
   cd projectsite
   python manage.py migrate
   ```

6. **Create a superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Collect static files** (for production)
   ```bash
   python manage.py collectstatic
   ```

8. **Run the development server**
   ```bash
   python manage.py runserver
   ```

9. **Access the application**
   - Main site: http://127.0.0.1:8000/
   - Admin panel: http://127.0.0.1:8000/admin/

## Configuration

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs:
   - `http://127.0.0.1:8000/accounts/google/login/callback/` (development)
   - Your production domain callback URL
6. Add credentials to `.env` file
7. In Django admin, go to **Social applications** and add:
   - Provider: Google
   - Client id: From `.env`
   - Secret key: From `.env`
   - Sites: Select your site

### Email Configuration

For Gmail:
1. Enable 2-factor authentication
2. Generate an App Password
3. Use the App Password in `EMAIL_HOST_PASSWORD`

## Project Structure

```
Pulse/
├── projectsite/          # Main Django project
│   ├── projectsite/      # Project settings
│   │   ├── settings.py   # Django settings
│   │   ├── urls.py       # URL configuration
│   │   └── wsgi.py       # WSGI configuration
│   ├── pulse/            # Main app
│   │   ├── models.py     # Database models
│   │   ├── views.py      # View functions
│   │   ├── admin_views.py # Admin views
│   │   ├── organization_views.py # Organization views
│   │   ├── qr_views.py   # QR code views
│   │   └── migrations/   # Database migrations
│   ├── templates/        # HTML templates
│   ├── static/           # Static files (CSS, images)
│   ├── media/            # User uploads (avatars, event images)
│   └── manage.py         # Django management script
├── venv/                 # Virtual environment (gitignored)
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## Key Models

- **UserProfile**: Extended user information with roles and points
- **Organization**: Campus organizations/clubs
- **Event**: Events with registration, attendance, and QR code support
- **Registration**: User event registrations
- **AttendanceRecord**: QR code-based attendance tracking
- **QRCode**: Unique QR codes for users
- **Announcement**: Newsfeed announcements
- **Excuse**: Excuse requests for mandatory events
- **PointsTransaction**: Points history tracking

## Usage

### For Administrators

1. **Manage Users**: `/admin/users/`
   - View all users
   - Update user roles
   - Manage permissions

2. **Manage Events**: `/events/add/`
   - Create events
   - Set capacity, points, and registration deadlines
   - Configure QR attendance settings

3. **Manage Organizations**: `/admin/organizations/`
   - Review organization requests
   - Approve/reject organizations
   - Assign organizers

4. **Manage Announcements**: `/admin/announcements/`
   - Create global or organization-specific announcements
   - Pin important announcements

5. **Review Excuses**: `/admin/excuses/`
   - Review excuse requests for mandatory events
   - Approve or reject with notes

### For Organizers

1. **Dashboard**: `/dashboard/`
   - View organization statistics
   - Manage events for your organization
   - Track attendance

2. **Create Events**: `/events/add/`
   - Create events for your organization
   - Configure mandatory/optional events
   - Set up QR attendance

3. **Scan QR Codes**: `/qr-code/scanner/`
   - Scan user QR codes for attendance
   - Track morning/afternoon in/out

### For Users

1. **Browse Events**: `/events/`
   - View all available events
   - Filter by organization
   - Register for events

2. **My QR Code**: `/qr-code/`
   - View your unique QR code
   - Download or display for scanning

3. **My Registrations**: `/my-registrations/`
   - View registered events
   - Track attendance status

4. **Profile**: `/profile/`
   - Update profile information
   - Change avatar, username, password
   - View points and transaction history

5. **Leaderboard**: `/leaderboard/`
   - View top participants by points

6. **Join Organizations**: `/organizations/join/`
   - Join using organization code or invite link

## Development

### Running Tests
```bash
python manage.py test
```

### Creating Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### Creating a New Superuser
```bash
python manage.py createsuperuser
```

### Accessing Django Admin
Navigate to `/admin/` and login with superuser credentials.

## Production Deployment

1. **Set `DEBUG=False`** in environment variables
2. **Use a production database** (PostgreSQL recommended)
3. **Configure `ALLOWED_HOSTS`** in settings
4. **Set up proper static file serving** (WhiteNoise is included)
5. **Use environment variables** for all secrets
6. **Set up SSL/HTTPS**
7. **Configure email backend** for production
8. **Use Gunicorn** for WSGI server:
   ```bash
   gunicorn projectsite.wsgi:application
   ```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is proprietary software. All rights reserved.

## Support

For issues, questions, or contributions, please contact the development team.

## Acknowledgments

- Built with Django
- UI powered by Tailwind CSS
- Authentication via Django Allauth
- QR Code generation with qrcode library

---

**Pulse** - Connecting campus communities through events. 🎓✨

