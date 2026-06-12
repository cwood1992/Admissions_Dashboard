/* Cash Position dashboard. Reads window.CASHFLOW (written by
   ledger/build_cashflow.py). All aggregation to months happens here —
   the Python layer ships raw per-tranche events only. */
(function () {
  'use strict';

  const DATA = window.CASHFLOW;
  if (!DATA) { document.body.innerHTML = '<p style="padding:2rem">cashflow.js missing — run <code>python ledger\\build_cashflow.py</code></p>'; return; }

  const FUNDS = DATA.funds; // ["VA","PELL","SEOG","SUB","UNSUB","PLUS","SCHOL"]
  const FUND_LABELS = { VA: 'VA', PELL: 'Pell', SEOG: 'SEOG', SUB: 'Sub loan', UNSUB: 'Unsub loan', PLUS: 'PLUS loan', SCHOL: 'Scholarship' };
  const TODAY = new Date().toISOString().slice(0, 10);

  const css = getComputedStyle(document.documentElement);
  const token = name => css.getPropertyValue(name).trim();
  const FUND_COLORS = {};
  FUNDS.forEach((f, i) => { FUND_COLORS[f] = token(`--series-${i + 1}`) || '#888'; });

  // ------------------------------------------------------------ state ----
  const state = { scenario: 'mid', kinds: new Set(['expected', 'projected']) };

  function eventAmount(e) {
    if (e.kind !== 'projected') return e.amount;
    if (state.scenario === 'low') return e.low;
    if (state.scenario === 'high') return e.high;
    return e.amount;
  }
  const visible = e => state.kinds.has(e.kind);

  // -------------------------------------------------------- formatting ----
  const fmt$ = v => '$' + Math.round(v).toLocaleString('en-US');
  const fmtK = v => Math.abs(v) >= 1e6 ? '$' + (v / 1e6).toFixed(1) + 'M'
    : Math.abs(v) >= 1e3 ? '$' + Math.round(v / 1e3) + 'k' : '$' + Math.round(v);
  const fmtDate = iso => new Date(iso + 'T00:00:00')
    .toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  const monthLabel = m => new Date(m + '-01T00:00:00')
    .toLocaleDateString('en-US', { month: 'short', year: '2-digit' });

  // ------------------------------------------------------------- meta ----
  document.getElementById('meta').textContent =
    `Generated ${DATA.generated_at.slice(0, 10)} · projection snapshot ${DATA.ledger_snapshot_date}` +
    ` · ${DATA.sources.expected_funds_files.length} expected-funds files (classes ` +
    `${Math.min(...DATA.sources.expected_funds_files.map(f => f.class))}–` +
    `${Math.max(...DATA.sources.expected_funds_files.map(f => f.class))})`;

  // ------------------------------------------------------------- KPIs ----
  function renderKpis() {
    const horizon = days => {
      const end = new Date(); end.setDate(end.getDate() + days);
      const endIso = end.toISOString().slice(0, 10);
      return DATA.events.filter(e => visible(e) && e.date >= TODAY && e.date <= endIso)
        .reduce((s, e) => s + eventAmount(e), 0);
    };
    const futureBy = kind => DATA.events
      .filter(e => e.kind === kind && e.date >= TODAY)
      .reduce((s, e) => s + eventAmount(e), 0);
    const kpis = [
      { label: 'Next 30 days', value: fmt$(horizon(30)) },
      { label: 'Next 60 days', value: fmt$(horizon(60)) },
      { label: 'Next 90 days', value: fmt$(horizon(90)) },
      { label: 'Future — expected (filed)', value: fmt$(futureBy('expected')), sub: 'classes with FA workbooks' },
      { label: `Future — projected (${state.scenario})`, value: fmt$(futureBy('projected')), sub: 'model, future cohorts' },
    ];
    document.getElementById('kpis').innerHTML = kpis.map(k =>
      `<div class="kpi"><div class="label">${k.label}</div><div class="value">${k.value}</div>` +
      `${k.sub ? `<div class="sub">${k.sub}</div>` : ''}</div>`).join('');
  }

  // ------------------------------------------------------------ chart ----
  let chart = null;

  function monthRange() {
    const months = DATA.events.filter(visible).map(e => e.date.slice(0, 7));
    if (!months.length) return [];
    let m = months.reduce((a, b) => a < b ? a : b);
    const last = months.reduce((a, b) => a > b ? a : b);
    const out = [];
    while (m <= last) {
      out.push(m);
      const [y, mo] = m.split('-').map(Number);
      m = mo === 12 ? `${y + 1}-01` : `${y}-${String(mo + 1).padStart(2, '0')}`;
    }
    return out;
  }

  function withAlpha(color, alpha) {
    if (color.startsWith('#')) {
      const n = parseInt(color.slice(1), 16);
      return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
    }
    return color;
  }

  function renderChart() {
    const months = monthRange();
    const idx = Object.fromEntries(months.map((m, i) => [m, i]));
    const buckets = {}; // `${kind}|${fund}` -> array per month
    for (const e of DATA.events) {
      if (!visible(e)) continue;
      const key = `${e.kind}|${e.fund}`;
      (buckets[key] = buckets[key] || months.map(() => 0))[idx[e.date.slice(0, 7)]] += eventAmount(e);
    }
    const datasets = [];
    for (const kind of ['expected', 'projected']) {
      for (const fund of FUNDS) {
        const data = buckets[`${kind}|${fund}`];
        if (!data || !data.some(v => v > 0)) continue;
        datasets.push({
          type: 'bar', stack: 'cash', data,
          label: FUND_LABELS[fund] + (kind === 'projected' ? ' (projected)' : ''),
          fundKey: fund, kindKey: kind,
          backgroundColor: withAlpha(FUND_COLORS[fund], kind === 'projected' ? 0.38 : 0.9),
          borderWidth: 0,
        });
      }
    }
    const monthTotals = months.map((_, i) =>
      datasets.reduce((s, d) => s + d.data[i], 0));
    const cumulative = [];
    monthTotals.reduce((s, v, i) => (cumulative[i] = s + v, s + v), 0);
    datasets.push({
      type: 'line', label: 'Cumulative', data: cumulative, yAxisID: 'y2',
      borderColor: token('--accent'), backgroundColor: 'transparent',
      pointRadius: 0, borderWidth: 2, tension: 0.25,
    });

    const thisMonth = TODAY.slice(0, 7);
    const cfg = {
      data: { labels: months.map(monthLabel), datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index' },
        scales: {
          x: {
            stacked: true, grid: { color: token('--border') },
            ticks: {
              color: ctx => months[ctx.index] < thisMonth ? token('--muted') : token('--text'),
            },
          },
          y: {
            stacked: true, grid: { color: token('--border') },
            ticks: { color: token('--muted'), callback: v => fmtK(v) },
          },
          y2: {
            position: 'right', grid: { drawOnChartArea: false },
            ticks: { color: token('--accent'), callback: v => fmtK(v) },
          },
        },
        plugins: {
          legend: {
            labels: {
              color: token('--text'),
              filter: item => !item.text.endsWith('(projected)'),
            },
          },
          tooltip: {
            callbacks: {
              label: ctx => ctx.dataset.type === 'line'
                ? ` Cumulative: ${fmt$(ctx.parsed.y)}`
                : ` ${ctx.dataset.label}: ${fmt$(ctx.parsed.y)}`,
              footer: items => {
                const i = items[0].dataIndex;
                return 'Month total: ' + fmt$(monthTotals[i]);
              },
            },
          },
        },
      },
    };
    if (chart) chart.destroy();
    chart = new Chart(document.getElementById('monthly-chart'), cfg);
  }

  // ----------------------------------------------------- events table ----
  const TRANCHE_LABELS = { disb1: '1st disbursement', disb2: '2nd disbursement', va1: 'VA release' };

  function renderEvents() {
    const groups = {}; // date|cohort|tranche|kind
    for (const e of DATA.events) {
      if (!visible(e) || e.date < TODAY) continue;
      const key = [e.date, e.cohort, e.tranche, e.kind].join('|');
      const g = groups[key] = groups[key] ||
        { date: e.date, cohort: e.cohort, tranche: e.tranche, kind: e.kind, amount: 0, funds: [] };
      g.amount += eventAmount(e);
      g.funds.push(FUND_LABELS[e.fund]);
    }
    const rows = Object.values(groups)
      .sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : a.cohort < b.cohort ? -1 : 1)
      .slice(0, 18);
    document.querySelector('#events-table tbody').innerHTML = rows.map(g => `
      <tr title="${g.funds.join(', ')}">
        <td>${fmtDate(g.date)}</td><td>${g.cohort}</td>
        <td>${TRANCHE_LABELS[g.tranche] || g.tranche}</td>
        <td><span class="tag ${g.kind}">${g.kind}</span></td>
        <td class="num">${fmt$(g.amount)}</td>
      </tr>`).join('') ||
      '<tr><td colspan="5">No upcoming events for the current filters.</td></tr>';
  }

  // ------------------------------------------------------ class table ----
  function renderClasses() {
    const rows = DATA.classes.map(c => {
      const students = c.programs.reduce((s, p) => s + (p.students || 0), 0);
      const cash = c.programs.reduce((s, p) => s + (p.cash_payers || 0), 0);
      const projMid = c.programs.reduce((s, p) => s + (p.proj_starts ? p.proj_starts.mid : 0), 0);
      const total = c.programs.reduce((s, p) => s + p.total_net, 0);
      const isFile = c.source === 'file';
      const past = c.dates.start < TODAY && isFile;
      return `<tr class="${past ? 'past' : ''}">
        <td>${c.class}${c.source === 'projected-derived-dates' ? ' *' : ''}</td>
        <td>${fmtDate(c.dates.start)}</td>
        <td><span class="tag ${isFile ? 'expected' : 'projected'}">${isFile ? 'FA file' : 'model'}</span></td>
        <td>${isFile ? students : projMid + ' (mid)'}</td>
        <td>${isFile ? cash : '—'}</td>
        <td class="num">${fmt$(total)}</td>
      </tr>`;
    });
    document.querySelector('#class-table tbody').innerHTML = rows.join('') +
      '<tr><td colspan="6" style="color:var(--muted)">* schedule dates extrapolated; ' +
      'model rows show mid-case totals regardless of scenario selector</td></tr>';
  }

  // ------------------------------------------------------ assumptions ----
  document.getElementById('assumptions').innerHTML =
    DATA.assumptions.map(a => `<li>${a}</li>`).join('');
  document.getElementById('sources').textContent =
    `Schedule: ${DATA.sources.schedule_file} · Expected funds: ` +
    DATA.sources.expected_funds_files.map(f => `${f.file} (modified ${f.modified})`).join(', ');

  // ---------------------------------------------------------- controls ----
  document.querySelectorAll('#scenario-group button').forEach(b => {
    b.addEventListener('click', () => {
      state.scenario = b.dataset.scenario;
      document.querySelectorAll('#scenario-group button')
        .forEach(x => x.classList.toggle('active', x === b));
      renderAll();
    });
  });
  document.querySelectorAll('#kind-group button').forEach(b => {
    b.addEventListener('click', () => {
      const kind = b.dataset.kind;
      if (state.kinds.has(kind) && state.kinds.size === 1) return; // keep one on
      state.kinds.has(kind) ? state.kinds.delete(kind) : state.kinds.add(kind);
      b.classList.toggle('active', state.kinds.has(kind));
      renderAll();
    });
  });

  function renderAll() { renderKpis(); renderChart(); renderEvents(); }
  renderAll();
  renderClasses();
})();
