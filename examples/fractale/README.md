# Fractale Workflow

This example will walk through the steps to generate local compatibility graphs to describe a user-space, and then make a request to generate a jobspec and match.

## Install Fractale

You can pip install, or install from GitHub.

```bash
pip install fractale

# or
git clone https://github.com/compspec/fractale
cd fractale
pip install -e .
```

## Local Subsystems

A local subsystem is typically a user-space install of software or other metadata that is associated with a cluster. Local subsystems can be defined for one or more clusters, and all provided to fractale to determine with of the clusters can support the work. For each cluster, the user will use fractale and (via the [compspec](https://github.com/compspec/compspec) library and plugins) generate one or more subsystem graphs associated with different clusters. Let's start with generating metadata for clusters A and B:

```bash
fractale generate --cluster A spack /home/vanessa/Desktop/Code/spack
```

## Satisfy Request

Satisfy asks two questions:

1. Which clusters have the subsystem resources that I need?
2. Which clusters have the job resources that I need (containment subsystem)?

This is the step where we want to say "Run gromacs on 2-4 nodes with these requirements." Since we haven't formalized a way to do that, I'm going to start with a flux jobspec, and then add attributes that can be used to search our subsystems. For example, I generated [software-gromacs.json](software-gromacs.json) with:

```bash
flux submit --dry-run --setattr=requires.software=spack:curl gmx | jq
```

Note that the important part of that (in yaml) is:

```yaml
requires:
  software:
    - name: curl
      type: binary
```

This is a list of software requirements, where each entry can have multiple criteria, but all items in the list must match a software graph for it to pass. E.g., we can say a cluster subsystem requires _two_ matches (two different software libraries). This is going to say "search subsystems that are of type software looking for curl." In practice, this looks for root nodes where the type is "software," which would be the case for spack or environment modules. This file can be json or yaml. Then we ask to satisfy. Right now we are requiring that all items be under the same software subsystem (e.g., spack or environment modules) but we could change that. Either of these will work:

```bash
fractale satisfy ./examples/fractale/software-curl.yaml
fractale satisfy ./examples/fractale/software-curl.json
```

Try the graph backend, install [graph-tool](https://graph-tool.skewed.de/installation.html) then:

```bash
export PYTHONPATH=/home/vanessa/anaconda3/lib/python3.12/site-packages
fractale satisfy --solver graph ./examples/fractale/software-curl.yaml
fractale satisfy --solver graph ./examples/fractale/software-curl.json
```
```console
=> 🍇 Loading cluster "a" subsystem "containment"
=> 🍇 Loading cluster "a" subsystem "modules"
=> 🍇 Loading cluster "a" subsystem "spack"
    => Exploring cluster "a" containment subsystem
          (1/1) satisfied resource core 
Cluster "a" is a match
```

Here is for a nested slot:

```bash
fractale satisfy --solver graph ./examples/fractale/software-nested-slot.yaml 
```
```console
=> 🍇 Loading cluster "a" subsystem "containment"
=> 🍇 Loading cluster "a" subsystem "modules"
=> 🍇 Loading cluster "a" subsystem "spack"
    => Exploring cluster "a" containment subsystem
          (1/1) satisfied resource socket 
          (1/4) found resource core 
          (2/4) found resource core 
          (3/4) found resource core 
          (4/4) satisfied resource core 
Cluster "a" is a match
```

By default, the above assumes subsystems located in the fractale home. If you want to adjust that, set `fractale --config-dir=<path> satisfy...` to adjust that (and note you will need to have generated the tree here. What we basically do with satisfy is build a database with tables for:

- clusters
- subsystems
- nodes
- attributes

And right now the search is just over attributes to find matching clusters. E.g., here are attributes for a spack package:

```json
"attributes": {
    "name": "py-ply",
    "version": "3.11",
    "platform": "linux",
    "target": "zen4",
    "os": "ubuntu24.04",
    "vendor": "AuthenticAMD"
}
```

Here is a jobspec that can't be satisfied because we ask for too many resources given the cluster [containment-subsystem.json]([containment-subsystem.json).

```bash
fractale satisfy ./examples/fractale/jobspec-containment-unsatisfied.yaml 
```
```console
=> 🍇 Loading cluster "a" subsystem "containment"
=> 🍇 Loading cluster "a" subsystem "modules"
=> 🍇 Loading cluster "a" subsystem "spack"
       (2) SELECT * from subsystems WHERE type = 'software';
=> No Matches due to containment
```
We likely want to have a more structured query syntax that can handle AND, OR, and other specifics. The actual search should remain general to support any generic key/value pair of attributes. My database structure and queries are also bad. 

## Script Request

A script request is going to:

```console
=> 1. take input (right now jobspec) "what clusters can satisfy this request?
=> 2. subsystem solver "these clusters can"
=> 3. selection plugin (defaults to random) "how many and how do you want to choose from this set?"
=> 4. I have chosen N, transform them appropriately to submit
=> 5. render the matches based on the subsystem
```

Right now we have this done rather manually, and the idea is that an LLM can eventually more elegantly do it. 
Here is an example.

```bash
$ fractale script ./examples/fractale/software-curl.yaml
```
```console
=> 🍇 Loading cluster "a" subsystem "containment"
=> 🍇 Loading cluster "a" subsystem "modules"
=> 🍇 Loading cluster "a" subsystem "spack"
    => Exploring cluster "a" containment subsystem
          (1/1) satisfied resource core 
Cluster "a" is a match
{
│   'version': 1,
│   'resources': [{'type': 'slot', 'count': 1, 'with': [{'type': 'core', 'count': 1}], 'label': 'task'}],
│   'tasks': [{'command': ['gmx'], 'slot': 'task', 'count': {'per_slot': 1}}],
│   'attributes': {
│   │   'system': {
│   │   │   'duration': 0,
│   │   │   'requires': {'software': [{'name': 'curl', 'type': 'binary'}]},
│   │   │   'files': {'batch-script': {'mode': 33216, 'data': '#!/bin/bash\n\nspack load curl\ngmx', 'encoding': 'utf-8'}}
│   │   }
│   }
}
```

## Save

We can save an image of our subystem for a cluster. E.g.,

```bash
$ fractale save a --out ./examples/fractale/cluster-a-containment.png
```
```console
=> 🍇 Loading cluster "a" subsystem "containment"
=> 🍇 Loading cluster "a" subsystem "modules"
=> 🍇 Loading cluster "a" subsystem "spack"
Saving to "./examples/fractale/cluster-a-containment.png"
```

<img src="./cluster-a-containment.svg">


## Transform

This mirrors the previous transform functionality for the jobspec library. It's a simple conversion, and no LLMs needed.
