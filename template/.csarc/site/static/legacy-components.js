(() => {
    // Generated repo-sites only need the shared copy-button behavior. The
    // template intentionally omits the root site's setup-command overlays.
    const lang = document.documentElement.lang.startsWith('en') ? 'en' : 'zh-tw';
    const uiText = lang === 'en'
      ? {
          copied: 'Copied',
          copyFailedShort: 'Copy failed',
          copyFailed: 'Copy failed — select the text above and copy it by hand.'
        }
      : {
          copied: '已複製',
          copyFailedShort: '複製失敗',
          copyFailed: '複製失敗，請自行選取上方文字複製。'
        };

    // Issue #681/#682: a single shared `aria-live` region announces every
    // copy outcome. The sibling `<pre>` is the visible source of copied text.
    let copyStatusRegion = document.getElementById('copy-status-region');
    if (!copyStatusRegion) {
      copyStatusRegion = document.createElement('div');
      copyStatusRegion.id = 'copy-status-region';
      copyStatusRegion.className = 'sr-only';
      copyStatusRegion.setAttribute('role', 'status');
      copyStatusRegion.setAttribute('aria-live', 'polite');
      document.body.append(copyStatusRegion);
    }
    function announceCopyStatus(message) {
      copyStatusRegion.textContent = '';
      requestAnimationFrame(() => { copyStatusRegion.textContent = message; });
    }
    function copyCommandText(text, button) {
      const restore = button.textContent;
      const onCopied = () => {
        button.textContent = uiText.copied;
        button.classList.remove('copy-command-failed');
        announceCopyStatus(uiText.copied);
        setTimeout(() => { button.textContent = restore; }, 1500);
      };
      const onFailed = () => {
        button.textContent = uiText.copyFailedShort;
        button.classList.add('copy-command-failed');
        announceCopyStatus(uiText.copyFailed);
        setTimeout(() => {
          button.textContent = restore;
          button.classList.remove('copy-command-failed');
        }, 3000);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(onCopied, () => copyCommandTextFallback(text, onCopied, onFailed));
      } else {
        copyCommandTextFallback(text, onCopied, onFailed);
      }
    }
    function copyCommandTextFallback(text, onCopied, onFailed) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.append(textarea);
      textarea.select();
      try {
        if (document.execCommand('copy')) onCopied();
        else onFailed();
      } catch {
        onFailed();
      }
      textarea.remove();
    }
    document.addEventListener('click', event => {
      const button = event.target.closest('.copy-command');
      if (!button) return;
      const block = button.closest('.command-block');
      const text = button.dataset.copyText ?? block?.querySelector('pre')?.textContent ?? '';
      if (text) copyCommandText(text, button);
    });
})();
