# API Module

This folder contains the Django app for the backend API of the project management and test automation platform.

## Features

- **Custom User Model**: Email-based authentication with roles (Admin, Owner, Manager, Developer, Tester).
- **Project Management**: Projects, members, epics, sprints, tickets, tasks, tags.
- **Test Case Management**: Manual and AI-generated test cases, automation scripts, attachments, comments.
- **Subscription & Billing**: Subscription plans, subscriptions, invoices.
- **OAuth & JWT Authentication**: Google OAuth2, JWT tokens, social login endpoints.
- **Permissions**: Custom permissions for owner/admin access.
- **Audit Fields**: Tracks creation/update times and IP addresses.

## Main Files

- [`models.py`](models.py): All database models.
- [`serializers.py`](serializers.py): DRF serializers for API endpoints.
- [`views.py`](views.py): ViewSets and API logic.
- [`urls.py`](urls.py): API routing, including nested routers.
- [`permissions.py`](permissions.py): Custom permission classes.
- [`utils.py`](utils.py): Utility functions (e.g., get client IP).
- [`apps.py`](apps.py): Django app config.
- [`admin.py`](admin.py): Admin registration (customize as needed).
- [`tests.py`](tests.py): Unit tests (add your tests here).
- [`migrations/`](migrations): Database migrations.

## Endpoints

- `/api/users/` - User CRUD
- `/api/admin/users/` - Admin user CRUD
- `/api/projects/` - Project CRUD
- `/api/projects/{project_pk}/testcases/` - Nested test cases per project
- `/api/testcases/` - Test case CRUD
- `/api/subscription-plans/` - Subscription plan CRUD
- `/api/subscriptions/` - Subscription CRUD
- `/api/invoices/` - Invoice CRUD
- `/api/members/` - Project member CRUD
- `/api/epics/` - Epic CRUD
- `/api/sprints/` - Sprint CRUD
- `/api/tickets/` - Ticket CRUD
- `/api/token/` - JWT token obtain
- `/api/token/refresh/` - JWT token refresh
- `/api/auth/google/` - Google OAuth2 login

## Usage

1. **Install dependencies**:  
   `pip install -r requirements.txt`

2. **Apply migrations**:  
   `python manage.py migrate`

3. **Run server**:  
   `python manage.py runserver`

4. **Access API**:  
   Use the endpoints above with JWT authentication.

# Requirements for Django API Backend (MySQL)

This project uses **Django REST Framework** with MySQL as the database.  
Below is the list of dependencies required to run the backend.

---

## Core Dependencies

- `Django>=4.2,<5.0` – Web framework  
- `djangorestframework>=3.14` – REST API toolkit  
- `djangorestframework-simplejwt>=5.2` – JWT authentication support  
- `django-oauth-toolkit>=2.3` – OAuth2 authentication  
- `django-cors-headers>=4.0` – Cross-origin resource sharing (CORS) support  
- `mysqlclient>=2.2` – MySQL database driver  
- `requests>=2.31` – HTTP requests library  
- `google-auth>=2.28` – Google authentication client  
- `google-auth-oauthlib>=1.2` – Google OAuth2 client  
- `PyJWT>=2.8` – JSON Web Token utilities  
- `drf-nested-routers>=0.93` – Nested routing for DRF  
- `Pillow>=10.0` – Image processing support  

---

## Optional Dependencies

### For Testing
- `pytest>=7.4` – Testing framework  
- `pytest-django>=4.5` – Django plugin for pytest  

### For Environment Variables
- `python-dotenv>=1.0` – Load environment variables from `.env` file  

---

## Notes
- The app uses a **custom user model** (`api.User`).  
- Supports **JWT** and **Google OAuth2** authentication.  
- Add any other dependencies your code might require in the future.  


---

For more details, see the main project [`README.md`](../README.md)." 
