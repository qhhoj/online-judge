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
def user_activity_detail_safe(request, username):
    """Safe version - View để xem chi tiết hoạt động của một người dùng"""
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return render(request, 'user_activity/404.html', status=404)
    
    # Lấy filter parameters
    days = request.GET.get('days', '30')
    try:
        days = int(days)
    except ValueError:
        days = 30
    
    # Lấy TẤT CẢ hoạt động trong khoảng thời gian
    time_ago = timezone.now() - timedelta(days=days)
    activities = UserActivity.objects.filter(
        user=user,
        timestamp__gte=time_ago
    ).order_by('-timestamp')
    
    # Phân trang cho activities
    paginator = Paginator(activities, 100)  # 100 per page
    page = request.GET.get('page', 1)
    activities_page = paginator.get_page(page)
    
    # Lấy tất cả các phiên truy cập
    all_sessions = UserSession.objects.filter(user=user).order_by('-last_activity')
    active_sessions = all_sessions.filter(
        last_activity__gte=timezone.now() - timedelta(minutes=30),
        is_active=True
    )
    
    # Safe stats without JSON serialization issues
    daily_stats_json = '[]'  # Empty for now to avoid any JSON issues
    
    # Thống kê theo IP
    ip_stats = UserActivity.objects.filter(
        user=user,
        timestamp__gte=time_ago
    ).values('ip_address').annotate(count=Count('id')).order_by('-count')[:10]
    
    # Thống kê theo path được truy cập nhiều nhất
    path_stats = UserActivity.objects.filter(
        user=user,
        timestamp__gte=time_ago
    ).values('path').annotate(count=Count('id')).order_by('-count')[:20]
    
    context = {
        'target_user': user,
        'activities': activities_page,
        'all_sessions': all_sessions,
        'active_sessions': active_sessions,
        'active_session_count': active_sessions.count(),
        'total_session_count': all_sessions.count(),
        'total_activities': activities.count(),
        'daily_stats': daily_stats_json,
        'ip_stats': ip_stats,
        'path_stats': path_stats,
        'days_filter': days,
    }
    
    return render(request, 'user_activity/user_detail.html', context) 