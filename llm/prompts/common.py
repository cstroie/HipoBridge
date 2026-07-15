"""Shared ChatML scaffolding for extraction prompts."""

CORRECTIVE_REMINDER = {
    "role": "system",
    "content": ("Your previous output did not match the required schema. "
                "Return only the JSON object, matching the fields shown in the example."),
}


def build_messages(system: str, example_user: str, example_assistant: str,
                    text: str, corrective: bool = False) -> list[dict]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": example_user},
        {"role": "assistant", "content": example_assistant},
        {"role": "user", "content": text},
    ]
    if corrective:
        messages.insert(-1, CORRECTIVE_REMINDER)
    return messages
