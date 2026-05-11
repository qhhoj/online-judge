from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext as _

from judge.models import Problem


def get_problem_single_organization(problem):
    if not problem.is_organization_private:
        return None

    org_ids = list(problem.organizations.values_list('id', flat=True))
    if len(org_ids) != 1:
        return None

    return problem.organizations.get(id=org_ids[0])


def is_organization_admin(user, organization):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm('judge.edit_all_organization'):
        return True
    return organization.admins.filter(pk=user.profile.pk).exists()


def validate_mirror_source_for_target(user, source, target_problem=None, target_org=None):
    if source is None:
        return

    if target_problem is not None and target_problem.pk and source.pk == target_problem.pk:
        raise ValidationError(_('A problem cannot mirror itself.'))

    if target_org is None and target_problem is not None:
        target_org = get_problem_single_organization(target_problem)
        if target_problem.is_organization_private and target_org is None:
            raise ValidationError(_('Organization-private problems must belong to exactly one organization to use mirroring.'))

    if target_org is not None and not is_organization_admin(user, target_org):
        raise ValidationError(_('Only organization admins can configure mirroring for organization-private problems.'))

    if source.is_organization_private:
        source_org = get_problem_single_organization(source)
        if source_org is None:
            raise ValidationError(_('Only organization-private problems belonging to exactly one organization can be mirrored.'))

        if target_org is None:
            raise ValidationError(_('Organization-private source problems can only be mirrored inside the same organization.'))

        if source_org.id != target_org.id:
            raise ValidationError(_('Mirroring across organizations is not allowed.'))

        if not is_organization_admin(user, target_org):
            raise ValidationError(_('Only organization admins can mirror organization-private problems.'))

        return

    if source.is_public and not source.is_organization_private:
        return

    raise ValidationError(_('Only public problems or same-organization private problems can be mirrored.'))


def resolve_mirror_root_id(mirror_of_id, current_problem_id=None):
    if not mirror_of_id:
        return None

    seen = set()
    if current_problem_id is not None:
        seen.add(current_problem_id)

    current_id = mirror_of_id
    while current_id is not None:
        if current_id in seen:
            raise ValidationError(_('Mirror relationship cannot contain cycles.'))
        seen.add(current_id)

        row = Problem.objects.filter(pk=current_id).values('id', 'mirror_of_id', 'mirror_root_id').first()
        if row is None:
            raise ValidationError(_('Mirror source problem does not exist.'))

        if row['mirror_of_id'] is None:
            return row['id']

        if row['mirror_root_id'] and row['mirror_root_id'] != row['id']:
            if row['mirror_root_id'] in seen:
                raise ValidationError(_('Mirror relationship cannot contain cycles.'))
            return row['mirror_root_id']

        current_id = row['mirror_of_id']

    return None


def rebuild_mirror_descendants(problem_id):
    queue = [problem_id]
    visited = set()

    while queue:
        parent_id = queue.pop(0)
        if parent_id in visited:
            continue
        visited.add(parent_id)

        children = list(Problem.objects.filter(mirror_of_id=parent_id))
        for child in children:
            root_id = resolve_mirror_root_id(child.mirror_of_id, current_problem_id=child.id)
            if child.mirror_root_id != root_id:
                Problem.objects.filter(pk=child.id).update(mirror_root_id=root_id)
            queue.append(child.id)


def sync_mirror_archive_for_problem(problem, bootstrap_cases_if_empty=False, heal_missing_files=False,
                                    force_regenerate=False):
    # Mirror archives are resolved by judge-side root routing.
    # Keep this helper for backward compatibility with existing call sites.
    return False


def sync_mirror_archives_for_root(root_problem):
    changed = 0
    mirrors = Problem.objects.filter(mirror_root_id=root_problem.id).exclude(pk=root_problem.id)
    for mirror in mirrors:
        if sync_mirror_archive_for_problem(
            mirror, bootstrap_cases_if_empty=False, heal_missing_files=True, force_regenerate=True,
        ):
            changed += 1
    return changed


def get_mirrorable_source_queryset(user, target_problem=None, target_org=None):
    if user is None:
        return Problem.objects.none()

    queryset = Problem.get_visible_problems(user)

    if target_problem is not None and target_problem.pk:
        queryset = queryset.exclude(pk=target_problem.pk)

    public_q = Q(is_public=True, is_organization_private=False)

    if target_org is None and target_problem is not None:
        target_org = get_problem_single_organization(target_problem)

    if target_org is None:
        return queryset.filter(public_q)

    if not is_organization_admin(user, target_org):
        return Problem.objects.none()

    org_q = Q(is_organization_private=True, organizations=target_org)
    return queryset.filter(public_q | org_q).distinct()
