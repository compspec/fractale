import json
import os
import shutil
import subprocess
import tempfile
import time

from rich import print

import fractale.agent.logger as logger
import fractale.utils as utils

# All the ways a container can go wrong... (upside down smiley face)
container_issues = [
    "ImagePullBackOff",
    "ErrImagePull",
    "ErrImageNeverPull",
    "CrashLoopBackOff",
    "CreateContainerConfigError",
]


class KubernetesAbstraction:
    def __init__(self, name, namespace="default", max_tries=25):
        self.name = name
        self.namespace = namespace
        self.max_tries = max_tries

    @property
    def kind(self):
        return self.obj.capitalize()

    def apply(self, manifest):
        """
        Apply a crd, writing some content to file first.
        """
        # Keep this controllable for us to clean up for now
        deploy_dir = tempfile.mkdtemp()
        print(f"[dim]Created temporary deploy context: {deploy_dir}[/dim]")

        # Create handle to object
        # But ensure we delete any that might exist from before.
        self.delete()

        # Write the manifest to a temporary directory
        manifest_path = os.path.join(deploy_dir, f"{self.obj}.yaml")
        utils.write_file(manifest, manifest_path)
        cmd = ["kubectl", "apply", "-f", manifest_path]
        p = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=deploy_dir)
        shutil.rmtree(deploy_dir)
        return p

    def get_events(self):
        """
        If we get ALL events it can be over 200K tokens. Let's get a smaller set.
        """
        selector = f"involvedObject.kind={self.kind},involvedObject.name={self.name}"
        events_cmd = [
            "kubectl",
            "get",
            "events",
            "-n",
            self.namespace,
            f"--field-selector={selector}",
            "-o",
            "json",
        ]
        events = subprocess.run(events_cmd, capture_output=True, text=True, check=False)
        events = json.loads(events.stdout).get("items", [])

        # Sort events by time and format to be shorter (most important stuff)
        events = [
            {
                "time": e.get("lastTimestamp"),
                "type": e.get("type"),
                "reason": e.get("reason"),
                "object": e.get("involvedObject", {}).get("name"),
                "message": e.get("message"),
            }
            for e in events
        ]
        return sorted(events, key=lambda e: e.get("lastTimestamp", ""))

    def get_status(self):
        """
        Get the status, return None if not possible.
        """
        info = self.get_info()
        if not info:
            return {}
        return info.get("status", {})

    def get_info(self):
        """
        Get the status, return None if not possible.
        """
        info = subprocess.run(
            ["kubectl", "get", self.obj, self.name, "-n", self.namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if info.returncode == 0:
            return json.loads(info.stdout)

    def delete(self):
        """
        Delete object so we can... create again?
        """
        subprocess.run(
            ["kubectl", "delete", self.obj, self.name, "-n", self.namespace, "--ignore-not-found"],
            capture_output=True,
            check=False,
        )


class KubernetesPod(KubernetesAbstraction):
    """
    Wrapper to better expose different interactions.
    """

    obj = "pod"

    def get_filtered_status(self):
        """
        Gets the most critical status fields from a Job's pod(s).
        This is the most valuable source of debugging information.
        """
        status = self.get_status()
        if not status:
            return

        # Extract container statuses, which contain exit codes, reasons, etc.
        container_statuses = []
        for cs in status.get("containerStatuses", []):
            container_statuses.append(
                {
                    "name": cs.get("name"),
                    "ready": cs.get("ready"),
                    "restartCount": cs.get("restartCount"),
                    "state": cs.get("state"),
                    "lastState": cs.get("lastState"),
                }
            )

        return {
            "phase": status.get("phase"),
            "reason": status.get("reason"),
            "message": status.get("message"),
            "containerStatuses": container_statuses,
        }

    def has_failed_container(self, pod_status=None):
        """
        Determine from container statusues if there is a failed container.
        We can pass in a status object in case it needs to sync with pod info.
        We return a failure reason, if exists.
        """
        pod_status = pod_status or self.get_status()
        container_statuses = pod_status.get("containerStatuses", [])
        for cs in container_statuses:
            if cs.get("state", {}).get("waiting"):
                reason = cs["state"]["waiting"].get("reason")
                if reason in container_issues:
                    message = cs["state"]["waiting"].get("message")
                    logger.error(f"Pod has a fatal container status: {reason}", title="Pod Error")
                    return f"{reason}\nMessage: {message}"

    def wait_for_ready(self, wait_for_completed=False):
        """
        Wait for a pod to be ready.
        """
        for j in range(self.max_tries):
            pod_status = self.get_status() or {}
            pod_phase = pod_status.get("phase")

            # Let's assume when we are running the pod is ready for logs.
            # If not, we need to check container statuses too.
            if pod_phase == "Running" and not wait_for_completed:
                print(f"[green]Pod '{self.name}' entered running phase.[/green]")
                return True

            if pod_phase in ["Succeeded", "Failed"]:
                print(
                    f"[yellow]Pod '{self.name}' entered terminal phase '{pod_phase}' before logging could start.[/yellow]"
                )
                return True

            # If we get here, not ready - sleep and try again.
            print(
                f"[dim]Pod '{self.name}' has status '{pod_phase}'. Waiting... ({j+1}/{self.max_tries})[/dim]",
                end="\r",
            )
            time.sleep(3)

        # If we get here, fail and timeout
        print(f"[red]Pod '{self.name}' never reached running status, state is unknown[/red]")
        return False

    def wait_for_complete(self):
        """
        Wait for a pod to be complete
        """
        return self.wait_for_ready(wait_for_completed=True)


class KubernetesJob(KubernetesAbstraction):
    """
    A wrapper around a job to provide an easier means to get
    pod names and metadata.
    """

    obj = "job"

    def wait_for_status(self):
        """
        Wait for a job to be active and fail or succeed.
        """
        is_active, is_failed, is_succeeded = False, False, False

        # Poll for 10 minutes. This assumes a large container that needs to pull
        # This is purposfully set to use "job" for the minicluster too so we
        # get status of the underlying indexed job
        for i in range(60):  # 60 * 10s = 600s = 10 minutes
            get_status_cmd = [
                "kubectl",
                "get",
                "job",
                self.name,
                "-n",
                self.namespace,
                "-o",
                "json",
            ]
            status_process = subprocess.run(
                get_status_cmd, capture_output=True, text=True, check=False
            )
            if status_process.returncode != 0:
                time.sleep(10)
                continue

            status = json.loads(status_process.stdout).get("status", {})
            if status.get("succeeded", 0) > 0:
                print("[green]✅ Job succeeded before log streaming began.[/green]")
                is_succeeded = True
                break

            if status.get("failed", 0) > 0:
                print("[red]❌ Job entered failed state.[/red]")
                is_failed = True
                break

            if status.get("active", 0) > 0:
                print("[green]Job is active. Attaching to logs...[/green]")
                is_active = True
                break

            print(f"[dim]Still waiting... ({i+1}/30)[/dim]")
            time.sleep(10)
        return is_active, is_failed, is_succeeded

    def get_logs(self, timeout_seconds=None, wait=True):
        """
        Get the logs of a pod.
        """
        full_logs = ""
        # We use the job selector to get logs, which is more robust if the pod was recreated.
        log_cmd = ["kubectl", "logs", f"job/{self.name}", "-n", self.namespace]

        # If we ware waiting, add -f so it hangs
        if wait:
            log_cmd.insert(2, "-f")
        if timeout_seconds is not None:
            log_cmd = ["timeout", f"{timeout_seconds}s"] + log_cmd
        with subprocess.Popen(
            log_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        ) as log_process:
            # We can add a timeout to the log streaming itself if needed
            # For now, we wait for it to complete naturally.
            full_logs = "".join(log_process.stdout)

        # Return if timed out
        was_timeout = False
        if log_process.returncode == 124:
            was_timeout = True
        return full_logs, was_timeout

    def get_filtered_status(self):
        """
        Get a more filtered (streamlined) status to minimize tokens.
        Jobs have information about their pods - succeeded, failed, etc.
        """
        status = self.get_status()
        if not status:
            return
        return {
            "succeeded": status.get("succeeded", 0),
            "failed": status.get("failed", 0),
            "active": status.get("active", 0),
            "conditions": [
                {
                    "type": c.get("type"),
                    "status": c.get("status"),
                    "reason": c.get("reason"),
                    "message": c.get("message"),
                }
                for c in status.get("conditions", [])
            ],
        }

    def get_pod(self):
        """
        Find the name of the pod created by a specific job.
        """
        cmd = [
            "kubectl",
            "get",
            "pods",
            "-n",
            self.namespace,
            "-l",
            f"job-name={self.name}",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = proc.stdout.strip()

        # Only return output
        if output:
            return KubernetesPod(output, self.namespace)


class MiniCluster(KubernetesJob):
    """
    A wrapper around a MiniCluster.
    """

    obj = "minicluster"
