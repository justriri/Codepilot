"""
MemoryManager

The central controller for all AI coding agent memory.

Every other part of the system communicates with memory through
this class.

Responsibilities:

- Load context before agent execution
- Track active coding sessions
- Store environment knowledge
- Remember successful workflows
- Save verification results
- Promote useful session knowledge into long-term memory

Memory hierarchy:

Working Memory
    Current task

Session Memory
    Current agent run

Long-Term Memory
    Permanent agent intelligence
"""


from typing import Optional


from agent.memory.long_term_memory import LongTermMemory
from agent.memory.session_memory import SessionMemory
from agent.memory.working_memory import WorkingMemory



_COMMENT_PREFIX = {

    "python": "#",

    "javascript": "//",

    "typescript": "//",

    "java": "//",

}



def apply_context_to_code(
    code: str,
    context: str,
    language: str
):

    """
    Adds memory context as comments before sending code
    to the AI model.

    Never changes executable code.
    """

    if not context:
        return code


    prefix = _COMMENT_PREFIX.get(
        language,
        "#"
    )


    commented = "\n".join(
        f"{prefix} {line}"
        if line.strip()
        else prefix

        for line in context.splitlines()
    )


    return (
        f"{prefix} --- Agent Memory Context ---\n"
        f"{commented}\n"
        f"{prefix} --- End Memory Context ---\n\n"
        f"{code}"
    )





class MemoryManager:


    def __init__(
        self,
        session_memory: Optional[SessionMemory] = None,
        long_term_memory: Optional[LongTermMemory] = None
    ):


        self.session_memory = (
            session_memory
            or SessionMemory()
        )


        self.long_term_memory = (
            long_term_memory
            or LongTermMemory()
        )



    # -----------------------------
    # Context Loading
    # -----------------------------


    def build_agent_context(
        self,
        session_id: Optional[str],
        project_key: str = "default",
        environment_name: Optional[str] = None
    ):


        parts = []



        # Current session history

        if session_id:

            context = (
                self.session_memory
                .get_recent_context(session_id)
            )

            if context:

                parts.append(context)



        # Project knowledge

        project_memory = (
            self.long_term_memory
            .get_project_memory(project_key)
        )


        if project_memory:

            parts.append(
                "Project Memory:\n" +
                "\n".join(
                    f"- {item['memory_type']}: {item['content']}"
                    for item in project_memory
                )
            )



        # Environment knowledge

        if environment_name:

            environment = (
                self.long_term_memory
                .get_environment(environment_name)
            )


            if environment:

                parts.append(
                    "Environment Memory:\n"
                    f"- OS: {environment['os_image']}\n"
                    f"- Runtime: {environment['runtime']}\n"
                    f"- Dependencies: {environment['dependencies']}"
                )



        # Preferences

        preferences = (
            self.long_term_memory
            .get_all_preferences()
        )


        if preferences:

            parts.append(
                "Developer Preferences:\n"
                +
                "\n".join(
                    f"- {k}: {v}"
                    for k,v in preferences.items()
                )
            )



        return "\n\n".join(parts)





    # -----------------------------
    # Session Recording
    # -----------------------------


    def record_analysis(
        self,
        session_id: str,
        working_memory: WorkingMemory
    ):


        self.session_memory.record(

            session_id,

            "analysis_completed",

            (f"Analyzed "
                f"{working_memory.language} code"
            ),

            {

                "issues":
                working_memory.issues_found,

                "severity":
                working_memory.severity

            }

        )





    def record_file_change(
        self,
        session_id: str,
        file_path: str
    ):


        self.session_memory.add_file_change(
            session_id,
            file_path
        )





    def record_environment(
        self,
        session_id: str,
        environment_id: str
    ):


        self.session_memory.update_environment(
            session_id,
            environment_id
        )





    def record_command(
        self,
        session_id: str,
        command: str
    ):


        self.session_memory.add_command(
            session_id,
            command
        )





    # -----------------------------
    # Verification Memory
    # -----------------------------


    def record_verification(
        self,
        session_id: str,
        project_key: str,
        test_type: str,
        result: str,
        evidence: str
    ):


        self.session_memory.record(

            session_id,

            "verification_completed",

            f"Verification {result}",

            {

                "test_type": test_type,

                "evidence": evidence

            }

        )



        self.long_term_memory.save_verification(

            project_key,

            test_type,

            result,

            evidence

        )





    # -----------------------------
    # Promotion to Long-Term Memory
    # -----------------------------


    def remember_project_decision(
        self,
        project_key: str,
        memory_type: str,
        content: str
    ):


        self.long_term_memory.add_project_memory(

            project_key,

            memory_type,

            content

        )





    def remember_environment(
        self,
        environment_name: str,
        os_image: str,
        runtime: str,
        dependencies: str,
        configuration: str
    ):


        self.long_term_memory.save_environment(

            environment_name,

            os_image,

            runtime,

            dependencies,

            configuration

        )





    def remember_workflow(
        self,
        task_type: str,
        workflow: str
    ):


        self.long_term_memory.save_workflow(

            task_type,

            workflow

        )