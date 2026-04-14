#!/usr/bin/env python
# VOLT STREAMER - CURSED CORE ENGINE + GHOST AUTH

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

# ==================== HIDE CONSOLE ====================
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

original_values = {}

hotkey_state = {
    "hold_key": None,
    "hold_active": False,
    "delay": 50
}

user_settings = {
    'ignore_knocked': True,
    'hotkey_aimbot': 'AimbotAi'
}

# ==================== GITHUB AUTH (YOUR METHOD) ====================
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

# ==================== PATTERN & OFFSETS (CURSED CORE) ====================
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

def update_entity_states():
    global entity_states, match_ended
    
    entities_in_match = 0
    entity_states['alive'] = set()
    entity_states['knocked'] = set()
    entity_states['dead'] = set()
    
    try:
        proc = Pymem(current_process_name)
        for entity in aimbot_addresses:
            try:
                match_offset = entity + OFFSET_MATCH_FLAG
                match_bytes = read_bytes(proc.process_handle, match_offset, 4)
                if match_bytes and len(match_bytes) == 4:
                    match_value = int.from_bytes(match_bytes, byteorder='little', signed=False)
                    if match_value != 0:
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
    global aimbot_addresses, is_initialized, entity_states, match_ended, original_values
    
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
    entity_states = {'alive': set(), 'knocked': set(), 'dead': set()}

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
        
        if not monitoring_active:
            start_entity_monitoring()
        
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
    global aimbot_states, original_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    if aimbot_states["Head"]:
        HEADOFF()
    if aimbot_states["LeftShoulder"]:
        LEFTSHOULDEROFF()
    if aimbot_states["RightShoulder"]:
        RIGHTSHOULDEROFF()
    
    AIMBOT_OFF()
    
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
        proc.close_process()
        aimbot_states["AimbotAi"] = True
        return "Aimbot AI enabled"
    except:
        return "Aimbot AI failed"

def AIMBOTAIOFF():
    global aimbot_states, original_values
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
        aimbot_states["AimbotAi"] = False
        return "Aimbot AI disabled"
    except:
        aimbot_states["AimbotAi"] = False
        return "Aimbot AI disabled"

def AIMBOT_OFF():
    global aimbot_states, original_values
    aimbot_states["Head"] = False
    aimbot_states["LeftShoulder"] = False
    aimbot_states["RightShoulder"] = False
    aimbot_states["AimbotAi"] = False
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
    print("[+] Shutting down VOLT Streamer...")
    AIMBOT_OFF()
    os._exit(0)

# ==================== FLASK APP ====================
app = Flask(__name__)
app.secret_key = 'voltstreamer2024'

# ==================== HTML TEMPLATE ====================
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta charset="UTF-8" />
    <title>VOLT Streamer Dashboard</title>
    <style>
        * {
            box-sizing: border-box;
            font-family: 'Segoe UI', sans-serif;
        }

        body {
            margin: 0;
            background-color: #111;
            color: #eee;
        }

        .container {
            max-width: 700px;
            margin: 20px auto;
            padding: 0 20px;
        }

        .panel {
            background-color: #1e1e1e;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 10px;
            box-shadow: 0 0 8px rgba(0, 0, 0, 0.5);
        }

        .panel h2 {
            margin-top: 0;
            font-size: 18px;
            color: #90caf9;
        }

        .status {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .badge {
            padding: 4px 10px;
            border-radius: 8px;
            background-color: #2e7d32;
            color: white;
            font-size: 12px;
            font-weight: bold;
        }

        .badge.online {
            background-color: #2e7d32;
        }

        .badge.offline {
            background-color: #dc3545;
        }

        .section-buttons, .aim-buttons, .tab-buttons, .settings-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .button {
            background-color: #333;
            color: #ccc;
            padding: 8px 12px;
            border-radius: 8px;
            cursor: pointer;
            border: 1px solid #444;
            transition: 0.2s;
            user-select: none;
            flex-shrink: 0;
            text-align: center;
        }

        .button:hover {
            background-color: #444;
        }

        .button.active {
            background-color: #ff2929;
            color: white;
            border-color: #ff2929;
        }

        .button.exit {
            background-color: #dc3545;
            color: white;
            border-color: #dc3545;
        }

        .button.exit:hover {
            background-color: #c82333;
        }

        .tab-buttons {
            display: flex;
            justify-content: space-around;
            margin: 10px 0;
        }

        .tab-buttons .button {
            flex: 1;
            text-align: center;
        }

        .console {
            background-color: #0d0d0d;
            border: 1px solid #222;
            padding: 12px;
            border-radius: 8px;
            min-height: 100px;
            font-family: monospace;
            color: #90ee90;
            overflow-y: auto;
            max-height: 150px;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .aim-section, .settings-section {
            margin-top: 10px;
        }

        .aim-row, .settings-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            flex-wrap: wrap;
            gap: 10px;
        }

        .aim-label, .settings-label {
            font-size: 14px;
            margin-bottom: 4px;
            min-width: 140px;
        }

        .note {
            font-size: 12px;
            color: #888;
            margin-top: 2px;
        }

        select {
            padding: 8px;
            background-color: #222;
            color: #eee;
            border: 1px solid #444;
            border-radius: 8px;
            min-width: 160px;
            cursor: pointer;
        }

        .content-panel {
            display: none;
        }

        .content-panel.active {
            display: block;
        }

        #notifications-container {
            position: fixed;
            top: 12px;
            right: 12px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 1000;
            max-width: 320px;
            pointer-events: none;
        }

        .notification {
            background-color: #2e7d32;
            color: white;
            padding: 12px 18px;
            border-radius: 8px;
            box-shadow: 0 4px 10px rgba(46, 125, 50, 0.7);
            font-weight: 600;
            font-size: 14px;
            user-select: none;
            pointer-events: auto;
            opacity: 0;
            transform: translateX(100%);
            animation: slideIn 0.3s forwards, fadeOut 0.3s forwards 3s;
        }

        @keyframes slideIn {
            to { opacity: 1; transform: translateX(0); }
        }

        @keyframes fadeOut {
            to { opacity: 0; transform: translateX(100%); }
        }

        .entity-info {
            background-color: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 12px;
            margin-top: 8px;
            width: 100%;
        }

        .entity-stats {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .entity-stat {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 13px;
        }

        .stat-label {
            color: #ccc;
            font-weight: 500;
        }

        .stat-value {
            color: #90ee90;
            font-weight: bold;
            background-color: #2a2a2a;
            padding: 2px 8px;
            border-radius: 4px;
            min-width: 40px;
            text-align: center;
        }

        .slider-container {
            width: 100%;
            margin: 10px 0;
        }

        .slider-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            font-size: 14px;
        }

        .slider-value {
            color: #90caf9;
            font-weight: bold;
        }

        .slider {
            -webkit-appearance: none;
            width: 100%;
            height: 6px;
            border-radius: 3px;
            background: #333;
            outline: none;
        }

        .slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #ff2929;
            cursor: pointer;
            border: 2px solid #fff;
        }

        .alternative-process-section {
            background-color: #2a1a1a;
            border: 1px solid #ff4444;
            border-radius: 8px;
            padding: 12px;
            margin-top: 8px;
        }

        .process-selector-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            flex-wrap: wrap;
            gap: 10px;
        }

        .display-none {
            display: none;
        }

        hr {
            border: none;
            border-top: 1px solid #2a2a2a;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="panel">
            <div class="status">
                <div>
                    <strong>VOLT STREAMER</strong><br />
                    <span id="statusText">Checking process status...</span><br />
                    <span id="currentProcessText" class="current-process" style="font-size:12px;color:#888;">Process: HD-Player.exe</span>
                </div>
                <div class="badge" id="statusBadge">Checking...</div>
            </div>
        </div>

        <div class="panel alternative-process-section display-none" id="alternative-process-section">
            <h2>Alternative Process Selector</h2>
            <div class="process-selector-row">
                <div>
                    <div class="process-selector-label">Select Process</div>
                    <div class="note">Current process is offline. Select an alternative process to attach to.</div>
                </div>
                <div class="section-buttons">
                    <select id="process-selector">
                        <option value="">Select a process...</option>
                    </select>
                    <div class="button" id="refresh-processes" onclick="updateProcessList()">Refresh</div>
                    <div class="button" onclick="setTargetProcess()">Set Process</div>
                </div>
            </div>
        </div>

        <div class="panel">
            <h2>Entity Monitoring</h2>
            <div class="aim-row">
                <div>
                    <div class="aim-label">Entity Information</div>
                    <div class="note">Live match status (updates every second)</div>
                </div>
                <div class="entity-info">
                    <div class="entity-stats">
                        <div class="entity-stat">
                            <span class="stat-label">Alive Players:</span>
                            <span class="stat-value" id="aliveCount">0</span>
                        </div>
                        <div class="entity-stat">
                            <span class="stat-label">Knocked Players:</span>
                            <span class="stat-value" id="knockedCount">0</span>
                        </div>
                        <div class="entity-stat">
                            <span class="stat-label">Total Entities:</span>
                            <span class="stat-value" id="totalCount">0</span>
                        </div>
                        <div class="entity-stat">
                            <span class="stat-label">Match Status:</span>
                            <span class="stat-value" id="matchStatus">Checking...</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="panel">
            <div class="tab-buttons">
                <div class="button active" data-tab="headshot">Headshot</div>
                <div class="button" data-tab="settings">Settings</div>
            </div>
        </div>

        <div class="panel content-panel active" id="headshot">
            <h2>Aimbot Options</h2>
            <div class="aim-section">
                <div class="aim-row">
                    <div>
                        <div class="aim-label">Scan Enemies</div>
                        <div class="note">Scans enemies in the match</div>
                    </div>
                    <div class="button" onclick="sendCommand('aimbotscan')">Scan Players</div>
                </div>

                <div class="aim-row">
                    <div>
                        <div class="aim-label">Aim Position</div>
                        <div class="note">Neck / Disable</div>
                    </div>
                    <div class="aim-buttons">
                        <div class="button" id="neckBtn" onclick="sendCommand('aimbotenable')">Neck</div>
                        <div class="button active" id="defaultBtn" onclick="sendCommand('aimbotdisable')">Disable</div>
                    </div>
                </div>

                <div class="aim-row">
                    <div>
                        <div class="aim-label">Other Aim Position</div>
                        <div class="note">Select aimbot type</div>
                    </div>
                    <select id="other-aimpos" onchange="updateSelectedAimbot()">
                        <option value="RightShoulder">Right Shoulder</option>
                        <option value="LeftShoulder">Left Shoulder</option>
                        <option value="AimbotAi">Aimbot Ai</option>
                    </select>
                </div>

                <div class="aim-row leftShoulder display-none">
                    <div>
                        <div class="aim-label">Left Shoulder</div>
                        <div class="note">Enable/Disable Left Shoulder</div>
                    </div>
                    <div class="aim-buttons">
                        <div class="button" id="leftEnableBtn" onclick="sendCommand('leftShoulderOn')">Enable</div>
                        <div class="button active" id="leftDisableBtn" onclick="sendCommand('leftShoulderOff')">Disable</div>
                    </div>
                </div>

                <div class="aim-row rightShoulder">
                    <div>
                        <div class="aim-label">Right Shoulder</div>
                        <div class="note">Enable/Disable Right Shoulder</div>
                    </div>
                    <div class="aim-buttons">
                        <div class="button" id="rightEnableBtn" onclick="sendCommand('rightShoulderOn')">Enable</div>
                        <div class="button active" id="rightDisableBtn" onclick="sendCommand('rightShoulderOff')">Disable</div>
                    </div>
                </div>

                <div class="aim-row Aiaimbot display-none">
                    <div>
                        <div class="aim-label">Aimbot Ai</div>
                        <div class="note">Enable/Disable Aimbot AI</div>
                    </div>
                    <div class="aim-buttons">
                        <div class="button" id="aiEnableBtn" onclick="sendCommand('AimbotAion')">Enable</div>
                        <div class="button active" id="aiDisableBtn" onclick="sendCommand('AimbotAioff')">Disable</div>
                    </div>
                </div>

                <hr>

                <div class="aim-row">
                    <div>
                        <div class="aim-label">Ignore Knocked Enemies</div>
                        <div class="note">When enabled, aimbot ignores knocked players</div>
                    </div>
                    <div class="aim-buttons">
                        <div class="button active" id="ignoreYesBtn" onclick="setIgnoreKnocked(true)">Yes</div>
                        <div class="button" id="ignoreNoBtn" onclick="setIgnoreKnocked(false)">No</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="panel content-panel" id="settings">
            <h2>Settings</h2>
            <div class="settings-section">
                <div class="settings-row">
                    <div>
                        <div class="settings-label">Headshot Toggle (Hold)</div>
                        <div class="note">Hold key for Aimbot AI</div>
                    </div>
                    <select id="hold-hotkey-selector">
                        <option value="">None</option>
                        <optgroup label="Alphabet Keys">
                            <option value="A">A</option><option value="B">B</option><option value="C">C</option>
                            <option value="D">D</option><option value="E">E</option><option value="F">F</option>
                            <option value="G">G</option><option value="H">H</option><option value="I">I</option>
                            <option value="J">J</option><option value="K">K</option><option value="L">L</option>
                            <option value="M">M</option><option value="N">N</option><option value="O">O</option>
                            <option value="P">P</option><option value="Q">Q</option><option value="R">R</option>
                            <option value="S">S</option><option value="T">T</option><option value="U">U</option>
                            <option value="V">V</option><option value="W">W</option><option value="X">X</option>
                            <option value="Y">Y</option><option value="Z">Z</option>
                        </optgroup>
                        <optgroup label="Mouse Buttons">
                            <option value="MouseLeft">Mouse Left</option>
                            <option value="MouseRight">Mouse Right</option>
                            <option value="MouseMiddle">Mouse Middle</option>
                            <option value="MouseButton4">Mouse Button 4</option>
                            <option value="MouseButton5">Mouse Button 5</option>
                        </optgroup>
                    </select>
                </div>

                <div class="settings-row">
                    <div>
                        <div class="settings-label">Hold Key Delay</div>
                        <div class="note">Delay before aimbot activates when holding key</div>
                    </div>
                    <div class="slider-container">
                        <div class="slider-label">
                            <span>Delay:</span>
                            <span class="slider-value" id="delayValue">50ms</span>
                        </div>
                        <input type="range" min="0" max="300" value="50" class="slider" id="delaySlider">
                    </div>
                </div>

                <hr>

                <div class="settings-row">
                    <div>
                        <div class="settings-label">Log Out</div>
                        <div class="note">Logs you out of the website.</div>
                    </div>
                    <div class="button" onclick="logout()">Log Out</div>
                </div>

                <div class="settings-row">
                    <div>
                        <div class="settings-label">Exit Application</div>
                        <div class="note">Closes the VOLT Streamer application</div>
                    </div>
                    <div class="button exit" onclick="exitApplication()">Exit</div>
                </div>
            </div>
        </div>

        <div class="panel">
            <h2>Console</h2>
            <div class="console" id="console"></div>
        </div>
    </div>

    <div id="notifications-container"></div>

    <script>
        const consoleEl = document.getElementById('console');
        const notificationsContainer = document.getElementById('notifications-container');
        const holdHotkeySelector = document.getElementById('hold-hotkey-selector');
        const delaySlider = document.getElementById('delaySlider');
        const delayValueSpan = document.getElementById('delayValue');

        function log(message) {
            const now = new Date();
            const time = now.toLocaleTimeString();
            consoleEl.textContent += `[${time}] ${message}\\n`;
            consoleEl.scrollTop = consoleEl.scrollHeight;
            if (consoleEl.textContent.length > 5000) consoleEl.textContent = consoleEl.textContent.slice(-4000);
        }

        function showNotification(message) {
            const notif = document.createElement('div');
            notif.className = 'notification';
            notif.textContent = message;
            notificationsContainer.appendChild(notif);
            setTimeout(() => { if (notif.parentNode) notif.remove(); }, 3500);
        }

        function updateButtonState(buttonId, isActive) {
            const btn = document.getElementById(buttonId);
            if (btn) isActive ? btn.classList.add('active') : btn.classList.remove('active');
        }

        function sendCommand(command) {
            if (command === 'aimbotscan') log('Scanning for entities...');
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: command })
            })
            .then(r => r.json())
            .then(d => { if (d.message) log(d.message); })
            .catch(e => log(`Error: ${e.message}`));
        }

        function logout() {
            fetch('/logout', { method: 'POST' }).then(() => window.location.href = '/');
        }

        function exitApplication() {
            if (confirm('Are you sure you want to exit VOLT Streamer?')) {
                fetch('/exit', { method: 'POST' });
                showNotification('Shutting down...');
                setTimeout(() => window.close(), 1500);
            }
        }

        function updateSelectedAimbot() {
            const val = document.getElementById('other-aimpos').value;
            fetch('/update_selected_aimbot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ aimbot: val })
            });
        }

        function setIgnoreKnocked(ignore) {
            fetch('/set_ignore_knocked', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ignore_knocked: ignore })
            });
            log(`Ignore knocked enemies: ${ignore ? 'Yes' : 'No'}`);
            if (ignore) {
                updateButtonState('ignoreYesBtn', true);
                updateButtonState('ignoreNoBtn', false);
            } else {
                updateButtonState('ignoreYesBtn', false);
                updateButtonState('ignoreNoBtn', true);
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

        function updateHDPlayerStatus() {
            fetch('/get_hd_player_status')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('statusBadge');
                    const statusText = document.getElementById('statusText');
                    const currentProcessText = document.getElementById('currentProcessText');
                    const altSection = document.getElementById('alternative-process-section');
                    
                    if (data.is_running) {
                        badge.textContent = 'Online';
                        badge.className = 'badge online';
                        statusText.textContent = 'Connected to VOLT';
                        currentProcessText.textContent = `Process: ${data.current_process}`;
                        altSection.classList.add('display-none');
                    } else {
                        badge.textContent = 'Offline';
                        badge.className = 'badge offline';
                        statusText.textContent = 'Process Offline';
                        currentProcessText.textContent = `Process: ${data.current_process}`;
                        altSection.classList.remove('display-none');
                    }
                });
        }

        function updateProcessList() {
            fetch('/get_processes')
                .then(r => r.json())
                .then(data => {
                    const selector = document.getElementById('process-selector');
                    if (selector && data.success) {
                        selector.innerHTML = '<option value="">Select a process...</option>';
                        data.processes.forEach(p => {
                            const opt = document.createElement('option');
                            opt.value = p.name;
                            opt.textContent = `${p.name} (PID: ${p.pid})`;
                            selector.appendChild(opt);
                        });
                        showNotification('Process list updated');
                    }
                });
        }

        function setTargetProcess() {
            const selector = document.getElementById('process-selector');
            const selected = selector.value;
            if (!selected) { showNotification('Select a process first'); return; }
            fetch('/set_target_process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ process_name: selected })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showNotification(`Target process set to: ${selected}`);
                    document.getElementById('currentProcessText').textContent = `Process: ${selected}`;
                    updateHDPlayerStatus();
                }
            });
        }

        function updateEntityInfo() {
            fetch('/get_entity_info')
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('aliveCount').textContent = data.alive;
                        document.getElementById('knockedCount').textContent = data.knocked;
                        document.getElementById('totalCount').textContent = data.total;
                        const matchStatus = document.getElementById('matchStatus');
                        if (data.match_active && !data.match_ended) {
                            matchStatus.textContent = 'Active';
                            matchStatus.style.color = '#90ee90';
                        } else {
                            matchStatus.textContent = 'Ended';
                            matchStatus.style.color = '#ff6b6b';
                        }
                    }
                }).catch(e => console.log('Entity error:', e));
        }

        document.addEventListener('DOMContentLoaded', () => {
            updateHDPlayerStatus();
            setInterval(updateHDPlayerStatus, 3000);
            setInterval(updateEntityInfo, 1000);
            updateProcessList();

            fetch('/get_hold_hotkey').then(r => r.json()).then(d => {
                if (d.success && d.hotkey) holdHotkeySelector.value = d.hotkey;
            });

            holdHotkeySelector.addEventListener('change', () => {
                const key = holdHotkeySelector.value;
                if (key) { saveHoldHotkey(key); log(`Hold hotkey set to: ${key}`); showNotification(`Hold hotkey set to: ${key}`); }
                else { saveHoldHotkey(''); log('Hold hotkey cleared'); showNotification('Hold hotkey cleared'); }
            });

            delaySlider.addEventListener('input', (e) => { delayValueSpan.textContent = e.target.value + 'ms'; });
            delaySlider.addEventListener('change', (e) => {
                const val = parseInt(e.target.value);
                saveHoldDelay(val);
                log(`Hold delay set to ${val}ms`);
                showNotification(`Hold delay set to ${val}ms`);
            });

            const otherSelect = document.getElementById('other-aimpos');
            const leftSec = document.querySelector('.leftShoulder');
            const rightSec = document.querySelector('.rightShoulder');
            const aiSec = document.querySelector('.Aiaimbot');
            
            otherSelect.addEventListener('change', () => {
                const val = otherSelect.value;
                leftSec.classList.add('display-none');
                rightSec.classList.add('display-none');
                aiSec.classList.add('display-none');
                if (val === 'LeftShoulder') leftSec.classList.remove('display-none');
                else if (val === 'RightShoulder') rightSec.classList.remove('display-none');
                else if (val === 'AimbotAi') aiSec.classList.remove('display-none');
            });

            const tabs = document.querySelectorAll('.tab-buttons .button');
            const panels = document.querySelectorAll('.content-panel');
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    const target = tab.getAttribute('data-tab');
                    tabs.forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    panels.forEach(p => p.classList.remove('active'));
                    document.getElementById(target).classList.add('active');
                });
            });
        });
    </script>
</body>
</html>"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>VOLT Streamer - Login</title>
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
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 6px;
            font-size: 14px;
            color: #ccc;
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
        }
        .btn:hover {
            background: #5462e7;
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
            font-size: 18px;
            color: #ff2929;
            font-weight: bold;
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
        <div class="loader-text">Verifying...</div>
    </div>
    <div class="container">
        <div class="login-box">
            <h2>VOLT STREAMER</h2>
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
            return render_template_string(LOGIN_HTML, error="Invalid credentials or SID mismatch")
    
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

@app.route('/update_selected_aimbot', methods=['POST'])
def update_selected_aimbot_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    return jsonify({"success": True})

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

@app.route('/exit', methods=['POST'])
def exit_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    threading.Thread(target=lambda: (time.sleep(1), exit_application()), daemon=True).start()
    return jsonify({"success": True})

# ==================== MAIN ====================
if __name__ == '__main__':
    print("=" * 50)
    print("VOLT STREAMER")
    print("=" * 50)
    print(f"Server running on: http://localhost:{SERVER_PORT}")
    print(f"Target Process: {current_process_name}")
    print(f"Hold Delay: {hotkey_state['delay']}ms")
    print("=" * 50)
    print("Hold key works for Aimbot AI only")
    print("Press Ctrl+C to exit")
    print("=" * 50)
    
    threading.Thread(target=hold_hotkey_monitor, daemon=True).start()
    
    try:
        app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n[+] Shutting down...")
        AIMBOT_OFF()
        print("[+] Goodbye!")
