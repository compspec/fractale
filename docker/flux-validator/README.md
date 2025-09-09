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
$ docker run -it -v $(pwd):/data ghcr.io/compspec/fractale:flux-validator /data/docker/flux-validator/batch.sh
$ echo $?
```

#### Invalid

```bash
$ docker run -it -v $(pwd):/data ghcr.io/compspec/fractale:flux-validator /data/docker/flux-validator/batch-invalid.sh
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
Sep 09 06:48:51.615419 UTC 2025 broker.err[0]: rc2.0: python3 /code/docker/flux-validator/validate.py validate /data/docker/flux-validator/batch-invalid.sh Exited (rc=1) 0.1s
```
