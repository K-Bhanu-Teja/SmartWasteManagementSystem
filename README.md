# Smart Waste Management System

A role-aware Django application for municipal waste services. It uses PostgreSQL in normal operation and provides citizen services, worker approval and operations, fleet management, GPS workflows, and Google Maps-based location views.

## Contents

- [Applications and architecture](#applications-and-architecture)
- [User and data model](#user-and-data-model)
- [Workflows](#workflows)
- [URL reference](#url-reference)
- [Maps and location behavior](#maps-and-location-behavior)
- [Configuration](#configuration)
- [Setup](#setup)
- [Migrations and data preservation](#migrations-and-data-preservation)
- [Tests and checks](#tests-and-checks)
- [Project layout](#project-layout)

## Applications and architecture

The project is split into three Django apps:

- `accounts` owns the custom authentication user, email authentication, registration profiles, approval state, password reset codes, and session timeout.
- `citizen_services` owns public waste locations, the service boundary, citizen complaints and pickups, saved locations, and vehicle proximity alerts.
- `workforce` owns vehicles and driver assignments, crews, attendance, approval operations, complaint status administration, GPS updates, and administrator/worker pages.
- `config` contains project settings, root URL routing, context processors, and WSGI/ASGI entry points.

Templates are under `templates/`; browser styles and scripts are under `static/`. Uploaded files use `MEDIA_ROOT`.

## User and data model

Authentication uses one custom `accounts.User` model extending Django's `AbstractUser`. Users sign in with email and password through the same login page. Passwords use Django's password hashing and configured password validators. Email uniqueness is enforced case-insensitively.

Current roles are `visitor`, `citizen`, `driver`, `cleaner`, `crew_leader`, and `administrator`. Public registration provides Citizen, Driver, and Worker choices. The public Worker choice maps to the existing `cleaner` role. Crew leaders and administrators are provisioned through existing admin/operations processes rather than the public registration choices.

Role-specific data is stored separately:

- `CitizenProfile`: house number, street/locality, ward, and village.
- `DriverProfile`: date of birth, optional gender, residential address, unique driving licence number, expiry date, experience, and licence document. Vehicle details are not part of driver registration.
- `WorkerProfile`: date of birth, optional gender, residential address, village, ward, optional experience, and optional identification document.
- `Vehicle`: fleet identifier, registration number, optional type, GPS position, and availability.
- `DriverVehicleAssignment`: driver/vehicle relationship with assignment history and active/released state. Database constraints allow at most one active vehicle per driver and one active driver per vehicle.
- `Crew`: a retained temporary operating group. Its roster and vehicles are recorded in `CrewMember` and `CrewVehicle`; a driver, vehicles, and workers are optional/flexible, with one designated leader.
- `CrewAssignment`: links one crew to a complaint or a pickup with an active-task constraint and retained assignment history.
- `WorkerLocation`: latest GPS position, signed-in state, and Available/Assigned/Off Duty/Unavailable availability.
- `TaskStatusHistory`, `CitizenConfirmation`, and `Notification`: immutable progress events, two-sided completion confirmation, and in-app notices.
- `Attendance`: one GPS-verified check-in per worker per local date.
- `Dustbin`: an active public dustbin with coordinates and an automatically assigned `DBno…` identifier.
- `ServiceBoundary`: the single four-point service polygon stored for the municipality.
- `Complaint`: citizen-submitted report, category, description, photo, coordinates, status, and optional assigned crew.
- `PickupRequest`: a scheduled citizen pickup, category, address, quantity, coordinates, and status.
- `SavedLocation`: a citizen-saved label and coordinates used for vehicle alerts.
- `PasswordResetOTP`: hashed, expiring, single-use password recovery codes with attempt tracking.

## Workflows

### Registration and access

`/register/` is one progressive registration page. It collects shared identity and login details, then displays the selected role's additional fields. `/register/citizen/`, `/register/driver/`, and `/register/worker/` remain compatible aliases to that same page.

Citizen accounts are activated on successful registration. Driver and Worker accounts start inactive and pending administrator review. Administrators can inspect submitted profile details and documents, then approve or reject an application. Rejected and pending accounts cannot log in; login reports the appropriate status when the password is correct.

The admin document endpoint is protected by administrator authorization. PDF/JPEG/PNG uploads are limited to 5 MB and validated by file extension and file signature.

Operations pages such as `/operations/admin/` require an authenticated administrator account. A browser with an existing valid session can open these pages directly; use Sign out or a private window to verify unauthenticated behavior.

When `DJANGO_DEBUG=True`, each development server process uses a distinct session marker and signs out existing sessions after a server restart. This reset is disabled when debug mode is off and in the isolated test settings.

### Vehicle assignment and crews

Administrators add fleet vehicles and assign them to approved, active drivers from Worker operations. They can change or remove an assignment. The assignment history remains in the database; a released vehicle becomes available again unless a crew still uses it. Pending, rejected, inactive, or non-driver accounts cannot receive an assignment.

Crews support one or more active workers and drivers, zero or more vehicles, and one leader selected from the chosen members. Worker operations uses independent checkboxes for selecting any available drivers, workers, and vehicles, followed by a crew-leader dropdown limited to the selected people. Legacy driver, cleaner, and primary-vehicle fields remain available for existing records. Roster and vehicle rows are retained after release; resources can be reused after their crew ends.

Administrators can create an unassigned crew in Worker operations or use the task assignment form on the home-pickup page. In Complaint management, administrators can assign an eligible existing crew or open Worker operations to create one; after creation, the complaint page offers an explicit next-step button to assign that crew. Existing active crews can be assigned without current GPS fixes; when available, the crew leader's location is shown for distance. New task crews created directly from a home-pickup form use signed-in workers/drivers with fresh GPS positions, sorted by straight-line distance to the task. Backend transactions recheck resource eligibility and active task/member constraints.

### Complaints and pickups

Citizens submit complaints with a category, description, photo, and location, then track the status timeline. Administrators manage complaints and pickups from separate pages but use the same assignment service. The new operational lifecycle is `pending`, `assigned`, `crew_on_the_way`, `arrived`, `in_progress`, `completed_awaiting_confirmation`, `confirmed`, and `closed`, with `admin_review`, `rejected_disputed`, and `cancelled` states available. Legacy status values remain readable.

Only the designated crew leader can update operational progress. Completion starts a configurable citizen confirmation window (default 24 hours). Citizens can confirm and close the task, or dispute it for administrator review; resources remain reserved until confirmation or admin resolution. Run `python manage.py process_task_confirmations` periodically (for example, every 10 minutes) to send reminders and move expired confirmations to admin review. Expired tasks are never auto-confirmed.

Citizens can schedule and review home pickups. Supported categories are household, recyclable, garden, and bulky waste. Citizens can also save map locations and use current or saved coordinates for nearby vehicle alerts.

### Worker operations

Approved workers can view their active crew and task, navigate to the destination with Google Maps, check in once per local day, and manage availability. Device GPS is requested on the worker dashboard; live coordinates are sent over authenticated HTTP while the assignment page is open. Crew leaders see only their own crew's members; administrators see active crew leader locations, and citizens see no member locations. Stale coordinates are not rendered as live.

An approved driver can share an active crew vehicle's location. Drivers without an active crew cannot update a vehicle position. Citizens can request proximity alerts for their current or saved locations using `VEHICLE_ALERT_RADIUS_METERS`.

## URL reference

| Area | URL | Purpose |
| --- | --- | --- |
| Home | `/` | Public home page and map |
| Login | `/login/` | Shared email/password login |
| Registration | `/register/` | Unified role-selecting registration |
| Registration aliases | `/register/citizen/`, `/register/driver/`, `/register/worker/` | Same unified registration page |
| Password recovery | `/forgot-password/` | Request OTP; verification at `/forgot-password/verify/` |
| Account dashboard | `/dashboard/` | Redirect to the signed-in user's workspace |
| Django admin | `/django-admin/` | Django administration |
| Citizen dashboard | `/citizen/dashboard/` | Citizen map and services |
| Citizen complaints | `/citizen/complaints/` | Submit and track complaints |
| Citizen pickups | `/citizen/pickups/` | Schedule and review pickups |
| Worker operations | `/operations/admin/workers/` | Approvals, vehicle assignments, crews, recommendations, and fleet |
| Complaint management | `/operations/admin/complaints/` | Admin complaint review and status changes |
| Pickup management | `/operations/admin/pickups/` | Admin home-pickup review and shared crew assignment |
| Admin map | `/operations/admin/` | Location management and complaint map |
| Worker dashboard | `/operations/worker/` | Approved worker's active crew and GPS attendance |

The `/accounts/...` login, registration, logout, dashboard, and password-reset paths remain as compatibility aliases. Important APIs include `/citizen/api/dustbins/`, `/citizen/api/vehicle-alerts/`, `/operations/api/boundary/`, `/operations/api/complaints-map/`, `/operations/api/active-crews-map/`, and the worker-only crew member location endpoint. Admin task assignment, crew progress, citizen completion responses, and dispute resolution are authenticated POST routes. The complaint and crew map APIs are administrator-only.

## Maps and location behavior

The shared citizen/home map requests only the public dustbin API; it does not receive complaint, pickup, or worker location data. Administrators can add permanent public dustbin markers inside the saved service boundary; each marker receives an automatic `DBno…` identifier. The admin map additionally loads complaint and pickup coordinates, status, and active crew leader locations. Crew markers refresh periodically and never expose individual member coordinates. Complaint and pickup status filters and crew task/availability filters are administrator-only.

The service boundary remains stored and functional even though its polygon is visually hidden. Its coordinates still center the map and validate whether administrators can add public locations. The public dustbin API returns only active locations and, when a boundary exists, only those inside it. The boundary geometry API remains separate from the public waste-location API.

Google Maps requires `GOOGLE_MAPS_API_KEY`. Without it, pages still render and show a setup message. If the key is rejected or the Maps JavaScript API fails to load, the map displays a diagnostic message; check that Maps JavaScript API and billing are enabled and that the current host is allowed by the key's HTTP referrer restrictions. Maps use the Maps JavaScript API Routes library (`Route.computeRoutes`) for driving directions to dustbins and crew tasks; enable both Maps JavaScript API and Routes API for the key.

## Configuration

Settings load key/value pairs from a root `.env` file when present, then allow real process environment variables to take precedence. `.env` is ignored by Git; this repository does not currently include an `.env.example`. The supported keys are:

| Variable | Purpose | Default/behavior |
| --- | --- | --- |
| `DJANGO_DEBUG` | Django debug mode | `False` |
| `DEVELOPMENT_SERVER_SESSION_RESET` | Sign out sessions after a development server restart | Enabled when debug is true; disabled when debug is false |
| `DJANGO_SECRET_KEY` | Django signing secret | Required when debug is false |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,127.0.0.1` |
| `DATABASE_NAME` | PostgreSQL database name | `smart_waste` |
| `DATABASE_USER` | PostgreSQL user | `postgres` |
| `DATABASE_PASSWORD` | PostgreSQL password | `postgres` |
| `DATABASE_HOST` | PostgreSQL host | `127.0.0.1` |
| `DATABASE_PORT` | PostgreSQL port | `5432` |
| `GOOGLE_MAPS_API_KEY` | Google Maps JavaScript API key (enable Maps JavaScript API and Routes API) | Empty; map fallback is shown |
| `MUNICIPAL_OFFICE_LAT`, `MUNICIPAL_OFFICE_LNG` | Attendance center coordinates | `16.833944`, `81.531444` |
| `ATTENDANCE_RADIUS_METERS` | Maximum check-in distance | `150` |
| `VEHICLE_ALERT_RADIUS_METERS` | Proximity alert radius | `1000` |
| `TASK_CONFIRMATION_TIMEOUT_HOURS` | Citizen completion response deadline | `24` |
| `TASK_CONFIRMATION_REMINDER_HOURS` | Reminder window before the deadline | `2` |
| `RESOURCE_LOCATION_MAX_AGE_SECONDS` | Maximum age for a location to count as fresh | `300` |
| `WORKER_LOCATION_UPDATE_INTERVAL_SECONDS` | GPS update interval while assigned | `15` |
| `CREW_LOCATION_POLL_INTERVAL_SECONDS` | Admin/leader map refresh interval | `15` |
| `DJANGO_EMAIL_BACKEND` | Email backend dotted path | Console backend in debug; SMTP backend otherwise |
| `DEFAULT_FROM_EMAIL` | Default sender address | `noreply@smartwaste.local` |

Example local `.env` values (replace credentials and secret locally):

```dotenv
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_NAME=smart_waste
DATABASE_USER=postgres
DATABASE_PASSWORD=replace-me
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
GOOGLE_MAPS_API_KEY=
MUNICIPAL_OFFICE_LAT=16.833944
MUNICIPAL_OFFICE_LNG=81.531444
ATTENDANCE_RADIUS_METERS=150
VEHICLE_ALERT_RADIUS_METERS=1000
TASK_CONFIRMATION_TIMEOUT_HOURS=24
TASK_CONFIRMATION_REMINDER_HOURS=2
RESOURCE_LOCATION_MAX_AGE_SECONDS=300
WORKER_LOCATION_UPDATE_INTERVAL_SECONDS=15
CREW_LOCATION_POLL_INTERVAL_SECONDS=15
```

In debug mode, password reset email is written to the console. For production email delivery, configure Django's SMTP host/port/credentials in the deployment settings; this project currently reads the email backend and sender address from environment variables, not the SMTP connection fields. Production must use HTTPS, `DJANGO_DEBUG=False`, a unique secret, restricted allowed hosts, and appropriately restricted media storage.

## Setup

Prerequisites: Python supported by the Django version installed from `requirements.txt`, PostgreSQL, and an optional Google Maps API key. `requirements.txt` currently specifies Django `>=5.0,<6.0`; the local environment used during recent development reported Django 6.0.2, so use a dependency environment that matches the declared range when reproducing installs and tests.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Before running migrations, configure PostgreSQL and set the variables above. On first setup, use Django Admin at `/django-admin/` to set the administrator role if needed, define the four-point service boundary, and add vehicles. Then use Worker operations to approve applicants, manage driver assignments and crews, and add public map locations inside the service boundary. Schedule `process_task_confirmations` so reminders and timeout-to-review transitions run automatically.

## Migrations and data preservation

Migrations are committed per app under each app's `migrations/` directory. Apply them with `python manage.py migrate`; do not delete migration files, reset migrations, or drop existing tables. The driver-vehicle migration copies legacy driver vehicle data into fleet inventory before removing the old profile columns. Pending/unapproved legacy drivers' vehicles are preserved as available fleet records but are not actively assigned.

Before applying production schema changes, take a PostgreSQL backup (for example, with `pg_dump`) and verify the configured database. Django fixture exports can preserve model rows but do not include uploaded file contents, PostgreSQL roles, or full database schema metadata.

## Tests and checks

The isolated test settings use in-memory SQLite and a locmem email backend; tests do not alter the configured PostgreSQL database:

```powershell
python manage.py test --settings=config.test_settings
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
```

## Project layout

```text
accounts/          Custom user, profiles, email authentication, registration, OTP reset
citizen_services/ Waste locations, boundaries, complaints, pickups, saved locations, APIs
workforce/         Vehicles, driver assignments, crews, attendance, admin/worker workflows
config/            Settings, root URLs, WSGI/ASGI, context processors, test settings
templates/         Shared layout and citizen, operations, and auth pages
static/css/        Shared site styles
static/js/         Map, citizen dashboard, and worker GPS interactions
media/             User uploads (ignored by Git)
manage.py          Django command-line entry point
requirements.txt   Python dependencies
```
