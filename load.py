#!/usr/bin/env python
# SIMPLE AIMBOT PANEL

import os
import sys
import time
import threading
import ctypes
from flask import Flask, render_template_string, request, jsonify
import psutil
from pymem import Pymem
from pymem.pattern import pattern_scan_all
from pymem.memory import read_bytes, write_bytes, read_int, write_int

if sys.platform == "win32":
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

app = Flask(__name__)

# ==================== GLOBALS ====================
SERVER_PORT = 2000
current_process_name = "HD-Player.exe"
aimbot_addresses = []
is_initialized = False
aimbot_active = False
original_values = {}

# ==================== PATTERN & OFFSETS ====================
AIMBOT_PATTERN = "FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? FF FF FF FF FF FF FF FF FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? A5 43"

OFFSET_READ = 0xFC
OFFSET_WRITE = -0x358

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

# ==================== PROCESS DETECTION ====================
def is_game_running():
    try:
        for proc in psutil.process_iter(['name']):
            if proc.info['name']:
                name_lower = proc.info['name'].lower()
                if 'hd-player' in name_lower or 'hdplayer' in name_lower:
                    return True
    except:
        pass
    return False

# ==================== SCAN FUNCTION ====================
def scan_entities():
    global aimbot_addresses, is_initialized, original_values, current_process_name
    
    aimbot_addresses = []
    original_values = {}
    
    if not is_game_running():
        return "Game not found"
    
    try:
        proc = Pymem(current_process_name)
    except Exception as e:
        return f"Process error: {str(e)}"
    
    try:
        entity_pattern = mkp(AIMBOT_PATTERN)
        addresses = pattern_scan_all(proc.process_handle, entity_pattern, return_multiple=True)
        found_addresses = [int(addr) for addr in addresses]
        
        if not found_addresses:
            proc.close_process()
            return "No entities found"
        
        valid_entities = []
        for base_addr in found_addresses:
            try:
                if read_bytes(proc.process_handle, base_addr, 4):
                    valid_entities.append(base_addr)
            except:
                continue
        
        aimbot_addresses = valid_entities
        is_initialized = True
        proc.close_process()
        
        return f"SCAN COMPLETE - {len(aimbot_addresses)} FOUND"
    except Exception as e:
        return f"Scan failed: {str(e)}"

# ==================== AIMBOT FUNCTIONS ====================
def enable_aimbot():
    global aimbot_active, original_values
    
    if not is_initialized or not aimbot_addresses:
        return "Scan first"
    
    if aimbot_active:
        return "Already enabled"
    
    try:
        proc = Pymem(current_process_name)
        for entity in aimbot_addresses:
            key = f"{entity}_ai"
            if key not in original_values:
                orig = read_bytes(proc.process_handle, entity + OFFSET_WRITE, 4)
                if orig:
                    original_values[key] = orig
            head_value = read_int(proc.process_handle, entity + OFFSET_READ)
            write_int(proc.process_handle, entity + OFFSET_WRITE, head_value)
        proc.close_process()
        aimbot_active = True
        return "AIMBOT ON"
    except Exception as e:
        return f"Enable failed: {str(e)}"

def disable_aimbot():
    global aimbot_active, original_values
    
    if not aimbot_active:
        return "Already disabled"
    
    try:
        proc = Pymem(current_process_name)
        for key, orig in original_values.items():
            if key.endswith("_ai"):
                addr = int(key.split("_")[0])
                try:
                    write_bytes(proc.process_handle, addr + OFFSET_WRITE, orig, len(orig))
                except:
                    pass
        proc.close_process()
        original_values = {k: v for k, v in original_values.items() if not k.endswith("_ai")}
        aimbot_active = False
        return "AIMBOT OFF"
    except Exception as e:
        aimbot_active = False
        return "Aimbot off"

# ==================== HTML ====================
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIMBOT PANEL</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: #0a0a0a;
            font-family: 'Segoe UI', monospace;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .container {
            width: 400px;
            background: #141414;
            border: 1px solid #ff2929;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 0 20px rgba(255, 41, 41, 0.2);
        }

        h1 {
            color: #ff2929;
            text-align: center;
            font-size: 24px;
            letter-spacing: 2px;
            margin-bottom: 5px;
        }

        .sub {
            text-align: center;
            color: #666;
            font-size: 11px;
            margin-bottom: 25px;
        }

        .btn {
            width: 100%;
            padding: 12px;
            margin-bottom: 12px;
            background: #1e1e1e;
            border: 1px solid #333;
            border-radius: 8px;
            color: #ccc;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn:hover {
            background: #2a2a2a;
            border-color: #ff2929;
        }

        .btn-scan {
            border-color: #ff4444;
            color: #ff8888;
        }

        .btn-on {
            border-color: #2e7d32;
            color: #4caf50;
        }

        .btn-off {
            border-color: #8b3a3a;
            color: #ff8a8a;
        }

        .console {
            background: #0a0a0a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 12px;
            height: 120px;
            overflow-y: auto;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            color: #8bc34a;
            margin-top: 15px;
        }

        .status {
            font-size: 12px;
            color: #888;
            text-align: center;
            margin-bottom: 15px;
            padding: 5px;
            background: #0f0f0f;
            border-radius: 6px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AIMBOT PANEL</h1>
        <div class="sub">PORT 2000</div>

        <div class="status" id="status">READY</div>

        <button class="btn btn-scan" onclick="sendCommand('scan')">SCAN</button>
        <button class="btn btn-on" onclick="sendCommand('on')">ON</button>
        <button class="btn btn-off" onclick="sendCommand('off')">OFF</button>

        <div class="console" id="console">[SYSTEM] READY</div>
    </div>

    <script>
        const consoleEl = document.getElementById('console');
        const statusEl = document.getElementById('status');

        function log(message) {
            const now = new Date();
            const time = now.toLocaleTimeString();
            if (consoleEl.textContent.length > 0 && !consoleEl.textContent.endsWith('\\n')) {
                consoleEl.textContent += '\\n';
            }
            consoleEl.textContent += `[${time}] ${message}`;
            consoleEl.scrollTop = consoleEl.scrollHeight;
            if (consoleEl.textContent.length > 2000) {
                consoleEl.textContent = consoleEl.textContent.slice(-1500);
            }
        }

        function setStatus(msg) {
            statusEl.textContent = msg;
        }

        async function sendCommand(cmd) {
            let action = '';
            if (cmd === 'scan') {
                log('SCANNING...');
                setStatus('SCANNING');
                action = 'scan';
            } else if (cmd === 'on') {
                log('ENABLING...');
                setStatus('ENABLING');
                action = 'on';
            } else if (cmd === 'off') {
                log('DISABLING...');
                setStatus('DISABLING');
                action = 'off';
            }

            try {
                const response = await fetch('/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: action })
                });
                const data = await response.json();
                if (data.message) {
                    log(data.message);
                    if (data.message.includes('ON')) setStatus('ACTIVE');
                    else if (data.message.includes('OFF')) setStatus('INACTIVE');
                    else if (data.message.includes('SCAN')) setStatus('SCAN DONE');
                    else setStatus('READY');
                }
            } catch (error) {
                log(`ERROR: ${error.message}`);
                setStatus('ERROR');
            }
        }
    </script>
</body>
</html>
"""

# ==================== ROUTES ====================
@app.route('/')
def index():
    return INDEX_HTML

@app.route('/execute', methods=['POST'])
def execute():
    data = request.get_json()
    command = data.get('command')
    
    if command == 'scan':
        result = scan_entities()
    elif command == 'on':
        result = enable_aimbot()
    elif command == 'off':
        result = disable_aimbot()
    else:
        result = 'Unknown'
    
    return jsonify({'message': result})

# ==================== MAIN ====================
if __name__ == '__main__':
    print("=" * 40)
    print("AIMBOT PANEL")
    print("=" * 40)
    print(f"URL: http://localhost:{SERVER_PORT}")
    print("=" * 40)
    
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, use_reloader=False)
