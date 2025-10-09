#!/usr/bin/env python3
"""
DMOJ User Activity Tracker Installation Script

This script helps automate the installation of the user activity tracker
into an existing DMOJ online judge system.
"""

import os
import sys
import shutil
import re
from pathlib import Path


def print_step(step_num, description):
    """Print installation step"""
    print(f"\n{'='*60}")
    print(f"STEP {step_num}: {description}")
    print(f"{'='*60}")


def check_dmoj_project(project_path):
    """Check if the path contains a valid DMOJ project"""
    required_files = ['manage.py', 'dmoj', 'judge']
    required_dirs = ['dmoj', 'judge', 'templates']
    
    for file in required_files:
        if not os.path.exists(os.path.join(project_path, file)):
            return False, f"Missing required file: {file}"
    
    for dir in required_dirs:
        if not os.path.isdir(os.path.join(project_path, dir)):
            return False, f"Missing required directory: {dir}"
    
    return True, "Valid DMOJ project found"


def copy_app_files(source_dir, project_path):
    """Copy user_activity app files to the project"""
    print("Copying user_activity app...")
    
    source_app = os.path.join(source_dir, 'user_activity')
    dest_app = os.path.join(project_path, 'user_activity')
    
    if os.path.exists(dest_app):
        print(f"Warning: {dest_app} already exists. Backing up...")
        shutil.move(dest_app, dest_app + '.backup')
    
    shutil.copytree(source_app, dest_app)
    print(f"✓ Copied user_activity app to {dest_app}")


def copy_templates(source_dir, project_path):
    """Copy template files to the project"""
    print("Copying template files...")
    
    source_templates = os.path.join(source_dir, 'templates')
    dest_templates = os.path.join(project_path, 'templates')
    
    # Copy admin templates
    admin_source = os.path.join(source_templates, 'admin', 'user_activity')
    admin_dest = os.path.join(dest_templates, 'admin', 'user_activity')
    
    os.makedirs(os.path.dirname(admin_dest), exist_ok=True)
    if os.path.exists(admin_dest):
        shutil.rmtree(admin_dest)
    shutil.copytree(admin_source, admin_dest)
    print(f"✓ Copied admin templates to {admin_dest}")
    
    # Copy user_activity templates
    user_source = os.path.join(source_templates, 'user_activity')
    user_dest = os.path.join(dest_templates, 'user_activity')
    
    if os.path.exists(user_dest):
        shutil.rmtree(user_dest)
    shutil.copytree(user_source, user_dest)
    print(f"✓ Copied user_activity templates to {user_dest}")


def update_settings(project_path):
    """Update Django settings to include the app and middleware"""
    settings_path = os.path.join(project_path, 'dmoj', 'settings.py')
    
    if not os.path.exists(settings_path):
        print(f"Warning: Could not find settings.py at {settings_path}")
        return False
    
    with open(settings_path, 'r') as f:
        content = f.read()
    
    # Add to INSTALLED_APPS
    if "'user_activity'," not in content:
        if 'INSTALLED_APPS' in content:
            # Find INSTALLED_APPS and add our app
            pattern = r'(INSTALLED_APPS\s*=\s*\[)(.*?)(\])'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                apps_content = match.group(2)
                if "'user_activity'," not in apps_content:
                    new_apps = match.group(1) + apps_content.rstrip() + "\n    'user_activity',\n" + match.group(3)
                    content = content.replace(match.group(0), new_apps)
                    print("✓ Added 'user_activity' to INSTALLED_APPS")
    
    # Add middleware
    if 'user_activity.middleware.UserActivityMiddleware' not in content:
        if 'MIDDLEWARE' in content:
            pattern = r'(MIDDLEWARE\s*=\s*\[)(.*?)(\])'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                middleware_content = match.group(2)
                if 'user_activity.middleware.UserActivityMiddleware' not in middleware_content:
                    new_middleware = match.group(1) + middleware_content.rstrip() + "\n    'user_activity.middleware.UserActivityMiddleware',\n" + match.group(3)
                    content = content.replace(match.group(0), new_middleware)
                    print("✓ Added UserActivityMiddleware to MIDDLEWARE")
    
    # Write back to file
    with open(settings_path, 'w') as f:
        f.write(content)
    
    return True


def update_urls(project_path):
    """Update main URLs to include user_activity URLs"""
    urls_path = os.path.join(project_path, 'dmoj', 'urls.py')
    
    if not os.path.exists(urls_path):
        print(f"Warning: Could not find urls.py at {urls_path}")
        return False
    
    with open(urls_path, 'r') as f:
        content = f.read()
    
    # Add the URL pattern
    url_pattern = "path('admin/user-activity/', include('user_activity.urls')),"
    
    if url_pattern not in content:
        # Find urlpatterns
        pattern = r'(urlpatterns\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            urls_content = match.group(2)
            new_urls = match.group(1) + urls_content.rstrip() + f"\n    {url_pattern}\n" + match.group(3)
            content = content.replace(match.group(0), new_urls)
            print("✓ Added user_activity URLs to urlpatterns")
        
        # Add import if not present
        if "from django.urls import path, include" not in content:
            if "from django.urls import" in content:
                content = content.replace(
                    "from django.urls import",
                    "from django.urls import path, include,"
                )
            else:
                content = "from django.urls import path, include\n" + content
    
    # Write back to file
    with open(urls_path, 'w') as f:
        f.write(content)
    
    return True


def create_migration_instructions(project_path):
    """Create instructions for database migration"""
    instructions = """
DATABASE MIGRATION INSTRUCTIONS
==============================

After running this installation script, you need to create and apply database migrations:

1. Create migrations for the user_activity app:
   python manage.py makemigrations user_activity

2. Apply the migrations:
   python manage.py migrate

3. (Optional) Create permission for user activity viewing:
   python manage.py shell
   
   Then run:
   from django.contrib.auth.models import Permission
   from django.contrib.contenttypes.models import ContentType
   from user_activity.models import UserActivity
   
   content_type = ContentType.objects.get_for_model(UserActivity)
   permission, created = Permission.objects.get_or_create(
       codename='can_see_user_activity',
       name='Can see user activity',
       content_type=content_type,
   )
   print(f"Permission {'created' if created else 'already exists'}")

4. Restart your Django application

5. Access the user activity dashboard at:
   http://yoursite.com/admin/user-activity/active-users/

NOTES:
- Make sure you have installed the required dependencies from requirements.txt
- The middleware will start tracking activities immediately after restart
- Only users with appropriate permissions can access the activity views

"""
    
    instructions_path = os.path.join(project_path, 'USER_ACTIVITY_SETUP.txt')
    with open(instructions_path, 'w') as f:
        f.write(instructions)
    
    print(f"✓ Created setup instructions at {instructions_path}")
    return instructions


def main():
    """Main installation function"""
    print("DMOJ User Activity Tracker Installation")
    print("======================================")
    
    # Check if running from correct directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    module_dir = os.path.dirname(script_dir)
    
    if not os.path.exists(os.path.join(module_dir, 'user_activity')):
        print("Error: user_activity directory not found!")
        print("Make sure you're running this script from the installation directory")
        sys.exit(1)
    
    # Get project path
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
    else:
        project_path = input("Enter the path to your DMOJ project directory: ")
    
    project_path = os.path.abspath(project_path)
    
    print_step(1, "Validating DMOJ Project")
    valid, message = check_dmoj_project(project_path)
    if not valid:
        print(f"Error: {message}")
        print("Please make sure you're pointing to a valid DMOJ project directory")
        sys.exit(1)
    print(f"✓ {message}")
    
    print_step(2, "Copying Application Files")
    copy_app_files(module_dir, project_path)
    
    print_step(3, "Copying Template Files")
    copy_templates(module_dir, project_path)
    
    print_step(4, "Updating Django Settings")
    if update_settings(project_path):
        print("✓ Settings updated successfully")
    else:
        print("⚠ Could not automatically update settings. Please add manually.")
    
    print_step(5, "Updating URL Configuration")
    if update_urls(project_path):
        print("✓ URLs updated successfully")
    else:
        print("⚠ Could not automatically update URLs. Please add manually.")
    
    print_step(6, "Creating Setup Instructions")
    instructions = create_migration_instructions(project_path)
    
    print_step(7, "Installation Complete!")
    print("✓ User Activity Tracker has been installed successfully!")
    print("\nNext steps:")
    print("1. Install dependencies: pip install -r requirements.txt")
    print("2. Run migrations: python manage.py makemigrations user_activity && python manage.py migrate")
    print("3. Restart your Django application")
    print("4. Check USER_ACTIVITY_SETUP.txt for detailed instructions")
    
    print(f"\nInstallation summary:")
    print(f"- App installed in: {os.path.join(project_path, 'user_activity')}")
    print(f"- Templates copied to: {os.path.join(project_path, 'templates')}")
    print(f"- Settings updated: {os.path.join(project_path, 'dmoj', 'settings.py')}")
    print(f"- URLs updated: {os.path.join(project_path, 'dmoj', 'urls.py')}")


if __name__ == "__main__":
    main() 