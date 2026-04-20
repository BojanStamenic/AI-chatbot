/* ═══════════════════════════════════════════════════════════════
   SNIMANJE GLASA — mikrofon, MediaRecorder, Whisper transkripcija
   ═══════════════════════════════════════════════════════════════ */

const micBtn = document.getElementById("micBtn");
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

micBtn.addEventListener("click", toggleRecording);

async function toggleRecording() {
  if (isRecording) {
    mediaRecorder.stop();
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];

    const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/ogg";
    mediaRecorder = new MediaRecorder(stream, { mimeType });

    mediaRecorder.ondataavailable = function(e) {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async function() {
      isRecording = false;
      micBtn.classList.remove("recording");
      stream.getTracks().forEach(function(t) { t.stop(); });

      const blob = new Blob(audioChunks, { type: mimeType });
      await transcribeAudio(blob, mimeType);
    };

    mediaRecorder.start();
    isRecording = true;
    micBtn.classList.add("recording");
  } catch (err) {
    addMsg("Microphone access denied: " + err.message, "error", false, false);
  }
}

async function transcribeAudio(blob, mimeType) {
  micBtn.disabled = true;
  const ext = mimeType.includes("ogg") ? "ogg" : "webm";
  const formData = new FormData();
  formData.append("audio", blob, "recording." + ext);

  try {
    const res = await fetch("/transcribe", { method: "POST", body: formData });
    const data = await res.json();
    if (data.error) {
      addMsg("Transcription error: " + data.error, "error", false, false);
    } else if (data.text && data.text.trim()) {
      msgInput.value = data.text.trim();
      msgInput.focus();
    }
  } catch (_) {
    addMsg("Transcription failed — check server.", "error", false, false);
  } finally {
    micBtn.disabled = false;
  }
}


/* ═══════════════════════════════════════════════════════════════
   WAKE WORD — "Hey JARVIS" detekcija putem SpeechRecognition
   ═══════════════════════════════════════════════════════════════ */

const wakeBtn      = document.getElementById("wakeBtn");
const SpeechRec    = window.SpeechRecognition || window.webkitSpeechRecognition;
const WAKE_PHRASES = [
  "hey jarvis", "jarvis", "wake up jarvis", "yo jarvis",
  "wake up", "hello", "hey bot"
];

let wakeRecognition    = null;
let commandRecognition = null;
let wakeWordEnabled    = false;
let commandActive      = false;
let isSpeaking         = false;
let ttsEnabled         = false;

wakeBtn.addEventListener("click", toggleWakeWord);

function toggleWakeWord() {
  if (!SpeechRec) {
    addMsg("Wake word nije podržan u ovom browseru. Koristi Chrome ili Edge.", "error", false, false);
    return;
  }
  wakeWordEnabled = !wakeWordEnabled;
  updateWakeBtn();

  if (wakeWordEnabled) {
    startWakeListen();
  } else {
    stopWakeListen();
    addMsg("JARVIS offline. Have a good one.", "system", false, false);
  }
}

function updateWakeBtn() {
  wakeBtn.classList.toggle("active", wakeWordEnabled);
  wakeBtn.title = wakeWordEnabled
    ? 'Online — say "Hey JARVIS" to fire up the AI (click to disable)'
    : 'Click to activate JARVIS wake detection';
}

function startWakeListen() {
  if (!SpeechRec || commandActive) return;

  wakeRecognition = new SpeechRec();
  wakeRecognition.continuous    = true;
  wakeRecognition.interimResults = true;
  wakeRecognition.lang           = "en-US";

  wakeRecognition.onresult = function(e) {
    if (isSpeaking) return;
    for (var i = e.resultIndex; i < e.results.length; i++) {
      var t = e.results[i][0].transcript.toLowerCase();
      if (WAKE_PHRASES.some(function(p) { return t.includes(p); })) {
        wakeRecognition.abort();
        onWakeWordDetected();
        return;
      }
    }
  };

  wakeRecognition.onend = function() {
    if (wakeWordEnabled && !commandActive) {
      setTimeout(function() {
        try { wakeRecognition.start(); } catch(_) {}
      }, 300);
    }
  };

  wakeRecognition.onerror = function(e) {
    if (e.error === "not-allowed") {
      wakeWordEnabled = false;
      updateWakeBtn();
      addMsg("Mikrofonski pristup odbijen — dozvoli u browseru.", "error", false, false);
    }
  };

  try {
    wakeRecognition.start();
    addMsg("JARVIS online. At your service, sir — say \"Hey JARVIS\" whenever you need me.", "system", false, false);
  } catch(_) {}
}

function stopWakeListen() {
  try { wakeRecognition && wakeRecognition.abort(); } catch(_) {}
  try { commandRecognition && commandRecognition.abort(); } catch(_) {}
  commandActive = false;
  wakeBtn.classList.remove("listening");
}

function onWakeWordDetected() {
  commandActive = true;
  wakeBtn.classList.add("listening");

  commandRecognition = new SpeechRec();
  commandRecognition.lang           = "en-US";
  commandRecognition.interimResults  = false;
  commandRecognition.maxAlternatives = 1;

  commandRecognition.onresult = function(e) {
    var text = e.results[0][0].transcript.trim();
    if (text) {
      msgInput.value = text;
      sendMessage();
    }
  };

  commandRecognition.onend = function() {
    commandActive = false;
    wakeBtn.classList.remove("listening");
    if (wakeWordEnabled) {
      setTimeout(function() {
        try { wakeRecognition.start(); } catch(_) {}
      }, 400);
    }
  };

  commandRecognition.onerror = function() {
    commandActive = false;
    wakeBtn.classList.remove("listening");
    if (wakeWordEnabled) {
      setTimeout(function() {
        try { wakeRecognition.start(); } catch(_) {}
      }, 400);
    }
  };

  try { commandRecognition.start(); } catch(_) {}
}


/* ═══════════════════════════════════════════════════════════════
   TEXT-TO-SPEECH — glasovni odgovori (Voice dugme u headeru)
   ═══════════════════════════════════════════════════════════════ */

const ttsBtn = document.getElementById("ttsBtn");
ttsBtn.addEventListener("click", function() {
  ttsEnabled = !ttsEnabled;
  ttsBtn.classList.toggle("active", ttsEnabled);
  ttsBtn.title = ttsEnabled ? "Voice replies on (click to disable)" : "Enable voice replies";
  if (!ttsEnabled) window.speechSynthesis && speechSynthesis.cancel();
});

function stripMarkdown(text) {
  return text
    .replace(/```[\s\S]*?```/g, "code block.")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/#{1,6}\s/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, " ");
}

function speak(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();

  const clean = stripMarkdown(text).trim();
  if (!clean) return;

  const utter = new SpeechSynthesisUtterance(clean);
  utter.lang  = "en-US";
  utter.rate  = 1.05;
  utter.pitch = 0.88;

  isSpeaking = true;
  try { wakeRecognition && wakeRecognition.abort(); } catch(_) {}

  function afterSpeech() {
    isSpeaking = false;
    if (wakeWordEnabled && !commandActive) {
      setTimeout(function() {
        try { wakeRecognition.start(); } catch(_) {}
      }, 400);
    }
  }
  utter.onend   = afterSpeech;
  utter.onerror = afterSpeech;

  speechSynthesis.speak(utter);
}
