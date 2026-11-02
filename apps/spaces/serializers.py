from rest_framework import serializers


class SpaceSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50, allow_blank=False, trim_whitespace=True,)
    kind = serializers.ChoiceField(choices=["room", "laboratory"],)