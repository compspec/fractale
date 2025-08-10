# Agents

Let's use fractale to run build, execute, and deploy agents. First now we will run these a-la-carte, and then we will group them together to be run by an agent to request steps when needed.

## A-la-carte

### Build

The build agent will use the Gemini API to generate a Dockerfile and then build until it succeeds. We would need subsequent agents to test it.
Here is how to first ask the build agent to generate a lammps container for Google cloud.

```bash
fractale agent build lammps --environment "google cloud" --outfile dockerfile
```

That might generate the [Dockerfile](Dockerfile) here, and a container that defaults to the application name "lammps"

### Kubernetes Job

The kubernetes job agent agent will be asked to run a command, and will be provided the Dockerfile and name of the container. We assume that another agent (or you) have built and either pushed the image to a registry, or loaded it. Let's create our cluster and load the image:

```bash
kind create cluster
kind load docker-image lammps
```

To start, we will assume a kind cluster running and tell the agent the image is loaded into it (and so the pull policy will be never). 

```bash
fractale agent kubernetes-job lammps --environment "google cloud CPU" --context-file ./Dockerfile --no-pull 
```

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
```

For this first design, we are taking an approach where we only re-assess the state and go back to a previous step given a last step failure. The assumption is that if a previous step fails, we keep trying until it succeeds. We only need to backtrack if the last step in a sequence is not successful, and it is due to failure at some stage in the process. But I do think we have a few options:

1. Allow the manager to decide what to do on _every_ step (likely not ideal)
2. Allow step managers to execute until success, always (too much issue if a step is failing because of dependency)
3. Allow step managers to execute until success unless a limit is set, and then let the manager take over (in other words, too many failures means we hand it back to the manager to look.)