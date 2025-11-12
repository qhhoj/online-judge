#!/usr/bin/env python
"""
Script to fix FSO contest points by recalculating ContestSubmission.points
for all submissions in FSO contests.

Usage:
    python fix_fso_points.py <contest_key>
"""
import sys
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dmoj.settings')
django.setup()

from judge.models import Contest, ContestSubmission

def fix_fso_contest_points(contest_key):
    """Fix points for all submissions in an FSO contest."""
    try:
        contest = Contest.objects.get(key=contest_key)
    except Contest.DoesNotExist:
        print(f"Contest '{contest_key}' not found!")
        return False
    
    if contest.format_name != 'final_submission':
        print(f"Contest '{contest_key}' is not FSO format (format: {contest.format_name})")
        return False
    
    print(f"Fixing points for FSO contest: {contest.name} ({contest_key})")
    
    # Get all contest submissions
    submissions = ContestSubmission.objects.filter(
        participation__contest=contest
    ).select_related('submission', 'problem', 'participation')
    
    total = submissions.count()
    print(f"Found {total} submissions")
    
    updated = 0
    for cs in submissions:
        submission = cs.submission
        
        # Recalculate ContestSubmission.points using update_contest()
        try:
            submission.update_contest()
            updated += 1
            if updated % 10 == 0:
                print(f"  Updated {updated}/{total} submissions...")
        except Exception as e:
            print(f"  Error updating submission {submission.id}: {e}")
    
    print(f"✓ Updated {updated}/{total} submissions")
    print(f"✓ Participation scores have been recalculated")
    return True

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python fix_fso_points.py <contest_key>")
        sys.exit(1)
    
    contest_key = sys.argv[1]
    success = fix_fso_contest_points(contest_key)
    sys.exit(0 if success else 1)

