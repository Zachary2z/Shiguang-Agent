const STORAGE_KEY = 'shiguang-ux-review-notes-v1';

const screenDefinitions = [
  {
    id: 'agent',
    code: 'M01',
    title: 'Agent 首页',
    short: '输入与首次价值',
    nav: 'agent',
    purpose: '验证用户是否能快速理解：这里不是推荐信息流，而是把内容交给 Agent 的入口。',
    checks: ['主输入是否足够突出', '三种输入方式是否容易理解', '用户是否知道收藏何时足以生成计划'],
    states: [
      ['default', '默认'],
      ['listening', '已输入要求'],
      ['empty', '无收藏']
    ],
    interactions: [
      ['发送内容', '进入识别结果'],
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
    checks: ['识别中不会过早宣称收藏成功', '修改和撤销是否容易发现', '待选择与失败状态是否给出最短恢复路径'],
    states: [
      ['saved', '已收藏'],
      ['recognizing', '识别中'],
      ['ambiguous', '待选择'],
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
    checks: ['卡片信息密度是否合适', '状态是否比平台来源更重要', '待选择内容是否明显且不会误入规划'],
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
    checks: ['候选差异是否足够清晰', '系统是否避免把第一名当作已确认', '用户能否继续修改结构化字段'],
    states: [
      ['ambiguous', '待选择'],
      ['selected', '已选择'],
      ['missing', '需要补充']
    ],
    interactions: [
      ['选择候选地点', '绑定准确 POI'],
      ['编辑字段', '纠正区域和标签'],
      ['确认并保存', '返回收藏库']
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
      ['generating', '生成中'],
      ['permission', '外部授权'],
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
    checks: ['路线、日历和提醒是否容易找到', '确认态和草稿态是否有明显差异', '反馈是否足够轻量且透明'],
    states: [
      ['confirmed', '已确认'],
      ['partial', '部分完成'],
      ['feedback', '完成反馈']
    ],
    interactions: [
      ['打开路线', '模拟高德导航'],
      ['设置提醒', '创建单次提醒'],
      ['分享方案', '打开只读分享页']
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
      ['privacy', '隐私管理']
    ],
    interactions: [
      ['管理偏好', '查看、修改或删除记忆'],
      ['提醒设置', '开关单次与主动提醒'],
      ['微信 ClawBot', '查看后续接入说明']
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
let toastTimer;

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

function icon(name) {
  return '<svg aria-hidden="true"><use href="#i-' + name + '"></use></svg>';
}

function getScreen(id) {
  return screenDefinitions.find(function (screen) {
    return screen.id === id;
  });
}

function screenHeader(kicker, title, actionIcon, action, brandTitle) {
  return [
    '<header class="mobile-header">',
      '<div class="mobile-header-copy">',
        '<p class="kicker">', kicker, '</p>',
        '<h1 class="', brandTitle ? 'brand-title' : '', '">', title, '</h1>',
      '</div>',
      actionIcon ? '<button class="icon-button" type="button" data-action="' + (action || 'noop') + '" aria-label="页面操作">' + icon(actionIcon) + '</button>' : '',
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
        return '<button type="button" class="nav-item ' + (id === active ? 'is-active' : '') + '" data-action="go-screen" data-screen="' + id + '">' + icon(item[1]) + '<span>' + item[2] + '</span></button>';
      }).join(''),
    '</nav>'
  ].join('');
}

function mobileShell(header, body, activeNav, share) {
  return [
    '<div class="mobile-app ', share ? 'share-app' : '', '">',
      header,
      '<main class="screen-scroll ', activeNav ? '' : 'no-nav', '">', body, '</main>',
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
  const header = screenHeader('SHENZHEN · MON 20 JUL', '晚上好，张子豪', 'settings', 'go-me');
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
        '<input id="agentPrompt" aria-label="告诉拾光你的想法" value="', state === 'listening' ? '周六下午 5 小时，福田优先' : '', '" placeholder="店名、链接、截图或一句要求" />',
        '<button class="send-button" type="button" data-action="submit-import" aria-label="发送">', icon('send'), '</button>',
      '</div>',
      '<div class="attachment-actions">',
        '<button type="button" data-action="toast" data-message="图片上传将在正式开发时接入">', icon('image'), '发截图</button>',
        '<button type="button" data-action="toast" data-message="粘贴链接后会创建识别任务">', icon('link'), '贴链接</button>',
      '</div>',
    '</section>',
    sectionLabel('快速开始', ''),
    '<div class="chips">',
      '<button class="chip" type="button" data-action="set-prompt" data-value="周六下午 5 小时，福田优先">周六下午有空</button>',
      '<button class="chip" type="button" data-action="set-prompt" data-value="找个适合下雨天的室内活动">下雨天室内</button>',
      '<button class="chip" type="button" data-action="set-prompt" data-value="只用我的收藏，轻松一点">只用我的收藏</button>',
    '</div>',
    collectionSummary
  ].join('');
  return mobileShell(header, body, 'agent');
}

function renderImport(state) {
  const header = screenHeader('AGENT CONVERSATION', '正在整理这条收藏', 'bookmark', 'go-collection');
  const userMessage = '<div class="message user">帮我收藏深圳当代艺术与城市规划馆</div>';
  let agentContent = '';

  if (state === 'recognizing') {
    agentContent = [
      '<div class="agent-line">',
        '<div class="agent-avatar">', icon('spark'), '</div>',
        '<div class="agent-bubble">',
          '<p>我正在读取内容，并核对深圳范围内的准确地点。</p>',
          '<div class="import-progress">',
            '<div class="progress-header"><span>正在识别地点与开放信息</span><span>72%</span></div>',
            '<div class="progress-track"><i></i></div>',
            '<div class="skeleton line"></div><div class="skeleton line short"></div>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');
  } else if (state === 'failed') {
    agentContent = [
      '<div class="agent-line">',
        '<div class="agent-avatar">', icon('spark'), '</div>',
        '<div class="agent-bubble">',
          '<p>这个页面暂时无法读取，没有创建收藏。</p>',
          statusCard('error', 'link', '公开页面无法访问', '你可以发送包含店名和区域的截图，或直接告诉我地点名称。', '发送截图', 'toast'),
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
    '</div>',
    '<div class="message-composer"><input aria-label="继续对话" placeholder="继续添加，或直接说出修改内容" /><button class="send-button" type="button" data-action="toast" data-message="已记录你的补充要求">', icon('send'), '</button></div>'
  ].join('');
  return mobileShell(header, body, 'agent');
}

function renderCollection(state) {
  const header = screenHeader('YOUR CITY MEMORY', '收藏', 'plus', 'toast');
  if (state === 'empty') {
    return mobileShell(header, '<div class="empty-state"><div><div class="empty-icon">' + icon('bookmark') + '</div><h3>收藏库还是空的</h3><p>从 Agent 页面发送一个店名、链接或截图，确认后会出现在这里。</p><button class="primary-action" type="button" data-action="go-agent">去添加第一个地点</button></div></div>', 'collection');
  }

  const pendingBanner = state === 'pending'
    ? '<div class="state-inline-banner warning">' + icon('map-pin') + '<span>有 2 条收藏仍需确认地点。确认前不会进入路线计算。</span></div>'
    : '';
  const body = [
    '<div class="collection-count"><strong>12</strong><span>个深圳收藏 · 9 个可参与规划</span></div>',
    pendingBanner,
    '<div class="search-field">', icon('search'), '<input aria-label="搜索收藏" placeholder="搜索名称、区域或标签" /></div>',
    '<div class="filter-tabs">',
      '<button class="filter-tab is-active" type="button">想去 9</button>',
      '<button class="filter-tab" type="button">已计划 2</button>',
      '<button class="filter-tab" type="button">去过 1</button>',
    '</div>',
    '<div class="chips">',
      '<button class="chip is-active" type="button">全部</button>',
      '<button class="chip" type="button">展览</button>',
      '<button class="chip" type="button">室内</button>',
      '<button class="chip" type="button">福田</button>',
    '</div>',
    sectionLabel('按最近添加', '多选'),
    '<div class="collection-list">',
      placeCard('深圳当代艺术与城市规划馆', '福田 · 免费', ['展览', '室内'], false, 'default'),
      placeCard('南头古城', '南山 · 约 ¥80', ['散步', '朋友'], false, 'city'),
      placeCard('一尺花园 · 海上世界店', '南山 · 价格待确认', ['咖啡', '室内'], state === 'pending', 'default'),
      placeCard('OCT-LOFT 创意文化园', '南山 · 免费', ['街区', '室外'], false, 'city'),
    '</div>',
    '<button class="primary-action" style="width:100%;margin-top:14px" type="button" data-action="go-plan">用当前筛选生成计划</button>'
  ].join('');
  return mobileShell(header, body, 'collection');
}

function placeCard(title, meta, tags, needsAction, thumbType) {
  return [
    '<article class="place-card" role="button" tabindex="0" data-action="go-detail">',
      '<div class="place-thumb ', thumbType === 'city' ? 'city' : '', '"></div>',
      '<div class="place-card-copy">',
        '<h3>', title, '</h3>',
        '<p>', meta, '</p>',
        '<div class="place-meta-row">',
          tags.map(function (tag) { return '<span class="tiny-tag">' + tag + '</span>'; }).join(''),
          needsAction ? '<span class="tiny-tag needs-action">待确认地点</span>' : '<span class="tiny-tag">已确认</span>',
        '</div>',
      '</div>',
    '</article>'
  ].join('');
}

function renderDetail(state) {
  const header = screenHeader('COLLECTION DETAIL', state === 'missing' ? '补充地点信息' : '确认准确地点', 'bookmark', 'go-collection');
  if (state === 'missing') {
    const bodyMissing = [
      '<div class="detail-visual"><div class="detail-visual-copy"><span>原始识别结果</span><h2>一尺花园</h2></div></div>',
      statusCard('warning', 'map-pin', '还不能确定是哪家分店', '请补充行政区、商圈、附近地标，或粘贴地图分享链接。', '', ''),
      sectionLabel('最少补充一项', ''),
      '<div class="editable-fields">',
        '<div class="editable-field"><span>行政区</span><strong>请选择</strong></div>',
        '<div class="editable-field"><span>商圈或地标</span><strong>例如：海上世界</strong></div>',
        '<div class="editable-field"><span>地图链接</span><strong>粘贴链接</strong></div>',
      '</div>',
      '<button class="primary-action" style="width:100%;margin-top:12px" type="button" data-action="choose-candidate">重新查找候选</button>'
    ].join('');
    return mobileShell(header, bodyMissing, 'collection');
  }

  const selected = state === 'selected';
  const body = [
    '<div class="detail-visual"><div class="detail-visual-copy"><span>原始内容识别 · 店名</span><h2>深圳当代艺术与城市规划馆</h2></div></div>',
    '<div class="state-inline-banner ', selected ? '' : 'warning', '">',
      icon(selected ? 'check' : 'map-pin'),
      '<span>', selected ? '已选择第 1 个候选，可以继续修改识别字段。' : '存在 2 个合理候选。排名第一不等于位置已经确认。', '</span>',
    '</div>',
    sectionLabel('请选择准确地点', ''),
    '<div class="candidate-list">',
      '<article class="candidate-card ', selected ? 'is-selected' : '', '" data-action="choose-candidate" role="button" tabindex="0">',
        '<span class="radio-mark"></span>',
        '<div><h3>深圳当代艺术与城市规划馆</h3><p>福田区福中路184号 · 与截图地标一致 · 1.2 km</p></div>',
      '</article>',
      '<article class="candidate-card" data-action="choose-candidate" role="button" tabindex="0">',
        '<span class="radio-mark"></span>',
        '<div><h3>深圳市当代艺术馆</h3><p>南山区 · 名称相近，但缺少来源中的建筑特征</p></div>',
      '</article>',
    '</div>',
    sectionLabel('识别字段', '编辑'),
    '<div class="editable-fields">',
      '<div class="editable-field"><span>区域</span><strong>福田区</strong></div>',
      '<div class="editable-field"><span>价格</span><strong>免费</strong></div>',
      '<div class="editable-field"><span>适用场景</span><strong>室内 · 独处 · 朋友</strong></div>',
    '</div>',
    '<div class="action-row">',
      '<button class="ghost-action" type="button" data-action="go-collection">取消</button>',
      '<button class="primary-action" type="button" data-action="save-place" ', selected ? '' : 'disabled', '>确认并保存</button>',
    '</div>'
  ].join('');
  return mobileShell(header, body, 'collection');
}

function renderPlan(state) {
  const header = screenHeader('PLAN DRAFT · V1', '周六半日计划', 'edit', 'toast');
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
        '<div class="action-row"><button class="secondary-action" type="button" data-action="deny-external">只用收藏</button><button class="primary-action" type="button" data-action="allow-external">允许补充</button></div>',
      '</div>'
    ].join('');
    return mobileShell(header, permission, 'plan');
  }
  if (state === 'failed') {
    const failed = [
      statusCard('error', 'route', '路线工具暂时不可用', '收藏筛选已经完成，但无法确认地点之间的预计路程。你可以稍后重试，或先查看未排序的候选。', '重新生成', 'retry-plan'),
      '<button class="secondary-action" style="width:100%;margin-top:10px" type="button" data-action="go-collection">返回收藏库</button>'
    ].join('');
    return mobileShell(header, failed, 'plan');
  }

  const body = [
    '<section class="plan-hero">',
      '<div class="plan-hero-top">',
        '<div><span class="eyebrow">MAIN PLAN</span><h2>一个展览，一次停留，再留点余地</h2><p>周六 14:00–19:00 · 福田区</p></div>',
        '<div class="plan-score">92</div>',
      '</div>',
      '<div class="plan-conditions"><span>5 小时</span><span>轻松一点</span><span>预算不限</span><span>公共交通</span></div>',
    '</section>',
    sectionLabel('时间光轨', '查看备选 2'),
    '<div class="time-ribbon">',
      timelineItem('14:00', '深圳当代艺术与城市规划馆', '约 2 小时 · 免费 · 周一闭馆', '收藏', false, '起点'),
      timelineItem('16:30', 'One Avenue 咖啡休息', '约 1 小时 · ¥60–100 · 未收藏', '高德补充', true, '步行 12 分钟'),
      timelineItem('18:00', '市民中心夜景散步', '约 45 分钟 · 免费', '收藏', false, '步行 8 分钟'),
    '</div>',
    '<div class="budget-bar">',
      '<div class="budget-stat"><small>预计花费</small><strong>¥60–100</strong></div>',
      '<div class="budget-stat"><small>步行</small><strong>约 2.1 km</strong></div>',
      '<div class="budget-stat"><small>结束留白</small><strong>25 min</strong></div>',
    '</div>',
    '<div class="explain-card"><strong>为什么这样安排</strong><p>核心展览来自你的收藏；咖啡店只为补足中途休息，并已标记为高德外部补充。预算未设置，因此仅展示估算。</p></div>',
    sectionLabel('继续调整', ''),
    '<div class="adjust-composer"><input aria-label="调整计划" placeholder="例如：少走一点，不要咖啡店" /><button class="send-button" type="button" data-action="toast" data-message="已保留其他条件并重新计算">', icon('send'), '</button></div>',
    '<div class="action-row"><button class="secondary-action" type="button" data-action="toast" data-message="已保存为备选方案">保存备选</button><button class="primary-action" type="button" data-action="confirm-plan">确认方案</button></div>'
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
      '</div>',
    '</article>'
  ].join('');
}

function renderConfirmed(state) {
  const header = screenHeader('CONFIRMED · SAT 14:00', '周六计划', 'share', 'share-plan');
  const partialBanner = state === 'partial'
    ? '<div class="state-inline-banner warning">' + icon('check') + '<span>已标记部分完成：到访 2 个地点，跳过咖啡休息。计划记录不会自动改写长期偏好。</span></div>'
    : '';
  const feedback = state === 'feedback'
    ? '<div class="feedback-card"><h3>这次安排怎么样？</h3><p>反馈只用于调整下次推荐排序，不会公开展示。</p><div class="feedback-options"><button data-action="feedback-done">已完成</button><button data-action="feedback-done">部分完成</button><button data-action="feedback-done">未完成</button></div></div>'
    : '';
  const body = [
    partialBanner,
    '<div class="confirmed-banner"><div class="confirmed-icon">', icon('check'), '</div><div><h3>计划已确认</h3><p>行前提醒将在 13:30 发送</p></div></div>',
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
      executionCard('bell', '提醒已开启', 'toast'),
      executionCard('share', '分享只读方案', 'share-plan'),
    '</div>',
    feedback,
    state !== 'feedback' ? '<button class="primary-action" style="width:100%;margin-top:12px" type="button" data-action="show-feedback">完成后反馈</button>' : ''
  ].join('');
  return mobileShell(header, body, 'plan');
}

function executionCard(iconName, label, action) {
  return '<button class="execution-card" type="button" data-action="' + action + '">' + icon(iconName) + '<strong>' + label + '</strong></button>';
}

function renderMe(state) {
  const header = screenHeader('ACCOUNT & MEMORY', '我的', 'settings', 'toast');
  const suggestion = state === 'suggestion'
    ? '<div class="permission-card"><h3>要记住“你更喜欢室内展览”吗？</h3><p>这是根据最近 3 次反馈推断的长期偏好。确认前不会写入记忆。</p><div class="action-row"><button class="secondary-action" data-action="toast" data-message="已忽略这条建议">不记住</button><button class="primary-action" data-action="toast" data-message="已保存偏好，可随时删除">确认记住</button></div></div>'
    : '';
  const privacy = state === 'privacy'
    ? '<div class="state-inline-banner">' + icon('settings') + '<span>你可以导出或删除收藏、计划和记忆。删除操作会再次确认，不影响本机评审笔记。</span></div>'
    : '';
  const body = [
    suggestion,
    privacy,
    '<section class="profile-card">',
      '<h2>拾光正在逐步了解你</h2>',
      '<p>所有长期记忆都可以查看、修改或删除</p>',
      '<div class="profile-stats"><div><strong>12</strong><span>收藏</span></div><div><strong>08</strong><span>完成计划</span></div><div><strong>04</strong><span>已确认偏好</span></div></div>',
    '</section>',
    sectionLabel('偏好记忆', '管理全部'),
    chips([['偏好展览', 'accent'], ['喜欢室内', ''], ['轻松节奏', ''], ['少排队', 'lime']]),
    sectionLabel('提醒与计划', ''),
    '<div class="settings-card">',
      settingRow('bell', '周六半日计划', '行前 30 分钟提醒', '已开启', false),
      settingRow('spark', '主动计划', '每周五询问周末是否有空', '未开启', true),
    '</div>',
    sectionLabel('使用渠道', ''),
    '<div class="settings-card">',
      settingRow('phone', 'Web / H5', '当前主要使用入口', '已连接', false),
      settingRow('agent', '微信 ClawBot', '后续通过适配器连接同一 Agent', '未连接', true),
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
  const header = screenHeader('SHARED FROM SHIGUANG', '拾光', 'share', 'copy-link', true);
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
      '<div class="budget-stat"><small>更新</small><strong>15:30</strong></div>',
    '</div>',
    '<button class="primary-action lime" style="width:100%;margin-top:14px" type="button" data-action="go-agent">用拾光生成我的计划</button>',
    '<button class="secondary-action" style="width:100%;margin-top:8px" type="button" data-action="copy-link">', icon('link'), '复制分享链接</button>'
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
    return '<button type="button" class="state-button ' + (stateByScreen[screen.id] === state[0] ? 'is-active' : '') + '" data-state="' + state[0] + '">' + state[1] + '</button>';
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
    return [
      '<button type="button" class="screen-link ', screen.id === currentScreenId ? 'is-active' : '', '" data-screen-link="', screen.id, '">',
        '<span class="screen-code">', screen.code, '</span>',
        '<div><strong>', screen.title, '</strong><small>', screen.short, '</small></div>',
      '</button>'
    ].join('');
  }).join('');
}

function updateScreenList() {
  document.querySelectorAll('[data-screen-link]').forEach(function (button) {
    button.classList.toggle('is-active', button.dataset.screenLink === currentScreenId);
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
    button.classList.toggle('is-active', button.dataset.view === view);
  });
  if (view === 'overview') renderOverview();
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
    showToast('已撤销本次收藏 · 5 秒内可恢复');
    return;
  }
  if (action === 'choose-candidate') {
    stateByScreen.detail = 'selected';
    renderScreen();
    showToast('已选择福田区候选地点');
    return;
  }
  if (action === 'save-place') {
    goToScreen('collection', 'default');
    showToast('地点已确认并保存');
    return;
  }
  if (action === 'confirm-plan') {
    goToScreen('confirmed', 'confirmed');
    showToast('计划已确认，行前提醒已开启');
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
    stateByScreen.plan = 'failed';
    renderScreen();
    showToast('将只使用现有收藏');
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
  if (action === 'feedback-done') {
    stateByScreen.confirmed = 'partial';
    renderScreen();
    showToast('反馈已记录，仅用于调整下次排序');
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
