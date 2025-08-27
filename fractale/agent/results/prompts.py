parsing_prompt = f"""You are a result parsing agent and expert. Your job is to look at an output log, and derive
a regular expression that can be used to extract an exact metric of interest. For this task you should do the following:

%s

And here is an example log:

%s

- You MUST only return one line with a regular expression.
- You MUST NOT add any additional commentary or code blocks.
"""
