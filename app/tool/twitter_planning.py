# tool/twitter_planning.py
from typing import Dict, List, Literal, Optional

from app.exceptions import ToolError
from app.tool.base import BaseTool, ToolResult


_TWITTER_PLANNING_TOOL_DESCRIPTION = """
A Twitter planning tool that allows the agent to create and manage plans for Twitter posts.
The tool provides functionality for planning tweets, managing hashtags, and tracking post status.
"""


class TwitterPlanningTool(BaseTool):
    """
    A Twitter planning tool that allows the agent to create and manage plans for Twitter posts.
    The tool provides functionality for planning tweets, managing hashtags, and tracking post status.
    """

    name: str = "twitter_planning"
    description: str = _TWITTER_PLANNING_TOOL_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "description": "The command to execute. Available commands: create, update, list, get, set_active, mark_post, delete.",
                "enum": [
                    "create",
                    "update",
                    "list",
                    "get",
                    "set_active",
                    "mark_post",
                    "delete",
                ],
                "type": "string",
            },
            "plan_id": {
                "description": "Unique identifier for the Twitter plan.",
                "type": "string",
            },
            "title": {
                "description": "Title for the Twitter campaign plan.",
                "type": "string",
            },
            "posts": {
                "description": "List of planned Twitter posts.",
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "hashtags": {"type": "array", "items": {"type": "string"}},
                        "image_prompt": {"type": "string"},
                        "scheduled_time": {"type": "string"},
                    },
                },
            },
            "post_index": {
                "description": "Index of the post to update (0-based).",
                "type": "integer",
            },
            "post_status": {
                "description": "Status to set for a post.",
                "enum": ["draft", "ready", "posted", "failed"],
                "type": "string",
            },
            "post_notes": {
                "description": "Additional notes for a post.",
                "type": "string",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    plans: dict = {}  # Dictionary to store Twitter plans by plan_id
    _current_plan_id: Optional[str] = None  # Track the current active plan

    async def execute(
        self,
        *,
        command: Literal[
            "create", "update", "list", "get", "set_active", "mark_post", "delete"
        ],
        plan_id: Optional[str] = None,
        title: Optional[str] = None,
        posts: Optional[List[Dict]] = None,
        post_index: Optional[int] = None,
        post_status: Optional[Literal["draft", "ready", "posted", "failed"]] = None,
        post_notes: Optional[str] = None,
        **kwargs,
    ):
        """
        Execute the Twitter planning tool with the given command and parameters.
        """
        if command == "create":
            return self._create_plan(plan_id, title, posts)
        elif command == "update":
            return self._update_plan(plan_id, title, posts)
        elif command == "list":
            return self._list_plans()
        elif command == "get":
            return self._get_plan(plan_id)
        elif command == "set_active":
            return self._set_active_plan(plan_id)
        elif command == "mark_post":
            return self._mark_post(plan_id, post_index, post_status, post_notes)
        elif command == "delete":
            return self._delete_plan(plan_id)
        else:
            raise ToolError(
                f"Unrecognized command: {command}. Allowed commands are: create, update, list, get, set_active, mark_post, delete"
            )

    def _create_plan(
        self, plan_id: Optional[str], title: Optional[str], posts: Optional[List[Dict]]
    ) -> ToolResult:
        """Create a new Twitter posting plan."""
        if not plan_id:
            raise ToolError("Parameter `plan_id` is required for command: create")

        if plan_id in self.plans:
            raise ToolError(
                f"A plan with ID '{plan_id}' already exists. Use 'update' to modify existing plans."
            )

        if not title:
            raise ToolError("Parameter `title` is required for command: create")

        if not posts or not isinstance(posts, list):
            raise ToolError(
                "Parameter `posts` must be a non-empty list of post objects for command: create"
            )

        # Create a new plan with initialized post statuses
        plan = {
            "plan_id": plan_id,
            "title": title,
            "posts": posts,
            "post_statuses": ["draft"] * len(posts),
            "post_notes": [""] * len(posts),
        }

        self.plans[plan_id] = plan
        self._current_plan_id = plan_id  # Set as active plan

        return ToolResult(
            output=f"Twitter plan created successfully with ID: {plan_id}\n\n{self._format_plan(plan)}"
        )

    def _update_plan(
        self, plan_id: Optional[str], title: Optional[str], posts: Optional[List[Dict]]
    ) -> ToolResult:
        """Update an existing Twitter plan."""
        if not plan_id:
            raise ToolError("Parameter `plan_id` is required for command: update")

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        plan = self.plans[plan_id]

        if title:
            plan["title"] = title

        if posts:
            if not isinstance(posts, list):
                raise ToolError(
                    "Parameter `posts` must be a list of post objects for command: update"
                )

            # Preserve existing post statuses for unchanged posts
            old_posts = plan["posts"]
            old_statuses = plan["post_statuses"]
            old_notes = plan["post_notes"]

            # Create new post statuses and notes
            new_statuses = []
            new_notes = []

            for i, post in enumerate(posts):
                if i < len(old_posts) and post == old_posts[i]:
                    new_statuses.append(old_statuses[i])
                    new_notes.append(old_notes[i])
                else:
                    new_statuses.append("draft")
                    new_notes.append("")

            plan["posts"] = posts
            plan["post_statuses"] = new_statuses
            plan["post_notes"] = new_notes

        return ToolResult(
            output=f"Twitter plan updated successfully: {plan_id}\n\n{self._format_plan(plan)}"
        )

    def _list_plans(self) -> ToolResult:
        """List all available Twitter plans."""
        if not self.plans:
            return ToolResult(
                output="No Twitter plans available. Create a plan with the 'create' command."
            )

        output = "Available Twitter plans:\n"
        for plan_id, plan in self.plans.items():
            current_marker = " (active)" if plan_id == self._current_plan_id else ""
            posted = sum(1 for status in plan["post_statuses"] if status == "posted")
            total = len(plan["posts"])
            progress = f"{posted}/{total} posts published"
            output += f"• {plan_id}{current_marker}: {plan['title']} - {progress}\n"

        return ToolResult(output=output)

    def _get_plan(self, plan_id: Optional[str]) -> ToolResult:
        """Get details of a specific Twitter plan."""
        if not plan_id:
            if not self._current_plan_id:
                raise ToolError(
                    "No active plan. Please specify a plan_id or set an active plan."
                )
            plan_id = self._current_plan_id

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        plan = self.plans[plan_id]
        return ToolResult(output=self._format_plan(plan))

    def _set_active_plan(self, plan_id: Optional[str]) -> ToolResult:
        """Set a Twitter plan as the active plan."""
        if not plan_id:
            raise ToolError("Parameter `plan_id` is required for command: set_active")

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        self._current_plan_id = plan_id
        return ToolResult(
            output=f"Twitter plan '{plan_id}' is now active.\n\n{self._format_plan(self.plans[plan_id])}"
        )

    def _mark_post(
        self,
        plan_id: Optional[str],
        post_index: Optional[int],
        post_status: Optional[str],
        post_notes: Optional[str],
    ) -> ToolResult:
        """Mark a post with a specific status and optional notes."""
        if not plan_id:
            if not self._current_plan_id:
                raise ToolError(
                    "No active plan. Please specify a plan_id or set an active plan."
                )
            plan_id = self._current_plan_id

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        if post_index is None:
            raise ToolError("Parameter `post_index` is required for command: mark_post")

        plan = self.plans[plan_id]

        if post_index < 0 or post_index >= len(plan["posts"]):
            raise ToolError(
                f"Invalid post_index: {post_index}. Valid indices range from 0 to {len(plan['posts'])-1}."
            )

        if post_status and post_status not in ["draft", "ready", "posted", "failed"]:
            raise ToolError(
                f"Invalid post_status: {post_status}. Valid statuses are: draft, ready, posted, failed"
            )

        if post_status:
            plan["post_statuses"][post_index] = post_status

        if post_notes:
            plan["post_notes"][post_index] = post_notes

        return ToolResult(
            output=f"Post {post_index} updated in plan '{plan_id}'.\n\n{self._format_plan(plan)}"
        )

    def _delete_plan(self, plan_id: Optional[str]) -> ToolResult:
        """Delete a Twitter plan."""
        if not plan_id:
            raise ToolError("Parameter `plan_id` is required for command: delete")

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        del self.plans[plan_id]

        if self._current_plan_id == plan_id:
            self._current_plan_id = None

        return ToolResult(output=f"Twitter plan '{plan_id}' has been deleted.")

    def _format_plan(self, plan: Dict) -> str:
        """Format a Twitter plan for display."""
        output = f"Twitter Plan: {plan['title']} (ID: {plan['plan_id']})\n"
        output += "=" * len(output) + "\n\n"

        # Calculate progress statistics
        total_posts = len(plan["posts"])
        posted = sum(1 for status in plan["post_statuses"] if status == "posted")
        ready = sum(1 for status in plan["post_statuses"] if status == "ready")
        failed = sum(1 for status in plan["post_statuses"] if status == "failed")
        draft = sum(1 for status in plan["post_statuses"] if status == "draft")

        output += f"Progress: {posted}/{total_posts} posts published "
        if total_posts > 0:
            percentage = (posted / total_posts) * 100
            output += f"({percentage:.1f}%)\n"
        else:
            output += "(0%)\n"

        output += f"Status: {posted} posted, {ready} ready, {failed} failed, {draft} draft\n\n"
        output += "Posts:\n"

        # Add each post with its status and notes
        for i, (post, status, notes) in enumerate(
            zip(plan["posts"], plan["post_statuses"], plan["post_notes"])
        ):
            status_symbol = {
                "draft": "[ ]",
                "ready": "[→]",
                "posted": "[✓]",
                "failed": "[!]",
            }.get(status, "[ ]")

            output += f"{i}. {status_symbol} Content: {post['content']}\n"
            if post.get("hashtags"):
                output += f"   Hashtags: {' '.join(post['hashtags'])}\n"
            if post.get("image_prompt"):
                output += f"   Image Prompt: {post['image_prompt']}\n"
            if post.get("scheduled_time"):
                output += f"   Scheduled: {post['scheduled_time']}\n"
            if notes:
                output += f"   Notes: {notes}\n"
            output += "\n"

        return output
