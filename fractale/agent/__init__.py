from fractale.agent.build import BuildAgent
from fractale.agent.kubernetes_job import KubernetesJobAgent


def get_agents():
    return {"build": BuildAgent, "kubernetes-job": KubernetesJobAgent}
