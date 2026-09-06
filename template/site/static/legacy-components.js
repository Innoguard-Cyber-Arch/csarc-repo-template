(() => {
    // Issue #681/#682 UX review, P1: the interactive hero (this file) used
    // to run on the zh-tw home page only -- the English home page fell
    // back to a flat, non-interactive body, so the two languages read as
    // different products. Both now share the same markup and this same
    // script; only the label/example text switches on page language.
    const lang = document.documentElement.lang.startsWith('en') ? 'en' : 'zh-tw';
    const setupExamplesByLang = {
      'zh-tw': {
        new: {
          title: '建立新 repo',
          goal: 'CLI 會選取核准 release、解析完整 commit SHA、顯示計畫，確認後才以 Copier 建立與驗證。',
          location: 'Terminal',
          code: `uvx --from csarc-repo-cli csarc init ./my-project`,
          ciCode: `uvx --from csarc-repo-cli csarc init ./my-project \\
  --yes --non-interactive`
        },
        existing: {
          title: '把公版導入既有 repo',
          goal: '先用 --dry-run 在 repo 外產生短版 Markdown 與一頁 PDF，預覽新增、覆寫、保留、人工合併與無法判定項目；必須是乾淨 Git working tree，預設保留產品內容。報告只描述已知風險，不保證沒有語意或執行期衝突。',
          location: '既有 repo 根目錄',
          code: `git switch -c chore/<issue-number>-adopt-csarc-template
uvx --from csarc-repo-cli csarc adopt . --dry-run \\
  --report-dir ../csarc-adoption-report
uvx --from csarc-repo-cli csarc adopt .`
        },
        update: {
          title: '更新已使用公版的 repo',
          goal: 'CLI 讀取 .csarc/config.yml，解析核准 release，以 Copier smart update 顯示新版差異；衝突時保留差異並 fail closed。',
          location: '專案 repo 根目錄',
          code: `git switch -c chore/<issue-number>-update-repo-template
uvx --from csarc-repo-cli csarc update --check --json
uvx --from csarc-repo-cli csarc update`
        },
        mac: {
          title: 'macOS 本機需求',
          goal: '共同安裝 Git、GitHub CLI、uv；選 TypeScript 再使用 Node 與 pnpm，選 Rust 再使用 rustup 與 Cargo。只有 GitHub 連線操作需要登入。',
          location: 'Terminal',
          code: `brew install git gh uv node pnpm

# Only for repository settings and GitHub end-to-end tests.
gh auth login -h github.com
gh auth status`
        },
        windows: {
          title: 'Windows 本機需求',
          goal: '採用 WSL2（Ubuntu）並在 WSL 裡操作 repo；選 TypeScript 再安裝 Node 24 與 pnpm 11，選 Rust 再安裝 rustup。',
          location: 'PowerShell（管理員）→ Ubuntu',
          code: `# PowerShell (Administrator)
wsl --install -d Ubuntu

# Ubuntu in WSL2
sudo apt update
sudo apt install -y git gh curl ca-certificates bash coreutils tar gawk libdigest-sha-perl
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pnpm@11.22.0

# Only for repository settings and GitHub end-to-end tests.
gh auth login -h github.com
gh auth status`
        }
      },
      en: {
        new: {
          title: 'Create a new repo',
          goal: 'The CLI selects the approved release, resolves the full commit SHA, shows the plan, and only then builds and verifies with Copier.',
          location: 'Terminal',
          code: `uvx --from csarc-repo-cli csarc init ./my-project`,
          ciCode: `uvx --from csarc-repo-cli csarc init ./my-project \\
  --yes --non-interactive`
        },
        existing: {
          title: 'Adopt the template into an existing repo',
          goal: 'A --dry-run run first produces a short Markdown report and a one-page PDF outside the repo, previewing additions, overwrites, kept content, manual-merge items, and anything it cannot classify; the working tree must be clean, and product content is kept by default. The report only describes known risk -- it does not guarantee there is no semantic or runtime conflict.',
          location: 'Existing repo root',
          code: `git switch -c chore/<issue-number>-adopt-csarc-template
uvx --from csarc-repo-cli csarc adopt . --dry-run \\
  --report-dir ../csarc-adoption-report
uvx --from csarc-repo-cli csarc adopt .`
        },
        update: {
          title: 'Update a repo already on the template',
          goal: 'The CLI reads .csarc/config.yml, resolves the approved release, and shows the diff with Copier smart update; a conflict keeps the difference and fails closed.',
          location: 'Project repo root',
          code: `git switch -c chore/<issue-number>-update-repo-template
uvx --from csarc-repo-cli csarc update --check --json
uvx --from csarc-repo-cli csarc update`
        },
        mac: {
          title: 'macOS local requirements',
          goal: 'Install Git, GitHub CLI, and uv either way; add Node and pnpm for TypeScript, or rustup and Cargo for Rust. Only GitHub-connected operations need you to sign in.',
          location: 'Terminal',
          code: `brew install git gh uv node pnpm

# Only for repository settings and GitHub end-to-end tests.
gh auth login -h github.com
gh auth status`
        },
        windows: {
          title: 'Windows local requirements',
          goal: 'Use WSL2 (Ubuntu) and work in the repo from inside WSL; add Node 24 and pnpm 11 for TypeScript, or rustup for Rust.',
          location: 'PowerShell (Administrator) -> Ubuntu',
          code: `# PowerShell (Administrator)
wsl --install -d Ubuntu

# Ubuntu in WSL2
sudo apt update
sudo apt install -y git gh curl ca-certificates bash coreutils tar gawk libdigest-sha-perl
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pnpm@11.22.0

# Only for repository settings and GitHub end-to-end tests.
gh auth login -h github.com
gh auth status`
        }
      }
    };
    const setupExamples = setupExamplesByLang[lang];
    const uiText = lang === 'en'
      ? {
          overlayLabel: 'Adoption and install commands',
          closeLabel: 'Close command',
          location: 'Run from: ',
          interactive: 'Interactive',
          ci: 'CI / already-authorized agent',
          copy: 'Copy',
          copied: 'Copied'
        }
      : {
          overlayLabel: '導入與安裝指令',
          closeLabel: '關閉指令',
          location: '執行位置：',
          interactive: '互動執行',
          ci: 'CI／已授權 agent',
          copy: '複製',
          copied: '已複製'
        };

    // Issue #681/#682 2026-09-06 redesign round: generic, not gated behind
    // the home-hero-only `capabilitySlide` check below, so any page's
    // `.command-block > .copy-command` works the same way -- e.g.
    // `install`'s standard-mode pane copies its full agent prompt from a
    // `data-copy-text` attribute without ever rendering that prompt as
    // visible body text (`data-copy-text` takes precedence over a sibling
    // `<pre>` when both exist). A downstream project's minimal repo-site
    // (Issue #681 decision N) has no `.capability-slide` at all, so this
    // would otherwise never run there.
    function copyCommandText(text, button) {
      const restore = button.textContent;
      const onCopied = () => {
        button.textContent = uiText.copied;
        setTimeout(() => { button.textContent = restore; }, 1500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(onCopied, () => copyCommandTextFallback(text, onCopied));
      } else {
        copyCommandTextFallback(text, onCopied);
      }
    }
    function copyCommandTextFallback(text, onCopied) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.append(textarea);
      textarea.select();
      try {
        if (document.execCommand('copy')) onCopied();
      } catch {
        // Clipboard unavailable in this context; the command text is
        // still visible in the <pre> for the reader to select by hand.
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

    const capabilitySlide = document.querySelector('.capability-slide');
    if (!capabilitySlide) return;

    function closeConfigOverlays() {
      document.querySelectorAll('.config-overlay').forEach(overlay => {
        overlay.hidden = true;
        overlay.removeAttribute('data-item-index');
      });
      document.querySelectorAll('.config-trigger[aria-expanded="true"], .setup-trigger[aria-expanded="true"], .term-trigger[aria-expanded="true"]').forEach(trigger => {
        trigger.setAttribute('aria-expanded', 'false');
      });
    }

    function closePackageDisclosures(except = null) {
      document.querySelectorAll('.package-disclosure[open]').forEach(detail => {
        if (detail !== except) detail.open = false;
      });
    }

    function closeBridgeDetails(except = null) {
      document.querySelectorAll('.bridge-detail[open]').forEach(detail => {
        if (detail !== except) detail.open = false;
      });
    }

    document.querySelectorAll('.package-disclosure').forEach(detail => {
      detail.addEventListener('toggle', () => {
        if (detail.open) closePackageDisclosures(detail);
      });
    });

    const setupOverlay = document.createElement('aside');
    setupOverlay.id = 'setup-overlay';
    setupOverlay.className = 'config-overlay';
    setupOverlay.hidden = true;
    setupOverlay.setAttribute('role', 'region');
    setupOverlay.setAttribute('aria-label', uiText.overlayLabel);
    setupOverlay.innerHTML = `<div class="config-overlay-card"><button class="config-overlay-close" type="button" aria-label="${uiText.closeLabel}">×</button><h3></h3><p class="config-overlay-goal"></p><p class="config-overlay-path">${uiText.location}<code></code></p><div class="command-block"><div class="command-block-head"><span class="command-block-label">${uiText.interactive}</span><button class="copy-command" type="button">${uiText.copy}</button></div><pre class="code"></pre></div><div class="command-block ci-block" hidden><div class="command-block-head"><span class="command-block-label">${uiText.ci}</span><button class="copy-command" type="button">${uiText.copy}</button></div><pre class="code"></pre></div></div>`;
    capabilitySlide.append(setupOverlay);

    // Issue #681/#682 UX review, P1: the same interactive command a
    // person runs by hand and the flag-laden variant CI or an already
    // authorized agent runs unattended used to sit in one <pre>, telling
    // readers apart by a code comment. `ciCode` (only set where the two
    // genuinely differ, e.g. "new") now renders in its own labeled block
    // instead.
    const [interactiveBlock, ciBlock] = setupOverlay.querySelectorAll('.command-block');

    capabilitySlide.querySelectorAll('.setup-trigger').forEach(trigger => {
      trigger.setAttribute('aria-controls', setupOverlay.id);
      trigger.addEventListener('click', () => {
        const key = trigger.dataset.setup;
        const setting = setupExamples[key];
        const isSameOpen = !setupOverlay.hidden && setupOverlay.dataset.itemIndex === key;
        closeConfigOverlays();
        if (!setting || isSameOpen) return;
        setupOverlay.querySelector('h3').textContent = setting.title;
        setupOverlay.querySelector('.config-overlay-goal').textContent = setting.goal;
        setupOverlay.querySelector('.config-overlay-path code').textContent = setting.location;
        interactiveBlock.querySelector('pre').textContent = setting.code;
        interactiveBlock.querySelector('.command-block-label').hidden = !setting.ciCode;
        ciBlock.hidden = !setting.ciCode;
        if (setting.ciCode) ciBlock.querySelector('pre').textContent = setting.ciCode;
        setupOverlay.dataset.itemIndex = key;
        setupOverlay.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
      });
    });
    setupOverlay.querySelector('.config-overlay-close').addEventListener('click', closeConfigOverlays);

    document.querySelectorAll('.term-trigger').forEach(trigger => {
      const overlay = document.querySelector(`#${trigger.getAttribute('aria-controls')}`);
      if (!overlay) return;
      trigger.addEventListener('click', () => {
        const isOpen = !overlay.hidden;
        closeConfigOverlays();
        if (isOpen) return;
        overlay.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
      });
      overlay.querySelector('.config-overlay-close').addEventListener('click', closeConfigOverlays);
    });

    // Issue #525: config-guidance content (site/data/config_examples.json,
    // rendered by render_config_guidance() in
    // scripts/build_repo_site.py) is now always a static block with
    // no click-to-reveal trigger of its own -- detail-toggle.css's
    // simple/technical toggle shows or hides the whole thing directly, so
    // this file no longer needs to wire up per-item overlay content for
    // it. The remaining `.config-overlay` instances below belong to the
    // unrelated setup-trigger/term-trigger widgets on the capability
    // slide, and to detail-toggle.js's own "維運附錄" overlay (which wires
    // its own close button already; this listener is a harmless no-op
    // duplicate for that one).
    document.querySelectorAll('.decision-slide .config-overlay .config-overlay-close').forEach(closeButton => {
      closeButton.addEventListener('click', closeConfigOverlays);
    });

    addEventListener('click', event => {
      if (!(event.target instanceof Element)) return;
      if (!event.target.closest('.package-disclosure')) closePackageDisclosures();
      if (!event.target.closest('.bridge-detail')) closeBridgeDetails();
      if (event.target.closest('.config-overlay-card, .config-trigger, .setup-trigger, .term-trigger')) return;
      closeConfigOverlays();
    });
})();
