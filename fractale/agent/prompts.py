def prompt_wrapper(prompt, context):
    """
    The prompt wrapper accepts the context and can add a prefix or suffix.
    This is typically an instruction or similar.
    """
    # Is there a prefix?
    prefix = context.get("prompt_prefix", "")
    suffix = context.get("prpmpt_prefix", "")
    details = context.get("details", "")
    return prefix + prompt + details + suffix
