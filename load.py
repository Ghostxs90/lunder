#!/usr/bin/env python
# GHOST PYTHON - AIMBOT ONLY (No Entity Info)

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
import atexit

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

aimbot_states = {
    "Head": False,
    "LeftShoulder": False,
    "RightShoulder": False,
    "AimbotAi": False
}

original_values = {}

hotkey_state = {
    "hold_key": None,
    "hold_active": False,
    "delay": 50
}

# Legit Aimbot settings
legit_settings = {
    'pixel_power': 25,
    'advance_maneuver': 15,
    'move_to_body': False,
    'x_aimbot_mode': 'Aimbot AI'
}

user_settings = {
    'ignore_knocked': True
}

# Mouse tracking for pixel power
last_mouse_pos = (0, 0)
mouse_movement = 0
legit_active = False
cps_toggle = False
last_cps_time = 0

# ==================== GITHUB AUTH ====================
GITHUB_AUTH_URL = "https://raw.githubusercontent.com/Ghostxs90/Sid/main/Sid.txt"

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
            lines = response.text.strip().split('\n')
            user = passw = sid = ""
            for line in lines:
                line = line.strip()
                if 'Username=' in line:
                    user = line.split('=')[1].strip()
                elif 'Password=' in line:
                    passw = line.split('=')[1].strip()
                elif 'sid=' in line:
                    sid = line.split('=')[1].strip()
                    if user and passw and sid:
                        creds[user] = (passw, sid)
                    user = passw = sid = ""
    except:
        pass
    return creds

# ==================== PATTERN & OFFSETS ====================
NEW_AIMBOT_AOB = "FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? FF FF FF FF FF FF FF FF FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? A5 43"

OFFSET_HEAD_READ = 0xB8
OFFSET_HEAD_WRITE = 0xB4
OFFSET_LEFT_READ = 0xEC
OFFSET_RIGHT_READ = 0xE8
OFFSET_SHOULDER_WRITE = 0xA8
OFFSET_AIMBOT_AI_READ = 0xFC
OFFSET_AIMBOT_AI_WRITE = -0x358
OFFSET_MATCH_FLAG = 0xFF
OFFSET_STATE_BYTE1 = 0x647
OFFSET_STATE_BYTE2 = 0x648

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

# ==================== ENTITY FUNCTIONS ====================
def get_entity_state(entity_address):
    try:
        proc = Pymem(current_process_name)
        dead_offset_1 = entity_address + OFFSET_STATE_BYTE1
        dead_offset_2 = entity_address + OFFSET_STATE_BYTE2
        match_offset = entity_address + OFFSET_MATCH_FLAG
        
        dead_byte_1 = read_bytes(proc.process_handle, dead_offset_1, 1)
        dead_byte_2 = read_bytes(proc.process_handle, dead_offset_2, 1)
        match_bytes = read_bytes(proc.process_handle, match_offset, 4)
        proc.close_process()
        
        if dead_byte_1 and dead_byte_2 and match_bytes:
            dead_val_1 = int.from_bytes(dead_byte_1, byteorder='little')
            dead_val_2 = int.from_bytes(dead_byte_2, byteorder='little')
            match_value = int.from_bytes(match_bytes, byteorder='little', signed=False)
            
            is_in_match = match_value != 0
            if not is_in_match:
                return 'not_in_match'
            
            if dead_val_1 == 0x3F:
                return 'alive'
            elif dead_val_1 == 0x3D and dead_val_2 == 0x01:
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

def update_match_status():
    global match_ended, is_initialized
    
    if not is_initialized or not aimbot_addresses:
        match_ended = True
        return
    
    try:
        proc = Pymem(current_process_name)
        entities_in_match = 0
        for entity in aimbot_addresses:
            try:
                match_bytes = read_bytes(proc.process_handle, entity + OFFSET_MATCH_FLAG, 4)
                if match_bytes and len(match_bytes) == 4:
                    match_value = int.from_bytes(match_bytes, byteorder='little', signed=False)
                    if match_value != 0:
                        entities_in_match += 1
            except:
                continue
        proc.close_process()
        
        match_ended = (entities_in_match == 0) and len(aimbot_addresses) > 0
        
    except:
        match_ended = True

def clear_entities():
    global aimbot_addresses, is_initialized, match_ended, original_values
    
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
    original_values = {}

def match_status_monitor():
    while True:
        if is_initialized and aimbot_addresses:
            update_match_status()
        time.sleep(2)

# ==================== SCAN FUNCTION ====================
def HEADLOAD():
    global aimbot_addresses, is_initialized, match_ended
    
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
        match_ended = False
        proc.close_process()
        
        return f"SCAN COMPLETE - {len(aimbot_addresses)} ENTITIES FOUND"
    except Exception as e:
        return f"Scan failed: {str(e)}"

# ==================== AIMBOT FUNCTIONS ====================
def HEADON():
    global aimbot_states, original_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    
    AIMBOT_OFF()
    
    try:
        proc = Pymem(current_process_name)
        for entity in aimbot_addresses:
            if not should_target_entity(entity):
                continue
            key = f"{entity}_head"
            if key not in original_values:
                original_values[key] = read_bytes(proc.process_handle, entity + OFFSET_HEAD_WRITE, 4)
            value_bytes = read_bytes(proc.process_handle, entity + OFFSET_HEAD_READ, 4)
            if value_bytes:
                write_bytes(proc.process_handle, entity + OFFSET_HEAD_WRITE, value_bytes, 4)
        proc.close_process()
        aimbot_states["Head"] = True
        return "Neck enabled"
    except:
        return "Neck failed"

def HEADOFF():
    global aimbot_states, original_values
    try:
        proc = Pymem(current_process_name)
        for key, orig in original_values.items():
            if key.endswith("_head"):
                addr = int(key.split("_")[0])
                try:
                    write_bytes(proc.process_handle, addr + OFFSET_HEAD_WRITE, orig, len(orig))
                except:
                    pass
        proc.close_process()
        aimbot_states["Head"] = False
        return "Neck disabled"
    except:
        aimbot_states["Head"] = False
        return "Neck disabled"

def LEFTSHOULDERON():
    global aimbot_states, original_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    
    AIMBOT_OFF()
    
    try:
        proc = Pymem(current_process_name)
        for entity in aimbot_addresses:
            if not should_target_entity(entity):
                continue
            key = f"{entity}_left"
            if key not in original_values:
                original_values[key] = read_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, 4)
            value_bytes = read_bytes(proc.process_handle, entity + OFFSET_LEFT_READ, 4)
            if value_bytes:
                write_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, value_bytes, 4)
        proc.close_process()
        aimbot_states["LeftShoulder"] = True
        return "Left shoulder enabled"
    except:
        return "Left shoulder failed"

def LEFTSHOULDEROFF():
    global aimbot_states, original_values
    try:
        proc = Pymem(current_process_name)
        for key, orig in original_values.items():
            if key.endswith("_left"):
                addr = int(key.split("_")[0])
                try:
                    write_bytes(proc.process_handle, addr + OFFSET_SHOULDER_WRITE, orig, len(orig))
                except:
                    pass
        proc.close_process()
        aimbot_states["LeftShoulder"] = False
        return "Left shoulder disabled"
    except:
        aimbot_states["LeftShoulder"] = False
        return "Left shoulder disabled"

def RIGHTSHOULDERON():
    global aimbot_states, original_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["AimbotAi"]:
        AIMBOTAIOFF()
    
    AIMBOT_OFF()
    
    try:
        proc = Pymem(current_process_name)
        for entity in aimbot_addresses:
            if not should_target_entity(entity):
                continue
            key = f"{entity}_right"
            if key not in original_values:
                original_values[key] = read_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, 4)
            value_bytes = read_bytes(proc.process_handle, entity + OFFSET_RIGHT_READ, 4)
            if value_bytes:
                write_bytes(proc.process_handle, entity + OFFSET_SHOULDER_WRITE, value_bytes, 4)
        proc.close_process()
        aimbot_states["RightShoulder"] = True
        return "Right shoulder enabled"
    except:
        return "Right shoulder failed"

def RIGHTSHOULDEROFF():
    global aimbot_states, original_values
    try:
        proc = Pymem(current_process_name)
        for key, orig in original_values.items():
            if key.endswith("_right"):
                addr = int(key.split("_")[0])
                try:
                    write_bytes(proc.process_handle, addr + OFFSET_SHOULDER_WRITE, orig, len(orig))
                except:
                    pass
        proc.close_process()
        aimbot_states["RightShoulder"] = False
        return "Right shoulder disabled"
    except:
        aimbot_states["RightShoulder"] = False
        return "Right shoulder disabled"

def AIMBOTAI_ON():
    global aimbot_states, original_values, legit_active, last_mouse_pos, mouse_movement, last_cps_time, cps_toggle
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    
    AIMBOT_OFF()
    
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    point = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    last_mouse_pos = (point.x, point.y)
    mouse_movement = 0
    legit_active = True
    last_cps_time = time.time() * 1000
    cps_toggle = False
    
    threading.Thread(target=_aimbot_ai_loop, daemon=True).start()
    aimbot_states["AimbotAi"] = True
    return f"{legit_settings['x_aimbot_mode']} enabled"

def _aimbot_ai_loop():
    global aimbot_states, legit_active, last_mouse_pos, mouse_movement, last_cps_time, cps_toggle
    
    while aimbot_states["AimbotAi"]:
        if not is_initialized or not aimbot_addresses or match_ended:
            time.sleep(0.01)
            continue
        
        should_be_active = True
        
        if legit_settings['x_aimbot_mode'] == 'Legit Aimbot':
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            point = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            
            dx = abs(point.x - last_mouse_pos[0])
            dy = abs(point.y - last_mouse_pos[1])
            mouse_movement += dx + dy
            last_mouse_pos = (point.x, point.y)
            
            if mouse_movement < legit_settings['pixel_power']:
                should_be_active = False
            else:
                mouse_movement = 0
            
            if should_be_active and legit_settings['advance_maneuver'] > 0:
                current_time = time.time() * 1000
                interval = 1000 / legit_settings['advance_maneuver']
                if current_time - last_cps_time >= interval:
                    last_cps_time = current_time
                    cps_toggle = not cps_toggle
                    should_be_active = cps_toggle
        
        if should_be_active:
            try:
                proc = Pymem(current_process_name)
                for entity in aimbot_addresses:
                    if not should_target_entity(entity):
                        continue
                    
                    key = f"{entity}_ai"
                    if key not in original_values:
                        original_values[key] = read_bytes(proc.process_handle, entity + OFFSET_AIMBOT_AI_WRITE, 4)
                    
                    head_value = read_int(proc.process_handle, entity + OFFSET_AIMBOT_AI_READ)
                    write_int(proc.process_handle, entity + OFFSET_AIMBOT_AI_WRITE, head_value)
                    
                    if legit_settings['x_aimbot_mode'] == 'Legit Aimbot' and legit_settings['move_to_body']:
                        body_offset = 0x10
                        body_value = read_int(proc.process_handle, entity + OFFSET_AIMBOT_AI_READ + body_offset)
                        write_int(proc.process_handle, entity + OFFSET_AIMBOT_AI_WRITE, body_value)
                        
                proc.close_process()
            except:
                pass
        
        time.sleep(0.005)

def AIMBOTAIOFF():
    global aimbot_states, original_values, legit_active
    aimbot_states["AimbotAi"] = False
    legit_active = False
    
    try:
        proc = Pymem(current_process_name)
        for key, orig in original_values.items():
            if key.endswith("_ai"):
                addr = int(key.split("_")[0])
                try:
                    write_bytes(proc.process_handle, addr + OFFSET_AIMBOT_AI_WRITE, orig, len(orig))
                except:
                    pass
        proc.close_process()
        original_values = {k: v for k, v in original_values.items() if not k.endswith("_ai")}
    except:
        pass
    
    return "Aimbot AI disabled"

def AIMBOT_OFF():
    global aimbot_states, original_values, legit_active
    aimbot_states["Head"] = False
    aimbot_states["LeftShoulder"] = False
    aimbot_states["RightShoulder"] = False
    aimbot_states["AimbotAi"] = False
    legit_active = False
    return "All aimbots disabled"

# ==================== HOTKEY MONITOR ====================
def hold_hotkey_monitor():
    global hotkey_state
    
    vk_map = {
        'A': 0x41, 'B': 0x42, 'C': 0x43, 'D': 0x44, 'E': 0x45, 'F': 0x46, 'G': 0x47,
        'H': 0x48, 'I': 0x49, 'J': 0x4A, 'K': 0x4B, 'L': 0x4C, 'M': 0x4D, 'N': 0x4E,
        'O': 0x4F, 'P': 0x50, 'Q': 0x51, 'R': 0x52, 'S': 0x53, 'T': 0x54, 'U': 0x55,
        'V': 0x56, 'W': 0x57, 'X': 0x58, 'Y': 0x59, 'Z': 0x5A,
        '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, '5': 0x35, '6': 0x36,
        '7': 0x37, '8': 0x38, '9': 0x39,
        'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73, 'F5': 0x74, 'F6': 0x75,
        'F7': 0x76, 'F8': 0x77, 'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B,
        'Space': 0x20, 'Enter': 0x0D, 'Shift': 0x10, 'Control': 0x11, 'Alt': 0x12,
        'Tab': 0x09, 'Escape': 0x1B, 'Backspace': 0x08,
        'MouseLeft': 0x01, 'MouseRight': 0x02, 'MouseMiddle': 0x04,
        'MouseButton4': 0x05, 'MouseButton5': 0x06
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
                            AIMBOTAI_ON()
                    threading.Thread(target=delayed_execute, daemon=True).start()
                elif not key_held and hotkey_state["hold_active"]:
                    hotkey_state["hold_active"] = False
                    if not match_ended:
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
    print("[+] Shutting down GHOST PYTHON...")
    AIMBOT_OFF()
    os._exit(0)

# ==================== FLASK APP ====================
app = Flask(__name__)
app.secret_key = 'ghostpython2024'

# ==================== HTML TEMPLATE ====================
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GHOST PYTHON</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', 'Orbitron', monospace;
        }

        body {
            background: linear-gradient(135deg, #0a0a0a 0%, #0d0d0d 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .container {
            max-width: 500px;
            width: 100%;
        }

        .header-card {
            background: rgba(20, 20, 20, 0.95);
            border: 1px solid rgba(255, 41, 41, 0.5);
            border-radius: 16px;
            padding: 24px 20px;
            margin-bottom: 20px;
            text-align: center;
            backdrop-filter: blur(10px);
            box-shadow: 0 0 30px rgba(255, 41, 41, 0.15);
        }

        .header-card h1 {
            font-size: 28px;
            font-weight: 700;
            letter-spacing: 3px;
            background: linear-gradient(135deg, #ff2929, #ff5555, #ff8888);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            text-shadow: 0 0 20px rgba(255, 41, 41, 0.5);
            animation: glow 2s ease-in-out infinite alternate;
        }

        @keyframes glow {
            from { text-shadow: 0 0 10px rgba(255, 41, 41, 0.3); }
            to { text-shadow: 0 0 25px rgba(255, 41, 41, 0.8); }
        }

        .header-card p {
            color: #666;
            font-size: 11px;
            letter-spacing: 2px;
            margin-top: 8px;
        }

        .status-badge {
            display: inline-block;
            margin-top: 12px;
            padding: 5px 16px;
            border-radius: 30px;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
        }

        .status-badge.online {
            background: rgba(30, 58, 46, 0.8);
            color: #4caf50;
            border: 1px solid #4caf50;
            box-shadow: 0 0 8px rgba(76, 175, 80, 0.3);
        }

        .status-badge.offline {
            background: rgba(58, 30, 30, 0.8);
            color: #ef5350;
            border: 1px solid #ef5350;
            box-shadow: 0 0 8px rgba(239, 83, 80, 0.3);
        }

        .current-process-text {
            font-size: 10px;
            color: #555;
            margin-top: 10px;
            letter-spacing: 1px;
        }

        .card {
            background: rgba(20, 20, 20, 0.95);
            border: 1px solid rgba(255, 41, 41, 0.3);
            border-radius: 16px;
            margin-bottom: 20px;
            overflow: hidden;
            backdrop-filter: blur(10px);
        }

        .card-header {
            padding: 14px 20px;
            background: rgba(15, 15, 15, 0.9);
            border-bottom: 1px solid rgba(255, 41, 41, 0.3);
        }

        .card-header h2 {
            font-size: 14px;
            font-weight: 600;
            color: #ff5555;
            letter-spacing: 2px;
        }

        .card-body {
            padding: 20px;
        }

        .process-section {
            background: rgba(26, 18, 18, 0.9);
            border: 1px solid #ff4444;
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 20px;
        }

        .process-section h3 {
            color: #ff8888;
            font-size: 12px;
            margin-bottom: 12px;
            letter-spacing: 1px;
        }

        .process-row {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        select {
            flex: 1;
            padding: 8px 12px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            color: #e0e0e0;
            font-size: 12px;
            cursor: pointer;
            font-family: monospace;
        }

        select:focus {
            outline: none;
            border-color: #ff4444;
        }

        .btn {
            padding: 8px 18px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            color: #ccc;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
            letter-spacing: 1px;
        }

        .btn:hover {
            background: #252525;
            border-color: #555;
        }

        .btn-primary {
            background: #1a1212;
            border-color: #ff4444;
            color: #ff8888;
        }

        .btn-primary:hover {
            background: #2a1a1a;
            border-color: #ff6666;
            box-shadow: 0 0 8px rgba(255, 68, 68, 0.3);
        }

        .btn-danger {
            background: #2a1a1a;
            border-color: #8b3a3a;
            color: #ff8a8a;
        }

        .btn-danger:hover {
            background: #3a1e1e;
            border-color: #aa4a4a;
        }

        .aimbot-panel {
            background: rgba(26, 26, 26, 0.8);
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 20px;
            border: 1px solid rgba(255, 68, 68, 0.3);
        }

        .aimbot-title {
            font-size: 13px;
            font-weight: 700;
            color: #ff5555;
            margin-bottom: 15px;
            text-align: center;
            letter-spacing: 2px;
        }

        .button-group {
            display: flex;
            gap: 15px;
            justify-content: center;
        }

        .btn-aimbot {
            padding: 10px 28px;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 2px;
        }

        .btn-aimbot.active {
            background: #ff2929;
            border-color: #ff2929;
            color: white;
            box-shadow: 0 0 12px rgba(255, 41, 41, 0.5);
        }

        .console {
            background: #0a0a0a;
            border: 1px solid #1a1a1a;
            border-radius: 10px;
            padding: 12px;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            color: #8bc34a;
            height: 100px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .settings-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .settings-row:last-child {
            margin-bottom: 0;
        }

        .settings-label {
            font-size: 12px;
            color: #aaa;
            letter-spacing: 1px;
        }

        hr {
            border: none;
            border-top: 1px solid #2a2a2a;
            margin: 15px 0;
        }

        .hidden {
            display: none;
        }

        .toggle-group {
            display: flex;
            gap: 8px;
        }

        .toggle-btn {
            padding: 5px 14px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 20px;
            color: #888;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            letter-spacing: 1px;
        }

        .toggle-btn.active {
            background: #ff2929;
            border-color: #ff2929;
            color: white;
            box-shadow: 0 0 8px rgba(255, 41, 41, 0.4);
        }

        .toggle-btn:hover {
            background: #2a2a2a;
        }

        .legit-settings {
            background-color: #1a1a2a;
            border-radius: 8px;
            padding: 12px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header-card">
            <h1>GHOST PYTHON</h1>
            <p>STEALTH • PRECISION • SPEED</p>
            <div class="status-badge" id="statusBadge">CHECKING</div>
            <div class="current-process-text" id="currentProcessText">TARGET: HD-PLAYER.EXE</div>
        </div>

        <div class="process-section hidden" id="process-section">
            <h3>OFFLINE - SELECT TARGET</h3>
            <div class="process-row">
                <select id="process-selector">
                    <option value="">SELECT PROCESS</option>
                </select>
                <div class="btn" onclick="refreshProcessList()">REFRESH</div>
                <div class="btn btn-primary" onclick="setTargetProcess()">SET</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2>AIMBOT SYSTEM</h2>
            </div>
            <div class="card-body">
                <div style="margin-bottom: 20px;">
                    <div class="btn btn-primary" style="width: 100%; text-align: center; padding: 10px;" onclick="scanPlayers()">SCAN ENTITIES</div>
                </div>

                <div class="aimbot-panel">
                    <div class="aimbot-title">NECK</div>
                    <div class="button-group">
                        <div class="btn btn-aimbot" id="neckEnableBtn" onclick="enableNeck()">ENABLE</div>
                        <div class="btn btn-aimbot active" id="neckDisableBtn" onclick="disableNeck()">DISABLE</div>
                    </div>
                </div>

                <div class="aimbot-panel">
                    <div class="aimbot-title">LEFT SHOULDER</div>
                    <div class="button-group">
                        <div class="btn btn-aimbot" id="leftEnableBtn" onclick="enableLeft()">ENABLE</div>
                        <div class="btn btn-aimbot active" id="leftDisableBtn" onclick="disableLeft()">DISABLE</div>
                    </div>
                </div>

                <div class="aimbot-panel">
                    <div class="aimbot-title">RIGHT SHOULDER</div>
                    <div class="button-group">
                        <div class="btn btn-aimbot" id="rightEnableBtn" onclick="enableRight()">ENABLE</div>
                        <div class="btn btn-aimbot active" id="rightDisableBtn" onclick="disableRight()">DISABLE</div>
                    </div>
                </div>

                <hr>

                <div class="aimbot-panel">
                    <div class="aimbot-title">SPECIAL AIMBOT</div>
                    <div class="button-group">
                        <div class="btn btn-aimbot" id="aiEnableBtn" onclick="enableAi()">ENABLE</div>
                        <div class="btn btn-aimbot active" id="aiDisableBtn" onclick="disableAi()">DISABLE</div>
                    </div>
                </div>

                <div class="settings-row" style="margin-top: 15px;">
                    <span class="settings-label">IGNORE KNOCKED</span>
                    <div class="toggle-group">
                        <div class="toggle-btn active" id="ignoreYesBtn" onclick="setIgnoreKnocked(true)">YES</div>
                        <div class="toggle-btn" id="ignoreNoBtn" onclick="setIgnoreKnocked(false)">NO</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2>SETTINGS</h2>
            </div>
            <div class="card-body">
                <div class="settings-row">
                    <span class="settings-label">HOLD KEY</span>
                    <select id="hold-hotkey-selector">
                        <option value="">NONE</option>
                        <optgroup label="KEYS">
                            <option value="X">X</option><option value="C">C</option><option value="V">V</option>
                            <option value="F">F</option><option value="MouseLeft">MOUSE LEFT</option>
                            <option value="MouseRight">MOUSE RIGHT</option>
                            <option value="MouseMiddle">MOUSE MIDDLE</option>
                        </optgroup>
                    </select>
                </div>

                <div class="settings-row">
                    <span class="settings-label">HOLD DELAY (MS)</span>
                    <input type="range" min="0" max="300" value="50" id="delaySlider" style="width: 200px;">
                    <span id="delayValue">50ms</span>
                </div>

                <hr>

                <div class="settings-row">
                    <span class="settings-label">LOGOUT</span>
                    <div class="btn" onclick="logout()" style="padding: 5px 16px;">LOGOUT</div>
                </div>

                <div class="settings-row">
                    <span class="settings-label">EXIT</span>
                    <div class="btn btn-danger" onclick="exitApp()" style="padding: 5px 16px;">EXIT</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2>CONSOLE</h2>
            </div>
            <div class="card-body">
                <div class="console" id="console">[SYSTEM] READY</div>
            </div>
        </div>
    </div>

    <script>
        const consoleEl = document.getElementById('console');
        const holdHotkeySelector = document.getElementById('hold-hotkey-selector');
        const delaySlider = document.getElementById('delaySlider');
        const delayValueSpan = document.getElementById('delayValue');

        function log(message) {
            const now = new Date();
            const time = now.toLocaleTimeString();
            if (consoleEl.textContent.length > 0 && !consoleEl.textContent.endsWith('\\n')) {
                consoleEl.textContent += '\\n';
            }
            consoleEl.textContent += `[${time}] ${message}`;
            consoleEl.scrollTop = consoleEl.scrollHeight;
            if (consoleEl.textContent.length > 5000) {
                consoleEl.textContent = consoleEl.textContent.slice(-4000);
            }
        }

        function updateButtonState(enableId, disableId, isEnabled) {
            const enableBtn = document.getElementById(enableId);
            const disableBtn = document.getElementById(disableId);
            if (isEnabled) {
                enableBtn.classList.add('active');
                disableBtn.classList.remove('active');
            } else {
                enableBtn.classList.remove('active');
                disableBtn.classList.add('active');
            }
        }

        function scanPlayers() {
            log('SCANNING FOR ENTITIES');
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'aimbotscan' })
            })
            .then(r => r.json())
            .then(d => { if (d.message) log(d.message); })
            .catch(e => log(`ERROR: ${e.message}`));
        }

        function enableNeck() {
            log('NECK ENABLED');
            updateButtonState('neckEnableBtn', 'neckDisableBtn', true);
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'aimbotenable' })
            }).catch(e => log(`ERROR: ${e.message}`));
        }

        function disableNeck() {
            log('NECK DISABLED');
            updateButtonState('neckEnableBtn', 'neckDisableBtn', false);
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'aimbotdisable' })
            }).catch(e => log(`ERROR: ${e.message}`));
        }

        function enableLeft() {
            log('LEFT SHOULDER ENABLED');
            updateButtonState('leftEnableBtn', 'leftDisableBtn', true);
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'leftShoulderOn' })
            }).catch(e => log(`ERROR: ${e.message}`));
        }

        function disableLeft() {
            log('LEFT SHOULDER DISABLED');
            updateButtonState('leftEnableBtn', 'leftDisableBtn', false);
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'leftShoulderOff' })
            }).catch(e => log(`ERROR: ${e.message}`));
        }

        function enableRight() {
            log('RIGHT SHOULDER ENABLED');
            updateButtonState('rightEnableBtn', 'rightDisableBtn', true);
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'rightShoulderOn' })
            }).catch(e => log(`ERROR: ${e.message}`));
        }

        function disableRight() {
            log('RIGHT SHOULDER DISABLED');
            updateButtonState('rightEnableBtn', 'rightDisableBtn', false);
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'rightShoulderOff' })
            }).catch(e => log(`ERROR: ${e.message}`));
        }

        function enableAi() {
            log('AIMBOT AI ENABLED');
            updateButtonState('aiEnableBtn', 'aiDisableBtn', true);
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'AimbotAion' })
            }).catch(e => log(`ERROR: ${e.message}`));
        }

        function disableAi() {
            log('AIMBOT AI DISABLED');
            updateButtonState('aiEnableBtn', 'aiDisableBtn', false);
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'AimbotAioff' })
            }).catch(e => log(`ERROR: ${e.message}`));
        }

        function setIgnoreKnocked(ignore) {
            fetch('/set_ignore_knocked', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ignore_knocked: ignore })
            });
            log(`IGNORE KNOCKED: ${ignore ? 'YES' : 'NO'}`);
            if (ignore) {
                document.getElementById('ignoreYesBtn').classList.add('active');
                document.getElementById('ignoreNoBtn').classList.remove('active');
            } else {
                document.getElementById('ignoreYesBtn').classList.remove('active');
                document.getElementById('ignoreNoBtn').classList.add('active');
            }
        }

        function logout() {
            fetch('/logout', { method: 'POST' }).then(() => window.location.href = '/');
        }

        function exitApp() {
            if (confirm('EXIT GHOST PYTHON?')) {
                fetch('/exit', { method: 'POST' });
                log('SYSTEM SHUTDOWN');
                setTimeout(() => window.close(), 1500);
            }
        }

        function saveHoldHotkey(key) {
            fetch('/save_hold_hotkey', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hotkey: key })
            });
        }

        function saveHoldDelay(delay) {
            fetch('/save_hold_delay', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delay: delay })
            });
        }

        function refreshProcessList() {
            fetch('/get_processes')
                .then(r => r.json())
                .then(data => {
                    const selector = document.getElementById('process-selector');
                    if (selector && data.success) {
                        selector.innerHTML = '<option value="">SELECT PROCESS</option>';
                        data.processes.forEach(p => {
                            const opt = document.createElement('option');
                            opt.value = p.name;
                            opt.textContent = `${p.name} (PID: ${p.pid})`;
                            selector.appendChild(opt);
                        });
                        log('PROCESS LIST UPDATED');
                    }
                });
        }

        function setTargetProcess() {
            const selector = document.getElementById('process-selector');
            const selected = selector.value;
            if (!selected) { log('SELECT A PROCESS FIRST'); return; }
            fetch('/set_target_process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ process_name: selected })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    log(`TARGET SET: ${selected}`);
                    document.getElementById('currentProcessText').textContent = `TARGET: ${selected.toUpperCase()}`;
                    updateStatus();
                }
            });
        }

        function updateStatus() {
            fetch('/get_hd_player_status')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('statusBadge');
                    const processSection = document.getElementById('process-section');
                    if (data.is_running) {
                        badge.textContent = 'ONLINE';
                        badge.className = 'status-badge online';
                        processSection.classList.add('hidden');
                    } else {
                        badge.textContent = 'OFFLINE';
                        badge.className = 'status-badge offline';
                        processSection.classList.remove('hidden');
                    }
                    document.getElementById('currentProcessText').textContent = `TARGET: ${data.current_process.toUpperCase()}`;
                });
        }

        document.addEventListener('DOMContentLoaded', () => {
            updateStatus();
            setInterval(updateStatus, 3000);
            refreshProcessList();

            fetch('/get_hold_hotkey').then(r => r.json()).then(d => {
                if (d.success && d.hotkey) holdHotkeySelector.value = d.hotkey;
            });

            holdHotkeySelector.addEventListener('change', () => {
                const key = holdHotkeySelector.value;
                saveHoldHotkey(key);
                log(`HOLD KEY: ${key || 'NONE'}`);
            });

            delaySlider.addEventListener('input', (e) => {
                delayValueSpan.textContent = e.target.value + 'ms';
                saveHoldDelay(parseInt(e.target.value));
            });
            delaySlider.addEventListener('change', (e) => {
                log(`HOLD DELAY: ${e.target.value}ms`);
            });

            log('GHOST PYTHON ACTIVE');
        });
    </script>
</body>
</html>"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>GHOST PYTHON - LOGIN</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            margin: 0;
            padding: 0;
            background: #0f0f0f;
            font-family: 'Segoe UI', sans-serif;
            color: #fff;
            overflow: hidden;
        }
        .container {
            display: flex;
            height: 100vh;
            justify-content: center;
            align-items: center;
            position: relative;
            z-index: 1;
        }
        .login-box {
            background: #1b1b1b;
            border: 1px solid #ff2929;
            border-radius: 15px;
            padding: 40px;
            box-shadow: 0 0 25px rgba(255, 41, 41, 0.4);
            width: 360px;
        }
        .login-box h2 {
            text-align: center;
            margin-bottom: 30px;
            color: #ff2929;
            letter-spacing: 2px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 6px;
            font-size: 12px;
            color: #ccc;
            letter-spacing: 1px;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            background: #0f0f0f;
            border: 1px solid #30363d;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            outline: none;
        }
        .form-group input:focus {
            border-color: #ff2929;
        }
        .btn {
            width: 100%;
            background: #ff2929;
            color: #000;
            padding: 12px;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.3s;
            letter-spacing: 1px;
        }
        .btn:hover {
            background: #ff5555;
        }
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #dc3545;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            display: none;
            z-index: 9999;
            font-weight: bold;
        }
        #particles-js {
            position: absolute;
            width: 100%;
            height: 100%;
            z-index: 0;
        }
        .loading-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(15, 15, 15, 0.95);
            z-index: 99999;
            display: none;
            align-items: center;
            justify-content: center;
            flex-direction: column;
        }
        .loader-ring {
            border: 5px solid rgba(255, 41, 41, 0.2);
            border-top: 5px solid #ff2929;
            border-radius: 50%;
            width: 70px;
            height: 70px;
            animation: spin 1s linear infinite;
        }
        .loader-text {
            margin-top: 15px;
            font-size: 14px;
            color: #ff2929;
            font-weight: bold;
            letter-spacing: 2px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div id="particles-js"></div>
    <div class="loading-overlay" id="loadingOverlay">
        <div class="loader-ring"></div>
        <div class="loader-text">VERIFYING</div>
    </div>
    <div class="container">
        <div class="login-box">
            <h2>GHOST PYTHON</h2>
            <form method="POST" action="/" onsubmit="showLoading()">
                <div class="form-group">
                    <label>USERNAME</label>
                    <input name="username" type="text" id="username" required autocomplete="off">
                </div>
                <div class="form-group">
                    <label>PASSWORD</label>
                    <input name="password" type="password" id="password" required>
                </div>
                <button class="btn" type="submit">LOGIN</button>
            </form>
            {% if error %}
                <div class="notification" style="display:block; position:relative; margin-top:15px;">{{ error }}</div>
            {% endif %}
        </div>
    </div>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
    <script>
        particlesJS("particles-js", {
            "particles": {
                "number": { "value": 80 },
                "color": { "value": "#ff2929" },
                "shape": { "type": "circle" },
                "opacity": { "value": 0.5 },
                "size": { "value": 3 },
                "move": { "enable": true, "speed": 5 }
            },
            "interactivity": {
                "events": { "onhover": { "enable": true, "mode": "repulse" } }
            }
        });
        function showLoading() { document.getElementById("loadingOverlay").style.display = "flex"; }
    </script>
</body>
</html>"""

# ==================== FLASK ROUTES ====================
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
            return render_template_string(LOGIN_HTML, error="INVALID CREDENTIALS OR SID MISMATCH")
    
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
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    data = request.get_json()
    command = data.get('command')
    
    result = "Unknown command"
    
    if command == "aimbotscan":
        result = HEADLOAD()
    elif command == "aimbotenable":
        result = HEADON()
    elif command == "aimbotdisable":
        result = AIMBOT_OFF()
    elif command == "leftShoulderOn":
        result = LEFTSHOULDERON()
    elif command == "leftShoulderOff":
        result = LEFTSHOULDEROFF()
    elif command == "rightShoulderOn":
        result = RIGHTSHOULDERON()
    elif command == "rightShoulderOff":
        result = RIGHTSHOULDEROFF()
    elif command == "AimbotAion":
        result = AIMBOTAI_ON()
    elif command == "AimbotAioff":
        result = AIMBOTAIOFF()
    
    return jsonify({"success": True, "message": result})

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

@app.route('/set_ignore_knocked', methods=['POST'])
def set_ignore_knocked_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    data = request.get_json()
    user_settings['ignore_knocked'] = data.get('ignore_knocked', True)
    return jsonify({"success": True})

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
    print("=" * 50)
    print("GHOST PYTHON")
    print("=" * 50)
    print(f"Server running on: http://localhost:{SERVER_PORT}")
    print(f"Target Process: {current_process_name}")
    print("=" * 50)
    print("Press Ctrl+C to exit")
    print("=" * 50)
    
    threading.Thread(target=hold_hotkey_monitor, daemon=True).start()
    threading.Thread(target=match_status_monitor, daemon=True).start()
    
    try:
        app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n[+] Shutting down...")
        AIMBOT_OFF()
        print("[+] Goodbye!")
