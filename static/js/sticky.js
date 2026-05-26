/* Sticky notes — board + free-floating.
   - Notes default to living on the board.
   - Drag a note OFF the board → it becomes "free" and floats on the page.
   - Drag a free note back ONTO the board → it returns to the board.
   - Closing the board hides board notes; free notes stay on the page. */

(function () {
  const STORAGE_KEY = "bojanbot_sticky_notes_v3";
  const COLORS = ["", "color-pink", "color-blue", "color-green"];

  function loadNotes() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }
    catch (e) { return []; }
  }
  function saveNotes(notes) { localStorage.setItem(STORAGE_KEY, JSON.stringify(notes)); }
  function updateNote(id, patch) {
    const notes = loadNotes();
    const i = notes.findIndex(n => n.id === id);
    if (i >= 0) { Object.assign(notes[i], patch); saveNotes(notes); }
  }
  function removeNote(id) { saveNotes(loadNotes().filter(n => n.id !== id)); }

  function toPlainText(html) {
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    return (tmp.textContent || tmp.innerText || "").trim();
  }
  function previewOf(text) {
    const t = (text || "").replace(/\s+/g, " ").trim();
    return t.length > 60 ? t.slice(0, 60) + "…" : (t || "(empty)");
  }

  function getSurface() { return document.getElementById("boardSurface"); }
  function getBoardEl() { return document.getElementById("noteBoard"); }

  function mountNote(el, note) {
    if (note.free) {
      el.classList.add("free");
      document.body.appendChild(el);
    } else {
      el.classList.remove("free");
      const s = getSurface();
      if (s) s.appendChild(el);
    }
  }

  function renderNote(note) {
    const existing = document.querySelector('.sticky-note[data-id="' + note.id + '"]');
    if (existing) return existing;

    const el = document.createElement("div");
    el.className = "sticky-note " + (note.color || "");
    el.dataset.id = note.id;
    el.dataset.preview = previewOf(note.text);
    el.style.left = (note.x ?? 30) + "px";
    el.style.top  = (note.y ?? 30) + "px";
    if (note.w) el.style.width = note.w + "px";
    if (note.h) el.style.height = note.h + "px";
    if (note.collapsed) el.classList.add("collapsed");

    const header = document.createElement("div");
    header.className = "sticky-header";

    const grip = document.createElement("div");
    grip.className = "grip";
    header.appendChild(grip);

    const collapseBtn = document.createElement("button");
    collapseBtn.className = "sticky-btn";
    collapseBtn.title = "Shrink / expand";
    collapseBtn.textContent = note.collapsed ? "▢" : "—";
    collapseBtn.onclick = function (e) {
      e.stopPropagation();
      el.classList.toggle("collapsed");
      const isCol = el.classList.contains("collapsed");
      collapseBtn.textContent = isCol ? "▢" : "—";
      updateNote(note.id, { collapsed: isCol });
    };

    const closeBtn = document.createElement("button");
    closeBtn.className = "sticky-btn";
    closeBtn.title = "Delete note";
    closeBtn.textContent = "✕";
    closeBtn.onclick = function (e) {
      e.stopPropagation();
      el.remove();
      removeNote(note.id);
      refreshEmptyState();
      updateCount();
    };

    header.appendChild(collapseBtn);
    header.appendChild(closeBtn);

    const body = document.createElement("div");
    body.className = "sticky-body";
    body.contentEditable = "true";
    body.spellcheck = false;
    body.textContent = note.text || "";
    body.addEventListener("input", function () {
      el.dataset.preview = previewOf(body.textContent);
      updateNote(note.id, { text: body.textContent });
    });

    el.appendChild(header);
    el.appendChild(body);
    mountNote(el, note);

    makeDraggable(el, header, note.id);
    observeResize(el, note.id);
    return el;
  }

  function boardRect() {
    const b = getBoardEl();
    if (!b || !b.classList.contains("open")) return null;
    return b.getBoundingClientRect();
  }

  function makeDraggable(el, handle, id) {
    let startX, startY, origLeft, origTop, dragging = false;

    handle.addEventListener("mousedown", function (e) {
      if (e.target.classList.contains("sticky-btn")) return;
      dragging = true;
      el.classList.add("dragging");

      // Switch to viewport-fixed coords while dragging so the cursor stays glued
      const rect = el.getBoundingClientRect();
      if (!el.classList.contains("free")) {
        el.classList.add("free");
        document.body.appendChild(el);
      }
      el.style.left = rect.left + "px";
      el.style.top  = rect.top  + "px";

      startX = e.clientX; startY = e.clientY;
      origLeft = rect.left; origTop = rect.top;
      e.preventDefault();
    });

    document.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      const x = origLeft + (e.clientX - startX);
      const y = origTop  + (e.clientY - startY);
      el.style.left = x + "px";
      el.style.top  = y + "px";
    });

    document.addEventListener("mouseup", function (e) {
      if (!dragging) return;
      dragging = false;
      el.classList.remove("dragging");

      const board = boardRect();
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;

      if (board && cx >= board.left && cx <= board.right && cy >= board.top && cy <= board.bottom) {
        // Dropped on the (open) board → stick to board, position relative to surface
        const surface = getSurface();
        const sRect = surface.getBoundingClientRect();
        const newX = rect.left - sRect.left + surface.scrollLeft;
        const newY = rect.top  - sRect.top  + surface.scrollTop;
        el.classList.remove("free");
        surface.appendChild(el);
        el.style.left = Math.max(0, newX) + "px";
        el.style.top  = Math.max(0, newY) + "px";
        updateNote(id, { free: false, x: Math.max(0, newX), y: Math.max(0, newY) });
      } else {
        // Free-floating on viewport
        updateNote(id, { free: true, x: rect.left, y: rect.top });
      }
      refreshEmptyState();
    });
  }

  function observeResize(el, id) {
    let w = el.offsetWidth, h = el.offsetHeight;
    const ro = new ResizeObserver(function () {
      const nw = el.offsetWidth, nh = el.offsetHeight;
      if (nw !== w || nh !== h) {
        w = nw; h = nh;
        if (!el.classList.contains("collapsed")) {
          updateNote(id, { w: nw, h: nh });
        }
      }
    });
    ro.observe(el);
  }

  function refreshEmptyState() {
    const surface = getSurface();
    if (!surface) return;
    let empty = surface.querySelector(".board-empty");
    const hasBoardNotes = surface.querySelector(".sticky-note");
    if (!empty) {
      empty = document.createElement("div");
      empty.className = "board-empty";
      empty.innerHTML = 'No notes on the board.<br>Pin a chat response or click "+ New".<br><small style="opacity:0.7">Drag notes off the board to stick them anywhere on screen.</small>';
      surface.appendChild(empty);
    }
    empty.style.display = hasBoardNotes ? "none" : "flex";
  }

  function updateCount() {
    const c = document.getElementById("notesCount");
    if (c) c.textContent = loadNotes().length;
  }

  function nextPosition() {
    const notes = loadNotes();
    const i = notes.filter(n => !n.free).length;
    const col = i % 3;
    const row = Math.floor(i / 3) % 4;
    return { x: 20 + col * 210, y: 20 + row * 180 };
  }

  function measureText(text) {
    const m = document.createElement("div");
    m.style.cssText =
      "position:absolute;visibility:hidden;left:-9999px;top:0;" +
      "font-family:'Caveat','Comic Sans MS',cursive,sans-serif;" +
      "font-size:15px;line-height:1.3;padding:4px 10px 12px;" +
      "white-space:pre-wrap;word-wrap:break-word;max-width:380px;min-width:120px;";
    m.textContent = text || "New note";
    document.body.appendChild(m);
    const w = Math.min(380, Math.max(140, m.offsetWidth + 20));
    const h = Math.max(110, m.offsetHeight + 30); // + header + pin padding
    m.remove();
    return { w, h };
  }

  window.createStickyFromText = function (text) {
    const pos = nextPosition();
    const notes = loadNotes();
    const plain = toPlainText(text);
    const size = measureText(plain);
    const note = {
      id: "n_" + Date.now() + "_" + Math.random().toString(36).slice(2, 7),
      text: plain,
      x: pos.x, y: pos.y,
      w: size.w, h: size.h,
      color: COLORS[notes.length % COLORS.length],
      collapsed: false,
      free: false,
    };
    notes.push(note);
    saveNotes(notes);

    // Open the board so the new note is visible
    const board = getBoardEl();
    if (board && !board.classList.contains("open")) board.classList.add("open");

    renderNote(note);
    refreshEmptyState();
    updateCount();
  };

  // ── Build the board (no toggle pill — handled by header button) ───
  function buildBoard() {
    if (document.getElementById("noteBoard")) return;

    const board = document.createElement("aside");
    board.className = "note-board";
    board.id = "noteBoard";
    board.innerHTML =
      '<div class="board-header">' +
        '<h3>📌 Note Board</h3>' +
        '<div class="board-actions">' +
          '<button id="boardAddBtn" title="Add empty note">+ New</button>' +
          '<button id="boardClearBtn" title="Delete all notes">Clear</button>' +
          '<button id="boardHideBtn" title="Hide board">Hide ✕</button>' +
        '</div>' +
      '</div>' +
      '<div class="board-surface" id="boardSurface"></div>';

    document.body.appendChild(board);

    document.getElementById("boardHideBtn").onclick = function () {
      board.classList.remove("open");
    };
    document.getElementById("boardAddBtn").onclick = function () {
      window.createStickyFromText("");
    };
    document.getElementById("boardClearBtn").onclick = function () {
      if (!confirm("Delete ALL saved notes (board + free)?")) return;
      document.querySelectorAll(".sticky-note").forEach(el => el.remove());
      saveNotes([]);
      refreshEmptyState();
      updateCount();
    };

    // Hook up the header button
    const headerBtn = document.getElementById("notesToggle");
    if (headerBtn) {
      headerBtn.addEventListener("click", function () {
        board.classList.toggle("open");
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    buildBoard();
    loadNotes().forEach(renderNote);
    refreshEmptyState();
    updateCount();
  });
})();
