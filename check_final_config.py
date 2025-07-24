#!/usr/bin/env python3
"""
Script kiểm tra config hoàn chỉnh cho User Activity Tracking System
"""

import os
import sys

def print_section(title):
    print("\n" + "="*60)
    print(f"🔍 {title}")
    print("="*60)

def check_file_exists(filepath, description):
    exists = os.path.exists(filepath)
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {filepath}")
    return exists

def check_content_in_file(filepath, search_text, description):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            found = search_text in content
            status = "✅" if found else "❌"
            print(f"{status} {description}")
            return found
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        return False
    except Exception as e:
        print(f"⚠️ Error reading {filepath}: {e}")
        return False

def main():
    print("🚀 FINAL CONFIG CHECKER - User Activity Tracking")
    print("Phiên bản: 2.0")
    
    all_good = True
    
    # 1. File Structure Check
    print_section("KIỂM TRA CẤU TRÚC FILES")
    
    required_files = [
        ('judge/middlewares/user_activity.py', 'Middleware file'),
        ('judge/models/user_activity.py', 'Models file'),
        ('judge/views/user_activity.py', 'Views file'),
        ('judge/admin/user_activity.py', 'Admin file'),
        ('judge/legacy_middleware.py', 'Legacy middleware (compatibility)'),
        ('templates/admin/user_activity/active_users.html', 'Active users template'),
        ('templates/admin/user_activity/user_detail.html', 'User detail template'),
        ('templates/admin/user_activity/all_logs.html', 'All logs template'),
        ('templates/admin/user_activity/404.html', '404 template'),
    ]
    
    for filepath, description in required_files:
        if not check_file_exists(filepath, description):
            all_good = False
    
    # 2. Settings Check
    print_section("KIỂM TRA SETTINGS.PY")
    
    settings_checks = [
        ('judge.middlewares.user_activity.UserActivityMiddleware', 'Middleware trong MIDDLEWARE'),
    ]
    
    # Check requirements.txt separately
    if check_content_in_file('requirements.txt', 'user-agents', 'Package user-agents trong requirements.txt'):
        print("✅ Package user-agents trong requirements.txt")
    else:
        print("❌ Package user-agents trong requirements.txt")
        all_good = False
    
    for search_text, description in settings_checks:
        if not check_content_in_file('dmoj/settings.py', search_text, description):
            all_good = False
    
    # 3. Models Import Check
    print_section("KIỂM TRA MODELS IMPORT")
    
    models_checks = [
        ('from judge.models.user_activity import UserActivity, UserSession', 'Models import trong __init__.py'),
    ]
    
    for search_text, description in models_checks:
        if not check_content_in_file('judge/models/__init__.py', search_text, description):
            all_good = False
    
    # 4. Admin Import Check
    print_section("KIỂM TRA ADMIN IMPORT")
    
    admin_checks = [
        ('from judge.admin.user_activity import UserActivityAdmin, UserSessionAdmin', 'Admin import'),
        ('admin.site.register(UserActivity, UserActivityAdmin)', 'UserActivity registration'),
        ('admin.site.register(UserSession, UserSessionAdmin)', 'UserSession registration'),
    ]
    
    for search_text, description in admin_checks:
        if not check_content_in_file('judge/admin/__init__.py', search_text, description):
            all_good = False
    
    # 5. URLs Check
    print_section("KIỂM TRA URLS")
    
    url_checks = [
        ('user_activity', 'Import user_activity views'),
        ('admin/user-activity/', 'User activity URL patterns'),
        ('active_users_view', 'Active users view'),
        ('user_activity_detail', 'User detail view'),
        ('all_logs_view', 'All logs view'),
        ('export_logs', 'Export logs view'),
        ('delete_user_logs', 'Delete user logs view'),
        ('delete_anonymous_logs', 'Delete anonymous logs view'),
        ('active_users_api', 'Active users API'),
    ]
    
    for search_text, description in url_checks:
        if not check_content_in_file('dmoj/urls.py', search_text, description):
            all_good = False
    
    # 6. Legacy Middleware Check
    print_section("KIỂM TRA LEGACY MIDDLEWARE")
    
    legacy_checks = [
        ('from .middleware import', 'Import từ middleware.py'),
        ('ShortCircuitMiddleware', 'ShortCircuitMiddleware'),
        ('DMOJLoginMiddleware', 'DMOJLoginMiddleware'),
        ('ContestMiddleware', 'ContestMiddleware'),
    ]
    
    for search_text, description in legacy_checks:
        if not check_content_in_file('judge/legacy_middleware.py', search_text, description):
            all_good = False
    
    # 7. Naming Conflicts Check
    print_section("KIỂM TRA NAMING CONFLICTS")
    
    # Check no middleware/ folder exists
    if os.path.exists('judge/middleware'):
        print("❌ CONFLICT: judge/middleware/ folder vẫn tồn tại!")
        print("   💡 Fix: Xóa hoặc đổi tên folder này")
        all_good = False
    else:
        print("✅ Không có conflict middleware/ vs middleware.py")
    
    # Check middlewares/ folder exists
    if os.path.exists('judge/middlewares'):
        print("✅ Folder judge/middlewares/ tồn tại")
    else:
        print("❌ Folder judge/middlewares/ không tồn tại!")
        all_good = False
    
    # 8. Template Structure Check
    print_section("KIỂM TRA TEMPLATES")
    
    template_dir = 'templates/admin/user_activity'
    if os.path.exists(template_dir):
        templates = os.listdir(template_dir)
        required_templates = ['active_users.html', 'user_detail.html', 'all_logs.html', '404.html']
        
        for template in required_templates:
            if template in templates:
                print(f"✅ Template: {template}")
            else:
                print(f"❌ Missing template: {template}")
                all_good = False
    else:
        print(f"❌ Template directory không tồn tại: {template_dir}")
        all_good = False
    
    # 9. Final Summary
    print_section("KẾT QUẢ TỔNG KẾT")
    
    if all_good:
        print("🎉 TẤT CẢ CONFIG ĐÚNG!")
        print("✅ System sẵn sàng deploy!")
        print("\n📋 NEXT STEPS:")
        print("1. python manage.py makemigrations judge")
        print("2. python manage.py migrate") 
        print("3. Cấp quyền 'can_see_user_activity' cho admin users")
        print("4. Access: /admin/user-activity/active-users/")
        sys.exit(0)
    else:
        print("❌ CÒN LỖI CẦN FIX!")
        print("⚠️ Kiểm tra lại các mục bị ❌ ở trên")
        print("\n🔧 COMMON FIXES:")
        print("- Chạy migrations: python manage.py makemigrations judge")
        print("- Kiểm tra imports trong __init__.py files")
        print("- Tạo thiếu templates") 
        print("- Fix URLs patterns")
        sys.exit(1)

if __name__ == "__main__":
    main() 