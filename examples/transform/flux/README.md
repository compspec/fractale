# Transform

This is an example of doing a transformation between types. We do a simple mapping of parameters.
To start testing, we will assume one node runs, and of the equivalent container. This way we can create a Job in Kubernetes without considering MPI networking.

## Flux to Kubernetes

```bash
# Print pretty
fractale transform --to kubernetes --from flux ./flux-batch.sh --pretty

# Print as raw yaml (to pipe to file)
fractale transform --to kubernetes --from flux ./flux-batch.sh
```
```console
apiVersion: batch/v1
kind: Job
metadata:
  name: lammps
spec:
  activeDeadlineSeconds: 100
  backoffLimit: 4
  completions: 1
  parallelism: 1
  template:
    metadata:
      labels:
        job-name: lammps
    spec:
      apiVersion: batch/v1
      kind: Job
      metadata:
        name: lammps
      spec:
        backoffLimit: 0
        template:
          spec:
            containers:
            - args:
              - lmp -v x 8 -v y 8 -v z 8 -in in.reaxc.hns -nocite
              command:
              - /bin/bash
              - -c
              image: ghcr.io/converged-computing/lammps-reax:ubuntu22.04
              name: lammps
              resources:
                limits:
                  cpu: '64'
                requests:
                  cpu: '64'
            restartPolicy: Never
```

## Flux to Slurm

```bash
fractale transform --to slurm --from flux ./flux-batch.sh --pretty
fractale transform --to slurm --from flux ./flux-batch.sh
```
