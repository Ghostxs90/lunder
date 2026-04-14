#!/usr/bin/env python
# GHOST-XS STREAMER - FINAL
# Single pattern, unified aimbot

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
PAGE_EXECUTE_READWRITE = 0x40

# ==================== GITHUB AUTH URL ====================
GITHUB_AUTH_URL = "https://raw.githubusercontent.com/Ghostxs90/Sid/main/Sid.txt"

# ==================== MEMORY FUNCTIONS ====================
try:
    from pymem import Pymem
    from pymem.memory import read_bytes, write_bytes, read_int, write_int
    from pymem.pattern import pattern_scan_all
    PYMEM_OK = True
except ImportError:
    PYMEM_OK = False
    print("[!] PyMem not installed - run: pip install pymem")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pymem"])
        from pymem import Pymem
        from pymem.memory import read_bytes, write_bytes, read_int, write_int
        from pymem.pattern import pattern_scan_all
        PYMEM_OK = True
    except:
        pass

# ==================== EMBEDDED DLL ====================
EMBEDDED_DLL_BASE64 = """
PASTE_YOUR_BASE64_ENCODED_DLL_HERE
"""

# ==================== GLOBAL VARIABLES ====================
aimbot_addresses = []
aimbot_original_values = {}
aimbot_active = False
current_aim_mode = None  # "NECK", "LEFT", "RIGHT", "AIMBOT_AI"
last_aim_time = 0

# OFFSETS
OFFSET_HEAD_TARGET = 0xB8      # Head mode - read from
OFFSET_HEAD_WRITE = 0xB4       # Head mode - write to
OFFSET_LEFT_TARGET = 0xEC      # Left Shoulder - read from
OFFSET_RIGHT_TARGET = 0xE8     # Right Shoulder - read from
OFFSET_SHOULDER_WRITE = 0xA8   # Left/Right Shoulder - write to
OFFSET_AIMBOT_AI_READ = 0xFC   # Aimbot Ai - read from
OFFSET_AIMBOT_AI_WRITE = -0x358  # Aimbot Ai - write to

hotkey_state = {
    "hold_key": None,
    "selected_aimbot": "Head",
    "hold_active": False,
    "delay": 50
}

current_target_process = "HD-Player.exe"
authenticated_users = {}

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

# ==================== SINGLE PATTERN ====================
AIMBOT_PATTERN = "FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? FF FF FF FF FF FF FF FF FF FF FF FF ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? A5 43"

# ==================== SCAN FUNCTION ====================
def HEADLOAD():
    global aimbot_addresses, aimbot_original_values
    
    aimbot_addresses = []
    aimbot_original_values = {}
    
    if not PYMEM_OK:
        return "PyMem not installed"
    
    try:
        proc = Pymem(current_target_process)
    except Exception as e:
        return f"Game not found - Launch {current_target_process} first"

    try:
        entity_pattern = mkp(AIMBOT_PATTERN)
        addresses = pattern_scan_all(proc.process_handle, entity_pattern, return_multiple=True)
        found_addresses = [int(addr) for addr in addresses]
        
        if not found_addresses:
            proc.close_process()
            return "No entities found"
        
        valid_entities = []
        for addr in found_addresses:
            try:
                test_bytes = read_bytes(proc.process_handle, addr, 4)
                if test_bytes:
                    valid_entities.append(addr)
            except:
                continue
        
        aimbot_addresses = valid_entities
        proc.close_process()
        
        return f"SCANNING WITH ADV METHOD\nSCAN DONE\n{len(aimbot_addresses)} ENTITIES FOUND"
        
    except Exception as e:
        return f"Scan failed: {str(e)}"

# ==================== AIMBOT MODES ====================

def HEADON():
    global aimbot_active, current_aim_mode, aimbot_original_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    AIMBOT_OFF()
    
    aimbot_active = True
    current_aim_mode = "NECK"
    
    threading.Thread(target=_aimbot_loop, daemon=True).start()
    
    return "Headshot Enabled"

def HEADOFF():
    return AIMBOT_OFF()

def leftShoulderOn():
    global aimbot_active, current_aim_mode, aimbot_original_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    AIMBOT_OFF()
    
    aimbot_active = True
    current_aim_mode = "LEFT"
    
    threading.Thread(target=_aimbot_loop, daemon=True).start()
    
    return "Left Shoulder mode enabled"

def leftShoulderOff():
    return AIMBOT_OFF()

def rightShoulderOn():
    global aimbot_active, current_aim_mode, aimbot_original_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    AIMBOT_OFF()
    
    aimbot_active = True
    current_aim_mode = "RIGHT"
    
    threading.Thread(target=_aimbot_loop, daemon=True).start()
    
    return "Right Shoulder mode enabled"

def rightShoulderOff():
    return AIMBOT_OFF()

def AimbotAion():
    global aimbot_active, current_aim_mode, aimbot_original_values
    
    if not aimbot_addresses:
        return "No players - scan first"
    
    AIMBOT_OFF()
    
    aimbot_active = True
    current_aim_mode = "AIMBOT_AI"
    
    threading.Thread(target=_aimbot_loop, daemon=True).start()
    
    return "Aimbot Ai enabled"

def AimbotAioff():
    return AIMBOT_OFF()

def AIMBOT_OFF():
    global aimbot_active, current_aim_mode, aimbot_original_values
    
    aimbot_active = False
    current_aim_mode = None
    
    if aimbot_original_values and PYMEM_OK:
        try:
            proc = Pymem(current_target_process)
            for addr, orig in aimbot_original_values.items():
                try:
                    write_bytes(proc.process_handle, addr, orig, len(orig))
                except:
                    pass
            proc.close_process()
            aimbot_original_values.clear()
        except:
            pass
    
    return "All aimbot modes disabled"

# ==================== AIMBOT LOOP ====================
def _aimbot_loop():
    global aimbot_active, current_aim_mode, aimbot_original_values, last_aim_time
    
    last_write = 0
    
    while aimbot_active:
        if not aimbot_addresses or not PYMEM_OK or not current_aim_mode:
            time.sleep(0.01)
            continue
        
        try:
            current_time = time.time() * 1000
            if current_time - last_write >= 5:
                proc = Pymem(current_target_process)
                
                for base_addr in aimbot_addresses:
                    try:
                        if current_aim_mode == "NECK":
                            read_offset = OFFSET_HEAD_TARGET
                            write_offset = OFFSET_HEAD_WRITE
                            
                            if base_addr not in aimbot_original_values:
                                orig = read_bytes(proc.process_handle, base_addr + write_offset, 4)
                                if orig:
                                    aimbot_original_values[base_addr + write_offset] = orig
                            
                            value_bytes = read_bytes(proc.process_handle, base_addr + read_offset, 4)
                            if value_bytes:
                                write_bytes(proc.process_handle, base_addr + write_offset, value_bytes, 4)
                                
                        elif current_aim_mode == "LEFT":
                            read_offset = OFFSET_LEFT_TARGET
                            write_offset = OFFSET_SHOULDER_WRITE
                            
                            value_bytes = read_bytes(proc.process_handle, base_addr + read_offset, 4)
                            if value_bytes:
                                write_bytes(proc.process_handle, base_addr + write_offset, value_bytes, 4)
                                
                        elif current_aim_mode == "RIGHT":
                            read_offset = OFFSET_RIGHT_TARGET
                            write_offset = OFFSET_SHOULDER_WRITE
                            
                            value_bytes = read_bytes(proc.process_handle, base_addr + read_offset, 4)
                            if value_bytes:
                                write_bytes(proc.process_handle, base_addr + write_offset, value_bytes, 4)
                                
                        elif current_aim_mode == "AIMBOT_AI":
                            value = read_int(proc.process_handle, base_addr + OFFSET_AIMBOT_AI_READ)
                            write_int(proc.process_handle, base_addr + OFFSET_AIMBOT_AI_WRITE, value)
                            
                    except Exception:
                        continue
                
                proc.close_process()
                last_write = current_time
                
        except Exception:
            pass
        
        time.sleep(0.001)

# ==================== HOTKEY MONITOR ====================
def hold_hotkey_monitor():
    global aimbot_active, current_aim_mode, last_aim_time
    
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
                            if aimbot_addresses:
                                AimbotAion()
                        elif hotkey_state["selected_aimbot"] == "LeftShoulder":
                            if aimbot_addresses:
                                leftShoulderOn()
                        elif hotkey_state["selected_aimbot"] == "RightShoulder":
                            if aimbot_addresses:
                                rightShoulderOn()
                        else:
                            if aimbot_addresses:
                                HEADON()
                            
                elif not key_held and hotkey_state["hold_active"]:
                    hotkey_state["hold_active"] = False
                    AIMBOT_OFF()
                    
        except:
            pass
        time.sleep(0.001)

# ==================== DLL INJECTION ====================
def extract_and_inject_dll(process_name):
    try:
        if not EMBEDDED_DLL_BASE64 or EMBEDDED_DLL_BASE64.strip() == "PASTE_YOUR_BASE64_ENCODED_DLL_HERE":
            return "No embedded DLL found"
        
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
        kernel32.WriteProcessMemory(handle, allocated_mem, dll_bytes, dll_size, ctypes.byref(bytes_written))
        
        try:
            dos_header = dll_bytes[:64]
            e_lfanew = struct.unpack('<I', dos_header[60:64])[0]
            entry_point_rva = struct.unpack('<I', dll_bytes[e_lfanew + 40:e_lfanew + 44])[0]
            entry_point = allocated_mem + entry_point_rva
        except:
            entry_point = allocated_mem
        
        thread_id = ctypes.c_ulong()
        thread = kernel32.CreateRemoteThread(handle, None, 0, ctypes.c_void_p(entry_point), allocated_mem, 0, ctypes.byref(thread_id))
        
        if not thread:
            kernel32.VirtualFreeEx(handle, allocated_mem, 0, MEM_RELEASE)
            kernel32.CloseHandle(handle)
            return "Failed to create remote thread"
        
        kernel32.WaitForSingleObject(thread, 5000)
        kernel32.CloseHandle(thread)
        kernel32.CloseHandle(handle)
        
        return f"DLL injected into {process_name} (PID: {pid})"
        
    except Exception as e:
        return f"Injection failed: {str(e)}"

# ==================== PROCESS UTILITIES ====================
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
            self.send_json({'is_running': is_process_running(current_target_process), 'current_process': current_target_process})
        elif path == '/get_processes':
            self.send_json({'success': True, 'processes': get_running_processes()})
        elif path == '/get_hotkey_aimbot':
            self.send_json({'success': True, 'aimbot': hotkey_state["selected_aimbot"]})
        elif path == '/get_hold_hotkey':
            self.send_json({'success': True, 'hotkey': hotkey_state["hold_key"] or ''})
        elif path == '/get_scope_hotkey':
            self.send_json({'success': True, 'hotkey': ''})
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
            self.send_json({'success': True})
        elif path == '/save_hold_hotkey':
            hotkey_state["hold_key"] = data.get('hotkey', '') or None
            self.send_json({'success': True})
        elif path == '/save_hold_delay':
            hotkey_state["delay"] = data.get('delay', 50)
            self.send_json({'success': True})
        elif path == '/save_scope_hotkey':
            self.send_json({'success': True})
        elif path == '/update_hotkey_aimbot':
            hotkey_state["selected_aimbot"] = data.get('aimbot', 'Head')
            self.send_json({'success': True})
        elif path == '/update_selected_aimbot':
            self.send_json({'success': True})
        elif path == '/set_target_process':
            global current_target_process
            p = data.get('process_name', '')
            if p:
                current_target_process = p
                self.send_json({'success': True})
            else:
                self.send_json({'success': False})
        elif path == '/set_ignore_knocked':
            self.send_json({'success': True})
        elif path == '/logout':
            if self.client_address[0] in authenticated_users:
                del authenticated_users[self.client_address[0]]
            self.send_json({'success': True})
        elif path == '/exit':
            self.send_json({'success': True})
            threading.Timer(1.0, self.server.shutdown).start()
        else:
            self.send_json({'success': False})
    
    def send_login_page(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html = """<!DOCTYPE html><html><head><title>GHOST-XS Login</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif;}body{background:#0a0a0a;min-height:100vh;display:flex;justify-content:center;align-items:center;}.login-container{width:90%;max-width:380px;}.login-box{background:#141414;border:1px solid #ff3333;border-radius:8px;padding:30px 25px;}h2{color:#ff5555;text-align:center;}input{width:100%;padding:12px;background:#1e1e1e;border:1px solid #333;border-radius:4px;color:#fff;margin-bottom:20px;}button{width:100%;padding:12px;background:#1e1e1e;border:1px solid #ff3333;border-radius:4px;color:#ff5555;cursor:pointer;}button:hover{background:#2a2a2a;}</style></head><body><div class=login-container><div class=login-box><h2>GHOST-XS</h2><input type=text id=username placeholder=Username><input type=password id=password placeholder=Password><button onclick=login()>Login</button><div id=error style=color:#ef5350;text-align:center;margin-top:15px;display:none></div></div></div><script>function login(){const u=document.getElementById('username').value;const p=document.getElementById('password').value;if(!u||!p){document.getElementById('error').style.display='block';document.getElementById('error').textContent='Enter username and password';return;}fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})}).then(r=>r.json()).then(d=>{if(d.success){window.location.href='/dashboard';}else{document.getElementById('error').style.display='block';document.getElementById('error').textContent='Invalid credentials';}}).catch(()=>{document.getElementById('error').style.display='block';document.getElementById('error').textContent='Connection error';});}</script></body></html>"""
        self.wfile.write(html.encode())
    
    def send_dashboard_page(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        # Paste your FULL original dashboard HTML here
        html = """<!DOCTYPE html><html><head><title>GHOST-XS Streamer</title><meta name=viewport content="width=device-width, initial-scale=1.0"><style>/* YOUR ORIGINAL CSS HERE */</style></head><body><!-- YOUR ORIGINAL DASHBOARD HTML HERE --></body></html>"""
        self.wfile.write(html.encode())
    
    def handle_login(self, data):
        u, p = data.get('username', ''), data.get('password', '')
        creds = fetch_credentials()
        sid = get_computer_sid()
        if u in creds and creds[u][0] == p and creds[u][1] == sid:
            authenticated_users[self.client_address[0]] = time.time()
            self.send_json({'success': True})
        else:
            self.send_json({'success': False})
    
    def handle_execute(self, data):
        cmd = data.get('command', '')
        result = "OK"
        
        if cmd == "aimbotscan":
            result = HEADLOAD()
        elif cmd == "aimbotenable":
            result = HEADON()
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
            result = "Sniper functions ready"
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
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, *args):
        pass

# ==================== MAIN ====================
if __name__ == "__main__":
    print("=" * 60)
    print("     GHOST-XS STREAMER")
    print("=" * 60)
    print(f"[*] PC SID: {get_computer_sid()}")
    print(f"[*] PyMem: {'OK' if PYMEM_OK else 'FAILED'}")
    print(f"[*] Pattern: SINGLE")
    print(f"[*] Aimbot Ai offset: +0xFC -> -0x358")
    
    threading.Thread(target=hold_hotkey_monitor, daemon=True).start()
    
    PORT = 7744
    server = HTTPServer(('0.0.0.0', PORT), GhostWebServer)
    ip = socket.gethostbyname(socket.gethostname())
    
    print("\n" + "=" * 60)
    print(f"URL: http://{ip}:{PORT}")
    print(f"Target Process: {current_target_process}")
    print(f"Hold Delay: {hotkey_state['delay']}ms")
    print("=" * 60)
    print("READY")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
