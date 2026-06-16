// ─────────────────────────────────────────────
// TẤT CẢ IMPORT PHẢI ĐẶT TRÊN CÙNG (ESM RULE)
// ─────────────────────────────────────────────
import express from 'express';
import fs from 'fs';
import path from 'path';
import https from 'https';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';
import { Zalo, LoginQRCallbackEventType } from 'zalo-api-final';

const require = createRequire(import.meta.url);

// ─────────────────────────────────────────────
// BẢN VÁ COOKIE — SỬA LỖI DOMAIN ZALO
// ─────────────────────────────────────────────
function applyCookiePatch(CookieJarClass) {
    if (!CookieJarClass || CookieJarClass.__patched) return;

    function normalizeZaloUrl(urlStr) {
        if (urlStr.includes('id.zalo.me')) return urlStr.replace('id.zalo.me', 'chat.zalo.me');
        if (urlStr.includes('jr.chat.zalo.me')) return urlStr.replace('jr.chat.zalo.me', 'chat.zalo.me');
        if (urlStr.includes('stc-zlogin.zdn.vn')) return 'https://chat.zalo.me/';
        return urlStr;
    }

    const _origSetCookie = CookieJarClass.prototype.setCookie;
    CookieJarClass.prototype.setCookie = function(cookie, url, options, cb) {
        if (typeof options === 'function') { cb = options; options = {}; }
        options = options || {};
        options.ignoreError = true;
        let urlStr = typeof url === 'string' ? url : (url?.href || String(url));
        // Lưu cookie vào CẢ HAI domain để mọi subdomain đều đọc được
        if (urlStr.includes('id.zalo.me')) {
            try { _origSetCookie.call(this, cookie, urlStr.replace('id.zalo.me', 'chat.zalo.me'), options, ()=>{}); } catch(e) {}
        } else if (urlStr.includes('chat.zalo.me') && !urlStr.includes('jr.')) {
            try { _origSetCookie.call(this, cookie, urlStr.replace('chat.zalo.me', 'id.zalo.me'), options, ()=>{}); } catch(e) {}
        }
        return _origSetCookie.call(this, cookie, url, options, cb);
    };

    const _origSetCookieSync = CookieJarClass.prototype.setCookieSync;
    CookieJarClass.prototype.setCookieSync = function(cookie, url, options) {
        options = options || {};
        options.ignoreError = true;
        let urlStr = typeof url === 'string' ? url : (url?.href || String(url));
        if (urlStr.includes('id.zalo.me')) {
            try { _origSetCookieSync.call(this, cookie, urlStr.replace('id.zalo.me', 'chat.zalo.me'), options); } catch(e) {}
        } else if (urlStr.includes('chat.zalo.me') && !urlStr.includes('jr.')) {
            try { _origSetCookieSync.call(this, cookie, urlStr.replace('chat.zalo.me', 'id.zalo.me'), options); } catch(e) {}
        }
        return _origSetCookieSync.call(this, cookie, url, options);
    };

    const _origGetCookies = CookieJarClass.prototype.getCookies;
    CookieJarClass.prototype.getCookies = function(url, options, cb) {
        if (typeof options === 'function') { cb = options; options = {}; }
        options = options || {};
        let urlStr = typeof url === 'string' ? url : (url?.href || String(url));
        return _origGetCookies.call(this, normalizeZaloUrl(urlStr), options, cb);
    };

    const _origGetCookiesSync = CookieJarClass.prototype.getCookiesSync;
    CookieJarClass.prototype.getCookiesSync = function(url, options) {
        options = options || {};
        let urlStr = typeof url === 'string' ? url : (url?.href || String(url));
        return _origGetCookiesSync.call(this, normalizeZaloUrl(urlStr), options);
    };

    const _origGetCookieString = CookieJarClass.prototype.getCookieString;
    CookieJarClass.prototype.getCookieString = function(url, options, cb) {
        if (typeof options === 'function') { cb = options; options = {}; }
        options = options || {};
        let urlStr = typeof url === 'string' ? url : (url?.href || String(url));
        return _origGetCookieString.call(this, normalizeZaloUrl(urlStr), options, cb);
    };

    const _origGetCookieStringSync = CookieJarClass.prototype.getCookieStringSync;
    CookieJarClass.prototype.getCookieStringSync = function(url, options) {
        options = options || {};
        let urlStr = typeof url === 'string' ? url : (url?.href || String(url));
        return _origGetCookieStringSync.call(this, normalizeZaloUrl(urlStr), options);
    };

    CookieJarClass.__patched = true;
    console.log("✅ ZAUTO: Kích hoạt khiên chống lỗi Zalo API (Max Level)!");
}

try { applyCookiePatch(require('zalo-api-final/node_modules/tough-cookie').CookieJar); } catch (e) {}
try { applyCookiePatch(require('tough-cookie').CookieJar); } catch (e) {}

// ─────────────────────────────────────────────
// PATCH HTTPS — GẮN COOKIE VÀO jr.chat.zalo.me
// global._zaloCookieJar được set ngay sau khi login thành công
// ─────────────────────────────────────────────
const _origHttpsRequest = https.request.bind(https);
https.request = function(urlOrOptions, optionsOrCb, cb) {
    try {
        let opts = typeof urlOrOptions === 'string' || urlOrOptions instanceof URL
            ? (typeof optionsOrCb === 'object' ? optionsOrCb : {})
            : urlOrOptions;
        let hostname = opts.hostname || opts.host || '';
        if (typeof urlOrOptions === 'string') {
            try { hostname = new URL(urlOrOptions).hostname; } catch(e) {}
        } else if (urlOrOptions instanceof URL) {
            hostname = urlOrOptions.hostname;
        }
        if (hostname.includes('jr.chat.zalo.me') || hostname.includes('jr.zalo.me')) {
            if (global._zaloCookieJar) {
                try {
                    const cookies = global._zaloCookieJar.getCookiesSync('https://chat.zalo.me/');
                    const cookieStr = cookies.map(c => c.cookieString()).join('; ');
                    if (cookieStr) {
                        if (typeof opts === 'object') {
                            opts.headers = opts.headers || {};
                            opts.headers['cookie'] = cookieStr;
                        }
                    }
                } catch(e) {}
            }
        }
    } catch(e) {}
    return _origHttpsRequest(urlOrOptions, optionsOrCb, cb);
};

// ─────────────────────────────────────────────
// KHỞI TẠO BIẾN VÀ EXPRESS
// ─────────────────────────────────────────────
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(express.json());
app.use(express.static(__dirname));

const zalo = new Zalo({ selfListen: false, checkUpdate: false, logging: true });
let api = null;
let eventQueue = [];
let currentUserInfo = { name: 'ZAuto (Đã kết nối)', avatar: 'profile.jpg' };
let groupCacheMap = {};

function saveSession() {
    try {
        const ctx = api.getContext();
        const sessionData = {
            cookie: ctx.cookie.toJSON().cookies, imei: ctx.imei,
            userAgent: ctx.userAgent, userInfo: currentUserInfo
        };
        fs.writeFileSync('cookie.json', JSON.stringify(sessionData, null, 2));
        console.log('✅ Đã lưu session và Profile vào cookie.json');
    } catch (e) {
        console.error('❌ Lỗi lưu session:', e);
    }
}

// ─────────────────────────────────────────────
// SET global._zaloCookieJar SAU KHI LOGIN
// ─────────────────────────────────────────────
function setCookieJarGlobal() {
    try {
        const ctx = api.getContext();
        if (ctx && ctx.cookie) {
            global._zaloCookieJar = ctx.cookie;
            console.log('✅ Đã set global._zaloCookieJar cho patch jr.chat.zalo.me');
        }
    } catch(e) {
        console.error('❌ Lỗi set cookie jar global:', e);
    }
}

function startListener() {
    api.listener.on('connected', () => console.log('🔌 WebSocket đã kết nối!'));
    api.listener.on('disconnected', (reason) => console.warn('⚠️ WebSocket ngắt kết nối:', reason));
    api.listener.on('error', (err) => console.error('❌ Lỗi listener:', err));

    api.listener.on('message', (msg) => {
        if (msg.isSelf) return;
        const content = msg.data.content;
        const msgType = msg.data.msgType;
        const isGroup = msg.type === 1;
        const realGroupName = groupCacheMap[msg.threadId] || msg.threadId;

        if (typeof content === 'string' && content.trim() !== '') {
            eventQueue.push({ action: 'WEB_NEW_MSG', data: { msg_type: 'text', group_id: msg.threadId, group_name: realGroupName, sender_id: msg.data.uidFrom, sender_name: msg.data.dName || '', text: content, msg_id: msg.data.msgId, is_group: isGroup, raw_msg_type: msgType }});
        }
        if (msgType === 'chat.voice' && typeof content === 'object' && content !== null) {
            const voiceUrl = content.href || content.fileUrl || '';
            if (voiceUrl) {
                eventQueue.push({ action: 'WEB_NEW_VOICE', data: { msg_type: 'voice', group_id: msg.threadId, group_name: realGroupName, sender_id: msg.data.uidFrom, sender_name: msg.data.dName || '', voice_url: voiceUrl, msg_id: msg.data.msgId, is_group: isGroup, raw_data: { content: msg.data.content, msgType: msg.data.msgType, msgId: msg.data.msgId, cliMsgId: msg.data.cliMsgId, ts: msg.data.ts, ttl: msg.data.ttl, uidFrom: msg.data.uidFrom, propertyExt: msg.data.propertyExt } }});
            }
        }
        if (msgType === 'chat.photo' && typeof content === 'object' && content !== null) {
            const photoUrl = content.href || content.normalUrl || content.hdUrl || '';
            if (photoUrl) {
                eventQueue.push({ action: 'WEB_NEW_PHOTO', data: { msg_type: 'photo', group_id: msg.threadId, group_name: realGroupName, sender_id: msg.data.uidFrom, sender_name: msg.data.dName || '', photo_url: photoUrl, msg_id: msg.data.msgId, is_group: isGroup, raw_data: { content: msg.data.content, msgType: msg.data.msgType, msgId: msg.data.msgId, cliMsgId: msg.data.cliMsgId, ts: msg.data.ts, ttl: msg.data.ttl, uidFrom: msg.data.uidFrom, propertyExt: msg.data.propertyExt } }});
            }
        }
    });

    api.listener.start({ retryOnClose: true });
    console.log('👂 Đang lắng nghe tin nhắn Zalo...');
}

async function startZalo() {
    try {
        if (fs.existsSync('cookie.json')) {
            console.log('✅ Tìm thấy phiên đăng nhập cũ, đang đăng nhập...');
            const savedData = JSON.parse(fs.readFileSync('cookie.json', 'utf8'));
            if (savedData.userInfo) currentUserInfo = savedData.userInfo;
            api = await zalo.login({ cookie: savedData.cookie, imei: savedData.imei, userAgent: savedData.userAgent });
            console.log('✅ Đăng nhập cookie thành công!');
            setCookieJarGlobal(); // ← SET NGAY SAU LOGIN
            saveSession();
        } else {
            console.log('⚠️ Chưa có phiên đăng nhập, đang tạo mã QR...');
            api = await zalo.loginQR({ qrPath: './qr.png' }, (event) => {
                if (event.type === LoginQRCallbackEventType.QRCodeGenerated) {
                    event.actions.saveToFile('./qr.png').then(() => {
                        setTimeout(() => { eventQueue.push({ action: 'REQUIRE_QR', data: { url: `http://127.0.0.1:5000/qr.png?t=${Date.now()}` } }); }, 1500);
                    });
                }
                if (event.type === LoginQRCallbackEventType.QRCodeExpired) {
                    console.log('⏰ QR hết hạn, đang tạo lại...');
                    eventQueue.push({ action: 'QR_EXPIRED', data: {} });
                    event.actions.retry();
                }
                if (event.type === LoginQRCallbackEventType.QRCodeScanned) {
                    console.log('📱 Đã quét QR:', event.data.display_name);
                    currentUserInfo = { name: event.data.display_name, avatar: event.data.avatar };
                    eventQueue.push({ action: 'QR_SCANNED', data: currentUserInfo });
                }
                if (event.type === LoginQRCallbackEventType.QRCodeDeclined) {
                    console.log('❌ Người dùng từ chối đăng nhập');
                    eventQueue.push({ action: 'QR_DECLINED', data: {} });
                }
            });
            setCookieJarGlobal(); // ← SET NGAY SAU LOGIN QR
            saveSession();
            console.log('✅ Đăng nhập QR thành công!');
        }

        eventQueue.push({ action: 'LOGIN_SUCCESS', data: currentUserInfo });

        const groups = await api.getAllGroups();
        if (groups && groups.gridVerMap) {
            const allGroupIds = Object.keys(groups.gridVerMap);
            console.log(`📋 Tìm thấy ${allGroupIds.length} nhóm. Đang lấy thông tin...`);
            let groupDetails = [];
            try {
                const batchInfo = await api.getGroupInfo(allGroupIds);
                if (batchInfo && batchInfo.gridInfoMap) {
                    for (const gid of allGroupIds) {
                        const info = batchInfo.gridInfoMap[gid];
                        let gName = (info && info.name) ? info.name : `Nhóm ${gid}`;
                        let gAvt = (info && (info.avt || info.fullAvt)) ? (info.avt || info.fullAvt) : 'profile.jpg';
                        groupCacheMap[gid] = gName;
                        groupDetails.push({ id: gid, name: gName, avatar: gAvt });
                    }
                }
            } catch (e) {
                console.error("Lỗi lấy danh sách nhóm:", e);
                groupDetails = allGroupIds.map(gid => ({ id: gid, name: `Nhóm ${gid}`, avatar: 'profile.jpg' }));
            }
            eventQueue.push({ action: 'GROUPS_DATA', data: { groups: groupDetails } });
            console.log(`✅ Đã gửi danh sách nhóm lên App!`);
        }

        startListener();

    } catch (error) {
        console.error('❌ Lỗi khởi động Zalo:', error);
        eventQueue.push({ action: 'LOGIN_ERROR', data: { error: String(error) } });
    }
}

app.get('/api/events', (req, res) => { res.json({ events: eventQueue }); eventQueue = []; });

app.get('/health', (req, res) => { res.sendStatus(200); });

app.post('/api/cookie_login', async (req, res) => {
    try {
        const { raw_cookie, imei, user_agent } = req.body;
        if (!raw_cookie) return res.status(400).json({error: 'Thiếu cookie'});

        if (fs.existsSync('cookie.json')) fs.unlinkSync('cookie.json');
        if (api) { try { api.listener.stop(); } catch(e){} api = null; }

        console.log('🔄 Đang chuyển đổi dữ liệu từ WebView...');
        const tempZalo = new Zalo({ selfListen: false, checkUpdate: false, logging: true });
        api = await tempZalo.login({ cookie: raw_cookie, imei: imei || undefined, userAgent: user_agent || undefined });

        setCookieJarGlobal(); // ← SET NGAY SAU LOGIN WEBVIEW

        currentUserInfo = { name: 'ZAuto (Từ WebView)', avatar: 'profile.jpg' };
        const sessionData = { cookie: api.getContext().cookie.toJSON().cookies, imei: api.getContext().imei, userAgent: api.getContext().userAgent, userInfo: currentUserInfo };
        fs.writeFileSync('cookie.json', JSON.stringify(sessionData, null, 2));

        eventQueue.push({ action: 'LOGIN_SUCCESS', data: currentUserInfo });

        const groups = await api.getAllGroups();
        if (groups && groups.gridVerMap) {
            const allGroupIds = Object.keys(groups.gridVerMap);
            let groupDetails = [];
            try {
                const batchInfo = await api.getGroupInfo(allGroupIds);
                if (batchInfo && batchInfo.gridInfoMap) {
                    for (const gid of allGroupIds) {
                        const info = batchInfo.gridInfoMap[gid];
                        let gName = (info && info.name) ? info.name : `Nhóm ${gid}`;
                        let gAvt = (info && (info.avt || info.fullAvt)) ? (info.avt || info.fullAvt) : 'profile.jpg';
                        groupCacheMap[gid] = gName;
                        groupDetails.push({ id: gid, name: gName, avatar: gAvt });
                    }
                }
            } catch(e) {
                console.error("Lỗi lấy danh sách nhóm:", e);
                groupDetails = allGroupIds.map(gid => ({ id: gid, name: `Nhóm ${gid}`, avatar: 'profile.jpg' }));
            }
            eventQueue.push({ action: 'GROUPS_DATA', data: { groups: groupDetails } });
        }

        startListener();
        res.json({status: 'success'});
    } catch (e) {
        console.error('❌ Lỗi xử lý WebView Data:', e);
        res.status(500).json({error: String(e)});
    }
});

app.post('/api/reply', async (req, res) => {
    if (!api) return res.status(400).json({ error: 'Chưa kết nối Zalo' });
    try {
        const { message, group_id, quote_raw_data, is_group } = req.body;
        let messageContent;
        if (quote_raw_data) {
            messageContent = {
                msg: message,
                quote: {
                    content: typeof quote_raw_data.content === 'object' ? JSON.stringify(quote_raw_data.content) : quote_raw_data.content,
                    msgType: quote_raw_data.msgType, propertyExt: quote_raw_data.propertyExt,
                    uidFrom: quote_raw_data.uidFrom, msgId: quote_raw_data.msgId,
                    cliMsgId: quote_raw_data.cliMsgId, ts: quote_raw_data.ts, ttl: quote_raw_data.ttl || 0
                }
            };
        } else {
            messageContent = { msg: message };
        }
        await api.sendMessage(messageContent, String(group_id), is_group ? 1 : 0);
        res.json({ status: 'success' });
    } catch (error) {
        console.error('❌ Lỗi gửi tin:', error);
        res.status(500).json({ error: String(error) });
    }
});

app.post('/api/restart', async (req, res) => {
    try {
        if (fs.existsSync('cookie.json')) fs.unlinkSync('cookie.json');
        if (api) { try { api.listener.stop(); } catch (_) {} api = null; }
        global._zaloCookieJar = null; // Reset cookie jar khi restart
        res.json({ status: 'restarting' });
        setTimeout(startZalo, 500);
    } catch (e) { res.status(500).json({ error: String(e) }); }
});

app.listen(5000, '127.0.0.1', () => {
    console.log('⚡ Server chạy ở cổng 5000...');
    startZalo();
});
