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
import uuid
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
import psutil
import win32api
import win32con
from pymem import Pymem
from pymem.pattern import pattern_scan_all
from pymem.memory import read_bytes, write_bytes, read_int, write_int
import atexit

# ==================== HIDE CONSOLE (For pythonw compatibility) ====================
if sys.platform == "win32":
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

# ==================== GLOBALS ====================
SERVER_PORT = 5735
current_process_name = "HD-Player.exe"
aimbot_addresses = []
is_initialized = False
match_ended = False
monitoring_active = False
monitoring_thread = None

aimbot_states = {
    "Head": False,
    "LeftShoulder": False,
    "RightShoulder": False,
    "AimbotAi": False
}

entity_states = {
    'alive': set(),
    'knocked': set(),
    'dead': set()
}

original_head_values = {}
original_left_values = {}
original_right_values = {}
original_ai_values = {}

hotkey_state = {
    "hold_key": None,
    "hold_active": False,
    "delay": 50
}

user_settings = {
    'ignore_knocked': True,
    'hotkey_aimbot': 'Head'
}

aimbot_ai_running = False
aimbot_ai_thread = None

# ==================== OFFSETS ====================
OFFSET_MATCH_FLAG = 0xFF
OFFSET_STATE_BYTE1 = 0x647
OFFSET_STATE_BYTE2 = 0x648

OFFSET_HEAD_READ = 0xB8
OFFSET_HEAD_WRITE = 0xB4
OFFSET_LEFT_READ = 0xEC
OFFSET_RIGHT_READ = 0xE8
OFFSET_SHOULDER_WRITE = 0xA8
OFFSET_AIMBOT_AI_READ = 0xFC
OFFSET_AIMBOT_AI_WRITE = -0x358

NEW_AIMBOT_AOB = "FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? FF FF FF FF FF FF FF FF FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? A5 43"

def mkp(aob):
    aob = aob.replace(" ", "")
    pattern = bytes()
    for i in range(0, len(aob), 2):
        hex_byte = aob[i:i+2]
        if hex_byte == "??":
            pattern += b"."
        else:
            pattern += bytes([int(hex_byte, 16)])
    return pattern

# ==================== ENTITY FUNCTIONS ====================
def get_entity_state(entity_address):
    try:
        proc = Pymem(current_process_name)
        state1 = read_bytes(proc.process_handle, entity_address + OFFSET_STATE_BYTE1, 1)
        state2 = read_bytes(proc.process_handle, entity_address + OFFSET_STATE_BYTE2, 1)
        match_bytes = read_bytes(proc.process_handle, entity_address + OFFSET_MATCH_FLAG, 4)
        proc.close_process()
        
        if state1 and state2 and match_bytes:
            val1 = int.from_bytes(state1, byteorder='little')
            val2 = int.from_bytes(state2, byteorder='little')
            match_val = int.from_bytes(match_bytes, byteorder='little', signed=False)
            
            if match_val == 0:
                return 'not_in_match'
            
            if val1 == 0x3F:
                return 'alive'
            elif val1 == 0x3D and val2 == 0x01:
                return 'dead'
            else:
                return 'knocked'
        return 'unknown'
    except:
        return 'error'

def should_target_entity(entity_address):
    if match_ended:
        return False
    state = get_entity_state(entity_address)
    if state == 'not_in_match' or state == 'dead':
        return False
    if state == 'knocked' and user_settings.get('ignore_knocked', True):
        return False
    return state == 'alive' or state == 'knocked'

def update_entity_states():
    global entity_states, match_ended
    
    entities_in_match = 0
    entity_states['alive'] = set()
    entity_states['knocked'] = set()
    entity_states['dead'] = set()
    
    if not is_initialized or not aimbot_addresses:
        return
    
    try:
        proc = Pymem(current_process_name)
        for entity in aimbot_addresses:
            try:
                match_bytes = read_bytes(proc.process_handle, entity + OFFSET_MATCH_FLAG, 4)
                if match_bytes and len(match_bytes) == 4:
                    match_val = int.from_bytes(match_bytes, byteorder='little', signed=False)
                    if match_val != 0:
                        entities_in_match += 1
                
                state = get_entity_state(entity)
                if state == 'alive':
                    entity_states['alive'].add(entity)
                elif state == 'knocked':
                    entity_states['knocked'].add(entity)
                elif state == 'dead':
                    entity_states['dead'].add(entity)
            except:
                continue
        proc.close_process()
    except:
        pass
    
    old_match = match_ended
    match_ended = (entities_in_match == 0) and len(aimbot_addresses) > 0
    if old_match != match_ended and match_ended:
        clear_entities()

def clear_entities():
    global aimbot_addresses, is_initialized, match_ended, entity_states
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    
    aimbot_addresses = []
    is_initialized = False
    match_ended = True
    entity_states = {'alive': set(), 'knocked': set(), 'dead': set()}
    
    original_head_values.clear()
    original_left_values.clear()
    original_right_values.clear()
    original_ai_values.clear()

def entity_monitoring_loop():
    global monitoring_active
    while monitoring_active:
        try:
            if is_initialized and aimbot_addresses:
                update_entity_states()
            else:
                global match_ended
                match_ended = True
            time.sleep(0.1)
        except:
            time.sleep(1)

def start_entity_monitoring():
    global monitoring_active, monitoring_thread
    if monitoring_active:
        return
    monitoring_active = True
    monitoring_thread = threading.Thread(target=entity_monitoring_loop, daemon=True)
    monitoring_thread.start()

# ==================== SCAN FUNCTION ====================
def HEADLOAD():
    global aimbot_addresses, is_initialized, match_ended
    global original_head_values, original_left_values, original_right_values, original_ai_values
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    
    aimbot_addresses = []
    is_initialized = False
    match_ended = False
    entity_states = {'alive': set(), 'knocked': set(), 'dead': set()}
    original_head_values.clear()
    original_left_values.clear()
    original_right_values.clear()
    original_ai_values.clear()
    
    try:
        proc = Pymem(current_process_name)
    except:
        return f"Process '{current_process_name}' not found"
    
    try:
        entity_pattern = mkp(NEW_AIMBOT_AOB)
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
        
        if not monitoring_active:
            start_entity_monitoring()
        
        alive = 0
        knocked = 0
        dead = 0
        for entity in aimbot_addresses:
            state = get_entity_state(entity)
            if state == 'alive':
                alive += 1
            elif state == 'knocked':
                knocked += 1
            elif state == 'dead':
                dead += 1
        
        return f"Aimbot Initialized - {len(aimbot_addresses)} Entities Found (Alive: {alive}, Knocked: {knocked}, Dead: {dead})"
    except Exception as e:
        return f"Scan failed: {str(e)}"

# ==================== AIMBOT FUNCTIONS ====================
def HEADON():
    global aimbot_states, original_head_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if match_ended:
        return "Match has ended - scan again"
    
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    
    try:
        proc = Pymem(current_process_name)
        success = 0
        for entity in aimbot_addresses:
            if not should_target_entity(entity):
                continue
            if entity not in original_head_values:
                original_head_values[entity] = read_bytes(proc.process_handle, entity + OFFSET_HEAD_WRITE, 4)
            value_bytes = read_bytes(proc.process_handle, entity + OFFSET_HEAD_READ, 4)
            if value_bytes:
                write_bytes(proc.process_handle, entity + OFFSET_HEAD_WRITE, value_bytes, 4)
                success += 1
        proc.close_process()
        aimbot_states["Head"] = True
        return f"Headshot Enabled on {success} entities"
    except Exception as e:
        return f"Headshot failed: {str(e)}"

def HEADOFF():
    global aimbot_states, original_head_values
    
    if not original_head_values:
        aimbot_states["Head"] = False
        return "Headshot was not enabled"
    
    try:
        proc = Pymem(current_process_name)
        for entity, orig in original_head_values.items():
            try:
                write_bytes(proc.process_handle, entity + OFFSET_HEAD_WRITE, orig, len(orig))
            except:
                pass
        proc.close_process()
        aimbot_states["Head"] = False
        return "Headshot Disabled"
    except:
        aimbot_states["Head"] = False
        return "Headshot Disabled"

def LEFTSHOULDERON():
    global aimbot_states, original_left_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if match_ended:
        return "Match has ended - scan again"
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    
    try:
        proc = Pymem(current_process_name)
        success = 0
        for entity in aimbot_addresses:
            if not should_target_entity(entity):
                continue
            if entity not in original_left_values:
                original_left_values[entity] = read_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, 4)
            value_bytes = read_bytes(proc.process_handle, entity + OFFSET_LEFT_READ, 4)
            if value_bytes:
                write_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, value_bytes, 4)
                success += 1
        proc.close_process()
        aimbot_states["LeftShoulder"] = True
        return f"Aimbot Legit Enabled (Left Shoulder) on {success} entities"
    except Exception as e:
        return f"Left shoulder failed: {str(e)}"

def LEFTSHOULDEROFF():
    global aimbot_states, original_left_values
    
    if not original_left_values:
        aimbot_states["LeftShoulder"] = False
        return "Left shoulder was not enabled"
    
    try:
        proc = Pymem(current_process_name)
        for entity, orig in original_left_values.items():
            try:
                write_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, orig, len(orig))
            except:
                pass
        proc.close_process()
        aimbot_states["LeftShoulder"] = False
        return "Aimbot Legit Disabled (Left Shoulder)"
    except:
        aimbot_states["LeftShoulder"] = False
        return "Left Shoulder Disabled"

def RIGHTSHOULDERON():
    global aimbot_states, original_right_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if match_ended:
        return "Match has ended - scan again"
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    
    try:
        proc = Pymem(current_process_name)
        success = 0
        for entity in aimbot_addresses:
            if not should_target_entity(entity):
                continue
            if entity not in original_right_values:
                original_right_values[entity] = read_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, 4)
            value_bytes = read_bytes(proc.process_handle, entity + OFFSET_RIGHT_READ, 4)
            if value_bytes:
                write_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, value_bytes, 4)
                success += 1
        proc.close_process()
        aimbot_states["RightShoulder"] = True
        return f"Aimbot Legit Enabled (Right Shoulder) on {success} entities"
    except Exception as e:
        return f"Right shoulder failed: {str(e)}"

def RIGHTSHOULDEROFF():
    global aimbot_states, original_right_values
    
    if not original_right_values:
        aimbot_states["RightShoulder"] = False
        return "Right shoulder was not enabled"
    
    try:
        proc = Pymem(current_process_name)
        for entity, orig in original_right_values.items():
            try:
                write_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, orig, len(orig))
            except:
                pass
        proc.close_process()
        aimbot_states["RightShoulder"] = False
        return "Aimbot Legit Disabled (Right Shoulder)"
    except:
        aimbot_states["RightShoulder"] = False
        return "Right Shoulder Disabled"

def aimbot_ai_worker():
    global aimbot_ai_running, original_ai_values, aimbot_states
    
    while aimbot_ai_running:
        if not aimbot_states["AimbotAi"]:
            time.sleep(0.1)
            continue
            
        if not is_initialized or not aimbot_addresses or match_ended:
            time.sleep(0.1)
            continue
        
        try:
            proc = Pymem(current_process_name)
            for entity in aimbot_addresses:
                if not should_target_entity(entity):
                    continue
                
                if entity not in original_ai_values:
                    try:
                        original_ai_values[entity] = read_bytes(proc.process_handle, entity + OFFSET_AIMBOT_AI_WRITE, 4)
                    except:
                        pass
                
                ai_value = read_int(proc.process_handle, entity + OFFSET_AIMBOT_AI_READ)
                if ai_value != 0:
                    write_int(proc.process_handle, entity + OFFSET_AIMBOT_AI_WRITE, ai_value)
            proc.close_process()
        except:
            pass
        
        time.sleep(0.005)

def AIMBOTAI_ON():
    global aimbot_ai_running, aimbot_states, aimbot_ai_thread
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if match_ended:
        return "Match has ended - scan again"
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    
    if aimbot_ai_running:
        return "Aimbot AI already running"
    
    aimbot_ai_running = True
    aimbot_ai_thread = threading.Thread(target=aimbot_ai_worker, daemon=True)
    aimbot_ai_thread.start()
    aimbot_states["AimbotAi"] = True
    return "Aimbot Ai Enabled"

def AIMBOTAIOFF():
    global aimbot_ai_running, aimbot_states, original_ai_values
    
    aimbot_ai_running = False
    aimbot_states["AimbotAi"] = False
    
    if original_ai_values:
        try:
            proc = Pymem(current_process_name)
            for entity, orig in original_ai_values.items():
                try:
                    write_bytes(proc.process_handle, entity + OFFSET_AIMBOT_AI_WRITE, orig, len(orig))
                except:
                    pass
            proc.close_process()
        except:
            pass
    
    return "Aimbot Ai Disabled"

def AIMBOT_OFF():
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    return "All Aimbots Disabled"

# ==================== AUTHENTICATION (Aimbot Lite X Style - NO TOKEN) ====================
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
    except:
        pass
    return creds

def authenticate_user(username, password):
    creds = fetch_credentials()
    current_sid = get_computer_sid()
    
    if username in creds and creds[username][0] == password and creds[username][1] == current_sid:
        return True, "Login successful"
    else:
        return False, "INVALID CREDENTIALS"

# ==================== HOTKEY MONITOR ====================
def hold_hotkey_monitor():
    global hotkey_state, aimbot_states
    
    vk_map = {
        'MouseLeft': 0x01, 'MouseRight': 0x02, 'MouseMiddle': 0x04,
        'MouseButton4': 0x05, 'MouseButton5': 0x06,
        'Shift': 0x10, 'Control': 0x11, 'Alt': 0x12,
        'A': 0x41, 'B': 0x42, 'C': 0x43, 'D': 0x44, 'E': 0x45, 'F': 0x46,
        'G': 0x47, 'H': 0x48, 'I': 0x49, 'J': 0x4A, 'K': 0x4B, 'L': 0x4C,
        'M': 0x4D, 'N': 0x4E, 'O': 0x4F, 'P': 0x50, 'Q': 0x51, 'R': 0x52,
        'S': 0x53, 'T': 0x54, 'U': 0x55, 'V': 0x56, 'W': 0x57, 'X': 0x58,
        'Y': 0x59, 'Z': 0x5A
    }
    
    while True:
        try:
            if hotkey_state["hold_key"] and hotkey_state["hold_key"] in vk_map:
                key_state = win32api.GetAsyncKeyState(vk_map[hotkey_state["hold_key"]])
                key_held = (key_state & 0x8000) != 0
                
                if key_held and not hotkey_state["hold_active"]:
                    hotkey_state["hold_active"] = True
                    def delayed_execute():
                        time.sleep(hotkey_state["delay"] / 1000.0)
                        if hotkey_state["hold_active"] and not match_ended:
                            if not aimbot_states["AimbotAi"]:
                                AIMBOTAI_ON()
                    threading.Thread(target=delayed_execute, daemon=True).start()
                elif not key_held and hotkey_state["hold_active"]:
                    hotkey_state["hold_active"] = False
                    if not match_ended and aimbot_states["AimbotAi"]:
                        AIMBOTAIOFF()
        except:
            pass
        time.sleep(0.01)

# ==================== PROCESS FUNCTIONS ====================
def is_target_process_running():
    try:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and current_process_name.lower() in proc.info['name'].lower():
                return True
    except:
        pass
    return False

def get_running_processes():
    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                processes.append({'pid': proc.info['pid'], 'name': proc.info['name']})
            except:
                pass
        processes.sort(key=lambda x: x['name'].lower())
    except:
        pass
    return processes

def set_target_process(process_name):
    global current_process_name, is_initialized, aimbot_addresses
    try:
        test_proc = Pymem(process_name)
        test_proc.close_process()
        current_process_name = process_name
        is_initialized = False
        aimbot_addresses = []
        return True
    except:
        return False

def exit_application():
    AIMBOT_OFF()
    os._exit(0)

# ==================== FLASK APP ====================
app = Flask(__name__)
app.secret_key = 'ghostxbasic2024'

# ==================== LOGIN HTML ====================
LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Ghost-X Basic - Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { margin: 0; padding: 0; background: #0a1628; font-family: 'Segoe UI', sans-serif; color: #fff; overflow: hidden; }
        .container { display: flex; height: 100vh; justify-content: center; align-items: center; position: relative; z-index: 1; }
        .login-box { background: #1a2744; border: 1px solid #3399ff; border-radius: 15px; padding: 40px; box-shadow: 0 0 25px rgba(51, 153, 255, 0.4); width: 360px; }
        .login-box h2 { text-align: center; margin-bottom: 30px; color: #3399ff; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 6px; font-size: 14px; color: #ccc; }
        .form-group input { width: 100%; padding: 12px; background: #0f1a2e; border: 1px solid #3399ff; border-radius: 8px; color: white; font-size: 14px; outline: none; }
        .btn { width: 100%; background: #3399ff; color: #fff; padding: 12px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; }
        .btn:hover { background: #2277dd; }
        .notification { position: fixed; top: 20px; right: 20px; background: #dc3545; color: white; padding: 12px 20px; border-radius: 8px; display: none; z-index: 9999; }
        #particles-js { position: absolute; width: 100%; height: 100%; z-index: 0; }
        .loading-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(15, 15, 15, 0.95); z-index: 99999; display: none; align-items: center; justify-content: center; flex-direction: column; }
        .loader-ring { border: 5px solid rgba(51, 153, 255, 0.2); border-top: 5px solid #3399ff; border-radius: 50%; width: 70px; height: 70px; animation: spin 1s linear infinite; }
        .loader-text { margin-top: 15px; font-size: 18px; color: #3399ff; font-weight: bold; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div id="particles-js"></div>
    <div class="loading-overlay" id="loadingOverlay">
        <div class="loader-ring"></div>
        <div class="loader-text">Verifying...</div>
    </div>
    <div class="container">
        <div class="login-box">
            <h2>GHOST-X BASIC</h2>
            <form method="POST" action="/" onsubmit="showLoading()">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input name="username" type="text" id="username" required autocomplete="off">
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input name="password" type="password" id="password" required>
                </div>
                <button class="btn" type="submit">Login</button>
            </form>
            {% if error %}
                <div class="notification" style="display:block;">{{ error }}</div>
            {% endif %}
        </div>
    </div>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
    <script>
        particlesJS("particles-js", {
            "particles": { "number": { "value": 80 }, "color": { "value": "#3399ff" }, "shape": { "type": "circle" }, "opacity": { "value": 0.5 }, "size": { "value": 3 }, "move": { "enable": true, "speed": 5 } },
            "interactivity": { "events": { "onhover": { "enable": true, "mode": "repulse" } } }
        });
        function showLoading() { document.getElementById("loadingOverlay").style.display = "flex"; }
    </script>
</body>
</html>"""

# ==================== DASHBOARD HTML ====================
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ghost-X Basic Dashboard</title>
    <style>
        * { box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body { margin: 0; background-color: #0a1628; color: #aad4ff; }
        .container { max-width: 700px; margin: 20px auto; padding: 0 20px; }
        .panel { background-color: #1a2744; border-radius: 12px; padding: 16px; margin-bottom: 10px; box-shadow: 0 0 8px rgba(51, 153, 255, 0.3); }
        .panel h2 { margin-top: 0; font-size: 18px; color: #3399ff; }
        .status { display: flex; justify-content: space-between; align-items: center; }
        .badge { padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: bold; }
        .badge.online { background-color: #2e7d32; color: white; }
        .badge.offline { background-color: #dc3545; color: white; }
        .button { background-color: #0f1a2e; color: #aad4ff; padding: 8px 12px; border-radius: 8px; cursor: pointer; border: 1px solid #3399ff; text-align: center; display: inline-block; }
        .button:hover { background-color: #1a3355; }
        .button.active { background-color: #3399ff; color: white; border-color: #3399ff; }
        .button.exit { background-color: #dc3545; color: white; border-color: #dc3545; }
        .tab-buttons { display: flex; gap: 10px; margin: 10px 0; }
        .tab-buttons .button { flex: 1; text-align: center; }
        .console { background-color: #0d1117; border: 1px solid #3399ff; padding: 12px; border-radius: 8px; min-height: 100px; font-family: monospace; color: #90ee90; overflow-y: auto; max-height: 150px; font-size: 12px; white-space: pre-wrap; }
        .aim-row, .settings-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 10px; }
        .aim-label, .settings-label { font-size: 14px; min-width: 140px; }
        .note { font-size: 12px; color: #88aadd; margin-top: 2px; }
        select { padding: 8px; background-color: #0f1a2e; color: #aad4ff; border: 1px solid #3399ff; border-radius: 8px; cursor: pointer; }
        .content-panel { display: none; }
        .content-panel.active { display: block; }
        .entity-info { background-color: #0f1a2e; border: 1px solid #3399ff; border-radius: 8px; padding: 12px; margin-top: 8px; }
        .entity-stats { display: flex; flex-direction: column; gap: 6px; }
        .entity-stat { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
        .stat-label { color: #aad4ff; }
        .stat-value { font-weight: bold; background-color: #0d1117; padding: 2px 8px; border-radius: 4px; min-width: 40px; text-align: center; color: #90ee90; }
        .alternative-process-section { background-color: #1a2744; border: 1px solid #3399ff; border-radius: 8px; padding: 12px; margin-top: 8px; }
        .process-selector-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
        .slider-container { width: 100%; margin: 10px 0; }
        .slider { width: 100%; height: 6px; border-radius: 3px; background: #0f1a2e; }
        .slider::-webkit-slider-thumb { width: 18px; height: 18px; border-radius: 50%; background: #3399ff; cursor: pointer; }
        .display-none { display: none; }
        hr { border: none; border-top: 1px solid #3399ff; margin: 20px 0; }
        .aim-buttons { display: flex; gap: 10px; }
        .current-process { font-size: 12px; color: #90ee90; margin-top: 2px; }
    </style>
</head>
<body>
<div class="container">
    <div class="panel">
        <div class="status">
            <div><strong>GHOST-X BASIC</strong><br><span id="statusText">Checking...</span><br><span id="currentProcessText" class="current-process">Process: HD-Player.exe</span></div>
            <div class="badge" id="statusBadge">Checking...</div>
        </div>
    </div>
    <div class="panel alternative-process-section display-none" id="alternative-process-section">
        <h2>Alternative Process Selector</h2>
        <div class="process-selector-row">
            <select id="process-selector"><option value="">Select a process...</option></select>
            <div class="button" onclick="updateProcessList()">Refresh</div>
            <div class="button" onclick="setTargetProcess()">Set Process</div>
        </div>
    </div>
    <div class="panel">
        <h2>Entity Monitoring</h2>
        <div class="entity-info">
            <div class="entity-stats">
                <div class="entity-stat"><span class="stat-label">Alive:</span><span class="stat-value" id="aliveCount">0</span></div>
                <div class="entity-stat"><span class="stat-label">Knocked:</span><span class="stat-value" id="knockedCount">0</span></div>
                <div class="entity-stat"><span class="stat-label">Dead:</span><span class="stat-value" id="deadCount">0</span></div>
                <div class="entity-stat"><span class="stat-label">Total:</span><span class="stat-value" id="totalCount">0</span></div>
                <div class="entity-stat"><span class="stat-label">Match:</span><span class="stat-value" id="matchStatus">---</span></div>
            </div>
        </div>
    </div>
    <div class="panel">
        <div class="tab-buttons"><div class="button active" data-tab="headshot">Headshot</div><div class="button" data-tab="settings">Settings</div></div>
    </div>
    <div class="panel content-panel active" id="headshot">
        <h2>Aimbot Options</h2>
        <div class="aim-row"><div><div class="aim-label">Scan Enemies</div><div class="note">Scan for entities</div></div><div class="button" onclick="sendCommand('aimbotscan')">Scan Players</div></div>
        <div class="aim-row"><div><div class="aim-label">Neck Aimbot</div><div class="note">Enable/Disable Neck</div></div><div class="aim-buttons"><div class="button" id="neckBtn" onclick="toggleNeck()">Enable</div><div class="button active" id="neckDisableBtn" onclick="toggleNeck()">Disable</div></div></div>
        <div class="aim-row"><div><div class="aim-label">Left Shoulder</div><div class="note">Enable/Disable Left Shoulder</div></div><div class="aim-buttons"><div class="button" id="leftBtn" onclick="toggleLeft()">Enable</div><div class="button active" id="leftDisableBtn" onclick="toggleLeft()">Disable</div></div></div>
        <div class="aim-row"><div><div class="aim-label">Right Shoulder</div><div class="note">Enable/Disable Right Shoulder</div></div><div class="aim-buttons"><div class="button" id="rightBtn" onclick="toggleRight()">Enable</div><div class="button active" id="rightDisableBtn" onclick="toggleRight()">Disable</div></div></div>
        <hr>
        <div class="aim-row"><div><div class="aim-label">Aimbot AI</div><div class="note">Hold hotkey activates this</div></div><div class="aim-buttons"><div class="button" id="aiBtn" onclick="toggleAI()">Enable</div><div class="button active" id="aiDisableBtn" onclick="toggleAI()">Disable</div></div></div>
        <div class="aim-row"><div><div class="aim-label">Ignore Knocked</div><div class="note">Ignore knocked enemies</div></div><div class="aim-buttons"><div class="button active" id="ignoreYesBtn" onclick="setIgnore(true)">Yes</div><div class="button" id="ignoreNoBtn" onclick="setIgnore(false)">No</div></div></div>
    </div>
    <div class="panel content-panel" id="settings">
        <h2>Settings</h2>
        <div class="settings-row"><div><div class="settings-label">Hold Hotkey (Aimbot AI)</div><div class="note">Key to hold for activation</div></div><select id="hold-hotkey-selector"><option value="">None</option><option value="MouseLeft">Mouse Left</option><option value="MouseRight">Mouse Right</option><option value="MouseMiddle">Mouse Middle</option><option value="Shift">Shift</option><option value="Control">Control</option><option value="Alt">Alt</option></select></div>
        <div class="settings-row"><div><div class="settings-label">Hold Delay (ms)</div><div class="note">Delay before activation</div></div><input type="range" min="0" max="300" value="50" id="delaySlider" class="slider"></div>
        <hr>
        <div class="settings-row"><div><div class="settings-label">Exit</div><div class="note">Close application</div></div><div class="button exit" onclick="exitApp()">Exit</div></div>
    </div>
    <div class="panel"><h2>Console</h2><div class="console" id="console">[System] GHOST-X BASIC Ready\n</div></div>
</div>
<script>
const consoleEl = document.getElementById('console');
let neckActive = false, leftActive = false, rightActive = false, aiActive = false;

function log(msg) { const now = new Date(); consoleEl.textContent += `[${now.toLocaleTimeString()}] ${msg}\n`; consoleEl.scrollTop = consoleEl.scrollHeight; }

function sendCommand(cmd) {
    fetch('/execute', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: cmd }) })
    .then(r => r.json()).then(d => { if(d.message) log(d.message); }).catch(e => log(`Error: ${e.message}`));
}

function toggleNeck() {
    if(neckActive) { sendCommand('aimbotdisable'); neckActive = false; document.getElementById('neckBtn').classList.remove('active'); document.getElementById('neckDisableBtn').classList.add('active'); }
    else { sendCommand('aimbotenable'); neckActive = true; document.getElementById('neckBtn').classList.add('active'); document.getElementById('neckDisableBtn').classList.remove('active'); if(leftActive) toggleLeft(); if(rightActive) toggleRight(); if(aiActive) toggleAI(); }
}

function toggleLeft() {
    if(leftActive) { sendCommand('leftShoulderOff'); leftActive = false; document.getElementById('leftBtn').classList.remove('active'); document.getElementById('leftDisableBtn').classList.add('active'); }
    else { sendCommand('leftShoulderOn'); leftActive = true; document.getElementById('leftBtn').classList.add('active'); document.getElementById('leftDisableBtn').classList.remove('active'); if(neckActive) toggleNeck(); if(rightActive) toggleRight(); if(aiActive) toggleAI(); }
}

function toggleRight() {
    if(rightActive) { sendCommand('rightShoulderOff'); rightActive = false; document.getElementById('rightBtn').classList.remove('active'); document.getElementById('rightDisableBtn').classList.add('active'); }
    else { sendCommand('rightShoulderOn'); rightActive = true; document.getElementById('rightBtn').classList.add('active'); document.getElementById('rightDisableBtn').classList.remove('active'); if(neckActive) toggleNeck(); if(leftActive) toggleLeft(); if(aiActive) toggleAI(); }
}

function toggleAI() {
    if(aiActive) { sendCommand('AimbotAioff'); aiActive = false; document.getElementById('aiBtn').classList.remove('active'); document.getElementById('aiDisableBtn').classList.add('active'); }
    else { sendCommand('AimbotAion'); aiActive = true; document.getElementById('aiBtn').classList.add('active'); document.getElementById('aiDisableBtn').classList.remove('active'); if(neckActive) toggleNeck(); if(leftActive) toggleLeft(); if(rightActive) toggleRight(); }
}

function setIgnore(val) { sendCommand(val ? 'ignoreknocked_yes' : 'ignoreknocked_no'); document.getElementById('ignoreYesBtn').classList.toggle('active', val); document.getElementById('ignoreNoBtn').classList.toggle('active', !val); }
function exitApp() { if(confirm('Exit GHOST-X BASIC?')) fetch('/exit', { method: 'POST' }).then(() => setTimeout(() => window.close(), 1000)); }

function updateStatus() {
    fetch('/get_entity_info').then(r=>r.json()).then(data=>{
        if(data.success) {
            document.getElementById('aliveCount').textContent = data.alive;
            document.getElementById('knockedCount').textContent = data.knocked;
            document.getElementById('deadCount').textContent = data.dead;
            document.getElementById('totalCount').textContent = data.total;
            let matchEl = document.getElementById('matchStatus');
            if(data.match_active && !data.match_ended) { matchEl.textContent = 'ACTIVE'; matchEl.style.color = '#90ee90'; }
            else { matchEl.textContent = 'ENDED'; matchEl.style.color = '#ff6b6b'; }
        }
    }).catch(e=>console.log(e));
    fetch('/get_hd_player_status').then(r=>r.json()).then(data=>{
        document.getElementById('statusBadge').textContent = data.is_running ? 'Online' : 'Offline';
        document.getElementById('statusBadge').className = `badge ${data.is_running ? 'online' : 'offline'}`;
        document.getElementById('statusText').textContent = data.is_running ? 'Connected' : 'Process Offline';
        document.getElementById('currentProcessText').textContent = `Process: ${data.current_process}`;
        document.getElementById('alternative-process-section').classList.toggle('display-none', data.is_running);
    });
}

function updateProcessList() { fetch('/get_processes').then(r=>r.json()).then(data=>{ let sel = document.getElementById('process-selector'); if(data.success) { sel.innerHTML = '<option value="">Select...</option>'; data.processes.forEach(p=>{ let opt = document.createElement('option'); opt.value = p.name; opt.textContent = `${p.name} (${p.pid})`; sel.appendChild(opt); }); } }); }
function setTargetProcess() { let sel = document.getElementById('process-selector').value; if(sel) fetch('/set_target_process', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ process_name: sel }) }).then(()=>updateStatus()); }

document.getElementById('hold-hotkey-selector').addEventListener('change', (e)=>fetch('/save_hold_hotkey', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hotkey: e.target.value }) }));
document.getElementById('delaySlider').addEventListener('change', (e)=>fetch('/save_hold_delay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ delay: parseInt(e.target.value) }) }));

setInterval(updateStatus, 1000);
updateProcessList();
document.querySelectorAll('.tab-buttons .button').forEach(btn=>{ btn.addEventListener('click',()=>{ document.querySelectorAll('.tab-buttons .button').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); document.querySelectorAll('.content-panel').forEach(p=>p.classList.remove('active')); document.getElementById(btn.dataset.tab).classList.add('active'); }); });
</script>
</body>
</html>"""

# ==================== FLASK ROUTES ====================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        success, message = authenticate_user(username, password)
        if success:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template_string(LOGIN_HTML, error=message)
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
def execute_command():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    data = request.get_json()
    cmd = data.get('command', '')
    
    if cmd == 'aimbotscan':
        return jsonify({"message": HEADLOAD()})
    elif cmd == 'aimbotenable':
        return jsonify({"message": HEADON()})
    elif cmd == 'aimbotdisable':
        return jsonify({"message": AIMBOT_OFF()})
    elif cmd == 'leftShoulderOn':
        return jsonify({"message": LEFTSHOULDERON()})
    elif cmd == 'leftShoulderOff':
        return jsonify({"message": LEFTSHOULDEROFF()})
    elif cmd == 'rightShoulderOn':
        return jsonify({"message": RIGHTSHOULDERON()})
    elif cmd == 'rightShoulderOff':
        return jsonify({"message": RIGHTSHOULDEROFF()})
    elif cmd == 'AimbotAion':
        return jsonify({"message": AIMBOTAI_ON()})
    elif cmd == 'AimbotAioff':
        return jsonify({"message": AIMBOTAIOFF()})
    elif cmd == 'ignoreknocked_yes':
        user_settings['ignore_knocked'] = True
        return jsonify({"message": "Ignore knocked: Yes"})
    elif cmd == 'ignoreknocked_no':
        user_settings['ignore_knocked'] = False
        return jsonify({"message": "Ignore knocked: No"})
    return jsonify({"message": "Unknown command"})

@app.route('/save_hold_hotkey', methods=['POST'])
def save_hold_hotkey_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    data = request.get_json()
    hotkey_state["hold_key"] = data.get('hotkey', '') or None
    return jsonify({"success": True})

@app.route('/save_hold_delay', methods=['POST'])
def save_hold_delay_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    data = request.get_json()
    hotkey_state["delay"] = data.get('delay', 50)
    return jsonify({"success": True})

@app.route('/get_hold_hotkey', methods=['GET'])
def get_hold_hotkey_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    return jsonify({"success": True, "hotkey": hotkey_state["hold_key"] or ''})

@app.route('/get_hold_delay', methods=['GET'])
def get_hold_delay_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    return jsonify({"success": True, "delay": hotkey_state["delay"]})

@app.route('/get_entity_info', methods=['GET'])
def get_entity_info_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    
    entities_in_match = 0
    if aimbot_addresses and is_initialized:
        for entity in aimbot_addresses:
            state = get_entity_state(entity)
            if state not in ['not_in_match', 'error', 'unknown']:
                entities_in_match += 1
    
    match_active = (entities_in_match > 0) and is_initialized and len(aimbot_addresses) > 0
    
    return jsonify({
        "success": True,
        "alive": len(entity_states.get('alive', [])),
        "knocked": len(entity_states.get('knocked', [])),
        "dead": len(entity_states.get('dead', [])),
        "total": len(aimbot_addresses),
        "match_active": match_active,
        "match_ended": match_ended
    })

@app.route('/get_hd_player_status', methods=['GET'])
def get_hd_player_status_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    return jsonify({"is_running": is_target_process_running(), "current_process": current_process_name})

@app.route('/get_processes', methods=['GET'])
def get_processes_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    return jsonify({"success": True, "processes": get_running_processes()})

@app.route('/set_target_process', methods=['POST'])
def set_target_process_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    data = request.get_json()
    process_name = data.get('process_name')
    if process_name and set_target_process(process_name):
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/exit', methods=['POST'])
def exit_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    threading.Thread(target=lambda: (time.sleep(1), exit_application()), daemon=True).start()
    return jsonify({"success": True})

# ==================== MAIN ====================
if __name__ == '__main__':
    threading.Thread(target=hold_hotkey_monitor, daemon=True).start()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, use_reloader=False)
