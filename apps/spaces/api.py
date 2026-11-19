from typing import ClassVar

from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from psycopg.errors import UniqueViolation
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.spaces.models import Space
from apps.spaces.serializers import SpaceSerializer


def is_duplicate_code(error):
    cause = error.__cause__
    return isinstance(cause, UniqueViolation) and (
        cause.diag.constraint_name == "spaces_space_code_key"
    )


def duplicate_code_response():
    return Response(
        {"code": ["Já existe um espaço com este código."]},
        status=status.HTTP_409_CONFLICT,
    )


def get_space(space_id):
    if space_id > 2**63 - 1:
        raise Http404
    return get_object_or_404(Space, pk=space_id)


class SpaceListCreateView(APIView):
    permission_classes: ClassVar = [IsAuthenticated]

    def get(self, request):
        spaces = Space.objects.order_by("id")
        return Response(SpaceSerializer(spaces, many=True).data)

    def post(self, request):
        serializer = SpaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                space = Space.objects.create(**serializer.validated_data)
        except IntegrityError as error:
            if not is_duplicate_code(error):
                raise
            return duplicate_code_response()
        return Response(
            SpaceSerializer(space).data,
            status=status.HTTP_201_CREATED,
        )


class SpaceDetailView(APIView):
    permission_classes: ClassVar = [IsAuthenticated]

    def get(self, request, space_id):
        space = get_space(space_id)
        return Response(SpaceSerializer(space).data)

    def patch(self, request, space_id):
        space = get_space(space_id)
        serializer = SpaceSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(space, field, value)
        try:
            with transaction.atomic():
                space.save(update_fields=list(serializer.validated_data))
        except IntegrityError as error:
            if not is_duplicate_code(error):
                raise
            return duplicate_code_response()
        return Response(SpaceSerializer(space).data)
