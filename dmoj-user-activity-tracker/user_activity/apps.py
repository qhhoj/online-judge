from django.apps import AppConfig


class UserActivityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_activity'
    verbose_name = 'User Activity Tracker'
    
    def ready(self):
        # Import signal handlers if any
        pass 