import google.generativeai as genai
import json
import os
import tempfile
from rich import print
from rich.panel import Panel
from rich.syntax import Syntax
from fractale.utils.timer import Timer
from fractale.agent.steps import Step
from fractale.agent.context import Context

# In the case of multiple agents working together, we can use a manager.

class ManagerAgent:
    """
    An LLM-powered agent that executes a plan. While the plan is fairly
    well defined, transitions between steps are up to the manager.
    """

    def __init__(self, plan):
        # load the plan first, throw up if not valid, etc.
        self.load_plan(plan)
        
        # The manager model works as the orchestrator of work.
        self.model = genai.GenerativeModel("gemini-1.5-pro")
        print(Panel(f"Manager Initialized with Agents: [bold cyan]{', '.join(self.agents.keys())}[/bold cyan]", title="[green]System Status[/green]"))

    def load_plan(self, plan_path):
        """
        Loads a manager plan from a specific JSON file path.
        """
        print(f"Loading plan from [bold magenta]{plan_path}[/bold magenta]...")
        self.plan_file = plan_path
        self.plan = utils.read_yaml(plan_path)
        print('LOAD AGENTS')
        import IPython
        IPython.embed()
        self.agents = {}

    def _get_recovery_step(self, failed_step: dict, error_message: str, context: dict) -> dict:
        """
        Uses Gemini to decide which agent to call to fix an error.
        This is the intelligent error routing engine.
        """
        agent_descriptions = "\n".join([f"- {name}: {agent.description}" for name, agent in self.agents.items()])
        
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
        print(Panel("Consulting LLM for error recovery plan...", title="[yellow]Error Triage[/yellow]", border_style="yellow"))
        response = self.model.generate_content(prompt)
        
        try:
            text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            print(Panel(f"[bold red]Error: Could not parse recovery step from LLM response.[/bold red]\nFull Response:\n{response.text}", title="[red]Critical Error[/red]"))
            return None

    def run(self, context=None, attempts=5):
        """
        Executes a plan-driven workflow with intelligent error recovery. How it can work:
        
        1. The plan is a YAML definition with some number of agents.
        2. Each agent can define initial inputs.
        3. A context directory is handed between agents. Each agent will be given the complete context.
        """
        # Create a global context
        context = Context(context)

        # Ensure we cleanup the workspace, unless user asks to keep it.
        try:
            self.run_tasks(context)
        finally:
            print(Panel(f"Cleaning up workspace: [bold magenta]{workspace}[/bold magenta]", title="[green]Workspace Teardown[/green]"))            
            context.cleanup()

    def run_tasks(self, context):
        """
        Run agent tasks until stopping condition.
        
        Each step in the plan can have a maximum number of attempts.
        """
        attempts = {}
        # Keep track of sequence of agent running times and sequence, and times
        tracker = []
        timer = Timer()
        print("INIT COUNTERS")
        import IPython
        IPython.embed()
        current_step_index = 0

        # Keep going until the plan is done, or max attempts reached for a step
        while current_step_index < len(plan):
            step = Step(plan[current_step_index])
            if step.agent not in self.agents:
                print(f"[red]Error: Agent '{step.agent}' in plan is not registered.[/red]")
                break
                
            # Keep track of attempts and check if we've gone over
            if step.agent not in attempts:
                attempts[step.agent] = 0
            if step.reached_maximum_attempts(attempts[step.agent]):
                print(f"[red]Agent '{step.agent}' has reached maximum attempts {step.attempts}.[/red]")
                break
            attempts[step.agent] += 1
                
            agent = self.agents[agent_name]
            print(Panel(f"Executing step {current_step_index + 1}/{len(plan)} with agent [bold cyan]{agent_name}[/bold cyan]\nTask: {task}", title=f"[blue]Orchestrator Attempt {attempts}[/blue]"))

            with timer:
                # TODO need to design consistent return interface
                exit_code, message, context = agent.run(context)
            
            # Keep track of running the agent and the time it took.
            tracker.append([agent.name, timer.elapsed_time])

            if exit_code == 0:
                print(f"[green]✅ Step successful.[/green]")
                current_step_index += 1
            else:
                print(Panel(f"Step failed. Message:\n{message}", title=f"[red]❌ Step Failed: {agent_name}[/red]", border_style="re///d", expand=False))
                recovery_step = self._get_recovery_step(step, message, context)
                
                if recovery_step:
                    print(Panel(f"Inserting recovery step from agent [bold cyan]{recovery_step['agent_name']}[/bold cyan].", title="[yellow]Recovery Plan[/yellow]"))
                    plan.insert(current_step_index, recovery_step)
                else:
                    print("[red]Could not determine recovery step. Aborting workflow.[/red]")
                    break
        
        if current_step_index == len(plan):
            print(Panel("🎉 Orchestration Complete: All plan steps succeeded!", title="[bold green]Workflow Success[/bold green]"))
            print(Panel(json.dumps(context, indent=2), title="[green]Final Context[/green]"))
        else:
            print(Panel(f"Workflow failed after {attempts} attempts.", title="[bold red]Workflow Failed[/bold red]"))


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
                return (1, "docker build error: The command '/bin/sh -c make' returned a non-zero code: 127. make: not found", context)
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
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_plan:
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
