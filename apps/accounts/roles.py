"""Papéis de UC002 derivados do ``auth.User`` nativo, sem tabela própria.

- ``admin``: superusuário ou membro do grupo ``admin``;
- ``employee``: ``is_staff`` sem ser admin;
- ``student``: os demais.
"""

from django.contrib.auth.models import Group
from django.db.models import Exists, OuterRef, Q

ADMIN_GROUP = "admin"
ADMIN = "admin"
EMPLOYEE = "employee"
STUDENT = "student"
ROLES = (ADMIN, EMPLOYEE, STUDENT)
STAFF_ROLES = (ADMIN, EMPLOYEE)


def admin_group():
    """Grupo ``admin``; a migration o cria, mas o código não depende dela."""
    group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
    return group


def is_admin_member(user):
    annotated = getattr(user, "in_admin_group", None)
    if annotated is not None:
        return annotated
    return user.groups.filter(name=ADMIN_GROUP).exists()


def get_role(user):
    if user.is_superuser or is_admin_member(user):
        return ADMIN
    if user.is_staff:
        return EMPLOYEE
    return STUDENT


def with_admin_flag(queryset):
    """Anota ``in_admin_group`` para calcular o papel sem uma consulta por linha."""
    membership = queryset.model.groups.through.objects.filter(
        user_id=OuterRef("pk"), group__name=ADMIN_GROUP
    )
    return queryset.annotate(in_admin_group=Exists(membership))


def role_filter(role):
    """Filtro equivalente a ``get_role`` para querysets anotados."""
    admin = Q(is_superuser=True) | Q(in_admin_group=True)
    if role == ADMIN:
        return admin
    if role == EMPLOYEE:
        return Q(is_staff=True) & ~admin
    return Q(is_staff=False) & ~admin


def apply_role(user, role):
    """Grava o papel; o chamador salva ``is_staff`` e a transação."""
    group = admin_group()
    if role == ADMIN:
        user.groups.add(group)
    else:
        user.groups.remove(group)
    user.is_staff = role in STAFF_ROLES
    # Invalida a anotação de leitura para refletir o novo vínculo.
    user.in_admin_group = role == ADMIN
