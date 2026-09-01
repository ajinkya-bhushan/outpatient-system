"""
frontend/streamlit_app.py
──────────────────────────
Streamlit UI for the SST Model Evaluation POC.

Tabs
----
1.  Audio Upload         - upload a file, select engine/model, transcribe, view results.
2.  Live Transcription   - microphone stream -> WebSocket -> partial + final transcripts
                           with real-time latency metrics panel.

Design notes
------------
* No business logic lives here; all heavy lifting is done by the FastAPI backend.
* The Streamlit app communicates with the backend over HTTP (upload tab) and
  WebSocket (live tab).
* API_BASE_URL is read from settings / env so the UI works without code changes
  when the backend moves to a different host/port.
* The live tab uses an embedded HTML/JS component (st.components.v1.html) because
  Streamlit does not natively support WebSocket or microphone access.
"""

from __future__ import annotations

import os
import time

import httpx
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SST Model Evaluation",
    page_icon="ST",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load backend URL from env / default ───────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
WS_BASE_URL = API_BASE_URL.replace("http://", "ws://").replace("https://", "wss://")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("SST Config")
    st.markdown("---")

    backend_url = st.text_input("Backend API URL", value=API_BASE_URL)
    API_BASE_URL = backend_url.rstrip("/")
    WS_BASE_URL = API_BASE_URL.replace("http://", "ws://").replace("https://", "wss://")

    st.markdown("---")

    if st.button("Check Backend Health"):
        try:
            r = httpx.get(f"{API_BASE_URL}/api/v1/health", timeout=5)
            if r.status_code == 200:
                data = r.json()
                st.success(f"Backend healthy  |  uptime: {data.get('uptime_s', '?')}s")
            else:
                st.error(f"Backend returned {r.status_code}")
        except Exception as exc:
            st.error(f"Cannot reach backend: {exc}")

    if st.button("Check Engine Status"):
        try:
            r = httpx.get(f"{API_BASE_URL}/api/v1/ready", timeout=5)
            data = r.json()
            for eng, info in data.get("engines", {}).items():
                loaded = info.get("model_loaded", "?")
                st.write(f"**{eng}** — loaded: {loaded}")
        except Exception as exc:
            st.error(f"Cannot reach backend: {exc}")

    st.markdown("---")
    st.caption("SST Model Evaluation v0.1.0")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_upload, tab_live = st.tabs(["Audio Upload", "Live Transcription"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 - AUDIO UPLOAD
# ════════════════════════════════════════════════════════════════════════════
with tab_upload:
    st.header("Audio File Transcription")
    st.markdown(
        "Upload an audio file to transcribe it using the selected engine and model."
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Choose an audio file",
            type=["mp3", "mp4", "wav", "m4a", "ogg", "flac", "webm"],
            help="Supported formats: MP3, MP4, WAV, M4A, OGG, FLAC, WebM",
        )

    with col2:
        engine_choice = st.selectbox(
            "Engine",
            options=["whisper", "whisperflow", "openai", "faster_whisper"],
            index=0,
            help="Select the STT engine",
        )

        language_input = st.text_input(
            "Language (optional)",
            value="",
            placeholder="e.g. en, fr, de (empty = auto-detect)",
            max_chars=5,
        )

        task_choice = st.selectbox(
            "Task",
            options=["transcribe", "translate"],
            index=0,
            help="'translate' always produces English output",
        )

    st.markdown("---")
    transcribe_btn = st.button("Transcribe", type="primary", disabled=uploaded_file is None)

    if transcribe_btn and uploaded_file is not None:
        with st.spinner("Transcribing... this may take a moment on first run (model loading)"):
            start_wall = time.perf_counter()
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {
                    "engine": engine_choice,
                    "language": language_input.strip(),
                    "task": task_choice,
                }
                response = httpx.post(
                    f"{API_BASE_URL}/api/v1/transcribe",
                    files=files,
                    data=data,
                    timeout=300,
                )

                wall_time = time.perf_counter() - start_wall

                if response.status_code == 200:
                    result = response.json()

                    st.success("Transcription complete!")
                    st.subheader("Transcript")
                    st.text_area(
                        label="",
                        value=result.get("text", ""),
                        height=200,
                        key="transcript_output",
                    )

                    st.subheader("Performance Metrics")
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Engine", result.get("engine", "-"))
                    m2.metric("Model", result.get("model", "-"))
                    m3.metric("Language", result.get("language", "-").upper())
                    m4.metric(
                        "Audio Duration",
                        f"{result.get('audio_duration', 0):.1f}s",
                    )
                    m5.metric(
                        "Processing Time",
                        f"{result.get('processing_time', 0):.2f}s",
                    )

                    rtf = result.get("real_time_factor", 0.0)
                    rtf_label = "faster" if rtf < 1.0 else "slower"
                    rtf_color = "normal" if rtf < 1.0 else "inverse"
                    st.metric(
                        label=f"Real-Time Factor (RTF) — {rtf_label} than real-time",
                        value=f"{rtf:.4f}",
                        delta=f"{1.0 - rtf:.4f} margin",
                        delta_color=rtf_color,
                    )

                    segments = result.get("segments", [])
                    if segments:
                        with st.expander(f"Timed Segments ({len(segments)} segments)"):
                            for seg in segments:
                                st.markdown(
                                    f"**[{seg['start']:.1f}s - {seg['end']:.1f}s]** "
                                    f"{seg['text']}"
                                )
                else:
                    detail = response.json().get("detail", response.text)
                    st.error(f"Error {response.status_code}: {detail}")

            except httpx.ConnectError:
                st.error(
                    f"Cannot connect to backend at `{API_BASE_URL}`. "
                    "Is the FastAPI server running?"
                )
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 - LIVE TRANSCRIPTION
# ════════════════════════════════════════════════════════════════════════════
with tab_live:
    st.header("Live Microphone Transcription")

    st.info(
        "**How it works:**\n"
        "1. Click **Start Recording** - your browser will request microphone permission.\n"
        "2. Speak into your microphone.\n"
        "3. Partial transcripts appear every ~2s (buffered batch inference).\n"
        "4. Click **Stop** to get the complete final transcript and session metrics.\n\n"
        "**Note:** Localhost is exempt from HTTPS requirements for microphone access."
    )

    # ── Limitation warning ────────────────────────────────────────────────────
    with st.expander("Known limitations of live transcription (click to read)"):
        st.markdown("""
**WhisperFlow installation conflict**
- The `whisperflow` PyPI package pins `fastapi==0.108.0`, which conflicts with
  this project's `fastapi>=0.111.0`. Both cannot coexist in the same virtualenv.
- **Workaround:** Use the `whisper` engine for live transcription (default).
  It uses the same Whisper model with rolling buffer inference.

**Not truly real-time word-by-word**
- Whisper is a batch model. Even with WhisperFlow windowing, you receive a
  transcript after each ~2s window, NOT one word at a time.
- For truly streaming word-level ASR, consider: Deepgram, AssemblyAI, or
  running a streaming model (e.g. wav2vec2 CTC).

**Audio format**
- Browser MediaRecorder sends `audio/webm`. Whisper decodes this via ffmpeg.
  Ensure ffmpeg is on PATH. Without ffmpeg, transcription will fail.

**CPU latency**
- On CPU with `base` model, expect RTF ~0.5-2x. For lower latency, use `tiny`.
- On GPU (cuda), RTF drops to ~0.05-0.1x.
        """)

    # ── Controls ──────────────────────────────────────────────────────────────
    live_col1, live_col2, live_col3 = st.columns([1, 1, 1])

    with live_col1:
        live_engine = st.selectbox(
            "Live Engine",
            options=["whisper", "whisperflow"],
            index=0,
            key="live_engine",
            help="whisper = always available; whisperflow = requires separate install",
        )

    with live_col2:
        live_language = st.text_input(
            "Language (optional)",
            value="",
            placeholder="e.g. en (empty = auto)",
            key="live_language",
        )

    with live_col3:
        chunk_interval_ms = st.slider(
            "MediaRecorder chunk interval (ms)",
            min_value=250,
            max_value=2000,
            value=500,
            step=250,
            help="How often the browser sends audio chunks. Lower = more responsive.",
        )

    ws_url = f"{WS_BASE_URL}/api/v1/live"
    st.code(f"WebSocket endpoint: {ws_url}", language="text")

    st.markdown("---")

    # ── Embedded HTML/JS component ────────────────────────────────────────────
    _ws_url        = ws_url
    _engine        = live_engine
    _lang          = live_language.strip()
    _chunk_ms      = chunk_interval_ms

    live_html = f"""
<style>
  :root {{
    --bg-dark:    #0e1117;
    --bg-panel:   #1a1d27;
    --bg-partial: #1e1e2e;
    --bg-final:   #0d2b1a;
    --txt-main:   #cdd6f4;
    --txt-partial:#a6adc8;
    --txt-final:  #a6e3a1;
    --accent:     #89b4fa;
    --red:        #f38ba8;
    --yellow:     #f9e2af;
    --green:      #a6e3a1;
    --radius:     8px;
    --font:       'Segoe UI', system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg-dark); color: var(--txt-main); font-family: var(--font); }}

  .stt-card {{
    background: var(--bg-panel);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 12px;
  }}

  .btn-row {{ display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }}
  .btn {{
    padding: 9px 20px; border: none; border-radius: 6px;
    cursor: pointer; font-size: 13px; font-weight: 600;
    transition: opacity .15s;
  }}
  .btn:hover {{ opacity: .85; }}
  #startBtn {{ background: #1a7f4f; color: #fff; }}
  #stopBtn  {{ background: #7f1a1a; color: #fff; display: none; }}
  .badge {{
    padding: 3px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 600; letter-spacing: .5px;
    background: #2a2d3e; color: var(--txt-partial);
  }}
  .badge.connected  {{ background: #1a7f4f; color: #fff; }}
  .badge.recording  {{ background: #7f1a1a; color: #fff; animation: pulse 1s infinite; }}
  .badge.processing {{ background: #7f4f1a; color: #fff; }}
  @keyframes pulse {{ 0%,100% {{ opacity:1 }} 50% {{ opacity:.6 }} }}

  .section-label {{
    font-size: 11px; color: #888; text-transform: uppercase;
    letter-spacing: .8px; margin-bottom: 5px;
  }}
  #partial-output {{
    background: var(--bg-partial);
    color: var(--txt-partial);
    padding: 12px 14px; border-radius: var(--radius);
    min-height: 72px; white-space: pre-wrap; font-size: 13.5px;
    line-height: 1.55; border-left: 3px solid var(--accent);
    margin-bottom: 10px;
  }}
  #final-output {{
    background: var(--bg-final);
    color: var(--txt-final);
    padding: 12px 14px; border-radius: var(--radius);
    min-height: 60px; white-space: pre-wrap; font-size: 14px;
    font-weight: 500; line-height: 1.55;
    border-left: 3px solid var(--green);
    margin-bottom: 10px;
  }}

  .metrics-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-top: 10px;
  }}
  .metric-box {{
    background: #12151f;
    border-radius: 6px; padding: 10px 12px;
    text-align: center;
  }}
  .metric-val {{
    font-size: 18px; font-weight: 700; color: var(--accent);
  }}
  .metric-lbl {{
    font-size: 10px; color: #666; margin-top: 2px;
    text-transform: uppercase; letter-spacing: .5px;
  }}

  #errorBox {{
    background: #2a1a1a; color: var(--red);
    border-left: 3px solid var(--red);
    padding: 10px 14px; border-radius: var(--radius);
    font-size: 12.5px; display: none; margin-top: 8px;
  }}
</style>

<div class="stt-card">
  <div class="btn-row">
    <button class="btn" id="startBtn" onclick="startRecording()">Start Recording</button>
    <button class="btn" id="stopBtn"  onclick="stopRecording()">Stop</button>
    <span class="badge" id="statusBadge">idle</span>
  </div>

  <div class="section-label">Partial transcript</div>
  <div id="partial-output">(waiting for audio...)</div>

  <div class="section-label">Final transcript</div>
  <div id="final-output"></div>

  <div id="errorBox"></div>
</div>

<div class="stt-card">
  <div class="section-label">Session Metrics</div>
  <div class="metrics-grid">
    <div class="metric-box">
      <div class="metric-val" id="m-ttft">-</div>
      <div class="metric-lbl">Time to First Token (ms)</div>
    </div>
    <div class="metric-box">
      <div class="metric-val" id="m-total">-</div>
      <div class="metric-lbl">Total Session (ms)</div>
    </div>
    <div class="metric-box">
      <div class="metric-val" id="m-rtf">-</div>
      <div class="metric-lbl">Final RTF</div>
    </div>
    <div class="metric-box">
      <div class="metric-val" id="m-audio">-</div>
      <div class="metric-lbl">Audio Duration (s)</div>
    </div>
    <div class="metric-box">
      <div class="metric-val" id="m-partials">0</div>
      <div class="metric-lbl">Partial Results</div>
    </div>
    <div class="metric-box">
      <div class="metric-val" id="m-latency">-</div>
      <div class="metric-lbl">Final Latency (ms)</div>
    </div>
  </div>
</div>

<script>
  const WS_URL      = "{_ws_url}";
  const ENGINE      = "{_engine}";
  const LANG        = "{_lang}";
  const CHUNK_MS    = {_chunk_ms};

  let ws, mediaRecorder, stream;
  let partialCount = 0;
  let sessionStartTime = null;

  function badge(text, cls) {{
    const b = document.getElementById("statusBadge");
    b.textContent = text;
    b.className   = "badge " + (cls || "");
  }}

  function showError(msg) {{
    const box = document.getElementById("errorBox");
    box.textContent = "Error: " + msg;
    box.style.display = "block";
  }}
  function clearError() {{
    document.getElementById("errorBox").style.display = "none";
  }}

  function setMetric(id, val) {{
    document.getElementById(id).textContent = val !== null && val !== undefined ? val : "-";
  }}

  async function startRecording() {{
    clearError();
    partialCount = 0;
    setMetric("m-ttft", "-");
    setMetric("m-total", "-");
    setMetric("m-rtf", "-");
    setMetric("m-audio", "-");
    setMetric("m-partials", "0");
    setMetric("m-latency", "-");
    document.getElementById("partial-output").textContent = "(connecting...)";
    document.getElementById("final-output").textContent   = "";
    document.getElementById("startBtn").style.display     = "none";
    document.getElementById("stopBtn").style.display      = "inline-block";
    badge("connecting");

    try {{
      ws = new WebSocket(WS_URL);
      ws.binaryType = "arraybuffer";

      ws.onopen = async () => {{
        badge("connected", "connected");
        ws.send(JSON.stringify({{ type: "start", engine: ENGINE, language: LANG }}));

        try {{
          stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
          const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
            ? "audio/webm;codecs=opus" : "audio/webm";
          mediaRecorder = new MediaRecorder(stream, {{ mimeType }});

          mediaRecorder.ondataavailable = (evt) => {{
            if (evt.data && evt.data.size > 0 && ws.readyState === WebSocket.OPEN) {{
              ws.send(evt.data);
            }}
          }};

          mediaRecorder.start(CHUNK_MS);
          sessionStartTime = Date.now();
          badge("recording", "recording");
          document.getElementById("partial-output").textContent = "(listening...)";
        }} catch(micErr) {{
          showError("Microphone error: " + micErr.message);
          resetUI();
        }}
      }};

      ws.onmessage = (evt) => {{
        try {{
          const msg = JSON.parse(evt.data);

          if (msg.type === "partial") {{
            partialCount++;
            setMetric("m-partials", partialCount);
            document.getElementById("partial-output").textContent =
              msg.text || "(no speech detected yet)";

          }} else if (msg.type === "final") {{
            document.getElementById("final-output").textContent =
              msg.text || "(empty - no speech detected)";
            document.getElementById("partial-output").textContent = "";
            setMetric("m-audio",   msg.audio_duration   != null ? msg.audio_duration.toFixed(2)   : "-");
            setMetric("m-rtf",     msg.real_time_factor != null ? msg.real_time_factor.toFixed(4)  : "-");
            setMetric("m-latency", msg.latency_ms       != null ? msg.latency_ms.toFixed(0)        : "-");

          }} else if (msg.type === "session_ended") {{
            const m = msg.metrics || {{}};
            setMetric("m-ttft",  m.time_to_first_token_ms != null ? m.time_to_first_token_ms.toFixed(0) : "-");
            setMetric("m-total", m.total_session_ms       != null ? m.total_session_ms.toFixed(0)       : "-");
            badge("done");
            resetUI();

          }} else if (msg.type === "error") {{
            showError(msg.detail || "Unknown error");
            badge("error");
          }}
        }} catch(e) {{ console.warn("WS parse error:", e); }}
      }};

      ws.onclose = (evt) => {{
        badge("closed");
        if (evt.code !== 1000 && evt.code !== 1001) {{
          showError("WebSocket closed unexpectedly (code " + evt.code + ")");
        }}
        resetUI();
      }};
      ws.onerror = () => {{
        badge("error");
        showError("WebSocket connection error. Is the backend running?");
        resetUI();
      }};

    }} catch(err) {{
      showError(err.message);
      badge("error");
      resetUI();
    }}
  }}

  function stopRecording() {{
    if (mediaRecorder && mediaRecorder.state !== "inactive") {{
      mediaRecorder.stop();
    }}
    if (stream) {{ stream.getTracks().forEach(t => t.stop()); }}
    if (ws && ws.readyState === WebSocket.OPEN) {{
      ws.send(JSON.stringify({{ type: "stop" }}));
    }}
    badge("processing", "processing");
    document.getElementById("partial-output").textContent = "(processing final transcript...)";
    document.getElementById("stopBtn").style.display = "none";
  }}

  function resetUI() {{
    document.getElementById("startBtn").style.display = "inline-block";
    document.getElementById("stopBtn").style.display  = "none";
  }}
</script>
"""
    st.components.v1.html(live_html, height=640, scrolling=False)
