import json
import os
from datetime import datetime

from rich import print

import fractale.agent.logger as logger
import fractale.agent.manager.prompts as prompts
import fractale.utils as utils
from fractale.agent.base import GeminiAgent
from fractale.agent.context import Context
from fractale.agent.manager.plan import Plan
from fractale.utils.timer import Timer

# In the case of multiple agents working together, we can use a manager.


class ManagerAgent(GeminiAgent):
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
        logger.warning("Consulting LLM for error recovery plan...", title="Error Triage")

        response = self.model.generate_content(prompt)

        try:
            text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            logger.custom(
                f"[bold red]Error: Could not parse recovery step from LLM response.[/bold red]\nFull Response:\n{response.text}",
                title="[red]Critical Error[/red]",
            )

    def save_results(self, tracker):
        """
        Save results to file based on timestamp.

        Just ploop into pwd for now, we can eventually take a path.
        """
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        results_file = os.path.join(self.results_dir, f"results-{timestamp}.json")
        utils.write_json(tracker, results_file)

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

        # Load plan (required) and pass on setting to use cache to agents
        plan = Plan(context.get("plan", required=True), use_cache=self.use_cache)

        # The manager model works as the orchestrator of work.
        logger.custom(
            f"Manager Initialized with Agents: [bold cyan]{plan.agent_names}[/bold cyan]",
            title="[green]Manager Status[/green]",
        )

        # Ensure we cleanup the workspace, unless user asks to keep it.
        try:
            tracker = self.run_tasks(context, plan)
            logger.custom(
                f"Agentic tasks complete: [bold magenta]{len(tracker)} agent runs[/bold magenta]",
                title="[green]Manager Status[/green]",
            )
            self.save_results(tracker)

        # Raise for now so I can see the issue.
        except Exception as e:
            raise e
            logger.error(
                f"Orchestration failed:\n{str(e)}", title="Orchestration Failed", expand=False
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

            # Each time build runs, it has its own internal attempts counter.
            # Important: this counter is external (different) for the entire step
            # which has some number of internal attempts that reset each time
            if step.reached_maximum_attempts(attempts[step.agent]):
                print(f"[red]Agent '{step.agent}' has reached max attempts {step.attempts}.[/red]")
                break
            attempts[step.agent] += 1

            logger.custom(
                f"Executing step {current_step_index + 1}/{len(plan)} with agent [bold cyan]{step.agent}[/bold cyan]",
                title=f"[blue]Orchestrator Attempt {attempts[step.agent]}[/blue]",
            )

            # Execute the agent.
            # The agent is allowed to run internally up to some number of retries (defaults to unset)
            # It will save final output to context.result
            with timer:
                context = step.execute(context)

            # Keep track of running the agent and the time it took
            # Also keep result of each build step (we assume there is one)
            # We will eventually want to also save the log.
            tracker.append(
                {
                    "agent": step.agent,
                    "elapsed_time_seconds": timer.elapsed_time,
                    "result": context.get("result"),
                    "attempts": step.attempts,
                    "logs": step.logs,
                }
            )

            # If we are successful, we go to the next step.
            # Not setting a return code indicates success.
            return_code = context.get("return_code") or 0
            if return_code == 0:
                current_step_index += 1
                context.reset()

            # If we reach max attempts and no success, we need to intervene
            else:
                print("STEP NOT SUCCESSFUL: TODO what to do here?")
                # Try getting recovery step and ask manager to choose next action
                import IPython

                IPython.embed()

                # This is the intiial (cleaned) prompt to give the manager context
                instruction = step.get_initial_prompt(context)

                # Give the error message to the manager to triage
                prompt = prompts.get_retry_prompt(instruction, context.result)
                response = self.ask_gemini(prompt, with_history=False)
                logger.error(
                    f"Step failed. Instruction to agent:\n{context.result}",
                    title=f"Manager Instruction: {step.agent}",
                    expand=False,
                )
                context.reset()
                context.error_message = response
                continue

                # TODO: we eventually want to allow the LLM to choose a step
                # At this point we need to get a recovery step, and include the entire context
                # up to that point.
                recovery_step = self.get_recovery_step(context, step, message)
                if recovery_step:
                    logger.warning()
                    print(
                        f"Inserting recovery step from agent [bold cyan]{recovery_step['agent_name']}[/bold cyan].",
                        title="Recovery Plan",
                    )
                    # TODO this shouldn't be an insert, but a find and replace and then
                    # updating of the index to supoprt that.
                    plan.insert(current_step_index, recovery_step)
                else:
                    print("[red]Could not determine recovery step. Aborting workflow.[/red]")
                    break

            # If successful, reset the context for the next step.
            # This resets return code and result only.
            context.reset()

        if current_step_index == len(plan):
            logger.custom(
                "🎉 Orchestration Complete: All plan steps succeeded!",
                title="[bold green]Workflow Success[/bold green]",
            )
        else:
            logger.custom(
                f"Workflow failed after {self.max_attempts} attempts.",
                title="[bold red]Workflow Failed[/bold red]",
            )

        # Tracker is final result from each step, along with timings
        return tracker
