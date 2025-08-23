import fractale.agent.defaults as defaults

# This should take application, thing to parse, and then any details.
parsing_prompt = f"""You are a result parsing agent and expert. Your job is to look at an output log, and derive
a regular expression that can be used to extract an exact metric of interest. For this task you should do the following:

%s

And here is an example log:

%s

You should ONLY return the string portion of a regular expression that can be run with re.search or re.match to find
the metric of interest. Do not add any additional commentary.
"""
