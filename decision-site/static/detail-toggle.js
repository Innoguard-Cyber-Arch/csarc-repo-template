(() => {
  const storageKey = 'csarc-detail-level';
  const root = document.documentElement;
  const controls = document.querySelector('.detail-level-control');
  const selectors = [
    '.language-contract',
    '.product-prerequisites',
    '.config-guidance',
    '.tool-deferred',
    '.background-band',
    '.pipeline-foundation',
    '.repo-map-legend',
    '.review-note-footer',
    '.reference'
  ].join(', ');

  document.querySelectorAll(selectors).forEach(detail => {
    if (detail.closest('.package-disclosure')) return;
    const panel = document.createElement('div');
    const content = document.createElement('div');
    panel.className = 'detail-panel';
    panel.dataset.detail = 'technical';
    content.className = 'detail-panel__content';
    detail.before(panel);
    content.append(detail);
    panel.append(content);
  });

  const panels = document.querySelectorAll('.detail-panel');
  const buttons = controls.querySelectorAll('[data-detail-level]');

  function setDetailLevel(level, persist = true) {
    const selected = level === 'simple' ? 'simple' : 'technical';
    const simple = selected === 'simple';
    root.dataset.detailLevel = selected;
    buttons.forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.detailLevel === selected));
    });
    panels.forEach(panel => {
      panel.inert = simple;
      panel.setAttribute('aria-hidden', String(simple));
    });
    if (!persist) return;
    try {
      localStorage.setItem(storageKey, selected);
    } catch {}
  }

  controls.addEventListener('click', event => {
    const button = event.target.closest('[data-detail-level]');
    if (button) setDetailLevel(button.dataset.detailLevel);
  });

  setDetailLevel(root.dataset.detailLevel, false);
  controls.hidden = false;
})();
