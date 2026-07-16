(function () {
  "use strict";

  // ---------- state ----------
  let tasks = [];

  // ---------- DOM refs ----------
  const taskInput   = document.getElementById("taskInput");
  const addBtn      = document.getElementById("addBtn");
  const taskList    = document.getElementById("taskList");
  const taskCount   = document.getElementById("taskCount");
  const clearBtn    = document.getElementById("clearCompletedBtn");

  // ---------- helpers ----------
  function save() {
    localStorage.setItem("todo-app-tasks", JSON.stringify(tasks));
  }

  function load() {
    try {
      const raw = localStorage.getItem("todo-app-tasks");
      if (raw) tasks = JSON.parse(raw);
    } catch (_) {
      tasks = [];
    }
  }

  function remainingCount() {
    return tasks.filter(t => !t.done).length;
  }

  function updateFooter() {
    const n = remainingCount();
    taskCount.textContent = n + " task" + (n !== 1 ? "s" : "") + " remaining";
  }

  // ---------- render ----------
  function render() {
    taskList.innerHTML = "";

    tasks.forEach(function (task, idx) {
      const li = document.createElement("li");
      li.className = "task-item" + (task.done ? " completed" : "");

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "task-checkbox";
      cb.checked = task.done;
      cb.setAttribute("aria-label", "Mark task as done");
      cb.addEventListener("change", function () {
        toggleTask(idx);
      });

      const span = document.createElement("span");
      span.className = "task-text";
      span.textContent = task.text;

      const delBtn = document.createElement("button");
      delBtn.className = "delete-btn";
      delBtn.innerHTML = "&#x2715;";
      delBtn.setAttribute("aria-label", "Delete task");
      delBtn.addEventListener("click", function () {
        deleteTask(idx);
      });

      li.appendChild(cb);
      li.appendChild(span);
      li.appendChild(delBtn);
      taskList.appendChild(li);
    });

    updateFooter();
    save();
  }

  // ---------- actions ----------
  function addTask() {
    const text = taskInput.value.trim();
    if (!text) return;

    tasks.push({ text: text, done: false });
    taskInput.value = "";
    taskInput.focus();
    render();
  }

  function toggleTask(idx) {
    if (idx < 0 || idx >= tasks.length) return;
    tasks[idx].done = !tasks[idx].done;
    render();
  }

  function deleteTask(idx) {
    if (idx < 0 || idx >= tasks.length) return;
    tasks.splice(idx, 1);
    render();
  }

  function clearCompleted() {
    tasks = tasks.filter(t => !t.done);
    render();
  }

  // ---------- event wiring ----------
  addBtn.addEventListener("click", addTask);
  taskInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") addTask();
  });
  clearBtn.addEventListener("click", clearCompleted);

  // ---------- init ----------
  load();
  render();
  taskInput.focus();
})();
