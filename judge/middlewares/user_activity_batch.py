import threading
import time
from collections import deque
from django.utils import timezone
from django.db import transaction
from user_agents import parse
import logging
import re

logger = logging.getLogger(__name__)


class BatchUserActivityMiddleware:
    """
    Middleware tracking realtime với batch write optimization
    - Flush mỗi 2 giây hoặc khi buffer đạt 200 items
    - Admin thấy data với delay tối đa 2 giây
    - Giảm 95-99% database load
    """
    
    # Shared buffers giữa các threads
    _activity_buffer = deque(maxlen=5000)
    _session_buffer = {}
    _lock = threading.Lock()
    _flush_thread = None
    _running = True
    
    # Config cho REALTIME
    FLUSH_INTERVAL = 2      # 2 giây - Realtime
    BATCH_SIZE = 200        # Flush ngay khi đạt 200 items
    
    # Excluded paths
    EXCLUDED_PATHS = [
        r'^/admin/user-activity/',
        r'^/static/',
        r'^/media/',
        r'^/favicon\.ico$',
        r'^/robots\.txt$',
        r'^/__debug__/',
        r'^/admin/jsi18n/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.excluded_patterns = [re.compile(pattern) for pattern in self.EXCLUDED_PATHS]
        
        # Start flush thread (chỉ 1 lần)
        if not self.__class__._flush_thread:
            self.__class__._flush_thread = threading.Thread(
                target=self._flush_worker,
                daemon=True,
                name='ActivityFlushThread'
            )
            self.__class__._flush_thread.start()
            logger.info("✅ Started realtime activity flush thread (2s interval)")
    
    def __call__(self, request):
        response = self.get_response(request)
        
        try:
            if not any(pattern.match(request.path) for pattern in self.excluded_patterns):
                self._collect_activity(request, response)
        except Exception as e:
            logger.error(f"Error collecting activity: {e}")
        
        return response
    
    def _collect_activity(self, request, response):
        """Thu thập activity vào buffer"""
        session_key = request.session.session_key
        if not session_key:
            return
        
        user_agent_string = request.META.get('HTTP_USER_AGENT', '')
        user_agent = parse(user_agent_string)
        device_type = self._get_device_type(user_agent)
        
        now = timezone.now()
        user = request.user if request.user.is_authenticated else None
        ip_address = self._get_client_ip(request)
        
        with self.__class__._lock:
            # Session data
            self.__class__._session_buffer[session_key] = {
                'user': user,
                'ip_address': ip_address,
                'user_agent': user_agent_string,
                'device_type': device_type,
                'browser': user_agent.browser.family or '',
                'os': user_agent.os.family or '',
                'last_activity': now,
                'is_active': True,
            }
            
            # Activity data
            self.__class__._activity_buffer.append({
                'user': user,
                'session_key': session_key,
                'path': request.path[:500],
                'method': request.method,
                'ip_address': ip_address,
                'user_agent': user_agent_string[:500],
                'referer': request.META.get('HTTP_REFERER', '')[:500],
                'response_code': response.status_code,
                'timestamp': now,
            })
            
            # Flush ngay nếu buffer đạt BATCH_SIZE
            buffer_size = len(self.__class__._activity_buffer)
            if buffer_size >= self.BATCH_SIZE:
                logger.info(f"🚀 Buffer reached {buffer_size} items, flushing immediately")
                threading.Thread(target=self._flush_now, daemon=True).start()
    
    @classmethod
    def _flush_worker(cls):
        """Background worker - flush mỗi 2 giây"""
        while cls._running:
            try:
                time.sleep(cls.FLUSH_INTERVAL)
                cls._flush_now()
            except Exception as e:
                logger.error(f"Error in flush worker: {e}", exc_info=True)
    
    @classmethod
    def _flush_now(cls):
        """Flush buffers vào database"""
        from judge.models import UserActivity, UserSession
        
        with cls._lock:
            if not cls._activity_buffer and not cls._session_buffer:
                return
            
            activities_to_save = list(cls._activity_buffer)
            sessions_to_update = dict(cls._session_buffer)
            
            cls._activity_buffer.clear()
            cls._session_buffer.clear()
        
        if not activities_to_save and not sessions_to_update:
            return
        
        try:
            with transaction.atomic():
                # 1. Update sessions
                if sessions_to_update:
                    session_objects = []
                    for session_key, data in sessions_to_update.items():
                        session, created = UserSession.objects.get_or_create(
                            session_key=session_key,
                            defaults=data
                        )
                        if not created:
                            for key, value in data.items():
                                setattr(session, key, value)
                            session_objects.append(session)
                    
                    if session_objects:
                        UserSession.objects.bulk_update(
                            session_objects,
                            ['user', 'ip_address', 'user_agent', 'device_type', 
                             'browser', 'os', 'last_activity', 'is_active'],
                            batch_size=100
                        )
                    
                    logger.info(f"✅ Flushed {len(sessions_to_update)} sessions")
                
                # 2. Create activities
                if activities_to_save:
                    session_keys = [a['session_key'] for a in activities_to_save]
                    sessions_map = {
                        s.session_key: s 
                        for s in UserSession.objects.filter(session_key__in=session_keys)
                    }
                    
                    activity_objects = []
                    for activity_data in activities_to_save:
                        session_key = activity_data.pop('session_key')
                        session = sessions_map.get(session_key)
                        activity_objects.append(UserActivity(session=session, **activity_data))
                    
                    UserActivity.objects.bulk_create(
                        activity_objects,
                        ignore_conflicts=True,
                        batch_size=200
                    )
                    
                    logger.info(f"✅ Flushed {len(activity_objects)} activities")
                    
        except Exception as e:
            logger.error(f"❌ Error flushing buffers: {e}", exc_info=True)
    
    def _get_device_type(self, user_agent):
        """Xác định loại thiết bị từ user agent"""
        if user_agent.is_mobile:
            return 'mobile'
        elif user_agent.is_tablet:
            return 'tablet'
        elif user_agent.is_bot:
            return 'bot'
        elif user_agent.is_pc:
            return 'desktop'
        return 'unknown'
    
    def _get_client_ip(self, request):
        """Lấy IP address của client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

