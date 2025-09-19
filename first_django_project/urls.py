from django.contrib import admin
from django.urls import path, include
from api.views import index

urlpatterns = [
    path('admin/', admin.site.urls),

    # API endpoints
    path('api/', include('api.urls')),

    # Allauth for Google OAuth + other social logins
    path('accounts/', include('allauth.urls')),

    # Homepage
    path('', index, name='index'),
]
