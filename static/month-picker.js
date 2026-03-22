/**
 * Custom Month Picker Widget
 * Replaces native <input type="month"> with a styled Bootstrap-compatible dropdown.
 * Usage: add class "month-picker" to a wrapper div with data-value="YYYY-MM",
 *        data-name="input_name", and optionally data-min="YYYY-MM".
 */
(function () {
  'use strict';

  const MONTHS_UK = [
    'Січень','Лютий','Березень','Квітень',
    'Травень','Червень','Липень','Серпень',
    'Вересень','Жовтень','Листопад','Грудень'
  ];

  function parseYM(str) {
    if (!str) return null;
    const parts = str.split('-');
    if (parts.length < 2) return null;
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    if (isNaN(y) || isNaN(m) || m < 1 || m > 12) return null;
    return { year: y, month: m };
  }

  function formatYM(year, month) {
    return `${year}-${String(month).padStart(2, '0')}`;
  }

  function initPicker(wrap) {
    const now = new Date();
    const rawValue = wrap.dataset.value || formatYM(now.getFullYear(), now.getMonth() + 1);
    const rawMin   = wrap.dataset.min   || null;

    let selected = parseYM(rawValue) || { year: now.getFullYear(), month: now.getMonth() + 1 };
    let minYM    = parseYM(rawMin);
    let displayYear = selected.year;

    // Hidden input (carries the value with the form submission)
    const hiddenInput = wrap.querySelector('.mp-hidden-input');
    hiddenInput.value = formatYM(selected.year, selected.month);

    // Toggle button label
    const labelEl = wrap.querySelector('.mp-label');

    // Panel
    const panel = wrap.querySelector('.month-picker-panel');

    // Year nav elements (created once)
    const yearNav = document.createElement('div');
    yearNav.className = 'mp-year-nav';

    const prevYearBtn = document.createElement('button');
    prevYearBtn.type = 'button';
    prevYearBtn.className = 'mp-year-btn';
    prevYearBtn.innerHTML = '<i class="bi bi-chevron-left"></i>';

    const yearLabel = document.createElement('span');
    yearLabel.className = 'mp-year-label';

    const nextYearBtn = document.createElement('button');
    nextYearBtn.type = 'button';
    nextYearBtn.className = 'mp-year-btn';
    nextYearBtn.innerHTML = '<i class="bi bi-chevron-right"></i>';

    yearNav.appendChild(prevYearBtn);
    yearNav.appendChild(yearLabel);
    yearNav.appendChild(nextYearBtn);

    // Month grid container
    const grid = document.createElement('div');
    grid.className = 'mp-month-grid';

    panel.appendChild(yearNav);
    panel.appendChild(grid);

    function updateLabel() {
      labelEl.textContent = `${MONTHS_UK[selected.month - 1]} ${selected.year}`;
    }

    function renderGrid() {
      yearLabel.textContent = displayYear;

      // Disable prev-year button if it would go below minYM year
      if (minYM && displayYear <= minYM.year) {
        prevYearBtn.disabled = true;
        prevYearBtn.style.opacity = '0.3';
      } else {
        prevYearBtn.disabled = false;
        prevYearBtn.style.opacity = '';
      }

      grid.innerHTML = '';
      for (let m = 1; m <= 12; m++) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'mp-month-btn';
        btn.textContent = MONTHS_UK[m - 1];

        // Disabled if before minYM
        if (minYM && (displayYear < minYM.year || (displayYear === minYM.year && m < minYM.month))) {
          btn.disabled = true;
          btn.classList.add('disabled');
        }

        // Active if this is the selected month
        if (displayYear === selected.year && m === selected.month) {
          btn.classList.add('active');
        }

        btn.addEventListener('click', function () {
          selected = { year: displayYear, month: m };
          hiddenInput.value = formatYM(selected.year, selected.month);
          updateLabel();
          closePanel();
        });

        grid.appendChild(btn);
      }
    }

    function openPanel() {
      displayYear = selected.year;
      renderGrid();
      panel.classList.remove('d-none');
      wrap.querySelector('.mp-chevron').style.transform = 'rotate(180deg)';
    }

    function closePanel() {
      panel.classList.add('d-none');
      wrap.querySelector('.mp-chevron').style.transform = '';
    }

    function togglePanel() {
      if (panel.classList.contains('d-none')) {
        // Close all other open pickers first
        document.querySelectorAll('.month-picker-panel:not(.d-none)').forEach(p => {
          p.classList.add('d-none');
          const chev = p.closest('.month-picker').querySelector('.mp-chevron');
          if (chev) chev.style.transform = '';
        });
        openPanel();
      } else {
        closePanel();
      }
    }

    // Wire toggle button
    wrap.querySelector('.month-picker-toggle').addEventListener('click', togglePanel);

    // Year navigation
    prevYearBtn.addEventListener('click', function () {
      if (!minYM || displayYear > minYM.year) {
        displayYear--;
        renderGrid();
      }
    });
    nextYearBtn.addEventListener('click', function () {
      displayYear++;
      renderGrid();
    });

    // Close on outside click
    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) {
        closePanel();
      }
    });

    // Initial label
    updateLabel();
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.month-picker').forEach(initPicker);
  });
})();
