# Agents

Let's use fractale to run build, execute, and deploy agents. 

## Build

The build agent will use the Gemini API to generate a Dockerfile and then build until it succeeds. We would need subsequent agents to test it.
Here is how to first ask the build agent to generate a lammps container for Google cloud.

```bash
fractale agent build lammps --environment "google cloud" --outfile dockerfile
```

That might generate the [Dockerfile](Dockerfile) here, and a container that defaults to the application name "lammps"

## Execute

The execute agent will be asked to run a command, and will be provided the Dockerfile.


