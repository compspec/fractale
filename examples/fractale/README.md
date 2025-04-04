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

This is the step where we want to say "Run gromacs on 2-4 nodes with these requirements." Since we haven't formalized a way to do that, I'm going to start with a flux jobspec, and then add attributes that can be used to search our subsystems. For example, I generated [software-gromacs.json](software-gromacs.json) with:

```bash
flux submit --dry-run --setattr=requires.software=spack:gromacs gmx | jq
```

Note that the important part of that is:

```json
  "attributes": {
    "system": {
      "requires": {
        "software": "gromacs"
      }
    }
  },
```

This is going to say "search subsystems that are of type software looking for gromacs." In practice, this looks for root nodes where the type is "software," which would be the case for spack or environment modules. This file can be json or yaml. Then we ask to satisfy. Either of these will work:

```bash
fractale satisfy ./examples/fractale/software-gromacs.yaml
fractale satisfy ./examples/fractale/software-gromacs.json
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

We likely want to have a more structured query syntax that can handle AND, OR, and other specifics. The actual search should remain general to support any generic key/value pair of attributes. My database structure and queries are also bad. 
