from typing import ClassVar

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.spaces.serializers import SpaceSerializer


class SpaceListCreateView(APIView):
    permission_classes: ClassVar = [IsAuthenticated]

    def get(self, request):
        return Response(
            {"detail": "Listagem de salas ainda não implementada."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    def post(self, request):
        serializer = SpaceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"detail": "Cadastro ainda não disponível."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class SpaceDetailView(APIView):
    permission_classes: ClassVar = [IsAuthenticated]

    def get(self, request, space_id):
        return Response(
            {"detail": "Consulta de espaço ainda não implementada."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    def patch(self, request, space_id):
        return Response(
            {"detail": "Atualização de espaço ainda não implementada."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
