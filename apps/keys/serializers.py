from rest_framework import serializers


class KeySerializer(serializers.Serializer):
    space_id = serializers.CharField(
        max_length=50,
        allow_blank=False,
        trim_whitespace=True,
    )
