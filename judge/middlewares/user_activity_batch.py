import logging
import re
import threading
import time
from collections import deque

from django.db import transaction
from django.utils import timezone
from user_agents import parse

from judge.utils.user_activity_realtime import publish_sessions_batch


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
                name='ActivityFlushThread',
            )
            self.__class__._flush_thread.start()
            logger.info('✅ Started realtime activity flush thread (2s interval)')

    def __call__(self, request):
        response = self.get_response(request)

        try:
            if not any(pattern.match(request.path) for pattern in self.excluded_patterns):
                self._collect_activity(request, response)
        except Exception:
            logger.exception('Error collecting activity')

        return response

    def _collect_activity(self, request, response):
        """Thu thập activity vào buffer"""
        # Validate response (theo logic gốc commit 5b0d18a)
        if not response or not hasattr(response, 'status_code'):
            return

        # Tạo session nếu chưa có (quan trọng cho anonymous users)
        if not hasattr(request, 'session'):
            return

        # Tạo session cho anonymous users (theo logic gốc)
        if not request.session.session_key:
            request.session.create()

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
                logger.info('🚀 Buffer reached %s items, flushing immediately', buffer_size)
                threading.Thread(target=self._flush_now, daemon=True).start()

    @classmethod
    def _flush_worker(cls):
        """Background worker - flush mỗi 2 giây"""
        while cls._running:
            try:
                time.sleep(cls.FLUSH_INTERVAL)
                cls._flush_now()
            except Exception:
                logger.exception('Error in flush worker')

    @classmethod
    def _flush_now(cls):
        """Flush buffers vào database"""
        from judge.models import (
            UserActivity,
            UserSession,
        )

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
                # 1. Update sessions - Build sessions_map đồng thời
                sessions_map = {}
                if sessions_to_update:
                    session_objects = []
                    for session_key, data in sessions_to_update.items():
                        session, created = UserSession.objects.get_or_create(
                            session_key=session_key,
                            defaults=data,
                        )
                        # Lưu vào map ngay (quan trọng!)
                        sessions_map[session_key] = session

                        if not created:
                            for key, value in data.items():
                                setattr(session, key, value)
                            session_objects.append(session)

                    if session_objects:
                        UserSession.objects.bulk_update(
                            session_objects,
                            [
                                'user', 'ip_address', 'user_agent', 'device_type',
                                'browser', 'os', 'last_activity', 'is_active',
                            ],
                            batch_size=100,
                        )

                    logger.info('✅ Flushed %s sessions', len(sessions_to_update))

                # 2. Create activities - Dùng sessions_map đã build ở trên
                if activities_to_save:
                    activity_objects = []
                    for activity_data in activities_to_save:
                        session_key = activity_data.pop('session_key')
                        session = sessions_map.get(session_key)
                        if session:  # Chỉ tạo activity nếu có session
                            activity_objects.append(UserActivity(session=session, **activity_data))

                    if activity_objects:
                        UserActivity.objects.bulk_create(
                            activity_objects,
                            ignore_conflicts=True,
                            batch_size=200,
                        )

                        logger.info('✅ Flushed %s activities', len(activity_objects))

            # 3. Publish realtime state to shared cache (Redis), non-blocking fallback
            if sessions_to_update:
                publish_sessions_batch(sessions_to_update)

        except Exception:
            logger.exception('❌ Error flushing buffers')

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
