from django.urls import path
from . import views

app_name = 'user_activity'

urlpatterns = [
    # Dashboard and main views
    path('active-users/', views.active_users_view, name='active_users'),
    path('all-logs/', views.all_user_activity_logs, name='all_logs'),
    
    # User-specific views  
    path('user/<str:username>/', views.user_activity_detail, name='user_detail'),
    path('user/<str:username>/safe/', views.user_activity_detail_safe, name='user_detail_safe'),
    
    # Admin actions
    path('delete-user-logs/<str:username>/', views.delete_user_logs, name='delete_user_logs'),
    path('clear-all-logs/', views.clear_all_logs, name='clear_all_logs'),
    
    # API endpoints
    path('api/active-users/', views.active_users_api, name='active_users_api'),
    path('api/user-stats/<str:username>/', views.user_stats_api, name='user_stats_api'),
    
    # Test views (remove in production)
    path('test/', views.test_user_activity, name='test'),
    path('test-simple/', views.test_simple, name='test_simple'),
] 