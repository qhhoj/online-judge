from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from judge.models import UserActivity, UserSession


class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip_address', 'device_type', 'browser', 'os', 'is_active', 'last_activity', 'created_at')
    list_filter = ('is_active', 'device_type', 'browser', 'os', 'created_at')
    search_fields = ('user__username', 'ip_address', 'user_agent')
    readonly_fields = ('session_key', 'user', 'ip_address', 'user_agent', 'device_type', 'browser', 'os', 'created_at')
    ordering = ('-last_activity',)
    
    def has_add_permission(self, request):
        return False
        
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Tự động đánh dấu session không hoạt động nếu quá 30 phút
        cutoff_time = timezone.now() - timedelta(minutes=30)
        qs.filter(is_active=True, last_activity__lt=cutoff_time).update(is_active=False)
        return qs


class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user_link', 'path', 'method', 'ip_address', 'timestamp', 'response_code')
    list_filter = ('method', 'response_code', 'timestamp')
    search_fields = ('user__username', 'path', 'ip_address')
    readonly_fields = ('user', 'session', 'timestamp', 'path', 'method', 'ip_address', 'user_agent', 'referer', 'response_code')
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'
    
    def user_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.user.pk])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = _('User')
    user_link.admin_order_field = 'user__username'
    
    def has_add_permission(self, request):
        return False
        
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


admin.site.register(UserSession, UserSessionAdmin)
admin.site.register(UserActivity, UserActivityAdmin) 