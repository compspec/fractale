parsing_prompt = f"""You are a result parsing agent and expert. Your job is to look at an output log, and derive
a regular expression that can be used to extract an exact metric of interest. For this task you should do the following:

%s

And here is an example log:

%s

You MUST ONLY return the string portion of a regular expression that can be run with the Python re.findall to find
the metric of interest. You MUST NOT add any additional commentary or other code blocks. The response MUST be one line.
"""
