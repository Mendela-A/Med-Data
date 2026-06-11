/*
 * Спільні функції експорту/друку для сторінок записів (/records, /ambulatory).
 *
 * Шаблон перед підключенням цього файлу задає конфіг:
 *   window.RecordsExportConfig = {
 *     exportUrl:    "...",                  // POST-ендпоінт експорту в Excel
 *     printUrl:     "...",                  // POST-ендпоінт друку PDF
 *     filterFields: ['discharge_status', ...] // name-атрибути фільтрів на сторінці
 *   };
 */
(function (global) {
  'use strict';

  function getConfig() {
    return global.RecordsExportConfig || {};
  }

  // Діапазон дат обраного місяця (або поточного, якщо фільтр порожній)
  function monthRange() {
    const monthInput = document.querySelector('input[name="month_filter"]');
    let year, month;
    if (monthInput && monthInput.value) {
      const parts = monthInput.value.split('-');
      year = parseInt(parts[0], 10);
      month = parseInt(parts[1], 10);
    } else {
      const today = new Date();
      year = today.getFullYear();
      month = today.getMonth() + 1;
    }
    const mm = String(month).padStart(2, '0');
    const lastDay = new Date(year, month, 0).getDate();
    return {
      from: `${year}-${mm}-01`,
      to: `${year}-${mm}-${String(lastDay).padStart(2, '0')}`
    };
  }

  // Поточні значення фільтрів сторінки + діапазон дат місяця
  function collectFields() {
    const range = monthRange();
    const fields = {
      export_mode: 'range',
      from_date: range.from,
      to_date: range.to
    };
    (getConfig().filterFields || []).forEach(function (name) {
      const el = document.querySelector(`select[name="${name}"], input[name="${name}"]`);
      fields[name] = el ? el.value : '';
    });
    return fields;
  }

  function buildAndSubmitForm(action, fields, newTab) {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = action;
    if (newTab) form.target = '_blank';
    if (typeof global.addCSRFToForm === 'function') global.addCSRFToForm(form);
    for (const [name, value] of Object.entries(fields)) {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = name;
      input.value = value;
      form.appendChild(input);
    }
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
  }

  // Швидкий експорт в Excel з поточними фільтрами
  global.quickExportRecords = function () {
    buildAndSubmitForm(getConfig().exportUrl, collectFields(), false);
  };

  // Друк PDF з поточними фільтрами (відкривається в новій вкладці)
  global.printRecords = function () {
    showPrintToast('Формування PDF документу...', 'info');
    buildAndSubmitForm(getConfig().printUrl, collectFields(), true);
  };

  // Тост-повідомлення (контейнер #printToastContainer має бути на сторінці)
  function showPrintToast(message, type) {
    const toastContainer = document.getElementById('printToastContainer');
    if (!toastContainer) return;

    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'success' ? 'bg-success' : type === 'info' ? 'bg-info' : 'bg-warning';
    const icon = type === 'success' ? 'check-circle' : type === 'info' ? 'hourglass-split' : 'exclamation-circle';

    const toastHtml = `
      <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="d-flex">
          <div class="toast-body">
            <i class="bi bi-${icon} me-2"></i>
            ${message}
          </div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
      </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, {
      autohide: true,
      delay: type === 'info' ? 2000 : 3000
    });
    toast.show();

    toastElement.addEventListener('hidden.bs.toast', function () {
      toastElement.remove();
    });
  }

  global.showPrintToast = showPrintToast;
})(window);
