#!/usr/bin/env python3
"""
Script cấp quyền user activity tracking cho admin users
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dmoj.settings')
django.setup()

from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from judge.models import Profile

def create_permission():
    """Tạo permission nếu chưa có"""
    try:
        content_type = ContentType.objects.get_for_model(Profile)
        
        # Try to get existing permission first
        try:
            permission = Permission.objects.get(
                codename='can_see_user_activity',
                content_type=content_type,
            )
            print("✅ Permission 'can_see_user_activity' đã tồn tại!")
            return permission
        except Permission.DoesNotExist:
            # Create new permission
            permission = Permission.objects.create(
                codename='can_see_user_activity',
                name='Can see user activity',
                content_type=content_type,
            )
            print("✅ Tạo permission 'can_see_user_activity' thành công!")
            return permission
            
    except Exception as e:
        print(f"❌ Lỗi tạo permission: {e}")
        
        # Try alternative approach - get any permission with this codename
        try:
            permission = Permission.objects.filter(codename='can_see_user_activity').first()
            if permission:
                print("✅ Tìm thấy permission existing, sử dụng permission đó!")
                return permission
        except:
            pass
            
        return None

def grant_permission_to_user(username, permission):
    """Cấp quyền cho user cụ thể"""
    try:
        user = User.objects.get(username=username)
        user.user_permissions.add(permission)
        print(f"✅ Cấp quyền cho user '{username}' thành công!")
        return True
    except User.DoesNotExist:
        print(f"❌ User '{username}' không tồn tại!")
        return False
    except Exception as e:
        print(f"❌ Lỗi cấp quyền cho '{username}': {e}")
        return False

def grant_permission_to_superusers(permission):
    """Cấp quyền cho tất cả superusers"""
    try:
        superusers = User.objects.filter(is_superuser=True)
        count = 0
        
        for user in superusers:
            if not user.user_permissions.filter(id=permission.id).exists():
                user.user_permissions.add(permission)
                print(f"✅ Cấp quyền cho superuser '{user.username}'")
                count += 1
            else:
                print(f"⚠️ Superuser '{user.username}' đã có quyền")
        
        if count > 0:
            print(f"✅ Cấp quyền cho {count} superusers thành công!")
        else:
            print("ℹ️ Tất cả superusers đã có quyền!")
            
        return True
    except Exception as e:
        print(f"❌ Lỗi cấp quyền cho superusers: {e}")
        return False

def list_users_with_permission(permission):
    """Liệt kê users có quyền"""
    try:
        users = User.objects.filter(user_permissions=permission)
        
        print("\n📋 USERS CÓ QUYỀN USER ACTIVITY:")
        print("-" * 40)
        
        if users.exists():
            for user in users:
                status = "🟢 Active" if user.is_active else "🔴 Inactive"
                super_status = "👑 Superuser" if user.is_superuser else "👤 Regular"
                print(f"  {user.username} - {status} - {super_status}")
        else:
            print("  (Chưa có user nào được cấp quyền)")
            
        # Also check superusers (they might have permission through is_superuser)
        superusers = User.objects.filter(is_superuser=True)
        if superusers.exists():
            print("\n👑 SUPERUSERS (có quyền tự động):")
            for user in superusers:
                if not users.filter(id=user.id).exists():
                    status = "🟢 Active" if user.is_active else "🔴 Inactive"
                    print(f"  {user.username} - {status}")
                    
    except Exception as e:
        print(f"❌ Lỗi liệt kê users: {e}")

def main():
    print("🔑 GRANT USER ACTIVITY PERMISSIONS")
    print("=" * 50)
    
    # 1. Tạo permission
    permission = create_permission()
    if not permission:
        print("❌ Không thể tạo permission!")
        sys.exit(1)
    
    # 2. Parse arguments
    if len(sys.argv) == 1:
        print("\nUsage:")
        print("  python grant_user_activity_permission.py --all-superusers")
        print("  python grant_user_activity_permission.py --user <username>")
        print("  python grant_user_activity_permission.py --list")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == '--all-superusers':
        print("\n🔄 Cấp quyền cho tất cả superusers...")
        grant_permission_to_superusers(permission)
        
    elif action == '--user':
        if len(sys.argv) < 3:
            print("❌ Cần nhập username! Ví dụ: --user admin")
            sys.exit(1)
        username = sys.argv[2]
        print(f"\n🔄 Cấp quyền cho user '{username}'...")
        grant_permission_to_user(username, permission)
        
    elif action == '--list':
        print("\n📋 Liệt kê users có quyền...")
        list_users_with_permission(permission)
        
    else:
        print(f"❌ Action không hợp lệ: {action}")
        sys.exit(1)
    
    # 3. Show final status
    print("\n" + "=" * 50)
    list_users_with_permission(permission)
    
    print("\n🎯 TRUY CẬP PANEL:")
    print("   URL: /admin/user-activity/active-users/")
    print("   Cần đăng nhập với user có quyền!")

if __name__ == "__main__":
    main() 