"""
Tool definitions (JSON schemas) sent to the Claude API.

This is the ONLY place the model learns what tools exist and how to
call them. To add a new tool later:
  1. Implement it in agent/tools/<something>.py
  2. Register it in ToolExecutor (agent/tools/executor.py)
  3. Add its schema here

Keeping schema definitions separate from implementations means you can
change tool internals freely without touching what the model sees.
"""

TOOL_DEFINITIONS = [
    {
        "name": "create_file",
        "description": (
            "Create a new file in the project workspace, or overwrite an existing "
            "one, with the given text content. Use this for writing HTML, CSS, JS, "
            "Python, config files, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file to create, e.g. 'index.html' or 'src/App.jsx'.",
                },
                "content": {
                    "type": "string",
                    "description": "Full text content to write into the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the current contents of an existing file in the project workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file to read.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List every file currently in the project workspace, to see the current project structure.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run a one-off shell command INSIDE THE ACTIVE SANDBOX (not on the "
            "host machine). Requires create_sandbox to have been called first. "
            "Use this for quick checks like syntax validation, linting, or "
            "curling a running server to confirm it responds."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute, e.g. 'python -m py_compile app.py' or 'curl -s localhost:3000'.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to allow the command to run before it's killed. Defaults to 30.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "create_sandbox",
        "description": (
            "Create a fresh, isolated Docker sandbox for this task. Must be "
            "called before install_dependencies, run_command, or "
            "start_application. Only one sandbox can be active at a time."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "install_dependencies",
        "description": (
            "Run a dependency-installation command inside the active sandbox "
            "(e.g. 'npm install' or 'pip install -r requirements.txt'). "
            "Functionally similar to run_command but with a longer default "
            "timeout suited to package installs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The install command to run, e.g. 'npm install'.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds before the install is killed. Defaults to 180.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "start_application",
        "description": (
            "Start a long-running application process in the background inside "
            "the sandbox (e.g. a dev server) and expose its port to the host. "
            "Returns a URL you can reach the app at. Startup output/errors are "
            "written to '.sandbox/app.log' in the project workspace, readable "
            "via read_file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command that starts the app, e.g. 'npm start' or 'python3 -m http.server 3000'.",
                },
                "port": {
                    "type": "integer",
                    "description": "The port the app listens on inside the container. Defaults to 3000.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "stop_application",
        "description": "Stop the application process previously started with start_application.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "destroy_sandbox",
        "description": (
            "Destroy the active sandbox and free its resources. Call this once "
            "you are done building and verifying the project."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_test_flow",
        "description": (
            "Execute an ordered sequence of browser actions against the running "
            "application inside the sandbox, simulating a real user flow "
            "end-to-end (e.g. navigate to a page, fill in a form, submit it, "
            "confirm the result). This is how you PROVE the app works, rather "
            "than assuming it does because the code looks right or a command "
            "exited 0. A screenshot is captured automatically after every step, "
            "saved under '.sandbox/evidence/'. If steps fail, this tool "
            "automatically runs a debugging pass, restarts the app, and "
            "retests up to a fixed number of attempts before returning — the "
            "result you get back already reflects that. Pass the app's internal_url "
            "(from start_application) as base_url."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "The app's internal_url as returned by start_application, e.g. 'http://localhost:3000'.",
                },
                "steps": {
                    "type": "array",
                    "description": "Ordered list of actions making up the user flow to test.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "navigate",
                                    "click",
                                    "fill",
                                    "wait_for_selector",
                                    "assert_visible",
                                    "assert_text",
                                    "assert_status",
                                    "screenshot",
                                ],
                                "description": (
                                    "navigate: go to base_url + path, recording the response status. "
                                    "click: click the element at selector. "
                                    "fill: type value into the input/textarea at selector. "
                                    "wait_for_selector: wait for selector to appear (e.g. after a submit). "
                                    "assert_visible: check selector is visible on the page. "
                                    "assert_text: check the element's text contains 'expected'. "
                                    "assert_status: check the most recent navigate's HTTP status equals 'expected'. "
                                    "screenshot: take an extra, explicitly-labeled screenshot."
                                ),
                            },
                            "path": {
                                "type": "string",
                                "description": "URL path for a navigate step, relative to base_url. Defaults to '/'.",
                            },
                            "selector": {
                                "type": "string",
                                "description": "CSS selector, required for click/fill/wait_for_selector/assert_visible/assert_text.",
                            },
                            "value": {
                                "type": "string",
                                "description": "Text to type in, required for fill.",
                            },
                            "expected": {
                                "description": "Expected value: a string substring for assert_text, an integer for assert_status.",
                            },
                            "label": {
                                "type": "string",
                                "description": "Optional custom name for this step's screenshot file.",
                            },
                            "timeout_ms": {
                                "type": "integer",
                                "description": "Optional timeout override for wait_for_selector, in milliseconds.",
                            },
                        },
                        "required": ["action"],
                    },
                },
                "record_video": {
                    "type": "boolean",
                    "description": "If true, records a video of the entire session, saved under '.sandbox/evidence/session.webm'. Defaults to false.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds for the whole flow to run before it's killed. Defaults to 90.",
                },
            },
            "required": ["base_url", "steps"],
        },
    },
    {
        "name": "generate_verification_report",
        "description": (
            "Compile a final verification report combining application status, "
            "the most recent run_test_flow results, evidence (screenshots/video), "
            "and an overall pass/fail verdict. Call this once you're done testing "
            "— it's the artifact the user will actually read to trust the result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "A short plain-language description of what was built and what user flow was tested.",
                },
            },
            "required": ["summary"],
        },
    },
]
