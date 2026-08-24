(() => {
  const slides = [...document.querySelectorAll('.slide')];
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

  slides.forEach((slide, index) => {
    slide.dataset.page = `${String(index + 1).padStart(2, '0')} / ${slides.length}`;
  });

  function closeDisclosures() {
    document.querySelectorAll('.package-disclosure[open]').forEach(disclosure => {
      disclosure.open = false;
    });
  }

  function indexFromHash() {
    const value = location.hash.slice(1);
    const target = document.getElementById(value);
    if (target) return slides.indexOf(target.closest('.slide'));
    return Number(value) - 1 || 0;
  }

  function show(index, updateHash = true) {
    closeDisclosures();
    current = Math.max(0, Math.min(slides.length - 1, index));
    slides.forEach((slide, slideIndex) => {
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
  addEventListener('keydown', event => {
    if (event.target.closest('summary, button, a, input, textarea, select')) return;
    if (['ArrowRight', 'PageDown', ' '].includes(event.key)) show(current + 1);
    if (['ArrowLeft', 'PageUp'].includes(event.key)) show(current - 1);
  });

  fit();
  show(indexFromHash(), !location.hash);
  slideControls.hidden = false;
  viewControls.hidden = false;
  progress.hidden = false;
})();
