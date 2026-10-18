#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iMouse 2.0 — Full 7-Layer Marketing Farm Localhost Server (Port 9914)

Connects the UI (`imouse_farm_command_center.html` and `FarmAutomationWindow.cs` in `iMouse2.exe`)
directly to all 7 backend layers in `imouse_social_automation.py` and your local `127.0.0.1:9913/api` kernel.

Endpoints:
  - GET  /                                -> Interactive 19-iPhone Farm Command Center UI
  - GET  /health                          -> Server & 7-layer backend health status
  - GET  /api/farm/state                  -> Full SQLite state (19 personas, slates, 0-view alerts)
  - POST /api/farm/auto-create-and-deploy -> Executes all 5 stages (Layer 1 Content Factory ->
                                             Layer 2 pHash/EXIF Spin -> Layer 3 iMousePull ->
                                             Layer 4 Multi-Platform Upload -> Layer 6 Pinned CTA & Swarm)
  - POST /api/farm/upload-single          -> Executes `SocialUploadOrchestrator` for one phone/format
  - POST /api/farm/warmup-wave            -> Executes `AccountWarmupEngine` across a cohort
  - POST /api/farm/funnel-action          -> Executes Pinned CTA Comment, Comment-to-DM, or Micro-Swarm
  - POST /api/farm/shadowban-scan         -> Executes `ShadowbanGuardAndDiagnostics` 3-5 clip 0-view check
  - POST /api/farm/update-persona         -> Updates a phone's niche, voice, CTA keyword, or offer URL
  - GET  /stage/<device_id>/manifest.json -> iOS Shortcut media & caption pull endpoint
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import random
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import imouse_social_automation as engine
from farm_jobs import FarmJobs, JobCancelled
from farm_drafts import CarouselDrafts, DraftConflict
from farm_transfers import CarouselTransfers, TransferConflict
from farm_capabilities import capabilities
from farm_video import VideoDrafts
from farm_observations import ObservationStore
from farm_draft_verification import DraftVerifications
from farm_preparation_schedule import PreparationSchedule

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9914
KERNEL_BASE_URL = "http://127.0.0.1:9913/api"
JOB_ACTIONS = {"create-content", "auto-create-and-deploy", "single-upload", "warmup-wave", "scheduler-tick", "funnel-action", "scan-profile-views"}


class FarmControlServer(ThreadingHTTPServer):
    """The control API never shares a port or exposes itself on the LAN."""
    allow_reuse_address = False

    def server_bind(self):
        if self.server_address[0] not in ('127.0.0.1', 'localhost'):
            raise ValueError('The farm control server must use loopback. Use the media transfer service for phone downloads.')
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

DASHBOARD_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8" />\n<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n<title>iMouse 2.0 — 19-iPhone Marketing Farm & Automation Command Center</title>\n<style>\n  :root {\n    --bg-root: #0b0f17;\n    --bg-panel: #111827;\n    --bg-card: #161f33;\n    --bg-card-hover: #1e2942;\n    --border-subtle: #26334d;\n    --border-active: #3b82f6;\n    --text-main: #f3f4f6;\n    --text-muted: #9ca3af;\n    --text-dim: #6b7280;\n    --accent-blue: #3b82f6;\n    --accent-indigo: #6366f1;\n    --accent-emerald: #10b981;\n    --accent-amber: #f59e0b;\n    --accent-rose: #f43f5e;\n    --accent-purple: #a855f7;\n    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;\n    --font-mono: "JetBrains Mono", "Cascadia Code", Consolas, monospace;\n  }\n\n  * {\n    box-sizing: border-box;\n    margin: 0;\n    padding: 0;\n  }\n\n  body {\n    background-color: var(--bg-root);\n    color: var(--text-main);\n    font-family: var(--font-sans);\n    font-size: 13px;\n    line-height: 1.45;\n    overflow-x: hidden;\n  }\n\n  /* Top Header Bar */\n  .topbar {\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    padding: 12px 20px;\n    background: linear-gradient(90deg, #0f172a 0%, #131c31 100%);\n    border-bottom: 1px solid var(--border-subtle);\n    position: sticky;\n    top: 0;\n    z-index: 50;\n    gap: 16px;\n    flex-wrap: wrap;\n  }\n\n  .brand {\n    display: flex;\n    align-items: center;\n    gap: 12px;\n  }\n\n  .brand-logo {\n    width: 36px;\n    height: 36px;\n    border-radius: 9px;\n    background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    font-weight: 800;\n    font-size: 16px;\n    color: #fff;\n    box-shadow: 0 0 18px rgba(59, 130, 246, 0.4);\n  }\n\n  .brand-title {\n    font-size: 16px;\n    font-weight: 700;\n    letter-spacing: -0.01em;\n  }\n\n  .brand-sub {\n    font-size: 11px;\n    color: var(--text-muted);\n    font-family: var(--font-mono);\n  }\n\n  .kernel-bar {\n    display: flex;\n    align-items: center;\n    gap: 10px;\n    flex-wrap: wrap;\n  }\n\n  .pill {\n    display: inline-flex;\n    align-items: center;\n    gap: 6px;\n    padding: 5px 10px;\n    border-radius: 999px;\n    background: var(--bg-card);\n    border: 1px solid var(--border-subtle);\n    font-size: 11.5px;\n    font-family: var(--font-mono);\n  }\n\n  .dot {\n    width: 8px;\n    height: 8px;\n    border-radius: 50%;\n    display: inline-block;\n  }\n  .dot.green { background: var(--accent-emerald); box-shadow: 0 0 8px var(--accent-emerald); }\n  .dot.amber { background: var(--accent-amber); box-shadow: 0 0 8px var(--accent-amber); }\n  .dot.rose  { background: var(--accent-rose); box-shadow: 0 0 8px var(--accent-rose); }\n  .dot.blue  { background: var(--accent-blue); box-shadow: 0 0 8px var(--accent-blue); }\n\n  .hero-actions {\n    display: flex;\n    align-items: center;\n    gap: 10px;\n  }\n\n  .btn {\n    border: 1px solid var(--border-subtle);\n    background: var(--bg-card);\n    color: var(--text-main);\n    padding: 8px 14px;\n    border-radius: 8px;\n    font-size: 12.5px;\n    font-weight: 600;\n    cursor: pointer;\n    display: inline-flex;\n    align-items: center;\n    gap: 7px;\n    transition: all 0.15s ease;\n  }\n\n  .btn:hover {\n    background: var(--bg-card-hover);\n    border-color: var(--accent-blue);\n  }\n\n  .btn-magic {\n    background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);\n    border: 1px solid #60a5fa;\n    color: #fff;\n    padding: 9px 18px;\n    font-size: 13px;\n    box-shadow: 0 4px 18px rgba(99, 102, 241, 0.4);\n  }\n\n  .btn-magic:hover {\n    filter: brightness(1.1);\n    transform: translateY(-1px);\n  }\n\n  .btn-stop {\n    background: rgba(244, 63, 94, 0.16);\n    border-color: var(--accent-rose);\n    color: #fda4af;\n  }\n\n  .btn-stop:hover {\n    background: var(--accent-rose);\n    color: #fff;\n  }\n\n  /* Main 3-Column Workspace matching iMouse Console Layout */\n  .workspace {\n    display: grid;\n    grid-template-columns: 310px 1fr 390px;\n    gap: 14px;\n    padding: 14px 18px;\n    min-height: calc(100vh - 64px);\n  }\n\n  @media (max-width: 1400px) {\n    .workspace {\n      grid-template-columns: 290px 1fr;\n    }\n    .right-col {\n      grid-column: 1 / -1;\n    }\n  }\n\n  @media (max-width: 960px) {\n    .workspace {\n      grid-template-columns: 1fr;\n    }\n  }\n\n  .panel {\n    background: var(--bg-panel);\n    border: 1px solid var(--border-subtle);\n    border-radius: 12px;\n    display: flex;\n    flex-direction: column;\n    overflow: hidden;\n  }\n\n  .panel-header {\n    padding: 12px 15px;\n    border-bottom: 1px solid var(--border-subtle);\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    background: rgba(22, 31, 51, 0.65);\n  }\n\n  .panel-title {\n    font-weight: 700;\n    font-size: 13.5px;\n    display: flex;\n    align-items: center;\n    gap: 8px;\n  }\n\n  .panel-body {\n    padding: 14px;\n    display: flex;\n    flex-direction: column;\n    gap: 12px;\n    flex: 1;\n    overflow-y: auto;\n  }\n\n  /* Selected Phone Preview (500x1080 Coordinate Visualizer) */\n  .phone-preview-wrap {\n    display: flex;\n    flex-direction: column;\n    align-items: center;\n    gap: 10px;\n  }\n\n  .phone-bezel {\n    width: 250px;\n    height: 540px;\n    border-radius: 26px;\n    border: 3px solid #334155;\n    background: #050811;\n    position: relative;\n    overflow: hidden;\n    box-shadow: inset 0 0 20px rgba(0,0,0,0.8), 0 8px 25px rgba(0,0,0,0.5);\n  }\n\n  .status-bar-mask {\n    height: 30px; /* Scaled 60px -> 30px */\n    width: 100%;\n    background: rgba(244, 63, 94, 0.14);\n    border-bottom: 1px dashed rgba(244, 63, 94, 0.5);\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    padding: 0 12px;\n    font-size: 10px;\n    font-family: var(--font-mono);\n    color: #fda4af;\n  }\n\n  #previewCanvas {\n    width: 250px;\n    height: 510px;\n    display: block;\n    cursor: crosshair;\n  }\n\n  /* 5-Stage Auto-Create & Deploy Pipeline Banner */\n  .pipeline-strip {\n    display: grid;\n    grid-template-columns: repeat(5, 1fr);\n    gap: 8px;\n    background: var(--bg-card);\n    border: 1px solid var(--border-subtle);\n    border-radius: 10px;\n    padding: 10px;\n  }\n\n  .stage-step {\n    padding: 8px 10px;\n    border-radius: 8px;\n    background: rgba(15, 23, 42, 0.7);\n    border: 1px solid var(--border-subtle);\n    display: flex;\n    flex-direction: column;\n    gap: 4px;\n    transition: all 0.2s ease;\n  }\n\n  .stage-step.active {\n    border-color: var(--accent-blue);\n    background: rgba(59, 130, 246, 0.15);\n    box-shadow: 0 0 14px rgba(59, 130, 246, 0.25);\n  }\n\n  .stage-step.done {\n    border-color: var(--accent-emerald);\n    background: rgba(16, 185, 129, 0.12);\n  }\n\n  .stage-num {\n    font-size: 10px;\n    font-family: var(--font-mono);\n    color: var(--text-muted);\n    text-transform: uppercase;\n  }\n\n  .stage-name {\n    font-weight: 700;\n    font-size: 12px;\n  }\n\n  .stage-desc {\n    font-size: 11px;\n    color: var(--text-muted);\n  }\n\n  /* 19-Phone Wall Grid */\n  .phone-wall {\n    display: grid;\n    grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));\n    gap: 10px;\n  }\n\n  .phone-tile {\n    background: var(--bg-card);\n    border: 1px solid var(--border-subtle);\n    border-radius: 10px;\n    padding: 10px;\n    cursor: pointer;\n    transition: all 0.15s ease;\n    display: flex;\n    flex-direction: column;\n    gap: 7px;\n    position: relative;\n  }\n\n  .phone-tile:hover {\n    border-color: #60a5fa;\n    transform: translateY(-1px);\n  }\n\n  .phone-tile.selected {\n    border-color: var(--accent-blue);\n    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.35);\n    background: #1a2640;\n  }\n\n  .tile-top {\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n  }\n\n  .tile-id {\n    font-family: var(--font-mono);\n    font-weight: 700;\n    font-size: 12.5px;\n    color: #fff;\n  }\n\n  .badge {\n    font-size: 10px;\n    font-family: var(--font-mono);\n    padding: 2px 6px;\n    border-radius: 4px;\n    font-weight: 600;\n  }\n\n  .badge-emerald { background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); }\n  .badge-blue    { background: rgba(59, 130, 246, 0.18); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.35); }\n  .badge-amber   { background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35); }\n  .badge-purple  { background: rgba(168, 85, 247, 0.18); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.35); }\n  .badge-rose    { background: rgba(244, 63, 94, 0.18); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.35); }\n\n  .tile-niche {\n    font-size: 11.5px;\n    font-weight: 600;\n    color: #cbd5e1;\n    white-space: nowrap;\n    overflow: hidden;\n    text-overflow: ellipsis;\n  }\n\n  .tile-platforms {\n    display: flex;\n    gap: 4px;\n    flex-wrap: wrap;\n  }\n\n  .plat-tag {\n    font-size: 9.5px;\n    padding: 1px 5px;\n    border-radius: 3px;\n    background: rgba(255,255,255,0.07);\n    color: var(--text-muted);\n    font-family: var(--font-mono);\n  }\n\n  .tile-progress {\n    height: 5px;\n    width: 100%;\n    background: #0f172a;\n    border-radius: 999px;\n    overflow: hidden;\n  }\n\n  .tile-progress-bar {\n    height: 100%;\n    background: linear-gradient(90deg, var(--accent-blue), var(--accent-emerald));\n    transition: width 0.3s ease;\n  }\n\n  .tile-foot {\n    display: flex;\n    justify-content: space-between;\n    font-size: 10.5px;\n    color: var(--text-muted);\n    font-family: var(--font-mono);\n  }\n\n  /* Tabs in Right Column */\n  .tabs {\n    display: flex;\n    border-bottom: 1px solid var(--border-subtle);\n    background: #0f172a;\n  }\n\n  .tab-btn {\n    flex: 1;\n    padding: 10px 6px;\n    text-align: center;\n    font-size: 11.5px;\n    font-weight: 600;\n    color: var(--text-muted);\n    background: transparent;\n    border: none;\n    border-bottom: 2px solid transparent;\n    cursor: pointer;\n  }\n\n  .tab-btn.active {\n    color: #fff;\n    border-bottom-color: var(--accent-blue);\n    background: rgba(59, 130, 246, 0.08);\n  }\n\n  .card {\n    background: var(--bg-card);\n    border: 1px solid var(--border-subtle);\n    border-radius: 9px;\n    padding: 11px;\n    display: flex;\n    flex-direction: column;\n    gap: 7px;\n  }\n\n  .card-title {\n    font-weight: 700;\n    font-size: 12.5px;\n    color: #fff;\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n  }\n\n  .kv-row {\n    display: flex;\n    justify-content: space-between;\n    font-size: 11.5px;\n    border-bottom: 1px solid rgba(255,255,255,0.04);\n    padding-bottom: 4px;\n  }\n\n  .kv-label { color: var(--text-muted); }\n  .kv-val   { font-family: var(--font-mono); font-weight: 600; }\n\n  .log-box {\n    background: #070b12;\n    border: 1px solid var(--border-subtle);\n    border-radius: 8px;\n    padding: 10px;\n    font-family: var(--font-mono);\n    font-size: 11px;\n    height: 220px;\n    overflow-y: auto;\n    display: flex;\n    flex-direction: column;\n    gap: 4px;\n  }\n\n  .log-line {\n    white-space: pre-wrap;\n    word-break: break-all;\n  }\n  .log-line .ts { color: var(--text-dim); }\n  .log-line .dev { color: #60a5fa; font-weight: 700; }\n  .log-line .ok { color: #34d399; }\n  .log-line .warn { color: #fbbf24; }\n\n  .input-row {\n    display: flex;\n    gap: 6px;\n  }\n\n  input[type="text"], select {\n    background: #0b111e;\n    border: 1px solid var(--border-subtle);\n    color: var(--text-main);\n    padding: 6px 9px;\n    border-radius: 6px;\n    font-size: 12px;\n    font-family: var(--font-mono);\n    width: 100%;\n  }\n\n  .kpi-grid {\n    display: grid;\n    grid-template-columns: repeat(4, 1fr);\n    gap: 8px;\n  }\n\n  .kpi-box {\n    background: var(--bg-card);\n    border: 1px solid var(--border-subtle);\n    border-radius: 8px;\n    padding: 9px 11px;\n  }\n\n  .kpi-val {\n    font-size: 18px;\n    font-weight: 800;\n    font-family: var(--font-mono);\n  }\n\n  .kpi-lbl {\n    font-size: 10.5px;\n    color: var(--text-muted);\n  }\n</style>\n</head>\n<body>\n\n<!-- TOP NAVIGATION & 1-CLICK CONTENT FACTORY BAR -->\n<header class="topbar">\n  <div class="brand">\n    <div class="brand-logo">iM2</div>\n    <div>\n      <div class="brand-title">iMouse 2.0 — 19-iPhone Marketing Farm Command Center</div>\n      <div class="brand-sub">Kernel Endpoint: <span id="endpointLabel">http://127.0.0.1:9913/api</span> • Lease-Enforced • 500x1080 Gaussian Jitter</div>\n    </div>\n  </div>\n\n  <div class="kernel-bar">\n    <span class="pill"><span class="dot green" id="kernelDot"></span><span id="kernelModeText">SIMULATED RACK + LIVE 9913 READY</span></span>\n    <span class="pill"><span class="dot blue"></span>Leases: <strong id="activeLeasesCount">0 / 19</strong></span>\n    <span class="pill"><span class="dot green"></span>Unique Clicks: <strong id="uniqueClicksCounter">0</strong> (0 Repeats)</span>\n  </div>\n\n  <div class="hero-actions">\n    <button class="btn btn-magic" onclick="triggerDailyContentFactory()">\n      ⚡ 1-Click: Auto-Create &amp; Deploy Today\'s Content\n    </button>\n    <button class="btn" onclick="triggerRackWarmupWave()">\n      🔥 Run Staggered Cohort Warmup\n    </button>\n    <button class="btn" onclick="probeLiveKernel()">\n      🔌 Connect Live 9913 Kernel\n    </button>\n    <button class="btn btn-stop" onclick="emergencyStopAll()">\n      🛑 Stop &amp; Release All (/input/stop)\n    </button>\n  </div>\n</header>\n\n<!-- MAIN 3-COLUMN WORKSPACE MIRRORING iMOUSE.CONSOLE -->\n<main class="workspace">\n\n  <!-- LEFT COLUMN: SELECTED PHONE 500x1080 LIVE PREVIEW & GAUSSIAN JITTER VISUALIZER -->\n  <section class="panel">\n    <div class="panel-header">\n      <div class="panel-title">\n        <span>📱 Selected Phone: <span id="selectedPhoneTitle" style="color:#60a5fa;font-family:var(--font-mono);">C24C</span></span>\n      </div>\n      <span class="badge badge-emerald" id="selectedPhoneBadge">MIRRORING</span>\n    </div>\n    <div class="panel-body">\n      <div class="phone-preview-wrap">\n        <div class="phone-bezel">\n          <div class="status-bar-mask">\n            <span>STATUS_BAR_PX = 60 (Masked)</span>\n            <span>500×1080 BMP</span>\n          </div>\n          <canvas id="previewCanvas" width="250" height="510"></canvas>\n        </div>\n      </div>\n\n      <div class="card">\n        <div class="card-title">\n          <span>🎯 Last Jittered Click Telemetry</span>\n          <span class="badge badge-blue" id="lastTargetBadge">ig_tab_create_plus</span>\n        </div>\n        <div class="kv-row"><span class="kv-label">500×1080 Pixel Coord:</span><span class="kv-val" id="lastCoordVal">(248, 1012)</span></div>\n        <div class="kv-row"><span class="kv-label">Approach Waypoint:</span><span class="kv-val" id="lastApproachVal">(239, 1004)</span></div>\n        <div class="kv-row"><span class="kv-label">Press Dwell / Ring Buffer:</span><span class="kv-val" id="lastDwellVal">81 ms • 48-tap unique</span></div>\n        <div class="kv-row"><span class="kv-label">Text Entry Strategy:</span><span class="kv-val" style="color:#34d399;">ON_SCREEN_QWERTY_JITTER</span></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span>⚡ Single-Phone Quick Actions</span></div>\n        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">\n          <button class="btn" onclick="simulateSingleUpload(\'IG_REEL\')">📸 IG Reel</button>\n          <button class="btn" onclick="simulateSingleUpload(\'IG_CAROUSEL\')">🖼️ IG Carousel</button>\n          <button class="btn" onclick="simulateSingleUpload(\'TT_VIDEO\')">🎵 TikTok Video</button>\n          <button class="btn" onclick="simulateSingleUpload(\'TT_PHOTO\')">📑 TT Photo Mode</button>\n          <button class="btn" onclick="simulateSingleUpload(\'X_VIDEO\')">𝕏 Video (Trim Guard)</button>\n          <button class="btn" onclick="simulateSingleUpload(\'YT_SHORT\')">▶️ YouTube Short</button>\n        </div>\n      </div>\n    </div>\n  </section>\n\n  <!-- CENTER COLUMN: 5-STAGE AUTO-CONTENT PIPELINE + 19-IPHONE WALL -->\n  <section class="panel">\n    <div class="panel-header">\n      <div class="panel-title">\n        <span>🖥️ 19-iPhone Rack Wall &amp; 1-Click Automated Content Pipeline</span>\n      </div>\n      <div style="display:flex;gap:8px;align-items:center;">\n        <span style="font-size:11px;color:var(--text-muted);">Filter Cohort:</span>\n        <select id="cohortFilter" onchange="renderPhoneWall()" style="width:130px;">\n          <option value="all">All 19 Phones</option>\n          <option value="1">Cohort 1 (Mon)</option>\n          <option value="2">Cohort 2 (Tue)</option>\n          <option value="3">Cohort 3 (Wed)</option>\n          <option value="4">Cohort 4 (Thu)</option>\n          <option value="5">Cohort 5 (Fri)</option>\n        </select>\n      </div>\n    </div>\n\n    <div class="panel-body">\n      <!-- KPI Summary Bar -->\n      <div class="kpi-grid">\n        <div class="kpi-box">\n          <div class="kpi-val" id="kpiContentGenerated">76</div>\n          <div class="kpi-lbl">Today\'s Assets Rendered (19×4)</div>\n        </div>\n        <div class="kpi-box">\n          <div class="kpi-val" style="color:#34d399;" id="kpiUploadsCompleted">42</div>\n          <div class="kpi-lbl">Native Mobile Uploads Live</div>\n        </div>\n        <div class="kpi-box">\n          <div class="kpi-val" style="color:#60a5fa;" id="kpiWarmupSessions">19 / 19</div>\n          <div class="kpi-lbl">Daily Trust Maintenance Done</div>\n        </div>\n        <div class="kpi-box">\n          <div class="kpi-val" style="color:#fbbf24;" id="kpiZeroViewAlerts">0 Flagged</div>\n          <div class="kpi-lbl">3–5 Clip Zero-View Guard</div>\n        </div>\n      </div>\n\n      <!-- 5-Stage Pipeline Strip -->\n      <div class="pipeline-strip" id="pipelineStrip">\n        <div class="stage-step" id="stage1">\n          <span class="stage-num">Stage 1 • AI Studio</span>\n          <span class="stage-name">Niche Script &amp; Render</span>\n          <span class="stage-desc">Generates hooks, Reels/Shorts, 4:5 carousels &amp; X threads per persona</span>\n        </div>\n        <div class="stage-step" id="stage2">\n          <span class="stage-num">Stage 2 • Anti-Dupe</span>\n          <span class="stage-name">pHash &amp; EXIF Spin</span>\n          <span class="stage-desc">Unique MD5/pHash per phone (1.5% crop, LUT shift, fresh iOS metadata)</span>\n        </div>\n        <div class="stage-step" id="stage3">\n          <span class="stage-num">Stage 3 • Media Pull</span>\n          <span class="stage-name">iOS Shortcut Sync</span>\n          <span class="stage-desc">Phones pull staged MP4/JPGs + clipboard caption from host port 9914</span>\n        </div>\n        <div class="stage-step" id="stage4">\n          <span class="stage-num">Stage 4 • Kernel 9913</span>\n          <span class="stage-name">Gaussian Upload</span>\n          <span class="stage-desc">Acquires lease, clicks non-repeating 500×1080 boxes across IG/TT/X/YT</span>\n        </div>\n        <div class="stage-step" id="stage5">\n          <span class="stage-num">Stage 5 • Funnel</span>\n          <span class="stage-name">Golden-Hour &amp; DM</span>\n          <span class="stage-desc">Pins CTA comment, replies to early comments &amp; auto-DMs keyword leads</span>\n        </div>\n      </div>\n\n      <!-- 19-Phone Grid -->\n      <div class="phone-wall" id="phoneWallGrid"></div>\n    </div>\n  </section>\n\n  <!-- RIGHT COLUMN: MARKETING AUTOMATION MODULES & KERNEL RPC LOG -->\n  <section class="panel right-col">\n    <div class="tabs">\n      <button class="tab-btn active" onclick="switchTab(\'tabPersona\', this)">1. Persona &amp; Content</button>\n      <button class="tab-btn" onclick="switchTab(\'tabStaging\', this)">2. Media Pull &amp; Warmup</button>\n      <button class="tab-btn" onclick="switchTab(\'tabFunnel\', this)">3. Funnel &amp; Guardrails</button>\n    </div>\n\n    <div class="panel-body" id="tabPersona">\n      <div class="card">\n        <div class="card-title">\n          <span>🎯 Selected Phone Marketing Profile</span>\n          <span class="badge badge-purple" id="profileCohortBadge">Cohort 1</span>\n        </div>\n        <div class="kv-row"><span class="kv-label">Device ID / Receiver:</span><span class="kv-val" id="profDeviceId">C24C (iMouse-C24C)</span></div>\n        <div class="kv-row"><span class="kv-label">Assigned Niche / Offer:</span><span class="kv-val" id="profNiche">AI SaaS Clipping &amp; Growth</span></div>\n        <div class="kv-row"><span class="kv-label">Target Persona Voice:</span><span class="kv-val" id="profVoice">Founder Breakdown / Fast Hook</span></div>\n        <div class="kv-row"><span class="kv-label">CTA Keyword Trigger:</span><span class="kv-val" id="profKeyword">Comment "SYSTEM" → Auto-DM</span></div>\n        <div class="kv-row"><span class="kv-label">Warmup Trust Stage:</span><span class="kv-val" id="profWarmupStage">Day 16 • Phase 4 (4/day max)</span></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title">\n          <span>🎬 Today\'s Auto-Generated Content Slate</span>\n          <button class="btn" style="padding:3px 8px;font-size:11px;" onclick="regenerateSelectedSlate()">🔄 Spin New Hooks</button>\n        </div>\n        <div id="contentSlateList" style="display:flex;flex-direction:column;gap:6px;"></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span>📡 Live Kernel 9913 JSON-RPC Stream</span></div>\n        <div class="log-box" id="rpcLogBox"></div>\n      </div>\n    </div>\n\n    <div class="panel-body" id="tabStaging" style="display:none;">\n      <div class="card">\n        <div class="card-title">\n          <span>📥 Zero-Touch PC → iPhone Media Staging</span>\n          <span class="badge badge-emerald">PORT 9914 ACTIVE</span>\n        </div>\n        <div class="kv-row"><span class="kv-label">Host Staging Folder:</span><span class="kv-val">output/media-stage/{deviceid}/</span></div>\n        <div class="kv-row"><span class="kv-label">iPhone Ingestion:</span><span class="kv-val">iOS Shortcut "iMousePull"</span></div>\n        <div class="kv-row"><span class="kv-label">pHash / EXIF Uniqueness:</span><span class="kv-val" style="color:#34d399;">+1.4% Crop • 1.02x Audio • New UUID</span></div>\n        <div class="kv-row"><span class="kv-label">Camera Roll Cleanup:</span><span class="kv-val">Auto-delete staged clips &gt; 24h</span></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span>🔥 4-Phase Warmup &amp; Cohort Scheduler</span></div>\n        <div class="kv-row"><span class="kv-label">Phase 1 (Days 1–3):</span><span class="kv-val">0 Uploads • 15m Watch • 2 Comments</span></div>\n        <div class="kv-row"><span class="kv-label">Phase 2 (Days 4–7):</span><span class="kv-val">1 Upload/d (IG waits til Day 5–6)</span></div>\n        <div class="kv-row"><span class="kv-label">Phase 3 (Days 8–14):</span><span class="kv-val">1–2 Uploads/d + 3.5–7.5h Buffer</span></div>\n        <div class="kv-row"><span class="kv-label">Phase 4 (Day 15+):</span><span class="kv-val">2–4 Uploads/d + 8m Trust Maint.</span></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span>🔌 Live Kernel Endpoint Configuration</span></div>\n        <div class="input-row">\n          <input type="text" id="kernelUrlInput" value="http://127.0.0.1:9913/api" />\n          <button class="btn" onclick="probeLiveKernel()">Test</button>\n        </div>\n      </div>\n    </div>\n\n    <div class="panel-body" id="tabFunnel" style="display:none;">\n      <div class="card">\n        <div class="card-title">\n          <span>💬 Conversion Funnel &amp; Golden-Hour Loop</span>\n          <span class="badge badge-blue">ENABLED</span>\n        </div>\n        <div class="kv-row"><span class="kv-label">Pinned CTA Comment:</span><span class="kv-val">Auto-posts 45s after publish</span></div>\n        <div class="kv-row"><span class="kv-label">Comment-to-DM Trigger:</span><span class="kv-val">OCR watches notifications tab</span></div>\n        <div class="kv-row"><span class="kv-label">Trending Audio Mixer:</span><span class="kv-val">Attaches niche sound @ 3% vol</span></div>\n        <div class="kv-row"><span class="kv-label">Story Sticker CTA:</span><span class="kv-val">Link Sticker + Poll Sticker</span></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title">\n          <span>🛡️ Anti-Shadowban &amp; Hardware Guardrails</span>\n          <span class="badge badge-emerald">ALL GREEN</span>\n        </div>\n        <div class="kv-row"><span class="kv-label">3–5 Clip Zero-View Gate:</span><span class="kv-val">Auto-pauses if &lt;5 views after 24h</span></div>\n        <div class="kv-row"><span class="kv-label">X 45s Video Trim Guard:</span><span class="kv-val">Bézier drags handle [340→470]</span></div>\n        <div class="kv-row"><span class="kv-label">Home / Tab Contamination:</span><span class="kv-val">Dismisses keyboard at (445, 548)</span></div>\n        <div class="kv-row"><span class="kv-label">Uncertain Input Retry:</span><span class="kv-val" style="color:#fda4af;">NEVER (Strict 8s Deadline)</span></div>\n      </div>\n    </div>\n  </section>\n\n</main>\n\n<script>\n  // 19-Phone Rack Inventory (matching GEMINI-HANDOFF.md C24C, C241 + 17 rack slots)\n  const RACK_PHONES = [\n    { id: "C24C",   cohort: 1, day: 18, state: "mirroring", lease: "idle", niche: "AI Workflow & SaaS Clips",     voice: "Founder Breakdown", kw: "SYSTEM",   views24h: "14.2K", progress: 100 },\n    { id: "C241",   cohort: 1, day: 16, state: "mirroring", lease: "idle", niche: "E-Com Product Teardowns",      voice: "Case Study Hook",   kw: "STORE",    views24h: "9.8K",  progress: 100 },\n    { id: "RACK-03",cohort: 1, day: 15, state: "mirroring", lease: "idle", niche: "B2B Lead Gen Automation",      voice: "Direct Proof",      kw: "LEADS",    views24h: "11.4K", progress: 100 },\n    { id: "RACK-04",cohort: 1, day: 15, state: "mirroring", lease: "idle", niche: "Creator Economy Playbooks",    voice: "Storyteller",       kw: "GROWTH",   views24h: "18.9K", progress: 100 },\n    { id: "RACK-05",cohort: 2, day: 11, state: "mirroring", lease: "idle", niche: "Fitness & Biohacking Habits",  voice: "High-Energy Coach", kw: "PROTOCOL", views24h: "7.6K",  progress: 75 },\n    { id: "RACK-06",cohort: 2, day: 11, state: "mirroring", lease: "idle", niche: "Personal Finance & Investing", voice: "Data Analyst",      kw: "SHEET",    views24h: "12.1K", progress: 75 },\n    { id: "RACK-07",cohort: 2, day: 10, state: "mirroring", lease: "idle", niche: "Real Estate Deal Analysis",    voice: "Local Deal Hunter", kw: "DEAL",     views24h: "6.3K",  progress: 75 },\n    { id: "RACK-08",cohort: 2, day: 10, state: "mirroring", lease: "idle", niche: "Remote Tech Career Tips",      voice: "Senior Engineer",   kw: "RESUME",   views24h: "8.4K",  progress: 75 },\n    { id: "RACK-09",cohort: 3, day: 6,  state: "mirroring", lease: "idle", niche: "MedSpa & Skincare Science",    voice: "Clinical Aesthetic",kw: "GLOW",     views24h: "3.1K",  progress: 50 },\n    { id: "RACK-10",cohort: 3, day: 6,  state: "mirroring", lease: "idle", niche: "Mechanical Keyboards & Desk",  voice: "Minimalist Setup",  kw: "DESK",     views24h: "5.5K",  progress: 50 },\n    { id: "RACK-11",cohort: 3, day: 5,  state: "mirroring", lease: "idle", niche: "Indie Game Dev Logs",          voice: "Behind-The-Scenes", kw: "WISHLIST", views24h: "4.2K",  progress: 50 },\n    { id: "RACK-12",cohort: 3, day: 5,  state: "mirroring", lease: "idle", niche: "Specialty Coffee & Gear",      voice: "Barista Craft",     kw: "BREW",     views24h: "2.9K",  progress: 50 },\n    { id: "RACK-13",cohort: 4, day: 3,  state: "mirroring", lease: "idle", niche: "Culinary Knife & Cookware",    voice: "Chef Technique",    kw: "CHEF",     views24h: "Warmup",progress: 25 },\n    { id: "RACK-14",cohort: 4, day: 3,  state: "mirroring", lease: "idle", niche: "Smart Home & HomeLab",         voice: "Hardware Tinkerer", kw: "LAB",      views24h: "Warmup",progress: 25 },\n    { id: "RACK-15",cohort: 4, day: 2,  state: "mirroring", lease: "idle", niche: "Streetwear & Sneaker Drops",   voice: "Culture Curator",   kw: "DROP",     views24h: "Warmup",progress: 25 },\n    { id: "RACK-16",cohort: 4, day: 2,  state: "mirroring", lease: "idle", niche: "Pet Nutrition & Training",     voice: "Vet Approved",      kw: "TREATS",   views24h: "Warmup",progress: 25 },\n    { id: "RACK-17",cohort: 5, day: 1,  state: "mirroring", lease: "idle", niche: "Luxury Watch Microbrands",     voice: "Collector Review",  kw: "DIAL",     views24h: "Warmup",progress: 15 },\n    { id: "RACK-18",cohort: 5, day: 1,  state: "mirroring", lease: "idle", niche: "EV & Garage Detailing",        voice: "Pro Detailer",      kw: "COAT",     views24h: "Warmup",progress: 15 },\n    { id: "RACK-19",cohort: 5, day: 1,  state: "mirroring", lease: "idle", niche: "Travel Hacks & Credit Points", voice: "Points Optimizer",  kw: "MILES",    views24h: "Warmup",progress: 15 }\n  ];\n\n  // 500x1080 Bounding Boxes from imouse_social_automation.py\n  const UI_BOXES = {\n    ig_tab_create_plus:   { x1: 215, y1: 985, x2: 285, y2: 1040, label: "IG \'+\' Create" },\n    ig_mode_reel:         { x1: 330, y1: 905, x2: 390, y2: 950,  label: "IG Mode: REEL" },\n    ig_carousel_multi:    { x1: 390, y1: 515, x2: 460, y2: 570,  label: "IG Carousel Multi" },\n    ig_gallery_slot_1:    { x1: 15,  y1: 605, x2: 155, y2: 735,  label: "Gallery Slot #1" },\n    ig_caption_field:     { x1: 40,  y1: 235, x2: 450, y2: 365,  label: "Caption Field" },\n    keyboard_dismiss:     { x1: 410, y1: 520, x2: 485, y2: 575,  label: "Safe Dismiss" },\n    ig_publish_share:     { x1: 40,  y1: 970, x2: 460, y2: 1035, label: "Publish / Share" },\n    tt_upload_gallery:    { x1: 380, y1: 800, x2: 460, y2: 875,  label: "TT Upload Gallery" },\n    x_video_trim_handle:  { x1: 340, y1: 840, x2: 480, y2: 905,  label: "X 45s Trim Guard" },\n    yt_audience_not_kids: { x1: 40,  y1: 580, x2: 450, y2: 645,  label: "YT Not Made For Kids" }\n  };\n\n  let selectedPhoneId = "C24C";\n  let uniqueClicksTotal = 0;\n  const tapHistory = []; // Stores recent {x, y, target} in 500x1080 space\n\n  function gaussRandom(mean, stdev) {\n    const u = 1 - Math.random();\n    const v = Math.random();\n    const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);\n    return z * stdev + mean;\n  }\n\n  function sampleGaussianClick(boxKey) {\n    const b = UI_BOXES[boxKey] || UI_BOXES.ig_tab_create_plus;\n    const mx = Math.max(1, Math.round((b.x2 - b.x1) * 0.14));\n    const my = Math.max(1, Math.round((b.y2 - b.y1) * 0.14));\n    const sx1 = b.x1 + mx, sx2 = b.x2 - mx;\n    const sy1 = b.y1 + my, sy2 = b.y2 - my;\n    const cx = (sx1 + sx2) / 2, cy = (sy1 + sy2) / 2;\n    const sigX = Math.max(1.5, (sx2 - sx1) * 0.24);\n    const sigY = Math.max(1.5, (sy2 - sy1) * 0.24);\n\n    let x = Math.round(cx), y = Math.round(cy);\n    for (let i = 0; i < 60; i++) {\n      let rx = Math.max(sx1, Math.min(sx2, Math.round(gaussRandom(cx, sigX))));\n      let ry = Math.max(sy1, Math.min(sy2, Math.round(gaussRandom(cy, sigY))));\n      if (!tapHistory.some(p => p.x === rx && p.y === ry)) {\n        x = rx; y = ry; break;\n      }\n    }\n    const preX = Math.max(0, Math.min(499, x + Math.floor(Math.random() * 21) - 10));\n    const preY = Math.max(60, Math.min(1079, y + Math.floor(Math.random() * 21) - 10));\n    const dwell = Math.floor(54 + Math.random() * 75);\n\n    tapHistory.push({ x, y, preX, preY, dwell, boxKey });\n    if (tapHistory.length > 48) tapHistory.shift();\n    uniqueClicksTotal++;\n\n    document.getElementById("uniqueClicksCounter").textContent = uniqueClicksTotal;\n    document.getElementById("lastTargetBadge").textContent = boxKey;\n    document.getElementById("lastCoordVal").textContent = `(${x}, ${y})`;\n    document.getElementById("lastApproachVal").textContent = `(${preX}, ${preY})`;\n    document.getElementById("lastDwellVal").textContent = `${dwell} ms • 48-tap unique`;\n\n    drawPreviewCanvas(boxKey);\n    return { x, y, preX, preY, dwell };\n  }\n\n  function drawPreviewCanvas(activeBoxKey) {\n    const canvas = document.getElementById("previewCanvas");\n    const ctx = canvas.getContext("2d");\n    // Canvas is 250x510 representing 500x(1080-60) -> scale factor 0.5\n    ctx.clearRect(0, 0, canvas.width, canvas.height);\n\n    // Subtle grid\n    ctx.strokeStyle = "rgba(59, 130, 246, 0.08)";\n    ctx.lineWidth = 1;\n    for (let x = 0; x <= 250; x += 25) {\n      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 510); ctx.stroke();\n    }\n    for (let y = 0; y <= 510; y += 25) {\n      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(250, y); ctx.stroke();\n    }\n\n    // Draw UI Bounding Boxes (scaled by 0.5, y shifted by -60px status bar)\n    Object.entries(UI_BOXES).forEach(([key, b]) => {\n      const rx = b.x1 * 0.5;\n      const ry = (b.y1 - 60) * 0.5;\n      const rw = (b.x2 - b.x1) * 0.5;\n      const rh = (b.y2 - b.y1) * 0.5;\n      const isActive = key === activeBoxKey;\n\n      ctx.strokeStyle = isActive ? "#34d399" : "rgba(148, 163, 184, 0.35)";\n      ctx.fillStyle = isActive ? "rgba(16, 185, 129, 0.14)" : "rgba(30, 41, 59, 0.45)";\n      ctx.lineWidth = isActive ? 1.8 : 1;\n      ctx.fillRect(rx, ry, rw, rh);\n      ctx.strokeRect(rx, ry, rw, rh);\n\n      ctx.fillStyle = isActive ? "#a7f3d0" : "#94a3b8";\n      ctx.font = "9px monospace";\n      ctx.fillText(b.label, rx + 3, ry + 10);\n    });\n\n    // Draw recent Gaussian click points\n    tapHistory.forEach((pt, idx) => {\n      const cx = pt.x * 0.5;\n      const cy = (pt.y - 60) * 0.5;\n      const isNewest = idx === tapHistory.length - 1;\n      ctx.beginPath();\n      ctx.arc(cx, cy, isNewest ? 4.2 : 2.3, 0, Math.PI * 2);\n      ctx.fillStyle = isNewest ? "#f43f5e" : "rgba(59, 130, 246, 0.75)";\n      ctx.fill();\n      if (isNewest) {\n        ctx.strokeStyle = "#fff";\n        ctx.lineWidth = 1.2;\n        ctx.stroke();\n      }\n    });\n  }\n\n  function appendRpcLog(deviceId, fun, detail, statusClass = "ok") {\n    const box = document.getElementById("rpcLogBox");\n    const now = new Date().toISOString().slice(11, 23);\n    const div = document.createElement("div");\n    div.className = "log-line";\n    div.innerHTML = `<span class="ts">[${now}]</span> <span class="dev">${deviceId}</span> <span>${fun}</span> → <span class="${statusClass}">${detail}</span>`;\n    box.prepend(div);\n    while (box.children.length > 60) box.removeChild(box.lastChild);\n  }\n\n  function renderPhoneWall() {\n    const filter = document.getElementById("cohortFilter").value;\n    const grid = document.getElementById("phoneWallGrid");\n    grid.innerHTML = "";\n\n    const activeCount = RACK_PHONES.filter(p => p.lease !== "idle").length;\n    document.getElementById("activeLeasesCount").textContent = `${activeCount} / 19`;\n\n    RACK_PHONES.filter(p => filter === "all" || String(p.cohort) === filter).forEach(phone => {\n      const tile = document.createElement("div");\n      tile.className = "phone-tile" + (phone.id === selectedPhoneId ? " selected" : "");\n      tile.onclick = () => selectPhone(phone.id);\n\n      let leaseBadgeClass = "badge-emerald";\n      let leaseText = "IDLE • READY";\n      if (phone.lease === "uploading") { leaseBadgeClass = "badge-blue"; leaseText = "LEASE: UPLOAD"; }\n      else if (phone.lease === "warmup") { leaseBadgeClass = "badge-purple"; leaseText = "LEASE: WARMUP"; }\n      else if (phone.lease === "staging") { leaseBadgeClass = "badge-amber"; leaseText = "PULLING MEDIA"; }\n      else if (phone.lease === "stopped") { leaseBadgeClass = "badge-rose"; leaseText = "STOPPED"; }\n\n      const canUpload = phone.day >= 4;\n\n      tile.innerHTML = `\n        <div class="tile-top">\n          <span class="tile-id">${phone.id}</span>\n          <span class="badge ${leaseBadgeClass}">${leaseText}</span>\n        </div>\n        <div class="tile-niche">${phone.niche}</div>\n        <div class="tile-platforms">\n          <span class="plat-tag">IG ${phone.day >= 5 ? "✓" : "Warm"}</span>\n          <span class="plat-tag">TT ${canUpload ? "✓" : "Warm"}</span>\n          <span class="plat-tag">𝕏 ${canUpload ? "✓" : "Warm"}</span>\n          <span class="plat-tag">YT ${canUpload ? "✓" : "Warm"}</span>\n        </div>\n        <div class="tile-progress">\n          <div class="tile-progress-bar" style="width:${phone.progress}%;"></div>\n        </div>\n        <div class="tile-foot">\n          <span>Cohort ${phone.cohort} • Day ${phone.day}</span>\n          <span>24h: ${phone.views24h}</span>\n        </div>\n      `;\n      grid.appendChild(tile);\n    });\n  }\n\n  function selectPhone(id) {\n    selectedPhoneId = id;\n    const p = RACK_PHONES.find(x => x.id === id) || RACK_PHONES[0];\n    document.getElementById("selectedPhoneTitle").textContent = p.id;\n    document.getElementById("profDeviceId").textContent = `${p.id} (iMouse-${p.id})`;\n    document.getElementById("profNiche").textContent = p.niche;\n    document.getElementById("profVoice").textContent = p.voice;\n    document.getElementById("profKeyword").textContent = `Comment "${p.kw}" → Auto-DM`;\n    document.getElementById("profileCohortBadge").textContent = `Cohort ${p.cohort}`;\n\n    const phaseLabel = p.day <= 3 ? "Phase 1 (0 Uploads)" : p.day <= 7 ? "Phase 2 (1/day)" : p.day <= 14 ? "Phase 3 (2/day)" : "Phase 4 (4/day max)";\n    document.getElementById("profWarmupStage").textContent = `Day ${p.day} • ${phaseLabel}`;\n\n    renderContentSlate(p);\n    renderPhoneWall();\n    sampleGaussianClick("ig_tab_create_plus");\n  }\n\n  function renderContentSlate(p) {\n    const container = document.getElementById("contentSlateList");\n    const isWarmupOnly = p.day <= 3;\n    if (isWarmupOnly) {\n      container.innerHTML = `\n        <div style="padding:8px;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.35);border-radius:6px;font-size:11.5px;color:#fcd34d;">\n          🛡️ <strong>Phase 1 Trust Protection (Day ${p.day}):</strong> Uploads are locked to 0 today. Scheduled for 2×15 min niche consumption + 2 genuine sentence comments.\n        </div>\n      `;\n      return;\n    }\n\n    const items = [\n      { plat: "Instagram Reel + Story", fmt: "IG_REEL", hook: `"3 mistakes killing your ${p.niche.split(\' \')[0]} results in 2026..."`, hash: "pHash #8f3a • 9:16 MP4" },\n      { plat: "Instagram 7-Slide Carousel", fmt: "IG_CAROUSEL", hook: `"Step-by-step ${p.niche} framework (Save this) →"`, hash: "4:5 Locked Crop • 7 JPGs" },\n      { plat: "TikTok Video + Photo Mode", fmt: "TT_VIDEO", hook: `"How we automated ${p.niche.toLowerCase()} from scratch"`, hash: "Trending Audio @ 3% Vol" },\n      { plat: "X Native Video + 4-Tweet Thread", fmt: "X_VIDEO", hook: `"Here is the exact breakdown for ${p.niche} (Thread 🧵):"`, hash: "45s Trim Guard Active" },\n      { plat: "YouTube Short + Community Poll", fmt: "YT_SHORT", hook: `"Watch this before starting ${p.niche} #shorts"`, hash: "Not-For-Kids Verified" }\n    ];\n\n    container.innerHTML = items.map(it => `\n      <div style="padding:7px 9px;background:#0c1322;border:1px solid var(--border-subtle);border-radius:6px;display:flex;justify-content:space-between;align-items:center;gap:8px;">\n        <div>\n          <div style="font-weight:700;font-size:11.5px;color:#93c5fd;">${it.plat}</div>\n          <div style="font-size:11px;color:var(--text-main);">${it.hook}</div>\n          <div style="font-size:10px;color:var(--text-muted);font-family:var(--font-mono);">${it.hash} • CTA: "${p.kw}"</div>\n        </div>\n        <button class="btn" style="padding:4px 8px;font-size:10.5px;" onclick="simulateSingleUpload(\'${it.fmt}\')">Deploy</button>\n      </div>\n    `).join("");\n  }\n\n  function regenerateSelectedSlate() {\n    const p = RACK_PHONES.find(x => x.id === selectedPhoneId) || RACK_PHONES[0];\n    appendRpcLog(p.id, "content/spin-hooks", `Generated fresh niche hooks & pHash variants for \'${p.niche}\'`, "ok");\n    renderContentSlate(p);\n  }\n\n  function simulateSingleUpload(fmt) {\n    const p = RACK_PHONES.find(x => x.id === selectedPhoneId) || RACK_PHONES[0];\n    p.lease = "uploading";\n    renderPhoneWall();\n\n    const seq = [\n      { box: "ig_tab_create_plus", fun: "/input/acquire", msg: "lease_ms=120000 token=tok_" + Math.random().toString(16).slice(2, 8) },\n      { box: "ig_mode_reel",       fun: "/mouse/click",   msg: `format=${fmt} Gaussian safe box` },\n      { box: "ig_gallery_slot_1",  fun: "/mouse/click",   msg: "selected staged Camera Roll slot #1" },\n      { box: "ig_caption_field",   fun: "/mouse/click",   msg: "ON_SCREEN_QWERTY_JITTER caption entry" },\n      { box: "keyboard_dismiss",   fun: "/mouse/click",   msg: "dismissed keyboard via safe zone (no Home Tab)" },\n      { box: "ig_publish_share",   fun: "/input/release", msg: "upload published & lease token revoked" }\n    ];\n\n    seq.forEach((step, idx) => {\n      setTimeout(() => {\n        const c = sampleGaussianClick(step.box);\n        appendRpcLog(p.id, step.fun, `(${c.x}, ${c.y}) dwell=${c.dwell}ms • ${step.msg}`, "ok");\n        if (idx === seq.length - 1) {\n          p.lease = "idle";\n          const curKpi = parseInt(document.getElementById("kpiUploadsCompleted").textContent, 10) || 42;\n          document.getElementById("kpiUploadsCompleted").textContent = curKpi + 1;\n          renderPhoneWall();\n        }\n      }, idx * 320);\n    });\n  }\n\n  function triggerDailyContentFactory() {\n    const stages = ["stage1", "stage2", "stage3", "stage4", "stage5"];\n    stages.forEach(s => {\n      document.getElementById(s).classList.remove("active", "done");\n    });\n\n    RACK_PHONES.forEach(p => {\n      if (p.day >= 4) { p.lease = "staging"; p.progress = 20; }\n      else { p.lease = "warmup"; p.progress = 30; }\n    });\n    renderPhoneWall();\n\n    const stageMessages = [\n      "Stage 1: Generated niche scripts, Reels/Shorts & 4:5 carousels across 19 accounts",\n      "Stage 2: Applied unique pHash crop/LUT/audio shifts & fresh iOS EXIF metadata",\n      "Stage 3: Triggered iOS Shortcut \'iMousePull\' from port 9914 into Camera Roll",\n      "Stage 4: Executing lease-isolated 500×1080 Gaussian uploads on C24C..RACK-19",\n      "Stage 5: Pinned CTA comments & armed Comment-to-DM keyword watchers"\n    ];\n\n    stages.forEach((stageId, idx) => {\n      setTimeout(() => {\n        if (idx > 0) {\n          document.getElementById(stages[idx - 1]).classList.remove("active");\n          document.getElementById(stages[idx - 1]).classList.add("done");\n        }\n        document.getElementById(stageId).classList.add("active");\n        appendRpcLog("FARM-ORCH", `pipeline/${stageId}`, stageMessages[idx], "ok");\n\n        RACK_PHONES.forEach(p => {\n          p.progress = Math.min(100, (idx + 1) * 20);\n          if (idx === 3 && p.day >= 4) p.lease = "uploading";\n        });\n        sampleGaussianClick(Object.keys(UI_BOXES)[idx % Object.keys(UI_BOXES).length]);\n        renderPhoneWall();\n\n        if (idx === stages.length - 1) {\n          setTimeout(() => {\n            document.getElementById(stageId).classList.remove("active");\n            document.getElementById(stageId).classList.add("done");\n            RACK_PHONES.forEach(p => { p.lease = "idle"; p.progress = 100; });\n            renderPhoneWall();\n            appendRpcLog("FARM-ORCH", "/input/release", "All 19 phone leases cleanly released; Golden-Hour monitors active", "ok");\n          }, 600);\n        }\n      }, idx * 650);\n    });\n  }\n\n  function triggerRackWarmupWave() {\n    RACK_PHONES.forEach((p, i) => {\n      setTimeout(() => {\n        p.lease = "warmup";\n        renderPhoneWall();\n        const c = sampleGaussianClick("ig_tab_create_plus");\n        appendRpcLog(p.id, "/mouse/swipe", `Cohort ${p.cohort} Day ${p.day} warmup: len=0.71 dur=385ms + like (${c.x},${c.y})`, "ok");\n        setTimeout(() => {\n          p.lease = "idle";\n          renderPhoneWall();\n        }, 700);\n      }, i * 120);\n    });\n  }\n\n  function emergencyStopAll() {\n    RACK_PHONES.forEach(p => { p.lease = "stopped"; });\n    renderPhoneWall();\n    appendRpcLog("ALL-PHONES", "/input/stop", "Emergency first-click Stop sent; all active tokens revoked", "warn");\n  }\n\n  async function probeLiveKernel() {\n    const baseUrl = document.getElementById("kernelUrlInput").value.replace(/\\/$/, "");\n    document.getElementById("endpointLabel").textContent = baseUrl;\n    if (baseUrl.includes(":9911")) {\n      appendRpcLog("GUARD", "PORT-CHECK", "Refusing vendor port 9911 per GEMINI-HANDOFF.md!", "warn");\n      return;\n    }\n    try {\n      const resp = await fetch(baseUrl + "/kernel/status", { method: "GET" });\n      const json = await resp.json();\n      document.getElementById("kernelModeText").textContent = "LIVE KERNEL 9913 CONNECTED";\n      appendRpcLog("KERNEL", "/kernel/status", `Connected live build: ${json?.data?.build_identity || "ok"}`, "ok");\n    } catch (err) {\n      appendRpcLog("KERNEL", "/kernel/status", "Local 9913 kernel unreachable from browser sandbox (running in interactive simulation mode)", "warn");\n    }\n  }\n\n  function switchTab(tabId, btnEl) {\n    ["tabPersona", "tabStaging", "tabFunnel"].forEach(id => {\n      document.getElementById(id).style.display = id === tabId ? "flex" : "none";\n    });\n    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));\n    btnEl.classList.add("active");\n  }\n\n  \n  // --- LIVE 7-LAYER BACKEND API BRIDGE (Connected to imouse_farm_server.py :9914) ---\n  async function callFarmBackend(endpoint, payload = null) {\n    try {\n      const opts = payload\n        ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }\n        : { method: "GET" };\n      const resp = await fetch(endpoint, opts);\n      if (!resp.ok) return null;\n      return await resp.json();\n    } catch (_) {\n      return null;\n    }\n  }\n\n  async function syncFromBackendState() {\n    const data = await callFarmBackend("/api/farm/state");\n    if (!data || !data.personas) return;\n    document.getElementById("kernelModeText").textContent = data.liveKernelConnected\n      ? "7-LAYER BACKEND + LIVE 9913 KERNEL"\n      : "7-LAYER BACKEND ACTIVE (MOCK 9913)";\n    data.personas.forEach(bp => {\n      const local = RACK_PHONES.find(p => p.id === bp.device_id);\n      if (local) {\n        local.cohort = bp.cohort;\n        local.day = bp.account_day;\n        local.niche = bp.niche;\n        local.voice = bp.brand_voice;\n        local.kw = bp.cta_keyword;\n        local.views24h = bp.paused_zero_view ? "0-VIEW PAUSED" : (bp.account_day <= 3 ? "Warmup" : `${(bp.views_24h / 1000).toFixed(1)}K`);\n        if (bp.paused_zero_view) local.lease = "stopped";\n      }\n    });\n    const flagged = data.personas.filter(p => p.paused_zero_view).length;\n    document.getElementById("kpiZeroViewAlerts").textContent = `${flagged} Flagged`;\n    renderPhoneWall();\n  }\n\n  // Hook into existing UI buttons so they execute real Python 7-layer backend calls\n  const _origTriggerDaily = triggerDailyContentFactory;\n  triggerDailyContentFactory = async function() {\n    _origTriggerDaily();\n    const res = await callFarmBackend("/api/farm/auto-create-and-deploy", { cohort: document.getElementById("cohortFilter").value });\n    if (res && res.summary) {\n      document.getElementById("kpiContentGenerated").textContent = res.summary.assetsRendered;\n      document.getElementById("kpiUploadsCompleted").textContent = res.summary.uploadsExecuted;\n      appendRpcLog("7-LAYER-BACKEND", "/api/farm/auto-create-and-deploy",\n        `SQLite + Pillow rendered ${res.summary.assetsRendered} 4:5 slides, spun pHashes, executed ${res.summary.uploadsExecuted} uploads & pinned CTAs`, "ok");\n      await syncFromBackendState();\n    }\n  };\n\n  const _origSimulateSingle = simulateSingleUpload;\n  simulateSingleUpload = async function(fmt) {\n    _origSimulateSingle(fmt);\n    const fmtMap = {\n      IG_REEL: ["instagram", "ig_reel"],\n      IG_CAROUSEL: ["instagram", "ig_carousel"],\n      TT_VIDEO: ["tiktok", "tt_video"],\n      TT_PHOTO: ["tiktok", "tt_photo_carousel"],\n      X_VIDEO: ["x", "x_video"],\n      YT_SHORT: ["youtube", "yt_short"]\n    };\n    const [platform, upload_format] = fmtMap[fmt] || ["instagram", "ig_reel"];\n    const res = await callFarmBackend("/api/farm/upload-single", {\n      device_id: selectedPhoneId,\n      platform,\n      upload_format\n    });\n    if (res && res.result && res.result.clickCoordinates) {\n      res.result.clickCoordinates.slice(-5).forEach(([target, x, y, dwell]) => {\n        tapHistory.push({ x, y, preX: x - 4, preY: y - 4, dwell, boxKey: target });\n        if (tapHistory.length > 48) tapHistory.shift();\n      });\n      drawPreviewCanvas("ig_publish_share");\n      appendRpcLog(selectedPhoneId, "Backend:SocialUploadOrchestrator",\n        `Executed ${res.result.totalClicks} real Gaussian clicks for ${upload_format}`, "ok");\n    }\n  };\n\n  const _origWarmupWave = triggerRackWarmupWave;\n  triggerRackWarmupWave = async function() {\n    _origWarmupWave();\n    const res = await callFarmBackend("/api/farm/warmup-wave", { cohort: document.getElementById("cohortFilter").value });\n    if (res && res.sessionsRun !== undefined) {\n      appendRpcLog("WARMUP-ENGINE", "/api/farm/warmup-wave",\n        `Completed ${res.sessionsRun} warmup sessions across cohort; timestamps saved to SQLite`, "ok");\n      await syncFromBackendState();\n    }\n  };\n\n  setTimeout(syncFromBackendState, 300);\n\n  // Initialize\n  selectPhone("C24C");\n  appendRpcLog("C24C", "/kernel/status", "input_leases_required=true • 500x1080 BMP stream ready", "ok");\n</script>\n</body>\n</html>\n'


def load_dashboard_html() -> str:
    html_file = HERE / "imouse_farm_command_center.html"
    if html_file.exists():
        try:
            return html_file.read_text(encoding="utf-8")
        except Exception:
            pass
    return DASHBOARD_HTML


class FarmBackendRuntime:
    """Holds live instances of all 7 Farm Layers backed by SQLite."""

    def __init__(
        self,
        db_path: Path | None = None,
        stage_root: Path | None = None,
        port: int = DEFAULT_PORT,
        execution_mode: str = "simulate",
    ) -> None:
        if execution_mode not in ("simulate", "live"):
            raise ValueError("Execution mode must be simulate or live.")
        self.execution_mode = execution_mode
        self.operation_lock = threading.RLock()
        source = Path(__file__).resolve().parent
        import hashlib
        self.source_hash = hashlib.sha256(b"".join((source / name).read_bytes() for name in ("imouse_farm_server.py", "imouse_social_automation.py", "farm_jobs.py", "farm_drafts.py", "farm_media_transfer.py", "farm_transfers.py", "farm_capabilities.py", "farm_video.py", "farm_observations.py", "Read-FarmImageText.ps1", "farm_preparation_schedule.py", "farm_frame_evidence.py", "farm_draft_verification.py"))).hexdigest()
        db_path = db_path or Path("output/farm-data/v2") / execution_mode / "imouse_farm.db"
        stage_root = stage_root or Path("output/media-stage/v2") / execution_mode
        self.calibration_path = db_path.parent / "ui-boxes.json"
        engine.load_calibrated_ui_boxes(config_path=self.calibration_path)
        self.db = engine.FarmDatabase(db_path=db_path)
        self.jobs = FarmJobs(journal_path=db_path.parent / "jobs.db")
        self.stage_root = stage_root
        self.drafts = CarouselDrafts(db_path.parent / "carousel-drafts.db", stage_root)
        self.videos = VideoDrafts(db_path.parent / "video-drafts.db", stage_root)
        self.observations = ObservationStore(db_path.parent / 'observations.db')
        self.verifications = DraftVerifications(db_path.parent / 'draft-verifications.db', self.observations, self.drafts)
        self.transfers = CarouselTransfers(db_path.parent / "transfers.db", self.drafts, videos=self.videos)
        self.port = port
        self.lan_host_url = (engine.MediaPullOrchestrator.detect_host_lan_url(port=port)
                             if execution_mode == "live" else f"http://127.0.0.1:{port}")
        self.rng = random.Random()
        self.spinner = engine.AntiDuplicateSpinEngine(rng=self.rng)
        self.factory = engine.ContentFactoryEngine(
            db=self.db,
            spinner=self.spinner,
            stage_root=self.stage_root,
            rng=self.rng,
        )
        self.preparation = PreparationSchedule(db_path.parent / 'preparation-schedule.db',
            lambda: self.factory.generate_daily_slate_for_device('C24C'),
            lambda: self.db.get_persona('C24C'), self.operation_lock)
        self.mock_kernel = engine.MockApiServer()
        self.kernel_client = engine.IMouseKernel(
            url=KERNEL_BASE_URL,
            transport=self.mock_kernel.handle if execution_mode == "simulate" else None,
        )
        self.live_kernel_connected = False
        self.jitter = engine.HumanizedTargetJitter(rng=self.rng)
        self.vision = engine.VlmComputerUseAdapter(mode=engine.ExecutionMode.API_BOUNDED_VISION)
        engine.MediaPullOrchestrator.export_ios_shortcut_plist(
            self.stage_root / "iMousePull.shortcut.plist",
            host_lan_url=self.lan_host_url,
            device_id="C24C",
        )

    def get_kernel(self) -> engine.IMouseKernel:
        """Use the selected mode for this process. Never substitute simulated success."""
        if self.execution_mode == "simulate":
            return self.kernel_client
        self.live_kernel_connected = False
        try:
            status = self.kernel_client.kernel_status()
            if status.get("code") != 0 or status.get("input_leases_required") is not True:
                raise engine.KernelSafetyError("The live kernel did not confirm its input ownership protocol.")
        except Exception as exc:
            raise engine.KernelSafetyError(f"Live kernel unavailable or incompatible; no action was simulated: {exc}") from exc
        self.live_kernel_connected = True
        return self.kernel_client

    def build_scheduler(self, kernel: engine.IMouseKernel | None = None) -> engine.BackgroundCohortScheduler:
        k = kernel or self.get_kernel()
        warmup = engine.AccountWarmupEngine(
            kernel=k, jitter=self.jitter, vision=self.vision, db=self.db, rng=self.rng
        )
        orchestrator = engine.SocialUploadOrchestrator(
            kernel=k, jitter=self.jitter, vision=self.vision, db=self.db, rng=self.rng
        )
        return engine.BackgroundCohortScheduler(
            db=self.db,
            warmup_engine=warmup,
            upload_orchestrator=orchestrator,
        )

    def selected_personas(self, cohort="all", device_id=None):
        personas = self.db.list_personas()
        if str(cohort) != "all":
            personas = [p for p in personas if str(p["cohort"]) == str(cohort)]
        if device_id is not None:
            selected = engine.persona_device_id(device_id)
            personas = [p for p in personas if p["device_id"] == selected]
        if not personas:
            raise ValueError("No matching persona; select a registered phone.")
        return personas

    def submit_job(self, request_id, action, payload):
        if action not in JOB_ACTIONS or not isinstance(payload, dict):
            raise ValueError("Unknown action or invalid job payload.")
        # The currently bundled automation uses calibrated coordinates, not verified
        # live app observations. Do not publish or message through that fallback.
        if self.execution_mode == "live" and action not in ("create-content", "scan-profile-views") and not (action == "scheduler-tick" and payload.get("execute_actions") is False):
            raise engine.KernelSafetyError("Live automation needs verified app observations and a validated account workflow. Content creation and manual C24C controls remain available.")
        def run(cancelled):
            handler = object.__new__(FarmRequestHandler)
            captured = []
            handler._send_json = lambda status, body: captured.append((status, body))
            with self.kernel_client.job_context(cancelled):
                handler._handle_post("/api/farm/" + action, payload, json.dumps(payload).encode())
                if not captured or captured[0][0] >= 400:
                    raise RuntimeError(str(captured[0][1]) if captured else "Job returned no result.")
                return {**captured[0][1], "executionMode": self.execution_mode, "simulated": self.execution_mode == "simulate"}
        return self.jobs.submit(request_id, action, payload, run)

    def preflight_targets(self, kernel, targets):
        # Validate the complete selection before the first phone can receive input.
        for target in targets:
            kernel._require_live_target(target)
        for target in targets:
            kernel.preflight_phone(target)

    def run_full_daily_factory(self, cohort_filter: str = "all", device_id=None) -> dict:
        kernel = self.get_kernel()
        orchestrator = engine.SocialUploadOrchestrator(
            kernel=kernel, jitter=self.jitter, vision=self.vision, db=self.db, rng=self.rng
        )
        funnel = engine.ConversionFunnelEngine(
            kernel=kernel, jitter=self.jitter, vision=self.vision, db=self.db, rng=self.rng
        )
        personas = self.selected_personas(cohort_filter, device_id)
        self.preflight_targets(kernel, [p["device_id"] for p in personas])

        assets_rendered = 0
        uploads_executed = 0
        pinned_ctas = 0
        per_device_results = []

        for p in personas:
            dev_id = p["device_id"]
            if p["account_day"] <= 3 or p["paused_zero_view"]:
                per_device_results.append({"deviceId": dev_id, "status": "warmup_or_paused", "assets": 0})
                continue

            slate = self.factory.generate_daily_slate_for_device(dev_id)
            assets_rendered += len(slate)

            # Export per-device iMousePull shortcut plist with auto-detected LAN URL
            engine.MediaPullOrchestrator.export_ios_shortcut_plist(
                self.stage_root / dev_id / "iMousePull.shortcut.plist",
                host_lan_url=self.lan_host_url,
                device_id=dev_id,
            )

            # Execute primary upload (IG Reel or Carousel) + Golden-Hour Pinned CTA
            job = engine.UploadJob(
                device_id=dev_id,
                platform=engine.Platform.INSTAGRAM,
                upload_format=engine.UploadFormat.IG_REEL,
                caption_or_title=slate[0]["caption"] if slate else f"Daily drop {dev_id}",
                pull_media_first=True,
                launch_app_via_spotlight=True,
                attach_trending_audio_3pct=True,
            )
            up_res = orchestrator.execute_upload(job)
            uploads_executed += 1
            funnel.post_and_pin_cta_comment(dev_id)
            pinned_ctas += 1
            per_device_results.append(
                {
                    "deviceId": dev_id,
                    "status": "simulated_upload_and_pin" if self.execution_mode == "simulate" else "publication_unverified",
                    "assets": len(slate),
                    "clicks": up_res["totalClicks"],
                    "phash": slate[0]["phashHex"] if slate else "",
                }
            )

        winners = self.factory.clone_winning_hooks()
        return {
            "summary": {
                "assetsRendered": assets_rendered,
                "uploadsExecuted": uploads_executed,
                "pinnedCtas": pinned_ctas,
                "winningHooksCloned": len(winners),
            },
            "devices": per_device_results,
            "winners": winners,
        }


RUNTIME: FarmBackendRuntime | None = None


class FarmRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[iMouse-Farm-9914] {self.address_string()} - {fmt % args}")

    def _is_origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "")
        if not origin:
            return True
        parsed = urllib.parse.urlparse(origin)
        return parsed.hostname in ("localhost", "127.0.0.1", "::1")

    def _transfer_access_allowed(self) -> bool:
        # Secret URLs are returned only to local clients addressed to this listener.
        return (self.client_address[0] in ('127.0.0.1', '::1') and self._is_origin_allowed()
                and self.headers.get('Host', '') in {f'127.0.0.1:{self.server.server_port}',
                    f'localhost:{self.server.server_port}', f'[::1]:{self.server.server_port}'})

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if RUNTIME is not None:
            self.send_header("X-Farm-Execution-Mode", RUNTIME.execution_mode)
        origin = self.headers.get("Origin", "")
        if origin and self._is_origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        if RUNTIME is not None:
            payload = {**payload, "protocolVersion": 2, "executionMode": RUNTIME.execution_mode,
                       "simulated": (payload['observation'].get('source') == 'simulation') if 'observation' in payload
                       else payload['verification']['assessment']['source'] != 'phone' if 'verification' in payload
                       else False if any(k in payload for k in ('transfer', 'draft', 'drafts', 'sources', 'observations', 'frame', 'preparationSchedule', 'verifications')) else RUNTIME.execution_mode == "simulate"}
        raw = json.dumps(payload, indent=2).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", raw)

    def do_OPTIONS(self) -> None:
        if not self._is_origin_allowed():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if origin and self._is_origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    def do_GET(self) -> None:
        assert RUNTIME is not None
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == '/api/farm/capabilities':
            self._send_json(200, capabilities())
            return

        if path == '/api/farm/draft-verifications' or path.startswith('/api/farm/draft-verifications/'):
            if not self._transfer_access_allowed():
                self._send_json(403, {'error': 'Draft evidence is local-only.'}); return
            try:
                if path == '/api/farm/draft-verifications':
                    draft_id = urllib.parse.parse_qs(parsed.query).get('draft_id', [''])[0]
                    self._send_json(200, {'verifications': RUNTIME.verifications.list(draft_id)})
                elif '/frames/' in path:
                    import base64
                    parts = path.split('/')
                    if len(parts) != 7 or parts[5] != 'frames': raise ValueError('Invalid review frame route.')
                    self._send_json(200, {'frame': base64.b64encode(RUNTIME.verifications.frame(parts[4], parts[6])).decode('ascii')})
                else: self._send_json(200, {'verification': RUNTIME.verifications.get(path.rsplit('/', 1)[-1])})
            except (ValueError, KeyError) as error: self._send_json(404, {'error': str(error)})
            return

        if path == '/api/farm/preparation-schedule':
            if not self._transfer_access_allowed():
                self._send_json(403, {'error': 'Preparation schedule is local-only.'}); return
            self._send_json(200, {'preparationSchedule': RUNTIME.preparation.status()})
            return

        if path == '/api/farm/observations' or path.startswith('/api/farm/observations/'):
            if not self._transfer_access_allowed():
                self._send_json(403, {'error': 'Observations are local-only.'})
                return
            try:
                if path == '/api/farm/observations':
                    self._send_json(200, {'observations': RUNTIME.observations.list()})
                elif path.endswith('/frame'):
                    import base64
                    self._send_json(200, {'frame': base64.b64encode(RUNTIME.observations.frame(path.split('/')[-2])).decode('ascii')})
                else:
                    self._send_json(200, {'observation': RUNTIME.observations.get(path.rsplit('/', 1)[-1])})
            except (KeyError, ValueError) as exc:
                self._send_json(404, {'error': str(exc)})
            return

        if path == '/api/farm/video-sources':
            try: self._send_json(200, {'sources': RUNTIME.videos.sources()})
            except (ValueError, KeyError, OSError) as ex: self._send_json(400, {'error': str(ex)})
            return
        if path == '/api/farm/video-drafts':
            self._send_json(200, {'drafts': RUNTIME.videos.list()})
            return
        if path.startswith('/api/farm/video-drafts/'):
            try: self._send_json(200, {'draft': RUNTIME.videos.get(path.rsplit('/', 1)[1])})
            except (ValueError, KeyError) as ex: self._send_json(404, {'error': str(ex)})
            return
        if path == "/api/farm/transfers/current" or path.startswith("/api/farm/transfers/"):
            if not self._transfer_access_allowed():
                self._send_json(403, {"error": "Cross-origin transfer access refused."})
                return
            try:
                transfer = RUNTIME.transfers.current() if path.endswith("/current") else RUNTIME.transfers.get(path.rsplit("/", 1)[1])
                self._send_json(200, {"transfer": transfer})
            except KeyError as exc:
                self._send_json(404, {"error": str(exc)})
            return

        if path == "/api/farm/drafts" or path.startswith("/api/farm/drafts/"):
            try:
                if path == "/api/farm/drafts":
                    self._send_json(200, {"drafts": RUNTIME.drafts.list()})
                else:
                    self._send_json(200, {"draft": RUNTIME.drafts.get(path[len('/api/farm/drafts/'):])})
            except (KeyError, ValueError) as exc:
                self._send_json(404, {"error": str(exc)})
            return

        if path.startswith("/api/farm/jobs/"):
            try:
                self._send_json(200, {"job": RUNTIME.jobs.get(path.rsplit("/", 1)[1])})
            except KeyError:
                self._send_json(404, {"error": "Job not found. Its outcome must not be assumed or replayed."})
            return

        if path in ("/", "/index.html", "/dashboard"):
            self._send_bytes(200, "text/html; charset=utf-8", load_dashboard_html().encode("utf-8"))
            return

        if path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "port": RUNTIME.port,
                    "sourceHash": RUNTIME.source_hash,
                    "carouselDraftsVersion": 1,
                    "carouselTransfersVersion": 1,
                    "videoDraftsVersion": 1,
                    "observationsVersion": 2,
                    "draftVerificationVersion": 1,
                    "preparationScheduleVersion": 1,
                    "lanHostUrl": RUNTIME.lan_host_url,
                    "layersBuilt": 7,
                    "personasCount": len(RUNTIME.db.list_personas()),
                },
            )
            return

        if path == "/api/farm/state":
            kernel_error = None
            try:
                RUNTIME.get_kernel()
            except engine.KernelSafetyError as exc:
                kernel_error = str(exc)
            personas = RUNTIME.db.list_personas()
            self._send_json(
                200,
                {
                    "status": "ok",
                    "liveKernelConnected": RUNTIME.live_kernel_connected,
                    "kernelError": kernel_error,
                    "activeJob": RUNTIME.jobs.current(),
                    "liveAutomationReady": False,
                    "carouselDraftsVersion": 1,
                    "observationStatus": "Read-only screen review available. Keyword actions and verified post metrics remain unavailable.",
                    "lanHostUrl": RUNTIME.lan_host_url,
                    "personas": personas,
                    "c24cSlates": RUNTIME.db.get_slates_for_device("C24C", limit=5),
                },
            )
            return

        if path == "/api/farm/scheduler-status":
            sched = RUNTIME.build_scheduler(kernel=RUNTIME.kernel_client)
            sched_st = sched.get_scheduler_status()
            self._send_json(
                200,
                {
                    "status": "ok",
                    "maxConcurrentPerWave": engine.BackgroundCohortScheduler.MAX_CONCURRENT_PHONES_PER_COHORT,
                    **sched_st,
                },
            )
            return

        if path.startswith("/stage/"):
            parts = urllib.parse.unquote(path).split("/")[1:]
            if (len(parts) != 3 or any(p in ("", ".", "..") or any(c in p for c in "\\:%\x00") for p in parts)
                    or parts[1] not in {p["device_id"] for p in RUNTIME.db.list_personas()}):
                self._send_json(404, {"error": "Staged file not found"})
                return
            if len(parts) == 3:
                device_id = parts[1]
                stage_root = RUNTIME.stage_root.resolve()
                dev_dir = (stage_root / device_id).resolve()
                target = (dev_dir / parts[2]).resolve()
                if not dev_dir.is_relative_to(stage_root) or not target.is_relative_to(dev_dir):
                    self._send_json(404, {"error": "Staged file not found"})
                    return
                if len(parts) == 3:
                    target_file = (dev_dir / parts[2]).resolve()
                    if target_file.is_relative_to(dev_dir.resolve()) and target_file.is_file():
                        ext = target_file.suffix.lower()
                        ctype = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".json": "application/json; charset=utf-8", ".plist": "application/x-plist"}.get(ext, "application/octet-stream")
                        self._send_bytes(200, ctype, target_file.read_bytes())
                        return
            self._send_json(404, {"error": "Staged file not found"})
            return

        if path.startswith("/kernel-proxy/"):
            subpath = path[len("/kernel-proxy") :]
            query = f"?{parsed.query}" if parsed.query else ""
            self._proxy_to_kernel("GET", f"{KERNEL_BASE_URL}{subpath}{query}", None)
            return

        self._send_json(404, {"error": f"Unknown GET path: {path}"})

    def do_POST(self) -> None:
        assert RUNTIME is not None
        if not self._is_origin_allowed():
            self.close_connection = True
            self._send_json(403, {"error": "Cross-origin request forbidden. Only localhost allowed."})
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path.startswith(('/api/farm/transfers', '/api/farm/observations', '/api/farm/preparation-schedule', '/api/farm/draft-verifications')) and not self._transfer_access_allowed():
            self.close_connection = True
            self._send_json(403, {"error": "Media, observation and preparation controls are local-only."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = 12 * 1024 * 1024 if path.startswith("/api/farm/drafts/") and path.endswith("/import") else 65536
            if length < 0 or length > limit:
                self._send_json(413, {"error": f"Request body exceeds the {limit}-byte limit."})
                self.close_connection = True
                return
            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            if not isinstance(data, dict):
                raise ValueError("Request must be a JSON object.")
            self._handle_post(path, data, raw_body)
        except (DraftConflict, TransferConflict) as ex:
            self._send_json(409, {"status": "draft_conflict", "error": str(ex)})
        except (ValueError, KeyError, UnicodeError) as ex:
            self._send_json(400, {"status": "invalid_request", "error": str(ex)})
        except engine.KernelSafetyError as ex:
            self._send_json(409, {"status": "safety_refused", "error": str(ex)})
        except JobCancelled as ex:
            self._send_json(409, {"status": "cancelled", "error": str(ex)})
        except Exception as ex:
            self._send_json(500, {"status": "error", "error": str(ex)})

    def _handle_post(self, path: str, data: dict, raw_body: bytes) -> None:
        assert RUNTIME is not None
        # Legacy synchronous clients share the same single-operation boundary.
        # Stop and cancellation must remain available while work is in progress.
        interrupt = path == "/api/farm/emergency-stop" or (path.startswith("/api/farm/jobs/") and path.endswith("/cancel"))
        interrupt = interrupt or (path.startswith("/kernel-proxy") and data.get("fun") == "/input/stop")
        interrupt = interrupt or path == '/api/farm/preparation-schedule/pause'
        if interrupt or path == "/api/farm/jobs" or (path.startswith("/api/farm/transfers/") and path.endswith("/stop")):
            self._dispatch_post(path, data, raw_body)
            return
        if not RUNTIME.operation_lock.acquire(blocking=False):
            if path == '/api/farm/video-drafts':
                self._send_json(409, {'status': 'preparation_busy', 'error': 'Another preparation is running. Check the saved draft before retrying.'})
                return
            raise ValueError("A farm operation is already running. Wait or cancel it first.")
        try:
            self._dispatch_post(path, data, raw_body)
        finally:
            RUNTIME.operation_lock.release()

    def _dispatch_post(self, path: str, data: dict, raw_body: bytes) -> None:
        assert RUNTIME is not None
        data = dict(data)
        if path == '/api/farm/draft-verifications':
            self._send_json(200, {'verification': RUNTIME.verifications.create(data)}); return
        if path == '/api/farm/preparation-schedule':
            self._send_json(200, {'preparationSchedule': RUNTIME.preparation.configure(data)}); return
        if path == '/api/farm/preparation-schedule/pause':
            self._send_json(200, {'preparationSchedule': RUNTIME.preparation.pause(data.get('cancel_request_id'))}); return
        if path == '/api/farm/observations':
            if data.get('read_only') is not True or data.get('source') != 'phone':
                raise ValueError('Choose an explicit read-only C24C phone observation. It never sends input.')
            self._send_json(200, {'observation': RUNTIME.observations.capture(data, engine.IMouseKernel(url=KERNEL_BASE_URL))})
            return
        if path == '/api/farm/video-drafts':
            self._send_json(200, {'draft': RUNTIME.videos.create(data)})
            return
        if path == "/api/farm/transfers":
            self._send_json(200, {"transfer": RUNTIME.transfers.start(data)})
            return
        if path.startswith("/api/farm/transfers/") and path.endswith("/stop"):
            parts = path.split("/")
            if len(parts) != 6:
                raise ValueError("Unknown transfer operation.")
            self._send_json(200, {"transfer": RUNTIME.transfers.stop(parts[4])})
            return
        if path == "/api/farm/drafts":
            draft = RUNTIME.drafts.create(data.get("id"), data.get("title", "Instagram carousel"), data.get("from_generated", False))
            self._send_json(200, {"draft": draft})
            return
        if path.startswith("/api/farm/drafts/"):
            import base64
            parts = path.split("/")
            if len(parts) != 6:
                raise ValueError("Unknown draft operation.")
            draft_id, action = parts[4:]
            revision = data.get("revision")
            if action == "import":
                draft = RUNTIME.drafts.import_image(draft_id, revision, data.get("name"), data.get("content"))
            elif action == "save":
                draft = RUNTIME.drafts.save(draft_id, revision, data.get("title"), data.get("caption"), data.get("slide_ids"))
            elif action == "export":
                archive = RUNTIME.drafts.export(draft_id, revision)
                self._send_json(200, {"filename": f"instagram-carousel-{draft_id}-r{revision}.zip", "content": base64.b64encode(archive).decode("ascii"), "savedInInstagram": False, "published": False})
                return
            else:
                raise ValueError("Unknown draft operation.")
            self._send_json(200, {"draft": draft})
            return
        if path.startswith("/api/farm/") and "device_id" in data:
            data["device_id"] = engine.persona_device_id(data["device_id"])

        if path == "/api/farm/jobs":
            job = RUNTIME.submit_job(data.get("request_id", ""), data.get("action", ""), data.get("payload"))
            self._send_json(202, {"job": job})
            return
        if path.startswith("/api/farm/jobs/") and path.endswith("/cancel"):
            self._send_json(200, {"job": RUNTIME.jobs.cancel(path.split("/")[-2])})
            return
        if path == "/api/farm/emergency-stop":
            RUNTIME.jobs.cancel_active()
        elif path.startswith("/api/farm/") and path.rsplit("/", 1)[1] in JOB_ACTIONS | {"upload-single", "funnel-suite", "update-persona", "calibrate-box", "clone-winners", "shadowban-scan"}:
            RUNTIME.jobs.assert_available()

        if (RUNTIME.execution_mode == "live" and path.rsplit("/", 1)[-1] in
                {"auto-create-and-deploy", "upload-single", "single-upload", "warmup-wave", "funnel-action", "funnel-suite"}):
            raise engine.KernelSafetyError("Live app automation is not yet validated. Create content or use manual C24C controls; no action was sent.")
        if path == "/api/farm/resume-simulation":
            RUNTIME.jobs.assert_available()
            if RUNTIME.execution_mode != "simulate":
                raise engine.KernelSafetyError("This action only resumes simulation. Use the console to recover real input.")
            RUNTIME.kernel_client.post("/input/resume", {"id": "C24C"})
            self._send_json(200, {"status": "ok", "message": "Simulation resumed; no actions replayed."})
            return

        if path == "/api/farm/create-content":
            dev_id = engine.persona_device_id(data.get("device_id", "C24C"))
            RUNTIME.db.get_persona(dev_id)
            RUNTIME.kernel_client.check_cancelled()
            slate = RUNTIME.factory.generate_daily_slate_for_device(dev_id)
            if not slate:
                raise ValueError("This profile is in warmup or paused; no content was generated.")
            engine.MediaPullOrchestrator.export_ios_shortcut_plist(
                RUNTIME.stage_root / dev_id / "iMousePull.shortcut.plist",
                host_lan_url=RUNTIME.lan_host_url, device_id=dev_id)
            self._send_json(200, {"status": "ok", "slates": slate, "manifest": f"/stage/{dev_id}/manifest.json", "contentSource": "local_templates", "reviewRequired": True})
            return

        if path == "/api/farm/auto-create-and-deploy":
            cohort = str(data.get("cohort", "all"))
            out = RUNTIME.run_full_daily_factory(cohort_filter=cohort, device_id=data.get("device_id"))
            self._send_json(200, {"status": "ok", **out})
            return

        if path in ("/api/farm/upload-single", "/api/farm/single-upload"):
            dev_id = str(data.get("device_id", "C24C"))
            plat = engine.Platform(str(data.get("platform", "instagram")))
            raw_fmt = str(data.get("upload_format") or data.get("format") or "ig_reel")
            fmt = engine.UploadFormat(raw_fmt)
            prefixes = {engine.Platform.INSTAGRAM: "ig_", engine.Platform.TIKTOK: "tt_", engine.Platform.X: "x_", engine.Platform.YOUTUBE: "yt_"}
            if not raw_fmt.startswith(prefixes[plat]):
                raise ValueError("The selected format does not belong to that platform.")
            caption = str(data.get("caption", f"Automated {fmt.value} drop"))
            kernel = RUNTIME.get_kernel()
            orch = engine.SocialUploadOrchestrator(
                kernel=kernel, jitter=RUNTIME.jitter, vision=RUNTIME.vision, db=RUNTIME.db, rng=RUNTIME.rng
            )
            res = orch.execute_upload(
                engine.UploadJob(
                    device_id=dev_id,
                    platform=plat,
                    upload_format=fmt,
                    caption_or_title=caption,
                    media_count=int(data.get("media_count", 3 if fmt in (engine.UploadFormat.IG_CAROUSEL, engine.UploadFormat.TT_PHOTO_CAROUSEL) else 1)),
                )
            )
            self._send_json(200, {"status": "ok", "result": res})
            return

        if path == "/api/farm/warmup-wave":
            cohort = str(data.get("cohort", "all"))
            dev_filter = data.get("device_id")
            clips = int(data.get("clips", 2))
            time_scale = float(data.get("time_scale", 0.5))
            kernel = RUNTIME.get_kernel()
            warmup = engine.AccountWarmupEngine(
                kernel=kernel, jitter=RUNTIME.jitter, vision=RUNTIME.vision, db=RUNTIME.db, rng=RUNTIME.rng
            )
            if clips < 1 or clips > 100 or not 0 <= time_scale <= 1:
                raise ValueError("Use 1–100 clips and time_scale between 0 and 1.")
            personas = RUNTIME.selected_personas(cohort, dev_filter)
            RUNTIME.preflight_targets(kernel, [p["device_id"] for p in personas])
            results = []
            for p in personas:
                r = warmup.run_warmup_session(
                    device_id=p["device_id"],
                    platform=engine.Platform.TIKTOK,
                    account_day=p["account_day"],
                    niche=p["niche"],
                    clips_to_watch=clips,
                    time_scale=time_scale,
                )
                results.append(r)
            self._send_json(200, {"status": "ok", "sessionsRun": len(results), "results": results})
            return

        if path == "/api/farm/scheduler-tick":
            cohort = int(data.get("cohort", 1))
            execute_actions = data.get("execute_actions", False)
            if type(execute_actions) is not bool:
                raise ValueError("execute_actions must be true or false.")
            if RUNTIME.execution_mode == "live" and execute_actions:
                raise engine.KernelSafetyError("Live scheduled actions await workflow validation; preview the schedule instead.")
            sched = RUNTIME.build_scheduler(kernel=None if execute_actions else RUNTIME.kernel_client)
            if execute_actions:
                RUNTIME.preflight_targets(sched.warmup_engine.kernel, [p["device_id"] for p in RUNTIME.selected_personas(cohort)])
            wave_res = sched.run_cohort_tick(cohort_id=cohort, execute_actions=execute_actions)
            self._send_json(200, {"status": "ok", "wave": wave_res})
            return

        if path == "/api/farm/clone-winners":
            threshold = int(data.get("threshold_views", 10000))
            cloned = RUNTIME.factory.clone_winning_hooks(threshold_views=threshold)
            self._send_json(200, {"status": "ok", "clonedCount": len(cloned), "cloned": cloned})
            return

        if path in ("/api/farm/funnel-action", "/api/farm/funnel-suite"):
            dev_id = str(data.get("device_id", "C24C"))
            action = str(data.get("action", "comment_to_dm" if path.endswith("funnel-suite") else "pin_cta"))
            if action not in ("comment_to_dm", "pin_cta", "micro_swarm"):
                raise ValueError("Unknown funnel action.")
            kernel = RUNTIME.get_kernel()
            funnel = engine.ConversionFunnelEngine(
                kernel=kernel, jitter=RUNTIME.jitter, vision=RUNTIME.vision, db=RUNTIME.db, rng=RUNTIME.rng
            )
            if action == "comment_to_dm":
                res = funnel.run_comment_to_dm_responder(dev_id)
                if res.get("observationAvailable") is False:
                    self._send_json(409, {"status": "observation_unavailable", "error": res.get("reason"), "result": res})
                    return
            elif action == "micro_swarm":
                peers = data.get("peers") or ["RACK-05", "RACK-09"]
                RUNTIME.preflight_targets(kernel, list(peers))
                res = {"swarm": funnel.run_cross_rack_micro_swarm(dev_id, peers)}
            else:
                res = funnel.post_and_pin_cta_comment(dev_id)
            self._send_json(200, {"status": "ok", "result": res})
            return
        if path == "/api/farm/emergency-stop":
            dev_id = str(data.get("device_id", "C24C"))
            status, payload = 500, {}
            try:
                kernel = RUNTIME.get_kernel()
                resolved = kernel.resolve_device_id(dev_id)
                res = kernel.post("/input/stop", {"id": resolved})
                code = res.get("code") if isinstance(res, dict) else None
                if code == 0 and all(r.get("code") == 0 for r in res.get("results", [])):
                    status, payload = 200, {"status": "ok", "stopped": dev_id, "kernel_response": res}
                else:
                    status, payload = 400, {"status": "error", "error": f"Kernel stop failed with code {code}", "kernel_response": res}
            except engine.KernelSafetyError as ex:
                status, payload = 409, {"status": "safety_refused", "error": str(ex)}
            except Exception as ex:
                payload = {"status": "error", "error": str(ex)}
            # Phone Stop must precede any potentially blocked local SQLite write.
            try:
                RUNTIME.preparation.pause()
                payload['preparationPaused'] = True
            except Exception as ex:
                payload['preparationPaused'] = False
                payload['preparationPauseError'] = str(ex)
                if status == 200:
                    status = 500
                    payload.update(status='partial', error='Phone stop completed, but recurring preparation could not be paused. Check its status.')
            self._send_json(status, payload)
            return

        if path == "/api/farm/shadowban-scan":
            kernel = RUNTIME.kernel_client
            guard = engine.ShadowbanGuardAndDiagnostics(kernel=kernel, db=RUNTIME.db, vision=RUNTIME.vision)
            dev_id = str(data.get("device_id", "C24C"))
            if 'observations' in data:
                res = guard.evaluate_observations(dev_id, data['observations'])
            else:
                res = guard.evaluate_device_views(dev_id, data.get('recent_views'))
            self._send_json(200, {"status": "ok", "result": res})
            return

        if path == "/api/farm/scan-profile-views":
            kernel = RUNTIME.get_kernel()
            guard = engine.ShadowbanGuardAndDiagnostics(kernel=kernel, db=RUNTIME.db, vision=RUNTIME.vision)
            dev_id = str(data.get("device_id", "C24C"))
            res = guard.scan_device_profile_views(dev_id)
            self._send_json(200, {"status": "ok", "result": res})
            return

        if path == "/api/farm/calibrate-box":
            key = str(data.get("key", ""))
            coords = data.get("coords") or []
            if "config_path" in data:
                raise ValueError("Calibration is stored in the farm data directory; a client cannot choose a file path.")
            if (key not in engine.UI_BOXES_500x1080 or not isinstance(coords, list) or len(coords) != 4
                    or any(type(c) is not int for c in coords)
                    or not (0 <= coords[0] < coords[2] <= 500 and 0 <= coords[1] < coords[3] <= 1080)):
                raise ValueError("Choose a known target and an integer rectangle within 500 by 1080.")
            box = engine.save_calibrated_ui_box(
                key,
                int(coords[0]),
                int(coords[1]),
                int(coords[2]),
                int(coords[3]),
                config_path=RUNTIME.calibration_path,
            )
            self._send_json(
                200,
                {
                    "status": "ok",
                    "key": key,
                    "box": [box.x_min, box.y_min, box.x_max, box.y_max],
                },
            )
            return

        if path == "/api/farm/update-persona":
            dev_id = str(data.get("device_id", "C24C"))
            updated = RUNTIME.db.update_persona(
                device_id=dev_id,
                niche=data.get("niche"),
                brand_voice=data.get("brand_voice"),
                cta_keyword=data.get("cta_keyword"),
                offer_url=data.get("offer_url"),
                account_day=data.get("account_day"),
                paused_zero_view=data.get("paused_zero_view"),
            )
            self._send_json(200, {"status": "ok", "persona": updated})
            return

        if path.startswith("/kernel-proxy"):
            subpath = path[len("/kernel-proxy") :] or "/"
            self._proxy_to_kernel("POST", f"{KERNEL_BASE_URL}{subpath}", raw_body)
            return

        self._send_json(404, {"error": f"Unknown POST path: {path}"})

    def _proxy_to_kernel(self, method: str, target_url: str, body: bytes | None) -> None:
        assert RUNTIME is not None
        try:
            target = urllib.parse.urlsplit(target_url)
            base = urllib.parse.urlsplit(KERNEL_BASE_URL)
            if (target.scheme, target.netloc) != (base.scheme, base.netloc):
                raise engine.KernelSafetyError("The proxy only serves the configured kernel endpoint.")
            kernel = RUNTIME.get_kernel()
            if method == "POST":
                command = json.loads((body or b"{}").decode("utf-8"))
                if not isinstance(command, dict) or not isinstance(command.get("fun"), str) or not isinstance(command.get("data"), dict):
                    raise ValueError("A kernel command needs fun and a data object.")
                if command["fun"] == "/input/stop":
                    RUNTIME.jobs.cancel_active()
                else:
                    RUNTIME.jobs.assert_available()
                reply = kernel.post(command["fun"], command["data"], timeout=8.0)
                self._send_json(200, {"status": 200, "message": "ok", "data": reply})
                return
            if method != "GET" or target.path not in (
                "/api/kernel/status", "/api/input/status", "/api/device/get",
                "/api/config/usb/get", "/api/config/imserver/get", "/api/pic/screenshot",
            ):
                raise engine.KernelSafetyError("This read-only proxy route is not supported.")
            if target.path == "/api/pic/screenshot":
                ids = urllib.parse.parse_qs(target.query).get("id", [])
                if len(ids) != 1:
                    raise ValueError("A screenshot requires one explicit phone.")
                raw, _ = kernel.shot(ids[0])
                self._send_bytes(200, "image/bmp", raw)
            else:
                raw, _ = kernel._transport("GET", target_url, None, 8.0)
                self._send_json(200, json.loads(raw.decode("utf-8")))
        except engine.KernelSafetyError as exc:
            self._send_json(409, {"status": "safety_refused", "error": str(exc)})
        except (ValueError, UnicodeError) as exc:
            self._send_json(400, {"status": "invalid_request", "error": str(exc)})
        except Exception as exc:
            self._send_json(502, {"status": 502, "message": "Kernel request failed; no retry or simulation fallback.", "detail": str(exc)})


def self_check() -> None:
    import tempfile

    global RUNTIME
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        test_db = tmp_path / "test_server_farm.db"
        RUNTIME = FarmBackendRuntime(db_path=test_db, stage_root=tmp_path / "test_server_stage", execution_mode="simulate")

        srv = ThreadingHTTPServer(("127.0.0.1", 0), FarmRequestHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            base = f"http://127.0.0.1:{port}"
            # 1. Verify /api/farm/state & /api/farm/scheduler-status
            with urllib.request.urlopen(f"{base}/api/farm/state", timeout=5.0) as r:
                st = json.loads(r.read().decode("utf-8"))
                assert len(st["personas"]) == 19

            with urllib.request.urlopen(f"{base}/api/farm/scheduler-status", timeout=5.0) as r:
                sched_st = json.loads(r.read().decode("utf-8"))
                assert sched_st["maxConcurrentPerWave"] == 4
                assert len(sched_st["devices"]) == 19

            # 2. Verify /api/farm/auto-create-and-deploy (Cohort 1 -> 4 phones)
            req = urllib.request.Request(
                f"{base}/api/farm/auto-create-and-deploy",
                data=json.dumps({"cohort": "1"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15.0) as r:
                deploy = json.loads(r.read().decode("utf-8"))
                assert deploy["summary"]["assetsRendered"] == 20  # 4 phones * 5 formats
                assert deploy["summary"]["uploadsExecuted"] == 4
                assert deploy["summary"]["winningHooksCloned"] == 0  # No invented view counts.

            # 3. Verify /stage/C24C/manifest.json, .mp4/.jpg & /stage/C24C/iMousePull.shortcut.plist
            with urllib.request.urlopen(f"{base}/stage/C24C/manifest.json", timeout=5.0) as r:
                manifest = json.loads(r.read().decode("utf-8"))
                assert len(manifest["files"]) == 5 and manifest["files"][0].endswith(".mp4")
                first_media_url = f"{base}{manifest['files'][0]}"
            with urllib.request.urlopen(first_media_url, timeout=5.0) as r:
                mp4_bytes = r.read()
                assert len(mp4_bytes) > 1000 and b"UUID-APPLE-IOS-MOV-" in mp4_bytes
            with urllib.request.urlopen(f"{base}/stage/C24C/iMousePull.shortcut.plist", timeout=5.0) as r:
                plist_text = r.read().decode("utf-8")
                assert "/stage/C24C/manifest.json" in plist_text

            # 4. Verify /api/farm/funnel-action (comment_to_dm & micro_swarm)
            req_f = urllib.request.Request(
                f"{base}/api/farm/funnel-action",
                data=json.dumps({"device_id": "C24C", "action": "comment_to_dm"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req_f, timeout=5.0)
                raise AssertionError("Unconfigured observations must not claim a message was sent")
            except urllib.error.HTTPError as error:
                with error:
                    f_res = json.loads(error.read().decode("utf-8"))
                assert error.code == 409 and f_res["status"] == "observation_unavailable"
                assert f_res["result"]["dmSentUrl"] is None

            # 5. Verify /api/farm/scheduler-tick, /api/farm/clone-winners, /api/farm/scan-profile-views & /api/farm/calibrate-box
            req_sc = urllib.request.Request(
                f"{base}/api/farm/scheduler-tick",
                data=json.dumps({"cohort": 2, "mode": "warmup"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_sc, timeout=5.0) as r:
                sc_res = json.loads(r.read().decode("utf-8"))
                assert sc_res["wave"]["cohort"] == 2 and len(sc_res["wave"]["actions"]) == 4

            req_scan = urllib.request.Request(
                f"{base}/api/farm/scan-profile-views",
                data=json.dumps({"device_id": "C24C"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_scan, timeout=5.0) as r:
                scan_res = json.loads(r.read().decode("utf-8"))
                assert scan_res["result"]["recentClipViews"] == []
                assert scan_res["result"]["status"] == "observation_unavailable"

            req_cal = urllib.request.Request(
                f"{base}/api/farm/calibrate-box",
                data=json.dumps({"key": "ig_carousel_aspect_ratio_btn", "coords": [22, 516, 74, 568]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_cal, timeout=5.0) as r:
                cal_res = json.loads(r.read().decode("utf-8"))
                assert cal_res["box"] == [22, 516, 74, 568]
            engine.UI_BOXES_500x1080["ig_carousel_aspect_ratio_btn"] = engine.PixelBoundingBox(
                "ig_carousel_aspect_ratio_btn", 20, 515, 75, 570
            )

            print(f"OK - Simulated routes and media checks passed on {base}; unavailable observations refused. No live app, OCR or messaging acceptance.")
        finally:
            srv.shutdown()
            srv.server_close()
            RUNTIME.transfers.close()


def main() -> int:
    global RUNTIME
    ap = argparse.ArgumentParser(description="Boot the iMouse 2.0 7-Layer Marketing Farm Server on localhost:9914")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--mode", choices=("simulate", "live"), default="simulate",
                    help="simulate is offline; live must be explicitly selected and only permits C24C input")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return 0

    srv = FarmControlServer((args.host, args.port), FarmRequestHandler)
    try:
        RUNTIME = FarmBackendRuntime(port=args.port, execution_mode=args.mode)
    except Exception:
        srv.server_close()
        raise
    url = f"http://localhost:{args.port}"
    print("=" * 72)
    print(f"  iMouse 2.0 7-Layer Marketing Farm Live at : {url}")
    print(f"  Execution mode                         : {args.mode.upper()}")
    print(f"  Bridged to iMouse Kernel API              : {KERNEL_BASE_URL}")
    print(f"  iPhone Shortcut Media Pull Endpoint       : {RUNTIME.lan_host_url}/stage/C24C/manifest.json")
    print("=" * 72)
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        RUNTIME.preparation.start()
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        RUNTIME.preparation.close()
        RUNTIME.transfers.close()
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
