/* Form 007 live-sync.
 *
 * Polls a cheap "revision" fingerprint of the day's / month's DailyReport rows.
 * Config comes from data-* on the #f007-live marker element:
 *   data-revision-url  — endpoint returning {"revision": "..."}
 *   data-revision      — fingerprint rendered with the page
 *   data-mode          — "reload" (read-only views) | "banner" (edit view)
 *
 * reload: another operator saved -> refresh the page automatically.
 * banner: another operator saved -> show a dismissible banner (never auto-reload,
 *         so the operator's typed-in values are not thrown away without a choice).
 */
(function () {
  var el = document.getElementById('f007-live');
  if (!el || !window.fetch) return;

  var url = el.dataset.revisionUrl;
  var current = el.dataset.revision || '';
  var mode = el.dataset.mode || 'reload';
  var INTERVAL = 20000;
  var stopped = false;

  function showBanner() {
    if (document.getElementById('f007-live-banner')) return;
    var bar = document.createElement('div');
    bar.id = 'f007-live-banner';
    bar.setAttribute('role', 'alert');
    bar.className = 'alert alert-warning d-flex align-items-center justify-content-between shadow';
    bar.style.cssText = 'position:fixed;left:1rem;right:1rem;bottom:1rem;z-index:1080;margin:0;';
    bar.innerHTML =
      '<span><i class="bi bi-exclamation-triangle me-2"></i>' +
      'Інший оператор зберіг зміни Форми 007 за цю дату. Перезавантажте сторінку, ' +
      'щоб бачити актуальні дані — незбережені зміни в цій формі буде втрачено.</span>' +
      '<span class="ms-3 text-nowrap">' +
      '<button type="button" class="btn btn-sm btn-warning me-2" id="f007-live-reload">Перезавантажити</button>' +
      '<button type="button" class="btn-close" aria-label="Закрити" id="f007-live-dismiss"></button>' +
      '</span>';
    document.body.appendChild(bar);
    document.getElementById('f007-live-reload').addEventListener('click', function () {
      window.location.reload();
    });
    document.getElementById('f007-live-dismiss').addEventListener('click', function () {
      bar.remove();
    });
  }

  function tick() {
    if (stopped || document.hidden || !url) return;
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.revision) return;
        if (!current) { current = data.revision; return; }
        if (data.revision === current) return;
        if (mode === 'banner') {
          showBanner();
          stopped = true;            // one notice is enough
        } else {
          window.location.reload();
        }
      })
      .catch(function () { /* transient network / auth error — try again next tick */ });
  }

  setInterval(tick, INTERVAL);
})();
