TRANSFORM_NAMES = [
    "trim",
    "upper",
    "lower",
    "digits_only",
    "regex_extract",
    "date_parse",
    "split",
    "map",
    "null_if",
    "constant",
]

CONFIG_SCHEMA = {
    "type": "object",
    "required": [
        "config_version",
        "source",
        "reader",
        "record_id",
        "observed_at",
        "fields",
        "unmapped",
    ],
    "properties": {
        "config_version": {"type": "string"},
        "source": {
            "type": "object",
            "required": ["source_id", "licence", "source_reliability"],
            "properties": {
                "source_id": {"type": "string"},
                "licence": {"type": "string"},
                "source_reliability": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "reader": {
            "type": "object",
            "required": ["format"],
            "properties": {"format": {"enum": ["csv", "xlsx", "json", "xml"]}},
        },
        "record_id": {
            "type": "object",
            "required": ["strategy", "how"],
            "properties": {
                "strategy": {"enum": ["field", "hash"]},
                "field": {"type": "string"},
                "how": {"type": "string"},
            },
        },
        "observed_at": {
            "type": "object",
            "required": ["strategy"],
            "properties": {
                "strategy": {"enum": ["constant", "field"]},
                "value": {"type": "string"},
                "field": {"type": "string"},
            },
        },
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "source_field",
                    "canonical_field",
                    "field_confidence",
                    "rationale",
                ],
                "properties": {
                    "source_field": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ]
                    },
                    "canonical_field": {"type": "string"},
                    "transforms": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {"name": {"enum": TRANSFORM_NAMES}},
                        },
                    },
                    "field_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                },
            },
        },
        "unmapped": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source_field", "reason"],
                "properties": {
                    "source_field": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}
