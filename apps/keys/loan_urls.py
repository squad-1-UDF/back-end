"""Rotas das UCs 005–008, separadas do futuro CRUD de chaves."""

from django.urls import path

from apps.keys.loan_views import (
    CheckoutView,
    LoanAvailabilityView,
    MovementsView,
    ReturnView,
)

urlpatterns = [
    path("key-loans/", CheckoutView.as_view(), name="key-loans-checkout"),
    path(
        "key-loans/<int:loan_id>/return/", ReturnView.as_view(), name="key-loans-return"
    ),
    path(
        "keys/<int:key_id>/loan-availability/",
        LoanAvailabilityView.as_view(),
        name="key-loan-availability",
    ),
    path(
        "keys/<int:key_id>/movements/",
        MovementsView.as_view(),
        name="key-movements",
    ),
]
