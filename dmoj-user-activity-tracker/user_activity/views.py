import json
import csv
from datetime import timedelta, datetime
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Count, Q
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator

from judge.models import UserActivity, UserSession, Profile


@login_required
@permission_required('judge.can_see_user_activity', raise_exception=True)
def active_users_view(request):
    """View để xem người dùng đang hoạt động - Cải thiện tách bot và human users"""
    # Lấy người dùng hoạt động trong 30 phút qua
    cutoff_time = timezone.now() - timedelta(minutes=30)
    
    # Lấy tất cả sessions đang hoạt động
    all_active_sessions = UserSession.objects.filter(
        last_activity__gte=cutoff_time,
        is_active=True
    ).select_related('user')
    
    # PHÂN LOẠI SESSIONS: BOT vs HUMAN
    bot_sessions = all_active_sessions.filter(device_type='bot')
    human_sessions = all_active_sessions.exclude(device_type='bot')
    
    # Phân loại human sessions
    authenticated_sessions = human_sessions.filter(user__isnull=False)
    anonymous_sessions = human_sessions.filter(user__isnull=True)
    
    # Bot sessions - phân loại bot auth và bot anonymous
    bot_authenticated_sessions = bot_sessions.filter(user__isnull=False)
    bot_anonymous_sessions = bot_sessions.filter(user__isnull=True)
    
    # Thống kê người dùng đăng nhập với nhiều phiên (KHÔNG bao gồm bot)
    users_with_sessions = {}
    for session in authenticated_sessions:
        username = session.user.username
        if username not in users_with_sessions:
            users_with_sessions[username] = {
                'user': session.user,
                'sessions': []
            }
        users_with_sessions[username]['sessions'].append(session)
    
    # Sắp xếp theo số lượng phiên
    multi_session_users = sorted(
        [(k, v) for k, v in users_with_sessions.items() if len(v['sessions']) > 1],
        key=lambda x: len(x[1]['sessions']),
        reverse=True
    )
    
    # Thống kê theo thiết bị cho HUMAN sessions (không bao gồm bot)
    device_stats = human_sessions.values('device_type').annotate(count=Count('id'))
    
    # Thống kê theo browser cho HUMAN sessions
    browser_stats = human_sessions.values('browser').annotate(count=Count('id'))
    
    # Thống kê theo OS cho HUMAN sessions
    os_stats = human_sessions.values('os').annotate(count=Count('id'))
    
    # Thống kê BOT riêng biệt
    bot_stats = {
        'total_bots': bot_sessions.count(),
        'bot_authenticated': bot_authenticated_sessions.count(),
        'bot_anonymous': bot_anonymous_sessions.count(),
        'bot_browser_stats': bot_sessions.values('browser').annotate(count=Count('id')),
        'bot_user_agents': bot_sessions.values('user_agent').annotate(count=Count('id')).order_by('-count')[:20],
    }
    
    # Thống kê theo IP (tìm các IP có nhiều sessions) - HUMAN only
    ip_stats = human_sessions.values('ip_address').annotate(
        count=Count('id'),
        users=Count('user', distinct=True)
    ).filter(count__gt=1).order_by('-count')[:10]
    
    # Thống kê BOT theo IP
    bot_ip_stats = bot_sessions.values('ip_address').annotate(
        count=Count('id'),
        users=Count('user', distinct=True)
    ).order_by('-count')[:10]
    
    # Thống kê tổng quan
    total_users_registered = User.objects.filter(is_active=True).count()
    total_users_online = authenticated_sessions.values('user').distinct().count()
    total_anonymous_online = anonymous_sessions.count()
    
    context = {
        # HUMAN USERS
        'authenticated_sessions': authenticated_sessions,
        'anonymous_sessions': anonymous_sessions,
        'total_active_users': total_users_online,
        'total_anonymous': total_anonymous_online,
        'total_human_sessions': human_sessions.count(),
        'total_users_registered': total_users_registered,
        'users_with_sessions': users_with_sessions,
        'multi_session_users': multi_session_users,
        'device_stats': device_stats,
        'browser_stats': browser_stats,
        'os_stats': os_stats,
        'ip_stats': ip_stats,
        
        # BOT STATISTICS - TÁCH RIÊNG
        'bot_sessions': bot_sessions,
        'bot_authenticated_sessions': bot_authenticated_sessions,
        'bot_anonymous_sessions': bot_anonymous_sessions,
        'bot_stats': bot_stats,
        'bot_ip_stats': bot_ip_stats,
        
        # TỔNG QUAN
        'total_sessions': all_active_sessions.count(),
        'show_bots_separate': True,  # Flag để template biết hiển thị bot riêng
    }
    
    return render(request, 'user_activity/active_users.html', context)


@login_required
@permission_required('judge.can_see_user_activity', raise_exception=True)
def user_activity_detail(request, username):
    """View để xem chi tiết hoạt động của một người dùng - LƯU LỊCH SỬ HOÀN CHỈNH"""
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return render(request, 'admin/user_activity/404.html', status=404)
    
    # Lấy filter parameters
    days = request.GET.get('days', '90')  # Tăng lên 90 ngày default
    try:
        days = int(days)
        # Giới hạn tối đa 365 ngày để tránh query quá nặng
        if days > 365:
            days = 365
    except ValueError:
        days = 90
    
    # Lấy TẤT CẢ hoạt động trong khoảng thời gian (LƯU LỊCH SỬ ĐẦY ĐỦ)
    if days == -1:  # -1 nghĩa là lấy tất cả
        activities = UserActivity.objects.filter(user=user).order_by('-timestamp')
        time_ago = None
    else:
        time_ago = timezone.now() - timedelta(days=days)
        activities = UserActivity.objects.filter(
            user=user,
            timestamp__gte=time_ago
        ).order_by('-timestamp')
    
    # Phân trang cho activities
    paginator = Paginator(activities, 100)  # 100 per page
    page = request.GET.get('page', 1)
    activities_page = paginator.get_page(page)
    
    # Lấy TẤT CẢ các phiên truy cập (KHÔNG chỉ active) - LỊCH SỬ ĐẦY ĐỦ
    all_sessions = UserSession.objects.filter(user=user).order_by('-last_activity')
    
    # Sessions hiện tại đang hoạt động
    active_sessions = all_sessions.filter(
        last_activity__gte=timezone.now() - timedelta(minutes=30),
        is_active=True
    )
    
    # Sessions gần đây (7 ngày qua)
    recent_sessions = all_sessions.filter(
        last_activity__gte=timezone.now() - timedelta(days=7)
    )
    
    # Thống kê hoạt động theo ngày - FIXED JSON serialization
    daily_stats = []
    if time_ago:
        try:
            # Sử dụng raw SQL để tránh vấn đề JSON serialization
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DATE(timestamp) as day, COUNT(*) as count
                    FROM judge_useractivity 
                    WHERE user_id = %s AND timestamp >= %s
                    GROUP BY DATE(timestamp)
                    ORDER BY day
                """, [user.id, time_ago])
                
                for row in cursor.fetchall():
                    daily_stats.append({
                        'day': row[0].strftime('%Y-%m-%d'),
                        'count': row[1]
                    })
        except Exception as e:
            # Fallback if there's any error
            daily_stats = []
    
    # Safe JSON serialization
    try:
        daily_stats_json = json.dumps(daily_stats) if daily_stats else '[]'
    except (TypeError, ValueError):
        daily_stats_json = '[]'
    
    # Thống kê theo IP - Lịch sử đầy đủ
    filter_condition = {'user': user}
    if time_ago:
        filter_condition['timestamp__gte'] = time_ago
        
    ip_stats = UserActivity.objects.filter(**filter_condition).values('ip_address').annotate(count=Count('id')).order_by('-count')[:20]
    
    # Thống kê theo path được truy cập nhiều nhất - Lịch sử đầy đủ  
    path_stats = UserActivity.objects.filter(**filter_condition).values('path').annotate(count=Count('id')).order_by('-count')[:30]
    
    # Thống kê theo device type từ sessions
    device_stats = all_sessions.values('device_type').annotate(count=Count('id')).order_by('-count')
    
    # Thống kê theo browser từ sessions
    browser_stats = all_sessions.values('browser').annotate(count=Count('id')).order_by('-count')
    
    # Thống kê theo thời gian truy cập (theo giờ trong ngày)
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT EXTRACT(hour FROM timestamp) as hour, COUNT(*) as count
                FROM judge_useractivity 
                WHERE user_id = %s {}
                GROUP BY EXTRACT(hour FROM timestamp)
                ORDER BY hour
            """.format("AND timestamp >= %s" if time_ago else ""), 
            [user.id] + ([time_ago] if time_ago else []))
            
            hour_stats = [{'hour': int(row[0]), 'count': row[1]} for row in cursor.fetchall()]
    except Exception:
        hour_stats = []
    
    context = {
        'target_user': user,
        'activities': activities_page,
        'all_sessions': all_sessions[:50],  # Limit display to 50 most recent
        'recent_sessions': recent_sessions,
        'active_sessions': active_sessions,
        'active_session_count': active_sessions.count(),
        'total_session_count': all_sessions.count(),
        'recent_session_count': recent_sessions.count(),
        'total_activities': activities.count(),
        'daily_stats': daily_stats_json,
        'ip_stats': ip_stats,
        'path_stats': path_stats,
        'device_stats': device_stats,
        'browser_stats': browser_stats,
        'hour_stats': hour_stats,
        'days_filter': days,
        'has_complete_history': True,  # Flag để template biết có lịch sử đầy đủ
    }
    
    return render(request, 'admin/user_activity/user_detail_standalone.html', context)


@login_required
@permission_required('judge.can_see_user_activity', raise_exception=True)
def all_logs_view(request):
    """View để xem tất cả logs"""
    # Lấy filter parameters
    days = request.GET.get('days', '7')
    user_filter = request.GET.get('user', '')
    ip_filter = request.GET.get('ip', '')
    path_filter = request.GET.get('path', '')
    
    try:
        days = int(days)
    except ValueError:
        days = 7
    
    # Base query
    time_ago = timezone.now() - timedelta(days=days)
    activities = UserActivity.objects.filter(timestamp__gte=time_ago)
    
    # Apply filters
    if user_filter:
        if user_filter == 'anonymous':
            activities = activities.filter(user__isnull=True)
        else:
            activities = activities.filter(user__username__icontains=user_filter)
    
    if ip_filter:
        activities = activities.filter(ip_address__icontains=ip_filter)
    
    if path_filter:
        activities = activities.filter(path__icontains=path_filter)
    
    activities = activities.select_related('user', 'session').order_by('-timestamp')
    
    # Phân trang
    paginator = Paginator(activities, 50)  # 50 per page
    page = request.GET.get('page', 1)
    activities_page = paginator.get_page(page)
    
    # Thống kê
    total_activities = activities.count()
    unique_users = activities.exclude(user__isnull=True).values('user').distinct().count()
    unique_anonymous = activities.filter(user__isnull=True).values('session').distinct().count()
    unique_ips = activities.values('ip_address').distinct().count()
    
    context = {
        'activities': activities_page,
        'total_activities': total_activities,
        'unique_users': unique_users,
        'unique_anonymous': unique_anonymous,
        'unique_ips': unique_ips,
        'days_filter': days,
        'user_filter': user_filter,
        'ip_filter': ip_filter,
        'path_filter': path_filter,
    }
    
    return render(request, 'admin/user_activity/all_logs.html', context)


@login_required
@permission_required('judge.can_see_user_activity', raise_exception=True)
def export_logs(request):
    """Export logs ra file CSV"""
    # Lấy filter parameters
    days = request.GET.get('days', '7')
    user_filter = request.GET.get('user', '')
    ip_filter = request.GET.get('ip', '')
    path_filter = request.GET.get('path', '')
    
    try:
        days = int(days)
    except ValueError:
        days = 7
    
    # Base query
    time_ago = timezone.now() - timedelta(days=days)
    activities = UserActivity.objects.filter(timestamp__gte=time_ago)
    
    # Apply filters (same as all_logs_view)
    if user_filter:
        if user_filter == 'anonymous':
            activities = activities.filter(user__isnull=True)
        else:
            activities = activities.filter(user__username__icontains=user_filter)
    
    if ip_filter:
        activities = activities.filter(ip_address__icontains=ip_filter)
    
    if path_filter:
        activities = activities.filter(path__icontains=path_filter)
    
    activities = activities.select_related('user', 'session').order_by('-timestamp')
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="user_activity_logs_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'User', 'IP Address', 'Path', 'Method', 'Response Code', 'User Agent', 'Referer'])
    
    for activity in activities:
        writer.writerow([
            activity.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            activity.user.username if activity.user else 'Anonymous',
            activity.ip_address,
            activity.path,
            activity.method,
            activity.response_code,
            activity.user_agent,
            activity.referer,
        ])
    
    return response


@login_required
@permission_required('judge.can_see_user_activity', raise_exception=True)
def delete_user_logs(request, username):
    """Xóa logs của một user cụ thể"""
    try:
        user = User.objects.get(username=username)
        deleted_count = UserActivity.objects.filter(user=user).count()
        UserActivity.objects.filter(user=user).delete()
        UserSession.objects.filter(user=user).delete()
        messages.success(request, f'Đã xóa {deleted_count} logs của user {username}')
    except User.DoesNotExist:
        messages.error(request, f'User {username} không tồn tại')
    
    return redirect('all_logs')


@login_required
@permission_required('judge.can_see_user_activity', raise_exception=True)
def delete_anonymous_logs(request):
    """Xóa logs của anonymous users"""
    if request.method == 'POST':
        deleted_activities = UserActivity.objects.filter(user__isnull=True).count()
        deleted_sessions = UserSession.objects.filter(user__isnull=True).count()
        
        UserActivity.objects.filter(user__isnull=True).delete()
        UserSession.objects.filter(user__isnull=True).delete()
        
        messages.success(request, f'Đã xóa {deleted_activities} activities và {deleted_sessions} sessions của anonymous users')
    
    return redirect('all_logs')


@login_required
@permission_required('judge.can_see_user_activity', raise_exception=True)
def active_users_api(request):
    """API endpoint để lấy số người đang truy cập (cập nhật realtime) - TÁCH BOT VÀ HUMAN"""
    cutoff_time = timezone.now() - timedelta(minutes=30)
    
    all_sessions = UserSession.objects.filter(
        last_activity__gte=cutoff_time,
        is_active=True
    )
    
    # PHÂN LOẠI BOT vs HUMAN
    bot_sessions = all_sessions.filter(device_type='bot')
    human_sessions = all_sessions.exclude(device_type='bot')
    
    # Human statistics
    authenticated_count = human_sessions.filter(user__isnull=False).values('user').distinct().count()
    anonymous_count = human_sessions.filter(user__isnull=True).count()
    
    # Bot statistics
    bot_authenticated_count = bot_sessions.filter(user__isnull=False).values('user').distinct().count()
    bot_anonymous_count = bot_sessions.filter(user__isnull=True).count()
    
    data = {
        # HUMAN USERS
        'authenticated_users': authenticated_count,
        'anonymous_users': anonymous_count,
        'total_human_sessions': human_sessions.count(),
        'total_human_unique': authenticated_count + anonymous_count,
        
        # BOT USERS - TÁCH RIÊNG
        'bot_authenticated': bot_authenticated_count,
        'bot_anonymous': bot_anonymous_count,
        'total_bot_sessions': bot_sessions.count(),
        'total_bot_unique': bot_authenticated_count + bot_anonymous_count,
        
        # TỔNG QUAN
        'total_sessions': all_sessions.count(),
        'total_unique_all': authenticated_count + anonymous_count + bot_authenticated_count + bot_anonymous_count,
    }
    
    # Lấy danh sách chi tiết nếu cần
    if request.GET.get('detailed') == 'true':
        # Lấy thông tin chi tiết về HUMAN authenticated users
        human_authenticated_data = human_sessions.filter(user__isnull=False).select_related('user').values(
            'user__username',
            'ip_address',
            'device_type',
            'browser',
            'os',
            'last_activity'
        )
        
        # Group by user để hiển thị nhiều sessions
        users_data = {}
        for session in human_authenticated_data:
            username = session['user__username']
            if username not in users_data:
                users_data[username] = {
                    'username': username,
                    'sessions': []
                }
            users_data[username]['sessions'].append({
                'ip_address': session['ip_address'],
                'device_type': session['device_type'],
                'browser': session['browser'],
                'os': session['os'],
                'last_activity': session['last_activity'].isoformat(),
            })
        
        # Thông tin HUMAN anonymous users
        human_anonymous_data = human_sessions.filter(user__isnull=True).values(
            'ip_address',
            'device_type',
            'browser',
            'os',
            'last_activity'
        )
        
        # Thông tin BOT users - TÁCH RIÊNG
        bot_authenticated_data = bot_sessions.filter(user__isnull=False).select_related('user').values(
            'user__username',
            'ip_address',
            'user_agent',
            'browser',
            'os',
            'last_activity'
        )
        
        bot_users_data = {}
        for session in bot_authenticated_data:
            username = session['user__username']
            if username not in bot_users_data:
                bot_users_data[username] = {
                    'username': username,
                    'sessions': []
                }
            bot_users_data[username]['sessions'].append({
                'ip_address': session['ip_address'],
                'user_agent': session['user_agent'][:100],  # Limit length
                'browser': session['browser'],
                'os': session['os'],
                'last_activity': session['last_activity'].isoformat(),
            })
        
        # Thông tin BOT anonymous
        bot_anonymous_data = bot_sessions.filter(user__isnull=True).values(
            'ip_address',
            'user_agent',
            'browser',
            'os',
            'last_activity'
        )
        
        # Cắt ngắn user_agent cho bot anonymous để tránh response quá lớn
        for bot in bot_anonymous_data:
            if bot['user_agent']:
                bot['user_agent'] = bot['user_agent'][:100]
        
        data.update({
            # HUMAN DETAILS
            'human_authenticated_details': list(users_data.values()),
            'human_anonymous_details': list(human_anonymous_data),
            
            # BOT DETAILS - TÁCH RIÊNG
            'bot_authenticated_details': list(bot_users_data.values()),
            'bot_anonymous_details': list(bot_anonymous_data),
        })
    
    return JsonResponse(data) 