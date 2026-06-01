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
    const s = viewsData.strategic;
    document.getElementById("strategic-summary").innerHTML = `
      <table style="max-width:520px">
        <tbody>
          <tr><th>Year-end starts (mid)</th><td class="num"><strong>${s.year_end_proj_mid}</strong></td></tr>
          <tr><th>Range (low–high)</th><td class="num">${s.year_end_proj_low} – ${s.year_end_proj_high}</td></tr>
          <tr><th>Revenue (mid)</th><td class="num">$${s.year_end_revenue_mid.toLocaleString()}</td></tr>
          <tr><th>Revenue range</th><td class="num">$${s.year_end_revenue_low.toLocaleString()} – $${s.year_end_revenue_high.toLocaleString()}</td></tr>
        </tbody>
      </table>
    `;
    const progTbody = document.querySelector("#program-table tbody");
    for (const [program, p] of Object.entries(s.by_program)) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="cohort">${program}</td>
        <td class="num">${p.cohort_count}</td>
        <td class="num">${p.proj_low}</td>
        <td class="num"><strong>${p.proj_mid}</strong></td>
        <td class="num">${p.proj_high}</td>
        <td class="num">$${(p.proj_mid * s.revenue_per_start).toLocaleString()}</td>
      `;
      progTbody.appendChild(tr);
    }
    document.getElementById("model-confidence").textContent = s.model_confidence_note;

    const m = viewsData.management;
    document.getElementById("management-headline").innerHTML = `
      <table style="max-width:520px">
        <tbody>
          <tr><th>Projected starts (mid)</th><td class="num"><strong>${m.headline_starts_mid}</strong></td></tr>
          <tr><th>Range</th><td class="num">${m.headline_starts_low} – ${m.headline_starts_high}</td></tr>
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
  if (repData && Array.isArray(repData.reps) && repData.reps.length) {
    const sortedReps = repData.reps.slice().sort((a, b) => b.quality_score - a.quality_score);
    for (const r of sortedReps) {
      const tr = document.createElement("tr");
      const durabilityLabel =
        r.durability < 0 ? "—" : (r.durability * 100).toFixed(0) + "%";
      const vsTeam = Number(r.vs_team_avg);
      const vsClass =
        r.is_new_rep
          ? "vs-neutral"
          : vsTeam >= 110
          ? "vs-above"
          : vsTeam <= 90
          ? "vs-below"
          : "vs-on";
      tr.innerHTML = `
        <td class="cohort">${r.rep_name}${r.is_new_rep ? ' <span class="tag-placeholder">new rep</span>' : ""}</td>
        <td class="num">${r.total_assigned}</td>
        <td class="num">${r.currently_enrolled}</td>
        <td class="num">${r.cancelled}</td>
        <td class="num">${(r.cancel_rate * 100).toFixed(1)}%</td>
        <td class="num">${(r.wbh_rate * 100).toFixed(1)}%</td>
        <td class="num">${durabilityLabel}${r.durability_basis_count > 0 ? ` <span class="muted">(n=${r.durability_basis_count})</span>` : ""}</td>
        <td class="num">${(r.quality_score * 100).toFixed(1)}</td>
        <td class="num"><span class="pace ${vsClass}">${vsTeam.toFixed(0)}</span></td>
        <td class="basis">${r.note || "—"}</td>
      `;
      repTbody.appendChild(tr);
    }
  }
})();
