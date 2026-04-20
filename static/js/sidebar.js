/* ═══════════════════════════════════════════════════════════════
   SIDEBAR — toggle, chat lista, switch, delete, rename, new chat
   ═══════════════════════════════════════════════════════════════ */

function toggleSidebar() {
  sidebar.classList.toggle("open");
  overlay.classList.toggle("open");
}

hamburger.addEventListener("click", toggleSidebar);
overlay.addEventListener("click", toggleSidebar);

async function loadChatList() {
  const data = await getJSON("/api/chats");
  chatList.innerHTML = "";
  data.forEach(function(c) {
    if (c.active) {
      activeChatId = c.id;
      headerTitle.textContent = c.title;
      turns = c.turn;
      syncStats();
    }

    const item = document.createElement("div");
    item.className = "chat-item" + (c.active ? " active" : "");
    item.innerHTML =
      '<div class="chat-item-info">' +
        '<div class="chat-item-title">' + escHtml(c.title) + '</div>' +
        '<div class="chat-item-meta">' + timeAgo(c.created) + ' &middot; ' + c.turn + ' turns</div>' +
      '</div>' +
      '<div class="chat-item-actions">' +
        '<button class="chat-item-btn rename" title="Rename">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>' +
        '</button>' +
        '<button class="chat-item-btn delete" title="Delete">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
        '</button>' +
      '</div>';

    item.querySelector(".chat-item-info").addEventListener("click", function() {
      switchChat(c.id);
    });

    item.querySelector(".rename").addEventListener("click", function(e) {
      e.stopPropagation();
      startRename(c.id, item.querySelector(".chat-item-title"));
    });

    item.querySelector(".delete").addEventListener("click", function(e) {
      e.stopPropagation();
      deleteChat(c.id);
    });

    chatList.appendChild(item);
  });
}

function startRename(chatId, titleEl) {
  const current = titleEl.textContent;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "rename-input";
  input.value = current;
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  function finish() {
    const newTitle = input.value.trim() || current;
    postJSON("/api/chats/rename", { id: chatId, title: newTitle }).then(function() {
      loadChatList();
    });
  }

  input.addEventListener("blur", finish);
  input.addEventListener("keydown", function(e) {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    if (e.key === "Escape") { input.value = current; input.blur(); }
  });
}

async function switchChat(chatId) {
  if (chatId === activeChatId) return;
  await postJSON("/api/chats/switch", { id: chatId });
  const data = await getJSON("/api/chats/history?id=" + chatId);
  activeChatId = chatId;
  turns = data.turn || 0;
  files = (data.loaded_files || []).length;
  syncStats();
  rebuildChat(data.messages || []);
  headerTitle.textContent = data.title || "Chat";
  loadChatList();
  if (sidebar.classList.contains("open")) toggleSidebar();
}

async function deleteChat(chatId) {
  await postJSON("/api/chats/delete", { id: chatId });
  const data = await getJSON("/api/chats");
  if (data.length > 0) {
    const active = data.find(function(c) { return c.active; }) || data[0];
    await switchChat(active.id);
  }
  loadChatList();
}

async function createNewChat() {
  const data = await postJSON("/api/chats/new", {});
  activeChatId = data.id;
  turns = 0;
  files = 0;
  syncStats();
  headerTitle.textContent = "New chat";
  rebuildChat([]);
  loadChatList();
  msgInput.focus();
  if (sidebar.classList.contains("open")) toggleSidebar();
}

newChatBtn.addEventListener("click", createNewChat);
