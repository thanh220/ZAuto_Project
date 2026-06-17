import json, os, re, time, traceback
import hashlib
import uuid
import queue
import threading
import gc
import random
import sqlite3
import logging
import urllib.request
import urllib.error
import traceback
import stat
import os
from kivy.network.urlrequest import UrlRequest
import webbrowser
from logging.handlers import RotatingFileHandler
from collections import OrderedDict
from kivy.uix.image import Image
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.core.clipboard import Clipboard
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.utils import platform
from kivy.clock import Clock
from kivy.core.window import Window
from kivymd.uix.card import MDCard
from kivymd.uix.list import TwoLineAvatarIconListItem, ImageLeftWidget
from kivy.properties import StringProperty, BooleanProperty
from kivymd.toast import toast


# BẮT BUỘC: Cấu hình đồ họa để giảm lag GPU trên Android yếu
from kivy.config import Config
Config.set('graphics', 'multisamples', '0')
Config.set('kivy', 'pause_on_minimize', '0') # CẤM KIVY NGỦ ĐÔNG KHI ẨN APP

# --- 1. HỆ THỐNG LOG PRODUCTION ---
if platform == 'android':
    # Sửa chữ taxi thành zauto cho khớp với buildozer.spec
    BASE_PATH = '/data/data/org.zauto.zauto/files/'
    from android.runnable import run_on_ui_thread
    from jnius import autoclass, cast
    from android.permissions import request_permissions, Permission
    from android.broadcast import BroadcastReceiver
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Settings = autoclass('android.provider.Settings')
    Intent = autoclass('android.content.Intent')
    FrameLayout = autoclass('android.widget.FrameLayout')
else:
    BASE_PATH = './'
    def run_on_ui_thread(func): return func

LOG_DIR = os.path.join(BASE_PATH, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    handlers=[RotatingFileHandler(os.path.join(LOG_DIR, 'system.log'), maxBytes=1024*1024, backupCount=3)],
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 2. CƠ SỞ DỮ LIỆU SQLITE (THAY THẾ JSON) ---
DB_PATH = os.path.join(BASE_PATH, 'zauto_pro.db')
db_lock = threading.Lock()

def init_db():
    with db_lock:
        try:
            # THÊM isolation_level=None (Autocommit) để Worker không bị block "Database is locked"
            conn = sqlite3.connect(DB_PATH, timeout=15.0, isolation_level=None)
            c = conn.cursor()
            c.execute('PRAGMA journal_mode=WAL;') # Chống crash khi đọc/ghi đồng thời
            c.execute('CREATE TABLE IF NOT EXISTS config (key_name TEXT PRIMARY KEY, value_data TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, group_name TEXT, msg TEXT)')
            conn.commit()
        except Exception as e:
            logger.error(f"init_db error: {e}")
        finally:
            if 'conn' in locals() and conn: conn.close()

# --- 3. LRU CACHE ANTI-DUPLICATE (CHỐNG TRÀN RAM) ---
class LRUCache(OrderedDict):
    def __init__(self, maxsize=1000, *args, **kwds):
        self.maxsize = maxsize
        super().__init__(*args, **kwds)
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            oldest = next(iter(self))
            del self[oldest]

CONFIG_FILE = BASE_PATH + 'config.json' # Giữ biến này để không lỗi code nếu sót
HISTORY_FILE = BASE_PATH + 'history.json'
SUPPORT_PHONE = "0838429999"
LICENSE_FILE = os.path.join(BASE_PATH, 'license.dat')
TRIAL_FILE = os.path.join(BASE_PATH, 'trial_check.dat')
def get_machine_id():
    """Lấy ID máy chuẩn (Logic từ launcher_auto_secure.py)"""
    if platform == 'android':
        try:
            Secure = autoclass('android.provider.Settings$Secure')
            content_resolver = PythonActivity.mActivity.getContentResolver()
            return Secure.getString(content_resolver, Secure.ANDROID_ID)
        except: pass
    return str(uuid.getnode())[:12] #

def verify_license(lic_string, machine_id):
    """Xác thực Key dựa trên SHA256 (Logic từ keygen.py)"""
    try:
        if not lic_string or ":" not in lic_string: return False, 0
        expire_ts_str, key_hash = lic_string.split(':')
        expire_ts = int(expire_ts_str)
        # Khớp logic băm SHA256: f"{machine_id}:{expire}"
        raw_data = f"{machine_id}:{expire_ts}"
        calculated_hash = hashlib.sha256(raw_data.encode()).hexdigest()[:32]
        if calculated_hash == key_hash and expire_ts > int(time.time()):
            return True, expire_ts
    except: pass
    return False, 0
KV = '''
<RideCard>:
    orientation: "vertical"
    padding: "16dp"
    spacing: "12dp"
    size_hint_y: None
    height: self.minimum_height
    adaptive_height: True
    elevation: 0
    radius: [15, 15, 15, 15]
    md_bg_color: 1, 1, 1, 1

    MDBoxLayout:
        orientation: "horizontal"
        size_hint_y: None
        height: "40dp"
        spacing: "15dp"
        FitImage:
            source: "profile.jpg"
            size_hint: None, None
            size: "40dp", "40dp"
            radius: [20, ]
        MDBoxLayout:
            orientation: "vertical"
            MDLabel:
                text: root.group_text
                font_style: "Subtitle1"
                bold: True
                theme_text_color: "Primary"
                shorten: True
                shorten_from: "right"
            MDLabel:
                text: "Vừa xong lúc " + root.time_text
                font_style: "Caption"
                theme_text_color: "Secondary"

    MDSeparator:

    MDLabel:
        text: root.msg_text
        font_style: "Body1"
        theme_text_color: "Custom"
        text_color: 0.15, 0.15, 0.15, 1
        valign: "top"
        halign: "left"
        size_hint_y: None
        height: self.texture_size[1]

    MDBoxLayout:
        orientation: "horizontal"
        spacing: "10dp"
        size_hint_y: None
        height: "45dp"
        MDRoundFlatButton:
            text: "BỎ QUA"
            size_hint_x: 0.4
            text_color: 0.6, 0.2, 0.2, 1
            line_color: 0.9, 0.5, 0.5, 1
            on_release: app.remove_ride(root)
        Button:
            text: "NHẬN CUỐC"
            size_hint_x: 0.6
            size_hint_y: None
            height: "45dp"
            bold: True
            background_normal: ''
            background_color: 0.1, 0.5, 0.8, 1
            on_release: app.manual_accept_ride(root)

MDScreen:
    md_bg_color: 0.95, 0.96, 0.98, 1

    MDBottomNavigation:
        id: bottom_nav
        panel_color: 1, 1, 1, 1
        text_color_active: 0.1, 0.5, 0.8, 1
        text_color_normal: 0.6, 0.6, 0.6, 1
        use_text: True

        # ================= TAB 1: CANH ME =================
        MDBottomNavigationItem:
            name: 'tab_canhme'
            text: 'Canh me'
            icon: 'radar'
            
            MDBoxLayout:
                orientation: "vertical"
                
                MDBoxLayout:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    adaptive_height: True
                    padding: "15dp"
                    spacing: "10dp"
                    md_bg_color: 1, 1, 1, 1
                    radius: [0, 0, 15, 15]
                    
                    MDBoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: "40dp"
                        
                        MDLabel:
                            id: lbl_radar_status
                            text: "TẠM DỪNG"
                            font_style: "Subtitle2"
                            bold: True
                            theme_text_color: "Custom"
                            text_color: 0.6, 0.6, 0.6, 1
                            valign: "center"
                            
                        MDLabel:
                            text: "Auto:"
                            font_style: "Caption"
                            bold: True
                            theme_text_color: "Primary"
                            halign: "right"
                            valign: "center"
                            size_hint_x: None
                            width: "40dp"
                            
                        MDSwitch:
                            id: sw_auto_main
                            pos_hint: {'center_y': .5}
                            on_active: app.sync_auto_switch(self.active)
                            
                    MDFillRoundFlatButton:
                        id: btn_toggle_radar
                        text: "BẬT QUÉT CUỐC"
                        font_name: "Roboto-Bold"
                        size_hint_x: 1
                        size_hint_y: None
                        height: "45dp"
                        md_bg_color: 0.1, 0.6, 0.2, 1
                        on_release: app.toggle_radar()
                
                MDBoxLayout:
                    size_hint_y: None
                    height: "40dp"
                    md_bg_color: 1, 0.95, 0.8, 1
                    padding: ["10dp", "0dp"]
                    MDIcon:
                        icon: "alert-circle-outline"
                        theme_text_color: "Custom"
                        text_color: 0.8, 0.5, 0, 1
                        pos_hint: {"center_y": .5}
                    MDLabel:
                        text: " Giữ sáng màn hình để bắt cuốc"
                        font_style: "Caption"
                        theme_text_color: "Custom"
                        text_color: 0.6, 0.4, 0, 1
                        valign: "center"

                ScrollView:
                    MDBoxLayout:
                        id: ride_list
                        orientation: "vertical"
                        padding: "10dp"
                        spacing: "10dp"
                        size_hint_y: None
                        height: self.minimum_height
                        adaptive_height: True

        # ================= TAB 2: LỊCH SỬ =================
        MDBottomNavigationItem:
            name: 'tab_tinnhan'
            text: 'Tin nhắn'
            icon: 'message-text-outline'
            MDBoxLayout:
                orientation: 'vertical'
                MDTopAppBar:
                    title: "Lịch sử chốt"
                    elevation: 0
                    md_bg_color: 1, 1, 1, 1
                    specific_text_color: 0.1, 0.1, 0.1, 1
                    right_action_items: [["delete-sweep-outline", lambda x: app.clear_history()]]
                
                MDBoxLayout:
                    size_hint_y: None
                    height: "60dp"
                    padding: "10dp"
                    md_bg_color: 1, 1, 1, 1
                    Button:
                        text: "MỞ KHUNG CHAT ZALO"
                        size_hint_x: 1
                        size_hint_y: None
                        height: "45dp"
                        bold: True
                        background_normal: ''
                        background_color: 0.1, 0.6, 0.2, 1
                        on_release: app.root.ids.bottom_nav.switch_tab('tab_zalo')

                ScrollView:
                    MDList:
                        id: msg_history_list
                        md_bg_color: 0.95, 0.96, 0.98, 1

        # ================= TAB NHÓM =================
        MDBottomNavigationItem:
            name: 'tab_nhom'
            text: 'Nhóm'
            icon: 'account-group'
            
            MDBoxLayout:
                orientation: 'vertical'
                
                MDTopAppBar:
                    title: "Danh sách nhóm"
                    elevation: 0
                    md_bg_color: 0.1, 0.6, 0.2, 1
                    specific_text_color: 1, 1, 1, 1
                    pos_hint: {"top": 1}
                    
                ScrollView:
                    MDList:
                        id: group_filter_list
                        md_bg_color: 0.95, 0.96, 0.98, 1

        # ================= TAB TÀI KHOẢN ZALO =================
        MDBottomNavigationItem:
            name: 'tab_zalo'
            text: 'Zalo'
            icon: 'account-circle'
            on_tab_press: app._init_webview_android()
            on_enter: app.set_webview_visible(True)
            on_leave: app.set_webview_visible(False)

            MDBoxLayout:
                orientation: 'vertical'

                MDBoxLayout:
                    id: zalo_status_bar
                    size_hint_y: None
                    height: "65dp"
                    padding: ["10dp", "5dp"]
                    spacing: "10dp"
                    md_bg_color: 0.1, 0.5, 0.8, 1
                    
                    FitImage:
                        id: zalo_avatar_view
                        source: "profile.jpg"
                        size_hint: None, None
                        size: "40dp", "40dp"
                        radius: [20, ]
                        pos_hint: {"center_y": .5}

                    # ---> ĐÃ LÙI LỀ VÀO TRONG NẰM CÙNG HÀNG VỚI FitImage <---
                    MDBoxLayout:
                        orientation: "vertical"
                        pos_hint: {"center_y": .5}
                        md_bg_color: 0.1, 0.5, 0.8, 1
                        MDLabel:
                            id: zalo_name_view
                            text: "Chưa kết nối Zalo"
                            theme_text_color: "Custom"
                            text_color: 1, 1, 1, 1
                            font_style: "Subtitle2"
                            bold: True
                        MDLabel:
                            text: "Trình duyệt chìm"
                            theme_text_color: "Custom"
                            text_color: 0.9, 0.9, 0.9, 1
                            font_style: "Caption"

                    # ---> NÚT NÀY CŨNG ĐÃ LÙI LỀ VÀO TRONG <---
                    MDRaisedButton:
                        id: btn_zalo_action
                        text: "TẢI LẠI"
                        size_hint_y: None
                        height: "36dp"
                        md_bg_color: 1, 1, 1, 0.25
                        pos_hint: {"center_y": .5}
                        elevation: 0
                        on_release: app.reload_zalo_web()

                # ---> HỘP CHỨA WEBVIEW PHẢI NẰM NGOÀI ĐỂ XẾP DƯỚI THANH STATUS <---
                MDBoxLayout:
                    id: webview_container
                    size_hint_y: 1
                    md_bg_color: 1, 1, 1, 1

        # ================= TAB CÀI ĐẶT =================
        MDBottomNavigationItem:
            name: 'tab_caidat'
            text: 'Cài đặt'
            icon: 'cog-outline'
            MDBoxLayout:
                orientation: 'vertical'
                MDTopAppBar:
                    title: "Thiết lập hệ thống"
                    elevation: 0
                    md_bg_color: 1, 1, 1, 1
                    specific_text_color: 0.1, 0.1, 0.1, 1
                
                ScrollView:
                    MDBoxLayout:
                        orientation: 'vertical'
                        size_hint_y: None
                        height: self.minimum_height
                        adaptive_height: True
                        padding: "10dp"
                        spacing: "15dp"
                        md_bg_color: 0.95, 0.96, 0.98, 1
                        
                        MDBoxLayout: # Thông tin tài khoản
                            orientation: "horizontal"
                            size_hint_y: None
                            height: "70dp"
                            padding: "10dp"
                            md_bg_color: 1, 1, 1, 1
                            radius: [10, ]
                            FitImage:
                                source: 'profile.jpg'
                                size_hint: None, None
                                size: "50dp", "50dp"
                                radius: [25, ]
                            MDBoxLayout:
                                orientation: 'vertical'
                                padding: ["10dp", 0, 0, 0]
                                MDLabel:
                                    text: "Taxi Lắk - ZAuto VIP"
                                    font_style: "Subtitle2"
                                    bold: True
                                MDLabel:
                                    text: "Hỗ trợ mua: 0838429999"
                                    theme_text_color: "Primary"
                                    font_style: "Caption"

                        # --- KHỐI NÚT ĐIỀU KHIỂN HỆ THỐNG ---
                        MDBoxLayout:
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height
                            adaptive_height: True
                            spacing: "10dp"

                            Button:
                                text: "CẤP QUYỀN APP"
                                size_hint_x: 1
                                size_hint_y: None
                                height: "45dp"
                                bold: True
                                background_normal: ''
                                background_color: 0.8, 0.4, 0.1, 1
                                on_release: app.check_permissions_and_guide()
                                
                            Button:
                                text: "CHỐNG NGỦ ĐÔNG (QUAN TRỌNG)"
                                size_hint_x: 1
                                size_hint_y: None
                                height: "45dp"
                                bold: True
                                background_normal: ''
                                background_color: 0.6, 0.1, 0.1, 1
                                on_release: app.request_ignore_battery()

                        # --- KHỐI CÔNG TẮC (GIỌNG NÓI / AUTO / FILTER) ---
                        MDBoxLayout:
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height
                            adaptive_height: True
                            padding: "10dp"
                            md_bg_color: 1, 1, 1, 1
                            radius: [10, ]

                            MDBoxLayout:
                                size_hint_y: None
                                height: "45dp"
                                MDLabel:
                                    text: "Đọc giọng nói (Báo cuốc/Chốt)"
                                    font_style: "Subtitle2"
                                MDSwitch:
                                    id: sw_voice
                                    pos_hint: {'center_y': .5}
                            
                            MDSeparator:

                            MDBoxLayout:
                                size_hint_y: None
                                height: "45dp"
                                MDLabel:
                                    text: "Tự động chốt cuốc"
                                    font_style: "Subtitle2"
                                MDSwitch:
                                    id: sw_auto_settings
                                    pos_hint: {'center_y': .5}
                                    on_active: app.sync_auto_switch(self.active)
                            
                            MDSeparator:

                            MDBoxLayout:
                                size_hint_y: None
                                height: "45dp"
                                MDLabel:
                                    text: "Chỉ nhận tin chứa Từ Khóa"
                                    font_style: "Subtitle2"
                                MDSwitch:
                                    id: sw_filter
                                    pos_hint: {'center_y': .5}
                                    on_active: app.on_filter_switch(self.active)
                            
                        # --- HƯỚNG DẪN DÙNG TIẾNG VIỆT ---
                        MDBoxLayout:
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height 
                            padding: "12dp"
                            spacing: "5dp" 
                            md_bg_color: 0.9, 0.95, 1, 1
                            radius: [10, ]
                            
                            MDLabel:
                                text: "💡 MẸO GÕ TIẾNG VIỆT:"
                                font_style: "Caption"
                                bold: True
                                theme_text_color: "Primary"
                                size_hint_y: None
                                height: self.texture_size[1]
                                
                            MDLabel:
                                text: "Soạn chữ ở Zalo rồi Copy,bấm biểu tượng DÁN ở bên cạnh mỗi ô."
                                font_style: "Caption"
                                theme_text_color: "Secondary"
                                size_hint_y: None
                                height: self.texture_size[1]

                        # --- CÁC Ô NHẬP LIỆU CÓ NÚT DÁN NHANH ---
                        MDBoxLayout: 
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height
                            adaptive_height: True
                            padding: "10dp"
                            spacing: "20dp"
                            md_bg_color: 1, 1, 1, 1
                            radius: [10, ]
                            
                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: "50dp"
                                spacing: "10dp"
                                TextInput:
                                    id: inp_nhan
                                    hint_text: "Từ khóa NHẬN"
                                    multiline: True
                                    background_color: 0.95, 0.95, 0.95, 1
                                    foreground_color: 0, 0, 0, 1
                                MDIconButton:
                                    icon: "content-paste"
                                    pos_hint: {"center_y": .5}
                                    on_release: inp_nhan.text = app.Clipboard.paste()

                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: "50dp"
                                spacing: "10dp"
                                TextInput:
                                    id: inp_loai
                                    hint_text: "Từ khóa BỎ QUA"
                                    multiline: True
                                    background_color: 0.95, 0.95, 0.95, 1
                                    foreground_color: 0, 0, 0, 1
                                MDIconButton:
                                    icon: "content-paste"
                                    pos_hint: {"center_y": .5}
                                    on_release: inp_loai.text = app.Clipboard.paste()

                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: "50dp"
                                spacing: "10dp"
                                TextInput:
                                    id: inp_reply
                                    hint_text: "Nội dung trả lời tự động"
                                    multiline: True
                                    background_color: 0.95, 0.95, 0.95, 1
                                    foreground_color: 0, 0, 0, 1
                                MDIconButton:
                                    icon: "content-paste"
                                    pos_hint: {"center_y": .5}
                                    on_release: inp_reply.text = app.Clipboard.paste()
                                
                            TextInput:
                                id: inp_delay
                                hint_text: "Khoảng cách chốt 2 cuốc (giây)"
                                text: "30"
                                input_filter: "int"
                                size_hint_y: None
                                height: "45dp"
                                background_color: 0.95, 0.95, 0.95, 1
                                foreground_color: 0, 0, 0, 1
                        
                        Button:
                            text: "LƯU CẤU HÌNH"
                            size_hint_x: 1
                            size_hint_y: None
                            height: "45dp"
                            bold: True
                            background_normal: ''
                            background_color: 0.1, 0.5, 0.8, 1
                            on_release: app.save_config()

                        MDBoxLayout:
                            orientation: "vertical"
                            size_hint_y: None
                            height: "180dp"
                            padding: "15dp"
                            spacing: "5dp"
                            md_bg_color: 1, 1, 1, 1
                            radius: [10, ]
                            MDLabel:
                                text: "BẢN QUYỀN"
                                bold: True
                                font_style: "Subtitle2"
                            MDSeparator:
                            MDLabel:
                                id: lbl_key_type
                                text: "Loại Key: Đang kiểm tra..."
                                font_style: "Caption"
                            MDLabel:
                                id: lbl_expiry
                                text: "Hết hạn: --/--/----"
                                font_style: "Caption"
                            MDLabel:
                                text: "SĐT Mua Key: 0838429999"
                                theme_text_color: "Custom"
                                text_color: 0.1, 0.5, 0.8, 1
                                font_style: "Caption"
                            Button:
                                text: "MUA THÊM HẠN"
                                size_hint_y: None
                                height: "35dp"
                                pos_hint: {"center_x": .5}
                                bold: True
                                background_normal: ''
                                background_color: 0.1, 0.6, 0.2, 1
                                on_release: app.show_activation_popup_from_settings()

                        # --- KHỐI KIỂM TRA HỆ THỐNG TỰ ĐỘNG (DEEP CHECK) ---
                        MDBoxLayout:
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height
                            adaptive_height: True
                            padding: "10dp"
                            spacing: "8dp"
                            md_bg_color: 1, 1, 1, 1
                            radius: [10, ]

                            MDLabel:
                                text: "🩺 KIỂM TRA & TỰ CHẨN ĐOÁN APP"
                                font_style: "Subtitle2"
                                bold: True
                                size_hint_y: None
                                height: self.texture_size[1]

                            MDLabel:
                                id: lbl_diag_status
                                text: "Chưa kiểm tra lần nào."
                                font_style: "Caption"
                                theme_text_color: "Secondary"
                                size_hint_y: None
                                height: self.texture_size[1]

                            Button:
                                id: btn_run_diagnostics
                                text: "🔍 KIỂM TRA HỆ THỐNG (DEEP CHECK)"
                                size_hint_x: 1
                                size_hint_y: None
                                height: "48dp"
                                bold: True
                                background_normal: ''
                                background_color: 0.5, 0.1, 0.7, 1
                                on_release: app.run_system_diagnostics()

                        MDBoxLayout:
                            size_hint_y: None
                            height: "20dp"
                            md_bg_color: 0.95, 0.96, 0.98, 1
'''


class ActivationPopup(Popup):
    def __init__(self, machine_id, on_success, can_cancel=False, **kwargs):
        super().__init__(**kwargs)
        self.title = "KÍCH HOẠT BẢN QUYỀN ZAUTO VIP"
        
        # --- CẤU HÌNH KÍCH THƯỚC THỦ CÔNG (CHỐNG LỆM NÚT) ---
        self.size_hint = (0.9, None) # Rộng 90% màn hình, cao không theo tỷ lệ %
        self.height = dp(480)        # Chiều cao cố định 480dp (vừa đủ hiện tất cả)
        self.auto_dismiss = can_cancel 
        self.on_success = on_success
        self.machine_id = machine_id

        # --- THIẾT KẾ NỀN TRẮNG CHUẨN VIP ---
        self.background = ""  
        self.background_color = (1, 1, 1, 1) 
        self.title_color = (0, 0, 0, 1)      
        self.separator_color = (0.1, 0.5, 0.8, 1)

        # --- TẠO BỘ CUỘN (SCROLLVIEW) ---
        # Giúp máy màn hình ngắn vẫn vuốt xuống để thấy nút Kích Hoạt
        root_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)

        # Layout chứa toàn bộ nội dung bên trong ScrollView
        main_layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(12), size_hint_y=None)
        # Quan trọng: Dòng này giúp layout tự nở dài ra theo nội dung để ScrollView hoạt động
        main_layout.bind(minimum_height=main_layout.setter('height'))

        # --- 1. NÚT X MÀU ĐỎ (CHỈ HIỆN KHI can_cancel=True) ---
        if can_cancel:
            header = BoxLayout(size_hint_y=None, height=dp(30))
            header.add_widget(Label()) # Đẩy nút X sang phải
            btn_close = Button(
                text="X", size_hint=(None, None), size=(dp(40), dp(30)),
                bold=True, color=(1, 1, 1, 1), background_normal='',
                background_color=(0.8, 0, 0, 1)
            )
            btn_close.bind(on_release=self.dismiss)
            header.add_widget(btn_close)
            main_layout.add_widget(header)

        # --- 2. PHẦN COPY ID MÁY ---
        main_layout.add_widget(Label(
            text="MÃ ID MÁY CỦA BẠN:", 
            color=(0.3, 0.3, 0.3, 1), font_size='14sp', 
            size_hint_y=None, height=dp(20), bold=True
        ))

        self.id_box = TextInput(
            text=machine_id, readonly=True, size_hint_y=None, height=dp(45),
            halign='center', font_size='16sp', font_name="Roboto",
            background_color=(0.95, 0.95, 0.95, 1), foreground_color=(0, 0, 0, 1)
        )
        main_layout.add_widget(self.id_box)

        btn_copy = Button(
            text="CHẠM ĐỂ COPY ID MÁY", 
            size_hint_y=None, height=dp(45),
            bold=True, font_size='15sp', background_normal='',
            background_color=(0.1, 0.5, 0.8, 1)
        )
        btn_copy.bind(on_release=self.copy_to_clipboard)
        main_layout.add_widget(btn_copy)
        
        # --- 3. PHẦN CHỌN GÓI VÀ NHẬP KEY ---
        main_layout.add_widget(Label(
            text="CHỌN GÓI VÀ NHẬP MÃ KEY:", 
            color=(0.2, 0.2, 0.2, 1), font_size='14sp',
            size_hint_y=None, height=dp(20), bold=True
        ))
        
        self.pkg_spin = Spinner(
            text='Chọn gói mua',
            values=('30 Ngày - 30K', '365 Ngày - 300K', 'VĨNH VIỄN - 600K'),
            size_hint_y=None, height=dp(45),
            background_color=(0.1, 0.5, 0.8, 1), color=(1, 1, 1, 1)
        )
        main_layout.add_widget(self.pkg_spin)

        self.key_in = TextInput(
            hint_text="Dán mã Key đã mua vào đây...", 
            multiline=False, size_hint_y=None, height=dp(45),
            halign='center', font_size='15sp'
        )
        main_layout.add_widget(self.key_in)

        # --- 4. THÔNG TIN HỖ TRỢ ---
        main_layout.add_widget(Label(
            text=f"Liên hệ Zalo mua Key: {SUPPORT_PHONE}", 
            font_size='13sp', color=(0.8, 0.2, 0.2, 1),
            size_hint_y=None, height=dp(30)
        ))

        # --- 5. NÚT KÍCH HOẠT ---
        btn_active = Button(
            text="KÍCH HOẠT NGAY", 
            size_hint_y=None, height=dp(55), 
            background_normal='', background_color=(0, 0.5, 0, 1), 
            color=(1, 1, 1, 1), bold=True
        )
        btn_active.bind(on_release=self.validate)
        main_layout.add_widget(btn_active)

        # Gán layout vào ScrollView, gán ScrollView làm nội dung của Popup
        root_scroll.add_widget(main_layout)
        self.content = root_scroll

    def copy_to_clipboard(self, instance):
        """Thực hiện copy ID vào clipboard"""
        from kivy.core.clipboard import Clipboard
        Clipboard.copy(self.machine_id)
        toast("Đã copy ID máy thành công!")

    def validate(self, instance):
        key = self.key_in.text.strip()
        ok, expiry = verify_license(key, self.machine_id)
        if ok:
            with open(LICENSE_FILE, 'w') as f: f.write(key)
            self.on_success(expiry)
            self.dismiss()
        else:
            toast("Mã Key không đúng hoặc đã hết hạn!")


class DiagnosticsPopup(Popup):
    """Popup hiện kết quả Deep Check — log dạng text để người dùng copy ra gửi sửa lỗi."""
    def __init__(self, report_text, **kwargs):
        super().__init__(**kwargs)
        self.title = "KẾT QUẢ KIỂM TRA HỆ THỐNG"
        self.size_hint = (0.95, 0.85)
        self.auto_dismiss = True
        self.report_text = report_text

        self.background = ""
        self.background_color = (1, 1, 1, 1)
        self.title_color = (0, 0, 0, 1)
        self.separator_color = (0.5, 0.1, 0.7, 1)

        root = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))

        self.log_box = TextInput(
            text=report_text,
            readonly=True,
            font_size='12sp',
            background_color=(0.07, 0.07, 0.09, 1),
            foreground_color=(0.85, 0.95, 0.85, 1),
            cursor_color=(1, 1, 1, 1),
        )
        root.add_widget(self.log_box)

        btn_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(48), spacing=dp(10))

        btn_copy = Button(
            text="COPY TOÀN BỘ LOG",
            background_normal='', background_color=(0.1, 0.5, 0.8, 1),
            color=(1, 1, 1, 1), bold=True
        )
        btn_copy.bind(on_release=self.copy_log)
        btn_row.add_widget(btn_copy)

        btn_close = Button(
            text="ĐÓNG",
            background_normal='', background_color=(0.6, 0.1, 0.1, 1),
            color=(1, 1, 1, 1), bold=True
        )
        btn_close.bind(on_release=self.dismiss)
        btn_row.add_widget(btn_close)

        root.add_widget(btn_row)
        self.content = root

    def copy_log(self, instance):
        from kivy.core.clipboard import Clipboard
        Clipboard.copy(self.report_text)
        toast("Đã copy toàn bộ log!")


class RideCard(MDCard):
    group_text = StringProperty()
    msg_text = StringProperty()
    time_text = StringProperty()
class ZAutoHybridVisionEngine:
    def __init__(self):
        # LAZY INIT: Không dùng np ở đây — tránh crash khi numpy chưa được cài
        self.lower_bound = [0, 0, 200]
        self.upper_bound = [180, 30, 255]

    def process_screenshot_and_double_click(self, screenshot_path):
        """
        Mắt nhìn AI: Phân tích ma trận điểm ảnh, định vị tọa độ khoảng trống lề phải
        cạnh bong bóng chat cuối cùng để phát lệnh click đúp vật lý.
        """
        try:
            # LAZY IMPORT: Chỉ import khi thật sự cần, không crash app khi thiếu thư viện
            try:
                import cv2
                import numpy as np
            except ImportError:
                logger.warning("OpenCV/numpy chưa cài — Vision Engine bị tắt tự động")
                return False

            if not os.path.exists(screenshot_path): return False
            
            lb = np.array(self.lower_bound)
            ub = np.array(self.upper_bound)

            # Đọc ảnh chụp màn hình thô
            img = cv2.imread(screenshot_path)
            if img is None: return False
            
            height, width, _ = img.shape
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, lb, ub)
            
            # Quét tìm các đa giác biên (Contours) của tin nhắn hiển thị trên màn hình
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            target_bubble = None
            max_y_axis = 0
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                # Bộ lọc loại bỏ thành phần nhiễu giao diện (Kích thước tối thiểu)
                if w > 100 and h > 40:
                    if y > max_y_axis: # Tìm tin nhắn mới nhất nằm dưới cùng màn hình
                        max_y_axis = y
                        target_bubble = (x, y, w, h)
            
            success = False
            if target_bubble:
                x, y, w, h = target_bubble
                # CƠ CHẾ ĐỊNH VỊ: Đẩy tọa độ dịch sang phải 30px tính từ viền ngoài bóng chat
                click_x = x + w + 30
                
                # Chống tràn biên lề phải màn hình thiết bị
                if click_x > width - 10: click_x = width - 40
                click_y = y + (h / 2)
                
                # PHÁT LỆNH ĐIỀU KHIỂN: Gửi sự kiện Touch vật lý trực tiếp qua Runtime Android
                from jnius import autoclass
                Runtime = autoclass('java.lang.Runtime')
                runtime = Runtime.getRuntime()
                
                # Thực hiện mô phỏng hai lệnh bấm liên tiếp giãn cách 60ms (Dblclick vật lý)
                runtime.exec(f"input tap {int(click_x)} {int(click_y)}")
                time.sleep(0.06)
                runtime.exec(f"input tap {int(click_x)} {int(click_y)}")
                success = True

            # ==============================================================
            # CRITICAL OPTIMIZATION: GIẢI PHÓNG BỘ NHỚ MA TRẬN ẢNH TỨC THÌ
            # ==============================================================
            del img, hsv, mask, contours
            gc.collect()
            
            return success
                
        except Exception as e:
            logger.error(f"Lỗi động cơ thị giác Vision Engine: {e}")
            gc.collect()
        return False
    
class ZAutoProApp(MDApp):
    # ==========================================
    # QUẢN LÝ PHIÊN BẢN (TĂNG SỐ NÀY LÊN MỖI LẦN BUILD MỚI)
    APP_VERSION = 4.6
    
    # LINK TRẠM PHÁT SÓNG GITHUB GIST CỦA BẠN
    UPDATE_URL = "https://gist.githubusercontent.com/thienne3110/201422dc482a5ba8e519cad25aeb8918/raw/update.json"
    # ==========================================

    def toggle_radar(self):
        """Hàm bật/tắt công tắc Radar (Chỉ quét, không quyết định Auto)"""
        self.is_radar_running = not self.is_radar_running
        
        btn = self.root.ids.btn_toggle_radar
        lbl = self.root.ids.lbl_radar_status
        
        if self.is_radar_running:
            btn.text = "ĐANG QUÉT... (BẤM ĐỂ DỪNG)"
            btn.md_bg_color = (0.8, 0.2, 0.2, 1) # Nút chuyển Đỏ
            lbl.text = "RADAR ĐANG HOẠT ĐỘNG"
            lbl.text_color = (0.1, 0.5, 0.8, 1) # Chữ chuyển Xanh dương
            toast("Radar đã BẬT: Đang lắng nghe cuốc xe!")
        else:
            btn.text = "BẬT RADAR QUÉT CUỐC"
            btn.md_bg_color = (0.1, 0.6, 0.2, 1)
            lbl.text = "HỆ THỐNG ĐANG TẠM DỪNG"
            lbl.text_color = (0.6, 0.6, 0.6, 1)
            toast("Radar đã TẠM DỪNG!")

    def sync_auto_switch(self, active_state):
        try:
            if self.root.ids.sw_auto_main.active != active_state:
                self.root.ids.sw_auto_main.active = active_state

            if self.root.ids.sw_auto_settings.active != active_state:
                self.root.ids.sw_auto_settings.active = active_state

            # FIX 1: BẮT BUỘC PHẢI CẬP NHẬT VÀO BỘ NHỚ RAM TRƯỚC KHI LƯU
            self.config_data['sw_auto'] = active_state
            self.save_config_silent()

            toast("Đã bật AUTO CHỐT" if active_state else "Đã tắt AUTO CHỐT")

        except Exception:
            print(traceback.format_exc())
    def on_filter_switch(self, active_state):
        self.config_data['sw_filter'] = active_state
        self.save_config_silent()
        toast("Đã BẬT lọc từ khóa" if active_state else "Đã TẮT lọc từ khóa - Nhận mọi tin")        
    def build(self):
        # Cấp quyền cho libnode.so trước khi ứng dụng khởi chạy hoàn toàn
        self.fix_permissions()
        
        from kivy.core.clipboard import Clipboard
        self.Clipboard = Clipboard
        self.icon = 'profile.jpg'
        self.theme_cls.primary_palette = "Blue"
        
        self.config_data = {
            'nhan': '', 'loai': '', 'reply_msg': 'Ok nhận', 'gia_km': '12000',
            'global_delay': '30', 'sw_voice': True,
            'sw_filter': False, 'sw_auto': False, 'is_linked': False
        }
        
        self.last_global_reply_time = 0
        self.is_linked = False
        
        self.root = Builder.load_string(KV)
        
        return self.root
    def fix_permissions(self):
        """Cấp quyền thực thi tự động cho libnode.so theo kiến trúc máy"""
        if platform == 'android':
            import os
            import stat
            import platform as sys_platform
            
            # Tự động lấy kiến trúc chip: aarch64 (64-bit) hoặc armv7l (32-bit)
            arch = sys_platform.machine()
            # Map sang tên thư mục bạn đã tạo trong nodejs_backend/bin/
            abi = "arm64-v8a" if arch == "aarch64" else "armeabi-v7a"
            
            # Đường dẫn linh hoạt dựa trên ABI
            lib_path = f"/data/data/org.zauto.zauto/files/app/nodejs_backend/bin/{abi}/libnode.so"
            
            if os.path.exists(lib_path):
                try:
                    # Cấp quyền thực thi: 0755 (rwxr-xr-x)
                    os.chmod(lib_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                    print(f"✅ Đã cấp quyền cho {abi} thành công!")
                except Exception as e:
                    print(f"❌ Lỗi cấp quyền cho {abi}: {e}")
            else:
                print(f"⚠️ Không tìm thấy file tại: {lib_path}")
    def on_start(self):
        try:
            init_db()
            threading.Thread(target=self.start_node_server, daemon=True).start()
            Clock.schedule_once(lambda dt: self.delayed_ui_startup(), 0.2)

            # KHỞI ĐỘNG WORKER CHO CẢ PC LẪN ANDROID — không bị kẹt queue khi test PC
            self.msg_worker_thread = threading.Thread(target=self._message_worker, daemon=True)
            self.msg_worker_thread.start()
            self.reply_worker_thread = threading.Thread(target=self._reply_worker_loop, daemon=True)
            self.reply_worker_thread.start()
            self.audio_worker_thread = threading.Thread(target=self._audio_worker_loop, daemon=True)
            self.audio_worker_thread.start()
            self.poll_worker_thread = threading.Thread(target=self._java_poll_worker, daemon=True)
            self.poll_worker_thread.start()
            self.node_poll_worker_thread = threading.Thread(target=self._node_poll_worker, daemon=True)
            self.node_poll_worker_thread.start()

            Clock.schedule_interval(self._system_watchdog, 180)
            Clock.schedule_interval(self._process_ui_queue, 0.1)

            if platform == 'android':
                try:
                    ActivityInfo = autoclass('android.content.pm.ActivityInfo')
                    PythonActivity.mActivity.setRequestedOrientation(
                        ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
                    )
                    request_permissions([Permission.INTERNET, Permission.ACCESS_FINE_LOCATION, Permission.POST_NOTIFICATIONS])
                    _fgIntent = autoclass('android.content.Intent')(PythonActivity.mActivity, autoclass('org.zauto.ZaloForegroundService'))
                    PythonActivity.mActivity.startForegroundService(_fgIntent)

                    # ÉP CPU KHÔNG NGỦ (MỨC 1)
                    PowerManager = autoclass('android.os.PowerManager')
                    Context = autoclass('android.content.Context')
                    pm = cast(PowerManager, PythonActivity.mActivity.getSystemService(Context.POWER_SERVICE))
                    self.wakelock = pm.newWakeLock(1, "ZAuto::WakeLockCore")
                    if not self.wakelock.isHeld():
                        self.wakelock.acquire()

                    # ÉP WIFI KHÔNG ĐƯỢC NGẮT (MỨC 3 - HIGH PERFORMANCE)
                    WifiManager = autoclass('android.net.wifi.WifiManager')
                    wm = cast(WifiManager, PythonActivity.mActivity.getApplicationContext().getSystemService(Context.WIFI_SERVICE))
                    self.wifilock = wm.createWifiLock(3, "ZAuto::WifiLockCore")
                    if not self.wifilock.isHeld():
                        self.wifilock.acquire()

                except Exception as e:
                    logger.error(f"Lỗi cấu hình phần cứng Android: {e}")

        except Exception as e:
            logger.error(f"Lỗi on_start: {traceback.format_exc()}")

    def delayed_ui_startup(self):
        """Hàm bổ sung: Đợi giao diện sẵn sàng rồi mới nạp cấu hình cài đặt (Thụt lề 4 dấu cách)"""
        try:
            self.load_config()
            self.check_license_at_startup()
            self.check_for_update()
            logger.info("Đã nạp thành công cấu hình UI và kiểm tra bản quyền.")
        except Exception as e:
            logger.error(f"Lỗi nạp UI chậm: {e}")
          
    def update_group_list_ui(self, groups):
        """Cập nhật danh sách nhóm từ Zalo Web lên giao diện Tab Nhóm"""
        try:
            group_list_widget = self.root.ids.group_filter_list
            # Lấy danh sách các nhóm hiện đang hiển thị trên màn hình
            current_ui_groups = [item.text for item in group_list_widget.children if hasattr(item, 'text')]
            
            from kivymd.uix.list import OneLineIconListItem, IconLeftWidget
            from kivymd.uix.selectioncontrol import MDSwitch
            from kivy.uix.boxlayout import BoxLayout

            for g_name in groups:
                # Nếu nhóm này chưa có trong giao diện thì mới thêm vào
                if g_name not in current_ui_groups:
                    # Mặc định nhóm mới là BẬT nếu chưa từng lưu trạng thái
                    if g_name not in self.enabled_groups:
                        self.enabled_groups[g_name] = False
                    
                    # Tạo item danh sách
                    item = OneLineIconListItem(text=g_name)
                    
                    # Thêm icon đại diện bên trái cho chuyên nghiệp
                    icon = IconLeftWidget(icon="account-group")
                    item.add_widget(icon)
                    
                    # Tạo công tắc gạt bên phải
                    switcher = MDSwitch(
                        active=self.enabled_groups[g_name],
                        pos_hint={'center_x': .9, 'center_y': .5}
                    )
                    
                    # Gán sự kiện khi tài xế gạt nút
                    # Dùng partial hoặc lambda có gán mặc định để tránh lỗi ghi đè biến name
                    switcher.bind(active=lambda sw, val, name=g_name: self.toggle_group(name, val))
                    
                    item.add_widget(switcher)
                    group_list_widget.add_widget(item)
        except Exception as e:
            print(f"Lỗi update_group_list_ui: {e}")

    def toggle_group(self, name, status):
        """Lưu trạng thái bật/tắt của từng nhóm và thông báo"""
        self.enabled_groups[name] = status
        self.save_config_silent() # Lưu ngay vào file config.json
        
        status_text = "BẬT" if status else "TẮT"
        toast(f"{status_text} nhận cuốc nhóm: {name}")            
    def check_license_at_startup(self):
        m_id = get_machine_id()
        current_time = int(time.time())

        # 1. KIỂM TRA BẢN QUYỀN CHÍNH THỨC (KEY VIP) TRƯỚC
        if os.path.exists(LICENSE_FILE):
            try:
                with open(LICENSE_FILE, 'r') as f:
                    key = f.read().strip()
                ok, expiry = verify_license(key, m_id)
                if ok:
                    if expiry < current_time:
                        self.safe_toast("Phát hiện thời gian hệ thống không chính xác!")
                        self.show_activation_popup()
                        return
                    self.apply_license_ui(expiry)
                    return
            except Exception as e:
                logger.error(f"Lỗi đọc license VIP: {e}")

        # 2. CƠ CHẾ OFFLINE CHỐNG GỠ APP & XÓA DATA ĐỂ RESET 15 NGÀY FREE
        trial_expire = 0

        # Đường dẫn file backup ẩn ở phân vùng dùng chung (Không bị xóa khi gỡ cài đặt app)
        backup_dir = "/sdcard/Android/media/org.zauto.zauto/"
        backup_file = os.path.join(backup_dir, ".sys_secure_node.dat")

        # Đọc dữ liệu dùng thử từ 3 nguồn để đối chiếu chéo (Local App, SharedPreferences, Backup SDCard)
        local_val = None
        shared_val = None
        backup_val = None

        # Nguồn A: Đọc file local của App (Bị xóa khi Clear Data hoặc Gỡ cài đặt)
        if os.path.exists(TRIAL_FILE):
            try:
                with open(TRIAL_FILE, 'r') as f:
                    local_val = self._decrypt_secure_data(f.read().strip(), m_id)
            except: pass

        # Nguồn B: Đọc SharedPreferences hệ thống (Bị xóa khi Gỡ cài đặt nhưng GIỮ LẠI khi Clear Data)
        if platform == 'android':
            try:
                context = PythonActivity.mActivity
                shared_pref = context.getSharedPreferences("ZAutoSecureStore", context.MODE_PRIVATE)
                cipher_shared = shared_pref.getString("secure_token", None)
                if cipher_shared:
                    shared_val = self._decrypt_secure_data(cipher_shared, m_id)
            except: pass

        # Nguồn C: Đọc file ẩn ở phân vùng bộ nhớ chung (GIỮ LẠI TRONG MỌI TRƯỜNG HỢP gỡ app hay xóa data)
        if os.path.exists(backup_file):
            try:
                with open(backup_file, 'r') as f:
                    backup_val = self._decrypt_secure_data(f.read().strip(), m_id)
            except: pass

        # --- LOGIC QUYẾT ĐỊNH ĐỒNG BỘ OFFLINE ---
        # Ưu tiên lấy mốc hết hạn dùng thử nhỏ nhất/cũ nhất từng được lưu để chặn đứng hành vi gia hạn lậu
        valid_trials = []
        for val in [local_val, shared_val, backup_val]:
            if val and val.isdigit():
                valid_trials.append(int(val))

        if valid_trials:
            # Phát hiện đã từng cài app hoặc từng dùng thử: Lấy mốc thời gian dùng thử cũ nhất (an toàn nhất)
            trial_expire = min(valid_trials)
        else:
            # Máy hoàn toàn sạch sẽ (Lần đầu tiên cài app thật sự)
            trial_expire = current_time + (15 * 24 * 3600) # Cấp 15 ngày dùng thử

        # ĐỒNG BỘ NGƯỢC LẠI CẢ 3 NƠI ĐỂ KHÓA CHẶT THIẾT BỊ
        cipher_value = self._encrypt_secure_data(str(trial_expire), m_id)
        
        # Đồng bộ Nguồn A
        try:
            with open(TRIAL_FILE, 'w') as f:
                f.write(cipher_value)
        except: pass

        # Đồng bộ Nguồn B
        if platform == 'android':
            try:
                context = PythonActivity.mActivity
                shared_pref = context.getSharedPreferences("ZAutoSecureStore", context.MODE_PRIVATE)
                editor = shared_pref.edit()
                editor.putString("secure_token", cipher_value)
                editor.commit()
            except: pass

        # Đồng bộ Nguồn C (Tạo thư mục ẩn bộ nhớ chung và ghi file)
        try:
            os.makedirs(backup_dir, exist_ok=True)
            with open(backup_file, 'w') as f:
                f.write(cipher_value)
        except: pass

        # 3. CHỐNG QUAY NGƯỢC THỜI GIAN ĐIỆN THOẠI (TIME-TRAVEL PROTECTION)
        last_runtime = self.config_data.get('last_runtime', 0)
        if current_time < last_runtime:
            self.safe_toast("Phát hiện gian lận đổi ngày giờ điện thoại! Thiết bị đã bị khóa.")
            self.show_activation_popup()
            return
            
        # Cập nhật mốc thời gian chạy app mới nhất
        self.config_data['last_runtime'] = current_time
        self.save_config_silent()

        # 4. KIỂM TRA HẠN DÙNG THỬ
        if trial_expire > current_time:
            self.apply_license_ui(trial_expire, is_trial=True)
        else:
            self.show_activation_popup()
    def _encrypt_secure_data(self, data, key):
        """Mã hóa chuỗi dữ liệu dựa trên mã ANDROID_ID duy nhất của phần cứng"""
        try:
            # Sử dụng SHA256 của key phần cứng làm mật mã XOR
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            encrypted = []
            for i in range(len(data)):
                key_c = key_hash[i % len(key_hash)]
                enc_c = chr(ord(data[i]) ^ ord(key_c))
                encrypted.append(enc_c)
            # Chuyển sang dạng Hex an toàn để ghi file
            return "".join(encrypted).encode('utf-8').hex()
        except:
            return data

    def _decrypt_secure_data(self, hex_data, key):
        """Giải mã chuỗi dữ liệu phần cứng"""
        try:
            data = bytes.fromhex(hex_data).decode('utf-8')
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            decrypted = []
            for i in range(len(data)):
                key_c = key_hash[i % len(key_hash)]
                dec_c = chr(ord(data[i]) ^ ord(key_c))
                decrypted.append(dec_c)
            return "".join(decrypted)
        except:
            return hex_data        

    def apply_license_ui(self, expiry, is_trial=False):
        if expiry > 4000000000:
            type_str, date_str = "VĨNH VIỄN (VIP)", "Không giới hạn"
        else:
            type_str = "DÙNG THỬ (FREE)" if is_trial else "TRẢ PHÍ"
            date_str = time.strftime('%d/%m/%Y', time.localtime(expiry))
        
        # Cập nhật thông tin vào Tab Cài đặt
        self.root.ids.lbl_key_type.text = f"Loại Key: {type_str}"
        self.root.ids.lbl_expiry.text = f"Hết hạn: {date_str}"

    def show_activation_popup(self):
        # Sửa self.m_id thành get_machine_id()
        popup = ActivationPopup(machine_id=get_machine_id(), on_success=self.apply_license_ui, can_cancel=False)
        popup.open()
    def show_activation_popup_from_settings(self):
        # Sửa self.m_id thành get_machine_id()
        popup = ActivationPopup(machine_id=get_machine_id(), on_success=self.apply_license_ui, can_cancel=True)
        popup.open()
    def _message_worker(self):
        while getattr(self, 'app_running', True):
            try:
                action, data = self.msg_queue.get(timeout=1.0)
                if action == 'WEB_NEW_MSG':
                    self._process_heavy_message(data)
                self.msg_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Message Worker Crash: {traceback.format_exc()}")
                time.sleep(1) # Chống CPU Spike khi lỗi liên tục

    def _reply_worker_loop(self):
        while getattr(self, 'app_running', True):
            try:
                reply_payload = self.reply_queue.get(timeout=1.0)
                with self.reply_lock:
                    self._execute_reply_safe(reply_payload)
                self.reply_queue.task_done()
                time.sleep(0.5)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Reply Worker Crash: {traceback.format_exc()}")
                time.sleep(1)
    def _audio_worker_loop(self):
        """Worker tuần tự: Đọc TTS thông báo nhóm → Play tin thoại → Chờ → Tin tiếp theo.
        Mỗi tin chỉ phát 1 lần. Nhiều nhóm/nhiều tin xếp hàng lần lượt không chèn nhau.
        """
        # Đổi set() thành dict() để lưu kèm thời gian nhận tin
        if not hasattr(self, 'audio_seen_dict'):
            self.audio_seen_dict = {}
            
        CACHE_TTL = 3600  # Thời gian sống của tin nhắn thoại trong RAM (3600 giây = 1 tiếng)

        while getattr(self, 'app_running', True):
            try:
                current_ts = time.time()
                
                # BƯỚC DỌN RÁC (GARBAGE COLLECTION): Chỉ xóa các tin đã quá 1 tiếng
                keys_to_delete = [k for k, ts in self.audio_seen_dict.items() if current_ts - ts > CACHE_TTL]
                for k in keys_to_delete:
                    del self.audio_seen_dict[k]

                # Nhận đủ 5 tham số; tương thích ngược với tuple 4 phần tử cũ
                item = self.audio_queue.get(timeout=1.0)
                if len(item) == 5:
                    conv_id, msg_id, cache_key, duration, tts_text = item
                else:
                    conv_id, msg_id, cache_key, duration = item
                    tts_text = ""

                 # Tạo khóa duy nhất chống phát lại
                # Dùng monotonic counter để đảm bảo mỗi item trong queue luôn có key riêng
                if not msg_id or len(msg_id) < 4 or msg_id.startswith("TIME_") or msg_id.startswith("VOICE_"):
                    # Không có ID thật: dùng monotonic time nano để tránh đụng key khi 2 tin < 1 giây
                    audio_unique_key = f"VOICE_{conv_id}_{time.monotonic_ns()}"
                    # Với key dạng này KHÔNG check audio_seen_dict (mỗi item đã unique)
                    skip_seen_check = True
                else:
                    audio_unique_key = f"{conv_id}_{msg_id}"
                    skip_seen_check = False
 
                if not skip_seen_check and audio_unique_key in self.audio_seen_dict:
                    self.audio_queue.task_done()
                    continue  # Đã phát rồi (ID thật trùng), bỏ qua

                # Đánh dấu ngay trước khi phát và ghi lại mốc thời gian
                self.audio_seen_dict[audio_unique_key] = current_ts

                if platform == 'android' and getattr(self, 'is_linked', False):
                    from jnius import autoclass
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    ZWM = autoclass('org.zauto.ZaloWebManager')

                    # BƯỚC 1: Đọc TTS thông báo nhóm trước (đợi xong mới play)
                    if tts_text:
                        try:
                            ZWM.speak(tts_text)
                            time.sleep(3.0)  # Chờ TTS đọc xong ~3s
                        except Exception as e_tts:
                            logger.error(f"TTS speak lỗi: {e_tts}")

                    # BƯỚC 2: Kích nút Play tin thoại trong WebView
                    ZWM.playSpecificAudio(PythonActivity.mActivity, conv_id, msg_id)
                    logger.info(f"AudioWorker: Play {audio_unique_key} (duration={duration}s)")

                    # BƯỚC 3: Chờ đúng thời lượng tin thoại trước khi phát tin tiếp
                    try:
                        wait_time = max(int(duration) + 2.0, 7.0) if int(duration) > 0 else 7.0
                    except:
                        wait_time = 7.0
                    time.sleep(wait_time)

                self.audio_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Audio Worker Crash: {traceback.format_exc()}")
                time.sleep(1)
    def _process_heavy_message(self, data):
        group = data.get('group', '')
        msg = data.get('msg', '')
        msg_id = data.get('msg_id', '')
        conversation_id = data.get('conversation_id', '')

        if not getattr(self, 'is_radar_running', False): return
        if not getattr(self, 'enabled_groups', {}).get(group, False): 
            return

        msg_clean = msg.strip()
        msg_low = msg_clean.lower()
        
        # Tách tên người gửi
        msg_content_only = msg_low
        if ": " in msg_content_only:
            msg_content_only = msg_content_only.split(": ", 1)[1]

        raw_reply = self.config_data.get('reply_msg', 'Ok nhận')
        replies = [r.strip().lower() for r in raw_reply.split(',') if r.strip()]
        
        # Bỏ qua tin do app tự trả lời
        if msg_content_only in replies or any(r in msg_content_only for r in replies):
            return 

        is_voice = (
            "tin nhắn thoại" in msg_low or "audio" in msg_low or 
            "giọng nói" in msg_low or "âm thanh" in msg_low or 
            "voice" in msg_low or "[tin nhắn thoại]" in msg_low
        )
        current_time = time.time()
        sw_filter_active = self.config_data.get('sw_filter', False)

        # ==============================================================
        # 3. CHỐNG SPAM TIN TRÙNG - CHỈ ÁP DỤNG CHO TIN TEXT, KHÔNG CHẶN VOICE
        # ==============================================================
        if not hasattr(self, 'last_msg_per_group'):
            self.last_msg_per_group = {}

        msg_hash = hashlib.md5(msg_clean.encode('utf-8')).hexdigest()[:12]

        # Chỉ kiểm tra trùng lặp cho tin TEXT - voice không áp dụng
        if not is_voice:
            if conversation_id in self.last_msg_per_group:
                last_id, last_hash, last_time = self.last_msg_per_group[conversation_id]
                both_time_fallback = msg_id.startswith("TIME_") and last_id.startswith("TIME_")
                if (msg_id == last_id or both_time_fallback) and msg_hash == last_hash:
                    if time.time() - last_time < 300.0:
                        return # Tin text trùng -> Bỏ qua
        # Voice: chặn trùng lặp cả 2 trường hợp — có ID thật và không có ID thật
        else:
            # msg_id giờ đã có SEQ riêng cho từng node DOM (set từ Java),
            # nên dùng trực tiếp msg_id làm khóa chống trùng — KHÔNG dùng cửa sổ
            # thời gian 5s nữa (cách cũ làm 2 tin thoại liên tiếp cùng duration
            # trong vòng 5s bị coi là 1 tin và bị chặn im lặng).
            voice_key = f"VOICE_FB_{conversation_id}_{msg_id}"
            if voice_key in self.processed_msg_hashes:
                return
            self.processed_msg_hashes[voice_key] = time.time()
            now_ts = time.time()
            stale = [k for k, v in list(self.processed_msg_hashes.items())
                     if k.startswith("VOICE_FB_") and now_ts - v > 120]
            for k in stale:
                self.processed_msg_hashes.pop(k, None)

        # Luôn cập nhật mốc mới nhất (cả voice lẫn text)
        self.last_msg_per_group[conversation_id] = (msg_id, msg_hash, time.time())

        # ==============================================================
        # ✅ PHÂN LUỒNG XỬ LÝ (VOICE / TEXT) SAU KHI ĐÃ LỌC SẠCH BÓNG ĐÈ
        # ==============================================================
        
        # Tạo khóa Cache cho UI (Để sau này chốt xong biết đường mà xóa)
        cache_key = f"CACHE_{conversation_id}_{msg_hash}"

        if is_voice:
            duration = -1 
            if "%%%" in msg:
                try: duration = int(msg.split("%%%")[1])
                except: pass
            display_msg = "🔊 CÓ BẢN GHI ÂM MỚI"

            # Tạo nội dung TTS thông báo để đưa vào audio_queue — phát tuần tự
            sender_name = msg_clean.split(": ")[0].strip() if ": " in msg_clean else ""
            clean_group = re.sub(r'[^\w\s]', '', group)
            clean_sender = re.sub(r'[^\w\s]', '', sender_name) if sender_name else ""
            tts_text = ""
            if self.config_data.get('sw_voice', True):
                tts_text = f"Có tin nhắn thoại của {clean_sender}, từ nhóm {clean_group}" if clean_sender else f"Có tin nhắn thoại từ nhóm {clean_group}"

            if platform == 'android':
                try:
                    # Đưa cả TTS + lệnh play vào cùng 1 queue để xử lý tuần tự
                    self.audio_queue.put(
                        (conversation_id, msg_id, cache_key, duration, tts_text),
                        timeout=0.5
                    )
                except queue.Full:
                    logger.warning(f"Audio queue đầy, bỏ qua tin thoại nhóm {group}")
            try:
                self.ui_queue.put_nowait(('add_ride', (group, display_msg, msg_id, conversation_id, cache_key, msg)))
                self.ui_queue.put_nowait(('log', (group, display_msg)))
                # KHÔNG dùng ('speak',...) ở đây nữa — TTS đã đưa vào audio_queue phát tuần tự
            except queue.Full: pass
            return

        else:
            # --- 💬 LUỒNG TEXT ---
            if sw_filter_active:
                # BƯỚC 1: Loại bỏ tin chứa từ khóa BỎ QUA
                loai_keys = [k.strip() for k in self.config_data.get('loai', '').lower().split(',') if k.strip()]
                if loai_keys and any(lk in msg_content_only for lk in loai_keys):
                    return # Chứa từ khóa bỏ qua -> Loại

                nhan_keys = [k.strip() for k in self.config_data.get('nhan', '').lower().split(',') if k.strip()]
                if nhan_keys and not any(nk in msg_content_only for nk in nhan_keys):
                    return # Có từ khóa nhận nhưng tin không khớp -> Bỏ qua

            # ✅ Vượt qua Filter -> Nổ Canh me
            display_msg = msg
            try:
                self.ui_queue.put_nowait(('add_ride', (group, display_msg, msg_id, conversation_id, cache_key, msg)))
                self.ui_queue.put_nowait(('log', (group, display_msg)))
                
                if self.config_data.get('sw_voice', True):
                    clean_group = re.sub(r'[^\w\s]', '', group)
                    self.ui_queue.put_nowait(('speak', f"Chú ý có cuốc xe mới từ nhóm {clean_group}"))
            except queue.Full: pass

            # 🚗 AUTO CHỐT
            sw_auto_active = self.config_data.get('sw_auto', False)
            if sw_auto_active:
                final_reply = random.choice(replies) if replies else "Ok nhận"
                self.queue_reply(group, conversation_id, msg_id, final_reply, display_msg)
                
                # BỔ SUNG: Gửi lệnh xóa ngay thẻ cuốc xe này khỏi Tab Canh me dựa vào cache_key
                try:
                    self.ui_queue.put_nowait(('remove_by_key', cache_key))
                except queue.Full: pass

    def _system_watchdog(self, dt):
        """Khôi phục Worker, Tối ưu RAM, chặn nhân bản Thread và kiểm tra Node.js"""
        self.gc_counter += 1
        if self.gc_counter % 10 == 0:
            try: gc.collect(2)
            except: pass

        if not getattr(self, 'app_running', False): return

        # KIỂM TRA NODE.JS CÒN SỐNG KHÔNG — tự restart nếu chết
        try:
            urllib.request.urlopen("http://127.0.0.1:5000/health", timeout=2)
        except Exception:
            logger.warning("Node.js không phản hồi — đang restart...")
            threading.Thread(target=self.start_node_server, daemon=True).start()

        with self.worker_restart_lock:
            if not hasattr(self, 'msg_worker_thread') or not self.msg_worker_thread.is_alive():
                if not getattr(self, '_restarting_msg_worker', False):
                    self._restarting_msg_worker = True
                    self.msg_worker_thread = threading.Thread(target=self._message_worker, daemon=True)
                    self.msg_worker_thread.start()
                    self._restarting_msg_worker = False

            if not hasattr(self, 'reply_worker_thread') or not self.reply_worker_thread.is_alive():
                if not getattr(self, '_restarting_reply_worker', False):
                    self._restarting_reply_worker = True
                    self.reply_worker_thread = threading.Thread(target=self._reply_worker_loop, daemon=True)
                    self.reply_worker_thread.start()
                    self._restarting_reply_worker = False

            # THÊM: Kiểm tra audio_worker — cũng cần sống liên tục
            if not hasattr(self, 'audio_worker_thread') or not self.audio_worker_thread.is_alive():
                self.audio_worker_thread = threading.Thread(target=self._audio_worker_loop, daemon=True)
                self.audio_worker_thread.start()
                logger.warning("audio_worker đã được restart")
    def log_history(self, group, msg):
        # Dùng List chuẩn Material của KivyMD
        item = TwoLineAvatarIconListItem(text=f"[{time.strftime('%H:%M')}] {group}", secondary_text=msg)
        item.add_widget(ImageLeftWidget(source="profile.jpg"))
        self.root.ids.msg_history_list.add_widget(item, index=0)

    def remove_ride(self, card_widget):
        try:
            if hasattr(card_widget, 'unbind'): card_widget.unbind()
            card_widget.clear_widgets()
            self.root.ids.ride_list.remove_widget(card_widget)
            try: del card_widget
            except: pass
        except Exception as e:
            logger.error(f"Lỗi remove_ride: {e}")
    def _poll_java_queue(self, dt):
        if platform == 'android':
            try:
                from jnius import autoclass
                ZaloWebManager = autoclass('org.zauto.ZaloWebManager')
                
                # Rút tin nhắn liên tục từ RAM Java
                while not ZaloWebManager.pythonMsgQueue.isEmpty():
                    raw_msg = ZaloWebManager.pythonMsgQueue.poll()
                    if not raw_msg: continue
                    
                    parts = raw_msg.split("|||")
                    action = parts[0]
                    
                    if action == 'LOGIN_SUCCESS':
                        # --- TÍCH HỢP ĐÓN LỆNH HYBRID VISION (ĐÃ FIX LỖI CHỤP MÀN HÌNH) ---
                        if len(parts) > 1 and parts[1] == 'TRIGGER_VISION_FALLBACK':
                            quote_msgId = parts[2] if len(parts) > 2 else ""
                            
                            # FIX 1: BẮT BUỘC CHUYỂN SANG TAB ZALO ĐỂ WEBVIEW HIỆN LÊN MÀN HÌNH
                            Clock.schedule_once(lambda dt: self.root.ids.bottom_nav.switch_tab('tab_zalo'), 0)
                            
                            def execute_vision_engine(dt):
                                screenshot_file = "/data/data/org.zauto.zauto/files/screen_vision.png"
                                if platform == 'android':
                                    # Chụp ảnh khi màn hình Zalo đã hiển thị
                                    os.system(f"screencap -p {screenshot_file}")
                                    vision_engine = ZAutoHybridVisionEngine()
                                    success = vision_engine.process_screenshot_and_double_click(screenshot_file)
                                    
                                    if success:
                                        logger.info("Chốt cuốc thành công bằng Vision Engine!")
                                    else:
                                        logger.error("Vision Engine: Không tìm thấy bong bóng Zalo!")
                            
                            # Đợi 1.2 giây để Android vẽ xong giao diện Zalo Web rồi mới chụp ảnh
                            Clock.schedule_once(execute_vision_engine, 1.2)
                            continue # Thoát luồng, không chạy lệnh Login bên dưới

                        # --- XỬ LÝ CÁC TIN NỘI BỘ TỪ CHỐT CUỐC ---
                        zalo_name = parts[1] if len(parts) > 1 else ""
                        if zalo_name in ('Chốt API QUOTE OK', 'Chốt DOM UI QUOTE OK', 'Đã chốt xong:'):
                            # Java xác nhận gửi thật → báo thành công lúc này mới đúng
                            self.safe_toast("✅ Chốt cuốc thành công!")
                            if self.config_data.get('sw_voice', True):
                                try:
                                    self.ui_queue.put_nowait(('speak', "Chốt cuốc xe thành công"))
                                except: pass
                            continue
                        # 'Đã kết nối' = JS inject xong → cập nhật trạng thái liên kết Zalo
                        if zalo_name == 'Đã kết nối':
                            if not self.is_linked:
                                self.is_linked = True
                                self.config_data['is_linked'] = True
                                # Nếu chưa có tên thật thì đặt tên tạm để không hiện "Chưa kết nối"
                                if self.config_data.get('zalo_name', 'Chưa kết nối Zalo') == 'Chưa kết nối Zalo':
                                    self.config_data['zalo_name'] = 'Đã kết nối Zalo Web'
                                self.save_config_silent()
                                Clock.schedule_once(lambda dt: self.update_profile_ui(), 0)
                            continue

                        # --- LOGIC LOGIN THẬT SỰ ---
                        self.is_linked = True
                        zalo_avatar = parts[2] if len(parts) > 2 else ""
                        if zalo_name: self.config_data['zalo_name'] = zalo_name
                        if zalo_avatar: self.config_data['zalo_avatar'] = zalo_avatar
                        self.save_config_silent()
                        Clock.schedule_once(lambda dt: self.update_profile_ui(), 0)
                        
                        # Chống spam Toast mỗi khi reload/kết nối lại
                        if not getattr(self, '_login_toasted', False):
                            self._login_toasted = True
                            self.safe_toast("Đã liên kết Zalo Web thành công!")
                            
                    elif action == 'ZALO_LOGOUT':
                        self._login_toasted = False  # Đặt lại cờ để lần sau đăng nhập sẽ hiện Toast
                        self.is_linked = False
                        self.config_data['is_linked'] = False
                        self.config_data['zalo_name'] = 'Chưa kết nối Zalo'
                        self.save_config_silent()
                        Clock.schedule_once(lambda dt: self.update_profile_ui(), 0)
                        self.safe_toast("Zalo đã đăng xuất! Vui lòng quét QR lại.")    
                    elif action == 'GROUPS_DATA':
                        groups_json = parts[1] if len(parts) > 1 else ""
                        if groups_json:
                            try:
                                groups = json.loads(groups_json)
                                # FIX CHÍ MẠNG: Ép Kivy vẽ và nổ danh sách nhóm trên Luồng UI chính (Main Thread)
                                Clock.schedule_once(lambda dt, g=groups: self.update_group_list_ui(g), 0)
                            except Exception as e:
                                logger.error(f"GROUPS_DATA Error: {e}")
                                
                    elif action == 'WEB_NEW_MSG':
                        group = parts[1] if len(parts) > 1 else ""
                        msg = parts[2] if len(parts) > 2 else ""
                        msg_id = parts[3] if len(parts) > 3 else ""
                        conv_id = parts[4] if len(parts) > 4 else ""
                        
                        if group and msg:
                            # ĐƠN GIẢN HÓA: Đẩy dữ liệu vào hàng đợi xử lý tuần tự
                            payload = {'group': group, 'msg': msg, 'msg_id': msg_id, 'conversation_id': conv_id}
                            try:
                                self.msg_queue.put(('WEB_NEW_MSG', payload), timeout=0.3)
                            except queue.Full: pass
            except Exception as e:
                pass # Bỏ qua lỗi jnius khi khởi động
    def _node_poll_worker(self):
        """Worker đọc dữ liệu LOGIN_SUCCESS/GROUPS_DATA/WEB_NEW_MSG từ Node.js server.js (port 5000)"""
        import urllib.request, json as _json
        while getattr(self, 'app_running', True):
            try:
                req = urllib.request.urlopen("http://127.0.0.1:5000/api/events", timeout=3)
                data = _json.loads(req.read().decode('utf-8'))
                events = data.get('events', [])
                for ev in events:
                    action = ev.get('action', '')
                    payload = ev.get('data', {})

                    if action == 'LOGIN_SUCCESS':
                        self.is_linked = True
                        zalo_name = payload.get('name', '')
                        zalo_avatar = payload.get('avatar', '')
                        if zalo_name: self.config_data['zalo_name'] = zalo_name
                        if zalo_avatar: self.config_data['zalo_avatar'] = zalo_avatar
                        self.save_config_silent()
                        Clock.schedule_once(lambda dt: self.update_profile_ui(), 0)
                        if not getattr(self, '_login_toasted', False):
                            self._login_toasted = True
                            self.safe_toast("Đã liên kết Zalo (Node.js) thành công!")

                    elif action == 'GROUPS_DATA':
                        groups = payload.get('groups', [])
                        group_names = [g.get('name', '') for g in groups if g.get('name')]
                        if group_names:
                            Clock.schedule_once(lambda dt, g=group_names: self.update_group_list_ui(g), 0)

                    elif action == 'WEB_NEW_MSG':
                        group   = payload.get('group_name', '')
                        msg     = payload.get('text', '')
                        msg_id  = payload.get('msg_id', '')
                        conv_id = payload.get('group_id', '')
                        if group and msg:
                            ev_payload = {
                                'group': group, 'msg': msg,
                                'msg_id': msg_id, 'conversation_id': conv_id
                            }
                            try:
                                self.msg_queue.put(('WEB_NEW_MSG', ev_payload), timeout=0.3)
                            except queue.Full: pass
 
                    elif action == 'WEB_NEW_VOICE':
                        # Node.js gửi tin thoại kèm URL file — cần đánh dấu rõ là VOICE
                        group       = payload.get('group_name', '')
                        voice_url   = payload.get('voice_url', '')
                        msg_id      = payload.get('msg_id', '')
                        conv_id     = payload.get('group_id', '')
                        sender_name = payload.get('sender_name', '')
                        # raw_data để gửi quote đúng chuẩn Zalo API
                        raw_data    = payload.get('raw_data', {})
                        duration    = -1
                        try:
                            # propertyExt có thể chứa "duration":30
                            prop = raw_data.get('propertyExt', {})
                            if isinstance(prop, dict):
                                duration = int(prop.get('duration', -1))
                        except: pass
 
                        if group and voice_url:
                            # Tạo msg chuẩn để _process_heavy_message nhận ra là VOICE
                            prefix = f"{sender_name}: " if sender_name else ""
                            msg = f"{prefix}[Tin nhắn thoại]%%%{duration}"
                            ev_payload = {
                                'group': group, 'msg': msg,
                                'msg_id': msg_id, 'conversation_id': conv_id,
                                'is_voice': True, 'voice_url': voice_url,
                                'raw_data': raw_data
                            }
                            try:
                                self.msg_queue.put(('WEB_NEW_MSG', ev_payload), timeout=0.3)
                            except queue.Full: pass
 
                    elif action == 'WEB_NEW_PHOTO':
                        group   = payload.get('group_name', '')
                        msg_id  = payload.get('msg_id', '')
                        conv_id = payload.get('group_id', '')
                        # Ảnh: chỉ hiển thị thẻ, không auto-chốt
                        if group:
                            ev_payload = {
                                'group': group,
                                'msg': '[Hình ảnh]',
                                'msg_id': msg_id,
                                'conversation_id': conv_id
                            }
                            try:
                                self.msg_queue.put(('WEB_NEW_MSG', ev_payload), timeout=0.3)
                            except queue.Full: pass

                    elif action == 'LOGIN_ERROR':
                        logger.error(f"Node LOGIN_ERROR: {payload.get('error','')}")

            except Exception as e:
                pass  # Bỏ qua lỗi khi Node chưa kịp khởi động hoặc mạng tạm gián đoạn

            time.sleep(1.5)

    def _java_poll_worker(self):
        """Worker cào dữ liệu từ Java ngầm 24/24 và kiêm luôn Báo thức Zalo"""
        tick_count = 0
        while getattr(self, 'app_running', True):
            try:
                # 1. Hút tin nhắn từ Java về liên tục
                self._poll_java_queue(None)
                
                # 2. BÁO THỨC ZALO & NUÔI WATCHDOG (Chống ngâm tin 5 phút)
                tick_count += 1
                if tick_count >= 10:  # Cứ 2 giây (10 vòng * 0.2s) châm kim 1 lần
                    tick_count = 0
                    if platform == 'android' and getattr(self, 'is_linked', False):
                        try:
                            from jnius import autoclass
                            mgr = autoclass('org.zauto.ZaloWebManager')
                            # Ép Zalo quẹt chuột ảo chống ngủ đông core
                            mgr.forceWakeup()
                            
                            # BƠM NHỊP TIM GIẢ: Ngăn Java reload trang khi ẩn nền
                            System = autoclass('java.lang.System')
                            mgr.lastHeartbeat = System.currentTimeMillis()
                        except:
                            pass
            except Exception:
                pass
            
            # Quét tốc độ cao 0.2s/lần
            time.sleep(0.2)            

    def add_ride_card(self, group, msg, msg_id="", conversation_id="", cache_key="", raw_msg=""):
        try:
            max_rides = 30
            ride_list = self.root.ids.ride_list
            while len(ride_list.children) >= max_rides:
                old_card = ride_list.children[-1]
                ride_list.remove_widget(old_card)
                old_card.clear_widgets()
                del old_card
            card = RideCard(group_text=group, msg_text=msg, time_text=time.strftime("%H:%M"))
            card.msg_id = msg_id
            card.conversation_id = conversation_id
            card.cache_key = cache_key # ĐÃ FIX: Nhận tham số cache_key để sau này xóa bộ đệm
            card.raw_msg = raw_msg if raw_msg else msg  # Nội dung gốc để Java tìm đúng tin click đúp
            self.root.ids.ride_list.add_widget(card, index=0)
            
            # TỰ XÓA CUỐC SAU 2 PHÚT (120 GIÂY) ĐỂ MÀN HÌNH CANH ME SẠCH SẼ
            Clock.schedule_once(lambda dt: self.auto_remove_card(card), 120)
        except Exception: logger.error(traceback.format_exc())

    def auto_remove_card(self, card_widget):
        try:
            if card_widget in self.root.ids.ride_list.children:
                self.remove_ride(card_widget)
        except Exception: pass

    def manual_accept_ride(self, card_widget):
        # Ẩn bàn phím TRƯỚC KHI CHỐT — tránh IME bật lên khi JS điền text vào input
        if platform == 'android':
            try:
                from jnius import autoclass as _ac
                _ac('org.zauto.ZaloWebManager').hideKeyboard(
                    _ac('org.kivy.android.PythonActivity').mActivity
                )
            except: pass

        raw_reply = self.root.ids.inp_reply.text
        replies = [r.strip() for r in raw_reply.split(',') if r.strip()]
        final_reply = random.choice(replies) if replies else "Ok nhận"

        self.queue_reply(
            card_widget.group_text,
            getattr(card_widget, 'conversation_id', ''),
            getattr(card_widget, 'msg_id', ''),
            final_reply,
            getattr(card_widget, 'raw_msg', card_widget.msg_text),
            force_manual=True
        )
        toast(f"Đang chốt: {card_widget.group_text}")
        self.remove_ride(card_widget)

    def queue_reply(self, group, conversation_id, msg_id, reply_text, msg_content="", force_manual=False):
        now = time.time()
        try:
            user_delay = float(self.config_data.get('global_delay', '30'))
        except:
            user_delay = 30.0

        # Chỉ kiểm tra delay khi là auto chốt, bấm tay thì luôn cho qua
        if not force_manual:
            with self.reply_time_lock:
                time_passed = now - getattr(self, 'last_global_reply_time', 0)
                if time_passed < user_delay:
                    return 
                self.last_global_reply_time = now

        cache_key = f"{conversation_id}_{msg_id}_{hashlib.md5(reply_text.encode('utf-8')).hexdigest()[:6]}"
        if now - self.last_reply_time.get(cache_key, 0) < 10: return 
        self.last_reply_time[cache_key] = now

        if self.reply_queue.qsize() > 40: return
        
        try:
            self.reply_queue.put({
                'group': group, 
                'conversation_id': conversation_id, 
                'msg_id': msg_id, 
                'reply_text': reply_text, 
                'msg_content': msg_content,
                'group_name': group
            }, timeout=0.3)
            
            # Thông báo cho người dùng
            self.safe_toast(f"⏳ Đang gửi vào nhóm {group}...")
            
            # Xử lý giọng nói
            if self.config_data.get('sw_voice', True):
                try:
                    # Đảm bảo regex không chứa ký tự lạ gây lỗi bộ giải mã giọng nói
                    clean_group_name = re.sub(r'[^\w\s]', '', str(group))
                    self.ui_queue.put_nowait(('speak', f"Đang chốt nhóm {clean_group_name}"))
                except Exception as e:
                    logging.error(f"Lỗi giọng nói: {e}")
                    pass
        except queue.Full:
            pass

    def _execute_reply_safe(self, payload):
        """
        CHỐT CUỐC ÂM THẦM (KHÔNG NHẢY TAB):
        - KHÔNG switch_tab nữa — WebView Java tự đưa mình vào vị trí ẩn (0,0 alpha=0.01)
          để chạy JS click/quote, không cần Tab Zalo hiện diện trên UI.
        - jnius chỉ được gọi từ đúng 1 background thread, không bao giờ từ UI thread trực tiếp.
        """
        if platform != 'android' or not getattr(self, 'is_linked', False):
            return

        def _bg_send():
            try:
                from jnius import autoclass as _ac
                _PA = _ac('org.kivy.android.PythonActivity')
                _ZWM = _ac('org.zauto.ZaloWebManager')
                _act = _PA.mActivity

                try:
                    _ZWM.hideKeyboard(_act)
                except Exception as ek:
                    logger.warning(f"hideKeyboard lỗi: {ek}")

                _ZWM.sendReplyToSpecificMessage(
                    _act,
                    payload.get('conversation_id', ''),
                    payload.get('msg_id', ''),
                    payload.get('reply_text', ''),
                    payload.get('msg_content', ''),
                    time.strftime('%H:%M')
                )
                logger.info(f"[CHOT] Đã gửi lệnh cho nhóm: {payload.get('group', '')}")

            except Exception as e_bg:
                logger.error(f"Lỗi _bg_send: {traceback.format_exc()}")

        import threading
        threading.Thread(target=_bg_send, daemon=True).start()
 
    
    def load_config(self):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=15.0, isolation_level=None)
            c = conn.cursor()
            c.execute("SELECT key_name, value_data FROM config")
            rows = c.fetchall()
            conn.close()

            # Đặt khung mặc định an toàn trước
            self.config_data = {
                'nhan': '', 'loai': '', 'reply_msg': 'Ok nhận',
                'sw_filter': False, 'sw_auto': False, 'is_linked': False, 
                'enabled_groups': {}, 'zalo_name': 'Chưa kết nối Zalo', 'zalo_avatar': 'profile.jpg'
            }
            # Nếu có data từ DB thì đè lên
            if rows:
                for k, v in rows: 
                    self.config_data[k] = json.loads(v)

            self.is_linked = self.config_data.get('is_linked', False)
            self.enabled_groups = self.config_data.get('enabled_groups', {})

            # ─────────────────────────────────────────────────────────────────
            # XOÁ LỖI TỪ GỐC: Nếu giao diện chưa dựng xong, thoát sớm để tránh crash .ids
            # ─────────────────────────────────────────────────────────────────
            if not getattr(self, 'root', None) or self.root is None:
                logger.info("Cấu hình đã nạp vào bộ nhớ đệm ngầm (Giao diện UI sẽ cập nhật sau).")
                return

            ids = self.root.ids
            if ids.get('inp_nhan'): ids.inp_nhan.text = self.config_data.get('nhan', '')
            if ids.get('inp_loai'): ids.inp_loai.text = self.config_data.get('loai', '')
            if ids.get('inp_reply'): ids.inp_reply.text = self.config_data.get('reply_msg', 'Ok nhận')
            if ids.get('inp_delay'): ids.inp_delay.text = self.config_data.get('global_delay', '30')
            if ids.get('sw_filter'): ids.sw_filter.active = self.config_data.get('sw_filter', False)
            
            # --- THÊM DÒNG LOAD TRẠNG THÁI NÚT GIỌNG NÓI ---
            if ids.get('sw_voice'): ids.sw_voice.active = self.config_data.get('sw_voice', True)
            
            is_auto = self.config_data.get('sw_auto', False)
            if ids.get('sw_auto_settings'): ids.sw_auto_settings.active = is_auto

            self.update_profile_ui()
            if self.enabled_groups:
                Clock.schedule_once(lambda dt: self.update_group_list_ui(self.enabled_groups.keys()), 0)
        except Exception as e:
            logger.error(f"Lỗi SQLite Load: {e}")

    def save_config_silent(self):
        try:
            with db_lock:
                conn = sqlite3.connect(DB_PATH, timeout=15.0, isolation_level=None)
                c = conn.cursor()
                for k, v in self.config_data.items():
                    c.execute("INSERT OR REPLACE INTO config (key_name, value_data) VALUES (?, ?)", (k, json.dumps(v)))
                conn.close()
        except Exception as e:
            logger.error(f"Lỗi SQLite Save: {e}")
    

    def update_profile_ui(self):
        try:
            ids = self.root.ids
            
            if 'zalo_name_view' in ids:
                ids.zalo_name_view.text = self.config_data.get('zalo_name', "Đã kết nối") if self.is_linked else "Chưa kết nối Zalo"

            if 'zalo_avatar_view' in ids:
                ids.zalo_avatar_view.source = self.config_data.get('zalo_avatar', 'profile.jpg') if self.is_linked else 'profile.jpg'

            if 'btn_zalo_action' in ids:
                ids.btn_zalo_action.text = "HUỶ LIÊN KẾT ZALO" if self.is_linked else "LIÊN KẾT ZALO NGAY"
                ids.btn_zalo_action.md_bg_color = (0.8, 0.2, 0.2, 1) if self.is_linked else (0.1, 0.5, 0.8, 1)
        except Exception as e:
            print(f"Lỗi UI Profile: {e}")

    # =====================================================================
    # DEEP CHECK — TỰ CHẨN ĐOÁN TOÀN BỘ APP (12 BƯỚC) + TỰ THỬ KHẮC PHỤC NHẸ
    # Chạy hoàn toàn ở background thread, KHÔNG làm treo UI.
    # Mọi bước đều test TRẠNG THÁI THẬT (không bịa), ghi log rõ PASS/FAIL/FIXED.
    # =====================================================================
    def run_system_diagnostics(self):
        if getattr(self, '_diag_running', False):
            toast("Đang kiểm tra rồi, vui lòng đợi...")
            return
        self._diag_running = True

        try:
            ids = self.root.ids
            if 'btn_run_diagnostics' in ids:
                ids.btn_run_diagnostics.disabled = True
                ids.btn_run_diagnostics.text = "ĐANG KIỂM TRA... (15-30s)"
            if 'lbl_diag_status' in ids:
                ids.lbl_diag_status.text = "🔄 Đang chạy Deep Check..."
        except Exception:
            pass

        threading.Thread(target=self._diagnostics_worker, daemon=True).start()

    def _diag_line(self, lines, ok, label, detail=""):
        """Thêm 1 dòng log chuẩn hoá PASS/FAIL/WARN/FIXED vào danh sách kết quả."""
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "FIXED": "🔧", "INFO": "ℹ️"}.get(ok, "•")
        line = f"{icon} [{ok}] {label}"
        if detail:
            line += f" — {detail}"
        lines.append(line)
        try:
            logger.info(f"[DIAG] {line}")
        except Exception:
            pass

    def _diagnostics_worker(self):
        """Chạy toàn bộ 12 bước kiểm tra thật trong background thread."""
        lines = []
        fail_count = 0
        warn_count = 0
        fixed_count = 0

        def mark(ok, label, detail=""):
            nonlocal fail_count, warn_count, fixed_count
            if ok == "FAIL":
                fail_count += 1
            elif ok == "WARN":
                warn_count += 1
            elif ok == "FIXED":
                fixed_count += 1
            self._diag_line(lines, ok, label, detail)

        lines.append("=" * 50)
        lines.append(f"  ZAUTO VIP — DEEP CHECK — {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 50)

        # ---------------------------------------------------------------
        # BƯỚC 1: Trạng thái Radar (đang canh me hay không)
        # ---------------------------------------------------------------
        try:
            if getattr(self, 'is_radar_running', False):
                mark("PASS", "Radar canh me", "đang chạy")
            else:
                mark("WARN", "Radar canh me", "đang TẮT — app sẽ không nhận tin mới")
        except Exception as e:
            mark("FAIL", "Radar canh me", str(e))

        # ---------------------------------------------------------------
        # BƯỚC 2: Trạng thái liên kết Zalo
        # ---------------------------------------------------------------
        try:
            if getattr(self, 'is_linked', False):
                mark("PASS", "Liên kết Zalo", "đã liên kết")
            else:
                mark("FAIL", "Liên kết Zalo", "CHƯA liên kết — quét QR hoặc đăng nhập lại")
        except Exception as e:
            mark("FAIL", "Liên kết Zalo", str(e))

        # ---------------------------------------------------------------
        # BƯỚC 3: Nhóm đang bật theo dõi
        # ---------------------------------------------------------------
        try:
            enabled = [g for g, v in getattr(self, 'enabled_groups', {}).items() if v]
            if enabled:
                mark("PASS", "Nhóm đang theo dõi", f"{len(enabled)} nhóm")
            else:
                mark("WARN", "Nhóm đang theo dõi", "0 nhóm đang bật — vào tab Nhóm để bật")
        except Exception as e:
            mark("FAIL", "Nhóm đang theo dõi", str(e))

        # ---------------------------------------------------------------
        # BƯỚC 4: Các luồng worker (thread) có còn sống không
        # ---------------------------------------------------------------
        worker_map = {
            'msg_worker_thread': "Luồng xử lý tin nhắn",
            'reply_worker_thread': "Luồng gửi chốt cuốc",
            'audio_worker_thread': "Luồng phát tin thoại",
            'poll_worker_thread': "Luồng đọc dữ liệu Java",
            'node_poll_worker_thread': "Luồng đọc dữ liệu Node.js",
        }
        for attr, label in worker_map.items():
            try:
                th = getattr(self, attr, None)
                if th is not None and th.is_alive():
                    mark("PASS", label, "đang chạy")
                else:
                    mark("FAIL", label, "ĐÃ CHẾT — cần khởi động lại app")
            except Exception as e:
                mark("FAIL", label, str(e))

        # ---------------------------------------------------------------
        # BƯỚC 5: Hàng đợi (queue) có bị nghẽn không
        # ---------------------------------------------------------------
        queue_map = {
            'msg_queue': ("Hàng đợi tin nhắn", 500),
            'reply_queue': ("Hàng đợi chốt cuốc", 50),
            'ui_queue': ("Hàng đợi cập nhật UI", 100),
            'audio_queue': ("Hàng đợi tin thoại", 50),
        }
        for attr, (label, maxsize) in queue_map.items():
            try:
                q = getattr(self, attr, None)
                if q is None:
                    mark("FAIL", label, "không tồn tại")
                    continue
                size = q.qsize()
                if size >= maxsize * 0.9:
                    mark("WARN", label, f"gần đầy ({size}/{maxsize}) — có thể bị nghẽn")
                else:
                    mark("PASS", label, f"{size}/{maxsize}")
            except Exception as e:
                mark("FAIL", label, str(e))

        # ---------------------------------------------------------------
        # BƯỚC 6: Node.js backend (server.js) — process còn sống?
        # ---------------------------------------------------------------
        node_alive = False
        try:
            proc = getattr(self, 'node_process', None)
            if proc is not None and proc.poll() is None:
                node_alive = True
                mark("PASS", "Tiến trình Node.js", f"PID={proc.pid} đang sống")
            elif proc is not None:
                mark("FAIL", "Tiến trình Node.js", f"ĐÃ CHẾT (exit code={proc.returncode})")
            else:
                mark("WARN", "Tiến trình Node.js", "chưa có thông tin process (có thể đang dùng kiến trúc Java WebView thuần)")
        except Exception as e:
            mark("FAIL", "Tiến trình Node.js", str(e))

        # ---------------------------------------------------------------
        # BƯỚC 7: Node.js — thử gọi thật /health và /api/events
        # ---------------------------------------------------------------
        try:
            import urllib.request
            req = urllib.request.urlopen("http://127.0.0.1:5000/health", timeout=3)
            if req.status == 200:
                mark("PASS", "Node.js /health", "phản hồi HTTP 200")
            else:
                mark("WARN", "Node.js /health", f"phản hồi mã {req.status}")
        except Exception as e:
            if node_alive:
                mark("FAIL", "Node.js /health", f"process sống nhưng KHÔNG phản hồi HTTP: {e}")
            else:
                mark("WARN", "Node.js /health", "không phản hồi (process không chạy, có thể đang dùng kiến trúc Java thuần)")

        try:
            import urllib.request, json as _json
            req = urllib.request.urlopen("http://127.0.0.1:5000/api/events", timeout=3)
            _json.loads(req.read().decode('utf-8'))
            mark("PASS", "Node.js /api/events", "trả JSON hợp lệ")
        except Exception as e:
            mark("WARN", "Node.js /api/events", f"không đọc được: {e}")

        # ---------------------------------------------------------------
        # BƯỚC 8: WebView Java — đã khởi tạo chưa, còn null không
        # ---------------------------------------------------------------
        webview_ok = False
        if platform == 'android':
            try:
                from jnius import autoclass
                ZWM = autoclass('org.zauto.ZaloWebManager')
                if not getattr(self, 'webview_inited', False):
                    mark("WARN", "WebView ẩn (ZaloWebManager)", "chưa khởi tạo — mở tab Zalo 1 lần để khởi tạo")
                elif ZWM.hiddenWebView is None:
                    mark("FAIL", "WebView ẩn (ZaloWebManager)", "đã khởi tạo nhưng hiddenWebView đang NULL")
                    # TỰ THỬ KHẮC PHỤC: gọi lại initWebView
                    try:
                        PA = autoclass('org.kivy.android.PythonActivity')
                        ZWM.initWebView(PA.mActivity)
                        mark("FIXED", "WebView ẩn (ZaloWebManager)", "đã thử gọi lại initWebView()")
                    except Exception as e_fix:
                        mark("FAIL", "Tự khắc phục WebView", str(e_fix))
                else:
                    webview_ok = True
                    mark("PASS", "WebView ẩn (ZaloWebManager)", "đã khởi tạo, hiddenWebView tồn tại")
            except Exception as e:
                mark("FAIL", "WebView ẩn (ZaloWebManager)", str(e))
        else:
            mark("INFO", "WebView ẩn (ZaloWebManager)", "bỏ qua — đang chạy trên PC, không phải Android")

        # ---------------------------------------------------------------
        # BƯỚC 9: Heartbeat Java — JS observer còn sống không (qua selfDiagnose)
        # ---------------------------------------------------------------
        if platform == 'android' and webview_ok:
            try:
                from jnius import autoclass
                ZWM = autoclass('org.zauto.ZaloWebManager')
                last_hb = ZWM.lastHeartbeat
                age_sec = (int(time.time() * 1000) - int(last_hb)) / 1000.0
                if age_sec < 25:
                    mark("PASS", "Heartbeat JS sidebar observer", f"{age_sec:.1f}s trước")
                elif age_sec < 60:
                    mark("WARN", "Heartbeat JS sidebar observer", f"{age_sec:.1f}s trước — hơi cũ")
                else:
                    mark("FAIL", "Heartbeat JS sidebar observer", f"{age_sec:.1f}s trước — JS có thể đã chết")
                    # TỰ THỬ KHẮC PHỤC: reload webview
                    try:
                        ZWM.safeReload()
                        mark("FIXED", "Heartbeat JS sidebar observer", "đã gọi safeReload() để khởi động lại JS")
                    except Exception as e_fix:
                        mark("FAIL", "Tự khắc phục Heartbeat", str(e_fix))
            except Exception as e:
                mark("FAIL", "Heartbeat JS sidebar observer", str(e))

        # ---------------------------------------------------------------
        # BƯỚC 10: Self-diagnose chi tiết từ JS (zMessenger API + tìm node tin cuối +
        # thử double-click thật trên tin cuối cùng nếu có) — gọi xuống Java
        # ---------------------------------------------------------------
        if platform == 'android' and webview_ok:
            try:
                from jnius import autoclass
                ZWM = autoclass('org.zauto.ZaloWebManager')
                PA = autoclass('org.kivy.android.PythonActivity')
                diag_json = ZWM.selfDiagnose(PA.mActivity)
                if diag_json:
                    try:
                        diag_data = json.loads(diag_json)
                    except Exception:
                        diag_data = {}

                    if diag_data.get('zMessengerFound'):
                        mark("PASS", "API nội bộ Zalo (zMessenger)", "đã tìm thấy — gửi/chốt qua API")
                    else:
                        mark("WARN", "API nội bộ Zalo (zMessenger)", "chưa tìm thấy — sẽ phải dùng double-click")

                    if diag_data.get('hasConversationList'):
                        mark("PASS", "Sidebar danh sách hội thoại", "đang hiển thị")
                    else:
                        mark("WARN", "Sidebar danh sách hội thoại", "không thấy — có thể đang ở màn hình QR/login")

                    last_msg_found = diag_data.get('lastMsgNodeFound')
                    if last_msg_found:
                        mark("PASS", "Tìm node tin nhắn cuối", "thành công")
                        bubble_w = diag_data.get('bubbleWidth', 0)
                        bubble_h = diag_data.get('bubbleHeight', 0)
                        if bubble_w and bubble_h:
                            mark("PASS", "Đo kích thước bong bóng tin", f"{bubble_w}x{bubble_h}px — double-click có toạ độ hợp lệ")
                        else:
                            mark("WARN", "Đo kích thước bong bóng tin", "kích thước 0 — double-click sẽ bấm sai vị trí")
                    else:
                        mark("WARN", "Tìm node tin nhắn cuối", "không có tin nào trong khung chat hiện tại")

                    is_login_screen = diag_data.get('isLoginScreen', False)
                    if is_login_screen:
                        mark("FAIL", "Màn hình hiện tại", "đang ở màn hình ĐĂNG NHẬP QR — cần quét lại")
                else:
                    mark("WARN", "Self-diagnose JS", "không nhận được phản hồi từ WebView")
            except Exception as e:
                mark("WARN", "Self-diagnose JS", f"chưa hỗ trợ hoặc lỗi: {e}")

        # ---------------------------------------------------------------
        # BƯỚC 11: GỬI TIN TEST THẬT vào (các) nhóm đang BẬT để kiểm tra toàn bộ
        # pipeline chốt cuốc từ đầu đến cuối (API → double-click → fallback).
        # Tin test có tiền tố rõ ràng [ZAUTO TEST] để không nhầm với cuốc thật.
        # Chỉ test trên nhóm đã có sẵn ít nhất 1 ride card (để lấy được conversation_id
        # thật) — KHÔNG bịa ID giả. Nếu nhóm bật nhưng chưa có tin nào, báo rõ lý do
        # bỏ qua, không coi là PASS.
        # ---------------------------------------------------------------
        try:
            enabled = [g for g, v in getattr(self, 'enabled_groups', {}).items() if v]
            if not getattr(self, 'is_linked', False):
                mark("INFO", "Test gửi tin thật", "bỏ qua — chưa liên kết Zalo")
            elif not enabled:
                mark("INFO", "Test gửi tin thật", "bỏ qua — chưa bật nhóm nào. Hãy TẮT các nhóm thật, " +
                     "chỉ BẬT 1 nhóm test riêng rồi chạy Deep Check lại để kiểm tra gửi thật.")
            elif platform != 'android':
                mark("INFO", "Test gửi tin thật", "bỏ qua — đang chạy trên PC, không có WebView Android")
            else:
                # Tìm 1 nhóm đang bật ĐÃ CÓ ride card (để lấy conversation_id thật, không bịa)
                target_group = None
                target_conv_id = None
                try:
                    ride_list = self.root.ids.ride_list
                    for card in list(ride_list.children):
                        g_text = getattr(card, 'group_text', '')
                        c_id = getattr(card, 'conversation_id', '')
                        if g_text in enabled and c_id:
                            target_group = g_text
                            target_conv_id = c_id
                            break
                except Exception:
                    pass

                if not target_group:
                    mark("WARN", "Test gửi tin thật", "có nhóm bật nhưng CHƯA có tin nào để lấy ID hội thoại — " +
                         "hãy gửi 1 tin bất kỳ vào nhóm test rồi chạy Deep Check lại")
                else:
                    test_text = f"[ZAUTO TEST] Deep Check {time.strftime('%H:%M:%S')} - vui lòng bỏ qua tin này"
                    sent_ok = False
                    fail_reason = ""
                    try:
                        from jnius import autoclass as _ac
                        _PA = _ac('org.kivy.android.PythonActivity')
                        _ZWM = _ac('org.zauto.ZaloWebManager')
                        _act = _PA.mActivity

                        # Dọn sạch hàng đợi pythonMsgQueue cũ liên quan đến chốt, để không đọc
                        # nhầm phản hồi của 1 lệnh chốt cuốc khác đang chạy song song
                        _ZWM.sendReplyToSpecificMessage(
                            _act, target_conv_id, "", test_text, "", time.strftime('%H:%M')
                        )

                        # Lắng nghe pythonMsgQueue tối đa 10 giây để bắt phản hồi THẬT từ Java
                        # (Chốt API QUOTE OK / Chốt DOM UI QUOTE OK / TRIGGER_VISION_FALLBACK)
                        wait_deadline = time.time() + 10.0
                        while time.time() < wait_deadline:
                            try:
                                raw = _ZWM.pythonMsgQueue.poll()
                            except Exception:
                                raw = None
                            if raw:
                                raw_str = str(raw)
                                if 'Chốt API QUOTE OK' in raw_str or 'Chốt DOM UI QUOTE OK' in raw_str or 'Đã chốt xong' in raw_str:
                                    sent_ok = True
                                    break
                                if 'TRIGGER_VISION_FALLBACK' in raw_str:
                                    fail_reason = "rơi vào Vision Fallback — double-click/API đều thất bại"
                                    break
                            time.sleep(0.2)
                    except Exception as e_send:
                        fail_reason = str(e_send)

                    if sent_ok:
                        mark("PASS", "Test gửi tin thật", f"đã gửi thành công vào nhóm '{target_group}'")
                    elif fail_reason:
                        mark("FAIL", "Test gửi tin thật", f"nhóm '{target_group}': {fail_reason}")
                    else:
                        mark("WARN", "Test gửi tin thật",
                             f"nhóm '{target_group}': không nhận được xác nhận trong 10s — " +
                             "có thể đã gửi nhưng JS chưa báo về kịp, hãy kiểm tra trong Zalo")
        except Exception as e:
            mark("FAIL", "Test gửi tin thật", str(e))

        # ---------------------------------------------------------------
        # BƯỚC 12: Dung lượng log + cảnh báo lỗi gần đây trong system.log
        # ---------------------------------------------------------------
        try:
            log_path = os.path.join(LOG_DIR, 'system.log')
            if os.path.exists(log_path):
                size_kb = os.path.getsize(log_path) / 1024.0
                mark("PASS", "File log hệ thống", f"{size_kb:.1f} KB tại {log_path}")
                # Đọc 50 dòng cuối, đếm số dòng ERROR gần đây
                try:
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        last_lines = f.readlines()[-200:]
                    recent_errors = [l.strip() for l in last_lines if " - ERROR - " in l]
                    if recent_errors:
                        mark("WARN", "Lỗi gần đây trong log", f"{len(recent_errors)} dòng ERROR trong 200 dòng cuối")
                        lines.append("   --- 5 lỗi gần nhất ---")
                        for e_line in recent_errors[-5:]:
                            lines.append(f"   {e_line}")
                    else:
                        mark("PASS", "Lỗi gần đây trong log", "không có dòng ERROR nào trong 200 dòng cuối")
                except Exception as e_read:
                    mark("WARN", "Đọc file log", str(e_read))
            else:
                mark("WARN", "File log hệ thống", "chưa được tạo")
        except Exception as e:
            mark("FAIL", "File log hệ thống", str(e))

        # ---------------------------------------------------------------
        # TỔNG KẾT
        # ---------------------------------------------------------------
        lines.append("=" * 50)
        if fail_count == 0 and warn_count == 0:
            summary = f"🎉 HOÀN HẢO: 0 lỗi, 0 cảnh báo. App đang hoạt động tốt."
        elif fail_count == 0:
            summary = f"✅ ỔN: 0 lỗi nghiêm trọng, {warn_count} cảnh báo nhẹ (xem chi tiết trên)."
        else:
            summary = f"❌ CÓ {fail_count} LỖI cần xử lý, {warn_count} cảnh báo. Đã tự sửa {fixed_count} lỗi an toàn."
        lines.append(summary)
        if fixed_count > 0:
            lines.append(f"🔧 Đã tự động thử khắc phục {fixed_count} vấn đề (reload webview/khởi tạo lại). Hãy kiểm tra lại sau ít giây.")
        lines.append("=" * 50)

        report_text = "\n".join(lines)

        def _show_result(dt):
            try:
                ids = self.root.ids
                if 'btn_run_diagnostics' in ids:
                    ids.btn_run_diagnostics.disabled = False
                    ids.btn_run_diagnostics.text = "🔍 KIỂM TRA HỆ THỐNG (DEEP CHECK)"
                if 'lbl_diag_status' in ids:
                    ids.lbl_diag_status.text = summary
                DiagnosticsPopup(report_text).open()
            except Exception as e:
                logger.error(f"Lỗi hiện popup Deep Check: {e}")
            finally:
                self._diag_running = False

        Clock.schedule_once(_show_result, 0)

    def save_config(self):
        """BẮT BUỘC ĐỌC UI VÀO BIẾN TRƯỚC KHI XUỐNG DB"""
        try:
            ids = self.root.ids
            if ids.get('inp_nhan'): self.config_data['nhan'] = ids.inp_nhan.text
            if ids.get('inp_loai'): self.config_data['loai'] = ids.inp_loai.text
            if ids.get('inp_reply'): self.config_data['reply_msg'] = ids.inp_reply.text
            if ids.get('inp_delay'): self.config_data['global_delay'] = ids.inp_delay.text
            if ids.get('sw_filter'): self.config_data['sw_filter'] = ids.sw_filter.active
            if ids.get('sw_auto_main'): self.config_data['sw_auto'] = ids.sw_auto_main.active
            
            # --- THÊM DÒNG LƯU TRẠNG THÁI NÚT GIỌNG NÓI ---
            if ids.get('sw_voice'): self.config_data['sw_voice'] = ids.sw_voice.active
            
            self.config_data['enabled_groups'] = self.enabled_groups
            self.config_data['is_linked'] = self.is_linked
            
            self.save_config_silent()
            self.safe_toast("Đã lưu cấu hình thành công!")
        except Exception as e:
            logger.error(f"Lỗi save_config: {e}")   

    def clear_history(self):
        self.root.ids.msg_history_list.clear_widgets()
        toast("Đã dọn dẹp tin nhắn.")

    def check_permissions_and_guide(self):
        """Hàm tự động quét quyền và điều hướng thông minh"""
        if platform == 'android':
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Settings = autoclass('android.provider.Settings')
                Intent = autoclass('android.content.Intent')
                
                context = PythonActivity.mActivity
                resolver = context.getContentResolver()
                
                # Lấy package name hiện tại (org.zauto.zauto)
                pkg_name = context.getPackageName() 
                
                acc_granted = False
                notif_granted = False
                
                # --- 1. KIỂM TRA QUYỀN TRỢ NĂNG (ACCESSIBILITY) ---
                # Đọc chuỗi các dịch vụ trợ năng đang được bật trên điện thoại
                acc_services = Settings.Secure.getString(resolver, "enabled_accessibility_services")
                if acc_services and f"{pkg_name}/org.zauto.ZaloAccessibility" in acc_services:
                    acc_granted = True
                    
                # --- 2. KIỂM TRA QUYỀN ĐỌC THÔNG BÁO (NOTIFICATION LISTENER) ---
                # Đọc chuỗi các dịch vụ nghe thông báo đang được bật
                notif_listeners = Settings.Secure.getString(resolver, "enabled_notification_listeners")
                if notif_listeners and f"{pkg_name}/org.zauto.ZaloNotificationService" in notif_listeners:
                    notif_granted = True

                # --- 3. XỬ LÝ ĐIỀU HƯỚNG ---
                if acc_granted and notif_granted:
                    # Nếu cả 2 quyền cốt lõi đã bật
                    toast("Tuyệt vời! Ứng dụng đã được cấp đầy đủ quyền.")
                
                elif not acc_granted:
                    # Nếu chưa bật Trợ Năng -> Dẫn thẳng vào mục Trợ Năng
                    toast("Vui lòng tìm và BẬT 'ZAuto VIP' trong phần Trợ Năng!")
                    intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(intent)
                
                elif not notif_granted:
                    # Nếu chưa bật Đọc Thông Báo -> Dẫn thẳng vào mục Quyền Thông Báo
                    toast("Vui lòng CHO PHÉP 'ZAuto VIP' đọc thông báo!")
                    intent = Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS")
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(intent)

            except Exception:
                print(traceback.format_exc())
                # Backup an toàn nếu điện thoại khách không hỗ trợ hàm check
                toast("Hãy tìm và cấp quyền cho ứng dụng ZAuto VIP")
                try:
                    PythonActivity.mActivity.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                except: pass

    def reload_zalo_web(self):
        if platform == 'android':
            autoclass('org.zauto.ZaloWebManager').reloadWeb(PythonActivity.mActivity)
            toast("Đang tải lại Zalo Web...")

    def show_update_popup(self, server_ver, update_note, apk_url):
        """Hiện popup cập nhật - responsive theo màn hình, đồng bộ style app"""
        # ScrollView bọc ngoài để máy nhỏ vẫn vuốt được
        root_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)

        main_layout = BoxLayout(
            orientation='vertical',
            padding=dp(15), spacing=dp(12),
            size_hint_y=None
        )
        main_layout.bind(minimum_height=main_layout.setter('height'))

        # --- TIÊU ĐỀ PHIÊN BẢN ---
        main_layout.add_widget(Label(
            text=f"[b]Phiên bản mới: v{server_ver}[/b]",
            markup=True, halign='center', valign='middle',
            color=(0.1, 0.1, 0.1, 1), bold=True,
            size_hint_y=None, height=dp(35)
        ))

        # --- NỘI DUNG GHI CHÚ CẬP NHẬT (tự co giãn theo text) ---
        note_lbl = Label(
            text=update_note,
            halign='center', valign='top',
            color=(0.3, 0.3, 0.3, 1),
            size_hint_y=None,
            text_size=(Window.width * 0.80, None)
        )
        note_lbl.bind(texture_size=lambda inst, val: setattr(inst, 'height', val[1] + dp(10)))
        main_layout.add_widget(note_lbl)

        # --- LABEL TIẾN TRÌNH TẢI ---
        self._update_progress_label = Label(
            text="",
            size_hint_y=None, height=dp(28),
            color=(0.1, 0.5, 0.8, 1),
            halign='center', valign='middle'
        )
        main_layout.add_widget(self._update_progress_label)

        # --- NÚT CẬP NHẬT NGAY (xanh, đồng bộ style app) ---
        btn_update = Button(
            text="⬇  CẬP NHẬT NGAY",
            size_hint_x=1, size_hint_y=None, height=dp(50),
            bold=True, font_size='16sp',
            background_normal='', background_color=(0.1, 0.5, 0.8, 1),
            color=(1, 1, 1, 1)
        )

        # --- NÚT BỎ QUA ---
        btn_skip = Button(
            text="Bỏ qua lần này",
            size_hint_x=1, size_hint_y=None, height=dp(42),
            background_normal='', background_color=(0.65, 0.65, 0.65, 1),
            color=(1, 1, 1, 1)
        )

        main_layout.add_widget(btn_update)
        main_layout.add_widget(btn_skip)
        # Khoảng đệm cuối tránh nút sát mép
        main_layout.add_widget(Label(size_hint_y=None, height=dp(8)))

        root_scroll.add_widget(main_layout)

        self._update_popup = Popup(
            title="🆕 Có bản cập nhật mới!",
            content=root_scroll,
            size_hint=(0.92, 0.55),   # 92% rộng, 55% cao màn hình -> vừa mọi máy
            auto_dismiss=False,
            background='',
            background_color=(1, 1, 1, 1),
            title_color=(0, 0, 0, 1),
            separator_color=(0.1, 0.5, 0.8, 1)
        )
        btn_update.bind(on_release=lambda x: self._start_download_apk(apk_url))
        btn_skip.bind(on_release=self._update_popup.dismiss)
        self._update_popup.open()

    def _start_download_apk(self, apk_url):
        # Đã đưa các import lên đầu file thì ở đây không cần nữa
        # Lưu vào cache thư mục ngoài để FileProvider có thể đọc được
        if platform == 'android':
            try:
                ctx = PythonActivity.mActivity
                save_path = os.path.join(ctx.getExternalCacheDir().getAbsolutePath(), 'update.apk')
            except:
                save_path = os.path.join(BASE_PATH, 'update.apk')
        else:
            save_path = os.path.join(BASE_PATH, 'update.apk')
        try:
            if os.path.exists(save_path):
                os.remove(save_path)
        except: 
            pass

        def download_thread():
            try:
                Clock.schedule_once(lambda dt: setattr(
                    self._update_progress_label, 'text', "Đang kết nối..."), 0)

                opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
                opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)

                req = urllib.request.Request(apk_url, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req, timeout=120)

                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0

                Clock.schedule_once(lambda dt: setattr(
                    self._update_progress_label, 'text', "Đang tải... 0%"), 0)

                with open(save_path, 'wb') as f:
                    while True:
                        block = response.read(8192)
                        if not block:
                            break
                        f.write(block)
                        downloaded += len(block)
                        if total_size > 0:
                            percent = min(int(downloaded * 100 / total_size), 99)
                            Clock.schedule_once(
                                lambda dt, p=percent: setattr(
                                    self._update_progress_label, 'text', f"Đang tải... {p}%"), 0)

                file_size = os.path.getsize(save_path)
                if file_size < 500 * 1024:  # hạ ngưỡng xuống 500KB
                    raise Exception(f"File quá nhỏ ({file_size} bytes) - tải thất bại")

                Clock.schedule_once(lambda dt: setattr(
                    self._update_progress_label, 'text', "✅ Tải xong! Đang mở cài đặt..."), 0)
                Clock.schedule_once(lambda dt: self._install_apk(save_path), 1.0)

            except Exception as e:
                err_detail = traceback.format_exc()
                logger.error(f"Lỗi tải APK:\n{err_detail}")
                try:
                    if os.path.exists(save_path):
                        os.remove(save_path)
                except: 
                    pass
                # Hiện lỗi chi tiết lên label
                Clock.schedule_once(lambda dt: setattr(
                    self._update_progress_label, 'text', f"❌ {str(e)[:120]}"), 0)

        # Khởi chạy luồng download
        threading.Thread(target=download_thread, daemon=False).start()


    def _install_apk(self, apk_path):
        if platform != 'android':
            toast(f"[PC] APK đã tải về: {apk_path}")
            return

        try:
            from jnius import autoclass
            File         = autoclass('java.io.File')
            IntentClass  = autoclass('android.content.Intent')
            Build        = autoclass('android.os.Build')
            activity     = PythonActivity.mActivity
            pkg          = activity.getPackageName()
            apk_file     = File(apk_path)

            if Build.VERSION.SDK_INT >= 24:
                FileProvider = autoclass('androidx.core.content.FileProvider')
                authority = f"{pkg}.fileprovider"
                try:
                    uri = FileProvider.getUriForFile(activity, authority, apk_file)
                except Exception:
                    uri = FileProvider.getUriForFile(activity, f"{pkg}.provider", apk_file)
            else:
                Uri = autoclass('android.net.Uri')
                uri = Uri.fromFile(apk_file)

            # Tạo intent cài APK — dùng IntentClass để không bị ghi đè
            install_intent = IntentClass(IntentClass.ACTION_VIEW)
            install_intent.setDataAndType(uri, "application/vnd.android.package-archive")
            install_intent.addFlags(IntentClass.FLAG_GRANT_READ_URI_PERMISSION)
            install_intent.addFlags(IntentClass.FLAG_ACTIVITY_NEW_TASK)
            install_intent.addFlags(IntentClass.FLAG_ACTIVITY_CLEAR_TOP)

            # Giữ Foreground Service sống — dùng tên biến KHÁC để không ghi đè install_intent
            try:
                _FgSvc = autoclass('org.zauto.ZaloForegroundService')
                _fg_intent = IntentClass(PythonActivity.mActivity, _FgSvc)
                PythonActivity.mActivity.startForegroundService(_fg_intent)
            except: pass

            # Chạy đúng intent cài APK (không bị ghi đè)
            activity.startActivity(install_intent)
            logger.info("Đã mở màn hình cài đặt APK")

            Clock.schedule_once(lambda dt: self._update_popup.dismiss()
                                if hasattr(self, '_update_popup') and self._update_popup else None, 1.5)

        except Exception as e:
            err = traceback.format_exc()
            logger.error(f"Lỗi _install_apk:\n{err}")
            Clock.schedule_once(lambda dt: setattr(
                self._update_progress_label, 'text', f"❌ Cài đặt lỗi: {str(e)[:100]}"), 0)
       
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_running = True
        self.is_radar_running = False  
        self.enabled_groups = {}       
        self.webview_inited = False
        self.webview_visible = False
        self._webview_timer = None 
        self.config_data = {}
        self.is_linked = False
        
        # Tối ưu RAM: Giảm Cache xuống 300 chống Leak
        self.processed_msg_hashes = LRUCache(maxsize=1000)
        self.global_last_reply = 0
        self.last_reply_time = LRUCache(maxsize=200)
        
        # QUEUE ĐA LUỒNG
        self.msg_queue = queue.Queue(maxsize=500)
        self.reply_queue = queue.Queue(maxsize=50)
        self.ui_queue = queue.Queue(maxsize=100) # Queue chuyên đẩy UI update chống Freeze Kivy
        self.audio_queue = queue.Queue(maxsize=50) # THÊM: Hàng đợi riêng cho tin nhắn thoại
        
        # LOCK SYSTEM CHUẨN
        self.reply_time_lock = threading.Lock()
        self.reply_lock = threading.Lock()
        self.worker_restart_lock = threading.Lock()
        self.toast_lock = threading.Lock()
        
        self._last_toast = 0
        self.gc_counter = 0
        self._restarting_msg_worker = False
        self._restarting_reply_worker = False
        self.last_webview_bounds = None
        self.node_process = None       # Lưu lại process Node.js để Deep Check kiểm tra sống/chết
        self._diag_running = False     # Chống bấm Deep Check nhiều lần chồng nhau
        Window.softinput_mode = "pan"  # Dùng pan thay below_target để tránh bàn phím bật lên tự động

    def safe_toast(self, msg):
        """Bảo vệ UI EventLoop khỏi spam toast"""
        with self.toast_lock:
            now = time.time()
            if now - self._last_toast < 1.5:
                return
            self._last_toast = now
        Clock.schedule_once(lambda dt: toast(msg), 0)

    def _process_ui_queue(self, dt):
        """Xử lý UI Update tập trung, chống Crash & Lag UI"""
        try:
            for _ in range(5): # Giới hạn 5 task / frame
                task, args = self.ui_queue.get_nowait()
                if task == 'add_ride':
                    self.add_ride_card(*args)
                elif task == 'log':
                    self.log_history(*args)
                elif task == 'toast':
                    self.safe_toast(*args)
                elif task == 'speak':
                    if platform == 'android':
                        try: autoclass('org.zauto.ZaloWebManager').speak(args)
                        except: pass
                # ĐÓN LỆNH XÓA THẺ KHI AUTO CHỐT THÀNH CÔNG VỚI MÃ KHÓA
                elif task == 'remove_by_key':
                    self.remove_ride_by_key(args)
                self.ui_queue.task_done()
        except queue.Empty:
            pass

    def remove_ride_by_key(self, cache_key):
        """Duyệt tìm thẻ cuốc xe trong danh sách theo mã khóa và xóa khỏi giao diện"""
        try:
            ride_list = self.root.ids.ride_list
            for card in list(ride_list.children):
                if getattr(card, 'cache_key', '') == cache_key:
                    self.remove_ride(card)
                    break # Xóa xong thẻ trùng khớp thì thoát vòng lặp ngay
        except Exception as e:
            logger.error(f"Lỗi remove_ride_by_key: {e}")

    def _init_webview_android(self):
        """Khởi tạo cấu trúc Webview chìm dưới Android"""
        if self.webview_inited: return
        if platform == 'android':
            try:
                activity = PythonActivity.mActivity
                autoclass('org.zauto.ZaloWebManager').initWebView(activity)
                self.webview_inited = True
                # Inject thủ công lần đầu sau 8 giây - bù cho onPageFinished chạy trước
                # (Dự phòng: nếu Zalo đã đăng nhập sẵn, onPageFinished chạy sớm hơn lúc JS được thêm vào)
                def _force_inject(dt):
                    try:
                        ZWM = autoclass('org.zauto.ZaloWebManager')
                        if ZWM.hiddenWebView is not None:
                            ZWM.injectSidebarObserver(ZWM.hiddenWebView)
                            logger.info("Force inject sidebar observer thành công")
                    except Exception as e:
                        logger.error(f"Force inject lỗi: {e}")
                Clock.schedule_once(_force_inject, 8.0)
            except Exception:
                print(traceback.format_exc())

    def set_webview_visible(self, is_visible):
        self.webview_visible = is_visible
        if is_visible:
            # 1. Ép giao diện cập nhật ngay lập tức
            self.update_profile_ui()
            
            # 2. Xóa cache toạ độ cũ để WebView vẽ lại đúng chỗ
            self.last_webview_bounds = None
            
            # 3. Kích hoạt bộ đếm thời gian đồng bộ toạ độ
            if not getattr(self, '_webview_timer', None):
                self._webview_timer = Clock.schedule_interval(self._sync_webview_pos, 0.2) # Tăng tốc độ đồng bộ

            def _do_resume(dt):
                if platform == 'android' and getattr(self, 'webview_inited', False):
                    try:
                        from jnius import autoclass
                        PythonActivity = autoclass('org.kivy.android.PythonActivity')
                        autoclass('org.zauto.ZaloWebManager').onResume(PythonActivity.mActivity)
                    except Exception: pass
            Clock.schedule_once(_do_resume, 0.5)
        else:
            # Khi rời Tab: Chỉ ẩn đi chứ TUYỆT ĐỐI không hủy WebView
            if getattr(self, '_webview_timer', None):
                self._webview_timer.cancel()
                self._webview_timer = None
            if platform == 'android' and self.webview_inited:
                self._hide_webview_overlay()

    @run_on_ui_thread
    def _hide_webview_overlay(self):
        try:
            autoclass('org.zauto.ZaloWebManager').updateWebViewBounds(PythonActivity.mActivity, 0, 0, 0, 0, False)
        except Exception: pass

    def _sync_webview_pos(self, dt):
        if platform != 'android' or not getattr(self, 'webview_inited', False) or not getattr(self, 'webview_visible', False): 
            return
        try:
            container = self.root.ids.webview_container
            
            # CHỐNG ANR: Không render Java Bounds nếu Widget đang nằm ngoài ViewTree
            if not container.get_root_window():
                return
                
            x, y = container.to_window(0, 0)
            w, h = container.size
            
            from kivy.core.window import Window
            android_y = Window.height - (y + h)
            
            new_bounds = (int(x), int(android_y), int(w), int(h))
            if new_bounds == getattr(self, 'last_webview_bounds', None):
                return
            if int(w) <= 0 or int(h) <= 0:
                return  # Container chưa layout xong, chờ tick tiếp theo
            
            self.last_webview_bounds = new_bounds
            
            activity = PythonActivity.mActivity
            autoclass('org.zauto.ZaloWebManager').updateWebViewBounds(
                activity, new_bounds[0], new_bounds[1], new_bounds[2], new_bounds[3], True
            )
        except Exception:
            pass
    def request_ignore_battery(self):
        if platform == 'android':
            from jnius import autoclass
            Context = autoclass('android.content.Context')
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            PowerManager = autoclass('android.os.PowerManager')
            
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            pm = activity.getSystemService(Context.POWER_SERVICE)
            
            if not pm.isIgnoringBatteryOptimizations(activity.getPackageName()):
                intent = Intent(autoclass('android.provider.Settings').ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                intent.setData(Uri.parse("package:" + activity.getPackageName()))
                activity.startActivity(intent)        
    def on_stop(self):
        self.app_running = False 
        
        # CHỐNG ZOMBIE THREAD: Ép Join luồng trước khi thoát
        try:
            if hasattr(self, 'msg_worker_thread') and self.msg_worker_thread:
                self.msg_worker_thread.join(timeout=2)
            if hasattr(self, 'reply_worker_thread') and self.reply_worker_thread:
                self.reply_worker_thread.join(timeout=2)
        except: pass
        
        if platform == 'android':
            try:
                # CHỐNG LEAK CONTEXT RECEIVER
                if hasattr(self, 'br'):
                    try:
                        self.br.stop()
                        self.br = None
                    except: pass
                    
                # 3. Dùng vòng while nhả triệt để reference counter của Wakelock
                if hasattr(self, 'wakelock') and self.wakelock is not None:
                    try:
                        while self.wakelock.isHeld():
                            self.wakelock.release()
                    except Exception as we: logger.error(f"Wakelock Error: {we}")

                # 4. Nhả triệt để Wifilock
                if hasattr(self, 'wifilock') and self.wifilock is not None:
                    try:
                        while self.wifilock.isHeld():
                            self.wifilock.release()
                    except Exception as wfe: logger.error(f"Wifilock Error: {wfe}")

            except Exception as e:
                logger.error(f"Lỗi dọn dẹp on_stop: {e}")
    def start_node_server(self):
            """Khởi động Node.js backend server.js (Hỗ trợ cả PC Windows và Android)"""
            import subprocess
            import shutil
            import os
            import threading
            
            try:
                base = os.path.dirname(os.path.abspath(__file__))
                server_script = os.path.join(base, 'nodejs_backend', 'server.js')
                node_cwd = os.path.join(base, 'nodejs_backend')

                if platform == 'android':
                    from jnius import autoclass
                    Build = autoclass('android.os.Build')
                    
                    # Xác định ABI ưu tiên
                    try:
                        abis = [str(Build.SUPPORTED_ABIS[i]) for i in range(Build.SUPPORTED_ABIS.length)]
                    except Exception:
                        abis = ['arm64-v8a']
                    abi = 'arm64-v8a' if 'arm64-v8a' in abis else abis[0]
                    
                    # Đường dẫn file libnode.so gốc (read-only)
                    src_node_bin = os.path.join(base, 'nodejs_backend', 'bin', abi, 'libnode.so')
                    
                    # Tạo thư mục writable nằm ngoài thư mục 'app' (lùi ra 1 cấp)
                    # Ví dụ: base là /data/data/.../files/app -> files_dir là /data/data/.../files
                    files_dir = os.path.dirname(base) 
                    writable_dir = os.path.join(files_dir, 'node_bin')
                    os.makedirs(writable_dir, exist_ok=True)
                    
                    # File thực thi đích
                    node_bin = os.path.join(writable_dir, 'node')
                    
                    if not os.path.exists(src_node_bin):
                        logger.error(f'Không tìm thấy node binary gốc tại: {src_node_bin}')
                        return
                    
                    # Chỉ copy và chmod nếu file đích chưa tồn tại 
                    # (hoặc bạn có thể thêm logic so sánh kích thước file để update phiên bản mới)
                    if not os.path.exists(node_bin):
                        shutil.copy2(src_node_bin, node_bin)
                        os.chmod(node_bin, 0o755)  # Cấp quyền thực thi trên thư mục writable
                        logger.info(f'Đã copy và chmod node binary sang: {node_bin}')
                else:
                    node_bin = 'node'  # Chạy trên PC bằng Node cài sẵn

                env = os.environ.copy()
                env['NODE_PATH'] = os.path.join(node_cwd, 'node_modules')
                is_windows = os.name == 'nt' and platform != 'android'

                proc = subprocess.Popen(
                    [node_bin, server_script],
                    cwd=node_cwd, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    shell=True if is_windows else False
                )
                self.node_process = proc  # Lưu lại để Deep Check kiểm tra tiến trình còn sống hay đã chết
                logger.info(f'Node.js server đã khởi động ngầm thành công, PID={proc.pid}')

                # Đọc luồng dữ liệu log tránh đầy bộ đệm treo tiến trình
                def log_stream(stream, prefix):
                    try:
                        for line in iter(stream.readline, b''):
                            msg = line.decode('utf-8', errors='ignore').strip()
                            if msg: logger.info(f'[{prefix}] {msg}')
                    except: pass
                    finally: stream.close()

                threading.Thread(target=log_stream, args=(proc.stdout, 'Node-Out'), daemon=True).start()
                threading.Thread(target=log_stream, args=(proc.stderr, 'Node-Err'), daemon=True).start()

            except Exception as e:
                logger.error(f'Lỗi nghiêm trọng khi khởi động Node server: {e}')
    
    def check_for_update(self):
        """Hàm tự động gửi yêu cầu kiểm tra phiên bản từ server Gist"""
        def on_success(req, result):
            try:
                import json
                
                # --- SỬA LỖI CHÍ MẠNG Ở ĐÂY ---
                # Kiểm tra nếu result là chuỗi (do GitHub trả về) thì ép kiểu nó thành Dictionary
                if isinstance(result, str):
                    data = json.loads(result)
                else:
                    data = result

                # Bây giờ dùng data.get() mới hoàn toàn an toàn
                server_ver = float(data.get("version", 1.0))
                update_note = str(data.get("note", "Vui lòng cập nhật phiên bản mới để tiếp tục sử dụng."))
                apk_download_url = str(data.get("url", ""))
                
                # Nếu bản trên mạng lớn hơn bản trong máy
                if server_ver > float(self.APP_VERSION):
                    # Kích hoạt popup hiển thị trên luồng chính UI
                    from kivy.clock import Clock
                    Clock.schedule_once(lambda dt: self.show_update_popup(server_ver, update_note, apk_download_url), 0.5)
            except Exception as e:
                logger.error(f"Lỗi xử lý dữ liệu update: {e}")

        def on_error(req, error):
            logger.error(f"Không thể kết nối máy chủ update: {error}")

        try:
            import time
            from kivy.network.urlrequest import UrlRequest
            
            # --- SỬA LỖI CACHE Ở ĐÂY ---
            # Thêm mốc thời gian vào cuối link để ép điện thoại luôn tải file mới nhất, không bị dính cache
            no_cache_url = f"{self.UPDATE_URL}?t={int(time.time())}"
            
            # Gửi request ngầm không lo treo app
            UrlRequest(no_cache_url, on_success=on_success, on_error=on_error, on_failure=on_error, timeout=10)
        except Exception as e:
            logger.error(f"Lỗi gọi UrlRequest: {e}")

if __name__ == '__main__':
    ZAutoProApp().run()
