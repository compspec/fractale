# Agents

Let's use fractale to run build, execute, and deploy agents. First now we will run these a-la-carte, and then we will group them together to be run by an agent to request steps when needed.

## A-la-carte

### Testing Prompts

You can use the agentic base to test prompts. For example:

```python
from fractale.agent.base import GeminiAgent

agent = GeminiAgent()
reponse = agent.ask_gemini(prompt)
```

### Cost Estimation

The cost estimation agent can receive application and environment requiremnts, and provide a listing of the applications, environments (cloud), estimated cost, and instance types for each. In the case of an application supporting GPU, a GPU instance can be provided too.

```bash
fractale agent --plan ./plans/cost-estimate.yaml
```


### Batch Job Generation

Here is how to give a description to generate a Flux batch job. I chose these intentionally over jobspecs.

```bash
fractale agent --plan ./plans/flux-batch.yaml
```

### Build

The build agent will use the Gemini API to generate a Dockerfile and then build until it succeeds. We would need subsequent agents to test it.
Here is how to first ask the build agent to generate a lammps container for Google cloud.

```bash
fractale agent build lammps --environment "google cloud CPU" --outfile Dockerfile --details "Ensure all globbed files from examples/reaxff/HNS from the root of the lammps codebase are in the WORKDIR. Clone the latest branch of LAMMPS."
```

Note that we are specific about the data and using CPU, which is something the builder agent would have to guess.
That might generate the [Dockerfile](Dockerfile) here, and a container that defaults to the application name "lammps"

### Kubernetes Job

The kubernetes job agent agent will be asked to run a command, and will be provided the Dockerfile and name of the container. We assume that another agent (or you) have built and either pushed the image to a registry, or loaded it. Let's create our cluster and load the image:

```bash
kind create cluster
kind load docker-image lammps
```

To start, we will assume a kind cluster running and tell the agent the image is loaded into it (and so the pull policy will be never). 

```bash
fractale agent kubernetes-job lammps --environment "google cloud CPU" --context-file ./Dockerfile --no-pull --details "Run in.reaxff.hns in the pwd with lmp" --outfile ./job.yaml
```

## With Cache

The same steps can be run using a cache. This will save to a deterministic path in the present working directory, and means that you can run steps a la carte, and run a workflow later to re-use the context (and not wait again).
Note that when you save a cache, you often don't need to save the output file, because it will be the result in the context.

```bash
fractale agent build lammps --environment "google cloud CPU"  --details "Ensure all globbed files from examples/reaxff/HNS from the root of the lammps codebase are in the WORKDIR. Clone the latest branch of LAMMPS." --use-cache
```

And then try running with the manager (below) with the cache to see it being used.

## Manager

Let's run with a manager. Using a manager means we provide a plan along with a goal. The manager itself takes on a similar structure to a step agent, but it has a high level goal. The manager will follow the high level structure of the plan, and step
managers can often run independently for some number of attempts. If a step manager
returns after these attempts still with a failure, or if the last step is a failure,
the manager can decide how to act. For example, if a Kubernetes job deploys but fails,
it could be due to the Dockerfile build (the build manager) or the manifest for the Job.
The Job manager needs to prepare the updated context to return to this step, and then
try again.

```bash
fractale agent --plan ./plans/run-lammps.yaml

# or try using with the cache
fractale agent --plan ./plans/run-lammps.yaml --use-cache

# Save metadata
fractale agent --plan ./plans/run-lammps.yaml --results ./results

# Save metadata and include incremental results
fractale agent --plan ./plans/run-lammps.yaml --results ./results --incremental
```

Test the minicluster:

```bash
fractale agent --plan ./plans/minicluster-lammps.yaml
```

We haven't hit the case yet where the manager needs to take over - that needs further development, along with being goal oriented (e.g., parsing a log and getting an output). 

## Notes

#### To do items

- The LLM absolutely needs detail about the data, and what to run.
- We, the user, provide guard-rails guidance to help steer the LLM in the right direction.
- Error messages from programs are immensely important now since the LLM makes decisions entirely from it.
- Right now when we restart, we do with fresh slate (no log memory) - should there be?
- We likely want some want to quantify the amount of change between prompts, and the difficulty of the task.
- I think likely when we return to the manager, we want the last response (that might say why it is returning) should inform step selection. But not just step selection, the updated prompt to the step missing something.
 - Right now we rely on random sampling of the space to avoid whatever the issue might be.

#### Research Questions

**And experiment ideas**

- Why does it make the same mistakes? E.g., always forgetting ca-certificates. Did it learn from data that was OK to do and thus errors result from inconsistencies between the way things used to work and the way they do now?
- Insight: if I don't know how to run an app, it's unlikely the LLM can do it, because I can't give any guidance (and it guesses)
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
- There are issues that result from not enough information. E.g., if you don't tell it what to run / data, it can only guess. It will loop forever.
 - As an example, we know where in a git clone is the data of interest. The LLM can only guess. It's easier to tell it exactly.
 - An LLM has no sense of time with respect to versions. For example, the reax data changed from reaxc to reaxff in the same path, and which you get depends on the clone. Depending on when the LLM was trained with how to build lammps, it might select an older (or latest) branch. Instead of a juggling or guessing game (that again) would result in an infinite loop, we need to tell it the branch and data file explicitly.
- Always include common issues in the initial prompt
- If you are too specific about instance types, it adds node selectors/affinity, and that often doesn't work.
