const MODES = {
  L0: {
    name: 'L0 · 对照组',
    intro: '同一个业务场景，查看缺少精确影响范围时会发生什么',
    steps: [
      { id: 'l0-normal', label: '正常传播', duration: 4300, title: 'claim A 与 claim B 同时开始传播', detail: '两条业务信息从供应商出发，共用主干后进入各自分支' },
      { id: 'l0-fault', label: '错误传播', duration: 5600, title: '上游信息出错，错误沿 claim A 传到买家 A', detail: 'claim B 保持正常，不受这次信息错误影响' },
      { id: 'l0-freeze', label: '全部冻结', duration: 5600, title: '无法精准定位，只能冻结仓库之后的全部支路', detail: 'claim B 的无关分支也被一起暂停' }
    ]
  },
  L4: {
    name: 'L4 · MAST',
    intro: '同一场景，查看 MAST 如何只阻断受影响部分并恢复',
    steps: [
      { id: 'l4-normal', label: '正常传播', duration: 3300, title: 'claim A 与 claim B 同时开始传播', detail: '场景、拓扑与初始信息和 L0 相同' },
      { id: 'l4-fault', label: '发现错误', duration: 3900, title: '上游信息出错，MAST 追踪 claim A 的依赖路径', detail: '红色只表示正在传播的错误信息' },
      { id: 'l4-contain', label: '局部阻断', duration: 4700, title: '只冻结受影响的 claim A，claim B 继续', detail: '依赖范围内局部阻断，无关业务不中断' },
      { id: 'l4-repair', label: '修订重建', duration: 4300, title: '权威来源发布修订 A′，重新构建受影响路径', detail: '紫色 A′ 是一条新链，旧 A 保持失效' },
      { id: 'l4-recheck', label: '重新检查', duration: 3300, title: '重新检查通过后，claim A 恢复执行', detail: '修复后的 A 安全完成，claim B 始终未中断' }
    ]
  }
};

let replay;
let currentMode = 'L0';
let index = -1;
let timer = null;
let running = false;
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

function money(cents) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: replay.business.currency, minimumFractionDigits: 2
  }).format(cents / 100);
}

function steps() { return MODES[currentMode].steps; }

function setModeUI() {
  $('#mode-l0').classList.toggle('active', currentMode === 'L0');
  $('#mode-l4').classList.toggle('active', currentMode === 'L4');
  $('#mode-l0').setAttribute('aria-pressed', String(currentMode === 'L0'));
  $('#mode-l4').setAttribute('aria-pressed', String(currentMode === 'L4'));
  $('#stage-mode').textContent = MODES[currentMode].name;
}

function buildTimeline() {
  $('#timeline').innerHTML = steps().map((step, i) =>
    `<li role="button" tabindex="0" data-index="${i}"><span>${i + 1}</span><b>${step.label}</b></li>`
  ).join('');
  $$('#timeline li').forEach(item => {
    const jump = () => {
      stop();
      render(Number(item.dataset.index));
    };
    item.addEventListener('click', jump);
    item.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        jump();
      }
    });
  });
}

function showOutcome(html, tone) {
  const outcome = $('#outcome');
  outcome.className = `outcome show ${tone}`;
  outcome.innerHTML = html;
}

function render(nextIndex) {
  index = nextIndex;
  const step = steps()[index];
  const stage = $('.stage');
  stage.className = 'stage';
  void stage.offsetWidth;
  stage.classList.add(step.id);
  setModeUI();
  $('#stage-title').textContent = step.title;
  $('#stage-detail').textContent = step.detail;
  $('#outcome').className = 'outcome';
  $('#outcome').innerHTML = '';
  $$('#timeline li').forEach((item, i) => {
    item.className = i < index ? 'done' : i === index ? 'active' : '';
  });

  if (step.id === 'l0-fault' || step.id === 'l4-fault') {
    $('#stage-detail').textContent = `信息由 ${money(replay.business.base_cents)} 更正为 ${money(replay.business.corrected_cents)}；错误只沿 claim A 传播`;
  }
  if (step.id === 'l0-freeze') {
    showOutcome('<b>影响范围不明</b><span>仓库后的 A、B 两条支路全部冻结</span><i></i><b>无关业务受影响</b><span>买家 B 也被迫等待</span>', 'danger');
  }
  if (step.id === 'l4-contain') {
    showOutcome('<b>claim A</b><span>受影响路径已冻结</span><i></i><b>claim B</b><span>无关分支持续执行</span>', 'contain');
  }
  if (step.id === 'l4-repair') {
    $('#stage-detail').textContent = `旧 A 失效 · 权威确认 ${money(replay.business.base_cents)} → ${money(replay.business.corrected_cents)} · 新 A′ 逐层重建`;
  }
  if (step.id === 'l4-recheck') {
    showOutcome('<b>claim A</b><span>修订后重建，重新检查通过</span><i></i><b>claim B</b><span>始终未受影响，持续完成</span>', 'safe');
  }
}

function schedule() {
  if (!running) return;
  const currentStep = steps()[index];
  timer = setTimeout(() => {
    if (index >= steps().length - 1) {
      running = false;
      $('#auto').innerHTML = '<span>↻</span> Auto Replay';
      $('#pause').innerHTML = 'Ⅱ　暂停';
      return;
    }
    render(index + 1);
    schedule();
  }, currentStep.duration);
}

function stop() {
  clearTimeout(timer);
  running = false;
  $('#auto').innerHTML = '<span>↻</span> Auto Replay';
  $('#pause').innerHTML = 'Ⅱ　暂停';
}

function reset() {
  stop();
  index = -1;
  $('.stage').className = 'stage';
  setModeUI();
  $('#stage-title').textContent = '准备开始';
  $('#stage-detail').textContent = MODES[currentMode].intro;
  $('#outcome').className = 'outcome';
  $('#outcome').innerHTML = '';
  $$('#timeline li').forEach(item => { item.className = ''; });
}

function switchMode(mode) {
  if (mode === currentMode) return;
  currentMode = mode;
  buildTimeline();
  reset();
}

async function init() {
  replay = await fetch('public/replay.json').then(response => {
    if (!response.ok) throw Error('replay.json unavailable');
    return response.json();
  });
  $('#fixture-id').textContent = replay.fixture_id;
  buildTimeline();
  $('#mode-l0').addEventListener('click', () => switchMode('L0'));
  $('#mode-l4').addEventListener('click', () => switchMode('L4'));
  $('#auto').addEventListener('click', () => {
    reset();
    running = true;
    render(0);
    schedule();
  });
  $('#pause').addEventListener('click', () => {
    if (index < 0) return;
    if (running) {
      clearTimeout(timer);
      running = false;
      $('#pause').innerHTML = '▶　继续';
    } else {
      running = true;
      $('#pause').innerHTML = 'Ⅱ　暂停';
      schedule();
    }
  });
  $('#step').addEventListener('click', () => {
    stop();
    render(Math.min(index + 1, steps().length - 1));
  });
  $('#reset').addEventListener('click', reset);
  if (new URLSearchParams(location.search).get('presentation') === '1') {
    document.body.classList.add('presentation');
  }
  reset();
}

init().catch(error => {
  $('#stage-title').textContent = '重放数据加载失败';
  $('#stage-detail').textContent = error.message;
});
