from fractale.agent.build import BuildAgent
from fractale.agent.kubernetes import KubernetesJobAgent
from fractale.agent.manager import ManagerAgent


def get_agents():
    # The Manager Agent is a special kind that can orchestrate other managers.
    # We could technically nest them.
    return {"build": BuildAgent, "kubernetes-job": KubernetesJobAgent, "manager": ManagerAgent}
