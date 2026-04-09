#!/usr/bin/env python
# GHOST-XS STREAMER - FINAL WITH CLEAN SCAN + POWER SLIDER + EMBED DLL SPACE
# SCAN ONLY - NO AUTO ACTIVATION

import os
import sys
import time
import socket
import threading
import ctypes
import requests
import subprocess
import hashlib
import json
import base64
import tempfile
import struct
from ctypes import wintypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import win32api
import win32con

# Hide console
if sys.platform == "win32":
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

# ==================== WINDOWS API ====================
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
user32 = ctypes.WinDLL('user32', use_last_error=True)

PROCESS_ALL_ACCESS = 0x1F0FFF
PROCESS_CREATE_THREAD = 0x0002
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x00001000
MEM_RESERVE = 0x00002000
PAGE_READWRITE = 0x04
PAGE_EXECUTE_READWRITE = 0x40

# ==================== GITHUB AUTH URL ====================
GITHUB_AUTH_URL = "https://raw.githubusercontent.com/Ghostxs90/Sid/main/Sid.txt"

# ==================== MEMORY FUNCTIONS ====================
try:
    from pymem import Pymem
    from pymem.memory import read_bytes, write_bytes
    from pymem.pattern import pattern_scan_all
    PYMEM_OK = True
except ImportError:
    PYMEM_OK = False
    print("[!] PyMem not installed - run: pip install pymem")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pymem"])
        from pymem import Pymem
        from pymem.memory import read_bytes, write_bytes
        from pymem.pattern import pattern_scan_all
        PYMEM_OK = True
    except:
        pass

# ==================== EMBEDDED DLL - PASTE YOUR BASE64 HERE ====================
EMBEDDED_DLL_BASE64 = """
PASTE_YOUR_BASE64_ENCODED_DLL_HERE
"""

# ==================== GLOBAL VARIABLES ====================
aimbot_addresses = []
aimbot_original_values = {}
aimbot_active = False
current_aim_mode = None
last_aim_time = 0

# DRAG MODE VARIABLES
drag_mode_active = False
drag_current_mode = None
drag_power = 50
drag_last_pos = (0, 0)
drag_threshold = 25

collider_addresses = []
collider_original_values = {}
collider_active = False

hotkey_state = {
    "hold_key": None,
    "selected_aimbot": "Head",
    "hold_active": False,
    "delay": 50
}

current_target_process = "HD-Player.exe"
authenticated_users = {}
player_count = 0

# ==================== GET COMPUTER SID ====================
def get_computer_sid():
    try:
        import win32security
        import win32api
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

# ==================== FETCH CREDENTIALS ====================
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

# ==================== PATTERN CONVERTER ====================
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

# ==================== EXTRACT AND INJECT EMBEDDED DLL ====================
def extract_and_inject_dll(process_name):
    """Extract embedded DLL and manually map inject"""
    try:
        if not EMBEDDED_DLL_BASE64 or EMBEDDED_DLL_BASE64.strip() == "PASTE_YOUR_BASE64_ENCODED_DLL_HERE":
            return "No embedded DLL found - please add your DLL base64"
        
        dll_bytes = base64.b64decode(EMBEDDED_DLL_BASE64.strip())
        
        pid = None
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and proc.info['name'].lower() == process_name.lower():
                pid = proc.info['pid']
                break
        
        if not pid:
            return f"Process {process_name} not found"
        
        handle = kernel32.OpenProcess(
            PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | 
            PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ,
            False, pid
        )
        
        if not handle:
            return "Failed to open process"
        
        dll_size = len(dll_bytes)
        allocated_mem = kernel32.VirtualAllocEx(
            handle, None, dll_size,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
        )
        
        if not allocated_mem:
            kernel32.CloseHandle(handle)
            return "Failed to allocate memory"
        
        bytes_written = ctypes.c_size_t()
        result = kernel32.WriteProcessMemory(
            handle, allocated_mem, dll_bytes, dll_size,
            ctypes.byref(bytes_written)
        )
        
        if not result or bytes_written.value != dll_size:
            kernel32.VirtualFreeEx(handle, allocated_mem, 0, MEM_RELEASE)
            kernel32.CloseHandle(handle)
            return "Failed to write DLL"
        
        try:
            dos_header = dll_bytes[:64]
            e_lfanew = struct.unpack('<I', dos_header[60:64])[0]
            entry_point_rva = struct.unpack('<I', dll_bytes[e_lfanew + 40:e_lfanew + 44])[0]
            entry_point = allocated_mem + entry_point_rva
        except:
            entry_point = allocated_mem
        
        thread_id = ctypes.c_ulong()
        thread = kernel32.CreateRemoteThread(
            handle, None, 0,
            ctypes.c_void_p(entry_point),
            allocated_mem, 0, ctypes.byref(thread_id)
        )
        
        if not thread:
            kernel32.VirtualFreeEx(handle, allocated_mem, 0, MEM_RELEASE)
            kernel32.CloseHandle(handle)
            return "Failed to create remote thread"
        
        kernel32.WaitForSingleObject(thread, 5000)
        kernel32.CloseHandle(thread)
        kernel32.CloseHandle(handle)
        
        return f"DLL manually mapped into {process_name} (PID: {pid}) - {dll_size} bytes"
        
    except Exception as e:
        return f"Manual map failed: {str(e)}"

# ==================== SCAN FUNCTION - CLEAN SCAN, NO ACTIVATION ====================
def HEADLOAD():
    global aimbot_addresses, collider_addresses, player_count
    
    aimbot_addresses = []
    aimbot_original_values = {}
    collider_addresses = []
    collider_original_values = {}
    player_count = 0
    
    if not PYMEM_OK:
        return "PyMem not installed"
    
    try:
        proc = Pymem(current_target_process)
    except Exception as e:
        return f"Game not found - Launch {current_target_process} first"

    try:
        aimbot_pattern = mkp("FF FF 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 FF FF FF FF FF FF FF FF 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 A5 43")
        aimbot_addresses = pattern_scan_all(proc.process_handle, aimbot_pattern, return_multiple=True)
        
        collider_pattern = mkp("FF FF FF FF 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 FF FF FF FF FF FF FF FF 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 A5 43")
        collider_addresses = pattern_scan_all(proc.process_handle, collider_pattern, return_multiple=True)
        
        valid_players = 0
        temp_valid_addresses = []
        
        for addr in aimbot_addresses:
            try:
                val = read_bytes(proc.process_handle, addr + 0xA6, 4)
                val2 = read_bytes(proc.process_handle, addr + 0xAA, 4)
                if any(v != 0 for v in val) or any(v != 0 for v in val2):
                    valid_players += 1
                    temp_valid_addresses.append(addr)
            except:
                pass
        
        aimbot_addresses = temp_valid_addresses
        player_count = valid_players
        
        proc.close_process()
        
        return f"SCANNING WITH ADV METHOD\nSCAN DONE\n{player_count} ENTITIES FOUND"
        
    except Exception as e:
        return f"Scan failed: {str(e)}"

# ==================== DRAG MODE FUNCTIONS ====================
def set_drag_power(power):
    global drag_power, drag_threshold
    drag_power = max(0, min(100, power))
    drag_threshold = int(drag_power / 2)
    return f"Drag power set to {power}% ({drag_threshold} pixels)"

def leftShoulderOn():
    global drag_mode_active, drag_current_mode, drag_last_pos
    global aimbot_active, current_aim_mode, collider_active
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    aimbot_active = False
    current_aim_mode = None
    collider_active = False
    
    drag_mode_active = True
    drag_current_mode = "LEFT"
    
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    drag_last_pos = (point.x, point.y)
    
    return "Left Shoulder mode enabled (drag to activate)"

def rightShoulderOn():
    global drag_mode_active, drag_current_mode, drag_last_pos
    global aimbot_active, current_aim_mode, collider_active
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    aimbot_active = False
    current_aim_mode = None
    collider_active = False
    
    drag_mode_active = True
    drag_current_mode = "RIGHT"
    
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    drag_last_pos = (point.x, point.y)
    
    return "Right Shoulder mode enabled (drag to activate)"

def ENABLE_NECK():
    global current_aim_mode, aimbot_active
    global drag_mode_active, drag_current_mode, collider_active
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    drag_mode_active = False
    drag_current_mode = None
    collider_active = False
    
    aimbot_active = True
    current_aim_mode = "NECK"
    
    return "NECK mode enabled"

def AimbotAion():
    global collider_active
    global aimbot_active, current_aim_mode, drag_mode_active, drag_current_mode
    
    if not collider_addresses:
        return "No collider - scan first"
    
    aimbot_active = False
    current_aim_mode = None
    drag_mode_active = False
    drag_current_mode = None
    
    collider_active = True
    
    return "Collider ON"

def AIMBOT_OFF():
    global aimbot_original_values, aimbot_active, current_aim_mode
    global drag_mode_active, drag_current_mode, collider_active, collider_original_values
    
    if aimbot_original_values and PYMEM_OK:
        try:
            proc = Pymem(current_target_process)
            for addr, orig in aimbot_original_values.items():
                try:
                    write_bytes(proc.process_handle, addr + 0xA6, orig, len(orig))
                except:
                    pass
            proc.close_process()
            aimbot_original_values.clear()
        except:
            pass
    
    if collider_original_values and PYMEM_OK:
        try:
            proc = Pymem(current_target_process)
            for base, orig in collider_original_values.items():
                try:
                    target_addr = base - 0x368 
                    write_bytes(proc.process_handle, target_addr, orig, len(orig))
                except:
                    pass
            proc.close_process()
            collider_original_values.clear()
        except:
            pass
    
    aimbot_active = False
    current_aim_mode = None
    drag_mode_active = False
    drag_current_mode = None
    collider_active = False
    
    return "All disabled"

def leftShoulderOff():
    return AIMBOT_OFF()

def rightShoulderOff():
    return AIMBOT_OFF()

def AimbotAioff():
    return AIMBOT_OFF()

# ==================== DRAG DETECTION LOOP ====================
def drag_detection_loop():
    global drag_last_pos, drag_threshold, aimbot_active, current_aim_mode
    global drag_mode_active, drag_current_mode, aimbot_original_values
    
    while True:
        if drag_mode_active and drag_current_mode and aimbot_addresses and PYMEM_OK:
            try:
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                point = POINT()
                user32.GetCursorPos(ctypes.byref(point))
                
                drag_x = abs(point.x - drag_last_pos[0])
                drag_y = abs(point.y - drag_last_pos[1])
                drag_distance = drag_x + drag_y
                
                drag_last_pos = (point.x, point.y)
                
                if drag_distance >= drag_threshold:
                    if drag_current_mode == "LEFT":
                        current_aim_mode = "LEFT"
                    elif drag_current_mode == "RIGHT":
                        current_aim_mode = "RIGHT"
                    
                    aimbot_active = True
                    
                    try:
                        proc = Pymem(current_target_process)
                        for addr in aimbot_addresses:
                            try:
                                if addr not in aimbot_original_values:
                                    aimbot_original_values[addr] = read_bytes(proc.process_handle, addr + 0xA6, 4)
                                
                                if current_aim_mode == "LEFT":
                                    target = read_bytes(proc.process_handle, addr + 0xD6, 4)
                                elif current_aim_mode == "RIGHT":
                                    target = read_bytes(proc.process_handle, addr + 0xDA, 4)
                                else:
                                    continue
                                    
                                write_bytes(proc.process_handle, addr + 0xA6, target, len(target))
                            except:
                                pass
                        proc.close_process()
                    except:
                        pass
                else:
                    aimbot_active = False
                    current_aim_mode = None
                    
            except Exception as e:
                pass
        
        time.sleep(0.01)

# ==================== AIMBOT LOOP ====================
def aimbot_loop():
    global aimbot_original_values
    last_write = 0
    
    while True:
        if aimbot_active and aimbot_addresses and PYMEM_OK and current_aim_mode:
            try:
                current = time.time() * 1000
                if current - last_write >= 10:
                    proc = Pymem(current_target_process)
                    for addr in aimbot_addresses:
                        try:
                            if addr not in aimbot_original_values:
                                aimbot_original_values[addr] = read_bytes(proc.process_handle, addr + 0xA6, 4)
                            
                            if current_aim_mode == "NECK":
                                target = read_bytes(proc.process_handle, addr + 0xAA, 4)
                            elif current_aim_mode == "LEFT":
                                target = read_bytes(proc.process_handle, addr + 0xD6, 4)
                            elif current_aim_mode == "RIGHT":
                                target = read_bytes(proc.process_handle, addr + 0xDA, 4)
                            else:
                                continue
                                
                            write_bytes(proc.process_handle, addr + 0xA6, target, len(target))
                        except:
                            pass
                    proc.close_process()
                    last_write = current
            except:
                pass
        time.sleep(0.005)

# ==================== COLLIDER LOOP ====================
def collider_loop():
    global collider_original_values
    
    while True:
        if collider_active and collider_addresses and PYMEM_OK:
            try:
                proc = Pymem(current_target_process)
                for base in collider_addresses:
                    try:
                        head_addr = base + 0xF0
                        target_addr = base - 0x368 
                        head_val = read_bytes(proc.process_handle, head_addr, 4)
                        
                        if all(b == 0 for b in head_val):
                            continue
                            
                        if base not in collider_original_values:
                            collider_original_values[base] = read_bytes(proc.process_handle, target_addr, 4)
                            
                        write_bytes(proc.process_handle, target_addr, head_val, len(head_val))
                    except:
                        pass
                proc.close_process()
            except:
                pass
        time.sleep(0.01)

# ==================== HOTKEY MONITOR WITH DELAY ====================
def hold_hotkey_monitor():
    global hotkey_state, aimbot_active, current_aim_mode, collider_active, last_aim_time
    global drag_mode_active, drag_current_mode
    
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
        'Tab': 0x09, 'CapsLock': 0x14, 'Escape': 0x1B, 'Backspace': 0x08,
        'Insert': 0x2D, 'Delete': 0x2E, 'Home': 0x24, 'End': 0x23,
        'PageUp': 0x21, 'PageDown': 0x22,
        'ArrowUp': 0x26, 'ArrowDown': 0x28, 'ArrowLeft': 0x25, 'ArrowRight': 0x27,
        'MouseLeft': 0x01, 'MouseRight': 0x02, 'MouseMiddle': 0x04,
        'MouseButton4': 0x05, 'MouseButton5': 0x06
    }
    
    while True:
        try:
            current_time = time.time() * 1000
            
            if hotkey_state["hold_key"] and hotkey_state["hold_key"] in vk_map:
                key_state = win32api.GetAsyncKeyState(vk_map[hotkey_state["hold_key"]])
                key_held = (key_state & 0x8000) != 0
                
                if key_held and not hotkey_state["hold_active"]:
                    hotkey_state["hold_active"] = True
                    last_aim_time = current_time
                    
                elif key_held and hotkey_state["hold_active"]:
                    if current_time - last_aim_time >= hotkey_state["delay"]:
                        if hotkey_state["selected_aimbot"] == "AimbotAi":
                            if collider_addresses:
                                aimbot_active = False
                                drag_mode_active = False
                                collider_active = True
                        elif hotkey_state["selected_aimbot"] == "LeftShoulder":
                            pass
                        elif hotkey_state["selected_aimbot"] == "RightShoulder":
                            pass
                        else:
                            if aimbot_addresses:
                                drag_mode_active = False
                                collider_active = False
                                current_aim_mode = "NECK"
                                aimbot_active = True
                            
                elif not key_held and hotkey_state["hold_active"]:
                    hotkey_state["hold_active"] = False
                    if hotkey_state["selected_aimbot"] == "AimbotAi":
                        collider_active = False
                    elif hotkey_state["selected_aimbot"] in ["LeftShoulder", "RightShoulder"]:
                        pass
                    else:
                        aimbot_active = False
                        current_aim_mode = None
        except:
            pass
        time.sleep(0.001)

# ==================== GET PROCESS LIST ====================
def get_running_processes():
    processes = []
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                processes.append({'pid': proc.info['pid'], 'name': proc.info['name']})
            except:
                pass
        processes.sort(key=lambda x: x['name'].lower())
    except:
        pass
    return processes

def is_process_running(process_name):
    try:
        import psutil
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and proc.info['name'].lower() == process_name.lower():
                return True
    except:
        pass
    return False

# ==================== WEB SERVER ====================
class GhostWebServer(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        
        if path == '/':
            self.send_login_page()
        elif path == '/dashboard':
            self.send_dashboard_page()
        elif path == '/get_hd_player_status':
            self.send_process_status()
        elif path == '/get_processes':
            self.send_process_list()
        elif path == '/get_hotkey_aimbot':
            self.send_hotkey_aimbot()
        elif path == '/get_hold_hotkey':
            self.send_hold_hotkey()
        elif path == '/get_scope_hotkey':
            self.send_scope_hotkey()
        elif path == '/get_drag_power':
            self.send_drag_power()
        else:
            self.send_error(404)
    
    def do_POST(self):
        path = urlparse(self.path).path
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data) if post_data else {}
        except:
            data = {}
        
        if path == '/login':
            self.handle_login(data)
        elif path == '/execute':
            self.handle_execute(data)
        elif path == '/save_hotkey':
            self.save_hotkey(data)
        elif path == '/save_hold_hotkey':
            self.save_hold_hotkey(data)
        elif path == '/save_hold_delay':
            self.save_hold_delay(data)
        elif path == '/save_scope_hotkey':
            self.save_scope_hotkey(data)
        elif path == '/set_drag_power':
            self.set_drag_power(data)
        elif path == '/update_hotkey_aimbot':
            self.update_hotkey_aimbot(data)
        elif path == '/update_selected_aimbot':
            self.update_selected_aimbot(data)
        elif path == '/set_target_process':
            self.set_target_process(data)
        elif path == '/set_ignore_knocked':
            self.set_ignore_knocked(data)
        elif path == '/logout':
            self.handle_logout()
        elif path == '/exit':
            self.handle_exit()
        else:
            self.send_json({'success': False})
    
    def send_login_page(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = """<!DOCTYPE html>
<html>
<head>
    <title>GHOST-XS Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:'Segoe UI',sans-serif; }
        body { background:#0a0a0a; min-height:100vh; display:flex; justify-content:center; align-items:center; position:relative; overflow:hidden; }
        canvas { position:fixed; top:0; left:0; width:100%; height:100%; z-index:1; }
        .login-container { position:relative; z-index:2; width:90%; max-width:380px; }
        .login-box { background:#141414; border:1px solid #ff3333; border-radius:8px; padding:30px 25px; box-shadow:0 0 20px rgba(255,51,51,0.2); }
        h2 { color:#ff5555; text-align:center; font-size:28px; margin-bottom:5px; font-weight:400; }
        .subtitle { color:#ff8888; text-align:center; margin-bottom:25px; font-size:13px; border-bottom:1px solid #ff3333; padding-bottom:15px; }
        input { width:100%; padding:12px 15px; background:#1e1e1e; border:1px solid #333; border-radius:4px; color:#ffffff; font-size:14px; margin-bottom:20px; outline:none; transition:all 0.3s; }
        input:focus { border-color:#ff5555; }
        input::placeholder { color:#666666; }
        button { width:100%; padding:12px; background:#1e1e1e; border:1px solid #ff3333; border-radius:4px; color:#ff5555; font-size:15px; cursor:pointer; transition:all 0.3s; }
        button:hover { background:#2a2a2a; border-color:#ff5555; color:#ff7777; }
        .error { color:#ef5350; text-align:center; margin-top:15px; display:none; }
        
        .loading-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 1000;
            display: none;
            justify-content: center;
            align-items: center;
            backdrop-filter: blur(5px);
        }
        .loader-container {
            text-align: center;
        }
        .circular-loader {
            width: 200px;
            height: 200px;
            position: relative;
        }
        .circle-bg {
            stroke: #333;
            stroke-width: 8;
            fill: none;
        }
        .circle-progress {
            stroke: #ffffff;
            stroke-width: 8;
            fill: none;
            stroke-dasharray: 565.48;
            stroke-dashoffset: 565.48;
            transition: stroke-dashoffset 0.05s linear;
            stroke-linecap: round;
        }
        .percentage-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 48px;
            font-weight: bold;
            color: #ffffff;
            font-family: monospace;
        }
        .status-text {
            margin-top: 20px;
            font-size: 18px;
            font-weight: bold;
        }
        .circle-progress.success {
            stroke: #00ff00;
        }
        .circle-progress.failed {
            stroke: #ff0000;
        }
        .status-text.success {
            color: #00ff00;
        }
        .status-text.failed {
            color: #ff0000;
        }
    </style>
</head>
<body>
    <canvas id="particleCanvas"></canvas>
    <div class="login-container">
        <div class="login-box">
            <h2>GHOST-XS</h2>
            <div class="subtitle">Streamer Edition</div>
            <input type="text" id="username" placeholder="Username">
            <input type="password" id="password" placeholder="Password">
            <button onclick="login()">Login</button>
            <div id="error" class="error"></div>
        </div>
    </div>
    
    <div class="loading-overlay" id="loadingOverlay">
        <div class="loader-container">
            <div class="circular-loader">
                <svg width="200" height="200" viewBox="0 0 200 200">
                    <circle cx="100" cy="100" r="90" class="circle-bg" stroke="#333" stroke-width="8" fill="none"/>
                    <circle cx="100" cy="100" r="90" class="circle-progress" stroke="#ffffff" stroke-width="8" fill="none" stroke-dasharray="565.48" stroke-dashoffset="565.48"/>
                </svg>
                <div class="percentage-text" id="percentageText">0%</div>
            </div>
            <div class="status-text" id="statusTextLoading"></div>
        </div>
    </div>
    
    <script>
        const canvas = document.getElementById('particleCanvas');
        const ctx = canvas.getContext('2d');
        
        let width = window.innerWidth;
        let height = window.innerHeight;
        canvas.width = width;
        canvas.height = height;
        
        let particles = [];
        
        class Particle {
            constructor() {
                this.x = Math.random() * width;
                this.y = Math.random() * height;
                this.vx = (Math.random() - 0.5) * 0.3;
                this.vy = (Math.random() - 0.5) * 0.3;
                this.radius = Math.random() * 1.5 + 0.5;
                this.color = `rgba(255, ${Math.random() * 100 + 50}, ${Math.random() * 50}, 0.4)`;
            }
            
            update() {
                this.x += this.vx;
                this.y += this.vy;
                
                if (this.x < 0) this.x = width;
                if (this.x > width) this.x = 0;
                if (this.y < 0) this.y = height;
                if (this.y > height) this.y = 0;
            }
            
            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
                ctx.fillStyle = this.color;
                ctx.fill();
            }
        }
        
        function initParticles() {
            particles = [];
            for (let i = 0; i < 100; i++) {
                particles.push(new Particle());
            }
        }
        
        function drawConnections() {
            for (let i = 0; i < particles.length; i++) {
                for (let j = i + 1; j < particles.length; j++) {
                    const dx = particles[i].x - particles[j].x;
                    const dy = particles[i].y - particles[j].y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    
                    if (distance < 100) {
                        ctx.beginPath();
                        ctx.moveTo(particles[i].x, particles[i].y);
                        ctx.lineTo(particles[j].x, particles[j].y);
                        const opacity = (1 - distance / 100) * 0.2;
                        ctx.strokeStyle = `rgba(255, 80, 80, ${opacity})`;
                        ctx.stroke();
                    }
                }
            }
        }
        
        function animate() {
            ctx.clearRect(0, 0, width, height);
            
            for (let p of particles) {
                p.update();
                p.draw();
            }
            
            drawConnections();
            requestAnimationFrame(animate);
        }
        
        window.addEventListener('resize', () => {
            width = window.innerWidth;
            height = window.innerHeight;
            canvas.width = width;
            canvas.height = height;
            initParticles();
        });
        
        initParticles();
        animate();
        
        let loadingAnimation = null;
        
        function startLoadingAnimation() {
            const overlay = document.getElementById('loadingOverlay');
            const circle = document.querySelector('.circle-progress');
            const percentageText = document.getElementById('percentageText');
            const statusText = document.getElementById('statusTextLoading');
            
            overlay.style.display = 'flex';
            circle.classList.remove('success', 'failed');
            circle.setAttribute('stroke', '#ffffff');
            statusText.classList.remove('success', 'failed');
            statusText.textContent = '';
            percentageText.style.color = '#ffffff';
            
            let progress = 0;
            const duration = 3000;
            const startTime = Date.now();
            
            if (loadingAnimation) clearInterval(loadingAnimation);
            
            loadingAnimation = setInterval(() => {
                const elapsed = Date.now() - startTime;
                progress = Math.min(100, (elapsed / duration) * 100);
                const circumference = 565.48;
                const offset = circumference - (progress / 100) * circumference;
                circle.style.strokeDashoffset = offset;
                percentageText.textContent = Math.floor(progress) + '%';
                
                if (progress >= 100) {
                    clearInterval(loadingAnimation);
                }
            }, 16);
            
            return {
                success: function() {
                    if (loadingAnimation) clearInterval(loadingAnimation);
                    const circle = document.querySelector('.circle-progress');
                    const statusText = document.getElementById('statusTextLoading');
                    const percentageText = document.getElementById('percentageText');
                    
                    circle.classList.add('success');
                    statusText.classList.add('success');
                    statusText.textContent = 'ACCESS GRANTED';
                    percentageText.style.color = '#00ff00';
                    
                    setTimeout(() => {
                        overlay.style.display = 'none';
                    }, 1500);
                },
                fail: function() {
                    if (loadingAnimation) clearInterval(loadingAnimation);
                    const circle = document.querySelector('.circle-progress');
                    const statusText = document.getElementById('statusTextLoading');
                    const percentageText = document.getElementById('percentageText');
                    
                    circle.classList.add('failed');
                    statusText.classList.add('failed');
                    statusText.textContent = 'ACCESS FAILED';
                    percentageText.style.color = '#ff0000';
                    
                    setTimeout(() => {
                        overlay.style.display = 'none';
                    }, 1500);
                }
            };
        }
        
        function login() {
            const u = document.getElementById('username').value;
            const p = document.getElementById('password').value;
            if (!u || !p) {
                document.getElementById('error').style.display = 'block';
                document.getElementById('error').textContent = 'Enter username and password';
                return;
            }
            
            document.getElementById('error').style.display = 'none';
            const loader = startLoadingAnimation();
            
            fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: u, password: p })
            })
            .then(r => r.json())
            .then(d => {
                setTimeout(() => {
                    if (d.success) {
                        loader.success();
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 1600);
                    } else {
                        loader.fail();
                        setTimeout(() => {
                            document.getElementById('error').style.display = 'block';
                            document.getElementById('error').textContent = 'Invalid credentials';
                        }, 1600);
                    }
                }, 3000);
            })
            .catch(() => {
                setTimeout(() => {
                    loader.fail();
                    setTimeout(() => {
                        document.getElementById('error').style.display = 'block';
                        document.getElementById('error').textContent = 'Connection error';
                    }, 1600);
                }, 3000);
            });
        }
        
        document.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') login();
        });
    </script>
</body>
</html>"""
        self.wfile.write(html.encode())
    
    def send_dashboard_page(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GHOST-XS Streamer</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: #0a0a0a;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #e0e0e0;
            padding: 20px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
        }

        .card {
            background: #141414;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            margin-bottom: 16px;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .card-header {
            padding: 16px 20px;
            border-bottom: 1px solid #2a2a2a;
            background: #0f0f0f;
        }

        .card-header h2 {
            font-size: 16px;
            font-weight: 600;
            color: #ffffff;
            letter-spacing: 0.3px;
        }

        .card-body {
            padding: 20px;
        }

        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .status-info {
            flex: 1;
        }

        .status-label {
            font-size: 13px;
            color: #888;
            margin-bottom: 4px;
        }

        .status-value {
            font-size: 15px;
            font-weight: 500;
            color: #fff;
        }

        .current-process {
            font-size: 12px;
            color: #666;
            margin-top: 4px;
        }

        .badge {
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-align: center;
            min-width: 70px;
        }

        .badge.online {
            background: #1e3a2e;
            color: #4caf50;
            border: 1px solid #2e7d32;
        }

        .badge.offline {
            background: #3a1e1e;
            color: #ef5350;
            border: 1px solid #c62828;
        }

        .tabs {
            display: flex;
            gap: 4px;
            background: #0f0f0f;
            padding: 4px;
            border-bottom: 1px solid #2a2a2a;
        }

        .tab {
            flex: 1;
            text-align: center;
            padding: 12px 16px;
            background: transparent;
            border: none;
            color: #888;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            border-radius: 8px;
            transition: all 0.3s ease;
        }

        .tab:hover {
            background: #1e1e1e;
            color: #ccc;
        }

        .tab.active {
            background: #1e1e1e;
            color: #fff;
        }

        .content-panel {
            display: none;
            animation: fadeIn 0.3s ease;
        }

        .content-panel.active {
            display: block;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 12px;
        }

        .row:last-child {
            margin-bottom: 0;
        }

        .row-label {
            flex: 1;
            min-width: 160px;
        }

        .row-label .title {
            font-size: 14px;
            font-weight: 500;
            color: #e0e0e0;
            margin-bottom: 4px;
        }

        .row-label .note {
            font-size: 11px;
            color: #666;
        }

        .row-controls {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }

        .btn {
            padding: 8px 16px;
            background: #1e1e1e;
            border: 1px solid #333;
            border-radius: 6px;
            color: #ccc;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
        }

        .btn:hover {
            background: #2a2a2a;
            border-color: #444;
        }

        .btn.active {
            background: #4caf50;
            border-color: #4caf50;
            color: #fff;
        }

        .btn-primary {
            background: #2c2c2c;
            border-color: #4a4a4a;
            color: #fff;
        }

        .btn-primary:hover {
            background: #3a3a3a;
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

        select {
            padding: 8px 12px;
            background: #1e1e1e;
            border: 1px solid #333;
            border-radius: 6px;
            color: #e0e0e0;
            font-size: 13px;
            cursor: pointer;
            min-width: 160px;
        }

        select:hover {
            border-color: #444;
        }

        .slider-container {
            min-width: 200px;
        }

        .slider-label {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: #888;
            margin-bottom: 6px;
        }

        .slider-value {
            color: #ccc;
        }

        input[type="range"] {
            width: 100%;
            height: 4px;
            -webkit-appearance: none;
            background: #2a2a2a;
            border-radius: 2px;
            outline: none;
        }

        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: #888;
            cursor: pointer;
            border: none;
        }

        input[type="range"]::-webkit-slider-thumb:hover {
            background: #aaa;
        }

        .console {
            background: #0a0a0a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 12px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #8bc34a;
            height: 120px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        #notifications-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .notification {
            background: #1e1e1e;
            border-left: 3px solid #4caf50;
            padding: 12px 18px;
            border-radius: 8px;
            color: #e0e0e0;
            font-size: 13px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateX(100%);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }

        .alt-process-section {
            border-color: #3a2a2a;
            background: #121212;
        }

        .alt-process-section .card-header {
            background: #1a1212;
            border-bottom-color: #3a2a2a;
        }

        .alt-process-section h2 {
            color: #ff8a8a;
        }

        .hidden {
            display: none;
        }

        hr {
            border: none;
            border-top: 1px solid #2a2a2a;
            margin: 20px 0;
        }

        .section-title {
            font-size: 14px;
            font-weight: 600;
            color: #aaa;
            margin-bottom: 16px;
            letter-spacing: 0.5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="card-header">
                <h2>GHOST-XS STREAMER</h2>
            </div>
            <div class="card-body">
                <div class="status-bar">
                    <div class="status-info">
                        <div class="status-label">Status</div>
                        <div class="status-value" id="statusText">Checking...</div>
                        <div class="current-process" id="currentProcessText">Process: HD-Player.exe</div>
                    </div>
                    <div class="badge" id="statusBadge">Checking...</div>
                </div>
            </div>
        </div>

        <div class="card alt-process-section hidden" id="alternative-process-section">
            <div class="card-header">
                <h2>Alternative Process Selector</h2>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="row-label">
                        <div class="title">Select Process</div>
                        <div class="note">Current target process is offline</div>
                    </div>
                    <div class="row-controls">
                        <select id="process-selector">
                            <option value="">Select a process...</option>
                        </select>
                        <div class="btn" id="refresh-processes" onclick="updateProcessList()">Refresh</div>
                        <div class="btn btn-primary" onclick="setTargetProcess()">Set Process</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="tabs">
                <button class="tab active" data-tab="headshot">Headshot</button>
                <button class="tab" data-tab="sniper">Sniper</button>
                <button class="tab" data-tab="settings">Settings</button>
            </div>

            <div class="content-panel active" id="headshot">
                <div class="card-body">
                    <div class="row">
                        <div class="row-label">
                            <div class="title">Scan Enemies</div>
                            <div class="note">Scans enemies in the match (CLEAN SCAN - NO AUTO ACTIVATION)</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn btn-primary" onclick="sendCommand('aimbotscan')">Scan Players</div>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Aim Position</div>
                            <div class="note">Hotkey - Help</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn" id="neckBtn" onclick="sendCommand('aimbotenable')">Neck</div>
                            <div class="btn active" id="defaultBtn" onclick="sendCommand('aimbotdisable')">Default</div>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Other Aim Position</div>
                            <div class="note">Hotkey - Help</div>
                        </div>
                        <div class="row-controls">
                            <select id="other-aimpos" onchange="updateSelectedAimbot()">
                                <option value="RightShoulder">Right Shoulder</option>
                                <option value="LeftShoulder">Left Shoulder</option>
                                <option value="AimbotAi">Aimbot Ai</option>
                            </select>
                        </div>
                    </div>

                    <div class="row hidden" id="power-slider-container">
                        <div class="row-label">
                            <div class="title">Drag Power</div>
                            <div class="note">0% = 0 pixels, 100% = 50 pixels drag needed</div>
                        </div>
                        <div class="slider-container">
                            <div class="slider-label">
                                <span>Power:</span>
                                <span class="slider-value" id="powerValue">50%</span>
                            </div>
                            <input type="range" min="0" max="100" value="50" id="powerSlider">
                        </div>
                    </div>

                    <div class="row leftShoulder hidden">
                        <div class="row-label">
                            <div class="title">Headshot Legit</div>
                            <div class="note">Left Shoulder (Drag Mode)</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn" id="leftEnableBtn" onclick="sendCommand('leftShoulderOn')">Enable</div>
                            <div class="btn active" id="leftDisableBtn" onclick="sendCommand('leftShoulderOff')">Disable</div>
                        </div>
                    </div>

                    <div class="row rightShoulder">
                        <div class="row-label">
                            <div class="title">Headshot Legit</div>
                            <div class="note">Right Shoulder (Drag Mode)</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn" id="rightEnableBtn" onclick="sendCommand('rightShoulderOn')">Enable</div>
                            <div class="btn active" id="rightDisableBtn" onclick="sendCommand('rightShoulderOff')">Disable</div>
                        </div>
                    </div>

                    <div class="row Aiaimbot hidden">
                        <div class="row-label">
                            <div class="title">Headshot Legit</div>
                            <div class="note">Aimbot Ai (Collider)</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn" id="aiEnableBtn" onclick="sendCommand('AimbotAion')">Enable</div>
                            <div class="btn active" id="aiDisableBtn" onclick="sendCommand('AimbotAioff')">Disable</div>
                        </div>
                    </div>

                    <hr>

                    <div class="section-title">Xghost Special Aimbot</div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Aimbot X (Hotkey Target)</div>
                            <div class="note">Select which aimbot hotkeys will trigger</div>
                        </div>
                        <div class="row-controls">
                            <select id="hotkey-aimbot-selector" onchange="updateHotkeyAimbot()">
                                <option value="Head" selected>Head (Default)</option>
                                <option value="RightShoulder">Right Shoulder</option>
                                <option value="LeftShoulder">Left Shoulder</option>
                                <option value="AimbotAi">Aimbot Ai</option>
                            </select>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Ignore Knocked Enemies</div>
                            <div class="note">When enabled, aimbot ignores knocked players</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn active" id="ignoreYesBtn" onclick="setIgnoreKnocked(true)">Yes</div>
                            <div class="btn" id="ignoreNoBtn" onclick="setIgnoreKnocked(false)">No</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="content-panel" id="sniper">
                <div class="card-body">
                    <div class="row">
                        <div class="row-label">
                            <div class="title">Sniper Load</div>
                            <div class="note">Loads Sniper Scope & Switch</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn btn-primary" onclick="sendCommand('loadsniper')">Scan Sniper</div>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Sniper Scope</div>
                            <div class="note">Turn on Sniper Scope</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn" onclick="sendCommand('sniperscopeenable')">Enable</div>
                            <div class="btn active" onclick="sendCommand('sniperscopedisable')">Disable</div>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Sniper Switch</div>
                            <div class="note">Turn on Sniper fast switch</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn" onclick="sendCommand('sniperswitchenable')">Enable</div>
                            <div class="btn active" onclick="sendCommand('sniperswitchdisable')">Disable</div>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Scope Toggle Hotkey</div>
                            <div class="note">Hold key to toggle scope (like C++ version)</div>
                        </div>
                        <div class="row-controls">
                            <select id="scope-hotkey-selector">
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
                                <optgroup label="Number Keys">
                                    <option value="0">0</option><option value="1">1</option><option value="2">2</option>
                                    <option value="3">3</option><option value="4">4</option><option value="5">5</option>
                                    <option value="6">6</option><option value="7">7</option><option value="8">8</option>
                                    <option value="9">9</option>
                                </optgroup>
                                <optgroup label="Function Keys">
                                    <option value="F1">F1</option><option value="F2">F2</option><option value="F3">F3</option>
                                    <option value="F4">F4</option><option value="F5">F5</option><option value="F6">F6</option>
                                    <option value="F7">F7</option><option value="F8">F8</option><option value="F9">F9</option>
                                    <option value="F10">F10</option><option value="F11">F11</option><option value="F12">F12</option>
                                </optgroup>
                                <optgroup label="Special Keys">
                                    <option value="Space">Space</option><option value="Enter">Enter</option>
                                    <option value="Shift">Shift</option><option value="Control">Control</option>
                                    <option value="Alt">Alt</option><option value="Tab">Tab</option>
                                    <option value="CapsLock">Caps Lock</option><option value="Escape">Escape</option>
                                    <option value="Backspace">Backspace</option>
                                </optgroup>
                                <optgroup label="Mouse Buttons">
                                    <option value="MouseLeft">Mouse Left</option><option value="MouseRight">Mouse Right</option>
                                    <option value="MouseMiddle">Mouse Middle</option><option value="MouseButton4">Mouse Button 4</option>
                                    <option value="MouseButton5">Mouse Button 5</option>
                                </optgroup>
                            </select>
                        </div>
                    </div>
                </div>
            </div>

            <div class="content-panel" id="settings">
                <div class="card-body">
                    <div class="row">
                        <div class="row-label">
                            <div class="title">Aimbot Legit Toggle</div>
                            <div class="note">Toggle aimbot legit with a hotkey</div>
                        </div>
                        <div class="row-controls">
                            <select id="hotkey-selector">
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
                                <optgroup label="Number Keys">
                                    <option value="0">0</option><option value="1">1</option><option value="2">2</option>
                                    <option value="3">3</option><option value="4">4</option><option value="5">5</option>
                                    <option value="6">6</option><option value="7">7</option><option value="8">8</option>
                                    <option value="9">9</option>
                                </optgroup>
                                <optgroup label="Function Keys">
                                    <option value="F1">F1</option><option value="F2">F2</option><option value="F3">F3</option>
                                    <option value="F4">F4</option><option value="F5">F5</option><option value="F6">F6</option>
                                    <option value="F7">F7</option><option value="F8">F8</option><option value="F9">F9</option>
                                    <option value="F10">F10</option><option value="F11">F11</option><option value="F12">F12</option>
                                </optgroup>
                                <optgroup label="Special Keys">
                                    <option value="Space">Space</option><option value="Enter">Enter</option>
                                    <option value="Shift">Shift</option><option value="Control">Control</option>
                                    <option value="Alt">Alt</option><option value="Tab">Tab</option>
                                    <option value="CapsLock">Caps Lock</option><option value="Escape">Escape</option>
                                    <option value="Backspace">Backspace</option>
                                </optgroup>
                                <optgroup label="Mouse Buttons">
                                    <option value="MouseLeft">Mouse Left</option><option value="MouseRight">Mouse Right</option>
                                    <option value="MouseMiddle">Mouse Middle</option><option value="MouseButton4">Mouse Button 4</option>
                                    <option value="MouseButton5">Mouse Button 5</option>
                                </optgroup>
                            </select>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Headshot Toggle (Hold)</div>
                            <div class="note">Hold key for Aimbot Legit</div>
                        </div>
                        <div class="row-controls">
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
                                <optgroup label="Number Keys">
                                    <option value="0">0</option><option value="1">1</option><option value="2">2</option>
                                    <option value="3">3</option><option value="4">4</option><option value="5">5</option>
                                    <option value="6">6</option><option value="7">7</option><option value="8">8</option>
                                    <option value="9">9</option>
                                </optgroup>
                                <optgroup label="Function Keys">
                                    <option value="F1">F1</option><option value="F2">F2</option><option value="F3">F3</option>
                                    <option value="F4">F4</option><option value="F5">F5</option><option value="F6">F6</option>
                                    <option value="F7">F7</option><option value="F8">F8</option><option value="F9">F9</option>
                                    <option value="F10">F10</option><option value="F11">F11</option><option value="F12">F12</option>
                                </optgroup>
                                <optgroup label="Special Keys">
                                    <option value="Space">Space</option><option value="Enter">Enter</option>
                                    <option value="Shift">Shift</option><option value="Control">Control</option>
                                    <option value="Alt">Alt</option><option value="Tab">Tab</option>
                                    <option value="CapsLock">Caps Lock</option><option value="Escape">Escape</option>
                                    <option value="Backspace">Backspace</option>
                                </optgroup>
                                <optgroup label="Mouse Buttons">
                                    <option value="MouseLeft">Mouse Left</option><option value="MouseRight">Mouse Right</option>
                                    <option value="MouseMiddle">Mouse Middle</option><option value="MouseButton4">Mouse Button 4</option>
                                    <option value="MouseButton5">Mouse Button 5</option>
                                </optgroup>
                            </select>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Hold Key Delay</div>
                            <div class="note">Delay before aimbot activates when holding key</div>
                        </div>
                        <div class="slider-container">
                            <div class="slider-label">
                                <span>Delay:</span>
                                <span class="slider-value" id="delayValue">50ms</span>
                            </div>
                            <input type="range" min="0" max="300" value="50" id="delaySlider">
                        </div>
                    </div>

                    <hr>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Log Out</div>
                            <div class="note">Logs you out of the website.</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn" onclick="logout()">Log Out</div>
                        </div>
                    </div>

                    <div class="row">
                        <div class="row-label">
                            <div class="title">Exit Application</div>
                            <div class="note">Closes the GHOST-XS Streamer application</div>
                        </div>
                        <div class="row-controls">
                            <div class="btn btn-danger" onclick="exitApplication()">Exit</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2>Console</h2>
            </div>
            <div class="card-body">
                <div class="console" id="console"></div>
            </div>
        </div>
    </div>

    <div id="notifications-container"></div>

    <script>
        const consoleEl = document.getElementById('console');
        const notificationsContainer = document.getElementById('notifications-container');
        const hotkeySelector = document.getElementById('hotkey-selector');
        const holdHotkeySelector = document.getElementById('hold-hotkey-selector');
        const delaySlider = document.getElementById('delaySlider');
        const delayValue = document.getElementById('delayValue');
        const powerSlider = document.getElementById('powerSlider');
        const powerValue = document.getElementById('powerValue');

        function log(message) {
            const now = new Date();
            const time = now.toLocaleTimeString();
            consoleEl.textContent += `[${time}] ${message}\\n`;
            consoleEl.scrollTop = consoleEl.scrollHeight;
        }

        function showNotification(message) {
            const notif = document.createElement('div');
            notif.className = 'notification';
            notif.textContent = message;
            notificationsContainer.appendChild(notif);
            setTimeout(() => {
                if (notif.parentNode) notif.remove();
            }, 3000);
        }

        function updateButtonState(buttonId, isActive) {
            const btn = document.getElementById(buttonId);
            if (btn) {
                if (isActive) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        }

        function sendCommand(command) {
            if (command === 'aimbotscan') {
                log('SCANNING WITH ADV METHOD');
            }
            
            if (command === 'aimbotenable') {
                updateButtonState('neckBtn', true);
                updateButtonState('defaultBtn', false);
            } else if (command === 'aimbotdisable') {
                updateButtonState('neckBtn', false);
                updateButtonState('defaultBtn', true);
            } else if (command === 'leftShoulderOn') {
                updateButtonState('leftEnableBtn', true);
                updateButtonState('leftDisableBtn', false);
            } else if (command === 'leftShoulderOff') {
                updateButtonState('leftEnableBtn', false);
                updateButtonState('leftDisableBtn', true);
            } else if (command === 'rightShoulderOn') {
                updateButtonState('rightEnableBtn', true);
                updateButtonState('rightDisableBtn', false);
            } else if (command === 'rightShoulderOff') {
                updateButtonState('rightEnableBtn', false);
                updateButtonState('rightDisableBtn', true);
            } else if (command === 'AimbotAion') {
                updateButtonState('aiEnableBtn', true);
                updateButtonState('aiDisableBtn', false);
            } else if (command === 'AimbotAioff') {
                updateButtonState('aiEnableBtn', false);
                updateButtonState('aiDisableBtn', true);
            }
            
            fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command }),
            })
            .then(response => response.json())
            .then(data => {
                if (data.message) {
                    if (command === 'aimbotscan') {
                        const lines = data.message.split('\\n');
                        for (let i = 1; i < lines.length; i++) {
                            if (lines[i].trim()) log(lines[i]);
                        }
                    } else {
                        log(data.message);
                    }
                }
            })
            .catch(err => log(`Error: ${err.message}`));
        }

        function logout() {
            fetch('/logout', { method: 'POST' }).then(() => {
                showNotification('Logged out');
                setTimeout(() => window.location.href = '/', 500);
            });
        }

        function exitApplication() {
            if (confirm('Are you sure you want to exit GHOST-XS Streamer? All features will be disabled.')) {
                fetch('/exit', { method: 'POST' });
                showNotification('Application shutting down...');
                setTimeout(() => window.close(), 1500);
            }
        }

        function updateSelectedAimbot() {
            const selected = document.getElementById('other-aimpos').value;
            fetch('/update_selected_aimbot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ aimbot: selected }),
            });
        }

        function updateHotkeyAimbot() {
            const selected = document.getElementById('hotkey-aimbot-selector').value;
            fetch('/update_hotkey_aimbot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ aimbot: selected }),
            });
            showNotification(`Hotkey target set to: ${selected}`);
        }

        function setIgnoreKnocked(ignore) {
            fetch('/set_ignore_knocked', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ignore_knocked: ignore }),
            });
            const status = ignore ? 'Yes' : 'No';
            log(`Ignore knocked enemies: ${status}`);
            
            if (ignore) {
                updateButtonState('ignoreYesBtn', true);
                updateButtonState('ignoreNoBtn', false);
            } else {
                updateButtonState('ignoreYesBtn', false);
                updateButtonState('ignoreNoBtn', true);
            }
        }

        function saveHotkey(key) {
            fetch('/save_hotkey', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hotkey: key }),
            });
        }

        function saveHoldHotkey(key) {
            fetch('/save_hold_hotkey', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hotkey: key }),
            });
        }

        function saveHoldDelay(delay) {
            fetch('/save_hold_delay', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delay: delay }),
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
                        statusText.textContent = 'Connected to Streamer';
                        currentProcessText.textContent = `Process: ${data.current_process}`;
                        altSection.classList.add('hidden');
                    } else {
                        badge.textContent = 'Offline';
                        badge.className = 'badge offline';
                        statusText.textContent = 'Server Offline';
                        currentProcessText.textContent = `Process: ${data.current_process}`;
                        altSection.classList.remove('hidden');
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
                        data.processes.forEach(proc => {
                            const opt = document.createElement('option');
                            opt.value = proc.name;
                            opt.textContent = `${proc.name} (PID: ${proc.pid})`;
                            selector.appendChild(opt);
                        });
                        showNotification('Process list updated');
                    }
                });
        }

        function setTargetProcess() {
            const selector = document.getElementById('process-selector');
            const selected = selector.value;
            if (!selected) {
                showNotification('Please select a process first');
                return;
            }
            fetch('/set_target_process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ process_name: selected }),
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

        function saveScopeHotkey(key) {
            fetch('/save_scope_hotkey', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hotkey: key }),
            });
        }

        document.addEventListener('DOMContentLoaded', () => {
            updateHDPlayerStatus();
            setInterval(updateHDPlayerStatus, 3000);
            updateProcessList();

            fetch('/get_hold_hotkey').then(r => r.json()).then(data => {
                if (data.success && data.hotkey) holdHotkeySelector.value = data.hotkey;
            });
            fetch('/get_hotkey_aimbot').then(r => r.json()).then(data => {
                if (data.success && data.aimbot) document.getElementById('hotkey-aimbot-selector').value = data.aimbot;
            });
            fetch('/get_drag_power').then(r => r.json()).then(data => {
                if (data.success && powerSlider) {
                    powerSlider.value = data.power;
                    powerValue.textContent = data.power + '%';
                }
            });
            fetch('/get_scope_hotkey').then(r => r.json()).then(data => {
                if (data.success && data.hotkey) document.getElementById('scope-hotkey-selector').value = data.hotkey;
            });

            hotkeySelector.addEventListener('change', () => {
                const key = hotkeySelector.value;
                if (key) { saveHotkey(key); log(`Hotkey set to: ${key}`); showNotification(`Hotkey set to: ${key}`); }
                else { saveHotkey(''); log('Hotkey cleared'); showNotification('Hotkey cleared'); }
            });

            holdHotkeySelector.addEventListener('change', () => {
                const key = holdHotkeySelector.value;
                if (key) { saveHoldHotkey(key); log(`Hold hotkey set to: ${key}`); showNotification(`Hold hotkey set to: ${key}`); }
                else { saveHoldHotkey(''); log('Hold hotkey cleared'); showNotification('Hold hotkey cleared'); }
            });

            delaySlider.addEventListener('input', () => {
                const delay = parseInt(delaySlider.value);
                delayValue.textContent = delay + 'ms';
                saveHoldDelay(delay);
            });

            delaySlider.addEventListener('change', () => {
                const delay = parseInt(delaySlider.value);
                log(`Hold key delay set to: ${delay}ms`);
                showNotification(`Hold key delay set to: ${delay}ms`);
            });

            powerSlider.addEventListener('input', () => {
                const power = parseInt(powerSlider.value);
                powerValue.textContent = power + '%';
                fetch('/set_drag_power', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ power: power }),
                });
            });

            document.getElementById('scope-hotkey-selector').addEventListener('change', () => {
                const key = document.getElementById('scope-hotkey-selector').value;
                if (key) { saveScopeHotkey(key); log(`Scope hotkey set to: ${key}`); showNotification(`Scope hotkey set to: ${key}`); }
                else { saveScopeHotkey(''); log('Scope hotkey cleared'); showNotification('Scope hotkey cleared'); }
            });

            const otherSelect = document.getElementById('other-aimpos');
            const leftShoulder = document.querySelector('.leftShoulder');
            const rightShoulder = document.querySelector('.rightShoulder');
            const aiAimbot = document.querySelector('.Aiaimbot');
            const powerContainer = document.getElementById('power-slider-container');
            
            otherSelect.addEventListener('change', () => {
                const val = otherSelect.value;
                leftShoulder.classList.add('hidden');
                rightShoulder.classList.add('hidden');
                aiAimbot.classList.add('hidden');
                powerContainer.classList.add('hidden');
                
                if (val === 'LeftShoulder') {
                    leftShoulder.classList.remove('hidden');
                    powerContainer.classList.remove('hidden');
                } else if (val === 'RightShoulder') {
                    rightShoulder.classList.remove('hidden');
                    powerContainer.classList.remove('hidden');
                } else if (val === 'AimbotAi') {
                    aiAimbot.classList.remove('hidden');
                }
            });

            const tabs = document.querySelectorAll('.tab');
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
        self.wfile.write(html.encode())
    
    def send_process_status(self):
        self.send_json({'is_running': is_process_running(current_target_process), 'current_process': current_target_process})
    
    def send_process_list(self):
        self.send_json({'success': True, 'processes': get_running_processes()})
    
    def send_hotkey_aimbot(self):
        self.send_json({'success': True, 'aimbot': hotkey_state["selected_aimbot"]})
    
    def send_hold_hotkey(self):
        self.send_json({'success': True, 'hotkey': hotkey_state["hold_key"] or ''})
    
    def send_scope_hotkey(self):
        self.send_json({'success': True, 'hotkey': ''})
    
    def send_drag_power(self):
        self.send_json({'success': True, 'power': drag_power})
    
    def handle_login(self, data):
        u,p = data.get('username',''), data.get('password','')
        creds = fetch_credentials()
        sid = get_computer_sid()
        if u in creds and creds[u][0]==p and creds[u][1]==sid:
            authenticated_users[self.client_address[0]] = time.time()
            self.send_json({'success': True})
        else:
            self.send_json({'success': False})
    
    def handle_execute(self, data):
        cmd = data.get('command','')
        result = "OK"
        
        if cmd == "aimbotscan":
            result = HEADLOAD()
        elif cmd == "aimbotenable":
            result = ENABLE_NECK()
        elif cmd == "aimbotdisable":
            result = AIMBOT_OFF()
        elif cmd == "leftShoulderOn":
            result = leftShoulderOn()
        elif cmd == "leftShoulderOff":
            result = leftShoulderOff()
        elif cmd == "rightShoulderOn":
            result = rightShoulderOn()
        elif cmd == "rightShoulderOff":
            result = rightShoulderOff()
        elif cmd == "AimbotAion":
            result = AimbotAion()
        elif cmd == "AimbotAioff":
            result = AimbotAioff()
        elif cmd == "loadsniper":
            result = "Sniper loaded"
        elif cmd == "sniperscopeenable":
            result = "Scope enabled"
        elif cmd == "sniperscopedisable":
            result = "Scope disabled"
        elif cmd == "sniperswitchenable":
            result = "Switch enabled"
        elif cmd == "sniperswitchdisable":
            result = "Switch disabled"
        elif cmd == "esp_inject":
            result = extract_and_inject_dll(current_target_process)
        elif cmd == "set_emulator_msi":
            result = "Emulator: MSI"
        elif cmd == "set_emulator_bluestacks":
            result = "Emulator: Bluestacks"
        elif cmd == "ignoreknocked_yes":
            result = "Ignore knocked: Yes"
        elif cmd == "ignoreknocked_no":
            result = "Ignore knocked: No"
        
        self.send_json({'success': True, 'message': result})
    
    def save_hotkey(self, data):
        self.send_json({'success': True})
    
    def save_hold_hotkey(self, data):
        hotkey_state["hold_key"] = data.get('hotkey','') or None
        self.send_json({'success': True})
    
    def save_hold_delay(self, data):
        hotkey_state["delay"] = data.get('delay', 50)
        self.send_json({'success': True})
    
    def save_scope_hotkey(self, data):
        self.send_json({'success': True})
    
    def set_drag_power(self, data):
        power = data.get('power', 50)
        result = set_drag_power(power)
        self.send_json({'success': True, 'message': result})
    
    def update_hotkey_aimbot(self, data):
        hotkey_state["selected_aimbot"] = data.get('aimbot','Head')
        self.send_json({'success': True})
    
    def update_selected_aimbot(self, data):
        self.send_json({'success': True})
    
    def set_target_process(self, data):
        global current_target_process
        p = data.get('process_name','')
        if p:
            current_target_process = p
            self.send_json({'success': True})
        else:
            self.send_json({'success': False})
    
    def set_ignore_knocked(self, data):
        self.send_json({'success': True})
    
    def handle_logout(self):
        if self.client_address[0] in authenticated_users:
            del authenticated_users[self.client_address[0]]
        self.send_json({'success': True})
    
    def handle_exit(self):
        self.send_json({'success': True})
        threading.Timer(1.0, self.server.shutdown).start()
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, *args): pass

# ==================== MAIN ====================
if __name__ == "__main__":
    print("=" * 60)
    print("     GHOST-XS STREAMER - FINAL")
    print("=" * 60)
    print(f"[*] PC SID: {get_computer_sid()}")
    print(f"[*] GitHub users: {len(fetch_credentials())}")
    print(f"[*] PyMem: {'OK' if PYMEM_OK else 'FAILED'}")
    print(f"[*] Embedded DLL: {'Found' if EMBEDDED_DLL_BASE64 and EMBEDDED_DLL_BASE64.strip() != 'PASTE_YOUR_BASE64_ENCODED_DLL_HERE' else 'Not found - add your DLL base64'}")
    
    threading.Thread(target=aimbot_loop, daemon=True).start()
    threading.Thread(target=collider_loop, daemon=True).start()
    threading.Thread(target=hold_hotkey_monitor, daemon=True).start()
    threading.Thread(target=drag_detection_loop, daemon=True).start()
    
    server = HTTPServer(('0.0.0.0', 8080), GhostWebServer)
    ip = socket.gethostbyname(socket.gethostname())
    
    print("\n" + "=" * 60)
    print(f"URL: http://{ip}:8080")
    print(f"Target Process: {current_target_process}")
    print(f"Delay: {hotkey_state['delay']}ms")
    print(f"Mouse Keys: Left, Right, Middle, X1, X2")
    print(f"Drag Power: 0-100% (maps to 0-50 pixels)")
    print("=" * 60)
    print("SCAN ONLY - No auto activation")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        try:
            os.system("taskkill /f /im pythonw.exe >nul 2>&1")
        except:
            pass
