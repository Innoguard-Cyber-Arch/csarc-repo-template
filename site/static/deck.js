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
    if (updateHash) history.replaceState(null, '', `#${current + 1}`);
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

  refreshSlides();
  fit();
  show(indexFromHash(), !location.hash);
  slideControls.hidden = false;
  viewControls.hidden = false;
  progress.hidden = false;
})();
