#!/bin/bash
#FLUX: -N 1
#FLUX: -n 64
#FLUX: -t 100s
#FLUX: -o cpu-affinity=per-task
#FLUX: --queue=pbatch
#FLUX: --setattr=container_image=ghcr.io/converged-computing/lammps-reax:ubuntu22.04
#FLUX: --output=job.{id}.out
#FLUX: --error=job.{id}.err
#FLUX: --job-name=lammps

lmp -v x 8 -v y 8 -v z 8 -in in.reaxc.hns -nocite
