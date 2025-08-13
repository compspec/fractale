# fractale

> Translation layer for a jobspec specification to cluster execution

[![PyPI version](https://badge.fury.io/py/fractale.svg)](https://badge.fury.io/py/fractale)
[![DOI](https://zenodo.org/badge/773568660.svg)](https://zenodo.org/doi/10.5281/zenodo.13787066)

This library is primarily being used for development for the descriptive thrust of the Fractale project. It is called fractale, but also not called fractale. You can't be sure of the name until you open the box.

## Design

### Agents

The `fractale agent` command provides means to run build, job generation, and deployment agents.
This part of the library is under development. There are three kinds of agents:

 - `step` agents are experts on doing specific tasks (do hold state)
 - `manager` agents know how to orchestrate step agents and choose between them (don't hold state, but could)
 - `helper` agents are used by step agents to do small tasks (e.g., suggest a fix for an error)

The design is simple in that each agent is responding to state of error vs. success. In the case of a step agent, the return code determines to continue or try again. In the case of a helper, the input is typically an erroneous response (or something that needs changing) with respect to a goal.
For a manager, we are making a choice based on a previous erroneous step.

See [examples/agent](examples/agent) for an example.

#### To do items

- refactor manager to not handle prompt, just get step when retries come back.
- then need to decide how to handle kubernetes job creating additional structures.
- Get basic runner working
- Add in ability to get log and optimize - the manager will need to use goal
- We likely want the manager to be able to edit the prompt.
 - should be provided with entire prompt?
- When pod pending, it can be due to resource issues (and will never start). Right now we will time out, but we should be able to catch that earlier.

#### Research Questions

**And experiment ideas**

- How do we define stability?
- What are the increments of change (e.g., "adding a library")? We should be able to keep track of times for each stage and what changed, and an analyzer LLM can look at result and understand (categorize) most salient contributions to change.
  - We also can time the time it takes to do subsequent changes, when relevant. For example, if we are building, we should be able to use cached layers (and the build times speed up) if the LLM is changing content later in the Dockerfile.
- We can also save the successful results (Dockerfile builds, for example) and compare for similarity. How consistent is the LLM?
- How does specificity of the prompt influence the result?
- For an experiment, we would want to do a build -> deploy and successful run for a series of apps and get distributions of attempts, reasons for failure, and a general sense of similarity / differences.
- For the optimization experiment, we'd want to do the same, but understand gradients of change that led to improvement.

#### Observations

- Specifying cpu seems important - if you don't it wants to do GPU
- If you ask for a specific example, it sometimes tries to download data (tell it where data is)
- Always include common issues in the initial prompt
- If you are too specific about instance types, it adds node selectors/affinity, and that often doesn't work.

#### Ideas

- The manager agent is currently generated an updated prompt AND choosing the step.
 - Arguably we should have a separation of responsibility so a step can ask to fix an error without a manager.
- I think we need one more level of agent - a step agent should have helper agents that can:
 - take an error message and analyze to get a fix.


### Job Specifications

#### Simple

We provide a simple translation layer between job specifications. We take the assumption that although each manager has many options, the actual options a user would use is a much smaller set, and it's relatively straight forward to translate (and have better accuracy).

See [examples/transform](examples/transform) for an example.

#### Complex

We want to:

1. Generate software graphs for some cluster (fluxion JGF) (this is done with [compspec](https://github.com/compspec/compspec)
2. Register N clusters to a tool (should be written as a python module)
3. Tool would have ability to select clusters from resources known, return
4. Need graphical representation (json) of each cluster - this will be used with the LLM inference

See [examples/fractale](examples/fractale) for a detailed walk-through of the above.

For graph tool:

```bash
conda install -c conda-forge graph-tool
```

<!-- ⭐️ [Documentation](https://compspec.github.io/fractale) ⭐️ -->

## License

HPCIC DevTools is distributed under the terms of the MIT license.
All new contributions must be made under this license.

See [LICENSE](https://github.com/converged-computing/cloud-select/blob/main/LICENSE),
[COPYRIGHT](https://github.com/converged-computing/cloud-select/blob/main/COPYRIGHT), and
[NOTICE](https://github.com/converged-computing/cloud-select/blob/main/NOTICE) for details.

SPDX-License-Identifier: (MIT)

LLNL-CODE- 842614
