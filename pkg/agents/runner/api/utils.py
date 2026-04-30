"""Utility functions for MCP runner."""

def filter_schema_for_gemini(schema):
  """Filters the schema to only include fields supported by Gemini API."""
  if isinstance(schema, bool):
    return {} if schema else None
  if not isinstance(schema, dict):
    return schema

  supported_fields = {
      "type",
      "format",
      "description",
      "nullable",
      "enum",
      "items",
      "properties",
      "required",
      "minItems",
      "maxItems",
      "minimum",
      "maximum",
      "anyOf",
      "oneOf",
      "$defs",
      "$ref",
  }

  schema_field_names = ("items",)
  list_schema_field_names = ("anyOf", "any_of", "oneOf", "one_of")
  dict_schema_field_names = ("properties", "defs", "$defs")

  filtered_schema = {}
  for field_name, field_value in schema.items():
    if field_name == "type":
      if isinstance(field_value, list):
        if "null" in field_value:
          filtered_schema["nullable"] = True
          non_null_types = [t for t in field_value if t != "null"]
          if non_null_types:
            filtered_schema["type"] = non_null_types[0].upper()
          else:
            filtered_schema["type"] = "NULL"
        elif field_value:
          filtered_schema["type"] = field_value[0].upper()
      elif isinstance(field_value, str):
        filtered_schema["type"] = field_value.upper()
    elif field_name in schema_field_names:
      filtered_value = filter_schema_for_gemini(field_value)
      if filtered_value is not None:
        filtered_schema[field_name] = filtered_value
    elif field_name in list_schema_field_names:
      if isinstance(field_value, list):
        filtered_schema[field_name] = [
            v
            for v in (
                filter_schema_for_gemini(value) for value in field_value
            )
            if v is not None
        ]
      else:
        filtered_schema[field_name] = field_value
    elif field_name in dict_schema_field_names:
      if isinstance(field_value, dict):
        filtered_dict = {}
        for key, value in field_value.items():
          filtered_value = filter_schema_for_gemini(value)
          if filtered_value is not None:
            filtered_dict[key] = filtered_value
        filtered_schema[field_name] = filtered_dict
      else:
        filtered_schema[field_name] = field_value
    elif field_name in supported_fields:
      filtered_schema[field_name] = field_value

  return filtered_schema
