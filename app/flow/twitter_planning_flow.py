import json
import time
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import Field

from app.agent.base import BaseAgent
from app.flow.base import BaseFlow
from app.llm import LLM
from app.logger import logger
from app.schema import AgentState, Message, ToolChoice
from app.tool.twitter_planning import TwitterPlanningTool


class PostStatus(str, Enum):
    """Enum class defining possible statuses of a Twitter post"""

    DRAFT = "draft"
    READY = "ready"
    POSTED = "posted"
    FAILED = "failed"

    @classmethod
    def get_all_statuses(cls) -> list[str]:
        """Return a list of all possible post status values"""
        return [status.value for status in cls]

    @classmethod
    def get_active_statuses(cls) -> list[str]:
        """Return a list of values representing active statuses (draft or ready)"""
        return [cls.DRAFT.value, cls.READY.value]

    @classmethod
    def get_status_marks(cls) -> Dict[str, str]:
        """Return a mapping of statuses to their marker symbols"""
        return {
            cls.POSTED.value: "[✓]",
            cls.READY.value: "[→]",
            cls.FAILED.value: "[!]",
            cls.DRAFT.value: "[ ]",
        }


class TwitterPlanningFlow(BaseFlow):
    """A flow that manages Twitter post planning and execution using agents."""

    llm: LLM = Field(default_factory=lambda: LLM())
    twitter_planning_tool: TwitterPlanningTool = Field(default_factory=TwitterPlanningTool)
    executor_keys: List[str] = Field(default_factory=list)
    active_plan_id: str = Field(default_factory=lambda: f"twitter_plan_{int(time.time())}")
    current_post_index: Optional[int] = None

    def __init__(
        self, agents: Union[BaseAgent, List[BaseAgent], Dict[str, BaseAgent]], **data
    ):
        # Set executor keys before super().__init__
        if "executors" in data:
            data["executor_keys"] = data.pop("executors")

        # Set plan ID if provided
        if "plan_id" in data:
            data["active_plan_id"] = data.pop("plan_id")

        # Initialize the twitter planning tool if not provided
        if "twitter_planning_tool" not in data:
            twitter_planning_tool = TwitterPlanningTool()
            data["twitter_planning_tool"] = twitter_planning_tool

        # Call parent's init with the processed data
        super().__init__(agents, **data)

        # Set executor_keys to all agent keys if not specified
        if not self.executor_keys:
            self.executor_keys = list(self.agents.keys())

    def get_executor(self, post_type: Optional[str] = None) -> BaseAgent:
        """
        Get an appropriate executor agent for the current post.
        Can be extended to select agents based on post type/requirements.
        """
        # If post type is provided and matches an agent key, use that agent
        if post_type and post_type in self.agents:
            return self.agents[post_type]

        # Otherwise use the first available executor or fall back to primary agent
        for key in self.executor_keys:
            if key in self.agents:
                return self.agents[key]

        # Fallback to primary agent
        return self.primary_agent

    async def execute(self, input_text: str) -> str:
        """Execute the Twitter planning flow with agents."""
        try:
            if not self.primary_agent:
                raise ValueError("No primary agent available")

            # Create initial plan if input provided
            if input_text:
                await self._create_initial_plan(input_text)

                # Verify plan was created successfully
                if self.active_plan_id not in self.twitter_planning_tool.plans:
                    logger.error(
                        f"Twitter plan creation failed. Plan ID {self.active_plan_id} not found in planning tool."
                    )
                    return f"Failed to create Twitter plan for: {input_text}"

            result = ""
            while True:
                # Get current post to execute
                self.current_post_index, post_info = await self._get_current_post_info()

                # Exit if no more posts or plan completed
                if self.current_post_index is None:
                    result += await self._finalize_plan()
                    break

                # Execute current post with appropriate agent
                post_type = post_info.get("type") if post_info else None
                logger.info(f"post info: {post_info}")
                executor = self.get_executor(post_type)
                post_result = await self._execute_post(executor, post_info)
                result += post_result + "\n"

                # Check if agent wants to terminate
                if hasattr(executor, "state") and executor.state == AgentState.FINISHED:
                    break

            return result
        except Exception as e:
            logger.error(f"Error in TwitterPlanningFlow: {str(e)}")
            return f"Execution failed: {str(e)}"

    async def _create_initial_plan(self, request: str) -> None:
        """Create an initial Twitter plan based on the request using the flow's LLM and TwitterPlanningTool."""
        logger.info(f"Creating initial Twitter plan with ID: {self.active_plan_id}")

        # Create a system message for plan creation
        system_message = Message.system_message(
            "You are a Twitter campaign planning assistant. Create a concise, actionable Twitter posting plan. "
            "Each post should have clear content, relevant hashtags, and image prompts where appropriate. "
            "Focus on engagement and message clarity."
        )

        # Create a user message with the request
        user_message = Message.user_message(
            f"Create a Twitter campaign plan with specific posts to accomplish: {request}"
        )

        # Call LLM with TwitterPlanningTool
        response = await self.llm.ask_tool(
            messages=[user_message],
            system_msgs=[system_message],
            tools=[self.twitter_planning_tool.to_param()],
            tool_choice=ToolChoice.AUTO,
        )

        # Process tool calls if present
        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call.function.name == "twitter_planning":
                    # Parse the arguments
                    args = tool_call.function.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse tool arguments: {args}")
                            continue

                    # Ensure plan_id is set correctly and execute the tool
                    args["plan_id"] = self.active_plan_id
                    print("--------------------------------")
                    print(response)
                    print("--------------------------------")
                    # Execute the tool
                    result = await self.twitter_planning_tool.execute(**args)
                    print("--------------------------------")
                    print(result)
                    print("--------------------------------")
                    exit()
                    logger.info(f"Twitter plan creation result: {str(result)}")
                    return

        # If execution reached here, create a default plan
        logger.warning("Creating default Twitter plan")

        # Create default Twitter plan
        await self.twitter_planning_tool.execute(
            **{
                "command": "create",
                "plan_id": self.active_plan_id,
                "title": f"Twitter Plan for: {request[:50]}{'...' if len(request) > 50 else ''}",
                "posts": [
                    {
                        "content": f"Announcing: {request[:100]}{'...' if len(request) > 100 else ''}",
                        "hashtags": ["#Announcement", "#News"],
                        "image_prompt": "",
                        "scheduled_time": "",
                    }
                ],
            }
        )

    async def _get_current_post_info(self) -> tuple[Optional[int], Optional[dict]]:
        """
        Parse the current plan to identify the first non-posted post's index and info.
        Returns (None, None) if no active post is found.
        """
        if (
            not self.active_plan_id
            or self.active_plan_id not in self.twitter_planning_tool.plans
        ):
            logger.error(f"Twitter plan with ID {self.active_plan_id} not found")
            return None, None

        try:
            # Direct access to plan data from twitter planning tool storage
            plan_data = self.twitter_planning_tool.plans[self.active_plan_id]
            posts = plan_data.get("posts", [])
            post_statuses = plan_data.get("post_statuses", [])

            # Find first non-completed post
            for i, post in enumerate(posts):
                if i >= len(post_statuses):
                    status = PostStatus.DRAFT.value
                else:
                    status = post_statuses[i]

                if status in PostStatus.get_active_statuses():
                    # Extract post type/category if available (e.g., image, poll, text)
                    post_info = post.copy()  # Use the full post object

                    # Add a default type based on post content
                    if post.get("image_prompt"):
                        post_info["type"] = "image"
                    else:
                        post_info["type"] = "text"

                    # Mark current post as ready
                    try:
                        await self.twitter_planning_tool.execute(
                            command="mark_post",
                            plan_id=self.active_plan_id,
                            post_index=i,
                            post_status=PostStatus.READY.value,
                        )
                    except Exception as e:
                        logger.warning(f"Error marking post as ready: {e}")
                        # Update post status directly if needed
                        if i < len(post_statuses):
                            post_statuses[i] = PostStatus.READY.value
                        else:
                            while len(post_statuses) < i:
                                post_statuses.append(PostStatus.DRAFT.value)
                            post_statuses.append(PostStatus.READY.value)

                        plan_data["post_statuses"] = post_statuses

                    return i, post_info

            return None, None  # No active post found

        except Exception as e:
            logger.warning(f"Error finding current post index: {e}")
            return None, None

    async def _execute_post(self, executor: BaseAgent, post_info: dict) -> str:
        """Execute the current post with the specified agent using agent.run()."""
        # Prepare context for the agent with current plan status
        plan_status = await self._get_plan_text()

        # Format post content for prompt
        post_content = post_info.get("content", "")
        hashtags = post_info.get("hashtags", [])
        image_prompt = post_info.get("image_prompt", "")

        hashtag_text = " ".join(hashtags) if hashtags else "No hashtags"
        image_text = f"Image prompt: {image_prompt}" if image_prompt else "No image required"

        # Create a prompt for the agent to execute the current post
        post_prompt = f"""
        CURRENT TWITTER PLAN STATUS:
        {plan_status}

        YOUR CURRENT TASK:
        You are now working on post {self.current_post_index}:

        Content: "{post_content}"
        Hashtags: {hashtag_text}
        {image_text}

        Please process this Twitter post appropriately. If an image is required, generate it first.
        When you're done, provide a confirmation that the post has been processed and is ready to be marked as posted.
        """

        # Use agent.run() to execute the post
        try:
            post_result = await executor.run(post_prompt)

            # Mark the post as posted after successful execution
            await self._mark_post_posted()

            return post_result
        except Exception as e:
            logger.error(f"Error executing post {self.current_post_index}: {e}")

            # Mark the post as failed
            await self.twitter_planning_tool.execute(
                command="mark_post",
                plan_id=self.active_plan_id,
                post_index=self.current_post_index,
                post_status=PostStatus.FAILED.value,
                post_notes=f"Error: {str(e)}"
            )

            return f"Error executing post {self.current_post_index}: {str(e)}"

    async def _mark_post_posted(self) -> None:
        """Mark the current post as posted."""
        if self.current_post_index is None:
            return

        try:
            # Mark the post as posted
            await self.twitter_planning_tool.execute(
                command="mark_post",
                plan_id=self.active_plan_id,
                post_index=self.current_post_index,
                post_status=PostStatus.POSTED.value,
            )
            logger.info(
                f"Marked post {self.current_post_index} as posted in plan {self.active_plan_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to update post status: {e}")
            # Update post status directly in twitter planning tool storage
            if self.active_plan_id in self.twitter_planning_tool.plans:
                plan_data = self.twitter_planning_tool.plans[self.active_plan_id]
                post_statuses = plan_data.get("post_statuses", [])

                # Ensure the post_statuses list is long enough
                while len(post_statuses) <= self.current_post_index:
                    post_statuses.append(PostStatus.DRAFT.value)

                # Update the status
                post_statuses[self.current_post_index] = PostStatus.POSTED.value
                plan_data["post_statuses"] = post_statuses

    async def _get_plan_text(self) -> str:
        """Get the current Twitter plan as formatted text."""
        try:
            result = await self.twitter_planning_tool.execute(
                command="get", plan_id=self.active_plan_id
            )
            return result.output if hasattr(result, "output") else str(result)
        except Exception as e:
            logger.error(f"Error getting Twitter plan: {e}")
            return self._generate_plan_text_from_storage()

    def _generate_plan_text_from_storage(self) -> str:
        """Generate Twitter plan text directly from storage if the planning tool fails."""
        try:
            if self.active_plan_id not in self.twitter_planning_tool.plans:
                return f"Error: Twitter plan with ID {self.active_plan_id} not found"

            plan_data = self.twitter_planning_tool.plans[self.active_plan_id]
            title = plan_data.get("title", "Untitled Twitter Plan")
            posts = plan_data.get("posts", [])
            post_statuses = plan_data.get("post_statuses", [])
            post_notes = plan_data.get("post_notes", [])

            # Ensure post_statuses and post_notes match the number of posts
            while len(post_statuses) < len(posts):
                post_statuses.append(PostStatus.DRAFT.value)
            while len(post_notes) < len(posts):
                post_notes.append("")

            # Count posts by status
            status_counts = {status: 0 for status in PostStatus.get_all_statuses()}

            for status in post_statuses:
                if status in status_counts:
                    status_counts[status] += 1

            posted = status_counts[PostStatus.POSTED.value]
            total = len(posts)
            progress = (posted / total) * 100 if total > 0 else 0

            plan_text = f"Twitter Plan: {title} (ID: {self.active_plan_id})\n"
            plan_text += "=" * len(plan_text) + "\n\n"

            plan_text += (
                f"Progress: {posted}/{total} posts published ({progress:.1f}%)\n"
            )
            plan_text += f"Status: {status_counts[PostStatus.POSTED.value]} posted, {status_counts[PostStatus.READY.value]} ready, "
            plan_text += f"{status_counts[PostStatus.FAILED.value]} failed, {status_counts[PostStatus.DRAFT.value]} draft\n\n"
            plan_text += "Posts:\n\n"

            status_marks = PostStatus.get_status_marks()

            for i, (post, status, notes) in enumerate(
                zip(posts, post_statuses, post_notes)
            ):
                # Use status marks to indicate post status
                status_mark = status_marks.get(
                    status, status_marks[PostStatus.DRAFT.value]
                )

                plan_text += f"{i}. {status_mark} Content: {post.get('content', '')}\n"
                if post.get("hashtags"):
                    plan_text += f"   Hashtags: {' '.join(post['hashtags'])}\n"
                if post.get("image_prompt"):
                    plan_text += f"   Image Prompt: {post['image_prompt']}\n"
                if post.get("scheduled_time"):
                    plan_text += f"   Scheduled: {post['scheduled_time']}\n"
                if notes:
                    plan_text += f"   Notes: {notes}\n"
                plan_text += "\n"

            return plan_text
        except Exception as e:
            logger.error(f"Error generating Twitter plan text from storage: {e}")
            return f"Error: Unable to retrieve Twitter plan with ID {self.active_plan_id}"

    async def _finalize_plan(self) -> str:
        """Finalize the Twitter plan and provide a summary using the flow's LLM directly."""
        plan_text = await self._get_plan_text()

        # Create a summary using the flow's LLM directly
        try:
            system_message = Message.system_message(
                "You are a Twitter campaign assistant. Your task is to summarize the completed Twitter campaign plan."
            )

            user_message = Message.user_message(
                f"The Twitter campaign plan has been completed. Here is the final plan status:\n\n{plan_text}\n\nPlease provide a summary of what was accomplished and any final thoughts or statistics about the campaign."
            )

            response = await self.llm.ask(
                messages=[user_message], system_msgs=[system_message]
            )

            return f"Twitter campaign plan completed:\n\n{response}"
        except Exception as e:
            logger.error(f"Error finalizing Twitter plan with LLM: {e}")

            # Fallback to using an agent for the summary
            try:
                agent = self.primary_agent
                summary_prompt = f"""
                The Twitter campaign plan has been completed. Here is the final plan status:

                {plan_text}

                Please provide a summary of what was accomplished and any final thoughts or statistics about the campaign.
                """
                summary = await agent.run(summary_prompt)
                return f"Twitter campaign plan completed:\n\n{summary}"
            except Exception as e2:
                logger.error(f"Error finalizing Twitter plan with agent: {e2}")
                return "Twitter campaign plan completed. Error generating summary."
