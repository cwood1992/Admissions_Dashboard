(function () {
  const data = window.SNAPSHOT_DATA;
  const repData = window.REP_HEALTH;
  const meta = document.getElementById("snapshot-meta");
  const tbody = document.querySelector("#cohort-table tbody");
  const repTbody = document.querySelector("#rep-table tbody");

  // Tab switching.
  document.querySelectorAll("#view-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view;
      document.querySelectorAll("#view-tabs button").forEach((b) =>
        b.classList.toggle("tab-active", b === btn)
      );
      document.querySelectorAll("main > section").forEach((s) => {
        s.hidden = s.dataset.view !== view;
      });
    });
  });

  if (!data || !Array.isArray(data.cohorts) || data.cohorts.length === 0) {
    meta.textContent =
      "No snapshot loaded. Run scripts/run_pipeline.py to populate dashboard/data/.";
    return;
  }

  meta.textContent = `Snapshot date: ${data.snapshot_date} · ${data.cohorts.length} cohorts · generated ${data.generated_at}`;

  const sorted = data.cohorts
    .slice()
    .sort((a, b) => {
      const da = Number(a.days_to_start ?? 9999);
      const db = Number(b.days_to_start ?? 9999);
      return da - db;
    });

  const fmt = (v) => (v === null || v === undefined || v === "" ? "—" : v);
  const fmtNum = (v) => (v === null || v === undefined || v === "" || Number.isNaN(Number(v)) ? "—" : v);

  const paceClass = {
    "above": "pace-above",
    "on-track": "pace-on",
    "below": "pace-below",
    "unknown": "pace-unknown",
  };

  for (const c of sorted) {
    const tr = document.createElement("tr");
    const basis = String(c.projection_basis || "");
    const placeholder = basis.includes("placeholder") || basis.startsWith("trivial");
    const pace = c.velocity_vs_historical;
    const paceLabel = pace ? `<span class="pace ${paceClass[pace] || ""}">${pace}</span>` : "—";

    tr.innerHTML = `
      <td class="cohort">${fmt(c.cohort)}</td>
      <td>${fmt(c.program)}</td>
      <td>${fmt(c.start_date)}</td>
      <td class="num">${fmt(c.days_to_start)}</td>
      <td class="num">${fmt(c.currently_enrolled)}</td>
      <td class="num">${fmt(c.wbh_count)}</td>
      <td class="num">${fmt(c.vip_count)}</td>
      <td class="num">${fmtNum(c.weekly_velocity)}</td>
      <td>${paceLabel}</td>
      <td class="num">${fmt(c.proj_low)}</td>
      <td class="num"><strong>${fmt(c.proj_mid)}</strong></td>
      <td class="num">${fmt(c.proj_high)}</td>
      <td class="basis">${fmt(basis)}${placeholder ? '<span class="tag-placeholder">placeholder</span>' : ""}</td>
    `;
    tbody.appendChild(tr);
  }

  // Render strategic + management views.
  const viewsData = window.VIEWS;
  if (viewsData) {
    // Strategic tab: financial-year roll-up with a current/next-year toggle.
    const fyViews = { current: viewsData.strategic, next: viewsData.strategic_next };

    function renderStrategic(view) {
      if (!view) return;
      document.getElementById("strategic-heading").textContent = `Financial Year ${view.label}`;
      const t = view.total;
      const projectedMid = t.proj_mid - t.actual_starts;
      document.getElementById("strategic-summary").innerHTML = `
        <table style="max-width:560px">
          <tbody>
            <tr><th>FY total starts (mid)</th><td class="num"><strong>${t.proj_mid}</strong></td></tr>
            <tr><th>Range (low–high)</th><td class="num">${t.proj_low} – ${t.proj_high}</td></tr>
            <tr><th>Booked (actual)</th><td class="num">${t.actual_starts}</td></tr>
            <tr><th>Projected (remaining, mid)</th><td class="num">${projectedMid}</td></tr>
            <tr><th>Revenue (mid)</th><td class="num">$${view.year_end_revenue_mid.toLocaleString()}</td></tr>
            <tr><th>Revenue range</th><td class="num">$${view.year_end_revenue_low.toLocaleString()} – $${view.year_end_revenue_high.toLocaleString()}</td></tr>
          </tbody>
        </table>
      `;
      const progTbody = document.querySelector("#program-table tbody");
      progTbody.innerHTML = "";
      for (const [program, p] of Object.entries(view.by_program)) {
        const projectedProg = p.proj_mid - p.actual_starts;
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="cohort">${program}</td>
          <td class="num">${p.cohort_count}</td>
          <td class="num">${p.actual_starts}</td>
          <td class="num">${projectedProg}</td>
          <td class="num"><strong>${p.proj_mid}</strong></td>
          <td class="num">${p.proj_low} – ${p.proj_high}</td>
          <td class="num">$${(p.proj_mid * view.revenue_per_start).toLocaleString()}</td>
        `;
        progTbody.appendChild(tr);
      }
      const cohTbody = document.querySelector("#fy-cohort-table tbody");
      cohTbody.innerHTML = "";
      for (const c of view.cohorts) {
        const isActual = c.status === "actual";
        const startsCell = isActual ? `${c.actual_starts}` : `${c.starts_mid}`;
        const rangeCell = isActual ? "—" : `${c.starts_low} – ${c.starts_high}`;
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="cohort">${c.cohort}</td>
          <td>${c.program}</td>
          <td>${c.start_date}</td>
          <td>${c.status}</td>
          <td class="num">${startsCell}</td>
          <td class="num">${rangeCell}</td>
        `;
        cohTbody.appendChild(tr);
      }
      document.getElementById("model-confidence").textContent = view.model_confidence_note;
    }

    // Label the toggle buttons from the actual FY labels and wire switching.
    const toggle = document.getElementById("fy-toggle");
    if (toggle) {
      const curBtn = toggle.querySelector('button[data-fy="current"]');
      const nextBtn = toggle.querySelector('button[data-fy="next"]');
      if (curBtn && fyViews.current) curBtn.textContent = fyViews.current.label;
      if (nextBtn && fyViews.next) nextBtn.textContent = fyViews.next.label;
      toggle.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          toggle.querySelectorAll("button").forEach((b) => b.classList.remove("fy-active"));
          btn.classList.add("fy-active");
          renderStrategic(fyViews[btn.dataset.fy]);
        });
      });
    }
    renderStrategic(fyViews.current);

    // Recognition tab: tuition earned pro rata across calendar years.
    const rec = viewsData.recognition;
    if (rec) {
      const years = rec.years;
      const yTbody = document.querySelector("#recognition-year-table tbody");
      yTbody.innerHTML = "";
      for (const y of years) {
        const b = rec.by_year[y];
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="cohort">${y}</td>
          <td class="num"><strong>$${b.earned_mid.toLocaleString()}</strong></td>
          <td class="num">$${b.earned_low.toLocaleString()} – $${b.earned_high.toLocaleString()}</td>
          <td class="num">$${b.earned_actual.toLocaleString()}</td>
          <td class="num">$${b.earned_projected.toLocaleString()}</td>
        `;
        yTbody.appendChild(tr);
      }
      // Per-cohort table gets one earned-revenue column per calendar year.
      const head = document.getElementById("recognition-cohort-head");
      for (const y of years) {
        const th = document.createElement("th");
        th.className = "num";
        th.textContent = y;
        head.appendChild(th);
      }
      const cTbody = document.querySelector("#recognition-cohort-table tbody");
      cTbody.innerHTML = "";
      for (const c of rec.cohorts) {
        let cells = `
          <td class="cohort">${c.cohort}</td>
          <td>${c.program}</td>
          <td>${c.start_date}</td>
          <td>${c.status}</td>
          <td class="num">$${c.revenue_mid.toLocaleString()}</td>
        `;
        for (const y of years) {
          const v = c.by_year[y] || 0;
          cells += `<td class="num">${v ? "$" + v.toLocaleString() : "—"}</td>`;
        }
        const tr = document.createElement("tr");
        tr.innerHTML = cells;
        cTbody.appendChild(tr);
      }
      document.getElementById("recognition-confidence").textContent = rec.model_confidence_note;
    }

    const m = viewsData.management;
    document.getElementById("management-headline").innerHTML = `
      <table style="max-width:520px">
        <tbody>
          <tr><th>FY${m.fiscal_year} starts (mid)</th><td class="num"><strong>${m.headline_starts_mid}</strong></td></tr>
          <tr><th>Range</th><td class="num">${m.headline_starts_low} – ${m.headline_starts_high}</td></tr>
          <tr><th>Booked to date</th><td class="num">${m.headline_actual_starts}</td></tr>
          <tr><th>Revenue (mid)</th><td class="num">$${m.headline_revenue_mid.toLocaleString()}</td></tr>
        </tbody>
      </table>
    `;
    document.getElementById("management-narrative").textContent = m.narrative;
    const flagsList = document.getElementById("management-flags");
    if (m.red_flagged_cohorts && m.red_flagged_cohorts.length) {
      for (const f of m.red_flagged_cohorts) {
        const li = document.createElement("li");
        li.innerHTML = `<strong>${f.cohort}</strong> (${f.days_to_start}d to start, ${f.program}): ${f.reason}`;
        flagsList.appendChild(li);
      }
    } else {
      flagsList.innerHTML = "<li class='muted'>None.</li>";
    }
  }

  // Render rep scorecards.
  // A rate is null when there is no sample; never render a sentinel as a number.
  const pct = (v, digits = 0) =>
    v === null || v === undefined ? "—" : (v * 100).toFixed(digits) + "%";
  const withN = (label, n) =>
    `${label}${n > 0 ? ` <span class="muted">(n=${n})</span>` : ""}`;

  if (repData && Array.isArray(repData.reps) && repData.reps.length) {
    const p = repData.params || {};
    const team = repData.team || {};
    const win = p.commitment_window_days ?? 45;
    document.getElementById("rep-th-near").textContent = `In ${win}d Window`;
    document.getElementById("rep-caption").textContent =
      `Forward pipeline = students in classes that have not started (stale listings in started classes are excluded). ` +
      `WBH and any-tag rates cover only classes ${win} days or less from start. ` +
      `vs Team averages each scored rate against the team rate (100 = team); rates with n under ${p.min_metric_sample ?? 10} are shown but not scored.`;

    const retentionCells = (r) => `
        <td class="num">${withN(pct(r.loss_rate_28d), r.retention_28d ? r.retention_28d.basis : 0)}</td>
        <td class="num">${withN(pct(r.durability ? r.durability.rate : null), r.durability ? r.durability.basis : 0)}</td>`;

    const sortedReps = repData.reps
      .slice()
      .sort((a, b) => (b.vs_team_avg ?? -1) - (a.vs_team_avg ?? -1));
    for (const r of sortedReps) {
      const tr = document.createElement("tr");
      const vs = r.vs_team_avg;
      const vsClass =
        vs === null || vs === undefined ? "vs-neutral" : vs >= 110 ? "vs-above" : vs <= 90 ? "vs-below" : "vs-on";
      tr.innerHTML = `
        <td class="cohort">${r.rep_name}</td>
        <td class="num">${r.forward_enrolled}</td>
        <td class="num">${r.near_enrolled}</td>
        <td class="num">${r.wbh_near} <span class="muted">(${pct(r.wbh_rate_near, 1)})</span></td>
        <td class="num">${r.tagged_near} <span class="muted">(${pct(r.tagged_rate_near)})</span></td>
        ${retentionCells(r)}
        <td class="num"><span class="pace ${vsClass}">${vs === null || vs === undefined ? "n/a" : vs.toFixed(0)}</span></td>
        <td class="basis">${r.note || "—"}</td>
      `;
      repTbody.appendChild(tr);
    }
    document.querySelector("#rep-table tfoot").innerHTML = `
      <tr>
        <td class="cohort">Team</td>
        <td class="num">${team.forward_enrolled ?? "—"}</td>
        <td class="num">${team.near_enrolled ?? "—"}</td>
        <td class="num">${team.wbh_near ?? 0} <span class="muted">(${pct(team.wbh_rate_near, 1)})</span></td>
        <td class="num">${team.tagged_near ?? 0} <span class="muted">(${pct(team.tagged_rate_near)})</span></td>
        ${retentionCells(team)}
        <td class="num">100</td>
        <td class="basis">—</td>
      </tr>`;

    // Outcome breakdown: where each lookback roster went.
    document.getElementById("rep-outcome-caption").textContent =
      `Each rep's forward roster from the lookback snapshot, classified today. ` +
      `Started = Active in the booked-class CCS. Listed in started class = still on the list in a class that started ` +
      `${p.stale_lost_after_days ?? 14}+ days ago (counted lost); under that is Pending. ` +
      `Unknown = gone after their class started but its booked CCS is not staged. ` +
      `Durable = (started + still enrolled) / (roster - pending - unknown).`;
    const outcomeBody = document.querySelector("#rep-outcome-table tbody");
    const lookbacks = [
      ["durability", p.durability_target_days ?? 60, p.durability_prior_date],
      ["retention_28d", p.loss_target_days ?? 28, p.loss_prior_date],
    ];
    for (const [key, days, priorDate] of lookbacks) {
      const label = priorDate ? `${days}d (${priorDate})` : `${days}d (no snapshot)`;
      const rows = repData.reps
        .map((r) => [r.rep_name, r[key]])
        .concat([["Team", team[key]]])
        .filter(([, m]) => m && m.n > 0);
      rows.forEach(([name, m], i) => {
        const o = m.outcomes;
        const tr = document.createElement("tr");
        if (i === 0) tr.className = "group-start";
        tr.innerHTML = `
          <td>${i === 0 ? label : ""}</td>
          <td class="cohort">${name}</td>
          <td class="num">${m.n}</td>
          <td class="num">${o.started}</td>
          <td class="num">${o.retained}</td>
          <td class="num">${o.lost_listed}</td>
          <td class="num">${o.gone}</td>
          <td class="num">${o.pending}</td>
          <td class="num">${o.unknown}</td>
          <td class="num">${pct(m.rate)}</td>`;
        outcomeBody.appendChild(tr);
      });
    }

    // Rep x upcoming-class matrix from the per-cohort rep breakdown.
    const excluded = new Set(p.excluded_names || []);
    const byCohort = data.reps_by_cohort || {};
    const repNames = Array.from(
      new Set(Object.values(byCohort).flat().map((r) => r.rep_name))
    ).filter((n) => !excluded.has(n)).sort();
    document.querySelector("#rep-matrix thead").innerHTML =
      `<tr><th>Class</th><th>Start</th><th class="num">Days</th>` +
      repNames.map((n) => `<th class="num">${n}</th>`).join("") +
      `<th class="num">Total</th></tr>`;
    const matrixBody = document.querySelector("#rep-matrix tbody");
    const cell = (r) =>
      !r || !r.rep_currently_enrolled
        ? `<td class="num muted">—</td>`
        : `<td class="num">${r.rep_currently_enrolled}<span class="cell-sub">W${r.rep_wbh} V${r.rep_vip} P${r.rep_priority} · cold ${r.rep_cold ?? 0}</span></td>`;
    for (const c of sorted) {
      const reps = (byCohort[c.cohort] || []).filter((r) => !excluded.has(r.rep_name));
      const total = reps.reduce((s, r) => s + Number(r.rep_currently_enrolled || 0), 0);
      if (!total) continue;
      const lookup = Object.fromEntries(reps.map((r) => [r.rep_name, r]));
      const sum = (k) => reps.reduce((s, r) => s + Number(r[k] || 0), 0);
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td class="cohort">${c.cohort}</td><td>${fmt(c.start_date)}</td><td class="num">${fmt(c.days_to_start)}</td>` +
        repNames.map((n) => cell(lookup[n])).join("") +
        cell({
          rep_currently_enrolled: total,
          rep_wbh: sum("rep_wbh"),
          rep_vip: sum("rep_vip"),
          rep_priority: sum("rep_priority"),
          rep_cold: sum("rep_cold"),
        });
      matrixBody.appendChild(tr);
    }
  }
})();
