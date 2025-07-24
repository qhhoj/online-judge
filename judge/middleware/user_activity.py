import re
from django.utils import timezone
from django.contrib.sessions.models import Session
from user_agents import parse

from judge.models import UserActivity, UserSession


class UserActivityMiddleware:
    """Middleware để theo dõi hoạt động người dùng"""
    
    # Các path không cần theo dõi
    EXCLUDED_PATHS = [
        r'^/admin/user-activity/active-users/$',
        r'^/static/',
        r'^/media/',
        r'^/favicon\.ico$',
        r'^/robots\.txt$',
        r'^/__debug__/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.excluded_patterns = [re.compile(pattern) for pattern in self.EXCLUDED_PATHS]
        
    def __call__(self, request):
        try:
        # Xử lý request
            response = self.get_response(request)
        
        # Kiểm tra xem path có bị loại trừ không
            if not any(pattern.match(request.path) for pattern in self.excluded_patterns):
            # Theo dõi cả người dùng đã đăng nhập và chưa đăng nhập
                if request.user.is_authenticated:
                    self.log_authenticated_activity(request, response)
                else:
                    self.log_anonymous_activity(request, response)
        except Exception as e:
            # Log lỗi nhưng không làm gián đoạn request
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error logging user activity: {e}")
                
            return self.get_response(request)
        
        
    def log_authenticated_activity(self, request, response):
        """Ghi lại hoạt động người dùng đã đăng nhập"""
        try:
            # Lấy hoặc tạo session
            session_key = request.session.session_key
            if session_key:
                user_agent_string = request.META.get('HTTP_USER_AGENT', '')
                user_agent = parse(user_agent_string)
                
                # Xác định loại thiết bị
                device_type = self.get_device_type(user_agent)
                
                # Cập nhật hoặc tạo UserSession
                user_session, created = UserSession.objects.update_or_create(
                    session_key=session_key,
                    defaults={
                        'user': request.user,
                        'ip_address': self.get_client_ip(request),
                        'user_agent': user_agent_string,
                        'device_type': device_type,
                        'browser': user_agent.browser.family if user_agent.browser.family else '',
                        'os': user_agent.os.family if user_agent.os.family else '',
                        'last_activity': timezone.now(),
                        'is_active': True,
                    }
                )
                
                # Ghi lại activity
                UserActivity.objects.create(
                    user=request.user,
                    session=user_session,
                    path=request.path,
                    method=request.method,
                    ip_address=self.get_client_ip(request),
                    user_agent=user_agent_string,
                    referer=request.META.get('HTTP_REFERER', ''),
                    response_code=response.status_code,
                )
        except Exception as e:
            # Log lỗi nhưng không làm gián đoạn request
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error logging authenticated user activity: {e}")
            
    def log_anonymous_activity(self, request, response):
        """Ghi lại hoạt động người dùng chưa đăng nhập"""
        try:
            # Tạo hoặc lấy session key cho anonymous user
            if not request.session.session_key:
                request.session.create()
            
            session_key = request.session.session_key
            if session_key:
                user_agent_string = request.META.get('HTTP_USER_AGENT', '')
                user_agent = parse(user_agent_string)
                
                # Xác định loại thiết bị
                device_type = self.get_device_type(user_agent)
                
                # Cập nhật hoặc tạo UserSession cho anonymous user (user=None)
                user_session, created = UserSession.objects.update_or_create(
                    session_key=session_key,
                    defaults={
                        'user': None,  # Anonymous user
                        'ip_address': self.get_client_ip(request),
                        'user_agent': user_agent_string,
                        'device_type': device_type,
                        'browser': user_agent.browser.family if user_agent.browser.family else '',
                        'os': user_agent.os.family if user_agent.os.family else '',
                        'last_activity': timezone.now(),
                        'is_active': True,
                    }
                )
                
                # Ghi lại activity cho anonymous user
                UserActivity.objects.create(
                    user=None,  # Anonymous user
                    session=user_session,
                    path=request.path,
                    method=request.method,
                    ip_address=self.get_client_ip(request),
                    user_agent=user_agent_string,
                    referer=request.META.get('HTTP_REFERER', ''),
                    response_code=response.status_code,
                )
        except Exception as e:
            # Log lỗi nhưng không làm gián đoạn request
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error logging anonymous user activity: {e}")
            
    def get_device_type(self, user_agent):
        """Xác định loại thiết bị từ user agent"""
        if user_agent.is_mobile:
            return 'mobile'
        elif user_agent.is_tablet:
            return 'tablet'
        elif user_agent.is_bot:
            return 'bot'
        elif user_agent.is_pc:
            return 'desktop'
        else:
            return 'unknown'
            
    def get_client_ip(self, request):
        """Lấy IP thực của client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip 