#!/usr/bin/env python3

import argparse
import os
import re
import sys

import yaml

from fractale.logger.generate import JobNamer
from fractale.transformer.base import TransformerBase

# Assume GPUs are NVIDIA
gpu_resource_name = "nvidia.com/gpu"


def normalize_cpu_request(cpus: int) -> str:
    """
    Convert an integer number of CPUs to a Kubernetes CPU string.
    """
    # Kubernetes can use millicores, e.g., 1 -> "1000m", 0.5 -> "500m"
    # We will stick to whole numbers, but this is where you'd convert.
    return str(cpus)


def normalize_memory_request(mem_str):
    """
    Convert memory units like 'G' and 'M' to Kubernetes 'Gi' and 'Mi'.
    """
    if not mem_str:
        return None
    mem_str = mem_str.upper()
    if mem_str.endswith("G"):
        return mem_str.replace("G", "Gi")
    if mem_str.endswith("M"):
        return mem_str.replace("M", "Mi")

    # Assume other formats (like Gi, Mi, K, Ki) are already correct
    return mem_str


def get_resources(spec):
    """
    Get Kubernetes resources from standard jobspec
    """
    # Resources (CPU, Memory, GPU)
    resources = {"requests": {}, "limits": {}}

    # We usually map tasks to kubernetes cores
    if spec.num_tasks > 1:
        cpu_request = normalize_cpu_request(spec.num_tasks)
        resources["requests"]["cpu"] = cpu_request
        resources["limits"]["cpu"] = cpu_request

    elif spec.cpus_per_task > 0:
        cpu_request = normalize_cpu_request(spec.cpus_per_task)
        resources["requests"]["cpu"] = cpu_request
        resources["limits"]["cpu"] = cpu_request

    if spec.mem_per_task:
        mem_request = normalize_memory_request(spec.mem_per_task)
        resources["requests"]["memory"] = mem_request
        resources["limits"]["memory"] = mem_request
    if spec.gpus_per_task > 0:
        resources["limits"][gpu_resource_name] = str(spec.gpus_per_task)
    return resources


class KubernetesTransformer(TransformerBase):
    """
    A Flux Transformer is a very manual way to transform a subsystem into
    a batch script. I am not even using jinja templates, I'm just
    parsing the subsystems in a sort of manual way. This a filler,
    and assuming that we will have an LLM that can replace this.
    """

    def convert(self, spec):
        """
        Convert a normalized jobspec to the format here.
        """
        # If we don't have a job name, generate one
        # Also sanitize for Kubernetes (DNS-1123 subdomain name)
        job_name = spec.job_name or JobNamer().generate()
        job_name = re.sub(r"[^a-z0-9-]", "-", job_name.lower()).strip("-")

        # This gets passed from flux attribute, --setattr=container_image=<value>
        if not spec.container_image:
            raise ValueError("Conversion to Kubernetes requires a container image.")

        # Parse the application container first.
        command = spec.executable if spec.executable else ["/bin/bash", "-c"]
        container = {
            "name": job_name,
            "image": spec.container_image,
            "command": command,
            "args": spec.arguments or None,
        }

        resources = get_resources(spec)
        if resources["requests"] or resources["limits"]:
            container["resources"] = resources
        if spec.working_directory:
            container["workingDir"] = spec.working_directory
        if spec.environment:
            container["env"] = [{"name": k, "value": v} for k, v in spec.environment.items()]

        pod_spec = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": job_name},
            "spec": {
                "template": {"spec": {"containers": [container], "restartPolicy": "Never"}},
                "backoffLimit": 0,
            },
        }

        if spec.priority:
            pod_spec["priorityClassName"] = str(spec.priority)

        # If >1 node, set affinity to spread across
        if spec.num_nodes > 1:
            pod_spec.setdefault("affinity", {})
            pod_spec["affinity"]["podAntiAffinity"] = {
                "requiredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "labelSelector": {
                            "matchExpressions": [
                                {"key": "job-name", "operator": "In", "values": [spec.job_name]}
                            ]
                        },
                        "topologyKey": "kubernetes.io/hostname",
                    }
                ]
            }

        # This controls the Job controller itself (parallelism, deadline, etc.)
        job_spec = {
            "parallelism": spec.num_nodes,
            "completions": spec.num_nodes,
            "backoffLimit": 4,  # A sensible default
            "template": {"metadata": {"labels": {"job-name": spec.job_name}}, "spec": pod_spec},
        }

        # This is already in seconds
        if spec.wall_time:
            job_spec["activeDeadlineSeconds"] = spec.wall_time

        job = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": spec.job_name,
            },
            "spec": job_spec,
        }

        # Add extra attributes that aren't relevant as labels
        if spec.account:
            job["metadata"].setdefault("labels", {})
            job["metadata"]["labels"]["account"] = spec.account
        return job
