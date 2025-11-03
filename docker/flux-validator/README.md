# Flux Validator

I built this into a container so it can be run, one-off, as a tool without needing a Flux instance running.

To build, from the root:

```bash
make
```

### Test Cases

To run against test cases:

#### Valid

```bash
$ docker run -it -v $(pwd):/data ghcr.io/compspec/fractale:flux-validator validate /data/docker/flux-validator/batch.sh
$ echo $?
```

##### Validate canonical jobspec in YAML or JSON format
```bash
$ docker run -it -v $(pwd):/data ghcr.io/compspec/fractale:flux-validator validate /data/docker/flux-validator/valid-canonical.yaml
$ echo $?
```

##### Validate counts
```bash
$ docker run -it -v $(pwd):/data ghcr.io/compspec/fractale:flux-validator count /data/docker/flux-validator/valid-canonical.yaml
The jobspec is valid! Here are the total resource counts per type requested by the provided jobspec:
Type: node, count: 1
Type: memory, count: 256
Type: socket, count: 2
Type: gpu, count: 8
Type: slot, count: 4
Type: L3cache, count: 4
Type: core, count: 16
Type: pu, count: 16
```

#### Invalid

```bash
$ docker run -it -v $(pwd):/data ghcr.io/compspec/fractale:flux-validator validate /data/docker/flux-validator/batch-invalid.sh
usage: batch [OPTIONS...] COMMAND [ARGS...]
batch: error: unrecognized arguments: --noodles=2
Flux Batch Validation Failed:
#!/bin/bash

#FLUX: -N2
#FLUX -n8
#FLUX: --out=lammps.out
#FLUX: --err=lammps.err
#FLUX: --noodles=2

hostname

Validation failed at directives:
#FLUX directives need to be FLUX:
--noodles=2: 2
```

##### Invalid canonical jobspec
```bash
$ docker run -it -v $(pwd):/data ghcr.io/compspec/fractale:flux-validator validate /data/docker/flux-validator/invalid-canonical-slot.yaml
Flux Batch Validation Failed:
version: 9999
resources:
    - type: node
      count: 1
      with:
        - type: memory
          count: 256
        - type: socket
          count: 2
          with:
            - type: gpu
              count: 4
            - type: slot
              count: 2
              with:
                - type: L3cache
                  count: 1
                  with:
                    - type: core
                      count: 4
                      with:
                        - type: pu
                          count: 1

# a comment
attributes:
  system:
    duration: 3600
tasks:
  - command: [ "app" ]
    slot: default
    count:
      per_slot: 1

slots must have labels
```
