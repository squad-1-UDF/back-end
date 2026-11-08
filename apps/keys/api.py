from typing import ClassVar

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.keys.serializers import KeySerializer


class KeyListCreateView(APIView):
    permission_classes: ClassVar = [IsAuthenticated]

    def get(self, request):
        return Response(
            {"detail": "Listagem de chaves ainda não implementada."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def post(self, request):
        serializer = KeySerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"detail": "Cadastro de chaves ainda não implementado."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class KeyDetailView(APIView):
    permission_classes: ClassVar = [IsAuthenticated]

    def get(self, request, key_id):
        return Response(
            {"detail": "Consulta de chave ainda não implementada."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def patch(self, request, key_id):
        serializer = KeySerializer(
            data=request.data,
            partial=True,
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"detail": "Atualização de chave ainda não implementada."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
