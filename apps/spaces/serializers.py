from rest_framework import serializers


class StrictBooleanField(serializers.BooleanField):
    """Aceita somente true/false do JSON, sem conversões de texto ou número."""

    def to_internal_value(self, data):
        if type(data) is not bool:
            raise serializers.ValidationError("Informe true ou false.")
        return data


class StrictCapacityField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:  # JSON bool ou texto não é capacidade
            raise serializers.ValidationError("Informe um inteiro.")
        return super().to_internal_value(data)


class SpaceSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(
        max_length=50,
        allow_blank=False,
        trim_whitespace=True,
    )
    kind = serializers.ChoiceField(
        choices=["room", "laboratory"],
    )
    name = serializers.CharField(
        max_length=120, allow_blank=True, trim_whitespace=True, required=False
    )
    capacity = StrictCapacityField(
        min_value=1, max_value=2**31 - 1, allow_null=True, required=False
    )
    location = serializers.CharField(
        max_length=120, allow_blank=True, trim_whitespace=True, required=False
    )
    is_active = StrictBooleanField(required=False)


class SpaceFilters(serializers.Serializer):
    is_active = serializers.ChoiceField(choices=["true", "false"], required=False)
    kind = serializers.ChoiceField(choices=["room", "laboratory"], required=False)

    def to_internal_value(self, data):
        if set(data) - {"is_active", "kind"} or any(
            len(data.getlist(field)) != 1 for field in data
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["Filtros inválidos ou duplicados."]}
            )
        return super().to_internal_value(data)
