"""
Long-term memory for an AI coding agent infrastructure system.

This memory persists knowledge that helps agents create,
debug, test, and verify software environments.

Unlike session memory (temporary agent runs),
long-term memory stores reusable knowledge:

- environments
- dependency setups
- project architecture
- successful workflows
- verification history
- developer preferences

Storage:
SQLite database for local-first development.
"""

import sqlite3
import time

from contextlib import contextmanager
from typing import Dict, List, Optional


class LongTermMemory:

    def __init__(self, db_path: str = "agent_memory.db"):
        self.db_path = db_path
        self._init_schema()


    @contextmanager
    def _connect(self):

        conn = sqlite3.connect(self.db_path)

        try:
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()

        finally:
            conn.close()



    def _init_schema(self):

        with self._connect() as conn:


            # Stores reusable environment knowledge
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS environments (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    environment_name TEXT NOT NULL,

                    os_image TEXT,

                    runtime TEXT,

                    dependencies TEXT,

                    configuration TEXT,

                    success_count INTEGER DEFAULT 1,

                    created_at REAL NOT NULL,

                    last_used REAL NOT NULL
                )
                """
            )



            # Stores project architecture memory
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_memory (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    project_key TEXT NOT NULL,

                    memory_type TEXT NOT NULL,

                    content TEXT NOT NULL,

                    created_at REAL NOT NULL
                )
                """
            )



            # Stores successful agent workflows
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_workflows (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    task_type TEXT NOT NULL,

                    workflow TEXT NOT NULL,

                    success_count INTEGER DEFAULT 1,

                    created_at REAL NOT NULL,

                    last_used REAL NOT NULL
                )
                """
            )



            # Stores verification knowledge
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_history (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    project_key TEXT,

                    test_type TEXT,

                    result TEXT,

                    evidence TEXT,

                    created_at REAL NOT NULL
                )
                """
            )



            # Stores user/developer preferences
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS developer_preferences (

                    key TEXT PRIMARY KEY,

                    value TEXT NOT NULL,

                    updated_at REAL NOT NULL
                )
                """
            )



    # -------------------------
    # Environment Memory
    # -------------------------


    def save_environment(
        self,
        environment_name: str,
        os_image: str,
        runtime: str,
        dependencies: str,
        configuration: str
    ):


        with self._connect() as conn:

            conn.execute(
                """
                INSERT INTO environments

                (
                environment_name,
                os_image,
                runtime,
                dependencies,
                configuration,
                created_at,
                last_used
                )

                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,

                (
                    environment_name,
                    os_image,
                    runtime,
                    dependencies,
                    configuration,
                    time.time(),
                    time.time()
                )

            )



    def get_environment(self, environment_name: str):

        with self._connect() as conn:

            row = conn.execute(
                """
                SELECT *
                FROM environments
                WHERE environment_name = ?

                """,
                (environment_name,)
            ).fetchone()


            return dict(row) if row else None




    # -------------------------
    # Project Memory
    # -------------------------


    def add_project_memory(
        self,
        project_key: str,
        memory_type: str,
        content: str
    ):


        with self._connect() as conn:

            conn.execute(
                """
                INSERT INTO project_memory

                (
                project_key,
                memory_type,
                content,
                created_at
                )

                VALUES (?, ?, ?, ?)

                """,

                (
                    project_key,
                    memory_type,
                    content,
                    time.time()
                )
            )



    def get_project_memory(
        self,
        project_key: str,
        limit: int = 20
    ):


        with self._connect() as conn:

            rows = conn.execute(
                """
                SELECT memory_type, content

                FROM project_memory

                WHERE project_key = ?

                ORDER BY created_at DESC

                LIMIT ?

                """,

                (
                    project_key,
                    limit
                )

            ).fetchall()


            return [
                dict(row)
                for row in rows
            ]



    # -------------------------
    # Agent Workflow Memory
    # -------------------------


    def save_workflow(
        self,
        task_type: str,
        workflow: str
    ):


        with self._connect() as conn:

            conn.execute(
                """
                INSERT INTO agent_workflows

                (
                task_type,
                workflow,
                created_at,
                last_used
                )

                VALUES (?, ?, ?, ?)

                """,

                (
                    task_type,
                    workflow,
                    time.time(),
                    time.time()
                )
            )



    def find_workflow(
        self,
        task_type: str
    ):


        with self._connect() as conn:

            row = conn.execute(
                """
                SELECT *

                FROM agent_workflows

                WHERE task_type = ?

                ORDER BY success_count DESC

                LIMIT 1

                """,

                (task_type,)

            ).fetchone()


            return dict(row) if row else None



    # -------------------------
    # Verification Memory
    # -------------------------


    def save_verification(
        self,
        project_key: str,
        test_type: str,
        result: str,
        evidence: str
    ):


        with self._connect() as conn:

            conn.execute(
                """
                INSERT INTO verification_history

                (
                project_key,
                test_type,
                result,
                evidence,
                created_at
                )

                VALUES (?, ?, ?, ?, ?)

                """,

                (
                    project_key,
                    test_type,
                    result,
                    evidence,
                    time.time()
                )
            )



    # -------------------------
    # Developer Preferences
    # -------------------------
    def set_preference(
        self,
        key: str,
        value: str
    ):

        with self._connect() as conn:

            conn.execute(
                """
                INSERT INTO developer_preferences

                (key,value,updated_at)

                VALUES (?, ?, ?)

                ON CONFLICT(key)

                DO UPDATE SET

                value = excluded.value,

                updated_at = excluded.updated_at

                """,

                (
                    key,
                    value,
                    time.time()
                )
            )



    def get_all_preferences(self):

        with self._connect() as conn:

            rows = conn.execute(
                """
                SELECT key,value

                FROM developer_preferences

                """
            ).fetchall()


            return {
                row["key"]: row["value"]
                for row in rows
            }