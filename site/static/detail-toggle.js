(() => {
  const storageKey = 'csarc-detail-level';
  const root = document.documentElement;
  const controls = document.querySelector('.detail-level-control');
  const audienceItems = document.querySelectorAll('[data-audience="maintainer"]');
  const languageLinks = document.querySelectorAll('.language-control a');
  const selectors = [
    '.config-guidance:not(.overview-detail)',
    '.tool-deferred',
    '.background-band',
    '.review-note-footer',
    '.reference',
    '.technical-detail'
  ].join(', ');

  document.querySelectorAll(selectors).forEach(detail => {
    if (detail.closest('.legacy-content')) return;
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
  const legacyDetails = document.querySelectorAll(
    selectors.split(', ').map(selector => `.legacy-content ${selector}`).join(', ')
  );
  const buttons = controls.querySelectorAll('[data-detail-level]');

  languageLinks.forEach(link => {
    link.addEventListener('click', () => {
      const destination = new URL(link.href, location.href);
      destination.hash = location.hash;
      link.href = destination.href;
    });
  });

  document.querySelectorAll('.similar-tools-slide').forEach(slide => {
    const tabs = [...slide.querySelectorAll('[data-similar-tools-tab]')];
    const toolPanels = [...slide.querySelectorAll('[data-similar-tools-panel]')];
    let selectedIndex = 0;

    function renderTab() {
      tabs.forEach((tab, index) => {
        tab.setAttribute('aria-selected', String(index === selectedIndex));
        tab.tabIndex = index === selectedIndex ? 0 : -1;
      });
      toolPanels.forEach((panel, index) => {
        panel.hidden = index !== selectedIndex;
      });
    }

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => {
        selectedIndex = index;
        renderTab();
      });
    });
    addEventListener('csarc:detail-level', event => {
      if (event.detail === 'simple' && selectedIndex !== 0) {
        selectedIndex = 0;
        renderTab();
      }
    });
    renderTab();
  });

  document.querySelectorAll('.legacy-content .config-guidance').forEach(guidance => {
    if (guidance.dataset.configDirect === 'true') return;
    const actions = guidance.querySelector('.config-actions');
    const triggers = actions ? [...actions.querySelectorAll('.config-trigger')] : [];
    const overlay = triggers[0]
      ? document.getElementById(triggers[0].getAttribute('aria-controls'))
      : null;
    const card = overlay?.querySelector('.config-overlay-card');
    if (!actions || !triggers.length || !overlay || !card) return;

    guidance.classList.add('config-guidance--paged');
    actions.remove();

    const launcher = document.createElement('button');
    launcher.type = 'button';
    launcher.className = 'config-trigger config-tour-trigger';
    launcher.setAttribute('aria-expanded', 'false');
    launcher.setAttribute('aria-controls', overlay.id);
    launcher.innerHTML = `<span class="config-trigger-title">開啟維運設定</span><span class="config-trigger-file">${triggers.length} 項</span><span class="config-trigger-summary">在同一視窗逐項查看設定檔、目的與範例。</span>`;
    guidance.append(launcher);

    overlay.classList.add('config-overlay--paged');
    overlay.setAttribute('aria-label', '設定實作導覽');

    const close = card.querySelector('.config-overlay-close');
    const stage = document.createElement('div');
    stage.className = 'config-overlay-stage';
    [...card.children].filter(child => child !== close).forEach(child => stage.append(child));

    const pager = document.createElement('nav');
    pager.className = 'config-overlay-pager';
    pager.setAttribute('aria-label', '設定項目切換');
    const previous = document.createElement('button');
    previous.type = 'button';
    previous.textContent = '← 上一項';
    const status = document.createElement('output');
    status.setAttribute('aria-live', 'polite');
    const next = document.createElement('button');
    next.type = 'button';
    next.textContent = '下一項 →';
    pager.append(previous, status, next);
    card.append(stage, pager);

    function currentIndex() {
      const value = Number(overlay.dataset.itemIndex);
      return Number.isInteger(value) ? value : 0;
    }

    function updatePager(index) {
      previous.disabled = index === 0;
      next.disabled = index === triggers.length - 1;
      status.value = `${index + 1} / ${triggers.length}`;
      status.textContent = `${index + 1} / ${triggers.length}`;
    }

    function showPage(index, direction = 1) {
      if (index < 0 || index >= triggers.length) return;
      triggers[index].click();
      launcher.setAttribute('aria-expanded', 'true');
      updatePager(index);
      if (!matchMedia('(prefers-reduced-motion: reduce)').matches && stage.animate) {
        stage.animate(
          [
            { opacity: .35, transform: `translateX(${direction * 12}px)` },
            { opacity: 1, transform: 'translateX(0)' }
          ],
          { duration: 180, easing: 'ease-out' }
        );
      }
    }

    launcher.addEventListener('click', () => {
      if (!overlay.hidden) {
        close.click();
        return;
      }
      showPage(currentIndex());
    });
    previous.addEventListener('click', () => showPage(currentIndex() - 1, -1));
    next.addEventListener('click', () => showPage(currentIndex() + 1));
    close.addEventListener('click', () => launcher.setAttribute('aria-expanded', 'false'));
    new MutationObserver(() => {
      launcher.setAttribute('aria-expanded', String(!overlay.hidden));
    }).observe(overlay, { attributes: true, attributeFilter: ['hidden'] });
    updatePager(0);
  });

  const supplementalGuides = {
    deploy: '版本範圍、SemVer 與發布邊界',
    governance: '部署原則、方案行為與參考資料'
  };

  Object.entries(supplementalGuides).forEach(([track, summary]) => {
    const slide = document.querySelector(`.legacy-slide[data-track="${track}"]`);
    const legacy = slide?.querySelector(':scope > .legacy-content');
    if (!slide || !legacy) return;

    let foundPrimaryContext = false;
    const supplements = [...legacy.children].filter(element => {
      if (element.classList.contains('context-line')) {
        if (!foundPrimaryContext) {
          foundPrimaryContext = true;
          return false;
        }
        return track === 'deploy';
      }
      return element.matches('.selection-note, .decision-register, .reference');
    });
    if (!supplements.length) return;

    const launcher = document.createElement('button');
    launcher.type = 'button';
    launcher.className = 'config-trigger config-tour-trigger technical-tour-trigger';
    launcher.setAttribute('aria-expanded', 'false');
    launcher.innerHTML = `<span class="config-trigger-title">開啟維運附錄</span><span class="config-trigger-file">${supplements.length} 頁</span><span class="config-trigger-summary">${summary}</span>`;

    const overlay = document.createElement('aside');
    overlay.id = `technical-overlay-${track}`;
    overlay.className = 'config-overlay config-overlay--paged technical-supplement-overlay';
    overlay.hidden = true;
    overlay.setAttribute('role', 'region');
    overlay.setAttribute('aria-label', '維運附錄導覽');
    launcher.setAttribute('aria-controls', overlay.id);

    const card = document.createElement('div');
    card.className = 'config-overlay-card';
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'config-overlay-close';
    close.setAttribute('aria-label', '關閉維運附錄');
    close.textContent = '×';
    const stage = document.createElement('div');
    stage.className = 'config-overlay-stage';
    const pages = supplements.map((supplement, index) => {
      const page = document.createElement('div');
      page.className = 'technical-supplement-page';
      page.hidden = index !== 0;
      page.append(supplement);
      stage.append(page);
      return page;
    });

    const pager = document.createElement('nav');
    pager.className = 'config-overlay-pager';
    pager.setAttribute('aria-label', '維運附錄切換');
    const previous = document.createElement('button');
    previous.type = 'button';
    previous.textContent = '← 上一頁';
    const status = document.createElement('output');
    status.setAttribute('aria-live', 'polite');
    const next = document.createElement('button');
    next.type = 'button';
    next.textContent = '下一頁 →';
    pager.append(previous, status, next);
    card.append(close, stage, pager);
    overlay.append(card);
    slide.append(overlay);

    const guidance = legacy.querySelector('.config-guidance');
    (guidance || legacy.querySelector('.decision-strip, .plan-grid')).after(launcher);

    let current = 0;
    function showPage(index, direction = 1) {
      if (index < 0 || index >= pages.length) return;
      current = index;
      pages.forEach((page, pageIndex) => {
        page.hidden = pageIndex !== current;
      });
      previous.disabled = current === 0;
      next.disabled = current === pages.length - 1;
      status.value = `${current + 1} / ${pages.length}`;
      status.textContent = `${current + 1} / ${pages.length}`;
      if (!matchMedia('(prefers-reduced-motion: reduce)').matches && stage.animate) {
        stage.animate(
          [
            { opacity: .35, transform: `translateX(${direction * 12}px)` },
            { opacity: 1, transform: 'translateX(0)' }
          ],
          { duration: 180, easing: 'ease-out' }
        );
      }
    }

    launcher.addEventListener('click', () => {
      const shouldOpen = overlay.hidden;
      document.querySelectorAll('.config-overlay').forEach(item => {
        item.hidden = true;
      });
      overlay.hidden = !shouldOpen;
      launcher.setAttribute('aria-expanded', String(shouldOpen));
      if (shouldOpen) showPage(current);
    });
    previous.addEventListener('click', () => showPage(current - 1, -1));
    next.addEventListener('click', () => showPage(current + 1));
    close.addEventListener('click', () => {
      overlay.hidden = true;
      launcher.setAttribute('aria-expanded', 'false');
    });
    new MutationObserver(() => {
      launcher.setAttribute('aria-expanded', String(!overlay.hidden));
    }).observe(overlay, { attributes: true, attributeFilter: ['hidden'] });
    showPage(0);
  });

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
    legacyDetails.forEach(detail => {
      detail.hidden = simple;
      detail.inert = simple;
      detail.setAttribute('aria-hidden', String(simple));
    });
    audienceItems.forEach(item => {
      item.hidden = simple;
      item.inert = simple;
    });
    if (!simple) {
      document.querySelectorAll('.config-guidance-fold').forEach(detail => {
        detail.open = true;
      });
    }
    if (simple) {
      document.querySelectorAll('.config-overlay').forEach(overlay => {
        overlay.hidden = true;
      });
    }
    dispatchEvent(new CustomEvent('csarc:detail-level', { detail: selected }));
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
