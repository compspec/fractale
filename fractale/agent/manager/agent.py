import json
import os
import tempfile

import google.generativeai as genai
from rich import print
from rich.panel import Panel

from fractale.agent.base import Agent
from fractale.agent.context import Context
from fractale.agent.manager.plan import Plan
from fractale.utils.timer import Timer

# In the case of multiple agents working together, we can use a manager.


class ManagerAgent(Agent):
    """
    An LLM-powered agent that executes a plan. While the plan is fairly
    well defined, transitions between steps are up to the manager.
    The manager can initialize other agents at the order it decides.
    """

    def get_recovery_step(self, context, failed_step, message):
        """
        Uses Gemini to decide which agent to call to fix an error.
        This is the intelligent error routing engine.
        """
        print("GET RECOVERY STEP")
        import IPython

        IPython.embed()
        # move to file
        agent_descriptions = "\n".join(
            [f"- {name}: {agent.description}" for name, agent in self.agents.items()]
        )

        prompt = f"""
        You are an expert AI workflow troubleshooter. A step in a workflow has failed. Your job is to analyze the error and recommend a single, corrective step.

        Available Agents:
        {agent_descriptions}

        Context:
        - The overall goal is to run a build-and-deploy workflow.
        - The step using agent '{failed_step['agent_name']}' failed while trying to: {failed_step['task_description']}

        Error Message:
        ```
        {error_message}
        ```

        Instructions:
        1. Analyze the error message to determine the root cause (e.g., is it a Dockerfile syntax error, a Kubernetes resource issue, an image name typo, etc.?).
        2. Decide which agent is best suited to fix this specific error.
        3. Formulate a JSON object for the corrective step with two keys: "agent_name" and "task_description".
        4. The new "task_description" MUST be a clear instruction for the agent to correct the specific error.

        Provide only the single JSON object for the corrective step in your response.
        """
        print(
            Panel(
                "Consulting LLM for error recovery plan...",
                title="[yellow]Error Triage[/yellow]",
                border_style="yellow",
            )
        )
        response = self.model.generate_content(prompt)

        try:
            text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            print(
                Panel(
                    f"[bold red]Error: Could not parse recovery step from LLM response.[/bold red]\nFull Response:\n{response.text}",
                    title="[red]Critical Error[/red]",
                )
            )
            return None

    def run(self, context):
        """
        Executes a plan-driven workflow with intelligent error recovery. How it can work:

        1. The plan is a YAML definition with some number of agents.
        2. Each agent can define initial inputs.
        3. A context directory is handed between agents. Each agent will be given the complete context.
        """
        # Create a global context
        context = Context(context)

        # The context is managed, meaning we return updated contexts
        context.managed = True

        # Load plan (required)
        plan = Plan(context.get("plan", required=True))

        # The manager model works as the orchestrator of work.
        self.model = genai.GenerativeModel("gemini-1.5-pro")
        print(
            Panel(
                f"Manager Initialized with Agents: [bold cyan]{plan.agent_names}[/bold cyan]",
                title="[green]Manager Status[/green]",
            )
        )

        # Ensure we cleanup the workspace, unless user asks to keep it.
        try:
            tracker = self.run_tasks(context, plan)
            print(
                Panel(
                    f"Agentic tasks complete: [bold magenta]{len(tracker)} agent runs[/bold magenta]",
                    title="[green]Manager Status[/green]",
                )
            )
        except Exception as e:
            print(
                Panel(
                    f"Orchestration failed:\n{str(e)}",
                    title=f"[red]❌ Orchestration Failed[/red]",
                    border_style="red",
                    expand=False,
                )
            )

    def run_tasks(self, context, plan):
        """
        Run agent tasks until stopping condition.

        Each step in the plan can have a maximum number of attempts.
        """
        # These are top level attempts. Each agent has its own counter
        # that is allowed to go up to some limit.

        attempts = {}
        # Keep track of sequence of agent running times and sequence, and times
        tracker = []
        timer = Timer()
        current_step_index = 0

        # Keep going until the plan is done, or max attempts reached for a step
        while current_step_index < len(plan):
            # Get the step - we already have validated the agent
            step = plan[current_step_index]

            # Keep track of attempts and check if we've gone over
            if step.agent not in attempts:
                attempts[step.agent] = 0

            # This is the external attempts (e.g., we allowed build to run N times)
            # Each time build runs, it has its own internal attempts counter.
            if step.reached_maximum_attempts(attempts[step.agent]):
                print(f"[red]Agent '{step.agent}' has reached max attempts {step.attempts}.[/red]")
                break
            attempts[step.agent] += 1

            print(
                Panel(
                    f"Executing step {current_step_index + 1}/{len(plan)} with agent [bold cyan]{step.agent}[/bold cyan]",
                    title=f"[blue]Orchestrator Attempt {attempts[step.agent]}[/blue]",
                )
            )
            # Execute the agent.
            # The agent is allowed to run internally up to some number
            # of retries (defaults to unset)
            # It will save final output to context.result
            with timer:
                context = step.execute(context)

            # Keep track of running the agent and the time it took
            # Also keep result of each build step (we assume there is one)
            tracker.append([step.agent, timer.elapsed_time, context.get("result")])

            # If we are successful, we go to the next step.
            # Not setting a return code indicates success.
            return_code = context.get("return_code", 0)
            if return_code == 0:
                print(f"[green]✅ Step successful.[/green]")
                current_step_index += 1

            # If we reach max attempts and no success, we need to intervene
            else:
                message = context.get("result", "")
                print(
                    Panel(
                        f"Step failed. Message:\n{message}",
                        title=f"[red]❌ Step Failed: {step.agent}[/red]",
                        border_style="re///d",
                        expand=False,
                    )
                )
                # At this point we need to get a recovery step, and include the entire context
                # up to that point.
                recovery_step = self.get_recovery_step(context, step, message)

                print("POST RECOVERY STEP")
                # need to decide how to move about plan
                # I don't think we sdhould insert, I think we should change the index instead.
                # This assumes that steps have unique names.
                import IPython

                IPython.embed()

                if recovery_step:
                    print(
                        Panel(
                            f"Inserting recovery step from agent [bold cyan]{recovery_step['agent_name']}[/bold cyan].",
                            title="[yellow]Recovery Plan[/yellow]",
                        )
                    )
                    plan.insert(current_step_index, recovery_step)
                else:
                    print("[red]Could not determine recovery step. Aborting workflow.[/red]")
                    break

            # Reset the context for the next step.
            # This resets return code and result only.
            context.reset()

        print("Orchestration complete - figure out return Vanessa")
        import IPython

        IPython.embed()
        if current_step_index == len(plan):
            print(
                Panel(
                    "🎉 Orchestration Complete: All plan steps succeeded!",
                    title="[bold green]Workflow Success[/bold green]",
                )
            )
            print(Panel(json.dumps(context, indent=2), title="[green]Final Context[/green]"))
        else:
            print(
                Panel(
                    f"Workflow failed after {attempts} attempts.",
                    title="[bold red]Workflow Failed[/bold red]",
                )
            )


if __name__ == "__main__":
    # --- DEMONSTRATION OF USAGE ---

    # 1. Define dummy worker agents for the demo
    class DummyDockerAgent:
        name = "docker-builder"
        description = "Handles Dockerfile creation and image building."

        def run(self, task, context):
            print(f"  [Docker Agent] Received task: {task}")
            # Simulate a failure on the first try
            if "fix" not in task.lower():
                # This error message will be sent to the LLM for analysis
                return (
                    1,
                    "docker build error: The command '/bin/sh -c make' returned a non-zero code: 127. make: not found",
                    context,
                )
            else:
                print("  [Docker Agent] Applying fix and building again...")
                context["image_uri"] = "my-hpc-app:v2-fixed"
                return (0, "Build successful", context)

    class DummyK8sAgent:
        name = "kubernetes-job"
        description = "Deploys containers as Kubernetes Jobs."

        def run(self, task, context):
            print(f"  [K8s Agent] Received task: {task}")
            print(f"  [K8s Agent] Using image: {context.get('image_uri')}")
            return (0, "Job deployed and completed successfully.", context)

    # 2. Create the JSON plan content as a string
    plan_content = """
    {
      "name": "Standard Build and Deploy",
      "description": "Builds a Docker container from source and deploys it as a Kubernetes Job.",
      "plan": [
        {
          "agent_name": "docker-builder",
          "task_description": "Create a Dockerfile and build a container image for the HPC application."
        },
        {
          "agent_name": "kubernetes-job",
          "task_description": "Take the 'image_uri' from the context and deploy it as a Kubernetes Job."
        }
      ]
    }
    """

    # 3. Create a temporary file to act as our plan file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as temp_plan:
        temp_plan.write(plan_content)
        temp_plan_path = temp_plan.name

    print(f"Created a temporary plan file for demonstration at: {temp_plan_path}\n")

    # 4. Configure Gemini and initialize agents
    # Configure Gemini API Key
    # genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

    docker_agent = DummyDockerAgent()
    k8s_agent = DummyK8sAgent()
    orchestrator = OrchestratorAgent(agents=[docker_agent, k8s_agent])

    # 5. Run the orchestrator, providing the FULL PATH to the plan
    orchestrator.run(plan_path=temp_plan_path, initial_context={"source_dir": "/path/to/src"})

    # 6. Clean up the temporary file
    os.remove(temp_plan_path)
