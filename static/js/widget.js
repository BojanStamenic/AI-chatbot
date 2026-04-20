/* ═══════════════════════════════════════════════════════════════
   WIDGET MODE — smanjeni chatbot na fiktivnom sajtu
   ═══════════════════════════════════════════════════════════════ */

const widgetToggle   = document.getElementById("widgetToggle");
const widgetMinimize = document.getElementById("widgetMinimize");
const widgetExpand   = document.getElementById("widgetExpand");
const chatBubble     = document.getElementById("chatBubble");

widgetToggle.addEventListener("click", function() {
  document.body.classList.add("widget-mode", "widget-open");
  msgInput.focus();
});

widgetExpand.addEventListener("click", function() {
  document.body.classList.remove("widget-mode", "widget-open");
  msgInput.focus();
});

widgetMinimize.addEventListener("click", function() {
  document.body.classList.remove("widget-open");
});

chatBubble.addEventListener("click", function() {
  document.body.classList.add("widget-open");
  msgInput.focus();
});
