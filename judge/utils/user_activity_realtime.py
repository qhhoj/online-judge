import json
import logging
import math

from django.conf import settings
from django.utils import timezone

try:
    from django_redis import get_redis_connection
except Exception:  # pragma: no cover - optional dependency at runtime
    get_redis_connection = None


logger = logging.getLogger(__name__)

TAB_AUTHENTICATED = 'authenticated'
TAB_ANONYMOUS = 'anonymous'
TAB_BOTS = 'bots'
TAB_ALL = 'all'

TAB_TO_KEY = {
    TAB_ALL: 'sessions:all',
    TAB_AUTHENTICATED: 'sessions:authenticated',
    TAB_ANONYMOUS: 'sessions:anonymous',
    TAB_BOTS: 'sessions:bots',
}


def _realtime_enabled():
    return bool(getattr(settings, 'USER_ACTIVITY_REALTIME_CACHE_ENABLED', False))


def _cache_alias():
    return getattr(settings, 'USER_ACTIVITY_REALTIME_CACHE_ALIAS', 'user_activity_realtime')


def _cache_prefix():
    return getattr(settings, 'USER_ACTIVITY_REALTIME_CACHE_PREFIX', 'user_activity:realtime')


def _window_seconds():
    return max(60, int(getattr(settings, 'USER_ACTIVITY_REALTIME_WINDOW_SECONDS', 1800)))


def _snapshot_ttl_seconds():
    return max(5, int(getattr(settings, 'USER_ACTIVITY_REALTIME_SNAPSHOT_TTL_SECONDS', 15)))


def _cache_key(name):
    return f'{_cache_prefix()}:{name}'


def _snapshot_cache_key():
    return _cache_key('snapshot')


def _session_hash_key(session_key):
    return _cache_key(f'session:{session_key}')


def _decode(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='ignore')
    return value


def _decode_hash(raw_hash):
    decoded = {}
    for key, value in raw_hash.items():
        decoded[_decode(key)] = _decode(value)
    return decoded


def _redis_client():
    if not _realtime_enabled() or get_redis_connection is None:
        return None
    try:
        return get_redis_connection(_cache_alias())
    except Exception:
        return None


def _session_tab(data):
    if data.get('device_type') == 'bot':
        return TAB_BOTS
    if data.get('user') is not None:
        return TAB_AUTHENTICATED
    return TAB_ANONYMOUS


def _cleanup_stale_sessions(client):
    cutoff = int(timezone.now().timestamp()) - _window_seconds()
    pipe = client.pipeline(transaction=False)
    for key_suffix in TAB_TO_KEY.values():
        pipe.zremrangebyscore(_cache_key(key_suffix), '-inf', cutoff)
    pipe.execute()


def publish_sessions_batch(sessions_to_update):
    """
    Publish active session state to realtime Redis keys.
    Keeps DB as source of truth for full history.
    """
    if not sessions_to_update:
        return False

    client = _redis_client()
    if client is None:
        return False

    now = timezone.now()
    hash_ttl = max(_window_seconds() * 3, _window_seconds() + 60)
    all_key = _cache_key(TAB_TO_KEY[TAB_ALL])
    tab_keys = {
        TAB_AUTHENTICATED: _cache_key(TAB_TO_KEY[TAB_AUTHENTICATED]),
        TAB_ANONYMOUS: _cache_key(TAB_TO_KEY[TAB_ANONYMOUS]),
        TAB_BOTS: _cache_key(TAB_TO_KEY[TAB_BOTS]),
    }

    try:
        pipe = client.pipeline(transaction=False)
        for session_key, data in sessions_to_update.items():
            if not session_key:
                continue

            session_key = str(session_key)
            last_activity = data.get('last_activity') or now
            score = int(last_activity.timestamp())
            user = data.get('user')
            user_id = str(getattr(user, 'id', '') or '')
            username = getattr(user, 'username', '') if user else ''
            tab_name = _session_tab(data)

            session_payload = {
                'user_id': user_id,
                'username': username or '',
                'ip_address': data.get('ip_address') or '',
                'device_type': data.get('device_type') or 'unknown',
                'browser': data.get('browser') or '',
                'os': data.get('os') or '',
                'user_agent': (data.get('user_agent') or '')[:500],
                'last_activity': last_activity.isoformat(),
                'last_activity_ts': str(score),
            }

            hash_key = _session_hash_key(session_key)
            pipe.hset(hash_key, mapping=session_payload)
            pipe.expire(hash_key, hash_ttl)

            pipe.zadd(all_key, {session_key: score})
            pipe.zadd(tab_keys[tab_name], {session_key: score})

            for other_tab, other_key in tab_keys.items():
                if other_tab != tab_name:
                    pipe.zrem(other_key, session_key)

        cutoff = int(now.timestamp()) - _window_seconds()
        pipe.zremrangebyscore(all_key, '-inf', cutoff)
        for key in tab_keys.values():
            pipe.zremrangebyscore(key, '-inf', cutoff)

        pipe.execute()
        return True
    except Exception:
        logger.exception('Failed to publish user activity realtime batch')
        return False


def _serialize_session(tab_name, session_hash):
    base = {
        'ip_address': session_hash.get('ip_address') or 'N/A',
        'device_type': session_hash.get('device_type') or 'unknown',
        'browser': session_hash.get('browser') or 'Unknown',
        'os': session_hash.get('os') or 'Unknown',
        'last_activity': session_hash.get('last_activity'),
    }

    if tab_name == TAB_AUTHENTICATED:
        base['username'] = session_hash.get('username') or 'Unknown'
    elif tab_name == TAB_BOTS:
        user_agent = session_hash.get('user_agent') or 'Unknown Bot'
        if len(user_agent) > 100:
            user_agent = user_agent[:100] + '...'
        base['user_agent'] = user_agent

    return base


def get_realtime_sessions_page(tab_name, page=1, per_page=50):
    if tab_name not in {TAB_AUTHENTICATED, TAB_ANONYMOUS, TAB_BOTS}:
        return None

    client = _redis_client()
    if client is None:
        return None

    per_page = max(1, min(int(per_page), 100))
    page = max(1, int(page))
    zset_key = _cache_key(TAB_TO_KEY[tab_name])

    try:
        _cleanup_stale_sessions(client)

        total_count = int(client.zcard(zset_key) or 0)
        total_pages = max(1, int(math.ceil(total_count / float(per_page))))
        if page > total_pages:
            page = total_pages

        start = (page - 1) * per_page
        stop = start + per_page - 1
        session_keys = [_decode(item) for item in client.zrevrange(zset_key, start, stop)]

        sessions = []
        if session_keys:
            pipe = client.pipeline(transaction=False)
            for session_key in session_keys:
                pipe.hgetall(_session_hash_key(session_key))
            raw_hashes = pipe.execute()
            for raw_hash in raw_hashes:
                session_hash = _decode_hash(raw_hash or {})
                if session_hash:
                    sessions.append(_serialize_session(tab_name, session_hash))

        return {
            'sessions': sessions,
            'has_next': page < total_pages,
            'has_previous': page > 1,
            'current_page': page,
            'total_pages': total_pages,
            'total_count': total_count,
        }
    except Exception:
        logger.exception('Failed to read realtime sessions page for %s', tab_name)
        return None


def build_realtime_snapshot():
    """
    Build summary metrics from realtime Redis state and cache it.
    """
    client = _redis_client()
    if client is None:
        return None

    all_key = _cache_key(TAB_TO_KEY[TAB_ALL])
    auth_key = _cache_key(TAB_TO_KEY[TAB_AUTHENTICATED])
    anon_key = _cache_key(TAB_TO_KEY[TAB_ANONYMOUS])
    bot_key = _cache_key(TAB_TO_KEY[TAB_BOTS])

    try:
        _cleanup_stale_sessions(client)

        total_sessions = int(client.zcard(all_key) or 0)
        authenticated_total = int(client.zcard(auth_key) or 0)
        anonymous_total = int(client.zcard(anon_key) or 0)
        bot_total = int(client.zcard(bot_key) or 0)

        auth_members = [_decode(item) for item in client.zrange(auth_key, 0, -1)]
        auth_unique_users = set()
        if auth_members:
            pipe = client.pipeline(transaction=False)
            for session_key in auth_members:
                pipe.hget(_session_hash_key(session_key), 'user_id')
            for user_id in pipe.execute():
                user_id = _decode(user_id)
                if user_id:
                    auth_unique_users.add(user_id)

        bot_members = [_decode(item) for item in client.zrange(bot_key, 0, -1)]
        bot_authenticated_users = set()
        bot_anonymous_sessions = 0
        if bot_members:
            pipe = client.pipeline(transaction=False)
            for session_key in bot_members:
                pipe.hget(_session_hash_key(session_key), 'user_id')
            for user_id in pipe.execute():
                user_id = _decode(user_id)
                if user_id:
                    bot_authenticated_users.add(user_id)
                else:
                    bot_anonymous_sessions += 1

        snapshot = {
            'authenticated_users': len(auth_unique_users),
            'anonymous_users': anonymous_total,
            'total_human_sessions': authenticated_total + anonymous_total,
            'total_human_unique': len(auth_unique_users) + anonymous_total,
            'bot_authenticated': len(bot_authenticated_users),
            'bot_anonymous': bot_anonymous_sessions,
            'total_bot_sessions': bot_total,
            'total_bot_unique': len(bot_authenticated_users) + bot_anonymous_sessions,
            'total_sessions': total_sessions,
            'total_unique_all': len(auth_unique_users) + anonymous_total + len(bot_authenticated_users) + bot_anonymous_sessions,
            'generated_at': timezone.now().isoformat(),
        }

        client.set(_snapshot_cache_key(), json.dumps(snapshot), ex=_snapshot_ttl_seconds())
        return snapshot
    except Exception:
        logger.exception('Failed to build realtime user activity snapshot')
        return None


def get_cached_realtime_snapshot():
    client = _redis_client()
    if client is None:
        return None

    try:
        raw = client.get(_snapshot_cache_key())
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8', errors='ignore')
            return json.loads(raw)
    except Exception:
        logger.exception('Failed to load realtime snapshot from cache')

    return build_realtime_snapshot()


def refresh_realtime_snapshot():
    return build_realtime_snapshot() is not None
