rebuild_prompt = f"""Act as a Dockerfile builder service expert. I am trying to build a Docker image named for the application '%s' in an environment for '%s'. The previous attempt to build or run the Dockerfile failed. Here is the problematic Dockerfile:

```dockerfile
%s
```

Here is the error message I received:
```
%s
```

Please analyze the error and the Dockerfile, and provide a corrected version.
- The response should only contain the complete, corrected Dockerfile inside a single markdown code block.
- Use succinct comments in the Dockerfile to explain build logic and changes.
- Optimize for performance and security using best practices like multi-stage builds, especially for HPC applications.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
"""


def get_rebuild_prompt(application, environment, dockerfile, error_message):
    return rebuild_prompt % (application, environment, dockerfile, error_message)


build_prompt = f"""Act as a Dockerfile builder service expert.
I need to create a Dockerfile for an application '%s'.
The target environment is '%s'.

Please generate a robust, production-ready Dockerfile.
- Since this is for HPC, prioritize strategies to keep the final image lean.
- If the application involves MPI, configure it for compatibility for the containerized environment.
- The response should ONLY contain the complete Dockerfile.
- Do not add your narration unless it has a "#" prefix to indicate a comment.
- Do not change the name of the application image provided.
"""


def get_build_prompt(application, environment):
    return build_prompt % (application, environment)
