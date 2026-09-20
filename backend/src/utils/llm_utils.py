import re


def skip_thinking_part_response(response: str) -> str:
    """
    Processes the given response string to remove:
    1. Any 'thinking' part within <think>...</think> tags.
    2. Any code fences such as ```json ... ``` or ```xml ... ``` or ```...```.

    Returns the cleaned response string.
    """
    # 1. REMOVE <THINK>...</THINK> SECTIONS IF PRESENT
    if '</think>' in response:
        think_end = response.find('</think>') + len('</think>')
        response = response[think_end:].strip()

    # 2. REMOVE MARKDOWN CODE FENCES (```JSON ... ``` OR ```XML ... ``` OR ``` ... ```)
    response = re.sub(r"```(?:json|xml)?\s*([\s\S]*?)```", r"\1", response, flags=re.IGNORECASE).strip()

    return response
