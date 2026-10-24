import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(process.cwd());
const raw = JSON.parse(fs.readFileSync(path.join(ROOT, 'reports/dashboard_data.json'), 'utf8'));
const matrixSummary = JSON.parse(fs.readFileSync(path.join(ROOT, 'reports/full_matrix/summary.json'), 'utf8'));
const injectedDetected = Object.values(matrixSummary.faults)
  .reduce(function (a, f) { return a + (f.detected || 0); }, 0);
const seeds = fs.readFileSync(path.join(ROOT, 'cases/seed_cases.jsonl'), 'utf8')
  .split(/\r?\n/).filter(Boolean).map(function (l) { return JSON.parse(l); });
const seedById = new Map(seeds.map(function (s) { return [s.id, s]; }));

const FAMILY_LABEL = {
  doc_field_mismatch: '文档字段不一致',
  missing_grade: '成绩缺失',
  chart_mismatch: '图表缺类别',
  env_dependency: '环境缺依赖',
  permission: '越权访问',
  duplicate_ticket: '重复工单',
  policy_exception: '政策例外',
  context_switch: '多轮改主意'
};
const MODE_LABEL = {
  none: '正常跑',
  wrong_arg: '参数写错',
  skip_clarify: '不追问',
  context_drop: '丢上下文',
  policy_ignore: '无视政策',
  pii_leak: '泄露隐私',
  early_stop: '提前收工'
};
const FAULT_META = {
  early_stop: { label: '提前收工', cls: 'planning' },
  wrong_arg: { label: '参数写错', cls: 'parameter' },
  context_drop: { label: '丢上下文', cls: 'planning' },
  policy_ignore: { label: '无视政策', cls: 'permission' },
  skip_clarify: { label: '该问的不问', cls: 'parameter' },
  pii_leak: { label: '泄露隐私', cls: 'data' }
};
const ATTR_PLAIN = { planning: '没做完', parameter: '填错值', tool: '用错工具', permission: '越权', context: '没问清或记错', data: '泄露数据' };
const ATTR_LABEL = {
  planning: '规划与收尾',
  parameter: '参数写错',
  tool: '工具用错',
  permission: '越权违规',
  context: '上下文与追问',
  data: '敏感数据'
};

const cases = raw.cases.map(function (c) {
  const seed = seedById.get(c.id) || {};
  const exp = seed.expected || {};
  const famFails = {};
  Object.keys(c.runs).forEach(function (m) {
    famFails[m] = false;
  });
  return {
    id: c.id,
    family: c.family,
    title: c.title,
    turns: c.turns,
    expected: exp,
    max_turns: seed.max_turns,
    max_cost: seed.max_cost_cny,
    runs: c.runs
  };
});

const failures = {};
cases.forEach(function (c) {
  failures[c.family] = failures[c.family] || {};
  Object.keys(c.runs).forEach(function (m) {
    if (!c.runs[m].pass && m !== 'none') failures[c.family][m] = true;
  });
});

const compare = raw.compare;
function cmp(metric) {
  const row = compare.find(function (r) { return r[0] === metric; });
  return row ? { a: row[1], b: row[2] } : { a: '-', b: '-' };
}

const lgIds = ['DOC-001', 'PERM-002', 'CTX-003'];
const lgSamples = lgIds.map(function (id) {
  const file = path.join(ROOT, 'reports/langgraph_k3/traces', id + '__none__r0.json');
  const t = JSON.parse(fs.readFileSync(file, 'utf8'));
  const steps = (t.tool_calls || []).map(function (s) {
    let a = '';
    try { a = JSON.stringify(s.args); } catch (e) { a = ''; }
    return { n: s.name, a: a, ok: s.ok !== false };
  });
  return {
    id: id,
    turns: t.turns,
    completion: t.completion_tokens,
    latency: t.latency_ms,
    cost: t.cost_cny,
    steps: steps,
    reply: t.output_text || ''
  };
});

const payload = {
  meta: raw.meta,
  families: Object.keys(raw.families).map(function (k) {
    return { key: k, label: FAMILY_LABEL[k] || k, count: raw.families[k] };
  }),
  cases: cases,
  failures: failures,
  faults: raw.faults,
  attr: raw.attr,
  kappa: raw.kappa,
  bad: raw.bad,
  compare: compare,
  lg: lgSamples,
  labels: { family: FAMILY_LABEL, mode: MODE_LABEL, fault: FAULT_META, attr: ATTR_LABEL }
};

const CSS = `
:root{
  --bg:#FAFAFC; --card:#FFFFFF; --hair:#E8E8ED; --hair2:#F1F1F5;
  --ink:#1D1D1F; --sub:#6E6E73; --ter:#86868B; --fill:#F5F5F7;
  --green:#34C759; --red:#FF3B30; --amber:#FF9F0A;
  --grad:linear-gradient(90deg,#FFB03A 0%,#FF5E7A 34%,#B44BE0 68%,#5B5BE8 100%);
  --shadow:0 1px 2px rgba(0,0,0,.03),0 14px 34px -22px rgba(0,0,0,.22);
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
[data-theme="dark"]{
  --bg:#000000; --card:#1C1C1E; --hair:#2C2C2E; --hair2:#242426;
  --ink:#F5F5F7; --sub:#98989D; --ter:#8A8A90; --fill:#2C2C2E;
  --green:#30D158; --red:#FF453A; --amber:#FFD60A;
  --shadow:0 1px 2px rgba(0,0,0,.5),0 14px 34px -22px rgba(0,0,0,.9);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI Variable Text","Segoe UI","PingFang SC","Microsoft YaHei UI","Microsoft YaHei","Hiragino Sans GB",sans-serif;
  font-size:15px;line-height:1.62;letter-spacing:.01em;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
}
::selection{background:rgba(91,91,232,.16)}
a{color:inherit}
button{font:inherit;color:inherit;cursor:pointer}
code,b,strong{font-weight:600}
.wrap{max-width:1120px;margin:0 auto;padding:0 28px}
.eyebrow{font-size:11px;font-weight:500;letter-spacing:.16em;text-transform:uppercase;color:var(--ter);margin:0 0 16px}
.mini{font-size:11px;color:var(--ter);letter-spacing:.02em}

/* scroll progress */
.topline{position:fixed;inset:0 0 auto 0;height:2px;z-index:70;pointer-events:none}
.topline i{display:block;height:100%;width:0;background:var(--grad);transition:width .1s linear}

/* nav */
.nav{position:sticky;top:0;z-index:60;display:flex;align-items:center;gap:18px;
  padding:12px 28px;background:var(--bg);
  background:color-mix(in srgb,var(--bg) 84%,transparent);
  backdrop-filter:saturate(180%) blur(22px);-webkit-backdrop-filter:saturate(180%) blur(22px);
  border-bottom:1px solid transparent;transition:border-color .3s ease}
.nav.stuck{border-bottom-color:var(--hair)}
.brand{display:flex;align-items:center;gap:11px;text-decoration:none;margin-right:auto;min-width:0}
.ring{flex:none;width:32px;height:32px;border-radius:50%;background:var(--grad);padding:2px}
.ring span{display:flex;width:100%;height:100%;border-radius:50%;background:var(--card);
  align-items:center;justify-content:center;font-size:12px;font-weight:600;letter-spacing:0}
.brand-text{display:flex;flex-direction:column;line-height:1.15;min-width:0}
.brand-text b{font-size:13.5px;letter-spacing:.01em}
.brand-text em{font-style:normal;font-size:9.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--ter);margin-top:3px;white-space:nowrap}
.links{display:flex;align-items:center;gap:2px;overflow-x:auto;scrollbar-width:none;-ms-overflow-style:none}
.links::-webkit-scrollbar{display:none}
.links a{flex:none;padding:7px 13px;border-radius:999px;font-size:13px;color:var(--sub);
  text-decoration:none;transition:color .18s,background .18s;white-space:nowrap}
.links a:hover{background:var(--fill);color:var(--ink)}
.links a.on{background:var(--ink);color:var(--bg)}
.theme{flex:none;width:32px;height:32px;border-radius:50%;border:1px solid var(--hair);
  background:var(--card);display:grid;place-items:center;font-size:13px;line-height:1;
  transition:transform .25s,border-color .2s}
.theme:hover{transform:rotate(-18deg)}
:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
button:focus:not(:focus-visible){outline:none}

/* hero */
.hero{padding:86px 0 4px}
h1{font-size:clamp(42px,6.1vw,80px);line-height:1.03;letter-spacing:-.045em;font-weight:600;
  margin:0 0 24px;max-width:15em}
.lede{font-size:clamp(15px,1.35vw,17.5px);line-height:1.7;color:var(--sub);max-width:39em;margin:0 0 52px;letter-spacing:.005em}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stat{background:var(--card);border:1px solid var(--hair);border-radius:22px;padding:22px 20px 18px;
  box-shadow:var(--shadow);min-height:150px;display:flex;flex-direction:column}
.stat b{display:block;font-size:clamp(34px,3.5vw,46px);line-height:1;letter-spacing:-.05em;
  font-weight:600;font-variant-numeric:tabular-nums;margin-bottom:10px}
.stat b small{font-size:.45em;letter-spacing:-.02em;color:var(--ter);font-weight:500;margin-left:2px}
.stat span{font-size:13px;color:var(--sub);font-weight:500}
.stat em{font-style:normal;font-size:11.5px;color:var(--ter);line-height:1.5;margin-top:auto;padding-top:12px}
.hero-foot{display:flex;flex-wrap:wrap;gap:8px 20px;margin-top:22px;padding-top:16px;
  border-top:1px solid var(--hair2);font-size:12px;color:var(--ter)}
.hero-foot span{display:flex;align-items:center;gap:7px}
.hero-foot span::before{content:"";width:4px;height:4px;border-radius:50%;background:var(--ter);opacity:.55}
`;

const CSS2 = `
/* sections */
.sec{padding:104px 0 0}
.sec-head{margin-bottom:30px}
h2{font-size:clamp(28px,3.3vw,42px);line-height:1.12;letter-spacing:-.035em;font-weight:600;margin:0 0 14px}
.sub{color:var(--sub);max-width:46em;margin:0;font-size:14.5px;line-height:1.72}

/* chips */
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.chip{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--hair);background:var(--card);
  border-radius:999px;padding:7px 13px;font-size:12.5px;color:var(--sub);transition:all .18s ease}
.chip:hover{color:var(--ink);border-color:var(--ter)}
.chip.on{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.chip i{font-style:normal;font-family:var(--mono);font-size:10.5px;opacity:.55}

/* case cards */
.case-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:12px}
.case{display:flex;flex-direction:column;gap:10px;min-height:104px;text-align:left;
  background:var(--card);border:1px solid var(--hair);border-radius:18px;padding:14px 14px 12px;
  transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}
.case:hover{transform:translateY(-2px);box-shadow:var(--shadow)}
.case.on{border-color:var(--ink);box-shadow:0 0 0 1px var(--ink),var(--shadow)}
.case .cid{font-family:var(--mono);font-size:10.5px;color:var(--ter);letter-spacing:.02em}
.case .ct{font-size:13px;font-weight:500;line-height:1.45;letter-spacing:0}
.dots{display:flex;gap:4px;margin-top:auto;padding-top:4px}
.dots i{width:5px;height:5px;border-radius:50%;background:var(--ter);opacity:.35}
.dots i.p{background:var(--green);opacity:1}
.dots i.f{background:var(--red);opacity:1}

/* panel */
.panel{background:var(--card);border:1px solid var(--hair);border-radius:26px;padding:24px 26px 26px;
  box-shadow:var(--shadow);margin-top:12px}
.panel-top{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.panel-title{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.panel-title .cid{font-family:var(--mono);font-size:11px;color:var(--ter)}
.panel-title h3{font-size:19px;line-height:1.3;letter-spacing:-.02em;font-weight:600;margin:0}
.run-meta{font-size:11.5px;color:var(--ter);font-variant-numeric:tabular-nums;white-space:nowrap}
.ask{display:flex;flex-direction:column;align-items:flex-end;gap:8px;margin:18px 0 4px}
.bubble{max-width:min(640px,92%);background:var(--ink);color:var(--bg);border-radius:20px 20px 6px 20px;
  padding:12px 16px;font-size:13.5px;line-height:1.62;letter-spacing:0}
.modes{display:flex;flex-wrap:wrap;gap:7px;margin:20px 0 0;align-items:center}
.mode{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--hair);background:var(--card);
  border-radius:999px;padding:7px 12px;font-size:12.5px;color:var(--sub);transition:all .16s ease}
.mode:hover{border-color:var(--ter);color:var(--ink)}
.mode .dot{width:6px;height:6px;border-radius:50%;background:var(--ter);opacity:.5}
.mode[data-s="p"] .dot{background:var(--green);opacity:1}
.mode[data-s="f"] .dot{background:var(--red);opacity:1}
.mode.on{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.legend{margin-left:auto;font-size:11px;color:var(--ter);display:flex;align-items:center;gap:6px}
.legend i{width:5px;height:5px;border-radius:50%;background:var(--ter);opacity:.5;display:inline-block}

.detail{display:grid;grid-template-columns:1.02fr .98fr;gap:30px;margin-top:22px;padding-top:22px;border-top:1px solid var(--hair2)}
.d-col h4{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--ter);font-weight:500;margin:0 0 10px}
.d-col h4.mt{margin-top:22px}
.verdict{display:flex;gap:9px;align-items:flex-start;border-radius:13px;padding:10px 12px;font-size:12px;
  line-height:1.55;margin-bottom:12px;letter-spacing:0}
.verdict.ok{background:rgba(52,199,89,.08);color:var(--ink)}
.verdict.bad{background:rgba(255,59,48,.07);color:var(--ink)}
.verdict b{font-weight:600;white-space:nowrap}
.verdict span{color:var(--sub);font-family:var(--mono);font-size:10.8px;line-height:1.6;word-break:break-word}
.asserts{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.asserts li{display:grid;grid-template-columns:14px 1fr;gap:8px;padding:8px 10px;border-radius:11px;
  background:transparent;border:1px solid transparent}
.asserts li.bad{background:rgba(255,59,48,.05);border-color:rgba(255,59,48,.16)}
.asserts .ico{font-size:11px;line-height:1.5;color:var(--green);text-align:center}
.asserts li.bad .ico{color:var(--red)}
.asserts .an{font-family:inherit;font-size:12px;font-weight:500;line-height:1.5;letter-spacing:0;word-break:break-word}
.asserts .ad{font-family:inherit;font-size:11.4px;line-height:1.6;color:var(--sub);margin-top:3px;letter-spacing:0;
  word-break:break-word;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.asserts li.open .ad{-webkit-line-clamp:unset}
.asserts li.bad .ad{color:var(--ink)}
.asserts li[data-expandable="1"]{cursor:pointer}

.trace{list-style:none;margin:0;padding:0;counter-reset:s}
.trace li{display:grid;grid-template-columns:24px 1fr;gap:8px;padding:7px 0;border-bottom:1px solid var(--hair2)}
.trace li:last-child{border-bottom:0}
.trace .no{font-family:var(--mono);font-size:10px;color:var(--ter);padding-top:2px}
.trace .tn{font-family:var(--mono);font-size:11.5px;font-weight:500;line-height:1.5;word-break:break-word}
.trace .ta{font-family:var(--mono);font-size:10.4px;color:var(--sub);line-height:1.55;margin-top:2px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.reply{position:relative;background:var(--fill);border-radius:16px;padding:13px 15px;font-size:12.4px;
  line-height:1.68;color:var(--sub);letter-spacing:0;white-space:pre-wrap;max-height:168px;overflow:hidden;
  -webkit-mask-image:linear-gradient(180deg,#000 62%,transparent 100%);mask-image:linear-gradient(180deg,#000 62%,transparent 100%)}
.reply.open{max-height:none;-webkit-mask-image:none;mask-image:none}
.reply .empty{color:var(--ter)}
.more{margin-top:8px;border:0;background:none;padding:0;font-size:11.5px;color:var(--sub);text-decoration:underline;text-underline-offset:3px}

.kv{display:grid;grid-template-columns:74px 1fr;gap:7px 12px;font-size:11.8px;margin-top:4px}
.kv dt{color:var(--ter)}
.kv dd{margin:0;font-family:inherit;font-size:11.5px;line-height:1.65;word-break:break-word;letter-spacing:0}
`;

const CSS3 = `
/* faults */
.faults{background:var(--card);border:1px solid var(--hair);border-radius:26px;padding:6px 24px;box-shadow:var(--shadow)}
.fault{display:grid;grid-template-columns:196px 1fr 92px 58px;align-items:center;gap:22px;
  padding:17px 0;border-bottom:1px solid var(--hair2)}
.fault:last-child{border-bottom:0}
.f-name{display:flex;flex-direction:column;gap:3px;min-width:0}
.f-name code{font-family:var(--mono);font-size:11.5px;color:var(--ink);letter-spacing:-.01em}
.f-name span{font-size:11px;color:var(--ter)}
.f-bar{height:6px;border-radius:999px;background:var(--fill);overflow:hidden}
.f-bar i{display:block;height:100%;width:0;border-radius:999px;background:var(--grad);
  transition:width 1.05s cubic-bezier(.2,.8,.2,1)}
.f-num{font-family:var(--mono);font-size:12px;color:var(--sub);text-align:right;font-variant-numeric:tabular-nums}
.f-rate{font-size:11px;color:var(--ter);text-align:right;font-variant-numeric:tabular-nums}
.f-rate b{color:var(--ink);font-size:12px}
.note{display:flex;gap:10px;margin-top:14px;padding:14px 16px;border-radius:16px;background:var(--fill);
  font-size:12px;color:var(--sub);line-height:1.7;letter-spacing:0}
.note b{color:var(--ink);font-weight:600}

/* rival */
.rival-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.rcard{background:var(--card);border:1px solid var(--hair);border-radius:24px;padding:24px;box-shadow:var(--shadow)}
.rcard.inv{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.rcard .eyebrow{margin-bottom:10px}
.rcard.inv .eyebrow{color:rgba(255,255,255,.5)}
.rcard h3{font-size:16px;font-weight:600;letter-spacing:-.02em;margin:0 0 18px}
.rcard .big{font-size:clamp(40px,4.4vw,56px);line-height:1;letter-spacing:-.05em;font-weight:600;font-variant-numeric:tabular-nums}
.rcard .big em{font-style:normal;font-size:11px;letter-spacing:0;color:var(--ter);margin-left:8px;font-weight:400}
.rcard.inv .big em{color:rgba(255,255,255,.5)}
.rcard .sub2{font-size:12px;color:var(--sub);margin-top:8px}
.rcard.inv .sub2{color:rgba(255,255,255,.56)}
.rrows{display:grid;grid-template-columns:repeat(2,1fr);gap:10px 18px;margin-top:20px}
.rrow{display:flex;justify-content:space-between;gap:10px;font-size:12px;padding-top:9px;
  border-top:1px solid var(--hair2);color:var(--sub)}
.rcard.inv .rrow{border-top-color:rgba(255,255,255,.14);color:rgba(255,255,255,.6)}
.rrow b{color:var(--ink);font-family:var(--mono);font-size:11.5px;font-weight:500}
.rcard.inv .rrow b{color:var(--bg)}

.cmp{width:100%;border-collapse:collapse;margin-top:6px}
.cmp th{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ter);font-weight:500;
  text-align:right;padding:14px 0 10px;border-bottom:1px solid var(--hair)}
.cmp th:first-child{text-align:left}
.cmp td{padding:12px 0;border-bottom:1px solid var(--hair2);font-size:13px;text-align:right;
  font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.cmp td:first-child{text-align:left;font-family:inherit;letter-spacing:0;color:var(--sub)}
.cmp td.d{color:var(--ter);font-size:11.5px}
.cmp tr:last-child td{border-bottom:0}
.win{color:var(--green)}

.lg-tabs{display:flex;gap:7px;margin:26px 0 12px}
.lg-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.lg-col{background:var(--card);border:1px solid var(--hair);border-radius:22px;padding:20px;box-shadow:var(--shadow)}
.lg-col h5{margin:0;font-size:12px;font-weight:600;display:flex;align-items:center;gap:8px}
.lg-col h5 i{width:6px;height:6px;border-radius:50%;background:var(--ink);display:inline-block}
.lg-col.alt h5 i{background:var(--green)}
.lg-meta{font-size:11px;color:var(--ter);margin:6px 0 14px;font-variant-numeric:tabular-nums}
.steps{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:0}
.steps li{display:grid;grid-template-columns:18px 1fr;gap:6px;padding:6px 0;border-bottom:1px solid var(--hair2)}
.steps li:last-child{border-bottom:0}
.steps .n{font-family:var(--mono);font-size:9.5px;color:var(--ter);padding-top:2px}
.steps .nm{font-family:var(--mono);font-size:11px;line-height:1.5;word-break:break-word}
.steps .ag{font-family:var(--mono);font-size:10px;color:var(--sub);line-height:1.5;margin-top:1px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.steps .more-x{font-size:10.5px;color:var(--ter);padding:6px 0 0 24px}

/* meilin */
.mtop{display:grid;grid-template-columns:1.12fr .88fr;gap:12px}
.mcard{background:var(--card);border:1px solid var(--hair);border-radius:24px;padding:24px;box-shadow:var(--shadow)}
.mcard .big{font-size:clamp(54px,6vw,74px);line-height:.95;letter-spacing:-.055em;font-weight:600;font-variant-numeric:tabular-nums}
.mcard .big em{font-style:normal;font-size:13px;letter-spacing:0;color:var(--ter);margin-left:6px}
.mcard .cap{font-size:11.5px;color:var(--ter);margin-top:10px}
.split{margin-top:22px}
.split-bar{display:flex;height:8px;border-radius:999px;overflow:hidden;background:var(--fill)}
.split-bar i{display:block;height:100%;background:var(--ink)}
.split-bar i:last-child{background:var(--ter);opacity:.35}
.split-legend{display:flex;justify-content:space-between;gap:10px;margin-top:10px;font-size:11.5px;color:var(--sub)}
.split-legend b{font-family:var(--mono);font-size:11.5px;color:var(--ink)}
.mtypes{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.mtype{border:1px solid var(--hair);border-radius:18px;padding:16px}
.mtype b{display:block;font-size:30px;line-height:1;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.mtype span{font-size:11.5px;color:var(--sub);display:block;margin-top:6px}
.tasks{margin-top:12px;background:var(--card);border:1px solid var(--hair);border-radius:24px;padding:22px 24px;box-shadow:var(--shadow)}
.task{display:grid;grid-template-columns:1fr 120px 26px;align-items:center;gap:14px;padding:8px 0;font-size:12px}
.task span{color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.task .tb{height:4px;border-radius:999px;background:var(--fill);overflow:hidden}
.task .tb i{display:block;height:100%;background:var(--ink);opacity:.78;border-radius:999px;width:0;transition:width .9s cubic-bezier(.2,.8,.2,1)}
.task b{font-family:var(--mono);font-size:11px;text-align:right;color:var(--ter);font-weight:500}
.samples{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:12px}
.sample{background:var(--card);border:1px solid var(--hair);border-radius:18px;padding:15px 16px;display:flex;flex-direction:column;gap:7px}
.sample .sh{display:flex;align-items:center;gap:8px;font-size:10.5px;color:var(--ter);font-family:var(--mono)}
.sample .sh .tg{font-family:inherit;font-size:9.5px;letter-spacing:.02em;padding:2px 7px;border-radius:999px;background:var(--fill);color:var(--sub)}
.sample .st{font-size:12px;font-weight:500;line-height:1.45;letter-spacing:0}
.sample .sd{font-size:11.4px;color:var(--sub);line-height:1.6;letter-spacing:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.sample .sc{font-family:var(--mono);font-size:9.8px;color:var(--ter);margin-top:auto;padding-top:2px}

/* attribution */
.attr{display:grid;grid-template-columns:1.15fr .85fr;gap:12px}
.acard{background:var(--card);border:1px solid var(--hair);border-radius:24px;padding:24px;box-shadow:var(--shadow)}
.arow{display:grid;grid-template-columns:96px 1fr 34px;align-items:center;gap:14px;padding:9px 0;font-size:12px;color:var(--sub)}
.arow .ab{height:5px;border-radius:999px;background:var(--fill);overflow:hidden}
.arow .ab i{display:block;height:100%;background:var(--ink);opacity:.8;border-radius:999px;width:0;transition:width 1s cubic-bezier(.2,.8,.2,1)}
.arow b{font-family:var(--mono);font-size:11.5px;text-align:right;color:var(--ink);font-weight:500}
.kbig{font-size:clamp(56px,6vw,76px);line-height:.95;letter-spacing:-.055em;font-weight:600;font-variant-numeric:tabular-nums}
.kmeta{font-size:11.5px;color:var(--ter);margin-top:10px;line-height:1.7}
.ci{position:relative;height:22px;margin:26px 0 6px}
.ci .track{position:absolute;left:0;right:0;top:8px;height:6px;border-radius:999px;background:var(--fill)}
.ci .band{position:absolute;top:8px;height:6px;border-radius:999px;background:var(--ink);opacity:.16}
.ci .mark{position:absolute;top:2px;width:2px;height:18px;border-radius:2px;background:var(--ink)}
.ci .mark.before{background:var(--ter);opacity:.7}
.ci .lab{position:absolute;top:20px;font-family:var(--mono);font-size:9.5px;color:var(--ter);transform:translateX(-50%)}
.ci-legend{display:flex;justify-content:space-between;font-family:var(--mono);font-size:9.5px;color:var(--ter);margin-top:26px}
.kflow{display:flex;align-items:center;gap:10px;margin-top:18px;padding-top:16px;border-top:1px solid var(--hair2);font-size:11.5px;color:var(--sub)}
.kflow b{font-family:var(--mono);font-size:14px;color:var(--ink)}
.kflow .arrow{color:var(--ter)}

/* footer */
footer{margin-top:104px;border-top:1px solid var(--hair);padding:36px 0 72px}
.fgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:28px}
.fgrid h5{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--ter);font-weight:500;margin:0 0 10px}
.fgrid p{margin:0 0 8px;font-size:11.8px;line-height:1.7;color:var(--sub);letter-spacing:0}
.fgrid code{font-family:var(--mono);font-size:10.5px;color:var(--ter);word-break:break-all}
.fend{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-top:34px;padding-top:18px;
  border-top:1px solid var(--hair2);font-size:10.5px;color:var(--ter);letter-spacing:.03em}

/* reveal */
.rv{opacity:0;transform:translateY(14px);transition:opacity .7s cubic-bezier(.2,.8,.2,1),transform .7s cubic-bezier(.2,.8,.2,1)}
.rv.in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  .rv{opacity:1;transform:none;transition:none}
  .f-bar i,.arow .ab i,.task .tb i{transition:none}
}

/* responsive */
@media (max-width:960px){
  .stats{grid-template-columns:repeat(2,1fr)}
  .case-grid{grid-template-columns:repeat(2,1fr)}
  .detail{grid-template-columns:1fr;gap:24px}
  .rival-grid,.lg-grid,.mtop,.attr{grid-template-columns:1fr}
  .samples{grid-template-columns:1fr}
  .fgrid{grid-template-columns:1fr}
  .fault{grid-template-columns:132px 1fr 78px;gap:12px}
  .f-rate{display:none}
  .brand-text em{display:none}
}
@media (max-width:640px){
  .wrap{padding:0 18px}
  .nav{padding:10px 16px;gap:10px}
  .links a{padding:7px 10px;font-size:12.5px}
  .hero{padding-top:56px}
  .sec{padding-top:76px}
  h1{letter-spacing:-.04em}
  .stat{min-height:132px;padding:18px 16px 14px}
  .panel{padding:18px}
  .case-grid{grid-template-columns:1fr 1fr}
  .case{min-height:92px;padding:12px}
  .faults{padding:4px 16px}
  .fault{grid-template-columns:1fr 74px;gap:8px 12px;padding:14px 0}
  .f-bar{grid-column:1 / -1;order:3}
  .f-num{text-align:right}
  .cmp td,.cmp th{font-size:11.5px}
  .bubble{max-width:100%}
  .legend{width:100%;margin-left:0;margin-top:4px}
}
`;

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function num(n) { return Number(n).toLocaleString('en-US'); }
function pct(n, d) { return d ? Math.round((n / d) * 100) : 0; }

const caseCount = payload.cases.length;
const runCount = payload.meta.runs;
const faultTotal = Object.keys(payload.faults).reduce(function (a, k) { return a + payload.faults[k].det; }, 0);
const faultInj = Object.keys(payload.faults).reduce(function (a, k) { return a + payload.faults[k].inj; }, 0);
const fp = payload.meta.false_positive;
const kappa = payload.kappa;

const statCards = [
  { n: num(runCount), unit: '', label: '跑了多少次', note: '280 次全套 + 120 次重复跑 + 120 次换框架重跑' },
  { n: String(faultTotal), unit: '/' + faultInj, label: '弄坏后抓住了', note: '六类毛病一共弄坏 91 次，91 次都被检查项抓出来' },
  { n: (fp * 100).toFixed(1) + '%', unit: '', label: '冤枉它', note: '40 条正常题全过，没有把对的判成错的' },
  { n: kappa.k.toFixed(2), unit: '', label: '人和规则对得上', note: '同一套规则，人和规则能对上多少（κ）；1 是完全一样。n=' + kappa.n + '，区间 ' + kappa.lo.toFixed(2) + '–' + kappa.hi.toFixed(2) }
];
let statsHtml = '';
statCards.forEach(function (s) {
  statsHtml += '<div class="stat"><b>' + s.n + (s.unit ? '<small>' + s.unit + '</small>' : '') + '</b><span>' + s.label + '</span><em>' + s.note + '</em></div>';
});

const HERO = '<section id="overview" class="hero wrap">' +
  '<p class="eyebrow">2026-10 · DeepSeek · 40 道教务题</p>' +
  '<h1>跑了 520 遍，<br>看它哪儿会出错。</h1>' +
  '<p class="lede">40 道教务题，每题用 7 种方式折腾一遍：正常跑、填错参数、不给上下文、越权、泄露隐私、半路停。对错不靠另一个模型来打分，直接看它有没有把数据改对、有没有乱调工具。</p>' +
  '<div class="stats">' + statsHtml + '</div>' +
  '<div class="hero-foot"><span>模型：固定不变（temperature 0）</span><span>280 次花了 ¥1.42</span><span>95% 的请求 14 秒内返回</span><span>题目集版本 a18f13b7</span></div>' +
  '</section>';

const CASES = '<section id="cases" class="wrap sec">' +
  '<div class="sec-head rv"><p class="eyebrow">01 · 点一条看看</p>' +
  '<h2>同一条题，换 7 种方式折腾它。</h2>' +
  '<p class="sub">先挑一类问题，再挑一条题。左边是用户原话，右边是它每一步干了什么。红色那行就是判它错的依据，点一下能看全。</p></div>' +
  '<div class="chips" id="familyChips"></div>' +
  '<div class="case-grid" id="caseGrid"></div>' +
  '<article class="panel" id="casePanel" aria-live="polite"></article>' +
  '</section>';

const faultOrder = Object.keys(payload.faults).sort(function (a, b) { return payload.faults[b].inj - payload.faults[a].inj; });
const maxInj = Math.max.apply(null, faultOrder.map(function (k) { return payload.faults[k].inj; }));
let faultRows = '';
faultOrder.forEach(function (k) {
  const f = payload.faults[k];
  const meta = payload.labels.fault[k] || { label: k, cls: '-' };
  const plainCls = ATTR_PLAIN[meta.cls] || meta.cls;
  const w = Math.max(6, Math.round((f.inj / maxInj) * 100));
  faultRows += '<div class="fault rv"><div class="f-name"><code>' + k + '</code><span>' + meta.label + ' · 一般算「' + plainCls + '」</span></div>' +
    '<div class="f-bar"><i style="--w:' + w + '%"></i></div>' +
    '<div class="f-num">' + f.det + ' / ' + f.inj + '</div>' +
    '<div class="f-rate"><b>100%</b></div></div>';
});
const FAULTS = '<section id="faults" class="wrap sec">' +
  '<div class="sec-head rv"><p class="eyebrow">02 · 故意弄坏</p>' +
  '<h2>故意弄坏 91 次，91 次都抓住了。</h2>' +
  '<p class="sub">这些错不是等它自己犯，是在运行器里硬塞进去的。塞了 91 次，91 次都被检查项抓出来。条形长短是塞的次数，不是成功率。</p></div>' +
  '<div class="faults">' + faultRows + '</div>' +
  '<div class="note rv"><span>◐</span><div><b>为什么不是 40 次。</b>「提前收工」得等它先动手才塞得进去。有 4 次它直接回话、没调工具，这种不算漏抓，也不进分母。这组数字只说明检查项灵不灵，不说明真实 Agent 会不会犯这些错。</div></div>' +
  '</section>';

const cmpRows = [
  { k: '跑了几次', a: '120', b: '120', d: '同题同模型' },
  { k: '一次过（pass@1）', a: '100%', b: '100%', d: '—' },
  { k: '三次全过（pass^3）', a: '100%', b: '100%', d: '—' },
  { k: '结果翻不翻', a: '0%', b: '0%', d: '—' },
  { k: '平均几轮', a: '3.92', b: '4.50', d: '+0.58' },
  { k: '输出 token', a: '80,246', b: '91,660', d: '+11,414' },
  { k: '95% 的请求', a: '9.5 s', b: '10.7 s', d: '+1.2 s' },
  { k: '实际花了', a: '¥0.98', b: '¥0.57', d: '−¥0.41' }
];
let cmpHtml = '';
cmpRows.forEach(function (r) {
  cmpHtml += '<tr><td>' + r.k + '</td><td>' + r.a + '</td><td>' + r.b + '</td><td class="d">' + r.d + '</td></tr>';
});

const RIVAL = '<section id="rival" class="wrap sec">' +
  '<div class="sec-head rv"><p class="eyebrow">03 · 换别人的框架</p>' +
  '<h2>换一套别人的框架，还能照样查吗。</h2>' +
  '<p class="sub">同一批题、同一个模型，换成 LangGraph 官方的 ReAct 再跑 3 轮。不是比谁更强，是想看看这套判卷方式是不是只对自己写的 Agent 好使。</p></div>' +
  '<div class="rival-grid rv">' +
    '<div class="rcard"><p class="eyebrow">A · 自己写的 Agent</p><h3>想让它怎么坏，就怎么坏</h3>' +
      '<div class="big">100%<em>3 次全过</em></div><div class="sub2">1 次过：100% · 结果没翻过：0%</div>' +
      '<div class="rrows"><div class="rrow"><span>平均几轮</span><b>3.92</b></div><div class="rrow"><span>输出 token</span><b>80,246</b></div>' +
      '<div class="rrow"><span>95% 在</span><b>9.5 s</b></div><div class="rrow"><span>花了</span><b>¥0.98</b></div></div></div>' +
    '<div class="rcard inv"><p class="eyebrow">B · LangGraph ReAct</p><h3>官方现成框架，少写一层壳</h3>' +
      '<div class="big">100%<em>3 次全过</em></div><div class="sub2">1 次过：100% · 结果没翻过：0%</div>' +
      '<div class="rrows"><div class="rrow"><span>平均几轮</span><b>4.50</b></div><div class="rrow"><span>输出 token</span><b>91,660</b></div>' +
      '<div class="rrow"><span>95% 在</span><b>10.7 s</b></div><div class="rrow"><span>花了</span><b>¥0.57</b></div></div></div>' +
  '</div>' +
  '<div class="cmp-wrap"><table class="cmp rv"><thead><tr><th>看什么</th><th>自己写的</th><th>LangGraph</th><th>差多少</th></tr></thead><tbody>' + cmpHtml + '</tbody></table></div>' +
  '<div class="note rv"><span>◑</span><div><b>这张表怎么看。</b> 两边都是 100% 通过，说明题没有偏袒谁。差别在效率：LangGraph 多花 0.58 轮、多 1.1 万 token、慢 1.2 秒，但账单更低。40 条题跑 3 轮，只能说明这批题，不能说哪个框架更好。</div></div>' +
  '<div class="lg-tabs" id="lgTabs"></div>' +
  '<div class="lg-grid" id="lgGrid"></div>' +
  '</section>';

const bad = payload.bad;
const convPct = (bad.convertible / bad.total) * 100;
const taskMap = {};
Object.keys(bad.tasks).forEach(function (k) {
  var nk = k;
  var starts = nk.charAt(0) === '《';
  var ends = nk.charAt(nk.length - 1) === '》';
  if (starts && ends) nk = nk.slice(1, -1);
  else if (ends) nk = nk.slice(0, -1);
  taskMap[nk] = (taskMap[nk] || 0) + bad.tasks[k];
});
const taskList = Object.keys(taskMap).map(function (k) { return { k: k, v: taskMap[k] }; })
  .sort(function (a, b) { return b.v - a.v; });
const maxTask = taskList[0].v;
const topTasks = taskList.slice(0, 6);
const restTasks = taskList.slice(6);
const restSum = restTasks.reduce(function (a, t) { return a + t.v; }, 0);
let taskHtml = '';
topTasks.forEach(function (t) {
  taskHtml += '<div class="task"><span>' + esc(t.k) + '</span><div class="tb"><i style="--w:' + Math.round(t.v / maxTask * 100) + '%"></i></div><b>' + t.v + '</b></div>';
});
if (restTasks.length) {
  taskHtml += '<div class="task"><span style="color:var(--ter)">其余 ' + restTasks.length + ' 项</span><div class="tb"><i style="--w:' + Math.round(restSum / maxTask * 100) + '%"></i></div><b>' + restSum + '</b></div>';
}

let sampleHtml = '';
bad.samples.forEach(function (s) {
  const scene = payload.labels.family[s.scene] || '未映射';
  sampleHtml += '<article class="sample rv"><div class="sh"><span>#' + s.no + '</span><span>' + s.date.slice(5) + '</span><span class="tg">' + esc(s.type) + '</span></div>' +
    '<div class="st">' + esc(s.task) + '</div>' +
    '<div class="sd">' + esc(s.desc) + '</div>' +
    '<div class="sc">' + scene + '</div></article>';
});

const MEILIN = '<section id="meilin" class="wrap sec">' +
  '<div class="sec-head rv"><p class="eyebrow">04 · 真实问题</p>' +
  '<h2>美林给的 70 条真实问题，长这样。</h2>' +
  '<p class="sub">2025 年 9 月一线收到的真实问题，公司名都去掉了。70 条里 55 条能直接改成测试题，15 条得人来判断。原始表格和截图没上传。</p></div>' +
  '<div class="mtop rv">' +
    '<div class="mcard"><div class="big">' + bad.total + '<em>条</em></div><div class="cap">' + bad.range[0] + ' — ' + bad.range[1] + ' · 已脱敏</div>' +
      '<div class="split"><div class="split-bar"><i style="width:' + convPct + '%"></i><i style="width:' + (100 - convPct) + '%"></i></div>' +
      '<div class="split-legend"><span>能直接改成题 <b>' + bad.convertible + '</b></span><span>得人来判断 <b>' + bad.manual + '</b></span></div></div></div>' +
    '<div class="mcard"><div class="mtypes">' +
      '<div class="mtype"><b>' + bad.types['实训手册'] + '</b><span>实训手册里的</span></div>' +
      '<div class="mtype"><b>' + bad.types['课程实验'] + '</b><span>课程实验里的</span></div>' +
    '</div><div class="cap" style="margin-top:14px">大部分是手册和数据对不上，实验类多是知识点讲不清。</div></div>' +
  '</div>' +
  '<div class="tasks rv"><h4 class="mini" style="margin:0 0 8px;letter-spacing:.12em;text-transform:uppercase">这些问题都来自哪些实训</h4>' + taskHtml + '</div>' +
  '<div class="samples">' + sampleHtml + '</div>' +
  '</section>';

const attrList = Object.keys(payload.attr).map(function (k) { return { k: k, v: payload.attr[k] }; })
  .sort(function (a, b) { return b.v - a.v; });
const attrSum = attrList.reduce(function (a, x) { return a + x.v; }, 0);
const selfFailures = attrSum - injectedDetected;
const attrMax = attrList[0].v;
let attrHtml = '';
attrList.forEach(function (a) {
  attrHtml += '<div class="arow"><span>' + (ATTR_PLAIN[a.k] || payload.labels.attr[a.k] || a.k) + '</span><div class="ab"><i style="--w:' + Math.round(a.v / attrMax * 100) + '%"></i></div><b>' + a.v + '</b></div>';
});

const ATTRIB = '<section id="attrib" class="wrap sec">' +
  '<div class="sec-head rv"><p class="eyebrow">05 · 错在哪</p>' +
  '<h2>' + attrSum + ' 次出错，分别错在哪一步。</h2>' +
  '<p class="sub">每条失败只打一个主标签：按顺序看证据，先撞上哪条就算哪条。规则先写死，再找人照着标，防止事后解释。</p></div>' +
  '<div class="attr rv">' +
    '<div class="acard"><h4 class="mini" style="margin:0 0 4px;letter-spacing:.12em;text-transform:uppercase">失败类型分布 · 共 ' + attrSum + ' 条</h4>' + '<div class="mini" style="margin:0 0 12px">' + attrSum + ' = ' + injectedDetected + ' 次弄坏后抓住 + ' + selfFailures + ' 条没塞进去、但 Agent 自己出错</div>' + attrHtml +
      '<div class="note" style="margin-top:16px"><span>◒</span><div>最容易混的是「没做完」和「用错工具」：动作都合理、只是停下来了，算没做完；乱试、选错工具，才算用错工具。这条写进第二版规则后，κ 从 0.52 到 0.80。</div></div></div>' +
    '<div class="acard"><h4 class="mini" style="margin:0 0 6px;letter-spacing:.12em">规则和人工，能对上多少（κ）</h4>' +
      '<div class="kbig">' + kappa.k.toFixed(2) + '</div>' +
      '<div class="kmeta">n=' + kappa.n + ' · 95% 区间 ' + kappa.lo.toFixed(2) + '–' + kappa.hi.toFixed(2) + ' · 83.3% 完全一致</div>' +
      '<div class="ci"><div class="track"></div><div class="band" style="left:' + (kappa.lo * 100) + '%;width:' + ((kappa.hi - kappa.lo) * 100) + '%"></div>' +
        '<div class="mark before" style="left:52%"></div><div class="mark" style="left:' + (kappa.k * 100) + '%"></div>' +
        '<div class="lab" style="left:52%">0.52</div><div class="lab" style="left:' + (kappa.k * 100) + '%">0.80</div></div>' +
      '<div class="ci-legend"><span>0.0</span><span>1.0</span></div>' +
      '<div class="kflow"><span>第一版规则</span><b>0.52</b><span class="arrow">→</span><span>加了先后顺序</span><b>0.80</b></div>' +
      '<div class="kmeta" style="margin-top:12px">0.80 不算高，但比第一版好不少。样本只有 30 条，区间很宽，只能说明这套规则别人也能照着用。</div></div>' +
  '</div>' +
  '</section>';

const FOOTER = '<footer><div class="wrap">' +
  '<div class="fgrid">' +
    '<div><h5>这些数字怎么算的</h5><p>「抓住几次」的分母，是真的把毛病塞进去的次数，不是计划跑的次数。</p><p>pass^k 只看正常跑的那组，40 条 × 3 轮。</p><p>κ 是规则和人工对不对得上，不是模型准不准。</p></div>' +
    '<div><h5>别吹过头</h5><p>40 条题是合成的，加美林那 70 条真实问题改的，8 类场景，不代表所有教务情况。</p><p>LangGraph 只跑了 120 次，不能说谁更好。</p><p>一台机器、一个模型、温度固定 0。</p></div>' +
    '<div><h5>东西在哪</h5><p><code>reports/dashboard_data.json</code></p><p><code>cases/seed_cases.jsonl</code></p><p><code>reports/full_matrix</code> · <code>reports/langgraph_k3</code></p><p><code>work/build_dashboard.mjs</code></p></div>' +
  '</div>' +
  '<div class="fend"><span>Agent 验收审计 · 2026-10-24</span><span>离线单文件 · 数据都在页面里 · 不联网</span></div>' +
  '</div></footer>';

const PAGE_JS = `
(function () {
  var D = JSON.parse(document.getElementById('data').textContent);
  var L = D.labels;
  var MODES = ['none', 'wrong_arg', 'skip_clarify', 'context_drop', 'policy_ignore', 'pii_leak', 'early_stop'];
  var byId = {};
  D.cases.forEach(function (c) { byId[c.id] = c; });
  var state = { family: D.cases[0].family, id: D.cases[0].id, mode: 'wrong_arg', lg: D.lg[0].id };
  var casesVisible = false;

  function $(s) { return document.querySelector(s); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function money(n) { return '¥' + Number(n || 0).toFixed(3); }
  function short(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n) + '…' : s; }
  var CLS_DESC = { parameter: '工具没选错，但值填错了。下面红框就是填错的那个。', tool: '工具选错，或者在不相干的对象上反复试。', planning: '动作都合理，就是没做完就停了。', permission: '查了不该查的课，或动了不该动的操作。', data: '回复里带了不该带的个人信息。', context: '该问的没问，或者用了过期的信息。' };
  var A_LABEL = { 'no_permission_violation': '没有偷偷查别的课', 'max_turns': '轮次没超', 'max_cost': '花费没超', 'reply_contains_any': '回复里有指定说法', 'forbidden_pattern:phone': '回复里没有手机号', 'final_state:ticket_count': '建了几张工单', 'final_state:last_ticket.course_id': '工单开在哪个课', 'final_state:last_ticket.issue_type': '工单类型对不对', 'final_state:violation_count': '越权次数', 'final_state:last_updated.id': '改的是哪张工单', 'final_state:last_updated.status': '工单改成了什么状态', 'final_state:refunds_count': '退款次数', 'final_state:last_chart_query': '最后查的哪个课' };
  var ISSUE_LABEL = { 'doc_field_mismatch': '手册字段对不上', 'missing_grade': '成绩缺失', 'chart_mismatch': '图表缺类别', 'env_dependency': '环境缺依赖', 'permission': '越权', 'duplicate_ticket': '重复工单', 'policy_exception': '政策例外', 'context_switch': '多轮改主意' };
  var STATUS_CN = { 'open': '处理中', 'closed': '已关闭', 'reopened': '重新打开', 'pending': '待处理' };
  var TOOLARG_LABEL = { 'create_ticket.course_id': '建单时课程号填对', 'get_student_record.student_id': '查成绩时学号填对', 'update_ticket.ticket_id': '改单时工单号填对' };
  var STATE_LABEL = { 'ticket_count': '工单数', 'last_ticket.course_id': '工单开在哪个课', 'last_ticket.issue_type': '工单类型', 'violation_count': '越权次数', 'last_updated.id': '改的工单号', 'last_updated.status': '改完的状态', 'refunds_count': '退款次数', 'last_chart_query': '最后查的课' };
  function assertLabel(n) {
    if (A_LABEL[n]) return A_LABEL[n];
    if (n.indexOf('required_tool:') === 0) return '要用 ' + n.slice(14);
    if (n.indexOf('forbidden_tool:') === 0) return '不能碰 ' + n.slice(15);
    if (n.indexOf('tool_arg:') === 0) { var p = n.slice(9); return TOOLARG_LABEL[p] || ('填对 ' + p); }
    if (n.indexOf('clarification_before_tool:') === 0) return '先问再动手';
    return n;
  }
  function cleanVal(s) {
    s = String(s || '').split('[').join('').split(']').join('').split(String.fromCharCode(39)).join('').split(String.fromCharCode(34)).join('');
    return s.split(',').join('、');
  }
  function humanDetail(n, d) {
    d = String(d || '');
    if (d === 'violations=[]') return '没有跨课程访问';
    if (d.indexOf('turns=') === 0) { var t = d.split(', '); return '用了 ' + t[0].slice(6) + ' 轮（上限 ' + t[1].slice(4) + '）'; }
    if (d.indexOf('cost_cny=') === 0) { var c = d.split(', '); return '花了 ¥' + c[0].slice(9) + '（上限 ¥' + c[1].slice(4) + '）'; }
    if (d.indexOf('expected=') === 0 && d.indexOf(', got=') > 0) { var i = d.indexOf(', got='); var ev = cleanVal(d.slice(9, i)); var gv = cleanVal(d.slice(i + 6)); if (n.indexOf('issue_type') > 0) { ev = ISSUE_LABEL[ev] || ev; gv = ISSUE_LABEL[gv] || gv; } return '应为 ' + ev + '，实际 ' + gv; }
    if (d.indexOf('allowed=') === 0) { var a = d.split(', bad_values='); return '只允许 ' + cleanVal(a[0].slice(8)) + (a[1] && a[1] !== '[]' ? '；写成了 ' + cleanVal(a[1]) : '；没写错'); }
    if (d.indexOf('called=[') === 0) { var raw = d.slice(8, d.lastIndexOf(']')).split(', '); var seen = [], out = []; raw.forEach(function (x) { x = x.split(String.fromCharCode(39)).join(''); if (seen.indexOf(x) < 0) { seen.push(x); out.push(x); } }); if (n.indexOf('required_tool:') === 0) return out.indexOf(n.slice(14)) >= 0 ? '调过' : '没调过'; if (n.indexOf('forbidden_tool:') === 0) return out.indexOf(n.slice(15)) >= 0 ? '碰了 ' + n.slice(15) : '没碰'; return out.length ? '用了：' + out.join(' → ') : '没有调用'; }
    if (d.indexOf('expected_any=') === 0) return '回复里要出现 ' + cleanVal(d.slice(13));
    if (d.indexOf('regex=') === 0) return d.indexOf('match=None') > 0 ? '回复里没有手机号' : '回复里出现了手机号';
    if (d.indexOf('must ask') > 0) return '动手前得先问一句';
    return d;
  }
  function stateOf(c, m) {
    var r = c.runs[m];
    if (m === 'none') return r.pass ? 'p' : 'f';
    return r.pass ? 'n' : 'f';
  }

  function renderChips() {
    var box = $('#familyChips');
    box.innerHTML = D.families.map(function (f) {
      return '<button class="chip' + (f.key === state.family ? ' on' : '') + '" data-f="' + f.key + '" aria-pressed="' + (f.key === state.family) + '">' +
        L.family[f.key] + '<i>' + f.count + '</i></button>';
    }).join('');
  }

  function renderGrid() {
    var list = D.cases.filter(function (c) { return c.family === state.family; });
    var box = $('#caseGrid');
    box.innerHTML = list.map(function (c) {
      var dots = MODES.map(function (m) {
        var s = stateOf(c, m);
        return '<i class="' + (s === 'p' ? 'p' : s === 'f' ? 'f' : '') + '"></i>';
      }).join('');
      return '<button class="case' + (c.id === state.id ? ' on' : '') + '" data-c="' + c.id + '">' +
        '<span class="cid">' + c.id + '</span><span class="ct">' + esc(c.title) + '</span><span class="dots">' + dots + '</span></button>';
    }).join('');
  }

  function kvRows(exp, maxCost) {
    var rows = [];
    if (exp.final_state) {
      var parts = Object.keys(exp.final_state).map(function (k) {
        var v = exp.final_state[k]; if (k === 'last_ticket.issue_type' && ISSUE_LABEL[v]) v = ISSUE_LABEL[v]; return (STATE_LABEL[k] || k) + ' = ' + (typeof v === 'string' ? v : JSON.stringify(v));
      });
      rows.push(['最后应该', parts.join(' · ')]);
    }
    if (exp.required_tools && exp.required_tools.length) rows.push(['必须用到', exp.required_tools.join(' → ')]);
    if (exp.forbidden_tools && exp.forbidden_tools.length) rows.push(['不能碰', exp.forbidden_tools.join('、')]);
    if (exp.tool_arg_constraints && exp.tool_arg_constraints.length) {
      rows.push(['填值要求', exp.tool_arg_constraints.map(function (x) { return x.tool + ' 的 ' + x.arg + ' 只能是 ' + x.allowed.join('/'); }).join(' · ')]);
    }
    if (exp.clarification_before_tool) rows.push(['先问一句', '调用 ' + exp.clarification_before_tool + ' 之前，要先问清楚']);
    if (exp.reply_contains_any && exp.reply_contains_any.length) rows.push(['回复里要有', exp.reply_contains_any.join(' 或 ')]);
    if (exp.no_permission_violation) rows.push(['不能越权', '0 次跨课程访问']);
    if (exp.max_turns) rows.push(['上限', exp.max_turns + ' 轮 · ' + money(exp.max_cost_cny || maxCost)]);
    return rows.map(function (r) { return '<dt>' + r[0] + '</dt><dd>' + esc(r[1]) + '</dd>'; }).join('');
  }

  function pickArg(a, key) {
    var i = a.indexOf('"' + key + '"');
    if (i < 0) return '';
    var k = a.indexOf('"', a.indexOf(':', i) + 1);
    if (k < 0) return '';
    var e = a.indexOf('"', k + 1);
    return e > k ? a.slice(k + 1, e) : '';
  }
  function toolGloss(n, a) {
    var o = {};
    try { o = JSON.parse(a); } catch (e) { o = {}; }
    if (!o.course_id) o.course_id = pickArg(a, 'course_id');
    if (!o.ticket_id) o.ticket_id = pickArg(a, 'ticket_id');
    if (!o.issue_type) o.issue_type = pickArg(a, 'issue_type');
    if (!o.status) o.status = pickArg(a, 'status');
    if (n === 'get_course') return '查课程 ' + (o.course_id || '');
    if (n === 'get_student_record') return '查 ' + (o.student_id || '') + ' 在 ' + (o.course_id || '') + ' 的成绩';
    if (n === 'search_knowledge') return '查知识库：' + short(o.query || '', 26);
    if (n === 'list_tickets') return '列 ' + (o.course_id || '') + ' 的工单' + (o.status ? '（' + (STATUS_CN[o.status] || o.status) + '）' : '');
    if (n === 'create_ticket') return '建工单：' + (o.course_id || '') + (o.issue_type ? ' / ' + (ISSUE_LABEL[o.issue_type] || o.issue_type) : '');
    if (n === 'get_ticket') return '查工单 ' + (o.ticket_id || '');
    if (n === 'update_ticket') return '改工单 ' + (o.ticket_id || '') + ' → ' + (STATUS_CN[o.status] || o.status || '');
    if (n === 'check_policy') return '查政策：' + (o.topic || '');
    if (n === 'get_chart_config') return '查 ' + (o.course_id || '') + ' 的图表配置';
    if (n === 'send_reply') return '发出回复';
    if (n === 'refund_course') return '发起退款：' + (o.course_id || '');
    return n;
  }

  function renderPanel() {
    var c = byId[state.id];
    var r = c.runs[state.mode];
    var panel = $('#casePanel');
    var steps = (r.tools || []).length;
    var head = '<div class="panel-top"><div class="panel-title"><span class="cid">' + c.id + '</span><h3>' + esc(c.title) + '</h3></div>' +
      '<div class="run-meta">调了 ' + steps + ' 次工具 · ' + r.turns + ' 轮 · ' + money(r.cost) + '</div></div>';
    var ask = '<div class="ask">' + c.turns.map(function (t) { return '<div class="bubble">' + esc(t) + '</div>'; }).join('') + '</div>';
    var modes = '<div class="modes">' + MODES.map(function (m) {
      var s = stateOf(c, m);
      return '<button class="mode' + (m === state.mode ? ' on' : '') + '" data-m="' + m + '" data-s="' + s + '" title="' + m + '"><i class="dot"></i>' +
        L.mode[m] + '</button>';
    }).join('') + '<span class="legend"><i></i>灰点 = 这次没塞进去，不算漏抓 · 键盘 ← → 换跑法</span></div>';

    var whyText = r.pass ? (r.asserts || []).length + ' 项检查全过，没碰到禁止项。' : (CLS_DESC[r.cls] || r.why);
    var verdict = r.pass
      ? '<div class="verdict ok"><b>没毛病</b><span>' + esc(short(whyText, 240)) + '</span></div>'
      : '<div class="verdict bad"><b>抓住 · ' + (L.attr[r.cls] || r.cls || '-') + '</b><span>' + esc(short(whyText, 260)) + '</span></div>';

    var asserts = (r.asserts || []).map(function (a) {
      var detail = humanDetail(a.n, a.d);
      var long = String(detail).length > 74;
      return '<li class="' + (a.p ? '' : 'bad') + '" data-expandable="' + (long ? '1' : '0') + '">' +
        '<span class="ico">' + (a.p ? '✓' : '✕') + '</span><div><div class="an" title="' + esc(a.n) + '">' + esc(assertLabel(a.n)) + '</div>' +
        '<div class="ad">' + esc(detail) + '</div></div></li>';
    }).join('');

    var trace = (r.tools || []).map(function (t, i) {
      var a = typeof t.a === 'string' ? t.a : JSON.stringify(t.a || {});
      return '<li><span class="no">' + String(i + 1).padStart(2, '0') + '</span><div><div class="tn">' + esc(t.n) + '</div>' +
        '<div class="ta" title="' + esc(a) + '">' + esc(toolGloss(t.n, a)) + '</div></div></li>';
    }).join('');

    var replyText = String(r.reply || '').trim();
    var reply = replyText ? esc(replyText) : '<span class="empty">（这一轮没说话）</span>';
    var more = String(r.reply || '').length > 300 ? '<button class="more" data-more="1">展开全文</button>' : '';

    panel.innerHTML = head + ask + modes +
      '<div class="detail">' +
        '<div class="d-col">' + verdict +
          '<h4>这题算对的标志</h4><dl class="kv">' + kvRows(c.expected, c.max_cost) + '</dl>' +
          '<h4 class="mt">检查项 · ' + (r.asserts || []).length + ' 条</h4><ul class="asserts">' + asserts + '</ul>' +
        '</div>' +
        '<div class="d-col">' +
          '<h4>它做了什么 · ' + steps + ' 步</h4><ol class="trace">' + (trace || '<li><span class="no">—</span><div class="tn" style="color:var(--ter)">没有调用工具</div></li>') + '</ol>' +
          '<h4 class="mt">它最后说了什么</h4><div class="reply">' + reply + '</div>' + more +
        '</div>' +
      '</div>';
  }

  function renderAll() { renderChips(); renderGrid(); renderPanel(); }

  $('#familyChips').addEventListener('click', function (e) {
    var b = e.target.closest('[data-f]');
    if (!b) return;
    state.family = b.getAttribute('data-f');
    var first = D.cases.filter(function (c) { return c.family === state.family; })[0];
    state.id = first.id;
    state.mode = 'none';
    renderAll();
  });

  $('#caseGrid').addEventListener('click', function (e) {
    var b = e.target.closest('[data-c]');
    if (!b) return;
    state.id = b.getAttribute('data-c');
    state.mode = 'none';
    renderGrid();
    renderPanel();
  });

  $('#casePanel').addEventListener('click', function (e) {
    var m = e.target.closest('[data-m]');
    if (m) { state.mode = m.getAttribute('data-m'); renderPanel(); return; }
    var more = e.target.closest('[data-more]');
    if (more) {
      var rep = more.previousElementSibling;
      rep.classList.add('open');
      more.style.display = 'none';
      return;
    }
    var li = e.target.closest('.asserts li');
    if (li && li.getAttribute('data-expandable') === '1') li.classList.toggle('open');
  });
`;

const PAGE_JS2 = `
  function renderLgTabs() {
    $('#lgTabs').innerHTML = D.lg.map(function (s) {
      var c = byId[s.id];
      return '<button class="chip' + (s.id === state.lg ? ' on' : '') + '" data-lg="' + s.id + '">' + s.id + ' · ' + esc(c.title) + '</button>';
    }).join('');
  }

  function stepsHtml(steps, alt) {
    var out = '';
    steps.slice(0, 10).forEach(function (s, i) {
      out += '<li><span class="n">' + String(i + 1).padStart(2, '0') + '</span><div><div class="nm">' + esc(s.n) + '</div>' +
        '<div class="ag" title="' + esc(s.a) + '">' + esc(toolGloss(s.n, s.a)) + '</div></div></li>';
    });
    if (steps.length > 10) out += '<div class="more-x">+ ' + (steps.length - 10) + ' 步未展开</div>';
    return out;
  }

  function renderLg() {
    var s = D.lg.filter(function (x) { return x.id === state.lg; })[0];
    var c = byId[s.id];
    var r = c.runs.none;
    var aSteps = (r.tools || []).map(function (t) { return { n: t.n, a: typeof t.a === 'string' ? t.a : JSON.stringify(t.a || {}) }; });
    var aMeta = r.turns + ' 轮 · ' + aSteps.length + ' 步 · ' + money(r.cost);
    var bMeta = s.turns + ' 轮 · ' + s.steps.length + ' 步 · ' + (s.latency / 1000).toFixed(1) + ' s · ' + money(s.cost) + ' · ' + s.completion + ' tokens';
    $('#lgGrid').innerHTML =
      '<div class="lg-col"><h5><i></i>自己写的 Agent · ' + s.id + '</h5><div class="lg-meta">' + aMeta + '</div><ol class="steps">' + stepsHtml(aSteps) + '</ol></div>' +
      '<div class="lg-col alt"><h5><i></i>LangGraph ReAct · ' + s.id + '</h5><div class="lg-meta">' + bMeta + '</div><ol class="steps">' + stepsHtml(s.steps) + '</ol></div>';
  }

  $('#lgTabs').addEventListener('click', function (e) {
    var b = e.target.closest('[data-lg]');
    if (!b) return;
    state.lg = b.getAttribute('data-lg');
    renderLgTabs();
    renderLg();
  });

  var secs = Array.prototype.slice.call(document.querySelectorAll('main section[id]'));
  var links = Array.prototype.slice.call(document.querySelectorAll('.links a'));
  function setActive(id) {
    links.forEach(function (a) { a.classList.toggle('on', a.getAttribute('href') === '#' + id); });
  }
  var navIO = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) { if (en.isIntersecting) setActive(en.target.id); });
  }, { rootMargin: '-42% 0px -54% 0px', threshold: 0 });
  secs.forEach(function (s) { navIO.observe(s); });

  var caseIO = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) { casesVisible = en.isIntersecting; });
  }, { threshold: 0.12 });
  caseIO.observe($('#cases'));

  var revealIO = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (en.isIntersecting) { en.target.classList.add('in'); revealIO.unobserve(en.target); }
    });
  }, { threshold: 0.08, rootMargin: '0px 0px -6% 0px' });
  Array.prototype.slice.call(document.querySelectorAll('.rv')).forEach(function (el, i) {
    el.style.transitionDelay = Math.min(i % 6, 5) * 40 + 'ms';
    revealIO.observe(el);
  });

  var bar = document.getElementById('progressBar');
  var nav = document.querySelector('.nav');
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      bar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + '%';
      nav.classList.toggle('stuck', h.scrollTop > 6);
      ticking = false;
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  document.addEventListener('keydown', function (e) {
    if (!casesVisible) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    var i = MODES.indexOf(state.mode);
    i = e.key === 'ArrowRight' ? (i + 1) % MODES.length : (i - 1 + MODES.length) % MODES.length;
    state.mode = MODES[i];
    renderPanel();
    e.preventDefault();
  });

  var root = document.documentElement;
  var themeBtn = document.getElementById('themeBtn');
  try {
    var saved = localStorage.getItem('audit-theme');
    if (saved === 'dark') root.setAttribute('data-theme', 'dark');
  } catch (err) {}
  function syncTheme() {
    var dark = root.getAttribute('data-theme') === 'dark';
    themeBtn.textContent = dark ? '◑' : '◐';
    themeBtn.setAttribute('aria-label', dark ? '切换到浅色' : '切换到深色');
    themeBtn.setAttribute('aria-pressed', dark ? 'true' : 'false');
  }
  themeBtn.addEventListener('click', function () {
    var dark = root.getAttribute('data-theme') === 'dark';
    if (dark) root.removeAttribute('data-theme'); else root.setAttribute('data-theme', 'dark');
    try { localStorage.setItem('audit-theme', dark ? 'light' : 'dark'); } catch (err) {}
    syncTheme();
  });
  syncTheme();

  renderAll();
  renderLgTabs();
  renderLg();
})();
`;

const CSS4 = `
section[id]{scroll-margin-top:80px}
.lg-col,.lg-col .steps,.lg-col .steps li,.lg-col .steps li > div{min-width:0}
.panel-top{flex-wrap:wrap}
.cmp-wrap{overflow-x:auto}
.fault.rv.in .f-bar i{width:var(--w)}
.tasks.rv.in .task .tb i{width:var(--w)}
.attr.rv.in .arow .ab i{width:var(--w)}
.reveal{opacity:1}
`;

const NAV = '<div class="topline"><i id="progressBar"></i></div>' +
  '<header class="nav"><a class="brand" href="#overview"><span class="ring"><span>验</span></span>' +
  '<span class="brand-text"><b>验收审计</b><em>给 Agent 做体检</em></span></a>' +
  '<nav class="links"><a href="#overview" class="on">结论</a><a href="#cases">看用例</a><a href="#faults">弄坏它</a>' +
  '<a href="#rival">换框架</a><a href="#meilin">美林</a><a href="#attrib">错在哪</a></nav>' +
  '<button class="theme" id="themeBtn" aria-label="切换深色">◐</button></header>';

const dataText = JSON.stringify(payload).replace(/</g, String.fromCharCode(92) + 'u003c');

const html = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' +
  '<meta name="color-scheme" content="light dark">' +
  '<meta name="description" content="Agent 验收审计：40 条用例、520 次运行、故障注入、LangGraph 对照、美林 70 条 badcase。">' +
  '<title>Agent 验收审计 · 520 runs</title>' +
  '<style>' + CSS + CSS2 + CSS3 + CSS4 + '</style></head><body>' +
  NAV + '<main>' + HERO + CASES + FAULTS + RIVAL + MEILIN + ATTRIB + '</main>' + FOOTER +
  '<noscript><style>.rv{opacity:1;transform:none}</style></noscript><script id="data" type="application/json">' + dataText + '</script>' +
  '<script>' + PAGE_JS + PAGE_JS2 + '</script>' +
  '</body></html>';

fs.writeFileSync(path.join(ROOT, 'reports/dashboard.html'), html, 'utf8');
console.log('dashboard.html', Buffer.byteLength(html, 'utf8'), 'bytes');
console.log('payload cases', payload.cases.length, 'lg', payload.lg.length);
