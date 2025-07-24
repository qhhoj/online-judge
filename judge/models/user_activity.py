from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserSession(models.Model):
    """Model để lưu thông tin phiên truy cập của người dùng"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_sessions', null=True, blank=True)
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField(verbose_name=_('IP address'))
    user_agent = models.TextField(verbose_name=_('user agent'))
    device_type = models.CharField(max_length=20, verbose_name=_('device type'), choices=[
        ('desktop', _('Desktop')),
        ('mobile', _('Mobile')),
        ('tablet', _('Tablet')),
        ('bot', _('Bot')),
        ('unknown', _('Unknown')),
    ], default='unknown')
    browser = models.CharField(max_length=50, verbose_name=_('browser'), blank=True)
    os = models.CharField(max_length=50, verbose_name=_('operating system'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))
    last_activity = models.DateTimeField(default=timezone.now, verbose_name=_('last activity'))
    is_active = models.BooleanField(default=True, verbose_name=_('is active'))
    
    class Meta:
        verbose_name = _('user session')
        verbose_name_plural = _('user sessions')
        ordering = ['-last_activity']
        
    def __str__(self):
        username = self.user.username if self.user else 'Anonymous'
        return f"{username} - {self.ip_address} - {self.device_type}"


class UserActivity(models.Model):
    """Model để lưu lịch sử hoạt động của người dùng"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities', null=True, blank=True)
    session = models.ForeignKey(UserSession, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_('timestamp'))
    path = models.CharField(max_length=500, verbose_name=_('path'))
    method = models.CharField(max_length=10, verbose_name=_('HTTP method'), default='GET')
    ip_address = models.GenericIPAddressField(verbose_name=_('IP address'))
    user_agent = models.TextField(verbose_name=_('user agent'), blank=True)
    referer = models.TextField(verbose_name=_('referer'), blank=True)
    response_code = models.IntegerField(verbose_name=_('response code'), null=True, blank=True)
    
    class Meta:
        verbose_name = _('user activity')
        verbose_name_plural = _('user activities')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['ip_address', '-timestamp']),
        ]
        
    def __str__(self):
        username = self.user.username if self.user else 'Anonymous'
        return f"{username} - {self.path} - {self.timestamp}" 