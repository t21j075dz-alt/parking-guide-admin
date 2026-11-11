/* 表示・導線のみ。既存要素のID、認証、保存、公開条件を維持する。 */
(() => {
  "use strict";
  const tools = document.querySelector('#admin-tools-panel');
  if (!tools) return;
  const en = () => document.documentElement.lang.startsWith('en');
  const t = (ja, english) => en() ? english : ja;
  const closeButtons = [];
  for (const [panelId, toggleId] of [['admin-tools-panel', 'admin-tools-toggle'], ['admin-settings-panel', 'admin-settings-toggle']]) {
    const panel = document.getElementById(panelId);
    if (!panel) continue;
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'workspace-panel-close';
    close.id = panelId + '-close';
    close.addEventListener('click', () => {
      const toggle = document.getElementById(toggleId);
      toggle.click(); toggle.focus();
    });
    panel.prepend(close); closeButtons.push(close);
  }
  const search = document.createElement('input');
  search.type = 'search'; search.id = 'admin-tool-search';
  const label = document.createElement('label');
  label.htmlFor = search.id;
  const empty = document.createElement('p');
  empty.hidden = true; empty.setAttribute('role', 'status');
  const box = document.createElement('div'); box.className = 'tool-search';
  box.append(label, search, empty);
  tools.querySelector('.admin-tool-controls').after(box);
  const sections = [...tools.querySelectorAll(':scope > details')];
  const previous = new Map();
  function filter() {
    const query = search.value.trim().toLocaleLowerCase();
    for (const section of sections) {
      if (query && !previous.has(section)) previous.set(section, section.open);
      section.hidden = !!query && !section.textContent.toLocaleLowerCase().includes(query);
      if (query && !section.hidden) section.open = true;
      if (!query && previous.has(section)) { section.open = previous.get(section); previous.delete(section); }
    }
    empty.hidden = !query || sections.some(section => !section.hidden);
  }
  search.addEventListener('input', filter);
  search.addEventListener('keydown', event => {
    if (event.key === 'Escape' && search.value) {
      event.preventDefault(); event.stopPropagation(); search.value = ''; filter();
    }
  });
  // ショートカットは検索結果にかかわらず目的の設定を表示する。
  document.querySelector('.admin-camera-shortcuts')?.addEventListener('click', () => {
    search.value = ''; filter();
  }, true);
  // 一般的な説明は補足へ。動的な状態・警告や入力条件は元の位置を保つ。
  for (const id of ['camera-monitor', 'live-monitor-panel', 'camera-map-alignment-tools']) {
    const panel = document.getElementById(id);
    if (!panel) continue;
    const notes = [...panel.querySelectorAll(':scope > p:not([id]):not([role])')];
    if (!notes.length) continue;
    const details = document.createElement('details'); details.className = 'workspace-help';
    const summary = document.createElement('summary');
    details.append(summary, ...notes); panel.append(details);
  }
  const cloud = document.getElementById('admin-cloud-summary');
  if (cloud) {
    cloud.tabIndex = 0; cloud.setAttribute('role', 'button');
    const open = () => {
      search.value = ''; filter();
      if (document.body.dataset.adminToolsOpen !== 'true') document.getElementById('admin-tools-toggle').click();
      const target = document.getElementById('cloud-sync-status')?.closest('details');
      if (target) { target.open = true; target.scrollIntoView({block:'nearest'}); target.querySelector('summary').focus(); }
    };
    cloud.addEventListener('click', open);
    cloud.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } });
  }
  function language() {
    closeButtons.forEach(button => button.textContent = t('閉じる', 'Close'));
    label.textContent = t('機能を探す', 'Find a tool');
    search.placeholder = t('区画・営業時間・カメラなど', 'Spaces, opening hours, camera…');
    empty.textContent = t('該当する機能がありません。検索語を変えてください。', 'No matching tools. Try another search.');
    document.querySelectorAll('.workspace-help > summary').forEach(node => node.textContent = t('使い方・注意事項', 'Help and notes'));
    filter();
  }
  new MutationObserver(language).observe(document.documentElement, {attributes:true, attributeFilter:['lang']});
  language();
})();
