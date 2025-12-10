from django.contrib import admin
from django.urls import path, include
from accounting import views as accounting_views

urlpatterns = [
    # Admin Site
    path('admin/', admin.site.urls),
    
    # Built-in Authentication (Login, Logout, Password Reset)
    path('accounts/', include('django.contrib.auth.urls')),
    
    # Custom Registration View
    path('accounts/register/', accounting_views.register, name='register'),
    
    # Include ALL the app URLs we just fixed
    path('', include('accounting.urls')),
]