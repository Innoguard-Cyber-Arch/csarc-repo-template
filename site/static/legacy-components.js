(() => {
    const setupExamples = {
      new: {
        title: '建立新 repo',
        goal: 'CLI 會選取核准 release、解析完整 commit SHA、顯示計畫，確認後才以 Copier 建立與驗證。',
        location: 'Terminal',
        code: `uvx --from csarc-repo-cli csarc init ./my-project

# CI or an explicitly authorized agent:
uvx --from csarc-repo-cli csarc init ./my-project \\
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
    };

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
    setupOverlay.setAttribute('aria-label', '導入與安裝指令');
    setupOverlay.innerHTML = `<div class="config-overlay-card"><button class="config-overlay-close" type="button" aria-label="關閉指令">×</button><h3></h3><p class="config-overlay-goal"></p><p class="config-overlay-path">執行位置：<code></code></p><pre class="code"></pre></div>`;
    capabilitySlide.append(setupOverlay);
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
        setupOverlay.querySelector('pre').textContent = setting.code;
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

    // Config-trigger / overlay content is now server-rendered by the
    // config-guidance Hugo shortcode (site/layouts/shortcodes/config-guidance.html)
    // from site/data/config_examples.json, in the page's own language. This
    // only wires open/close interaction on top of the data-* attributes that
    // shortcode already emitted; it no longer builds DOM from an in-memory
    // JS object. A `data-config-direct="true"` guidance block renders native
    // <details>/<summary> and needs no JS at all.
    document.querySelectorAll('.decision-slide .config-guidance:not([data-config-direct="true"]) .config-trigger').forEach(trigger => {
      const overlay = document.getElementById(trigger.getAttribute('aria-controls'));
      if (!overlay) return;
      const card = overlay.querySelector('.config-overlay-card');
      const heading = card.querySelector('h3');
      const goalField = card.querySelector('.config-overlay-goal');
      const fileField = card.querySelector('.config-overlay-path code');
      const codeField = card.querySelector('pre');

      trigger.addEventListener('click', () => {
        const index = trigger.dataset.configIndex;
        const isSameOpen = !overlay.hidden && overlay.dataset.itemIndex === index;
        closeConfigOverlays();
        if (isSameOpen) return;
        heading.textContent = trigger.dataset.configTitle;
        goalField.textContent = trigger.dataset.configGoal;
        fileField.textContent = trigger.dataset.configFile;
        // The shortcode HTML-escapes code and uses "&#10;" for newlines
        // (see config-guidance.html); the browser decodes that entity back
        // to a real newline when reading the attribute, so no JS unescaping
        // is needed here.
        codeField.textContent = trigger.dataset.configCode;
        overlay.dataset.itemIndex = index;
        overlay.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
      });
    });

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
