import copy
import json
import os
from datetime import datetime

from rich import print

import fractale.agent.logger as logger
import fractale.agent.manager.prompts as prompts
import fractale.utils as utils
from fractale.agent.base import GeminiAgent
from fractale.agent.context import Context
from fractale.agent.decorators import timed
from fractale.agent.manager.plan import Plan
from fractale.utils.timer import Timer

# In the case of multiple agents working together, we can use a manager.


class ManagerAgent(GeminiAgent):
    """
    An LLM-powered agent that executes a plan. While the plan is fairly
    well defined, transitions between steps are up to the manager.
    The manager can initialize other agents at the order it decides.
    """

    def get_recovery_step(self, context, failed_step, plan):
        """
        Uses Gemini to decide which agent to call to fix an error.
        """
        # Only go up to the step we are at...
        descriptions = ""
        for step in plan.agents:
            descriptions += f"- {step.agent}: {step.description}"
            if step.agent == failed_step.agent:
                break

        prompt = prompts.recovery_prompt % (descriptions, failed_step.agent, context.error_message)
        logger.warning("Consulting Manager Agent for error recovery plan...", title="Error Triage")
        step = None

        while not step:
            response = self.model.generate_content(prompt)
            try:
                step = json.loads(self.get_code_block(response.text, "json"))

                # I haven't seen these happen yet, but might as well be robust to error
                if "agent_name" not in step or "task_description" not in step:
                    prompt += "\n You MUST include an agent_name and task_description in the JSON response."
                    step = None
                if step["agent_name"] not in plan.agent_names:
                    prompt += "\n You MUST select an agent from the list of available agents."
                    step = None

            except Exception as e:
                step = None
                prompt = prompts.recovery_error_prompt % (
                    descriptions,
                    failed_step.agent,
                    context.error_message,
                    e,
                )
        return step

    def save_results(self, tracker, plan):
        """
        Save results to file based on timestamp.
        """
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        results_file = os.path.join(self.results_dir, f"results-{timestamp}.json")
        manager = plan.plan

        # The manager will only have times/recovery if needed to ask gemini
        if self.metadata["times"]:
            manager["times"] = self.metadata["times"]
        if self.metadata["assets"]["recovery"]:
            manager["recovery"] = self.metadata["assets"]["recovery"]
        result = {"steps": tracker, "manager": manager, "status": self.metadata["status"]}
        utils.write_json(result, results_file)

    @timed
    def run(self, context):
        """
        Executes a plan-driven workflow with intelligent error recovery. How it can work:

        1. The plan is a YAML definition with some number of agents.
        2. Each agent can define initial inputs.
        3. A context directory is handed between agents. Each agent will be given the complete context.
        """
        if "recovery" not in self.metadata["assets"]:
            self.metadata["assets"]["recovery"] = {}

        # The context is managed, meaning we return updated contexts
        context["managed"] = True

        # Store raw context for restore
        self._context = copy.deepcopy(context)

        # Create a global context
        context = Context(context)

        # We shouldn't allow the manager to go forever
        self.max_attempts = self.max_attempts or 10

        # Load plan (required) and pass on setting to use cache to agents
        plan = Plan(
            context.get("plan", required=True),
            use_cache=self.use_cache,
            save_incremental=self.save_incremental,
        )

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
            self.save_results(tracker, plan)

        # Raise for now so I can see the issue.
        except Exception as e:
            logger.error(
                f"Orchestration failed:\n{str(e)}", title="Orchestration Failed", expand=False
            )
            raise e

    def restore_context(self):
        """
        Get a new, updated context.
        """
        context = copy.deepcopy(self._context)
        context.manager = True
        return context

    def reset_context(self, context, plan, failed_step=None):
        """
        reset context up to failed state.

        If no failed state provided, reset the entire thing.
        """
        for step in plan.agents:
            context = step.reset_context(context)
            for key in ["result", "return_code"]:
                if key in context:
                    del context[key]
            if failed_step is not None and step.agent == failed_step.agent:
                break
        return context

    def assemble_issues(self, agent):
        """
        Get a list of previous issues with the step so the LLM maybe won't repeat
        """
        if agent not in self.metadata["assets"]["recovery"]:
            return []
        issues = []
        for issue in self.metadata["assets"]["recovery"][agent]:
            issues.append(issue["task_description"])
        return issues

    def run_tasks(self, context, plan):
        """
        Run agent tasks until stopping condition.

        Each step in the plan can have a maximum number of attempts.
        """
        # These are top level attempts. Each agent has its own counter
        # that is allowed to go up to some limit. The manager will
        # attempt the entire thing some number of times. Note that
        # I haven't tested this yet.
        tracker = []
        timer = Timer()
        current_step_index = 0

        # Keep going until the plan is done, or max attempts reached for the manager
        # Each step has its own internal max attempts (just another agent)
        while current_step_index < len(plan):
            # Get the step - we already have validated the agent
            step = plan[current_step_index]
            logger.custom(
                f"Executing step {current_step_index + 1}/{len(plan)} with agent [bold cyan]{step.agent}[/bold cyan]",
                title=f"[blue]Orchestrator Attempt {self.attempts}[/blue]",
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
                    "total_seconds": timer.elapsed_time,
                    "result": context.get("result"),
                    # We start counting at 0
                    "attempts": step.attempts + 1,
                    "metadata": step.logs(),
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
                # Do we try again? If we reached max, break to cut out of loop
                if self.reached_max_attempts():
                    break

                # Otherwise, we want to get a recovery step and keep going
                self.attempts += 1

                # If we are at the first step, just reset and try again.
                if current_step_index == 0:
                    context = self.reset_context(context, plan=plan)
                    continue

                # Allow the LLM to choose a step
                # At this point we need to get a recovery step, and include the entire context
                recovery_step = self.get_recovery_step(context, step, plan)

                if step.agent not in self.metadata["assets"]["recovery"]:
                    self.metadata["assets"]["recovery"][step.agent] = []

                # Keep track of recoveries. E.g., the step.agent was directed to recovery step
                self.metadata["assets"]["recovery"][step.agent].append(recovery_step)

                print(
                    f"Attempting recovery step from agent [bold cyan]{recovery_step['agent_name']}[/bold cyan].",
                )
                current_step_index = [
                    i
                    for i, step in enumerate(plan.agents)
                    if step.agent == recovery_step["agent_name"]
                ][0]

                # Reset the context. This removes output and stateful variables UP TO the failed
                # step so we don't give context that leads to another erroneous state
                context = self.reset_context(context, plan, step)

                # But assemble all the errors that we have had, we don't want to repeat.
                issues = self.assemble_issues(step.agent)
                context.error_message = prompts.get_retry_prompt(context, issues)
                continue

            # If successful, reset the context for the next step.
            # This resets return code and result only.
            context.reset()

        if current_step_index == len(plan):
            self.metadata["status"] = "Succeeded"
            logger.custom(
                "🎉 Orchestration Complete: All plan steps succeeded!",
                title="[bold green]Workflow Success[/bold green]",
            )
        else:
            self.metadata["status"] = "Failed"
            logger.custom(
                f"Workflow failed after {self.max_attempts} attempts.",
                title="[bold red]Workflow Failed[/bold red]",
            )

        # Tracker is final result from each step, along with timings
        return tracker
