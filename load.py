import os
import sys
import time
import threading
import ctypes
import requests
import subprocess
import hashlib
import json
import base64
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
import psutil
import win32api
import win32con
from pymem import Pymem
from pymem.pattern import pattern_scan_all
from pymem.memory import read_bytes, write_bytes, read_int, write_int

if sys.platform == "win32":
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

app = Flask(__name__)
app.secret_key = 'aimbot2024'

# ==================== GLOBALS ====================
SERVER_PORT = 1000
current_process_name = "HD-Player.exe"
aimbot_addresses = []
is_initialized = False
aimbot_active = False
original_values = {}
thread_running = False
thread_handle = None

# Settings
aimbot_delay = 50
aimbot_power = 50
body_after_fire = True

# Sniper globals
sniper_addresses = []
sniper_loaded = False

# ==================== PATTERN & OFFSETS (YOUR WORKING ONE) ====================
PATTERN = "FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? FF FF FF FF FF FF FF FF FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? A5 43"

OFFSET_READ = 0xFC
OFFSET_WRITE = -0x358
BODY_OFFSET = 0x10

# Sniper Pattern
SNIPER_PATTERN = "03 00 01 00 00 00 9A 99 99 3E FF FF FF FF 08 00 00 00 00 00 60 40 CD CC 8C 3F 8F C2 F5 3C CD CC CC 3D 06 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 80 3F 33 33 13 40 00 00 B0 3F 00 00 80 3F 01"

SNIPER_OFFSET_1 = 39
SNIPER_OFFSET_2 = 44
SNIPER_OFFSET_3 = 45

def mkp(aob):
    if '??' in aob:
        if aob.startswith("??"):
            aob = f" {aob}"
            n = aob.replace(" ??", ".").replace(" ", "\\x")
            return bytes(n.encode())
        else:
            n = aob.replace(" ??", ".").replace(" ", "\\x")
            return bytes(f"\\x{n}".encode())
    else:
        m = aob.replace(" ", "\\x")
        return bytes(f"\\x{m}".encode())

# ==================== GITHUB AUTH ====================
GITHUB_AUTH_URL = "https://raw.githubusercontent.com/Ghostxs90/X-sid/main/sid2.txt"

def get_computer_sid():
    try:
        import win32security
        hToken = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_QUERY
        )
        sid = win32security.GetTokenInformation(hToken, win32security.TokenUser)[0]
        return win32security.ConvertSidToStringSid(sid)
    except:
        try:
            result = subprocess.run(['wmic', 'useraccount', 'where', 'name="%username%"', 'get', 'sid'],
                                   capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'S-1-5-21' in line:
                    return line.strip()
        except:
            pass
        return "S-1-5-21-123456789-123456789-123456789-500"

def fetch_credentials():
    creds = {}
    try:
        headers = {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(GITHUB_AUTH_URL, headers=headers, timeout=10)
        if response.status_code == 200:
            content = response.text.strip()
            lines = content.split('\n')
            user = passw = sid = ""
            for line in lines:
                line = line.strip()
                if line.startswith('Username='):
                    user = line.split('=', 1)[1].strip()
                elif line.startswith('Password='):
                    passw = line.split('=', 1)[1].strip()
                elif line.startswith('sid='):
                    sid = line.split('=', 1)[1].strip()
                    if user and passw and sid:
                        creds[user] = (passw, sid)
                        user = passw = sid = ""
    except Exception as e:
        print(f"[-] Auth error: {e}")
    return creds

# ==================== MOUSE DETECTION ====================
VK_LBUTTON = 0x01

def is_left_mouse_pressed():
    return (win32api.GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0

# ==================== SMOOTH AIM FUNCTIONS ====================
def calculate_steps_and_delay(power):
    # Power 1 = almost instant, Power 100 = max drag
    steps = int(5 + (power - 1) * (45 / 99))
    if steps < 5:
        steps = 5
    if steps > 50:
        steps = 50
    delay = 1.0 + (power - 1) * (4.0 / 99)
    delay = round(delay, 1)
    return steps, delay

def smooth_write_aim(entity, proc):
    global aimbot_power, body_after_fire
    
    try:
        current = read_int(proc.process_handle, entity + OFFSET_WRITE)
        target = read_int(proc.process_handle, entity + OFFSET_READ)
        
        if target == 0:
            return False
        
        if body_after_fire and is_left_mouse_pressed():
            body_target = read_int(proc.process_handle, entity + OFFSET_READ + BODY_OFFSET)
            if body_target != 0:
                target = body_target
        
        if current == target:
            return True
        
        steps, step_delay = calculate_steps_and_delay(aimbot_power)
        
        for i in range(1, steps + 1):
            fraction = i / steps
            intermediate = current + int((target - current) * fraction)
            write_int(proc.process_handle, entity + OFFSET_WRITE, intermediate)
            time.sleep(step_delay / 1000.0)
        
        return True
    except:
        return False

def write_aim_instant(entity, proc):
    global body_after_fire
    
    try:
        target = read_int(proc.process_handle, entity + OFFSET_READ)
        
        if target == 0:
            return False
        
        if body_after_fire and is_left_mouse_pressed():
            body_target = read_int(proc.process_handle, entity + OFFSET_READ + BODY_OFFSET)
            if body_target != 0:
                target = body_target
        
        write_int(proc.process_handle, entity + OFFSET_WRITE, target)
        return True
    except:
        return False

# ==================== SCAN (YOUR WORKING ONE) ====================
def scan_entities():
    global aimbot_addresses, is_initialized, original_values
    
    aimbot_addresses = []
    original_values = {}
    
    try:
        proc = Pymem("HD-Player.exe")
    except:
        return "Game not found"
    
    try:
        pattern = mkp(PATTERN)
        addresses = pattern_scan_all(proc.process_handle, pattern, return_multiple=True)
        found = [int(addr) for addr in addresses]
        
        if not found:
            proc.close_process()
            return "No entities found"
        
        valid = []
        for addr in found:
            try:
                if read_bytes(proc.process_handle, addr, 4):
                    valid.append(addr)
            except:
                continue
        
        aimbot_addresses = valid
        is_initialized = True
        proc.close_process()
        
        return f"Scan complete - {len(aimbot_addresses)} entities"
    except Exception as e:
        return f"Scan failed: {str(e)}"

# ==================== AIMBOT LOOP ====================
def aimbot_loop():
    global aimbot_active, original_values, thread_running, aimbot_power
    
    while thread_running:
        if aimbot_active and is_initialized and aimbot_addresses:
            try:
                proc = Pymem("HD-Player.exe")
                for entity in aimbot_addresses:
                    try:
                        key = f"{entity}_ai"
                        if key not in original_values:
                            orig = read_bytes(proc.process_handle, entity + OFFSET_WRITE, 4)
                            if orig:
                                original_values[key] = orig
                        
                        if aimbot_power <= 5:
                            write_aim_instant(entity, proc)
                        else:
                            smooth_write_aim(entity, proc)
                    except:
                        continue
                proc.close_process()
            except:
                pass
        
        time.sleep(0.005)

def start_aimbot_thread():
    global thread_handle, thread_running
    if thread_handle is None or not thread_running:
        thread_running = True
        thread_handle = threading.Thread(target=aimbot_loop, daemon=True)
        thread_handle.start()

def enable_aimbot():
    global aimbot_active
    
    if not is_initialized or not aimbot_addresses:
        return "Scan first"
    
    if aimbot_active:
        return "Already active"
    
    start_aimbot_thread()
    aimbot_active = True
    return "Aimbot active"

def disable_aimbot():
    global aimbot_active, original_values
    
    if not aimbot_active:
        return "Already inactive"
    
    aimbot_active = False
    
    if original_values:
        try:
            proc = Pymem("HD-Player.exe")
            for key, orig in original_values.items():
                if key.endswith("_ai"):
                    addr = int(key.split("_")[0])
                    try:
                        write_bytes(proc.process_handle, addr + OFFSET_WRITE, orig, len(orig))
                    except:
                        pass
            proc.close_process()
        except:
            pass
    
    return "Aimbot inactive"

# ==================== SNIPER FUNCTIONS ====================
def scan_sniper():
    global sniper_addresses, sniper_loaded
    
    sniper_addresses = []
    
    try:
        proc = Pymem("HD-Player.exe")
    except:
        return "Game not found"
    
    try:
        pattern = mkp(SNIPER_PATTERN)
        addresses = pattern_scan_all(proc.process_handle, pattern, return_multiple=True)
        found = [int(addr) for addr in addresses]
        
        if not found:
            proc.close_process()
            return "No sniper scope found"
        
        sniper_addresses = found
        sniper_loaded = True
        proc.close_process()
        
        return f"Sniper loaded - {len(sniper_addresses)} addresses"
    except Exception as e:
        return f"Sniper load failed: {str(e)}"

def scope_on():
    global sniper_loaded, sniper_addresses
    
    if not sniper_loaded or not sniper_addresses:
        return "Load sniper first"
    
    try:
        proc = Pymem("HD-Player.exe")
        for addr in sniper_addresses:
            write_bytes(proc.process_handle, addr + SNIPER_OFFSET_1, bytes([0xFF]), 1)
            write_bytes(proc.process_handle, addr + SNIPER_OFFSET_2, bytes([0xFF]), 1)
            write_bytes(proc.process_handle, addr + SNIPER_OFFSET_3, bytes([0xFF]), 1)
        proc.close_process()
        return "Scope ON"
    except Exception as e:
        return f"Scope failed: {str(e)}"

def scope_off():
    global sniper_loaded, sniper_addresses
    
    if not sniper_loaded or not sniper_addresses:
        return "Load sniper first"
    
    try:
        proc = Pymem("HD-Player.exe")
        for addr in sniper_addresses:
            write_bytes(proc.process_handle, addr + SNIPER_OFFSET_1, bytes([0x00]), 1)
            write_bytes(proc.process_handle, addr + SNIPER_OFFSET_2, bytes([0x00]), 1)
            write_bytes(proc.process_handle, addr + SNIPER_OFFSET_3, bytes([0x00]), 1)
        proc.close_process()
        return "Scope OFF"
    except Exception as e:
        return f"Scope failed: {str(e)}"

# ==================== SETTINGS ====================
def set_aimbot_delay(delay):
    global aimbot_delay
    aimbot_delay = delay
    return f"Aimbot delay set to {delay}ms"

def set_aimbot_power(power):
    global aimbot_power
    aimbot_power = power
    steps, delay = calculate_steps_and_delay(power)
    if power <= 5:
        return f"Aimbot power set to {power} (Instant)"
    else:
        return f"Aimbot power set to {power}"

def set_body_mode(enabled):
    global body_after_fire
    body_after_fire = enabled
    return f"Body after fire: {'ON' if enabled else 'OFF'}"

# ==================== EXIT ====================
def exit_app():
    os._exit(0)

# ==================== LOGIN HTML ====================
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIMBOT LITE-X</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0a;
            font-family: 'Segoe UI', monospace;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            width: 360px;
            background: #111;
            border: 1px solid #ff2222;
            border-radius: 16px;
            padding: 32px;
            box-shadow: 0 0 30px rgba(255,34,34,0.15);
        }
        h1 {
            color: #ff2222;
            text-align: center;
            font-size: 24px;
            letter-spacing: 3px;
            margin-bottom: 8px;
        }
        .sub {
            text-align: center;
            color: #555;
            font-size: 10px;
            letter-spacing: 1px;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            color: #888;
            font-size: 11px;
            letter-spacing: 1px;
            margin-bottom: 6px;
        }
        input {
            width: 100%;
            padding: 10px;
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            color: #fff;
            font-size: 13px;
            outline: none;
        }
        input:focus {
            border-color: #ff2222;
        }
        button {
            width: 100%;
            padding: 10px;
            background: #ff2222;
            border: none;
            border-radius: 8px;
            color: #fff;
            font-size: 13px;
            font-weight: bold;
            cursor: pointer;
            margin-top: 10px;
            letter-spacing: 1px;
        }
        button:hover {
            background: #ff4444;
        }
        .error {
            color: #ff6666;
            text-align: center;
            font-size: 11px;
            margin-top: 15px;
        }
        .loading-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            display: none;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        .loader-ring {
            border: 3px solid #2a2a2a;
            border-top: 3px solid #ff2222;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
        }
        .loader-text {
            margin-top: 15px;
            color: #ff2222;
            font-size: 12px;
            letter-spacing: 2px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="loading-overlay" id="loadingOverlay">
        <div class="loader-ring"></div>
        <div class="loader-text">VERIFYING</div>
    </div>
    <div class="container">
        <h1>AIMBOT LITE-X</h1>
        <div class="sub">SECURE ACCESS</div>
        <form method="POST" action="/" onsubmit="showLoading()">
            <div class="form-group">
                <label>USERNAME</label>
                <input name="username" type="text" id="username" required autocomplete="off">
            </div>
            <div class="form-group">
                <label>PASSWORD</label>
                <input name="password" type="password" id="password" required>
            </div>
            <button type="submit">LOGIN</button>
        </form>
        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}
    </div>
    <script>
        function showLoading() {
            document.getElementById('loadingOverlay').style.display = 'flex';
        }
    </script>
</body>
</html>
"""

# ==================== DASHBOARD HTML ====================
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIMBOT LITE-X</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0a0a0a; font-family: 'Segoe UI', monospace; min-height: 100vh; display: flex; justify-content: center; align-items: center; }
        .container { width: 420px; background: #111; border: 1px solid #ff2222; border-radius: 16px; padding: 28px; box-shadow: 0 0 30px rgba(255,34,34,0.15); }
        h1 { color: #ff2222; text-align: center; font-size: 22px; font-weight: 600; letter-spacing: 3px; margin-bottom: 6px; }
        .sub { text-align: center; color: #555; font-size: 10px; letter-spacing: 1px; margin-bottom: 28px; }
        .status-panel { background: #0a0a0a; border: 1px solid #222; border-radius: 10px; padding: 10px; margin-bottom: 20px; text-align: center; }
        .status-label { color: #666; font-size: 10px; letter-spacing: 1px; margin-bottom: 4px; }
        .status-value { color: #ff4444; font-size: 13px; font-weight: 500; font-family: monospace; }
        .btn { width: 100%; padding: 12px; margin-bottom: 12px; background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; color: #ccc; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s; letter-spacing: 1px; }
        .btn:hover { background: #222; border-color: #ff2222; }
        .btn-scan { border-color: #aa3333; color: #ff6666; }
        .btn-scan:hover { background: #1a0a0a; border-color: #ff4444; }
        .btn-on { border-color: #226622; color: #55cc55; }
        .btn-on:hover { background: #0a1a0a; border-color: #44ff44; }
        .btn-off { border-color: #662222; color: #cc5555; }
        .btn-off:hover { background: #1a0a0a; border-color: #ff4444; }
        .btn-exit { border-color: #662222; color: #ff8888; margin-bottom: 0; }
        .console { background: #050505; border: 1px solid #1a1a1a; border-radius: 10px; padding: 12px; height: 110px; overflow-y: auto; font-family: 'Monaco', 'Consolas', monospace; font-size: 10px; color: #55cc55; margin-top: 15px; white-space: pre-wrap; word-wrap: break-word; }
        .console::-webkit-scrollbar { width: 4px; }
        .console::-webkit-scrollbar-track { background: #111; }
        .console::-webkit-scrollbar-thumb { background: #ff2222; border-radius: 4px; }
        .tab-buttons {
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
        }
        .tab-btn {
            flex: 1;
            padding: 8px;
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            color: #ccc;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
        }
        .tab-btn:hover {
            background: #222;
            border-color: #ff2222;
        }
        .tab-btn.active {
            background: #ff2222;
            color: #fff;
            border-color: #ff2222;
        }
        .content-panel {
            display: none;
        }
        .content-panel.active {
            display: block;
        }
        .settings-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .settings-label {
            font-size: 12px;
            color: #aaa;
            letter-spacing: 1px;
        }
        .slider-container {
            flex: 1;
            margin-left: 20px;
        }
        .slider {
            width: 100%;
            height: 4px;
            -webkit-appearance: none;
            background: #2a2a2a;
            border-radius: 2px;
            outline: none;
        }
        .slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: #ff2222;
            cursor: pointer;
            border: none;
        }
        .slider-value {
            margin-left: 12px;
            min-width: 35px;
            color: #ff8888;
            font-size: 11px;
        }
        .toggle-group {
            display: flex;
            gap: 8px;
        }
        .toggle-btn {
            padding: 5px 14px;
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 20px;
            color: #888;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .toggle-btn.active {
            background: #ff2222;
            border-color: #ff2222;
            color: white;
        }
        hr {
            border: none;
            border-top: 1px solid #2a2a2a;
            margin: 15px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AIMBOT LITE-X</h1>
        <div class="sub">CONTROL PANEL</div>
        
        <div class="status-panel">
            <div class="status-label">STATUS</div>
            <div class="status-value" id="status">STANDBY</div>
        </div>

        <div class="tab-buttons">
            <div class="tab-btn active" data-tab="aimbot">AIMBOT</div>
            <div class="tab-btn" data-tab="sniper">SNIPER</div>
            <div class="tab-btn" data-tab="settings">SETTINGS</div>
        </div>

        <!-- AIMBOT TAB -->
        <div class="content-panel active" id="aimbot">
            <button class="btn btn-scan" onclick="sendCmd('scan')">SCAN</button>
            <button class="btn btn-on" onclick="sendCmd('on')">ON</button>
            <button class="btn btn-off" onclick="sendCmd('off')">OFF</button>
            <button class="btn btn-exit" onclick="exitApp()">EXIT</button>
        </div>

        <!-- SNIPER TAB -->
        <div class="content-panel" id="sniper">
            <button class="btn btn-scan" onclick="sendCmd('loadsniper')">SCAN SNIPER</button>
            <button class="btn btn-on" onclick="sendCmd('sniperscopeon')">SCOPE ON</button>
            <button class="btn btn-off" onclick="sendCmd('sniperscopeoff')">SCOPE OFF</button>
            <button class="btn btn-exit" onclick="exitApp()">EXIT</button>
        </div>

        <!-- SETTINGS TAB -->
        <div class="content-panel" id="settings">
            <div class="settings-row">
                <span class="settings-label">AIMBOT DELAY</span>
                <div class="slider-container">
                    <input type="range" id="delay-slider" class="slider" min="0" max="300" value="50">
                </div>
                <span class="slider-value" id="delay-value">50ms</span>
            </div>
            
            <hr>
            
            <div class="settings-row">
                <span class="settings-label">AIMBOT POWER</span>
                <div class="slider-container">
                    <input type="range" id="power-slider" class="slider" min="1" max="100" value="50">
                </div>
                <span class="slider-value" id="power-value">50</span>
            </div>
            
            <div class="settings-row">
                <span class="settings-label">AIM TO BODY AFTER FIRE</span>
                <div class="toggle-group">
                    <div class="toggle-btn" id="body-off-btn" onclick="setBodyMode(false)">OFF</div>
                    <div class="toggle-btn active" id="body-on-btn" onclick="setBodyMode(true)">ON</div>
                </div>
            </div>
        </div>

        <div class="console" id="console">> READY</div>
    </div>

    <script>
        const consoleEl = document.getElementById('console');
        const statusEl = document.getElementById('status');
        const delaySlider = document.getElementById('delay-slider');
        const delayValue = document.getElementById('delay-value');
        const powerSlider = document.getElementById('power-slider');
        const powerValue = document.getElementById('power-value');
        
        function log(msg) {
            const now = new Date();
            const time = now.toLocaleTimeString();
            if (consoleEl.textContent.length > 0 && !consoleEl.textContent.endsWith('\\n')) {
                consoleEl.textContent += '\\n';
            }
            consoleEl.textContent += `[${time}] ${msg}`;
            consoleEl.scrollTop = consoleEl.scrollHeight;
            if (consoleEl.textContent.length > 3000) {
                consoleEl.textContent = consoleEl.textContent.slice(-2500);
            }
        }
        
        function setStatus(s) { 
            statusEl.textContent = s; 
        }
        
        function exitApp() {
            if (confirm('Exit AIMBOT LITE-X?')) {
                fetch('/exit', { method: 'POST' });
                log('Shutting down...');
                setTimeout(() => window.close(), 1500);
            }
        }
        
        function setBodyMode(on) {
            if (on) {
                document.getElementById('body-on-btn').classList.add('active');
                document.getElementById('body-off-btn').classList.remove('active');
                log('Aim to body after fire: ON');
            } else {
                document.getElementById('body-on-btn').classList.remove('active');
                document.getElementById('body-off-btn').classList.add('active');
                log('Aim to body after fire: OFF');
            }
            fetch('/set_body_mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: on })
            }).catch(e => console.log(e));
        }
        
        delaySlider.addEventListener('input', function() {
            delayValue.textContent = this.value + 'ms';
        });
        
        delaySlider.addEventListener('change', function() {
            const val = parseInt(this.value);
            log(`Aimbot delay set to ${val}ms`);
            fetch('/set_delay', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delay: val })
            }).catch(e => console.log(e));
        });
        
        powerSlider.addEventListener('input', function() {
            powerValue.textContent = this.value;
        });
        
        powerSlider.addEventListener('change', function() {
            const val = parseInt(this.value);
            log(`Aimbot power set to ${val}`);
            fetch('/set_power', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ power: val })
            }).catch(e => console.log(e));
        });
        
        async function sendCmd(cmd) {
            let action = '';
            if (cmd === 'scan') { log('Scanning...'); setStatus('SCANNING'); action = 'scan'; }
            else if (cmd === 'on') { log('Activating...'); setStatus('ACTIVATING'); action = 'on'; }
            else if (cmd === 'off') { log('Deactivating...'); setStatus('DEACTIVATING'); action = 'off'; }
            else if (cmd === 'loadsniper') { log('Loading sniper...'); setStatus('LOADING'); action = 'loadsniper'; }
            else if (cmd === 'sniperscopeon') { log('Enabling scope...'); setStatus('SCOPE ON'); action = 'sniperscopeon'; }
            else if (cmd === 'sniperscopeoff') { log('Disabling scope...'); setStatus('SCOPE OFF'); action = 'sniperscopeoff'; }
            
            try {
                const r = await fetch('/execute', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command:action}) });
                const d = await r.json();
                if (d.message) {
                    if (d.message.includes('complete')) {
                        log(d.message);
                        setStatus('READY');
                    } else if (d.message.includes('active')) {
                        log('Aimbot active');
                        setStatus('ACTIVE');
                    } else if (d.message.includes('inactive')) {
                        log('Aimbot inactive');
                        setStatus('STANDBY');
                    } else if (d.message.includes('Scope ON')) {
                        log('Scope enabled');
                        setStatus('SCOPE ACTIVE');
                    } else if (d.message.includes('Scope OFF')) {
                        log('Scope disabled');
                        setStatus('STANDBY');
                    } else {
                        log(d.message);
                    }
                }
            } catch(e) { log(`ERROR: ${e.message}`); setStatus('ERROR'); }
        }

        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.getAttribute('data-tab');
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                document.querySelectorAll('.content-panel').forEach(p => p.classList.remove('active'));
                document.getElementById(tab).classList.add('active');
            });
        });
    </script>
</body>
</html>
"""

# ==================== ROUTES ====================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        creds = fetch_credentials()
        sid = get_computer_sid()
        
        if username in creds and creds[username][0] == password and creds[username][1] == sid:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template_string(LOGIN_HTML, error="INVALID CREDENTIALS")
    
    return render_template_string(LOGIN_HTML)

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template_string(INDEX_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/execute', methods=['POST'])
def execute():
    if not session.get('logged_in'):
        return jsonify({"message": "Not logged in"}), 401
    
    data = request.get_json()
    cmd = data.get('command')
    
    if cmd == 'scan':
        result = scan_entities()
    elif cmd == 'on':
        result = enable_aimbot()
    elif cmd == 'off':
        result = disable_aimbot()
    elif cmd == 'loadsniper':
        result = scan_sniper()
    elif cmd == 'sniperscopeon':
        result = scope_on()
    elif cmd == 'sniperscopeoff':
        result = scope_off()
    else:
        result = 'Unknown'
    
    return jsonify({'message': result})

@app.route('/set_delay', methods=['POST'])
def set_delay():
    if not session.get('logged_in'):
        return jsonify({"message": "Not logged in"}), 401
    data = request.get_json()
    delay = data.get('delay', 50)
    result = set_aimbot_delay(delay)
    return jsonify({'message': result})

@app.route('/set_power', methods=['POST'])
def set_power():
    if not session.get('logged_in'):
        return jsonify({"message": "Not logged in"}), 401
    data = request.get_json()
    power = data.get('power', 50)
    result = set_aimbot_power(power)
    return jsonify({'message': result})

@app.route('/set_body_mode', methods=['POST'])
def set_body_mode():
    if not session.get('logged_in'):
        return jsonify({"message": "Not logged in"}), 401
    data = request.get_json()
    enabled = data.get('enabled', True)
    result = set_body_mode(enabled)
    return jsonify({'message': result})

@app.route('/exit', methods=['POST'])
def exit_route():
    if not session.get('logged_in'):
        return jsonify({"message": "Not logged in"}), 401
    threading.Thread(target=lambda: (time.sleep(0.5), exit_app()), daemon=True).start()
    return jsonify({"message": "Exiting..."})

# ==================== MAIN ====================
if __name__ == '__main__':
    print("=" * 50)
    print("AIMBOT LITE-X")
    print("=" * 50)
    print(f"URL: http://localhost:{SERVER_PORT}")
    print("=" * 50)
    print("Login: Brok / 1")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, use_reloader=False)
