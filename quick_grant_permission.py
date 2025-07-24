#!/usr/bin/env python3
"""
Quick script để cấp quyền user activity mà không cần tạo permission
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dmoj.settings')
django.setup()

from django.contrib.auth.models import User, Permission

def get_permission():
    """Lấy permission đã có sẵn"""
    try:
        # Try multiple ways to get the permission
        permission = Permission.objects.filter(codename='can_see_user_activity').first()
        if permission:
            print(f"✅ Tìm thấy permission: {permission.name}")
            return permission
        
        # If not found, list all available permissions related to profile
        print("🔍 Không tìm thấy permission 'can_see_user_activity'")
        print("📋 Available permissions liên quan đến judge/profile:")
        
        permissions = Permission.objects.filter(content_type__app_label='judge').order_by('codename')
        for perm in permissions:
            print(f"   - {perm.codename}: {perm.name}")
        
        return None
        
    except Exception as e:
        print(f"❌ Lỗi lấy permission: {e}")
        return None

def grant_to_user(username):
    """Cấp quyền cho user cụ thể"""
    permission = get_permission()
    if not permission:
        return False
    
    try:
        user = User.objects.get(username=username)
        
        # Check if user already has permission
        if user.user_permissions.filter(id=permission.id).exists():
            print(f"⚠️ User '{username}' đã có quyền này rồi!")
            return True
        
        user.user_permissions.add(permission)
        print(f"✅ Cấp quyền cho user '{username}' thành công!")
        return True
        
    except User.DoesNotExist:
        print(f"❌ User '{username}' không tồn tại!")
        return False
    except Exception as e:
        print(f"❌ Lỗi cấp quyền: {e}")
        return False

def grant_to_all_superusers():
    """Cấp quyền cho tất cả superusers"""
    permission = get_permission()
    if not permission:
        return False
    
    try:
        superusers = User.objects.filter(is_superuser=True, is_active=True)
        
        if not superusers.exists():
            print("⚠️ Không tìm thấy superuser nào!")
            return False
        
        count = 0
        for user in superusers:
            if not user.user_permissions.filter(id=permission.id).exists():
                user.user_permissions.add(permission)
                print(f"✅ Cấp quyền cho superuser: {user.username}")
                count += 1
            else:
                print(f"⚠️ Superuser '{user.username}' đã có quyền")
        
        if count > 0:
            print(f"🎉 Hoàn thành! Cấp quyền cho {count} superusers")
        
        return True
        
    except Exception as e:
        print(f"❌ Lỗi cấp quyền cho superusers: {e}")
        return False

def list_users_with_permission():
    """Liệt kê users có quyền"""
    permission = get_permission()
    if not permission:
        return
    
    try:
        users = User.objects.filter(user_permissions=permission, is_active=True)
        
        print(f"\n📋 USERS CÓ QUYỀN '{permission.name}':")
        print("-" * 50)
        
        if users.exists():
            for user in users:
                status = "👑 Superuser" if user.is_superuser else "👤 Regular"
                print(f"  ✅ {user.username} ({status})")
        else:
            print("  (Chưa có user nào)")
        
        # Also show superusers
        superusers = User.objects.filter(is_superuser=True, is_active=True)
        if superusers.exists():
            print(f"\n👑 TẤT CẢ SUPERUSERS (có thể có quyền admin):")
            for user in superusers:
                has_explicit = users.filter(id=user.id).exists()
                marker = "✅" if has_explicit else "❓"
                print(f"  {marker} {user.username}")
        
    except Exception as e:
        print(f"❌ Lỗi liệt kê users: {e}")

def main():
    print("🚀 QUICK PERMISSION GRANT")
    print("=" * 40)
    
    if len(sys.argv) == 1:
        print("Usage:")
        print("  python3 quick_grant_permission.py <username>")
        print("  python3 quick_grant_permission.py --all-superusers")
        print("  python3 quick_grant_permission.py --list")
        print("  python3 quick_grant_permission.py --check")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == '--all-superusers':
        print("🔄 Cấp quyền cho tất cả superusers...")
        grant_to_all_superusers()
        
    elif action == '--list':
        print("📋 Liệt kê users có quyền...")
        list_users_with_permission()
        
    elif action == '--check':
        print("🔍 Kiểm tra permission...")
        get_permission()
        list_users_with_permission()
        
    else:
        # Treat as username
        username = action
        print(f"🔄 Cấp quyền cho user: {username}")
        grant_to_user(username)
    
    print("\n" + "=" * 40)
    print("🎯 TRUY CẬP PANEL:")
    print("   URL: /admin/user-activity/active-users/")
    print("   Yêu cầu login với user có quyền!")

if __name__ == "__main__":
    main() 