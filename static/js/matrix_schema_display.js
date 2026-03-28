/**
 * Подписи уровней и колонок из window.__matrixColumnSchema
 * (effective_matrix_column_schema с сервера).
 */
(function (global) {
  'use strict';

  function schemaRows() {
    return Array.isArray(global.__matrixColumnSchema) ? global.__matrixColumnSchema : [];
  }

  function stripTagSuffix(header) {
    return String(header || '').replace(/\s*\([^)]*\)\s*$/i, '').trim();
  }

  /** Служебные label из БД (item_0, ITEM_01) — для UI берём текст из header. */
  function isPlaceholderItemLabel(s) {
    const t = String(s || '').trim().toLowerCase().replace(/\s+/g, '');
    if (!t) return true;
    return /^item_\d+$/.test(t);
  }

  function effectiveSchemaCaption(r) {
    if (!r) return '';
    const lab = String(r.label || '').trim();
    const hdr = String(r.header || '').trim();
    if (lab && !isPlaceholderItemLabel(lab)) return stripTagSuffix(lab);
    if (hdr) {
      const fromHdr = stripTagSuffix(hdr);
      if (fromHdr && !isPlaceholderItemLabel(fromHdr)) return fromHdr;
    }
    if (lab) {
      const fromLab = stripTagSuffix(lab);
      if (fromLab && !isPlaceholderItemLabel(fromLab)) return fromLab;
    }
    return '';
  }

  function excelColumnSortKey(col) {
    const c = String(col || '').toUpperCase().trim();
    if (!c || !/^[A-Z]+$/.test(c)) return [9999, 0];
    let w = 0;
    for (let i = 0; i < c.length; i += 1) {
      w = w * 26 + (c.charCodeAt(i) - 64);
    }
    return [c.length, w];
  }

  /** Item-колонки с восстановленным item_depth (как на сервере: порядок колонок Excel). */
  function itemSchemaRowsWithDepth() {
    const rows = schemaRows()
      .filter(function (r) {
        if (!r || !r.tags) return false;
        const tags = (r.tags || []).map(function (t) { return String(t).toLowerCase(); });
        return tags.indexOf('item') >= 0;
      })
      .sort(function (a, b) {
        const ka = excelColumnSortKey(a.col);
        const kb = excelColumnSortKey(b.col);
        if (ka[0] !== kb[0]) return ka[0] - kb[0];
        return ka[1] - kb[1];
      });
    let inferredNext = 0;
    return rows.map(function (r) {
      let idep = r.item_depth;
      if (idep == null || idep === '') {
        idep = inferredNext;
        inferredNext += 1;
      } else {
        idep = Number(idep);
        inferredNext = Math.max(inferredNext, idep + 1);
      }
      return { row: r, depth: idep };
    });
  }

  /** Подпись item-колонки по item_depth (0 = корень). */
  global.matrixSchemaItemLevelLabel = function (level) {
    const list = itemSchemaRowsWithDepth();
    for (let i = 0; i < list.length; i += 1) {
      if (list[i].depth !== level) continue;
      const cap = effectiveSchemaCaption(list[i].row);
      if (cap) return cap;
    }
    return '';
  };

  /** Текст колонки (skill_sticker), напр. «Ответственный» из шапки Excel. */
  global.matrixSchemaSkillStickerLabel = function () {
    const rows = schemaRows();
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (!r || !r.tags) continue;
      const tags = (r.tags || []).map(function (t) { return String(t).toLowerCase(); });
      if (tags.indexOf('skill_sticker') < 0) continue;
      const cap = effectiveSchemaCaption(r);
      if (cap) return cap;
    }
    return '';
  };

  /** Подпись последней item-колонки (лист в unified). */
  global.matrixSchemaDeepestItemLabel = function () {
    const list = itemSchemaRowsWithDepth();
    let maxD = -1;
    let title = '';
    list.forEach(function (item) {
      const d = item.depth;
      if (d > maxD) {
        maxD = d;
        title = effectiveSchemaCaption(item.row);
      }
    });
    return title;
  };

  /**
   * Заголовок колонки уровня в дереве: level_name с API, затем схема, затем item_{n}.
   */
  global.matrixSchemaLevelLabel = function (level, sampleNode) {
    const sample = sampleNode;
    if (sample && typeof sample.level_name === 'string' && sample.level_name.trim()) {
      const ln = sample.level_name.trim();
      if (!isPlaceholderItemLabel(ln)) return ln;
    }
    const s = global.matrixSchemaItemLevelLabel(level);
    if (s) return s;
    if (sample && Number.isInteger(sample.level)) {
      return 'item_' + String(Number(sample.level));
    }
    return 'item_' + String(level);
  };

  /** Заголовок колонки «открыть карточку листа». */
  global.matrixSchemaLeafColumnHeading = function () {
    const t = global.matrixSchemaDeepestItemLabel();
    return t ? (t + ' · leaf') : 'leaf';
  };

  global.matrixSchemaLeafViewTitleForKey = function (key) {
    const rows = schemaRows();
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (r && r.leaf_view_key === key) {
        const cap = effectiveSchemaCaption(r);
        if (cap) return cap;
      }
    }
    return String(key || '').replace(/_/g, ' ');
  };

  /** Подпись для title у ответственного / владельца навыка. */
  global.matrixSchemaResponsibleTitleAttr = function () {
    const s = global.matrixSchemaSkillStickerLabel();
    return s || 'responsible';
  };

  var PLACEHOLDER_RESP = {
    '': 1,
    'не указан': 1,
    'не указано': 1,
    'не указаны': 1,
    'n/a': 1,
    na: 1,
    '-': 1,
    '—': 1,
    'нет': 1,
    'отсутствует': 1,
    'not specified': 1,
    'none': 1,
    'null': 1,
  };

  /** True если строка ответственного не пустая и не шаблон вроде «не указан». */
  global.matrixResponsibleIsMeaningful = function (val) {
    var s = String(val == null ? '' : val).trim();
    if (!s) return false;
    var low = s.toLowerCase().replace(/\s+/g, ' ').trim();
    if (PLACEHOLDER_RESP[low]) return false;
    var collapsed = low.replace(/\s/g, '');
    if (PLACEHOLDER_RESP[collapsed]) return false;
    return true;
  };

  /**
   * Облако наклеек по свойствам узла: описание (иконка), ответственный, J/M/S.
   * esc — функция экранирования HTML (как escHtml на странице).
   */
  global.matrixNodePropertyStickersHtml = function (node, esc) {
    var escFn = typeof esc === 'function' ? esc : function (x) { return String(x); };
    if (!node) return '';
    var parts = [];
    var desc = (node.description && String(node.description).trim()) ? String(node.description).trim() : '';
    if (desc) {
      var dt = desc.length > 100 ? desc.slice(0, 97) + '…' : desc;
      parts.push(
        '<span class="tree-node-prop-badge tree-node-prop-desc" title="' +
          escFn(dt) +
          '" role="img" aria-label="Описание"><i class="fas fa-align-left" aria-hidden="true"></i></span>'
      );
    }
    var r = String(node.responsible || '').trim();
    if (global.matrixResponsibleIsMeaningful(r)) {
      var rt = global.matrixSchemaResponsibleTitleAttr();
      parts.push(
        '<span class="tree-skill-owner" title="' +
          escFn(rt) +
          '">' +
          escFn(r) +
          '</span>'
      );
    }
    var tags = Array.isArray(node.level_tags) && node.level_tags.length
      ? node.level_tags
      : node.level_tag
        ? [node.level_tag]
        : [];
    tags.forEach(function (t) {
      parts.push(
        '<span class="tree-node-level-badge">' + escFn(String(t).toUpperCase()) + '</span>'
      );
    });
    var legacy = !tags.length && node.level_sticker
      ? '<span class="tree-skill-sticker">' + escFn(String(node.level_sticker).toUpperCase()) + '</span>'
      : '';
    if (legacy) parts.push(legacy);
    return parts.length ? '<div class="tree-node-badges-wrap tree-node-prop-cloud">' + parts.join('') + '</div>' : '';
  };
})(typeof window !== 'undefined' ? window : this);
