# Agents

Let's use fractale to run build, execute, and deploy agents. Right now we will run these a-la-carte, and eventually we will group them together to loop back and repeat steps if needed.

## Build

The build agent will use the Gemini API to generate a Dockerfile and then build until it succeeds. We would need subsequent agents to test it.
Here is how to first ask the build agent to generate a lammps container for Google cloud.

```bash
fractale agent build lammps --environment "google cloud" --outfile dockerfile
```

That might generate the [Dockerfile](Dockerfile) here, and a container that defaults to the application name "lammps"

## Kubernetes Job

The kubernetes job agent agent will be asked to run a command, and will be provided the Dockerfile and name of the container. We assume that another agent (or you) have built and either pushed the image to a registry, or loaded it. Let's create our cluster and load the image:

```bash
kind create cluster
kind load docker-image lammps
```

To start, we will assume a kind cluster running and tell the agent the image is loaded into it (and so the pull policy will be never). 

```bash
fractale agent kubernetes-job lammps --environment "google cloud CPU" --context-file ./Dockerfile --no-pull 
```

