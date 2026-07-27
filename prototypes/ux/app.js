const STORAGE_KEY = 'shiguang-ux-review-notes-v2';

const screenDefinitions = [
  {
    id: 'agent',
    code: 'M01',
    title: 'Agent 首页',
    short: '输入与首次价值',
    nav: 'agent',
    purpose: '验证用户是否能快速理解：这里不是推荐信息流，而是把内容交给 Agent 的入口。',
    checks: ['主输入和两个任务入口是否清楚', '三种输入方式是否容易理解', '用户是否知道收藏何时足以生成计划'],
    states: [
      ['default', '默认'],
      ['listening', '已输入要求'],
      ['empty', '无收藏']
    ],
    interactions: [
      ['发送内容', '进入识别结果'],
      ['收藏一个地点 / 帮我安排时间', '明确选择任务'],
      ['查看或添加收藏', '有内容时看详情，无内容时添加'],
      ['底部导航', '切换一级页面']
    ],
    render: renderAgent
  },
  {
    id: 'import',
    code: 'M02',
    title: '对话与收藏结果',
    short: '识别、修改与撤销',
    nav: 'agent',
    purpose: '验证 Agent 是否清楚说明识别结果、字段来源与接下来的可逆操作。',
    checks: ['标题和阶段随识别状态变化', '撤销后可以真实恢复', '待补充、待选择与失败有不同恢复路径'],
    states: [
      ['saved', '已收藏'],
      ['recognizing', '识别中'],
      ['ambiguous', '待选择'],
      ['needs_input', '待补充'],
      ['undone', '已撤销'],
      ['failed', '识别失败']
    ],
    interactions: [
      ['修改', '进入地点消歧'],
      ['撤销', '撤销本次收藏'],
      ['用它生成计划', '进入计划草稿']
    ],
    render: renderImport
  },
  {
    id: 'collection',
    code: 'M03',
    title: '收藏库',
    short: '搜索、筛选与状态',
    nav: 'collection',
    purpose: '验证收藏库能否让用户快速找到可规划地点，并区分待确认内容。',
    checks: ['多城市收藏是否容易理解', '每条收藏是否说明能否参与当前计划', '待选择内容是否明显且不会误入规划'],
    states: [
      ['default', '有内容'],
      ['pending', '含待确认'],
      ['empty', '空收藏']
    ],
    interactions: [
      ['搜索与筛选', '缩小收藏范围'],
      ['点击地点卡', '查看和修改详情'],
      ['新建计划', '使用筛选结果规划']
    ],
    render: renderCollection
  },
  {
    id: 'detail',
    code: 'M04',
    title: '收藏详情与消歧',
    short: '确认准确地点',
    nav: 'collection',
    purpose: '验证只有店名或存在同名分店时，用户能否低成本完成地点确认。',
    checks: ['候选、任意分店和以上都不是是否完整', '系统是否真实记录用户选择', '修改、删除后能否返回原对话'],
    states: [
      ['ambiguous', '待选择'],
      ['selected', '已选择'],
      ['any_branch', '任意分店'],
      ['missing', '需要补充']
    ],
    interactions: [
      ['选择候选地点', '绑定准确 POI'],
      ['任意分店 / 以上都不是', '记录品牌级或待补充选择'],
      ['编辑或删除', '修改结构化字段或移除收藏'],
      ['确认并保存', '返回原对话上下文']
    ],
    render: renderDetail
  },
  {
    id: 'plan',
    code: 'M05',
    title: '计划草稿',
    short: '时间、路线与预算',
    nav: 'plan',
    purpose: '验证用户能否理解计划由哪些收藏组成、为什么补充外部地点，以及预算与风险。',
    checks: ['时间光轨是否易读', '高德补充是否显著但不过度打扰', '预算是否明确交给用户判断'],
    states: [
      ['draft', '计划草稿'],
      ['alternatives', '查看备选'],
      ['generating', '生成中'],
      ['permission', '外部授权'],
      ['collection_only', '仅用收藏'],
      ['failed', '工具失败']
    ],
    interactions: [
      ['自然语言调整', '保留其余约束重新计算'],
      ['确认方案', '进入执行入口'],
      ['外部地点操作', '替换、删除或收藏']
    ],
    render: renderPlan
  },
  {
    id: 'confirmed',
    code: 'M06',
    title: '已确认计划',
    short: '执行、提醒与反馈',
    nav: 'plan',
    purpose: '验证确认后的行动入口是否集中，并解释反馈如何影响下一次规划。',
    checks: ['提醒是否在确认后单独授权', '版本、取消和分享是否可管理', '三种完成反馈是否有各自后续操作'],
    states: [
      ['confirmed', '已确认'],
      ['reminder', '设置提醒'],
      ['share_preview', '分享预览'],
      ['share_active', '分享管理'],
      ['versions', '版本与取消'],
      ['partial', '部分完成'],
      ['incomplete', '未完成'],
      ['feedback', '完成反馈']
    ],
    interactions: [
      ['打开路线', '模拟高德导航'],
      ['设置提醒', '创建单次提醒'],
      ['分享方案', '先脱敏预览，再创建链接'],
      ['版本与取消', '修改、查看历史或取消计划']
    ],
    render: renderConfirmed
  },
  {
    id: 'me',
    code: 'M07',
    title: '我的',
    short: '记忆、提醒与渠道',
    nav: 'me',
    purpose: '验证长期记忆是否透明可控，并清楚区分 Web 与微信使用渠道。',
    checks: ['用户能否看懂系统记住了什么', '推断偏好是否需要确认', '删除、导出和连接状态是否清晰'],
    states: [
      ['default', '默认'],
      ['suggestion', '偏好待确认'],
      ['memory', '记忆详情'],
      ['privacy', '隐私管理']
    ],
    interactions: [
      ['管理偏好', '查看、修改或删除记忆'],
      ['提醒设置', '开关单次与主动提醒'],
      ['微信入口', '了解如何在微信里继续使用拾光']
    ],
    render: renderMe
  },
  {
    id: 'share',
    code: 'M08',
    title: '只读分享页',
    short: '脱敏的计划查看',
    nav: null,
    purpose: '验证未登录访客能否理解计划，同时确认原用户的收藏和私人记忆不会泄露。',
    checks: ['只读属性是否明确', '费用和路线是否足够独立理解', '关闭或失效后是否给出明确说明'],
    states: [
      ['valid', '有效'],
      ['cancelled', '计划已取消'],
      ['revoked', '分享已关闭'],
      ['expired', '链接已失效']
    ],
    interactions: [
      ['打开地点', '查看公开地图信息'],
      ['生成我的计划', '回到拾光首页'],
      ['复制链接', '模拟复制成功']
    ],
    render: renderShare
  }
];

const stateByScreen = Object.fromEntries(
  screenDefinitions.map(function (screen) {
    return [screen.id, screen.states[0][0]];
  })
);

let currentScreenId = 'agent';
let currentView = 'single';
let currentCanvas = 'mobile';
let toastTimer;
let reminderEnabled = false;
let shareActive = false;

const els = {
  screenList: document.getElementById('screenList'),
  prototypeScreen: document.getElementById('prototypeScreen'),
  stageCode: document.getElementById('stageCode'),
  stageTitle: document.getElementById('stageTitle'),
  stageState: document.getElementById('stageState'),
  singleView: document.getElementById('singleView'),
  overviewView: document.getElementById('overviewView'),
  overviewGrid: document.getElementById('overviewGrid'),
  reviewPurpose: document.getElementById('reviewPurpose'),
  reviewChecks: document.getElementById('reviewChecks'),
  stateControls: document.getElementById('stateControls'),
  interactionList: document.getElementById('interactionList'),
  interactionCount: document.getElementById('interactionCount'),
  noteScreenName: document.getElementById('noteScreenName'),
  reviewNote: document.getElementById('reviewNote'),
  savedNotes: document.getElementById('savedNotes'),
  toast: document.getElementById('toast')
};
els.canvasSize = document.getElementById('canvasSize');

function icon(name) {
  return '<svg aria-hidden="true"><use href="#i-' + name + '"></use></svg>';
}

function getScreen(id) {
  return screenDefinitions.find(function (screen) {
    return screen.id === id;
  });
}

function screenHeader(kicker, title, actionIcon, action, brandTitle, actionLabel) {
  return [
    '<header class="mobile-header">',
      '<div class="mobile-header-copy">',
        '<p class="kicker">', kicker, '</p>',
        '<h1 class="', brandTitle ? 'brand-title' : '', '">', title, '</h1>',
      '</div>',
      actionIcon ? '<button class="icon-button" type="button" data-action="' + (action || 'noop') + '" aria-label="' + actionLabel + '">' + icon(actionIcon) + '</button>' : '',
    '</header>'
  ].join('');
}

function bottomNav(active) {
  const items = [
    ['agent', 'agent', 'Agent'],
    ['collection', 'bookmark', '收藏'],
    ['plan', 'calendar', '计划'],
    ['me', 'user', '我的']
  ];
  return [
    '<nav class="mobile-bottom-nav" aria-label="一级导航">',
      items.map(function (item) {
        const id = item[0];
        return '<button type="button" class="nav-item ' + (id === active ? 'is-active' : '') + '" data-action="go-screen" data-screen="' + id + '" ' + (id === active ? 'aria-current="page"' : '') + '>' + icon(item[1]) + '<span>' + item[2] + '</span></button>';
      }).join(''),
    '</nav>'
  ].join('');
}

function mobileShell(header, body, activeNav, share, dock) {
  return [
    '<div class="mobile-app ', share ? 'share-app ' : '', dock ? 'has-screen-dock' : '', '">',
      header,
      '<main class="screen-scroll ', activeNav ? '' : 'no-nav', '">', body, '</main>',
      dock || '',
      activeNav ? bottomNav(activeNav) : '',
    '</div>'
  ].join('');
}

function sectionLabel(title, actionText) {
  return '<div class="section-label"><h2>' + title + '</h2>' + (actionText ? '<button type="button" data-action="noop">' + actionText + '</button>' : '') + '</div>';
}

function chips(items) {
  return '<div class="chips">' + items.map(function (item) {
    return '<span class="chip ' + (item[1] || '') + '">' + item[0] + '</span>';
  }).join('') + '</div>';
}

function statusCard(type, iconName, title, copy, actionLabel, action) {
  return [
    '<div class="status-card ', type || '', '">',
      '<div class="status-illustration">', icon(iconName), '</div>',
      '<h3>', title, '</h3>',
      '<p>', copy, '</p>',
      actionLabel ? '<button type="button" class="primary-action" data-action="' + action + '" style="margin-top:14px">' + actionLabel + '</button>' : '',
    '</div>'
  ].join('');
}

function renderAgent(state) {
  const header = screenHeader('SHENZHEN · MON 20 JUL', '晚上好，张子豪', 'settings', 'go-me', false, '打开设置');
  const listeningBanner = state === 'listening'
    ? '<div class="state-inline-banner">' + icon('spark') + '<span>已记住本次条件：周六下午、福田优先、轻松一点。继续添加地点不会覆盖这些要求。</span></div>'
    : '';

  const collectionSummary = state === 'empty'
    ? [
        sectionLabel('计划准备度', ''),
        '<section class="soft-card readiness-card readiness-empty">',
          '<div>',
            '<div class="readiness-value"><strong>0</strong><span>个有效收藏</span></div>',
            '<p>添加想去的地方后，这里会显示是否足以生成计划。</p>',
          '</div>',
          '<div class="progress-ring is-empty"><span>暂无</span></div>',
        '</section>',
        sectionLabel('最近收藏', ''),
        '<section class="soft-card recent-empty-card">',
          '<div class="recent-empty-icon">', icon('bookmark'), '</div>',
          '<div><h3>暂无收藏</h3><p>发送店名、链接或截图，我会先帮你识别地点。</p></div>',
          '<button class="inline-add-action" type="button" data-action="focus-agent">添加</button>',
        '</section>'
      ].join('')
    : [
        sectionLabel('计划准备度', '查看收藏'),
        '<section class="soft-card readiness-card">',
          '<div>',
            '<div class="readiness-value"><strong>12</strong><span>个有效收藏</span></div>',
            '<p>足以生成 1 个轻松的半日计划</p>',
          '</div>',
          '<div class="progress-ring"><span>READY</span></div>',
        '</section>',
        sectionLabel('最近收藏', '全部 12 个'),
        '<section class="soft-card">',
          '<div class="mini-place-row">',
            '<div class="place-thumb"></div>',
            '<div><h4>深圳当代艺术与城市规划馆</h4><p>福田 · 免费 · 室内</p></div>',
            '<button class="row-arrow" type="button" data-action="go-detail" aria-label="查看详情">', icon('chevron'), '</button>',
          '</div>',
          '<div class="mini-place-row">',
            '<div class="place-thumb city"></div>',
            '<div><h4>南头古城</h4><p>南山 · 约 ¥80 · 室外</p></div>',
            '<button class="row-arrow" type="button" data-action="go-detail" aria-label="查看详情">', icon('chevron'), '</button>',
          '</div>',
        '</section>'
      ].join('');

  const body = [
    listeningBanner,
    '<section class="hero-composer">',
      '<div class="hero-kicker">', icon('spark'), ' PERSONAL CITY AGENT</div>',
      '<h2>把想去的地方发给我，或者告诉我你什么时候有空</h2>',
      '<div class="hero-input">',
        '<input id="agentPrompt" name="agent_prompt" autocomplete="off" aria-label="告诉拾光你的想法" value="', state === 'listening' ? '周六下午 5 小时，福田优先' : '', '" placeholder="店名、链接、截图或一句要求" />',
        '<button class="send-button" type="button" data-action="submit-import" aria-label="发送">', icon('send'), '</button>',
      '</div>',
      '<div class="attachment-actions">',
        '<button type="button" data-action="toast" data-message="图片上传将在正式开发时接入">', icon('image'), '发截图</button>',
        '<button type="button" data-action="toast" data-message="粘贴链接后会创建识别任务">', icon('link'), '贴链接</button>',
      '</div>',
    '</section>',
    sectionLabel('快速开始', ''),
    '<div class="task-entry-grid">',
      '<button class="task-entry" type="button" data-action="focus-agent">', icon('bookmark'), '<span><strong>收藏一个地点</strong><small>发送店名、链接或截图</small></span>', icon('chevron'), '</button>',
      '<button class="task-entry" type="button" data-action="go-plan-permission">', icon('calendar'), '<span><strong>帮我安排时间</strong><small>优先使用已有收藏</small></span>', icon('chevron'), '</button>',
    '</div>',
    '<div class="chips">',
      '<button class="chip" type="button" data-action="set-prompt" data-value="周六下午 5 小时，福田优先">周六下午有空</button>',
      '<button class="chip" type="button" data-action="set-prompt" data-value="找个适合下雨天的室内活动">下雨天室内</button>',
      '<button class="chip" type="button" data-action="set-prompt" data-value="只用我的收藏，轻松一点">只用我的收藏</button>',
    '</div>',
    collectionSummary
  ].join('');
  return mobileShell(header, '<div class="agent-page-stack">' + body + '</div>', 'agent');
}

function renderImport(state) {
  const headerTitles = {
    saved: '已完成收藏',
    recognizing: '正在识别收藏',
    ambiguous: '请选择准确地点',
    needs_input: '还需要一点信息',
    undone: '已撤销收藏',
    failed: '未能识别'
  };
  const header = screenHeader('AGENT CONVERSATION', headerTitles[state] || '收藏结果', 'bookmark', 'go-collection', false, '打开收藏库');
  const userMessage = '<div class="message user">帮我收藏深圳当代艺术与城市规划馆</div>';
  let agentContent = '';

  if (state === 'recognizing') {
    agentContent = [
      '<div class="agent-line">',
        '<div class="agent-avatar">', icon('spark'), '</div>',
        '<div class="agent-bubble">',
          '<p>我会先读取来源，再识别地点，最后判断是否需要你确认。</p>',
          '<div class="import-progress">',
            '<div class="stage-progress-list">',
              '<div class="is-done"><span>', icon('check'), '</span><div><strong>内容已收到</strong><small>图片安全检查完成</small></div></div>',
              '<div class="is-current"><span>2</span><div><strong>正在识别地点</strong><small>核对名称、城市与来源线索</small></div></div>',
              '<div><span>3</span><div><strong>整理收藏结果</strong><small>确认后才会进入收藏库</small></div></div>',
            '</div>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');
  } else if (state === 'needs_input') {
    agentContent = [
      '<div class="agent-line">',
        '<div class="agent-avatar">', icon('spark'), '</div>',
        '<div class="agent-bubble">',
          '<p>我已经保留来源和店名，但信息还不足以确定具体位置。这不是识别失败。</p>',
          statusCard('warning', 'map-pin', '收藏已保留，等待补充', '补充行政区、商圈、附近地标或地图链接中的任意一项即可继续。', '补充地点信息', 'go-detail-missing'),
          '<button class="text-link-action" type="button" data-action="toast" data-message="已暂时保留，之后可以从收藏库继续补充">暂时保留</button>',
        '</div>',
      '</div>'
    ].join('');
  } else if (state === 'undone') {
    agentContent = [
      '<div class="agent-line">',
        '<div class="agent-avatar">', icon('undo'), '</div>',
        '<div class="agent-bubble">',
          '<p>刚才的收藏已经撤销，原始对话仍然保留。</p>',
          '<div class="undo-card"><div><strong>深圳当代艺术与城市规划馆</strong><small>撤销后尚未从本次对话移除</small></div><button type="button" data-action="restore-import">恢复收藏</button></div>',
        '</div>',
      '</div>'
    ].join('');
  } else if (state === 'failed') {
    agentContent = [
      '<div class="agent-line">',
        '<div class="agent-avatar">', icon('spark'), '</div>',
        '<div class="agent-bubble">',
          '<p>这个页面暂时无法读取，因此没有创建或保留收藏。</p>',
          statusCard('error', 'link', '来源读取失败', '换成包含店名和区域的截图、直接输入地点名称，或稍后重试这个链接。', '换成截图', 'toast'),
          '<button class="secondary-action full-action" type="button" data-action="submit-import">重新尝试</button>',
        '</div>',
      '</div>'
    ].join('');
  } else if (state === 'ambiguous') {
    agentContent = [
      '<div class="agent-line">',
        '<div class="agent-avatar">', icon('spark'), '</div>',
        '<div class="agent-bubble">',
          '<p>我记录了店名，但找到了多个合理地点。确认前不会让它进入正式计划。</p>',
          '<div class="state-inline-banner warning">', icon('map-pin'), '<span>已记录，待选择位置 · 共 3 个候选</span></div>',
          '<button class="primary-action" type="button" data-action="go-detail">选择准确地点</button>',
        '</div>',
      '</div>'
    ].join('');
  } else {
    agentContent = [
      '<div class="agent-line">',
        '<div class="agent-avatar">', icon('spark'), '</div>',
        '<div class="agent-bubble">',
          '<p>已找到唯一高置信地点，并完成收藏。周一闭馆信息会在规划前再次核验。</p>',
          '<article class="result-place-card">',
            '<div class="place-visual"><span class="source-badge">来源 · 用户截图</span><div class="building"></div></div>',
            '<div class="result-place-body">',
              '<h3>深圳当代艺术与城市规划馆</h3>',
              '<p>福田区福中路184号 · 深圳市民中心A区</p>',
              chips([['福田区', 'accent'], ['免费', ''], ['室内', ''], ['周一闭馆', 'warning']]),
              '<div class="field-source">', icon('check'), ' POI 已由高德核对 · 刚刚</div>',
              '<div class="action-row">',
                '<button class="secondary-action" type="button" data-action="go-detail">', icon('edit'), '修改</button>',
                '<button class="ghost-action" type="button" data-action="undo-import">', icon('undo'), '撤销</button>',
              '</div>',
            '</div>',
          '</article>',
          '<button class="primary-action lime" style="width:100%;margin-top:10px" type="button" data-action="go-plan">用它生成计划 ', icon('chevron'), '</button>',
        '</div>',
      '</div>'
    ].join('');
  }

  const body = [
    '<div class="message-list">',
      userMessage,
      agentContent,
    '</div>'
  ].join('');
  const dock = '<div class="message-composer screen-dock"><input name="message" autocomplete="off" aria-label="继续对话" placeholder="继续添加，或直接说出修改内容" /><button class="send-button" type="button" data-action="toast" data-message="已记录你的补充要求" aria-label="发送补充内容">' + icon('send') + '</button></div>';
  return mobileShell(header, body, 'agent', false, dock);
}

function renderCollection(state) {
  const header = screenHeader('YOUR CITY MEMORY', '收藏', 'plus', 'toast', false, '添加收藏');
  if (state === 'empty') {
    return mobileShell(header, '<div class="empty-state"><div><div class="empty-icon">' + icon('bookmark') + '</div><h3>收藏库还是空的</h3><p>从 Agent 页面发送一个店名、链接或截图，确认后会出现在这里。</p><button class="primary-action" type="button" data-action="go-agent">去添加第一个地点</button></div></div>', 'collection');
  }

  const pendingBanner = state === 'pending'
    ? '<div class="state-inline-banner warning">' + icon('map-pin') + '<span>有 2 条收藏需要处理：1 条待选择、1 条待补充。它们仍会保留，但不会进入深圳计划。</span></div>'
    : '';
  const body = [
    '<div class="collection-overview"><div><strong>15</strong><span>个收藏</span></div><small>最近添加优先</small></div>',
    '<button class="planning-scope-compact" type="button" data-action="toast" data-message="已展开每条收藏的参与状态和原因"><span class="scope-icon">', icon('check'), '</span><span class="scope-copy"><strong>本次深圳计划</strong><small>9 条可参与 · 3 条暂不参与</small></span><span class="scope-link">查看原因 ', icon('chevron'), '</span></button>',
    pendingBanner,
    '<div class="filter-tabs">',
      '<button class="filter-tab is-active" type="button">全部 15</button>',
      '<button class="filter-tab" type="button">想去 9</button>',
      '<button class="filter-tab" type="button">去过 1</button>',
    '</div>',
    '<div class="collection-tools">',
      '<div class="search-field">', icon('search'), '<input name="collection_search" autocomplete="off" aria-label="搜索收藏" placeholder="搜索收藏" /></div>',
      '<details class="collection-filter-panel">',
        '<summary>筛选 <b>2</b></summary>',
        '<div class="collection-filter-sheet">',
          '<div class="filter-sheet-head"><strong>筛选收藏</strong><button type="button" data-action="toast" data-message="已清除全部筛选">清除</button></div>',
          '<div class="filter-group"><span>城市</span><div class="filter-options"><button class="is-active" type="button">深圳 12</button><button type="button">广州 2</button><button type="button">待确认 1</button></div></div>',
          '<div class="filter-group"><span>计划使用</span><div class="filter-options"><button class="is-active" type="button">可参与本次计划</button><button type="button">已计划 2</button><button type="button">暂不参与 3</button></div></div>',
          '<div class="filter-group"><span>场景与区域</span><div class="filter-options"><button type="button">展览</button><button type="button">室内</button><button type="button">福田</button></div></div>',
          '<button class="primary-action full-action" type="button" data-action="toast" data-message="已应用筛选，共 9 条结果">查看 9 条结果</button>',
        '</div>',
      '</details>',
    '</div>',
    sectionLabel('最近添加', '4 条结果'),
    '<div class="collection-list">',
      placeCard('深圳当代艺术与城市规划馆', '福田 · 免费', ['展览', '室内'], 'eligible', 'default', '可参与当前计划'),
      placeCard('南头古城', '南山 · 约 ¥80', ['散步', '朋友'], 'eligible', 'city', '可参与当前计划'),
      placeCard('一尺花园', '南山 · 价格待确认', ['咖啡', '室内'], state === 'pending' ? 'pending' : 'eligible', 'default', state === 'pending' ? '待选择具体分店，暂不参与计划' : '可参与当前计划'),
      placeCard('广东美术馆新馆', '广州 · 免费', ['展览', '室内'], 'excluded', 'city', '收藏属于广州，当前深圳计划不会使用'),
    '</div>',
    '<button class="primary-action" style="width:100%;margin-top:14px" type="button" data-action="go-plan">用当前筛选生成计划</button>'
  ].join('');
  return mobileShell(header, '<div class="collection-page-stack">' + body + '</div>', 'collection');
}

function placeCard(title, meta, tags, status, thumbType, reason) {
  const statusLabel = {
    eligible: '可参与计划',
    pending: '待选择',
    excluded: '暂不参与'
  }[status];
  return [
    '<article class="place-card" role="button" tabindex="0" data-action="go-detail">',
      '<div class="place-thumb ', thumbType === 'city' ? 'city' : '', '"></div>',
      '<div class="place-card-copy">',
        '<h3>', title, '</h3>',
        '<p>', meta, '</p>',
        '<div class="place-meta-row">',
          tags.map(function (tag) { return '<span class="tiny-tag">' + tag + '</span>'; }).join(''),
          '<span class="tiny-tag ', status === 'pending' ? 'needs-action' : '', '">', statusLabel, '</span>',
        '</div>',
        '<div class="participation-reason ', status, '">', reason, '</div>',
      '</div>',
    '</article>'
  ].join('');
}

function renderDetail(state) {
  const header = screenHeader('COLLECTION DETAIL', state === 'missing' ? '补充地点信息' : '确认准确地点', 'bookmark', 'back-context', false, '返回原对话');
  if (state === 'missing') {
    const bodyMissing = [
      '<div class="context-return-note">来自 Agent 对话 · 保存后返回刚才的位置</div>',
      '<div class="detail-visual"><div class="detail-visual-copy"><span>原始识别结果已保留</span><h2>一尺花园</h2></div></div>',
      statusCard('warning', 'map-pin', '收藏处于“待补充”', '请补充行政区、商圈、附近地标，或粘贴地图分享链接。暂时不补也不会丢失。', '', ''),
      sectionLabel('最少补充一项', ''),
      '<div class="editable-fields">',
        '<button class="editable-field" type="button" data-action="toast" data-message="已选择南山区"><span>行政区</span><strong>请选择</strong></button>',
        '<button class="editable-field" type="button" data-action="toast" data-message="可输入商圈或附近地标"><span>商圈或地标</span><strong>例如：海上世界</strong></button>',
        '<button class="editable-field" type="button" data-action="toast" data-message="可粘贴高德或微信地图链接"><span>地图链接</span><strong>粘贴链接</strong></button>',
      '</div>',
      '<button class="primary-action full-action" type="button" data-action="choose-candidate">重新查找候选</button>',
      '<button class="text-link-action" type="button" data-action="back-context">暂时保留，返回对话</button>'
    ].join('');
    return mobileShell(header, bodyMissing, 'collection');
  }

  const selected = state === 'selected';
  const anyBranch = state === 'any_branch';
  const body = [
    '<div class="context-return-note">来自 Agent 对话 · 保存后返回刚才的位置</div>',
    '<div class="detail-visual"><div class="detail-visual-copy"><span>原始内容识别 · 连锁品牌</span><h2>一尺花园</h2></div></div>',
    '<div class="state-inline-banner ', selected || anyBranch ? '' : 'warning', '">',
      icon(selected || anyBranch ? 'check' : 'map-pin'),
      '<span>', selected ? '已选择海上世界店，可以继续修改识别字段。' : anyBranch ? '已记录“任意分店都可以”。规划时会在活动范围内选择具体分店。' : '存在多个合理分店。排名第一不等于位置已经确认。', '</span>',
    '</div>',
    sectionLabel('请选择准确地点', ''),
    '<div class="candidate-list">',
      '<article class="candidate-card ', selected ? 'is-selected' : '', '" data-action="choose-candidate" role="button" tabindex="0">',
        '<span class="radio-mark"></span>',
        '<div><h3>一尺花园 · 海上世界店</h3><p>南山区太子路 · 与来源中的海边地标一致 · 1.2 km</p></div>',
      '</article>',
      '<article class="candidate-card" data-action="choose-candidate" role="button" tabindex="0">',
        '<span class="radio-mark"></span>',
        '<div><h3>一尺花园 · 万象天地店</h3><p>南山区深南大道 · 名称一致，但来源没有商圈线索</p></div>',
      '</article>',
      '<article class="candidate-card choice-card ', anyBranch ? 'is-selected' : '', '" data-action="choose-any" role="button" tabindex="0">',
        '<span class="radio-mark"></span><div><h3>任意分店都可以</h3><p>保存为品牌级收藏，生成计划时再按范围解析具体分店</p></div>',
      '</article>',
      '<article class="candidate-card choice-card" data-action="choose-none" role="button" tabindex="0">',
        '<span class="radio-mark"></span><div><h3>以上都不是</h3><p>保留原始内容，并转为待补充状态</p></div>',
      '</article>',
    '</div>',
    sectionLabel('识别字段', '编辑'),
    '<div class="editable-fields">',
      '<button class="editable-field" type="button" data-action="toast" data-message="字段编辑会保留来源记录"><span>区域</span><strong>', anyBranch ? '规划时确定' : '南山区', '</strong></button>',
      '<button class="editable-field" type="button" data-action="toast" data-message="已打开价格编辑"><span>价格</span><strong>约 ¥60–100</strong></button>',
      '<button class="editable-field" type="button" data-action="toast" data-message="已打开场景标签编辑"><span>适用场景</span><strong>室内 · 独处 · 朋友</strong></button>',
    '</div>',
    '<div class="action-row">',
      '<button class="danger-action" type="button" data-action="delete-place">删除收藏</button>',
      '<button class="primary-action" type="button" data-action="save-place" ', selected || anyBranch ? '' : 'disabled', '>保存并返回对话</button>',
    '</div>',
    '<button class="text-link-action" type="button" data-action="back-context">取消修改，返回对话</button>'
  ].join('');
  return mobileShell(header, body, 'collection');
}

function renderPlan(state) {
  const header = screenHeader('PLAN DRAFT · V1', '周六半日计划', 'edit', 'toast', false, '编辑计划条件');
  if (state === 'generating') {
    const generating = [
      '<div class="plan-hero"><div class="plan-hero-top"><div><span class="eyebrow">正在生成</span><h2>把收藏排成一条轻松路线</h2><p>正在核对路线、营业时间和价格信息</p></div><div class="plan-score">···</div></div></div>',
      sectionLabel('正在组合计划', ''),
      '<div class="soft-card"><div class="skeleton line"></div><div class="skeleton line"></div><div class="skeleton line short"></div></div>',
      '<div class="import-progress" style="margin-top:10px"><div class="progress-header"><span>已完成收藏筛选，正在计算路线</span><span>2 / 3</span></div><div class="progress-track"><i></i></div></div>'
    ].join('');
    return mobileShell(header, generating, 'plan');
  }
  if (state === 'permission') {
    const permission = [
      '<div class="plan-hero"><div class="plan-hero-top"><div><span class="eyebrow">需要你的决定</span><h2>收藏不足以组成这次计划</h2><p>当前条件：周六下午 · 福田 · 5 小时</p></div><div class="plan-score">1/3</div></div></div>',
      sectionLabel('允许外部地点补充吗？', ''),
      '<div class="permission-card">',
        '<h3>可以使用高德补充固定地点</h3>',
        '<p>拾光会根据你的偏好搜索少量 Place，并明确标注来源。不会搜索外部展览或活动，也不会自动加入收藏。</p>',
        '<div class="permission-actions"><button class="primary-action" type="button" data-action="allow-external">允许补充地点</button><button class="secondary-action" type="button" data-action="deny-external">仅用现有收藏生成</button><button class="text-link-action" type="button" data-action="go-collection">继续添加收藏</button></div>',
      '</div>'
    ].join('');
    return mobileShell(header, permission, 'plan');
  }
  if (state === 'collection_only') {
    const collectionOnly = [
      '<div class="state-inline-banner">', icon('check'), '<span>已按你的选择关闭外部地点补充。现有收藏仍然有效，没有发生错误。</span></div>',
      '<section class="plan-hero">',
        '<div class="plan-hero-top"><div><span class="eyebrow">COLLECTION ONLY</span><h2>只安排一个核心展览，也可以成行</h2><p>周六 14:00–17:00 · 福田区</p></div><div class="plan-score"><strong>84</strong><small>匹配度</small></div></div>',
        '<div class="plan-conditions"><span>3 小时</span><span>只用收藏</span><span>预算未设置</span></div>',
      '</section>',
      '<div class="time-ribbon">', timelineItem('14:00', '深圳当代艺术与城市规划馆', '约 2 小时 · 免费', '你的收藏', false, '起点'), '</div>',
      '<div class="risk-card"><strong>方案较短</strong><p>只有 1 个满足条件的收藏，因此没有安排中途休息。你可以确认这个轻量方案，或继续添加收藏。</p></div>',
      '<div class="action-row"><button class="secondary-action" type="button" data-action="go-collection">继续添加收藏</button><button class="primary-action" type="button" data-action="confirm-plan">确认轻量方案</button></div>'
    ].join('');
    return mobileShell(header, collectionOnly, 'plan');
  }
  if (state === 'failed') {
    const failed = [
      statusCard('error', 'route', '路线工具暂时不可用', '收藏筛选已经完成，但无法确认地点之间的预计路程。你可以稍后重试，或先查看未排序的候选。', '重新生成', 'retry-plan'),
      '<button class="secondary-action" style="width:100%;margin-top:10px" type="button" data-action="go-collection">返回收藏库</button>'
    ].join('');
    return mobileShell(header, failed, 'plan');
  }

  const alternatives = state === 'alternatives'
    ? [
        '<div class="alternative-list">',
          '<button class="alternative-card is-active" type="button" data-action="toast" data-message="当前正在查看主方案"><span>主方案</span><strong>展览 + 咖啡 + 可选散步</strong><small>步行较少 · ¥60–100</small></button>',
          '<button class="alternative-card" type="button" data-action="toast" data-message="已切换为雨天备选，尚未确认"><span>备选 A</span><strong>展览 + 书店</strong><small>全程室内 · ¥30–70</small></button>',
          '<button class="alternative-card" type="button" data-action="toast" data-message="已切换为零预算备选，尚未确认"><span>备选 B</span><strong>展览 + 市民中心</strong><small>全部免费 · 户外风险较高</small></button>',
        '</div>'
      ].join('')
    : '';
  const body = [
    '<section class="plan-hero">',
      '<div class="plan-hero-top">',
        '<div><span class="eyebrow">MAIN PLAN</span><h2>一个展览，一次停留，再留点余地</h2><p>周六 14:00–19:00 · 福田区</p></div>',
        '<button class="plan-score" type="button" data-action="toast" data-message="匹配度综合收藏命中、路程、时间余量与风险，不代表地点评分"><strong>92</strong><small>匹配度</small></button>',
      '</div>',
      '<div class="plan-conditions"><span>5 小时</span><span>轻松一点</span><span>预算未设置</span><span>公共交通</span></div>',
    '</section>',
    '<button class="alternatives-trigger" type="button" data-action="show-alternatives"><span><strong>2 个备选方案</strong><small>雨天室内 · 零预算</small></span><span class="alternatives-open">查看 ', icon('chevron'), '</span></button>',
    alternatives,
    '<div class="timeline-heading"><div><span class="eyebrow">SAT · 14:00—19:00</span><h2>时间光轨</h2></div><div><strong>3 站</strong><small>步行约 2.1 km</small></div></div>',
    '<div class="time-ribbon">',
      timelineItem('14:00', '深圳当代艺术与城市规划馆', '约 2 小时 · 免费 · 周一闭馆', '你的收藏', false, '起点'),
      timelineItem('16:30', 'One Avenue 咖啡休息', '约 1 小时 · ¥60–100 · 未收藏', '高德补充', true, '步行 12 分钟'),
      timelineItem('18:00', '市民中心夜景散步', '可选延伸 · 约 45 分钟 · 下雨可跳过', '你的收藏', false, '步行 8 分钟'),
    '</div>',
    '<div class="budget-bar">',
      '<div class="budget-stat"><small>预计花费</small><strong>¥60–100</strong></div>',
      '<div class="budget-stat"><small>步行</small><strong>约 2.1 km</strong></div>',
      '<div class="budget-stat"><small>结束留白</small><strong>25 min</strong></div>',
    '</div>',
    '<div class="risk-card"><strong>出发前需要确认</strong><p>咖啡店价格与营业时间来自外部信息，可能变化；18:00 的散步受阵雨影响，是可跳过的延伸，不影响主计划。</p><small>事实最后核验：刚刚</small></div>',
    '<div class="explain-card"><strong>为什么这样安排</strong><p>核心展览来自你的收藏；咖啡店只为补足中途休息，并已标记为高德补充且未加入收藏。预算未设置，因此仅展示估算。</p></div>',
    sectionLabel('继续调整', ''),
    '<div class="adjust-composer"><input name="plan_adjustment" autocomplete="off" aria-label="调整计划" placeholder="例如：少走一点，不要咖啡店" /><button class="send-button" type="button" data-action="toast" data-message="已保留其他条件并重新计算" aria-label="发送计划调整">', icon('send'), '</button></div>',
    '<div class="plan-sticky-cta"><div><strong>确认当前方案</strong><small>不会自动设置提醒，也不会把外部地点加入收藏</small></div><button class="primary-action" type="button" data-action="confirm-plan">确认方案</button></div>'
  ].join('');
  return mobileShell(header, body, 'plan');
}

function timelineItem(time, title, meta, source, external, travel) {
  return [
    '<article class="timeline-item ', external ? 'external' : '', '">',
      '<div class="timeline-time">', time, '</div>',
      '<div class="timeline-node"></div>',
      '<div class="timeline-content">',
        '<header><h3>', title, '</h3><span class="source-label ', external ? 'external' : '', '">', source, '</span></header>',
        '<p>', meta, '</p>',
        '<div class="travel-row">', icon('route'), travel, '</div>',
        external ? '<div class="external-actions"><button type="button" data-action="toast" data-message="补充原因：现有收藏缺少合适的中途休息地点">推荐原因</button><button type="button" data-action="toast" data-message="已打开外部地点替换列表">替换</button><button type="button" data-action="toast" data-message="已从当前草案删除，不影响收藏">删除</button><button type="button" data-action="toast" data-message="已加入收藏，可随时撤销">加入收藏</button></div>' : '',
      '</div>',
    '</article>'
  ].join('');
}

function renderConfirmed(state) {
  const header = screenHeader('CONFIRMED · SAT 14:00', '周六计划', 'share', 'show-share-preview', false, '分享计划');
  let statePanel = '';
  if (state === 'reminder') {
    statePanel = [
      '<div class="permission-card">',
        '<span class="eyebrow">单独授权</span><h3>要设置行前提醒吗？</h3>',
        '<p>只为这份计划设置一次提醒。确认计划本身不会自动开启提醒。</p>',
        '<label class="select-field"><span>提醒时间</span><select name="reminder_time" aria-label="提醒时间"><option>出发前 60 分钟</option><option>出发前 30 分钟</option><option>当天上午 10:00</option></select></label>',
        '<div class="action-row"><button class="secondary-action" type="button" data-action="skip-reminder">暂不设置</button><button class="primary-action" type="button" data-action="enable-reminder">设置提醒</button></div>',
      '</div>'
    ].join('');
  } else if (state === 'share_preview') {
    statePanel = [
      '<div class="share-preview-card">',
        '<span class="eyebrow">分享前预览</span><h3>确认将公开这些内容</h3>',
        '<div class="share-columns"><div><strong>将会分享</strong><p>日期、时间线、公开地点、费用估算、路线入口、风险与更新时间</p></div><div><strong>不会分享</strong><p>姓名、收藏来源备注、完整对话、长期记忆、精确住址</p></div></div>',
        '<div class="share-expiry-row"><span>失效时间</span><strong>计划结束 7 天后</strong></div>',
        '<div class="action-row"><button class="secondary-action" type="button" data-action="close-state-panel">返回</button><button class="primary-action" type="button" data-action="create-share">确认并创建链接</button></div>',
      '</div>'
    ].join('');
  } else if (state === 'share_active') {
    statePanel = [
      '<div class="share-management-card">',
        '<div><span class="live-share-dot"></span><strong>分享链接有效</strong><small>最后更新：今天 15:30 · 7 月 26 日 19:00 失效</small></div>',
        '<button type="button" data-action="open-share">查看分享页</button>',
        '<button type="button" data-action="copy-link">复制链接</button>',
        '<button class="danger-text" type="button" data-action="revoke-share">关闭分享</button>',
      '</div>'
    ].join('');
  } else if (state === 'versions') {
    statePanel = [
      '<div class="version-card"><div><span>当前执行版本</span><strong>V2 · 今天 15:30 确认</strong><small>调整了咖啡休息时间；分享页已同步</small></div><button type="button" data-action="toast" data-message="已打开 V1 与 V2 的差异">历史版本</button></div>',
      '<div class="action-row"><button class="secondary-action" type="button" data-action="go-plan">修改计划</button><button class="danger-action" type="button" data-action="cancel-plan">取消计划</button></div>'
    ].join('');
  } else if (state === 'feedback') {
    statePanel = [
      '<div class="feedback-card"><h3>这次计划完成得怎么样？</h3><p>请选择最符合实际情况的一项，之后仍可修改。</p>',
        '<div class="feedback-options">',
          '<button data-action="feedback-complete"><strong>已完成</strong><small>按计划到访主要地点</small></button>',
          '<button data-action="feedback-partial"><strong>部分完成</strong><small>继续选择实际到访地点</small></button>',
          '<button data-action="feedback-incomplete"><strong>未完成</strong><small>收藏保持原状态</small></button>',
        '</div>',
      '</div>'
    ].join('');
  } else if (state === 'partial') {
    statePanel = [
      '<div class="feedback-card"><h3>你实际去了哪些地方？</h3><p>只有选中的收藏会标记为去过；外部地点只更新本次计划记录。</p>',
        '<label class="visit-choice"><input type="checkbox" name="visited_places" value="深圳当代艺术与城市规划馆" checked />深圳当代艺术与城市规划馆 <span>你的收藏</span></label>',
        '<label class="visit-choice"><input type="checkbox" name="visited_places" value="One Avenue 咖啡休息" />One Avenue 咖啡休息 <span>外部未收藏</span></label>',
        '<label class="visit-choice"><input type="checkbox" name="visited_places" value="市民中心夜景散步" checked />市民中心夜景散步 <span>你的收藏</span></label>',
        '<button class="primary-action full-action" type="button" data-action="save-partial">保存部分完成</button>',
      '</div>'
    ].join('');
  } else if (state === 'incomplete') {
    statePanel = [
      '<div class="state-inline-banner warning">', icon('calendar'), '<span>计划已标记为未完成。收藏保持“想去”，提醒已停止，之后仍可重新安排。</span></div>',
      '<div class="action-row"><button class="secondary-action" type="button" data-action="go-plan">调整后重排</button><button class="primary-action" type="button" data-action="go-collection">继续看收藏</button></div>'
    ].join('');
  }
  const body = [
    statePanel,
    '<div class="confirmed-banner"><div class="confirmed-icon">', icon('check'), '</div><div><h3>计划已确认 · 当前 V2</h3><p>', reminderEnabled ? '提醒已设置：出发前 60 分钟' : '提醒尚未设置，可按需开启', '</p></div></div>',
    '<div class="weather-strip"><div><strong>周六 · 多云转阵雨</strong><br><span>26–31°C · 建议带伞</span></div><span>刚刚核验</span></div>',
    sectionLabel('今天的时间光轨', '查看详情'),
    '<div class="time-ribbon">',
      timelineItem('14:00', '当代艺术与城市规划馆', '开放中 · 免费', '已核验', false, '打开路线'),
      timelineItem('16:30', 'One Avenue 咖啡休息', '价格待现场确认', '外部', true, '步行 12 分钟'),
      timelineItem('18:00', '市民中心夜景散步', '雨天可跳过', '收藏', false, '步行 8 分钟'),
    '</div>',
    sectionLabel('行动入口', ''),
    '<div class="execution-actions">',
      executionCard('route', '打开高德路线', 'open-route'),
      executionCard('calendar', '下载日历', 'toast'),
      executionCard('bell', reminderEnabled ? '提醒已设置' : '设置提醒', 'show-reminder'),
      executionCard('share', shareActive ? '管理分享' : '分享计划', shareActive ? 'show-share-management' : 'show-share-preview'),
    '</div>',
    '<div class="management-links"><button type="button" data-action="show-versions">修改与历史版本</button><button type="button" data-action="show-feedback">完成后反馈</button></div>'
  ].join('');
  return mobileShell(header, body, 'plan');
}

function executionCard(iconName, label, action) {
  return '<button class="execution-card" type="button" data-action="' + action + '">' + icon(iconName) + '<strong>' + label + '</strong></button>';
}

function renderMe(state) {
  const header = screenHeader('ACCOUNT & MEMORY', '我的', 'settings', 'toast', false, '打开账户设置');
  const suggestion = state === 'suggestion'
    ? '<div class="permission-card"><h3>要记住“你更喜欢室内展览”吗？</h3><p>这是根据最近 3 次反馈推断的长期偏好。确认前不会写入记忆。</p><div class="action-row"><button class="secondary-action" data-action="toast" data-message="已忽略这条建议">不记住</button><button class="primary-action" data-action="toast" data-message="已保存偏好，可随时删除">确认记住</button></div></div>'
    : '';
  const privacy = state === 'privacy'
    ? '<div class="state-inline-banner">' + icon('settings') + '<span>你可以导出或删除收藏、计划和记忆。删除操作会再次确认，不影响本机评审笔记。</span></div>'
    : '';
  const memoryDetail = state === 'memory'
    ? [
        '<div class="memory-detail-card">',
          '<div class="memory-detail-head"><span>', icon('spark'), '</span><div><strong>更喜欢室内展览</strong><small>已用于推荐</small></div></div>',
          '<dl><div><dt>来源</dt><dd>你在 3 次计划反馈中确认</dd></div><div><dt>创建时间</dt><dd>2026-06-18</dd></div><div><dt>最近使用</dt><dd>今天的福田半日计划</dd></div><div><dt>影响过的计划</dt><dd>4 份 · 查看记录</dd></div></dl>',
          '<div class="memory-actions"><button type="button" data-action="toast" data-message="已打开记忆编辑">修改</button><button type="button" data-action="toast" data-message="已停止将这条记忆用于推荐">停止用于推荐</button><button class="danger-text" type="button" data-action="toast" data-message="删除前会再次确认">删除</button></div>',
        '</div>'
      ].join('')
    : '';
  const body = [
    suggestion,
    privacy,
    memoryDetail,
    '<section class="profile-card">',
      '<h2>拾光正在逐步了解你</h2>',
      '<p>所有长期记忆都可以查看、修改或删除</p>',
      '<div class="profile-stats"><div><strong>12</strong><span>收藏</span></div><div><strong>08</strong><span>完成计划</span></div><div><strong>04</strong><span>已确认偏好</span></div></div>',
    '</section>',
    sectionLabel('偏好记忆', '查看全部 4 条'),
    '<button class="memory-summary" type="button" data-action="show-memory"><span>', icon('spark'), '</span><div><strong>更喜欢室内展览</strong><small>来自 3 次已确认反馈 · 今天使用过</small></div>', icon('chevron'), '</button>',
    '<button class="memory-summary" type="button" data-action="toast" data-message="已打开“轻松节奏”的来源和使用记录"><span>', icon('clock'), '</span><div><strong>偏好轻松节奏</strong><small>由你在 2026-07-02 主动设置 · 影响 2 份计划</small></div>', icon('chevron'), '</button>',
    sectionLabel('提醒与计划', ''),
    '<div class="settings-card">',
      settingRow('bell', '周六半日计划', '行前 30 分钟提醒', '已开启', false),
      settingRow('spark', '主动计划', '每周五询问周末是否有空', '未开启', true),
    '</div>',
    sectionLabel('使用渠道', ''),
    '<div class="settings-card">',
      settingRow('phone', '网页版', '当前正在使用，收藏和计划会同步保留', '已连接', false),
      settingRow('agent', '在微信里使用拾光', '以后可以直接把店名、链接和截图发给拾光', '尚未开放', true),
    '</div>',
    sectionLabel('数据与隐私', ''),
    '<div class="settings-card">',
      settingRow('download', '导出我的数据', '收藏、计划与已确认记忆', '', false),
      settingRow('settings', '管理或清除记忆', '不会删除收藏和计划', '', false),
    '</div>'
  ].join('');
  return mobileShell(header, body, 'me');
}

function settingRow(iconName, title, detail, status, offline) {
  return [
    '<div class="settings-row">',
      '<div class="setting-icon">', icon(iconName), '</div>',
      '<div class="settings-row-copy"><h3>', title, '</h3><p>', detail, '</p></div>',
      status ? '<span class="setting-status ' + (offline ? 'offline' : '') + '">' + status + '</span>' : icon('chevron'),
    '</div>'
  ].join('');
}

function renderShare(state) {
  const header = screenHeader('SHARED FROM SHIGUANG', '拾光', 'share', 'copy-link', true, '复制分享链接');
  if (state !== 'valid') {
    const copy = {
      cancelled: ['这个计划已经取消', '分享者取消了原计划，因此路线不再提供。'],
      revoked: ['分享已经关闭', '分享者关闭了公开访问。原收藏和私人信息始终没有包含在链接中。'],
      expired: ['链接已经失效', '为了保护计划信息，分享链接已超过有效期。']
    }[state];
    return mobileShell(header, [
      '<div class="empty-state"><div>',
        '<div class="empty-icon">', icon(state === 'cancelled' ? 'calendar' : 'link'), '</div>',
        '<h3>', copy[0], '</h3><p>', copy[1], '</p>',
        '<button class="primary-action" type="button" data-action="go-agent">用拾光生成我的计划</button>',
      '</div></div>'
    ].join(''), null, true);
  }
  const body = [
    '<section class="share-cover">',
      '<div class="share-cover-top"><div class="share-author"><span class="author-avatar">张</span>张子豪分享</div><span class="read-only-badge">READ ONLY</span></div>',
      '<h1>深圳周六<br>半日计划</h1>',
      '<p>7 月 25 日 · 14:00–19:00 · 福田区</p>',
      '<div class="share-freshness"><span>最后更新：今天 15:30</span><span>7 月 26 日 19:00 失效</span></div>',
    '</section>',
    '<div class="privacy-note" style="margin-top:10px">', icon('check'), '<span>这是只读分享，不包含收藏库、历史反馈、私人记忆和精确住址。</span></div>',
    sectionLabel('行程安排', ''),
    '<div class="time-ribbon">',
      timelineItem('14:00', '当代艺术与城市规划馆', '约 2 小时 · 免费', '地点', false, '查看公开地图'),
      timelineItem('16:30', 'One Avenue 咖啡休息', '约 1 小时 · ¥60–100', '地点', true, '步行 12 分钟'),
      timelineItem('18:00', '市民中心夜景散步', '约 45 分钟 · 免费', '地点', false, '步行 8 分钟'),
    '</div>',
    '<div class="budget-bar">',
      '<div class="budget-stat"><small>预计花费</small><strong>¥60–100</strong></div>',
      '<div class="budget-stat"><small>总时长</small><strong>约 4.5 h</strong></div>',
      '<div class="budget-stat"><small>步行</small><strong>约 2.1 km</strong></div>',
    '</div>',
    '<button class="primary-action lime full-action" type="button" data-action="open-route">', icon('route'), '查看路线</button>',
    '<div class="action-row"><button class="secondary-action" type="button" data-action="copy-link">', icon('link'), '复制链接</button><button class="secondary-action" type="button" data-action="go-agent">生成我的计划</button></div>'
  ].join('');
  return mobileShell(header, body, null, true);
}

function renderScreen() {
  const screen = getScreen(currentScreenId);
  const state = stateByScreen[currentScreenId];
  els.prototypeScreen.innerHTML = screen.render(state);
  els.stageCode.textContent = screen.code + ' · ' + (screen.nav ? screen.nav.toUpperCase() : 'PUBLIC');
  els.stageTitle.textContent = screen.title;
  const stateLabel = screen.states.find(function (item) { return item[0] === state; });
  els.stageState.textContent = stateLabel ? stateLabel[1] : '默认状态';
  els.reviewPurpose.textContent = screen.purpose;
  els.reviewChecks.innerHTML = screen.checks.map(function (item) { return '<li>' + item + '</li>'; }).join('');
  els.noteScreenName.textContent = screen.code + ' ' + screen.title;
  renderStateControls(screen);
  renderInteractions(screen);
  updateScreenList();
  renderSavedNotes();
}

function renderStateControls(screen) {
  els.stateControls.innerHTML = screen.states.map(function (state) {
    const isActive = stateByScreen[screen.id] === state[0];
    return '<button type="button" class="state-button ' + (isActive ? 'is-active' : '') + '" data-state="' + state[0] + '" aria-pressed="' + String(isActive) + '">' + state[1] + '</button>';
  }).join('');
}

function renderInteractions(screen) {
  els.interactionCount.textContent = screen.interactions.length + ' 项';
  els.interactionList.innerHTML = screen.interactions.map(function (item) {
    return '<div class="interaction-row">' + icon('chevron') + '<strong>' + item[0] + '</strong><span>' + item[1] + '</span></div>';
  }).join('');
}

function renderScreenList() {
  els.screenList.innerHTML = screenDefinitions.map(function (screen) {
    const isActive = screen.id === currentScreenId;
    return [
      '<button type="button" class="screen-link ', isActive ? 'is-active' : '', '" data-screen-link="', screen.id, '" ', isActive ? 'aria-current="page"' : '', '>',
        '<span class="screen-code">', screen.code, '</span>',
        '<div><strong>', screen.title, '</strong><small>', screen.short, '</small></div>',
      '</button>'
    ].join('');
  }).join('');
}

function updateScreenList() {
  document.querySelectorAll('[data-screen-link]').forEach(function (button) {
    const isActive = button.dataset.screenLink === currentScreenId;
    button.classList.toggle('is-active', isActive);
    if (isActive) {
      button.setAttribute('aria-current', 'page');
    } else {
      button.removeAttribute('aria-current');
    }
  });
}

function renderOverview() {
  els.overviewGrid.innerHTML = screenDefinitions.map(function (screen) {
    const state = screen.states[0][0];
    return [
      '<article class="overview-card" data-overview-screen="', screen.id, '">',
        '<header><strong>', screen.title, '</strong><span>', screen.code, '</span></header>',
        '<div class="overview-window"><div class="overview-device">', screen.render(state), '</div></div>',
      '</article>'
    ].join('');
  }).join('');
}

function goToScreen(id, state) {
  if (!getScreen(id)) return;
  currentScreenId = id;
  if (state) stateByScreen[id] = state;
  if (currentView !== 'single') setView('single');
  renderScreen();
  const scroll = els.prototypeScreen.querySelector('.screen-scroll');
  if (scroll) scroll.scrollTop = 0;
}

function setView(view) {
  currentView = view;
  els.singleView.classList.toggle('is-active', view === 'single');
  els.overviewView.classList.toggle('is-active', view === 'overview');
  document.querySelectorAll('[data-view]').forEach(function (button) {
    const isActive = button.dataset.view === view;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-pressed', String(isActive));
  });
  if (view === 'overview') renderOverview();
}

function setCanvas(canvas) {
  currentCanvas = canvas === 'desktop' ? 'desktop' : 'mobile';
  document.body.classList.toggle('canvas-desktop', currentCanvas === 'desktop');
  els.singleView.classList.toggle('desktop-canvas', currentCanvas === 'desktop');
  els.canvasSize.textContent = currentCanvas === 'desktop' ? '960 × 760' : '390 × 844';
  document.querySelectorAll('[data-canvas]').forEach(function (button) {
    const isActive = button.dataset.canvas === currentCanvas;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-pressed', String(isActive));
  });
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  els.toast.textContent = message;
  els.toast.classList.add('is-visible');
  toastTimer = window.setTimeout(function () {
    els.toast.classList.remove('is-visible');
  }, 2200);
}

function handlePrototypeAction(action, element) {
  const routes = {
    'go-agent': ['agent'],
    'go-import': ['import', 'saved'],
    'go-collection': ['collection'],
    'go-detail': ['detail', 'ambiguous'],
    'go-plan': ['plan', 'draft'],
    'go-confirmed': ['confirmed', 'confirmed'],
    'go-me': ['me'],
    'share-plan': ['share', 'valid']
  };
  if (routes[action]) {
    goToScreen(routes[action][0], routes[action][1]);
    return;
  }
  if (action === 'go-screen') {
    goToScreen(element.dataset.screen);
    return;
  }
  if (action === 'go-plan-permission') {
    goToScreen('plan', 'permission');
    return;
  }
  if (action === 'go-detail-missing') {
    goToScreen('detail', 'missing');
    return;
  }
  if (action === 'back-context') {
    goToScreen('import', 'saved');
    showToast('已返回刚才的对话位置');
    return;
  }
  if (action === 'submit-import') {
    goToScreen('import', 'recognizing');
    window.setTimeout(function () {
      if (currentScreenId === 'import' && stateByScreen.import === 'recognizing') {
        stateByScreen.import = 'saved';
        renderScreen();
      }
    }, 1400);
    return;
  }
  if (action === 'set-prompt') {
    const input = document.getElementById('agentPrompt');
    if (input) input.value = element.dataset.value || '';
    stateByScreen.agent = 'listening';
    showToast('已作为本次计划条件，不会写入长期偏好');
    return;
  }
  if (action === 'focus-agent') {
    const input = document.getElementById('agentPrompt');
    if (input) input.focus();
    return;
  }
  if (action === 'undo-import') {
    stateByScreen.import = 'undone';
    renderScreen();
    showToast('已撤销本次收藏，可以恢复');
    return;
  }
  if (action === 'restore-import') {
    stateByScreen.import = 'saved';
    renderScreen();
    showToast('收藏已恢复');
    return;
  }
  if (action === 'choose-candidate') {
    stateByScreen.detail = 'selected';
    renderScreen();
    showToast('已选择福田区候选地点');
    return;
  }
  if (action === 'choose-any') {
    stateByScreen.detail = 'any_branch';
    renderScreen();
    showToast('已记录：任意分店都可以');
    return;
  }
  if (action === 'choose-none') {
    stateByScreen.detail = 'missing';
    renderScreen();
    showToast('候选均未采用，原始收藏已保留为待补充');
    return;
  }
  if (action === 'save-place') {
    goToScreen('import', 'saved');
    showToast('地点选择已保存，并返回原对话');
    return;
  }
  if (action === 'delete-place') {
    stateByScreen.import = 'undone';
    goToScreen('import', 'undone');
    showToast('收藏已删除，可以恢复');
    return;
  }
  if (action === 'confirm-plan') {
    goToScreen('confirmed', 'confirmed');
    showToast('计划已确认；提醒尚未设置');
    return;
  }
  if (action === 'show-alternatives') {
    stateByScreen.plan = stateByScreen.plan === 'alternatives' ? 'draft' : 'alternatives';
    renderScreen();
    return;
  }
  if (action === 'allow-external') {
    stateByScreen.plan = 'generating';
    renderScreen();
    window.setTimeout(function () {
      if (currentScreenId === 'plan') {
        stateByScreen.plan = 'draft';
        renderScreen();
        showToast('已补充 1 个高德地点，并标明来源');
      }
    }, 1000);
    return;
  }
  if (action === 'deny-external') {
    stateByScreen.plan = 'collection_only';
    renderScreen();
    showToast('已关闭外部补充，将只使用现有收藏');
    return;
  }
  if (action === 'retry-plan') {
    stateByScreen.plan = 'generating';
    renderScreen();
    return;
  }
  if (action === 'show-feedback') {
    stateByScreen.confirmed = 'feedback';
    renderScreen();
    return;
  }
  if (action === 'feedback-complete') {
    stateByScreen.confirmed = 'confirmed';
    renderScreen();
    showToast('已记录完成；计划中的收藏地点已标记为去过');
    return;
  }
  if (action === 'feedback-partial') {
    stateByScreen.confirmed = 'partial';
    renderScreen();
    return;
  }
  if (action === 'save-partial') {
    stateByScreen.confirmed = 'confirmed';
    renderScreen();
    showToast('部分完成已保存，只更新了你选中的地点');
    return;
  }
  if (action === 'feedback-incomplete') {
    stateByScreen.confirmed = 'incomplete';
    renderScreen();
    return;
  }
  if (action === 'show-reminder') {
    stateByScreen.confirmed = 'reminder';
    renderScreen();
    return;
  }
  if (action === 'enable-reminder') {
    reminderEnabled = true;
    stateByScreen.confirmed = 'confirmed';
    renderScreen();
    showToast('已设置出发前 60 分钟提醒');
    return;
  }
  if (action === 'skip-reminder' || action === 'close-state-panel') {
    stateByScreen.confirmed = 'confirmed';
    renderScreen();
    return;
  }
  if (action === 'show-share-preview') {
    stateByScreen.confirmed = 'share_preview';
    renderScreen();
    return;
  }
  if (action === 'create-share') {
    shareActive = true;
    stateByScreen.confirmed = 'share_active';
    renderScreen();
    showToast('只读分享链接已创建');
    return;
  }
  if (action === 'show-share-management') {
    stateByScreen.confirmed = 'share_active';
    renderScreen();
    return;
  }
  if (action === 'open-share') {
    goToScreen('share', 'valid');
    return;
  }
  if (action === 'revoke-share') {
    shareActive = false;
    stateByScreen.share = 'revoked';
    stateByScreen.confirmed = 'confirmed';
    renderScreen();
    showToast('分享已关闭，原链接不再显示计划');
    return;
  }
  if (action === 'show-versions') {
    stateByScreen.confirmed = 'versions';
    renderScreen();
    return;
  }
  if (action === 'cancel-plan') {
    stateByScreen.share = 'cancelled';
    goToScreen('share', 'cancelled');
    showToast('计划已取消，分享页已同步停止');
    return;
  }
  if (action === 'show-memory') {
    stateByScreen.me = 'memory';
    renderScreen();
    return;
  }
  if (action === 'open-route') {
    showToast('正式版本将打开高德路线');
    return;
  }
  if (action === 'copy-link') {
    showToast('分享链接已复制（原型演示）');
    return;
  }
  if (action === 'toast') {
    showToast(element.dataset.message || '该操作将在正式开发时接入');
    return;
  }
  if (action === 'noop') {
    showToast('当前为 UX/UI 演示，不执行真实操作');
  }
}

function loadNotes() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch (error) {
    return [];
  }
}

function saveNotes(notes) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
}

function renderSavedNotes() {
  const notes = loadNotes().filter(function (note) {
    return note.screenId === currentScreenId;
  }).slice(-3).reverse();
  els.savedNotes.innerHTML = notes.map(function (note) {
    return '<div class="saved-note"><small>' + note.code + ' · ' + note.time + '</small><p>' + escapeHtml(note.text) + '</p></div>';
  }).join('');
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, function (char) {
    return {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    }[char];
  });
}

function addReviewNote() {
  const text = els.reviewNote.value.trim();
  if (!text) {
    showToast('先写下一条具体意见');
    return;
  }
  const screen = getScreen(currentScreenId);
  const notes = loadNotes();
  notes.push({
    screenId: screen.id,
    code: screen.code + ' ' + screen.title,
    text: text,
    time: new Date().toLocaleString('zh-CN', { hour12: false })
  });
  saveNotes(notes);
  els.reviewNote.value = '';
  renderSavedNotes();
  showToast('评审意见已保存在本机');
}

function exportReviewNotes() {
  const notes = loadNotes();
  if (!notes.length) {
    showToast('还没有可导出的意见');
    return;
  }
  const blob = new Blob([JSON.stringify(notes, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = '拾光_UX评审意见.json';
  link.click();
  URL.revokeObjectURL(url);
  showToast('评审意见已导出');
}

function bindEvents() {
  els.screenList.addEventListener('click', function (event) {
    const button = event.target.closest('[data-screen-link]');
    if (button) goToScreen(button.dataset.screenLink);
  });

  els.prototypeScreen.addEventListener('click', function (event) {
    const target = event.target.closest('[data-action]');
    if (target && !target.disabled) handlePrototypeAction(target.dataset.action, target);
  });

  els.prototypeScreen.addEventListener('keydown', function (event) {
    if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[role="button"]')) {
      event.preventDefault();
      handlePrototypeAction(event.target.dataset.action, event.target);
    }
  });

  els.stateControls.addEventListener('click', function (event) {
    const button = event.target.closest('[data-state]');
    if (!button) return;
    stateByScreen[currentScreenId] = button.dataset.state;
    renderScreen();
  });

  document.querySelectorAll('[data-view]').forEach(function (button) {
    button.addEventListener('click', function () {
      setView(button.dataset.view);
    });
  });

  document.querySelectorAll('[data-canvas]').forEach(function (button) {
    button.addEventListener('click', function () {
      setCanvas(button.dataset.canvas);
      if (currentView !== 'single') setView('single');
    });
  });

  els.overviewGrid.addEventListener('click', function (event) {
    const card = event.target.closest('[data-overview-screen]');
    if (card) goToScreen(card.dataset.overviewScreen);
  });

  document.getElementById('restartFlow').addEventListener('click', function () {
    stateByScreen.agent = 'default';
    goToScreen('agent');
    showToast('已回到核心流程起点');
  });

  document.getElementById('saveNote').addEventListener('click', addReviewNote);
  document.getElementById('exportNotes').addEventListener('click', exportReviewNotes);
}

renderScreenList();
renderScreen();
bindEvents();
