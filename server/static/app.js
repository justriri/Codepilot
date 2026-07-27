(function () {
  const STAGE_LABELS = {
    create_sandbox: 'Provisioning sandbox',
    install_dependencies: 'Installing dependencies',
    start_application: 'Starting application',
    run_command: 'Running command',
    run_test_flow: 'Browser verification',
    stop_application: 'Stopping application',
    destroy_sandbox: 'Sandbox teardown',
    generate_verification_report: 'Generating report',
    create_file: 'Writing project file',
    read_file: 'Reading file',
    list_files: 'Listing files',
  };

  const jobsListContainer = document.getElementById('jobs-list-container');
  const lightbox = document.getElementById('lightbox');
  const lightboxImg = document.getElementById('lightbox-img');
  const toastContainer = document.getElementById('toast-container');
  let healthCache = null;
  let activeJobId = null;
  let activeJobIdFull = null;
  let allJobsCache = [];
  let jobFilter = 'all';
  let evidenceGallery = [];
  let lightboxIndex = 0;
  let lastReportHuman = '';
  let lastReportMachine = null;

  function showToast(message, type) {
    if (!toastContainer) return;
    toastContainer.appendChild(mk('div', { className: 'toast' + (type ? ' ' + type : ''), text: message }));
    setTimeout(function () {
      if (toastContainer.firstChild) toastContainer.firstChild.remove();
    }, 5000);
  }

  function friendlyError(err) {
    var msg = (err && err.message) ? String(err.message) : String(err || 'Unknown error');
    if (/^HTTP \d+/i.test(msg)) {
      var code = msg.replace(/^HTTP\s+/i, '');
      if (code === '400') return 'The request was invalid. Check your task specification.';
      if (code === '404') return 'That job was not found on the server.';
      if (code === '403') return 'You do not have permission to perform this action.';
      return 'The server returned an error (' + code + ').';
    }
    return msg;
  }

  function truncateId(id) {
    if (!id || id.length <= 20) return id;
    return id.slice(0, 10) + '…' + id.slice(-6);
  }

  function formatRelativeTime(ts) {
    if (!ts) return 'None';
    var ms = typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts;
    var diff = Date.now() - ms;
    var mins = Math.floor(diff / 60000);
    var hours = Math.floor(mins / 60);
    var days = Math.floor(hours / 24);
    if (mins < 1) return 'Just now';
    if (mins < 60) return mins + 'm ago';
    if (hours < 24) return hours + 'h ago';
    return days + 'd ago';
  }

  function jobHash(id) { return '#/job/' + id; }

  function parseRoute() {
    var hash = window.location.hash || '';
    if (hash.indexOf('#/job/') === 0) return { view: 'job', id: hash.slice(6) };
    if (hash === '#/submit') return { view: 'submit' };
    if (hash === '#/console' || hash.indexOf('#/') === 0) return { view: 'jobs' };
    return { view: 'landing' };
  }

  function setHash(path) {
    if (window.location.hash !== path) window.location.hash = path;
  }

  function getStoredJobs() {
    try { return JSON.parse(localStorage.getItem('codepilot_jobs') || '[]'); }
    catch (e) { return []; }
  }

  function storeJob(job) {
    var jobs = getStoredJobs().filter(function (j) { return j.id !== job.id; });
    jobs.unshift(job);
    localStorage.setItem('codepilot_jobs', JSON.stringify(jobs.slice(0, 50)));
  }

  function updateStoredJobStatus(id, status) {
    var jobs = getStoredJobs();
    var job = jobs.find(function (j) { return j.id === id; });
    if (job) { job.status = status; localStorage.setItem('codepilot_jobs', JSON.stringify(jobs)); }
  }

  function mergeJobs(serverJobs) {
    var byId = {};
    (serverJobs || []).forEach(function (j) {
      byId[j.id] = {
        id: j.id,
        request: j.request,
        status: j.status === 'done' ? 'done' : j.status === 'error' ? 'error' : j.status === 'running' ? 'running' : 'pending',
        submittedAt: j.created_at ? j.created_at * 1000 : Date.now(),
      };
    });
    getStoredJobs().forEach(function (j) {
      if (!byId[j.id]) byId[j.id] = j;
      else if (!byId[j.id].request && j.request) byId[j.id].request = j.request;
    });
    return Object.values(byId).sort(function (a, b) { return (b.submittedAt || 0) - (a.submittedAt || 0); });
  }

  async function fetchJobs() {
    try {
      var res = await fetch('/api/sessions');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      return mergeJobs(data.sessions || []);
    } catch (e) {
      return mergeJobs([]);
    }
  }

  function setHintText(text) {
    var el = document.getElementById('submit-hint-text');
    if (el) el.textContent = text;
  }

  async function renderEnvStatus() {
    var wrap = document.getElementById('env-status');
    var submitBtn = document.getElementById('submit-job-btn');
    var demoBtn = document.getElementById('demo-verification-btn');
    if (!wrap) return;
    try {
      var res = await fetch('/api/health');
      healthCache = await res.json();
    } catch (e) {
      healthCache = null;
    }
    clearChildren(wrap);
    if (!healthCache) {
      wrap.appendChild(mk('span', { className: 'env-chip warn', html: '<span class="env-chip-dot"></span> API unreachable' }));
      setHintText('Start the server with uvicorn, then refresh to check environment status.');
      return;
    }
    function chip(label, ok) {
      var el = mk('span', { className: 'env-chip ' + (ok ? 'ok' : 'warn') });
      el.appendChild(mk('span', { className: 'env-chip-dot' }));
      el.appendChild(document.createTextNode(label));
      return el;
    }
    wrap.appendChild(chip('E2B · ' + (healthCache.e2b_configured ? 'ready' : 'not configured'), healthCache.e2b_configured));
    wrap.appendChild(chip(healthCache.ai_provider + ' · ' + (healthCache.ai_configured ? 'ready' : 'not configured'), healthCache.ai_configured));
    setHintText(
      healthCache.full_jobs_ready
        ? 'Environment ready. Full agent jobs and E2B demo are available.'
        : healthCache.demo_ready
          ? 'E2B demo available. Set your AI provider key in .env for full agent jobs.'
          : 'Set E2B_API_KEY in .env to run verification jobs.'
    );
    if (demoBtn) demoBtn.disabled = !healthCache.demo_ready;
    if (submitBtn) submitBtn.disabled = !healthCache.full_jobs_ready;
  }

  function updateTopbarCrumb(viewId, jobId) {
    var el = document.getElementById('topbar-breadcrumb');
    if (!el) return;
    clearChildren(el);
    if (viewId === 'jobs-view') {
      el.appendChild(mk('span', { className: 'crumb-current', text: 'Jobs' }));
    } else if (viewId === 'submit-view') {
      el.appendChild(mk('span', { className: 'crumb-current', text: 'Submit job' }));
    } else if (viewId === 'job-detail-view') {
      el.appendChild(mk('span', { text: 'Jobs' }));
      el.appendChild(mk('span', { className: 'crumb-sep', text: '/' }));
      el.appendChild(mk('span', { className: 'crumb-current', text: jobId ? truncateId(jobId) : 'Job detail' }));
    }
  }

  function setActiveNav(viewId) {
    document.querySelectorAll('.nav-item').forEach(function (n) { n.classList.remove('active'); });
    var navBtn = document.querySelector('.nav-item[data-view="' + viewId + '"]');
    if (navBtn) navBtn.classList.add('active');
  }

  function showView(viewId) {
    document.querySelectorAll('.view').forEach(function (v) { v.classList.remove('active'); });
    document.getElementById(viewId).classList.add('active');
    if (viewId === 'jobs-view' || viewId === 'submit-view') setActiveNav(viewId);
    updateTopbarCrumb(viewId, viewId === 'job-detail-view' ? activeJobIdFull : null);
  }

  document.getElementById('nav-jobs').addEventListener('click', function () {
    enterConsole(); refreshJobsList(); showView('jobs-view'); setHash('#/console');
  });
  document.getElementById('nav-submit').addEventListener('click', function () {
    enterConsole(); renderEnvStatus(); showView('submit-view'); setHash('#/submit');
  });
  document.getElementById('jobs-new-btn').addEventListener('click', function () {
    renderEnvStatus(); showView('submit-view'); setHash('#/submit');
  });
  document.getElementById('back-to-jobs-btn').addEventListener('click', function () {
    refreshJobsList(); showView('jobs-view'); setHash('#/console');
  });

  document.querySelectorAll('.job-filter-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      jobFilter = tab.getAttribute('data-filter') || 'all';
      document.querySelectorAll('.job-filter-tab').forEach(function (t) { t.classList.remove('active'); });
      tab.classList.add('active');
      renderJobsList(allJobsCache);
    });
  });

  lightbox.addEventListener('click', function () { closeLightbox(); });

  function mk(tag, opts) {
    var n = document.createElement(tag);
    if (opts) {
      if (opts.className) n.className = opts.className;
      if (opts.text !== undefined) n.textContent = opts.text;
      if (opts.html !== undefined) n.innerHTML = opts.html;
      if (opts.title) n.title = opts.title;
    }
    return n;
  }

  function clearChildren(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function statusBadge(status) {
    var map = { running: 'Running', done: 'Passed', error: 'Failed', pending: 'Pending' };
    var badge = mk('span', { className: 'status-badge status-' + status });
    badge.appendChild(mk('span', { className: 'dot' }));
    badge.appendChild(document.createTextNode(map[status] || status));
    return badge;
  }

  function filterJobs(jobs) {
    if (jobFilter === 'all') return jobs;
    if (jobFilter === 'running') return jobs.filter(function (j) { return j.status === 'running' || j.status === 'pending'; });
    if (jobFilter === 'done') return jobs.filter(function (j) { return j.status === 'done'; });
    if (jobFilter === 'error') return jobs.filter(function (j) { return j.status === 'error'; });
    return jobs;
  }

  function appendMobileLabel(parent, text) {
    parent.appendChild(mk('span', { className: 'job-mobile-label', text: text }));
  }

  function renderJobsList(jobs) {
    allJobsCache = jobs || [];
    clearChildren(jobsListContainer);
    var list = filterJobs(allJobsCache);
    if (!list.length) {
      var empty = mk('div', { className: 'empty-state' });
      empty.appendChild(mk('span', { className: 'micro-label', text: 'Jobs' }));
      empty.appendChild(mk('div', {
        className: 'empty-state-title',
        text: allJobsCache.length ? 'No jobs match this filter' : 'No verification jobs yet',
      }));
      empty.appendChild(mk('div', {
        text: allJobsCache.length
          ? 'Try another filter or submit a new job.'
          : 'Run the E2B demo to see the full pipeline. No AI key required.',
      }));
      if (!allJobsCache.length) {
        var actions = mk('div', { className: 'empty-state-actions' });
        var demoBtn = mk('button', { className: 'btn btn-primary', text: 'Run E2B demo' });
        demoBtn.addEventListener('click', function () { runDemo(); });
        var submitLink = mk('button', { className: 'btn btn-ghost', text: 'Submit a job' });
        submitLink.addEventListener('click', function () { enterConsole(); showView('submit-view'); setHash('#/submit'); });
        actions.appendChild(demoBtn);
        actions.appendChild(submitLink);
        empty.appendChild(actions);
      }
      jobsListContainer.appendChild(empty);
      return;
    }
    var wrap = mk('div', { className: 'jobs-table-wrap' });
    var tableHeader = mk('div', { className: 'jobs-table-header' });
    ['Job ID', 'Request', 'Status', 'Updated'].forEach(function (label) {
      tableHeader.appendChild(mk('span', { className: 'micro-label', text: label }));
    });
    wrap.appendChild(tableHeader);
    list.forEach(function (job) {
      var row = mk('div', { className: 'job-row-card' });
      var idCell = mk('div', { className: 'job-id-cell', text: truncateId(job.id), title: job.id });
      appendMobileLabel(idCell, 'Job ID');
      row.appendChild(idCell);
      var reqCell = mk('div', { className: 'job-request-cell', text: job.request || 'None', title: job.request || '' });
      appendMobileLabel(reqCell, 'Request');
      row.appendChild(reqCell);
      var statusCell = mk('div');
      appendMobileLabel(statusCell, 'Status');
      statusCell.appendChild(statusBadge(job.status || 'pending'));
      row.appendChild(statusCell);
      var timeCell = mk('div', { className: 'job-time-cell', text: formatRelativeTime(job.submittedAt) });
      appendMobileLabel(timeCell, 'Updated');
      row.appendChild(timeCell);
      row.addEventListener('click', function () { openJobDetail(job.id, job.request); });
      wrap.appendChild(row);
    });
    var panel = mk('div', { className: 'panel' });
    panel.appendChild(mk('div', { className: 'panel-header', html: '<span class="micro-label">Recent jobs</span>' }));
    var panelBody = mk('div', { className: 'panel-body panel-body-flush' });
    panelBody.appendChild(wrap);
    panel.appendChild(panelBody);
    jobsListContainer.appendChild(panel);
  }

  async function refreshJobsList() {
    var jobs = await fetchJobs();
    renderJobsList(jobs);
    return jobs;
  }

  const EXAMPLE_TASKS = {
    static: 'Build a simple static website:\n\n1. Create index.html with h1 "Welcome", button #go that sets #msg to "Done"\n2. Start: python3 -m http.server 3000\n3. Browser verify: navigate /, click #go, assert #msg is "Done"\n4. Generate verification report',
  };

  document.querySelectorAll('.example-pill').forEach(function (pill) {
    pill.addEventListener('click', function () {
      if (pill.getAttribute('data-example') === 'demo') {
        enterConsole(); showView('submit-view'); runDemo();
        return;
      }
      var key = pill.getAttribute('data-example');
      if (EXAMPLE_TASKS[key]) document.getElementById('job-spec-input').value = EXAMPLE_TASKS[key];
    });
  });

  document.getElementById('submit-job-btn').addEventListener('click', async function () {
    var input = document.getElementById('job-spec-input');
    var text = input.value.trim();
    if (!text) { showToast('Enter a request before submitting.', 'error'); return; }
    var btn = document.getElementById('submit-job-btn');
    btn.disabled = true;
    btn.textContent = 'Submitting…';
    try {
      var res = await fetch('/api/sessions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request: text }),
      });
      var data = await res.json();
      if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
      storeJob({ id: data.session_id, request: text, status: 'running', submittedAt: Date.now() });
      input.value = '';
      showToast('Job submitted', 'success');
      openJobDetail(data.session_id, text);
    } catch (err) {
      showToast('Could not submit job: ' + friendlyError(err), 'error');
    } finally {
      btn.disabled = !(healthCache && healthCache.full_jobs_ready);
      btn.textContent = 'Submit job';
    }
  });

  async function runDemo() {
    var btn = document.getElementById('demo-verification-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Starting…'; }
    try {
      var res = await fetch('/api/demo/verification', { method: 'POST' });
      var data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message || ('HTTP ' + res.status));
      var label = 'E2B screenshot demo (no AI)';
      storeJob({ id: data.session_id, request: label, status: 'running', submittedAt: Date.now() });
      showToast('E2B demo started', 'success');
      enterConsole();
      openJobDetail(data.session_id, label);
    } catch (err) {
      showToast('Demo failed: ' + friendlyError(err), 'error');
    } finally {
      if (btn) {
        btn.disabled = !(healthCache && healthCache.demo_ready);
        btn.textContent = 'Run E2B demo';
      }
    }
  }

  document.getElementById('demo-verification-btn').addEventListener('click', runDemo);

  var activeSocket = null;

  function showTimelineLoading(timeline) {
    clearChildren(timeline);
    var row = mk('div', { className: 'timeline-loading' });
    row.appendChild(mk('span', { className: 'timeline-loading-dot' }));
    row.appendChild(document.createTextNode('Waiting for sandbox…'));
    timeline.appendChild(row);
  }

  function clearTimelineLoading(timeline) {
    var loading = timeline.querySelector('.timeline-loading');
    if (loading) loading.remove();
  }

  function setJobDetailId(jobId) {
    activeJobIdFull = jobId;
    var el = document.getElementById('detail-job-id');
    el.textContent = truncateId(jobId);
    el.title = jobId;
  }

  function openJobDetail(jobId, requestText, fromRoute) {
    if (!fromRoute && activeJobIdFull === jobId && document.getElementById('job-detail-view').classList.contains('active')) {
      setHash(jobHash(jobId));
      return;
    }
    activeJobId = jobId;
    evidenceGallery = [];
    lastReportHuman = '';
    lastReportMachine = null;
    if (activeSocket) { try { activeSocket.close(); } catch (e) {} activeSocket = null; }
    enterConsole();
    if (!fromRoute) setHash(jobHash(jobId));
    setJobDetailId(jobId);
    document.getElementById('detail-job-request').textContent = requestText || 'None';
    var badgeEl = document.getElementById('detail-status-badge');
    badgeEl.className = 'status-badge status-running';
    badgeEl.innerHTML = '<span class="dot"></span>Running';
    var timeline = document.getElementById('pipeline-timeline');
    showTimelineLoading(timeline);
    ['sandbox-status-card', 'evidence-card', 'report-card', 'test-results-card', 'logs-card'].forEach(function (id) {
      document.getElementById(id).style.display = 'none';
    });
    document.getElementById('evidence-grid').innerHTML = '';
    document.getElementById('video-link-container').innerHTML = '';
    showView('job-detail-view');
    updateTopbarCrumb('job-detail-view', jobId);
    var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var socket = new WebSocket(proto + '//' + window.location.host + '/api/sessions/' + jobId + '/stream');
    activeSocket = socket;
    socket.addEventListener('message', function (ev) {
      var event;
      try { event = JSON.parse(ev.data); } catch (e) { return; }
      clearTimelineLoading(timeline);
      handleSessionEvent(jobId, event, timeline);
    });
    socket.addEventListener('error', function () {
      clearTimelineLoading(timeline);
      appendTimelineItem(timeline, { state: 'error', label: 'Connection error', detail: 'Lost connection to the job stream.' });
    });
  }

  function appendTimelineItem(timeline, opts) {
    var item = mk('div', { className: 'timeline-item tl-' + (opts.state || 'pending') });
    item.appendChild(mk('div', { className: 'timeline-marker', html: '<div class="timeline-dot"></div>' }));
    var content = mk('div', { className: 'timeline-content' });
    var label = mk('div', { className: 'timeline-label' });
    label.appendChild(mk('span', { text: opts.label }));
    if (opts.time) label.appendChild(mk('span', { className: 'timeline-time', text: opts.time }));
    content.appendChild(label);
    if (opts.detail) content.appendChild(mk('div', { className: 'timeline-detail', text: opts.detail }));
    if (opts.note) content.appendChild(mk('div', { className: 'timeline-note', text: opts.note }));
    item.appendChild(content);
    timeline.appendChild(item);
    return item;
  }

  function revealCard(cardId) {
    var card = document.getElementById(cardId);
    if (!card) return;
    card.style.display = 'block';
    card.classList.remove('card-reveal');
    void card.offsetWidth;
    card.classList.add('card-reveal');
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function renderSandboxStatus(result) {
    revealCard('sandbox-status-card');
    var body = document.getElementById('sandbox-status-body');
    clearChildren(body);
    var rows = [];
    if (result.sandbox_id) rows.push(['Sandbox', result.sandbox_id]);
    if (result.status) rows.push(['Status', result.status]);
    if (result.internal_url) rows.push(['Internal URL', result.internal_url]);
    if (result.browser_engine) rows.push(['Browser', result.browser_engine]);
    rows.forEach(function (pair) {
      var row = mk('div', { className: 'kv-row' });
      row.appendChild(mk('span', { className: 'kv-label', text: pair[0] }));
      row.appendChild(mk('span', { className: 'kv-value', text: pair[1] }));
      body.appendChild(row);
    });
  }

  function evidenceTitleForStep(path, steps) {
    if (Array.isArray(steps)) {
      for (var i = 0; i < steps.length; i++) {
        if (steps[i] && steps[i].screenshot === path) {
          var label = 'Step ' + steps[i].index + ': ' + (steps[i].action || '');
          if (steps[i].selector) label += ' (' + steps[i].selector + ')';
          return label;
        }
      }
    }
    return path.split('/').pop();
  }

  function openLightboxAt(index) {
    if (!evidenceGallery.length) return;
    lightboxIndex = (index + evidenceGallery.length) % evidenceGallery.length;
    var item = evidenceGallery[lightboxIndex];
    lightboxImg.src = item.url;
    lightboxImg.alt = item.title;
    document.getElementById('lightbox-caption').textContent = item.title + ' (' + (lightboxIndex + 1) + '/' + evidenceGallery.length + ')';
    lightbox.classList.add('visible');
  }

  function closeLightbox() {
    lightbox.classList.remove('visible');
  }

  function renderEvidence(jobId, screenshots, video, steps) {
    if ((!screenshots || !screenshots.length) && !video) return;
    revealCard('evidence-card');
    var grid = document.getElementById('evidence-grid');
    var videoContainer = document.getElementById('video-link-container');
    (screenshots || []).forEach(function (path) {
      var url = '/api/sessions/' + jobId + '/evidence/' + path;
      var title = evidenceTitleForStep(path, steps);
      evidenceGallery.push({ url: url, title: title });
      var idx = evidenceGallery.length - 1;
      var thumb = mk('div', { className: 'evidence-thumb' });
      var imgWrap = mk('div', { className: 'evidence-thumb-img-wrap' });
      var img = mk('img');
      img.src = url;
      img.alt = title;
      imgWrap.appendChild(img);
      thumb.appendChild(imgWrap);
      thumb.appendChild(mk('div', { className: 'evidence-label', text: title }));
      thumb.addEventListener('click', function (e) {
        e.stopPropagation();
        openLightboxAt(idx);
      });
      grid.appendChild(thumb);
    });
    if (video) {
      var link = mk('a', { className: 'video-link', text: 'Recording · ' + video.split('/').pop() });
      link.href = '/api/sessions/' + jobId + '/evidence/' + video;
      link.target = '_blank';
      videoContainer.appendChild(link);
    }
  }

  function highlightJson(jsonStr) {
    var escaped = jsonStr.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return escaped.replace(/("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (m) {
      var cls = 'json-number';
      if (/^"/.test(m)) cls = /:$/.test(m) ? 'json-key' : 'json-string';
      else if (/true|false/.test(m)) cls = 'json-bool';
      else if (/null/.test(m)) cls = 'json-null';
      return '<span class="' + cls + '">' + m + '</span>';
    });
  }

  function renderReport(reportText, machineReadable) {
    revealCard('report-card');
    var body = document.getElementById('report-body');
    clearChildren(body);
    lastReportHuman = reportText || '';
    if (machineReadable) lastReportMachine = machineReadable;

    var hasJson = !!lastReportMachine;
    var looksLikeJson = !hasJson && reportText && /^[\s[{]/.test(reportText.trim());
    if (looksLikeJson) {
      try { lastReportMachine = JSON.parse(reportText); hasJson = true; } catch (e) {}
    }

    if (hasJson) {
      var tabs = mk('div', { className: 'report-tabs' });
      var humanTab = mk('button', { className: 'report-tab active', text: 'Human' });
      humanTab.type = 'button';
      humanTab.setAttribute('data-tab', 'human');
      var machineTab = mk('button', { className: 'report-tab', text: 'Machine' });
      machineTab.type = 'button';
      machineTab.setAttribute('data-tab', 'machine');
      tabs.appendChild(humanTab);
      tabs.appendChild(machineTab);
      body.appendChild(tabs);
      var humanPane = mk('div', { className: 'report-pane active' });
      humanPane.setAttribute('data-pane', 'human');
      humanPane.appendChild(mk('div', { className: 'report-text', text: lastReportHuman || '(No markdown report)' }));
      var jsonStr = JSON.stringify(lastReportMachine, null, 2);
      var machinePane = mk('div', { className: 'report-pane' });
      machinePane.setAttribute('data-pane', 'machine');
      machinePane.appendChild(mk('pre', { className: 'json-block', html: highlightJson(jsonStr) }));
      body.appendChild(humanPane);
      body.appendChild(machinePane);
      tabs.querySelectorAll('.report-tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
          var target = tab.getAttribute('data-tab');
          tabs.querySelectorAll('.report-tab').forEach(function (t) { t.classList.remove('active'); });
          body.querySelectorAll('.report-pane').forEach(function (p) { p.classList.remove('active'); });
          tab.classList.add('active');
          var pane = body.querySelector('.report-pane[data-pane="' + target + '"]');
          if (pane) pane.classList.add('active');
        });
      });
    } else {
      body.appendChild(mk('div', { className: 'report-text', text: reportText }));
    }
  }

  function renderTestResultsCard(mr) {
    if (!mr || !mr.tests) return;
    revealCard('test-results-card');
    var body = document.getElementById('test-results-body');
    clearChildren(body);
    var statusKeyMap = { PASS: 'done', FAIL: 'error' };
    var statusRow = mk('div', { className: 'kv-row' });
    statusRow.appendChild(mk('span', { className: 'kv-label', text: 'Overall status' }));
    var valueWrap = mk('span', { className: 'kv-value' });
    valueWrap.appendChild(statusBadge(statusKeyMap[mr.status] || 'pending'));
    statusRow.appendChild(valueWrap);
    body.appendChild(statusRow);
    [['Total', mr.tests.total], ['Passed', mr.tests.passed], ['Failed', mr.tests.failed]].forEach(function (pair) {
      var row = mk('div', { className: 'kv-row' });
      row.appendChild(mk('span', { className: 'kv-label', text: pair[0] }));
      row.appendChild(mk('span', { className: 'kv-value', text: String(pair[1]) }));
      body.appendChild(row);
    });
  }

  function renderLogsCard(mr) {
    if (!mr) return;
    var logs = (mr.evidence && mr.evidence.logs) || [];
    if (!logs.length) return;
    revealCard('logs-card');
    var body = document.getElementById('logs-body');
    clearChildren(body);
    body.appendChild(mk('div', { className: 'logs-box', text: logs.join('\n') }));
  }

  function handleSessionEvent(jobId, event, timeline) {
    var time = new Date().toLocaleTimeString();
    if (event.type === 'iteration_start') return;

    if (event.type === 'bootstrap_progress') {
      var items = timeline.querySelectorAll('.timeline-item.tl-running');
      var lastRunning = items[items.length - 1];
      if (lastRunning) {
        var content = lastRunning.querySelector('.timeline-content');
        var detailEl = content.querySelector('.timeline-bootstrap-detail');
        if (!detailEl) {
          detailEl = mk('div', { className: 'timeline-detail timeline-bootstrap-detail' });
          content.appendChild(detailEl);
        }
        detailEl.textContent = event.message;
      }
      return;
    }

    if (event.type === 'tool_call') {
      appendTimelineItem(timeline, { state: 'running', label: STAGE_LABELS[event.name] || event.name, time: time });
      return;
    }

    if (event.type === 'tool_result') {
      var running = timeline.querySelectorAll('.timeline-item.tl-running');
      var lastRunning = running[running.length - 1];
      if (lastRunning) {
        var result = event.result || {};
        var failed = result.success === false || result.error;
        lastRunning.className = 'timeline-item tl-' + (failed ? 'error' : 'done');
        if (event.name === 'create_sandbox' || event.name === 'start_application') renderSandboxStatus(result);
        if (event.name === 'run_test_flow') {
          renderEvidence(jobId, result.screenshots, result.video, result.steps);
          if (result.simple_report && result.simple_report.text) {
            lastRunning.querySelector('.timeline-content').appendChild(mk('div', { className: 'timeline-detail', text: result.simple_report.text }));
          }
        }
        if (event.name === 'generate_verification_report') {
          if (result.content) renderReport(result.content, result.machine_readable);
          else if (result.machine_readable) renderReport('', result.machine_readable);
        }
        if (event.name === 'generate_verification_report' && result.machine_readable) {
          renderTestResultsCard(result.machine_readable);
          renderLogsCard(result.machine_readable);
          var grid = document.getElementById('evidence-grid');
          if (grid && !grid.children.length && result.machine_readable.evidence) {
            renderEvidence(jobId, result.machine_readable.evidence.screenshots, result.machine_readable.evidence.video);
          }
        }
        if (failed && result.error) {
          lastRunning.querySelector('.timeline-content').appendChild(mk('div', { className: 'timeline-detail', text: result.error }));
        }
      }
      return;
    }

    if (event.type === 'agent_text' || event.type === 'final_summary') {
      var last = timeline.children[timeline.children.length - 1];
      if (last && last.querySelector('.timeline-content')) {
        last.querySelector('.timeline-content').appendChild(mk('div', { className: 'timeline-note', text: (event.text || '').slice(0, 300) }));
      }
      return;
    }

    if (event.type === 'error') {
      appendTimelineItem(timeline, { state: 'error', label: 'Pipeline error', detail: event.message, time: time });
      return;
    }

    if (event.type === 'session_done') {
      document.getElementById('detail-status-badge').className = 'status-badge status-done';
      document.getElementById('detail-status-badge').innerHTML = '<span class="dot"></span>Passed';
      updateStoredJobStatus(jobId, 'done');
      if (event.result) {
        var text = typeof event.result === 'string' ? event.result : JSON.stringify(event.result, null, 2);
        renderReport(text, typeof event.result === 'object' ? event.result : null);
      }
      return;
    }

    if (event.type === 'session_error') {
      document.getElementById('detail-status-badge').className = 'status-badge status-error';
      document.getElementById('detail-status-badge').innerHTML = '<span class="dot"></span>Failed';
      updateStoredJobStatus(jobId, 'error');
      appendTimelineItem(timeline, { state: 'error', label: 'Session failed', detail: event.message, time: time });
    }
  }

  async function checkBackendStatus() {
    var el = document.getElementById('backend-status');
    if (!el) return;
    var textEl = el.querySelector('.connection-text');
    try {
      var res = await fetch('/api/health');
      if (!res.ok) throw new Error('non-200');
      healthCache = await res.json();
      el.className = 'connection-pill connected';
      textEl.textContent = healthCache.demo_ready ? 'Backend · ready' : 'E2B · not configured';
    } catch (e) {
      el.className = 'connection-pill unreachable';
      textEl.textContent = 'Backend · offline';
    }
  }

  document.getElementById('copy-job-link-btn').addEventListener('click', function () {
    if (!activeJobIdFull) return;
    var url = window.location.origin + window.location.pathname + jobHash(activeJobIdFull);
    navigator.clipboard.writeText(url).then(function () {
      showToast('Job link copied', 'success');
    }).catch(function () {
      showToast('Could not copy link', 'error');
    });
  });

  document.getElementById('copy-job-id-btn').addEventListener('click', function () {
    if (!activeJobIdFull) return;
    navigator.clipboard.writeText(activeJobIdFull).then(function () {
      showToast('Job ID copied', 'success');
    }).catch(function () {
      showToast('Could not copy ID', 'error');
    });
  });

  function enterConsole() {
    closeMobileNav();
    document.getElementById('landing-page').style.display = 'none';
    document.querySelector('.app-shell').style.display = 'flex';
  }

  function showLanding() {
    document.getElementById('landing-page').style.display = 'flex';
    document.querySelector('.app-shell').style.display = 'none';
    window.scrollTo(0, 0);
  }

  function closeMobileNav() {
    var nav = document.getElementById('site-nav');
    var overlay = document.getElementById('site-nav-overlay');
    var menuBtn = document.getElementById('mobile-menu-btn');
    if (!nav || !overlay) return;
    nav.classList.remove('open');
    overlay.classList.remove('visible');
    overlay.setAttribute('aria-hidden', 'true');
    if (menuBtn) {
      menuBtn.setAttribute('aria-expanded', 'false');
      menuBtn.setAttribute('aria-label', 'Open menu');
    }
    document.body.classList.remove('nav-open');
  }

  function initMobileNav() {
    var menuBtn = document.getElementById('mobile-menu-btn');
    var nav = document.getElementById('site-nav');
    var overlay = document.getElementById('site-nav-overlay');
    if (!menuBtn || !nav || !overlay) return;

    function setOpen(open) {
      nav.classList.toggle('open', open);
      overlay.classList.toggle('visible', open);
      overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      menuBtn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      document.body.classList.toggle('nav-open', open);
    }

    menuBtn.addEventListener('click', function () {
      setOpen(!nav.classList.contains('open'));
    });
    overlay.addEventListener('click', closeMobileNav);
    nav.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', closeMobileNav);
    });
    window.addEventListener('resize', function () {
      if (window.innerWidth > 768) closeMobileNav();
    });
  }

  function goHome() {
    setHash('');
    showLanding();
  }

  async function applyRoute() {
    var route = parseRoute();
    if (route.view === 'landing') {
      showLanding();
      return;
    }
    enterConsole();
    if (route.view === 'submit') {
      await renderEnvStatus();
      showView('submit-view');
      return;
    }
    if (route.view === 'job' && route.id) {
      if (activeJobIdFull === route.id && document.getElementById('job-detail-view').classList.contains('active')) return;
      try {
        var res = await fetch('/api/sessions/' + encodeURIComponent(route.id));
        if (res.ok) {
          var data = await res.json();
          openJobDetail(route.id, data.request, true);
          return;
        }
      } catch (e) {}
      openJobDetail(route.id, 'None', true);
      return;
    }
    await refreshJobsList();
    showView('jobs-view');
  }

  document.addEventListener('keydown', function (e) {
    if (!lightbox.classList.contains('visible')) return;
    if (e.key === 'Escape') { e.preventDefault(); closeLightbox(); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); openLightboxAt(lightboxIndex - 1); }
    if (e.key === 'ArrowRight') { e.preventDefault(); openLightboxAt(lightboxIndex + 1); }
  });

  var consoleBrand = document.getElementById('console-brand-btn');
  if (consoleBrand) consoleBrand.addEventListener('click', goHome);
  var topbarHome = document.getElementById('topbar-home-btn');
  if (topbarHome) topbarHome.addEventListener('click', goHome);
  var landingBrand = document.getElementById('landing-brand-btn');
  if (landingBrand) landingBrand.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });

  function initPipelineCarousel() {
    var carousel = document.getElementById('pipeline-carousel');
    var prev = document.getElementById('pipeline-prev');
    var next = document.getElementById('pipeline-next');
    if (!carousel || !prev || !next) return;

    function scrollStep(direction) {
      var card = carousel.querySelector('.pipeline-step');
      var gap = 16;
      var amount = card ? card.offsetWidth + gap : 320;
      carousel.scrollBy({ left: direction * amount, behavior: 'smooth' });
    }

    function updateButtons() {
      var maxScroll = carousel.scrollWidth - carousel.clientWidth;
      prev.disabled = carousel.scrollLeft <= 4;
      next.disabled = carousel.scrollLeft >= maxScroll - 4;
    }

    prev.addEventListener('click', function () { scrollStep(-1); });
    next.addEventListener('click', function () { scrollStep(1); });
    carousel.addEventListener('scroll', updateButtons, { passive: true });
    window.addEventListener('resize', updateButtons);
    updateButtons();
  }

  function initNavScrollSpy() {
    var links = document.querySelectorAll('.site-nav-link[data-section]');
    if (!links.length) return;
    var sections = [];
    links.forEach(function (link) {
      var id = link.getAttribute('data-section');
      var el = document.getElementById(id);
      if (el) sections.push({ id: id, el: el, link: link });
    });
    if (!sections.length) return;

    function setActive(id) {
      links.forEach(function (link) {
        link.classList.toggle('is-active', link.getAttribute('data-section') === id);
      });
    }

    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function (entries) {
        var visible = entries.filter(function (e) { return e.isIntersecting; })
          .sort(function (a, b) { return b.intersectionRatio - a.intersectionRatio; });
        if (visible.length) setActive(visible[0].target.id);
      }, { rootMargin: '-40% 0px -45% 0px', threshold: [0, 0.25, 0.5] });
      sections.forEach(function (s) { observer.observe(s.el); });
    }

    links.forEach(function (link) {
      link.addEventListener('click', function () {
        setActive(link.getAttribute('data-section'));
      });
    });
    setActive(sections[0].id);
  }

  function initFloatingHeader() {
    var header = document.getElementById('site-header');
    if (!header) return;
    function onScroll() {
      header.classList.toggle('is-scrolled', window.scrollY > 20);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  checkBackendStatus();
  initMobileNav();
  initNavScrollSpy();
  initFloatingHeader();
  initPipelineCarousel();
  applyRoute();
  window.addEventListener('hashchange', function () {
    closeMobileNav();
    applyRoute();
  });

  function enterDashboard() { setHash('#/console'); applyRoute(); }
  document.getElementById('landing-enter-btn').addEventListener('click', enterDashboard);
  document.getElementById('landing-hero-btn').addEventListener('click', enterDashboard);
  var scrollBtn = document.getElementById('landing-scroll-btn');
  if (scrollBtn) {
    scrollBtn.addEventListener('click', function () {
      var target = document.getElementById('how-it-works');
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
})();
