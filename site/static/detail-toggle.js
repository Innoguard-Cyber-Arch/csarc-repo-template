(() => {
  const storageKey = 'csarc-detail-level';
  const root = document.documentElement;
  const controls = document.querySelector('.detail-level-control');
  const audienceItems = document.querySelectorAll('[data-audience="maintainer"]');
  const languageLinks = document.querySelectorAll('.language-control a');
  // Issue #525: technical-only content used to be revealed either by
  // wrapping it in a click-to-expand `.detail-panel` (an animated
  // grid-collapse) or, for config-guidance, a button plus modal overlay
  // with a pager -- both "inline expand box" patterns that squeezed
  // technical content into the same layout as the simple content and
  // left no room for images. Both are gone now: `.technical-detail`
  // (the {{< detail >}} shortcode's output) is shown or hidden directly
  // in its natural page position by detail-toggle.css's
  // `[data-detail-level]` rules alone, with no JS involved.
  // `.config-guidance` and the other technical-only elements below still
  // live inside `.legacy-content` and are shown/hidden directly (no
  // wrapping, no overlay) via the `legacyDetails` collection.
  const selectors = [
    '.config-guidance',
    '.tool-deferred',
    '.background-band',
    '.review-note-footer',
    '.reference'
  ].join(', ');

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

  const supplementalGuides = {
    deploy: '版本範圍、SemVer 與發布邊界',
    governance: '方案能力、治理設定與例外處理'
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
    legacyDetails.forEach(detail => {
      detail.hidden = simple;
      detail.inert = simple;
      detail.setAttribute('aria-hidden', String(simple));
    });
    audienceItems.forEach(item => {
      item.hidden = simple;
      item.inert = simple;
    });
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
