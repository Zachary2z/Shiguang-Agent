const viewButtons = document.querySelectorAll('[data-view]');
const productViews = document.querySelectorAll('[data-product-view]');
const viewportButtons = document.querySelectorAll('[data-viewport]');
const previewStage = document.querySelector('.preview-stage');
const toast = document.querySelector('.toast');
let toastTimer;

function showView(viewName) {
  productViews.forEach(function (view) {
    const active = view.dataset.productView === viewName;
    view.hidden = !active;
    view.classList.toggle('is-active', active);
  });

  viewButtons.forEach(function (button) {
    const active = button.dataset.view === viewName;
    button.classList.toggle('is-active', active);
    if (button.closest('nav')) {
      button.setAttribute('aria-current', active ? 'page' : 'false');
    }
  });

  const main = document.getElementById('main-content');
  if (main) main.scrollTop = 0;
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add('is-visible');
  toastTimer = window.setTimeout(function () {
    toast.classList.remove('is-visible');
  }, 2200);
}

viewButtons.forEach(function (button) {
  button.addEventListener('click', function () {
    showView(button.dataset.view);
  });
});

viewportButtons.forEach(function (button) {
  button.addEventListener('click', function () {
    const viewport = button.dataset.viewport;
    previewStage.dataset.preview = viewport;
    viewportButtons.forEach(function (candidate) {
      candidate.classList.toggle('is-active', candidate === button);
    });
    const viewportLabel = viewport === 'mobile' ? '390px 移动端' : '1440px 桌面端';
    showToast(viewport === 'fluid' ? '已切换为响应式预览' : '已切换为 ' + viewportLabel + '预览');
  });
});

document.querySelectorAll('button:not([data-view]):not([data-viewport])').forEach(function (button) {
  button.addEventListener('click', function () {
    showToast('这是方向评审稿，操作将在对应 M1 阶段接入');
  });
});

showView('agent');
