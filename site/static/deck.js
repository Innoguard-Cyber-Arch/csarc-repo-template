(() => {
  const allSlides = [...document.querySelectorAll('.slide')];
  const previous = document.querySelector('#previous');
  const next = document.querySelector('#next');
  const counter = document.querySelector('#counter');
  const bar = document.querySelector('#bar');
  const zoomOut = document.querySelector('#zoom-out');
  const zoomReset = document.querySelector('#zoom-reset');
  const zoomIn = document.querySelector('#zoom-in');
  const zoomLevel = document.querySelector('#zoom-level');
  const slideControls = document.querySelector('.controls');
  const viewControls = document.querySelector('.view-controls');
  const progress = document.querySelector('.progress');
  const navToggle = document.querySelector('#nav-toggle');
  let current = 0;
  let zoom = 1;
  let slides = [];

  function refreshSlides() {
    const maintenance = document.documentElement.dataset.detailLevel === 'technical';
    slides = allSlides.filter(slide => slide.dataset.audience !== 'archive' && (slide.dataset.audience !== 'maintainer' || maintenance));
    allSlides.forEach(slide => slide.removeAttribute('data-page'));
    slides.forEach((slide, index) => {
      slide.dataset.page = `${String(index + 1).padStart(2, '0')} / ${slides.length}`;
    });
  }

  function closeDisclosures() {
    document.querySelectorAll('.package-disclosure[open]').forEach(disclosure => {
      disclosure.open = false;
    });
  }

  function indexFromHash() {
    const value = location.hash.slice(1);
    const target = document.getElementById(value);
    if (target) {
      const targetIndex = slides.indexOf(target.closest('.slide'));
      return targetIndex < 0 ? 0 : targetIndex;
    }
    return Number(value) - 1 || 0;
  }

  function show(index, updateHash = true) {
    refreshSlides();
    closeDisclosures();
    document.querySelectorAll('.config-overlay').forEach(overlay => {
      overlay.hidden = true;
    });
    document.querySelectorAll('[aria-expanded="true"]').forEach(trigger => {
      trigger.setAttribute('aria-expanded', 'false');
    });
    current = Math.max(0, Math.min(slides.length - 1, index));
    allSlides.forEach(slide => {
      const slideIndex = slides.indexOf(slide);
      const active = slideIndex === current;
      slide.classList.toggle('active', active);
      slide.setAttribute('aria-hidden', String(!active));
    });
    counter.textContent = `${current + 1} / ${slides.length}`;
    bar.style.width = `${((current + 1) / slides.length) * 100}%`;
    previous.disabled = current === 0;
    next.disabled = current === slides.length - 1;
    // Issue #681/#682 UX review, P2: write the slide's own id, not its
    // numeric position, so a shared link keeps resolving to the same
    // content -- standard and ops modes hide a different set of slides
    // (refreshSlides() above), so the same slide sits at a different
    // number in each, and a numeric hash saved from one mode could open
    // the wrong slide in the other.
    if (updateHash) history.replaceState(null, '', `#${slides[current].id}`);
    // window.csarcMermaidRun() (defined in the mermaid init script, only
    // once a mermaid block actually appears on this page) renders any
    // `.mermaid` block that is visible now and not yet processed --
    // including one in this slide that just became `.active` and so was
    // still hidden the last time it ran. See that script for why a
    // visibility filter is required here instead of a plain
    // `mermaid.run()`.
    if (typeof window.csarcMermaidRun === 'function') window.csarcMermaidRun();
  }

  function fit() {
    const narrow = innerWidth <= 640;
    const scale = narrow ? .68 : Math.min(innerWidth / 1600, innerHeight / 900);
    document.documentElement.classList.toggle('narrow-screen', narrow);
    document.documentElement.style.setProperty('--deck-scale', Math.max(.1, scale * zoom));
    zoomLevel.textContent = `${Math.round(zoom * 100)}%`;
    zoomOut.disabled = zoom <= .6;
    zoomIn.disabled = zoom >= 1;
  }

  function setZoom(value) {
    zoom = Math.max(.6, Math.min(1, value));
    fit();
  }

  document.querySelectorAll('.package-disclosure').forEach(disclosure => {
    disclosure.addEventListener('toggle', () => {
      if (!disclosure.open) return;
      document.querySelectorAll('.package-disclosure[open]').forEach(other => {
        if (other !== disclosure) other.open = false;
      });
    });
  });
  previous.addEventListener('click', () => show(current - 1));
  next.addEventListener('click', () => show(current + 1));
  zoomOut.addEventListener('click', () => setZoom(zoom - .1));
  zoomReset.addEventListener('click', () => setZoom(1));
  zoomIn.addEventListener('click', () => setZoom(zoom + .1));
  addEventListener('resize', fit);
  addEventListener('hashchange', () => show(indexFromHash(), false));
  addEventListener('csarc:detail-level', () => {
    const activeSlide = document.querySelector('.slide.active');
    refreshSlides();
    const activeIndex = slides.indexOf(activeSlide);
    const fallbackSlide = activeSlide?.id === 'testing'
      ? document.querySelector('#similar-tools')
      : document.querySelector('#ecosystem');
    const fallbackIndex = slides.indexOf(fallbackSlide);
    show(activeIndex >= 0 ? activeIndex : Math.max(0, fallbackIndex));
  });
  addEventListener('keydown', event => {
    if (event.target.closest('summary, button, a, input, textarea, select')) return;
    if (['ArrowRight', 'PageDown', ' '].includes(event.key)) show(current + 1);
    if (['ArrowLeft', 'PageUp'].includes(event.key)) show(current - 1);
  });

  // Issue #681/#682 UX review, P0: on a narrow screen (styles.css's
  // `html.narrow-screen` rules) the always-visible journey rail becomes
  // an off-canvas drawer instead, opened by this button and by no other
  // means -- there is no hover state on touch to reveal a persistent
  // sidebar. `nav-open` on <html> is the single source of truth for
  // whether it is showing.
  function setNavOpen(open) {
    document.documentElement.classList.toggle('nav-open', open);
    navToggle.setAttribute('aria-expanded', String(open));
  }
  navToggle.addEventListener('click', () => {
    setNavOpen(!document.documentElement.classList.contains('nav-open'));
  });
  document.addEventListener('click', event => {
    if (!document.documentElement.classList.contains('nav-open')) return;
    if (event.target.closest('.journey-rail, #nav-toggle')) return;
    setNavOpen(false);
  });
  addEventListener('keydown', event => {
    if (event.key === 'Escape') setNavOpen(false);
  });
  addEventListener('hashchange', () => setNavOpen(false));

  refreshSlides();
  fit();
  show(indexFromHash(), !location.hash);
  slideControls.hidden = false;
  viewControls.hidden = false;
  progress.hidden = false;
})();
