"""
Safe User Activity Middleware - Version with robust error handling
"""
import re
import logging
from django.utils import timezone

# Configure logger
logger = logging.getLogger(__name__)

class UserActivityMiddleware:
    """Safe middleware để theo dõi hoạt động người dùng với error handling tốt hơn"""
    
    # Các path không cần theo dõi
    EXCLUDED_PATHS = [
        r'^/admin/user-activity/',  # Tất cả user activity admin paths
        r'^/static/',
        r'^/media/',
        r'^/favicon\.ico$',
        r'^/robots\.txt$',
        r'^/__debug__/',
        r'^/admin/jsi18n/',  # Django admin i18n
        r'^/admin/logout/',  # Admin logout
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.excluded_patterns = [re.compile(pattern) for pattern in self.EXCLUDED_PATHS]
        self.enabled = True
        
        # Test if models are available
        try:
            from judge.models import UserActivity, UserSession
            self.UserActivity = UserActivity
            self.UserSession = UserSession
        except ImportError as e:
            logger.error(f"Cannot import UserActivity models: {e}")
            self.enabled = False
        except Exception as e:
            logger.error(f"Error initializing UserActivity middleware: {e}")
            self.enabled = False
        
    def __call__(self, request):
        # LUÔN phải get response trước
        response = self.get_response(request)
        
        # Chỉ xử lý nếu middleware enabled và response valid
        if not self.enabled or not response:
            return response
            
        # Kiểm tra response có valid không
        if not hasattr(response, 'status_code'):
            logger.warning("Response object missing status_code attribute")
            return response
        
        try:
            # Kiểm tra xem path có bị loại trừ không
            if not any(pattern.match(request.path) for pattern in self.excluded_patterns):
                self._safe_log_activity(request, response)
        except Exception as e:
            logger.error(f"Critical error in UserActivity middleware: {e}", exc_info=True)
            # Không làm gián đoạn request trong mọi trường hợp
        
        return response
    
    def _safe_log_activity(self, request, response):
        """Safely log activity with comprehensive error handling"""
        try:
            # Check if user is authenticated
            if hasattr(request, 'user') and request.user.is_authenticated:
                self._log_authenticated_activity(request, response)
            else:
                self._log_anonymous_activity(request, response)
        except Exception as e:
            logger.error(f"Error in _safe_log_activity: {e}", exc_info=True)
    
    def _log_authenticated_activity(self, request, response):
        """Ghi lại hoạt động người dùng đã đăng nhập"""
        try:
            session_key = getattr(request.session, 'session_key', None)
            if not session_key:
                return
                
            # Import user-agents safely
            try:
                from user_agents import parse
                user_agent_string = request.META.get('HTTP_USER_AGENT', '')
                user_agent = parse(user_agent_string)
                device_type = self._get_device_type(user_agent)
                browser = user_agent.browser.family if user_agent.browser.family else ''
                os = user_agent.os.family if user_agent.os.family else ''
            except ImportError:
                logger.warning("user-agents library not available")
                device_type = 'unknown'
                browser = ''
                os = ''
            except Exception as e:
                logger.error(f"Error parsing user agent: {e}")
                device_type = 'unknown'
                browser = ''
                os = ''
            
            # Cập nhật hoặc tạo UserSession
            user_session, created = self.UserSession.objects.update_or_create(
                session_key=session_key,
                defaults={
                    'user': request.user,
                    'ip_address': self._get_client_ip(request),
                    'user_agent': user_agent_string,
                    'device_type': device_type,
                    'browser': browser,
                    'os': os,
                    'last_activity': timezone.now(),
                    'is_active': True,
                }
            )
            
            # Ghi lại activity
            self.UserActivity.objects.create(
                user=request.user,
                session=user_session,
                path=request.path[:500],  # Limit path length
                method=request.method,
                ip_address=self._get_client_ip(request),
                user_agent=user_agent_string[:500],  # Limit user agent length
                referer=request.META.get('HTTP_REFERER', '')[:500],  # Limit referer length
                response_code=response.status_code,
            )
            
        except Exception as e:
            logger.error(f"Error logging authenticated user activity: {e}")
    
    def _log_anonymous_activity(self, request, response):
        """Ghi lại hoạt động người dùng chưa đăng nhập"""
        try:
            # Tạo session nếu chưa có
            if not hasattr(request, 'session'):
                return
                
            if not request.session.session_key:
                request.session.create()
            
            session_key = request.session.session_key
            if not session_key:
                return
                
            # Import user-agents safely
            try:
                from user_agents import parse
                user_agent_string = request.META.get('HTTP_USER_AGENT', '')
                user_agent = parse(user_agent_string)
                device_type = self._get_device_type(user_agent)
                browser = user_agent.browser.family if user_agent.browser.family else ''
                os = user_agent.os.family if user_agent.os.family else ''
            except ImportError:
                logger.warning("user-agents library not available")
                device_type = 'unknown'
                browser = ''
                os = ''
            except Exception as e:
                logger.error(f"Error parsing user agent: {e}")
                device_type = 'unknown'
                browser = ''
                os = ''
            
            # Cập nhật hoặc tạo UserSession cho anonymous user
            user_session, created = self.UserSession.objects.update_or_create(
                session_key=session_key,
                defaults={
                    'user': None,  # Anonymous user
                    'ip_address': self._get_client_ip(request),
                    'user_agent': user_agent_string,
                    'device_type': device_type,
                    'browser': browser,
                    'os': os,
                    'last_activity': timezone.now(),
                    'is_active': True,
                }
            )
            
            # Ghi lại activity cho anonymous user
            self.UserActivity.objects.create(
                user=None,  # Anonymous user
                session=user_session,
                path=request.path[:500],  # Limit path length
                method=request.method,
                ip_address=self._get_client_ip(request),
                user_agent=user_agent_string[:500],  # Limit user agent length
                referer=request.META.get('HTTP_REFERER', '')[:500],  # Limit referer length
                response_code=response.status_code,
            )
            
        except Exception as e:
            logger.error(f"Error logging anonymous user activity: {e}")
    
    def _get_device_type(self, user_agent):
        """Xác định loại thiết bị từ user agent"""
        try:
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
        except:
            return 'unknown'
    
    def _get_client_ip(self, request):
        """Lấy IP thực của client"""
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
            return ip
        except:
            return '127.0.0.1' 